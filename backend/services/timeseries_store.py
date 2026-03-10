"""
PostgreSQL Time-Series Store for StockPulse

Handles storage and retrieval of time-series data across 14 tables:
- prices_daily, derived_metrics_daily, technical_indicators,
  ml_features_daily, risk_metrics, valuation_daily,
  fundamentals_quarterly, shareholding_quarterly,
  corporate_actions, macro_indicators, derivatives_daily,
  intraday_metrics, weekly_metrics, schema_migrations

Uses asyncpg for high-performance async PostgreSQL access.
"""

import asyncpg
import json
import logging
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _parse_date(val) -> Optional[date]:
    """Safely parse a date value. Returns None for empty/invalid strings."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
        return datetime.strptime(val, "%Y-%m-%d").date()
    return None


class TimeSeriesStore:
    """
    Async PostgreSQL storage for time-series financial data.
    
    Uses asyncpg connection pool for efficient async operations.
    Designed to complement MongoDB (entity store) for time-indexed data.
    """
    
    def __init__(self, dsn: str = "postgresql://localhost:5432/stockpulse_ts"):
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None
        self._is_initialized = False
    
    async def initialize(self):
        """Create connection pool and verify schema."""
        if self._is_initialized:
            return
        
        try:
            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=2,
                max_size=10,
                command_timeout=30,
            )
            # Verify connection
            async with self._pool.acquire() as conn:
                version = await conn.fetchval("SELECT version()")
                logger.info(f"✅ PostgreSQL time-series store connected: {version[:50]}...")
                
                # Verify tables exist
                tables = await conn.fetch(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
                table_names = [t["table_name"] for t in tables]
                logger.info(f"Available tables: {table_names}")
            
            self._is_initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize time-series store: {e}")
            raise
    
    async def close(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
        self._is_initialized = False
    
    # ========================
    # Prices Daily
    # ========================
    
    async def upsert_prices(self, records: List[Dict[str, Any]]) -> int:
        """
        Insert or update daily price records.
        
        Args:
            records: List of dicts with keys matching BhavcopyData.to_dict()
                     Required: symbol, date, open, high, low, close, volume
        
        Returns:
            Number of records upserted.
        """
        if not records:
            return 0
        
        query = """
            INSERT INTO prices_daily (
                symbol, date, open, high, low, close, adjusted_close, last, prev_close,
                volume, turnover, total_trades, delivery_qty, delivery_pct,
                vwap, isin, series
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
            ON CONFLICT (symbol, date)
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                adjusted_close = COALESCE(EXCLUDED.adjusted_close, prices_daily.adjusted_close),
                last = EXCLUDED.last,
                prev_close = EXCLUDED.prev_close,
                volume = EXCLUDED.volume,
                turnover = EXCLUDED.turnover,
                total_trades = EXCLUDED.total_trades,
                delivery_qty = EXCLUDED.delivery_qty,
                delivery_pct = EXCLUDED.delivery_pct,
                vwap = EXCLUDED.vwap,
                isin = EXCLUDED.isin,
                series = EXCLUDED.series
        """

        count = 0
        async with self._pool.acquire() as conn:
            # Use a transaction for batch insert
            async with conn.transaction():
                for record in records:
                    try:
                        date_val = _parse_date(record.get("date"))
                        adj_close = record.get("adjusted_close")
                        if adj_close is not None:
                            adj_close = float(adj_close)

                        await conn.execute(
                            query,
                            record.get("symbol", ""),
                            date_val,
                            float(record.get("open", 0) or 0),
                            float(record.get("high", 0) or 0),
                            float(record.get("low", 0) or 0),
                            float(record.get("close", 0) or 0),
                            adj_close,
                            float(record.get("last", 0) or 0),
                            float(record.get("prev_close", 0) or 0),
                            int(record.get("volume", 0) or 0),
                            float(record.get("turnover", 0) or 0),
                            int(record.get("total_trades", 0) or 0),
                            int(record.get("delivery_quantity", record.get("delivery_qty", 0)) or 0),
                            float(record.get("delivery_percentage", record.get("delivery_pct", 0)) or 0),
                            float(record.get("vwap", 0) or 0),
                            record.get("isin", ""),
                            record.get("series", "EQ"),
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error upserting price for {record.get('symbol')}: {e}")
        
        return count
    
    async def get_prices(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Get daily price history for a symbol.
        
        Args:
            symbol: Stock symbol
            start_date: Start date (YYYY-MM-DD), inclusive
            end_date: End date (YYYY-MM-DD), inclusive
            limit: Max rows to return
        
        Returns:
            List of price records, newest first
        """
        conditions = ["symbol = $1"]
        params: list = [symbol]
        idx = 2
        
        if start_date:
            sd = _parse_date(start_date)
            if sd:
                conditions.append(f"date >= ${idx}")
                params.append(sd)
                idx += 1
        if end_date:
            ed = _parse_date(end_date)
            if ed:
                conditions.append(f"date <= ${idx}")
                params.append(ed)
                idx += 1

        where = " AND ".join(conditions)
        query = f"""
            SELECT symbol, date, open, high, low, close, adjusted_close, last, prev_close,
                   volume, turnover, total_trades, delivery_qty, delivery_pct,
                   vwap, isin, series
            FROM prices_daily
            WHERE {where}
            ORDER BY date DESC
            LIMIT {limit}
        """
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]
    
    async def get_latest_price_date(self, symbol: str) -> Optional[date]:
        """Get the most recent date for which we have price data."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT MAX(date) FROM prices_daily WHERE symbol = $1", symbol
            )
    
    async def get_price_count(self, symbol: Optional[str] = None) -> int:
        """Get total number of price records."""
        async with self._pool.acquire() as conn:
            if symbol:
                return await conn.fetchval(
                    "SELECT COUNT(*) FROM prices_daily WHERE symbol = $1", symbol
                )
            return await conn.fetchval("SELECT COUNT(*) FROM prices_daily")
            
    async def get_weekly_prices(
        self, symbol: str, limit: int = 150
    ) -> List[Dict[str, Any]]:
        """
        Get weekly aggregated price history for a symbol.
        Uses plain-Postgres aggregation from prices_daily (no TimescaleDB required).
        Each week starts on Monday (ISO week). Open = first day's open, Close = last day's close.
        """
        query = f"""
            SELECT
                $1::text AS symbol,
                date_trunc('week', date)::date AS date,
                (ARRAY_AGG(open ORDER BY date ASC))[1] AS open,
                MAX(high) AS high,
                MIN(low) AS low,
                (ARRAY_AGG(close ORDER BY date DESC))[1] AS close,
                SUM(volume) AS volume
            FROM prices_daily
            WHERE symbol = $1
            GROUP BY date_trunc('week', date)
            ORDER BY date DESC
            LIMIT {limit}
        """
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(query, symbol)
                return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to aggregate weekly prices: {e}")
            return []

    async def get_monthly_prices(
        self, symbol: str, limit: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Get monthly aggregated price history for a symbol.
        Uses plain-Postgres aggregation from prices_daily (no TimescaleDB required).
        Open = first day's open, Close = last day's close.
        """
        query = f"""
            SELECT
                $1::text AS symbol,
                date_trunc('month', date)::date AS date,
                (ARRAY_AGG(open ORDER BY date ASC))[1] AS open,
                MAX(high) AS high,
                MIN(low) AS low,
                (ARRAY_AGG(close ORDER BY date DESC))[1] AS close,
                SUM(volume) AS volume
            FROM prices_daily
            WHERE symbol = $1
            GROUP BY date_trunc('month', date)
            ORDER BY date DESC
            LIMIT {limit}
        """
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(query, symbol)
                return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to aggregate monthly prices: {e}")
            return []
    
    # ========================
    # Technical Indicators
    # ========================
    
    async def upsert_technicals(self, records: List[Dict[str, Any]]) -> int:
        """Insert or update technical indicator records (all 27 columns from schema)."""
        if not records:
            return 0

        query = """
            INSERT INTO technical_indicators (
                symbol, date, sma_20, sma_50, sma_200, ema_12, ema_26,
                rsi_14, macd, macd_signal, macd_histogram,
                bollinger_upper, bollinger_lower,
                atr_14, adx_14, obv, support_level, resistance_level,
                ichimoku_tenkan, ichimoku_kijun, ichimoku_senkou_a, ichimoku_senkou_b,
                stoch_k, stoch_d, cci_20, williams_r, cmf
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27)
            ON CONFLICT (symbol, date)
            DO UPDATE SET
                sma_20 = EXCLUDED.sma_20, sma_50 = EXCLUDED.sma_50,
                sma_200 = EXCLUDED.sma_200, ema_12 = EXCLUDED.ema_12,
                ema_26 = EXCLUDED.ema_26, rsi_14 = EXCLUDED.rsi_14,
                macd = EXCLUDED.macd, macd_signal = EXCLUDED.macd_signal,
                macd_histogram = EXCLUDED.macd_histogram,
                bollinger_upper = EXCLUDED.bollinger_upper,
                bollinger_lower = EXCLUDED.bollinger_lower,
                atr_14 = EXCLUDED.atr_14, adx_14 = EXCLUDED.adx_14,
                obv = EXCLUDED.obv, support_level = EXCLUDED.support_level,
                resistance_level = EXCLUDED.resistance_level,
                ichimoku_tenkan = EXCLUDED.ichimoku_tenkan,
                ichimoku_kijun = EXCLUDED.ichimoku_kijun,
                ichimoku_senkou_a = EXCLUDED.ichimoku_senkou_a,
                ichimoku_senkou_b = EXCLUDED.ichimoku_senkou_b,
                stoch_k = EXCLUDED.stoch_k, stoch_d = EXCLUDED.stoch_d,
                cci_20 = EXCLUDED.cci_20, williams_r = EXCLUDED.williams_r,
                cmf = EXCLUDED.cmf
        """

        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for r in records:
                    try:
                        date_val = _parse_date(r.get("date"))

                        await conn.execute(
                            query,
                            r.get("symbol", ""),
                            date_val,
                            r.get("sma_20"), r.get("sma_50"), r.get("sma_200"),
                            r.get("ema_12"), r.get("ema_26"), r.get("rsi_14"),
                            r.get("macd"), r.get("macd_signal"), r.get("macd_histogram"),
                            r.get("bollinger_upper"), r.get("bollinger_lower"),
                            r.get("atr_14"), r.get("adx_14"), r.get("obv"),
                            r.get("support_level"), r.get("resistance_level"),
                            r.get("ichimoku_tenkan"), r.get("ichimoku_kijun"),
                            r.get("ichimoku_senkou_a"), r.get("ichimoku_senkou_b"),
                            r.get("stoch_k"), r.get("stoch_d"),
                            r.get("cci_20"), r.get("williams_r"), r.get("cmf"),
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error upserting technicals for {r.get('symbol')}: {e}")

        return count
    
    async def get_technicals(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Get technical indicators for a symbol."""
        conditions = ["symbol = $1"]
        params: list = [symbol]
        idx = 2
        
        if start_date:
            conditions.append(f"date >= ${idx}")
            params.append(_parse_date(start_date))
            idx += 1
        if end_date:
            conditions.append(f"date <= ${idx}")
            params.append(_parse_date(end_date))
            idx += 1
        
        where = " AND ".join(conditions)
        query = f"""
            SELECT * FROM technical_indicators
            WHERE {where}
            ORDER BY date DESC
            LIMIT {limit}
        """
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]
    
    # ========================
    # Fundamentals Quarterly
    # ========================
    
    async def upsert_fundamentals(self, records: List[Dict[str, Any]]) -> int:
        """Insert or update quarterly fundamental records (all 55 columns from schema)."""
        if not records:
            return 0

        # All columns matching fundamentals_quarterly schema
        FUND_COLS = [
            "revenue", "revenue_growth_yoy", "revenue_growth_qoq",
            "operating_profit", "operating_margin", "gross_profit", "gross_margin",
            "net_profit", "net_profit_margin", "eps", "eps_growth_yoy",
            "interest_expense", "depreciation", "ebitda", "ebit",
            "other_income", "tax_expense", "effective_tax_rate",
            "total_assets", "total_equity", "total_debt", "long_term_debt",
            "short_term_debt", "cash_and_equiv", "net_debt",
            "current_assets", "current_liabilities", "inventory",
            "receivables", "payables", "fixed_assets", "intangible_assets",
            "reserves_and_surplus", "book_value_per_share", "contingent_liabilities",
            "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
            "capital_expenditure", "free_cash_flow", "dividends_paid",
            "debt_repayment", "equity_raised",
            "roe", "roa", "roic", "debt_to_equity", "interest_coverage",
            "current_ratio", "quick_ratio", "asset_turnover",
            "inventory_turnover", "receivables_turnover", "dividend_payout_ratio",
            "earnings_surprise_pct", "analyst_rating_consensus",
            "target_price_consensus", "num_analysts",
            "revenue_5y_cagr", "eps_5y_cagr", "roe_5y_avg", "fcf_3y_avg",
        ]

        placeholders = ", ".join(f"${i}" for i in range(1, len(FUND_COLS) + 4))  # +3 for symbol, period_end, period_type
        col_names = ", ".join(FUND_COLS)
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in FUND_COLS)

        query = f"""
            INSERT INTO fundamentals_quarterly (
                symbol, period_end, period_type, {col_names}
            ) VALUES ({placeholders})
            ON CONFLICT (symbol, period_end, period_type)
            DO UPDATE SET {set_clause}
        """

        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for r in records:
                    try:
                        period_end = _parse_date(r.get("period_end"))

                        params = [
                            r.get("symbol", ""),
                            period_end,
                            r.get("period_type", "quarterly"),
                        ]
                        for c in FUND_COLS:
                            params.append(r.get(c))

                        await conn.execute(query, *params)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error upserting fundamentals for {r.get('symbol')}: {e}")

        return count
    
    async def get_fundamentals(
        self,
        symbol: str,
        period_type: str = "quarterly",
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        """Get quarterly/annual fundamentals for a symbol."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM fundamentals_quarterly
                WHERE symbol = $1 AND period_type = $2
                ORDER BY period_end DESC
                LIMIT $3
                """,
                symbol, period_type, limit,
            )
            return [dict(r) for r in rows]
    
    # ========================
    # Shareholding Quarterly
    # ========================
    
    async def upsert_shareholding(self, records: List[Dict[str, Any]]) -> int:
        """Insert or update quarterly shareholding records."""
        if not records:
            return 0
        
        query = """
            INSERT INTO shareholding_quarterly (
                symbol, quarter_end, promoter_holding, promoter_pledging,
                fii_holding, dii_holding, public_holding,
                promoter_holding_change, fii_holding_change,
                num_shareholders, mf_holding, insurance_holding
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (symbol, quarter_end)
            DO UPDATE SET
                promoter_holding = EXCLUDED.promoter_holding,
                promoter_pledging = EXCLUDED.promoter_pledging,
                fii_holding = EXCLUDED.fii_holding, dii_holding = EXCLUDED.dii_holding,
                public_holding = EXCLUDED.public_holding,
                promoter_holding_change = EXCLUDED.promoter_holding_change,
                fii_holding_change = EXCLUDED.fii_holding_change,
                num_shareholders = EXCLUDED.num_shareholders,
                mf_holding = EXCLUDED.mf_holding,
                insurance_holding = EXCLUDED.insurance_holding
        """
        
        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for r in records:
                    try:
                        quarter_end = _parse_date(r.get("quarter_end"))
                        
                        await conn.execute(
                            query,
                            r.get("symbol", ""),
                            quarter_end,
                            r.get("promoter_holding"), r.get("promoter_pledging"),
                            r.get("fii_holding"), r.get("dii_holding"),
                            r.get("public_holding"), r.get("promoter_holding_change"),
                            r.get("fii_holding_change"), r.get("num_shareholders"),
                            r.get("mf_holding"), r.get("insurance_holding"),
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error upserting shareholding for {r.get('symbol')}: {e}")
        
        return count
    
    async def get_shareholding(
        self,
        symbol: str,
        limit: int = 28,
    ) -> List[Dict[str, Any]]:
        """Get quarterly shareholding for a symbol."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM shareholding_quarterly
                WHERE symbol = $1
                ORDER BY quarter_end DESC
                LIMIT $2
                """,
                symbol, limit,
            )
            return [dict(r) for r in rows]
    
    # ========================
    # Derived Metrics Daily
    # ========================

    async def upsert_derived_metrics(self, records: List[Dict[str, Any]]) -> int:
        """Insert or update derived price metrics."""
        if not records:
            return 0

        query = """
            INSERT INTO derived_metrics_daily (
                symbol, date, daily_return_pct, return_5d_pct, return_20d_pct,
                return_60d_pct, day_range_pct, gap_percentage, week_52_high,
                week_52_low, distance_from_52w_high, volume_ratio, avg_volume_20d
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
            ON CONFLICT (symbol, date) DO UPDATE SET
                daily_return_pct = EXCLUDED.daily_return_pct,
                return_5d_pct = EXCLUDED.return_5d_pct,
                return_20d_pct = EXCLUDED.return_20d_pct,
                return_60d_pct = EXCLUDED.return_60d_pct,
                day_range_pct = EXCLUDED.day_range_pct,
                gap_percentage = EXCLUDED.gap_percentage,
                week_52_high = EXCLUDED.week_52_high,
                week_52_low = EXCLUDED.week_52_low,
                distance_from_52w_high = EXCLUDED.distance_from_52w_high,
                volume_ratio = EXCLUDED.volume_ratio,
                avg_volume_20d = EXCLUDED.avg_volume_20d
        """

        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for r in records:
                    try:
                        d = _parse_date(r.get("date"))
                        await conn.execute(
                            query, r.get("symbol", ""), d,
                            r.get("daily_return_pct"), r.get("return_5d_pct"),
                            r.get("return_20d_pct"), r.get("return_60d_pct"),
                            r.get("day_range_pct"), r.get("gap_percentage"),
                            r.get("week_52_high"), r.get("week_52_low"),
                            r.get("distance_from_52w_high"), r.get("volume_ratio"),
                            r.get("avg_volume_20d"),
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error upserting derived metrics for {r.get('symbol')}: {e}")
        return count

    async def get_derived_metrics(
        self, symbol: str, start_date: Optional[str] = None,
        end_date: Optional[str] = None, limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Get derived price metrics for a symbol."""
        conditions = ["symbol = $1"]
        params: list = [symbol]
        idx = 2
        if start_date:
            conditions.append(f"date >= ${idx}")
            params.append(_parse_date(start_date))
            idx += 1
        if end_date:
            conditions.append(f"date <= ${idx}")
            params.append(_parse_date(end_date))
            idx += 1
        where = " AND ".join(conditions)
        query = f"SELECT * FROM derived_metrics_daily WHERE {where} ORDER BY date DESC LIMIT {limit}"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]

    # ========================
    # Valuation Daily
    # ========================

    async def upsert_valuation(self, records: List[Dict[str, Any]]) -> int:
        """Insert or update daily valuation metrics."""
        if not records:
            return 0

        query = """
            INSERT INTO valuation_daily (
                symbol, date, market_cap, enterprise_value, pe_ratio, pe_ratio_forward,
                peg_ratio, pb_ratio, ps_ratio, ev_to_ebitda, ev_to_sales,
                dividend_yield, fcf_yield, earnings_yield, sector_avg_pe,
                sector_avg_roe, industry_avg_pe, historical_pe_median, sector_performance
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
            ON CONFLICT (symbol, date) DO UPDATE SET
                market_cap = EXCLUDED.market_cap, enterprise_value = EXCLUDED.enterprise_value,
                pe_ratio = EXCLUDED.pe_ratio, pe_ratio_forward = EXCLUDED.pe_ratio_forward,
                peg_ratio = EXCLUDED.peg_ratio, pb_ratio = EXCLUDED.pb_ratio,
                ps_ratio = EXCLUDED.ps_ratio, ev_to_ebitda = EXCLUDED.ev_to_ebitda,
                ev_to_sales = EXCLUDED.ev_to_sales, dividend_yield = EXCLUDED.dividend_yield,
                fcf_yield = EXCLUDED.fcf_yield, earnings_yield = EXCLUDED.earnings_yield,
                sector_avg_pe = EXCLUDED.sector_avg_pe, sector_avg_roe = EXCLUDED.sector_avg_roe,
                industry_avg_pe = EXCLUDED.industry_avg_pe,
                historical_pe_median = EXCLUDED.historical_pe_median,
                sector_performance = EXCLUDED.sector_performance
        """

        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for r in records:
                    try:
                        d = _parse_date(r.get("date"))
                        await conn.execute(
                            query, r.get("symbol", ""), d,
                            r.get("market_cap"), r.get("enterprise_value"),
                            r.get("pe_ratio"), r.get("pe_ratio_forward"),
                            r.get("peg_ratio"), r.get("pb_ratio"),
                            r.get("ps_ratio"), r.get("ev_to_ebitda"),
                            r.get("ev_to_sales"), r.get("dividend_yield"),
                            r.get("fcf_yield"), r.get("earnings_yield"),
                            r.get("sector_avg_pe"), r.get("sector_avg_roe"),
                            r.get("industry_avg_pe"), r.get("historical_pe_median"),
                            r.get("sector_performance"),
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error upserting valuation for {r.get('symbol')}: {e}")
        return count

    async def get_valuation(
        self, symbol: str, limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Get valuation metrics for a symbol."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM valuation_daily WHERE symbol = $1 ORDER BY date DESC LIMIT $2",
                symbol, limit,
            )
            return [dict(r) for r in rows]

    # ========================
    # ML Features Daily
    # ========================

    async def upsert_ml_features(self, records: List[Dict[str, Any]]) -> int:
        """Insert or update ML/strategy feature records."""
        if not records:
            return 0

        query = """
            INSERT INTO ml_features_daily (
                symbol, date, realized_volatility_10d, realized_volatility_20d,
                return_1d_pct, return_3d_pct, return_10d_pct, momentum_rank_sector,
                price_vs_sma20_pct, price_vs_sma50_pct, volume_zscore,
                volatility_percentile_1y, turnover_20d_avg, free_float_market_cap,
                days_since_earnings, days_to_earnings, trading_day_of_week,
                nifty_50_return_1m, fii_net_activity_daily, dii_net_activity_daily,
                sp500_return_1d, nasdaq_return_1d
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22)
            ON CONFLICT (symbol, date) DO UPDATE SET
                realized_volatility_10d = EXCLUDED.realized_volatility_10d,
                realized_volatility_20d = EXCLUDED.realized_volatility_20d,
                return_1d_pct = EXCLUDED.return_1d_pct, return_3d_pct = EXCLUDED.return_3d_pct,
                return_10d_pct = EXCLUDED.return_10d_pct,
                momentum_rank_sector = EXCLUDED.momentum_rank_sector,
                price_vs_sma20_pct = EXCLUDED.price_vs_sma20_pct,
                price_vs_sma50_pct = EXCLUDED.price_vs_sma50_pct,
                volume_zscore = EXCLUDED.volume_zscore,
                volatility_percentile_1y = EXCLUDED.volatility_percentile_1y,
                turnover_20d_avg = EXCLUDED.turnover_20d_avg,
                free_float_market_cap = EXCLUDED.free_float_market_cap,
                days_since_earnings = EXCLUDED.days_since_earnings,
                days_to_earnings = EXCLUDED.days_to_earnings,
                trading_day_of_week = EXCLUDED.trading_day_of_week,
                nifty_50_return_1m = EXCLUDED.nifty_50_return_1m,
                fii_net_activity_daily = EXCLUDED.fii_net_activity_daily,
                dii_net_activity_daily = EXCLUDED.dii_net_activity_daily,
                sp500_return_1d = EXCLUDED.sp500_return_1d,
                nasdaq_return_1d = EXCLUDED.nasdaq_return_1d
        """

        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for r in records:
                    try:
                        d = _parse_date(r.get("date"))
                        await conn.execute(
                            query, r.get("symbol", ""), d,
                            r.get("realized_volatility_10d"), r.get("realized_volatility_20d"),
                            r.get("return_1d_pct"), r.get("return_3d_pct"),
                            r.get("return_10d_pct"), r.get("momentum_rank_sector"),
                            r.get("price_vs_sma20_pct"), r.get("price_vs_sma50_pct"),
                            r.get("volume_zscore"), r.get("volatility_percentile_1y"),
                            r.get("turnover_20d_avg"), r.get("free_float_market_cap"),
                            r.get("days_since_earnings"), r.get("days_to_earnings"),
                            r.get("trading_day_of_week"), r.get("nifty_50_return_1m"),
                            r.get("fii_net_activity_daily"), r.get("dii_net_activity_daily"),
                            r.get("sp500_return_1d"), r.get("nasdaq_return_1d"),
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error upserting ML features for {r.get('symbol')}: {e}")
        return count

    async def get_ml_features(
        self, symbol: str, limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Get ML features for a symbol."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM ml_features_daily WHERE symbol = $1 ORDER BY date DESC LIMIT $2",
                symbol, limit,
            )
            return [dict(r) for r in rows]

    # ========================
    # Risk Metrics
    # ========================

    async def upsert_risk_metrics(self, records: List[Dict[str, Any]]) -> int:
        """Insert or update risk/performance metric records."""
        if not records:
            return 0

        query = """
            INSERT INTO risk_metrics (
                symbol, date, beta_1y, beta_3y, max_drawdown_1y,
                sharpe_ratio_1y, sortino_ratio_1y, information_ratio_1y,
                rolling_volatility_30d, downside_deviation_1y
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (symbol, date) DO UPDATE SET
                beta_1y = EXCLUDED.beta_1y, beta_3y = EXCLUDED.beta_3y,
                max_drawdown_1y = EXCLUDED.max_drawdown_1y,
                sharpe_ratio_1y = EXCLUDED.sharpe_ratio_1y,
                sortino_ratio_1y = EXCLUDED.sortino_ratio_1y,
                information_ratio_1y = EXCLUDED.information_ratio_1y,
                rolling_volatility_30d = EXCLUDED.rolling_volatility_30d,
                downside_deviation_1y = EXCLUDED.downside_deviation_1y
        """

        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for r in records:
                    try:
                        d = _parse_date(r.get("date"))
                        await conn.execute(
                            query, r.get("symbol", ""), d,
                            r.get("beta_1y"), r.get("beta_3y"),
                            r.get("max_drawdown_1y"), r.get("sharpe_ratio_1y"),
                            r.get("sortino_ratio_1y"), r.get("information_ratio_1y"),
                            r.get("rolling_volatility_30d"), r.get("downside_deviation_1y"),
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error upserting risk metrics for {r.get('symbol')}: {e}")
        return count

    async def get_risk_metrics(
        self, symbol: str, limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Get risk metrics for a symbol."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM risk_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT $2",
                symbol, limit,
            )
            return [dict(r) for r in rows]

    # ========================
    # Corporate Actions
    # ========================

    async def upsert_corporate_action(self, record: Dict[str, Any]) -> int:
        """Insert or update a corporate action (deduplicates on symbol+action_type+action_date)."""
        query = """
            INSERT INTO corporate_actions (
                symbol, action_type, action_date, ex_date, record_date,
                dividend_per_share, stock_split_ratio, bonus_ratio,
                rights_issue_ratio, buyback_details, next_earnings_date,
                pending_events, stock_status, sebi_investigation
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            ON CONFLICT (symbol, action_type, action_date) DO UPDATE SET
                ex_date = COALESCE(EXCLUDED.ex_date, corporate_actions.ex_date),
                record_date = COALESCE(EXCLUDED.record_date, corporate_actions.record_date),
                dividend_per_share = COALESCE(EXCLUDED.dividend_per_share, corporate_actions.dividend_per_share),
                stock_split_ratio = COALESCE(EXCLUDED.stock_split_ratio, corporate_actions.stock_split_ratio),
                bonus_ratio = COALESCE(EXCLUDED.bonus_ratio, corporate_actions.bonus_ratio),
                rights_issue_ratio = COALESCE(EXCLUDED.rights_issue_ratio, corporate_actions.rights_issue_ratio),
                buyback_details = COALESCE(EXCLUDED.buyback_details, corporate_actions.buyback_details),
                next_earnings_date = COALESCE(EXCLUDED.next_earnings_date, corporate_actions.next_earnings_date),
                pending_events = COALESCE(EXCLUDED.pending_events, corporate_actions.pending_events),
                stock_status = EXCLUDED.stock_status,
                sebi_investigation = EXCLUDED.sebi_investigation
            RETURNING id
        """
        async with self._pool.acquire() as conn:
            d = _parse_date(record.get("action_date"))
            ex = _parse_date(record.get("ex_date"))
            rec_date = _parse_date(record.get("record_date"))
            ne = _parse_date(record.get("next_earnings_date"))

            return await conn.fetchval(
                query,
                record.get("symbol", ""), record.get("action_type", ""),
                d, ex, rec_date,
                record.get("dividend_per_share"), record.get("stock_split_ratio"),
                record.get("bonus_ratio"), record.get("rights_issue_ratio"),
                record.get("buyback_details"), ne,
                record.get("pending_events"), record.get("stock_status", "active"),
                record.get("sebi_investigation", False),
            )

    async def get_corporate_actions(
        self, symbol: str, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get corporate actions for a symbol."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM corporate_actions WHERE symbol = $1 ORDER BY action_date DESC LIMIT $2",
                symbol, limit,
            )
            return [dict(r) for r in rows]

    # ========================
    # Macro Indicators
    # ========================

    async def upsert_macro_indicators(self, records: List[Dict[str, Any]]) -> int:
        """Insert or update monthly macro indicator records."""
        if not records:
            return 0

        query = """
            INSERT INTO macro_indicators (
                date, cpi_inflation, iip_growth, rbi_repo_rate, usdinr_rate,
                crude_brent_price, gold_price, steel_price, copper_price
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (date) DO UPDATE SET
                cpi_inflation = EXCLUDED.cpi_inflation, iip_growth = EXCLUDED.iip_growth,
                rbi_repo_rate = EXCLUDED.rbi_repo_rate, usdinr_rate = EXCLUDED.usdinr_rate,
                crude_brent_price = EXCLUDED.crude_brent_price, gold_price = EXCLUDED.gold_price,
                steel_price = EXCLUDED.steel_price, copper_price = EXCLUDED.copper_price
        """

        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for r in records:
                    try:
                        d = _parse_date(r.get("date"))
                        await conn.execute(
                            query, d,
                            r.get("cpi_inflation"), r.get("iip_growth"),
                            r.get("rbi_repo_rate"), r.get("usdinr_rate"),
                            r.get("crude_brent_price"), r.get("gold_price"),
                            r.get("steel_price"), r.get("copper_price"),
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error upserting macro indicators: {e}")
        return count

    async def get_macro_indicators(self, limit: int = 60) -> List[Dict[str, Any]]:
        """Get macro indicators."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM macro_indicators ORDER BY date DESC LIMIT $1", limit,
            )
            return [dict(r) for r in rows]

    # ========================
    # Derivatives Daily
    # ========================

    async def upsert_derivatives(self, records: List[Dict[str, Any]]) -> int:
        """Insert or update derivatives/F&O data."""
        if not records:
            return 0

        query = """
            INSERT INTO derivatives_daily (
                symbol, date, futures_oi, futures_oi_change_pct, futures_price_near,
                futures_basis_pct, fii_index_futures_long_oi, fii_index_futures_short_oi,
                options_call_oi_total, options_put_oi_total, put_call_ratio_oi,
                put_call_ratio_volume, options_max_pain_strike, iv_atm_pct,
                iv_percentile_1y, pcr_index_level
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
            ON CONFLICT (symbol, date) DO UPDATE SET
                futures_oi = EXCLUDED.futures_oi,
                futures_oi_change_pct = EXCLUDED.futures_oi_change_pct,
                futures_price_near = EXCLUDED.futures_price_near,
                futures_basis_pct = EXCLUDED.futures_basis_pct,
                fii_index_futures_long_oi = EXCLUDED.fii_index_futures_long_oi,
                fii_index_futures_short_oi = EXCLUDED.fii_index_futures_short_oi,
                options_call_oi_total = EXCLUDED.options_call_oi_total,
                options_put_oi_total = EXCLUDED.options_put_oi_total,
                put_call_ratio_oi = EXCLUDED.put_call_ratio_oi,
                put_call_ratio_volume = EXCLUDED.put_call_ratio_volume,
                options_max_pain_strike = EXCLUDED.options_max_pain_strike,
                iv_atm_pct = EXCLUDED.iv_atm_pct,
                iv_percentile_1y = EXCLUDED.iv_percentile_1y,
                pcr_index_level = EXCLUDED.pcr_index_level
        """

        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for r in records:
                    try:
                        d = _parse_date(r.get("date"))
                        await conn.execute(
                            query, r.get("symbol", ""), d,
                            r.get("futures_oi"), r.get("futures_oi_change_pct"),
                            r.get("futures_price_near"), r.get("futures_basis_pct"),
                            r.get("fii_index_futures_long_oi"), r.get("fii_index_futures_short_oi"),
                            r.get("options_call_oi_total"), r.get("options_put_oi_total"),
                            r.get("put_call_ratio_oi"), r.get("put_call_ratio_volume"),
                            r.get("options_max_pain_strike"), r.get("iv_atm_pct"),
                            r.get("iv_percentile_1y"), r.get("pcr_index_level"),
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error upserting derivatives for {r.get('symbol')}: {e}")
        return count

    async def get_derivatives(
        self, symbol: str, limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Get derivatives data for a symbol."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM derivatives_daily WHERE symbol = $1 ORDER BY date DESC LIMIT $2",
                symbol, limit,
            )
            return [dict(r) for r in rows]

    # ========================
    # Intraday Metrics
    # ========================

    async def upsert_intraday_metrics(self, records: List[Dict[str, Any]]) -> int:
        """Insert or update hourly/intraday metric records."""
        if not records:
            return 0

        query = """
            INSERT INTO intraday_metrics (
                symbol, timestamp, rsi_hourly, macd_crossover_hourly,
                vwap_intraday, advance_decline_ratio, sectoral_heatmap, india_vix
            ) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8)
            ON CONFLICT (symbol, timestamp) DO UPDATE SET
                rsi_hourly = EXCLUDED.rsi_hourly,
                macd_crossover_hourly = EXCLUDED.macd_crossover_hourly,
                vwap_intraday = EXCLUDED.vwap_intraday,
                advance_decline_ratio = EXCLUDED.advance_decline_ratio,
                sectoral_heatmap = EXCLUDED.sectoral_heatmap,
                india_vix = EXCLUDED.india_vix
        """

        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for r in records:
                    try:
                        import json as _json
                        ts = r.get("timestamp")
                        if isinstance(ts, str):
                            ts = datetime.fromisoformat(ts)
                        if ts and ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)

                        heatmap = r.get("sectoral_heatmap")
                        if heatmap and not isinstance(heatmap, str):
                            heatmap = _json.dumps(heatmap)

                        await conn.execute(
                            query,
                            r.get("symbol", ""), ts,
                            r.get("rsi_hourly"), r.get("macd_crossover_hourly"),
                            r.get("vwap_intraday"), r.get("advance_decline_ratio"),
                            heatmap, r.get("india_vix"),
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error upserting intraday for {r.get('symbol')}: {e}")
        return count

    async def get_intraday_metrics(
        self, symbol: str,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Get intraday metrics for a symbol with optional timestamp range."""
        conditions = ["symbol = $1"]
        params: list = [symbol]
        idx = 2
        if start_ts:
            ts = datetime.fromisoformat(start_ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            conditions.append(f"timestamp >= ${idx}")
            params.append(ts)
            idx += 1
        if end_ts:
            ts = datetime.fromisoformat(end_ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            conditions.append(f"timestamp <= ${idx}")
            params.append(ts)
            idx += 1
        where = " AND ".join(conditions)
        query = f"SELECT * FROM intraday_metrics WHERE {where} ORDER BY timestamp DESC LIMIT {limit}"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]

    # ========================
    # Weekly Metrics
    # ========================

    async def upsert_weekly_metrics(self, records: List[Dict[str, Any]]) -> int:
        """Insert or update weekly metric records."""
        if not records:
            return 0

        query = """
            INSERT INTO weekly_metrics (
                symbol, week_start, sma_weekly_crossover,
                support_resistance_weekly, google_trends_score, job_postings_growth
            ) VALUES ($1,$2,$3,$4::jsonb,$5,$6)
            ON CONFLICT (symbol, week_start) DO UPDATE SET
                sma_weekly_crossover = EXCLUDED.sma_weekly_crossover,
                support_resistance_weekly = EXCLUDED.support_resistance_weekly,
                google_trends_score = EXCLUDED.google_trends_score,
                job_postings_growth = EXCLUDED.job_postings_growth
        """

        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for r in records:
                    try:
                        import json as _json
                        ws = _parse_date(r.get("week_start"))

                        sr = r.get("support_resistance_weekly")
                        if sr and not isinstance(sr, str):
                            sr = _json.dumps(sr)

                        await conn.execute(
                            query,
                            r.get("symbol", ""), ws,
                            r.get("sma_weekly_crossover"),
                            sr, r.get("google_trends_score"),
                            r.get("job_postings_growth"),
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error upserting weekly metrics for {r.get('symbol')}: {e}")
        return count

    async def get_weekly_metrics(
        self, symbol: str, limit: int = 104,
    ) -> List[Dict[str, Any]]:
        """Get weekly metrics for a symbol (default 2 years)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM weekly_metrics WHERE symbol = $1 ORDER BY week_start DESC LIMIT $2",
                symbol, limit,
            )
            return [dict(r) for r in rows]

    # ========================
    # Analytics Queries
    # ========================
    
    async def get_screener_data(
        self,
        filters: Optional[List[Dict[str, Any]]] = None,
        symbols: Optional[List[str]] = None,
        sort_by: str = "symbol",
        sort_order: str = "asc",
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Cross-join latest prices with technicals and fundamentals for screener.
        This is the key advantage of SQL — filtering across multiple data types.

        Args:
            filters: List of filter dicts with keys: metric, operator, value, value2
                     Supported metrics map to columns:
                       - rsi_14, sma_50, sma_200, macd -> technical_indicators
                       - close, volume -> prices_daily
                       - roe, debt_to_equity, eps, revenue, net_profit, current_ratio,
                         operating_margin, net_profit_margin -> fundamentals_quarterly
                       - promoter_holding, fii_holding, dii_holding -> shareholding_quarterly
            symbols: Filter to specific symbols
            sort_by: Column to sort by
            sort_order: 'asc' or 'desc'
            limit: Max results
        """
        conditions = []
        params: list = []
        idx = 1

        # Column mapping: metric name -> SQL alias.column
        COLUMN_MAP = {
            # Price columns (alias: p)
            "close": "p.close", "current_price": "p.close",
            "volume": "p.volume", "prev_close": "p.prev_close",
            # Technical columns (alias: t)
            "rsi_14": "t.rsi_14", "sma_50": "t.sma_50", "sma_200": "t.sma_200",
            "macd": "t.macd", "macd_signal": "t.macd_signal",
            "sma_20": "t.sma_20", "ema_12": "t.ema_12", "ema_26": "t.ema_26",
            "atr_14": "t.atr_14", "adx_14": "t.adx_14",
            "bollinger_upper": "t.bollinger_upper", "bollinger_lower": "t.bollinger_lower",
            "stoch_k": "t.stoch_k", "stoch_d": "t.stoch_d",
            "cci_20": "t.cci_20", "williams_r": "t.williams_r", "cmf": "t.cmf",
            # Fundamental columns (alias: f)
            "roe": "f.roe", "roa": "f.roa", "roic": "f.roic",
            "debt_to_equity": "f.debt_to_equity",
            "eps": "f.eps", "revenue": "f.revenue",
            "net_profit": "f.net_profit", "operating_margin": "f.operating_margin",
            "net_profit_margin": "f.net_profit_margin", "current_ratio": "f.current_ratio",
            "quick_ratio": "f.quick_ratio", "interest_coverage": "f.interest_coverage",
            "free_cash_flow": "f.free_cash_flow", "operating_cash_flow": "f.operating_cash_flow",
            "ebitda": "f.ebitda", "gross_margin": "f.gross_margin",
            "dividend_payout_ratio": "f.dividend_payout_ratio",
            # Shareholding columns (alias: s)
            "promoter_holding": "s.promoter_holding", "fii_holding": "s.fii_holding",
            "dii_holding": "s.dii_holding", "public_holding": "s.public_holding",
            "promoter_pledging": "s.promoter_pledging",
            # Derived metrics columns (alias: d)
            "daily_return_pct": "d.daily_return_pct",
            "return_5d_pct": "d.return_5d_pct", "return_20d_pct": "d.return_20d_pct",
            "return_60d_pct": "d.return_60d_pct",
            "week_52_high": "d.week_52_high", "week_52_low": "d.week_52_low",
            "distance_from_52w_high": "d.distance_from_52w_high",
            "volume_ratio": "d.volume_ratio",
            # Valuation columns (alias: v)
            "market_cap": "v.market_cap", "enterprise_value": "v.enterprise_value",
            "pe_ratio": "v.pe_ratio", "pe_ratio_forward": "v.pe_ratio_forward",
            "peg_ratio": "v.peg_ratio", "pb_ratio": "v.pb_ratio",
            "ps_ratio": "v.ps_ratio", "ev_to_ebitda": "v.ev_to_ebitda",
            "ev_to_sales": "v.ev_to_sales", "dividend_yield": "v.dividend_yield",
            "fcf_yield": "v.fcf_yield", "earnings_yield": "v.earnings_yield",
            # Risk metrics columns (alias: r)
            "beta_1y": "r.beta_1y", "beta_3y": "r.beta_3y",
            "max_drawdown_1y": "r.max_drawdown_1y",
            "sharpe_ratio_1y": "r.sharpe_ratio_1y",
            "sortino_ratio_1y": "r.sortino_ratio_1y",
            "rolling_volatility_30d": "r.rolling_volatility_30d",
        }

        if symbols:
            conditions.append(f"p.symbol = ANY(${idx})")
            params.append(symbols)
            idx += 1

        # Process filters
        if filters:
            for f in filters:
                metric = f.get("metric", "")
                col = COLUMN_MAP.get(metric)
                if not col:
                    continue  # Skip unknown metrics

                op = f.get("operator", "gte")
                val = f.get("value", 0)

                if op == "gt":
                    conditions.append(f"{col} > ${idx}")
                    params.append(float(val))
                    idx += 1
                elif op == "lt":
                    conditions.append(f"{col} < ${idx}")
                    params.append(float(val))
                    idx += 1
                elif op == "gte":
                    conditions.append(f"{col} >= ${idx}")
                    params.append(float(val))
                    idx += 1
                elif op == "lte":
                    conditions.append(f"{col} <= ${idx}")
                    params.append(float(val))
                    idx += 1
                elif op == "eq":
                    conditions.append(f"{col} = ${idx}")
                    params.append(float(val))
                    idx += 1
                elif op == "between" and f.get("value2") is not None:
                    conditions.append(f"{col} BETWEEN ${idx} AND ${idx + 1}")
                    params.append(float(val))
                    params.append(float(f["value2"]))
                    idx += 2

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        # Determine sort column
        sort_col = COLUMN_MAP.get(sort_by, "p.symbol")
        sort_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

        query = f"""
            WITH latest_prices AS (
                SELECT DISTINCT ON (symbol)
                    symbol, date, close, volume, prev_close
                FROM prices_daily
                ORDER BY symbol, date DESC
            ),
            latest_tech AS (
                SELECT DISTINCT ON (symbol)
                    symbol, sma_20, sma_50, sma_200, ema_12, ema_26,
                    rsi_14, macd, macd_signal, bollinger_upper, bollinger_lower,
                    atr_14, adx_14, stoch_k, stoch_d, cci_20, williams_r, cmf
                FROM technical_indicators
                ORDER BY symbol, date DESC
            ),
            latest_fund AS (
                SELECT DISTINCT ON (symbol)
                    symbol, revenue, operating_profit, operating_margin,
                    gross_margin, net_profit, net_profit_margin, eps,
                    ebitda, roe, roa, roic, debt_to_equity,
                    interest_coverage, current_ratio, quick_ratio,
                    free_cash_flow, operating_cash_flow, dividend_payout_ratio
                FROM fundamentals_quarterly
                WHERE period_type = 'quarterly'
                ORDER BY symbol, period_end DESC
            ),
            latest_share AS (
                SELECT DISTINCT ON (symbol)
                    symbol, promoter_holding, promoter_pledging,
                    fii_holding, dii_holding, public_holding
                FROM shareholding_quarterly
                ORDER BY symbol, quarter_end DESC
            ),
            latest_derived AS (
                SELECT DISTINCT ON (symbol)
                    symbol, daily_return_pct, return_5d_pct, return_20d_pct,
                    return_60d_pct, week_52_high, week_52_low,
                    distance_from_52w_high, volume_ratio
                FROM derived_metrics_daily
                ORDER BY symbol, date DESC
            ),
            latest_val AS (
                SELECT DISTINCT ON (symbol)
                    symbol, market_cap, enterprise_value, pe_ratio, pe_ratio_forward,
                    peg_ratio, pb_ratio, ps_ratio, ev_to_ebitda, ev_to_sales,
                    dividend_yield, fcf_yield, earnings_yield
                FROM valuation_daily
                ORDER BY symbol, date DESC
            ),
            latest_risk AS (
                SELECT DISTINCT ON (symbol)
                    symbol, beta_1y, beta_3y, max_drawdown_1y,
                    sharpe_ratio_1y, sortino_ratio_1y, rolling_volatility_30d
                FROM risk_metrics
                ORDER BY symbol, date DESC
            )
            SELECT
                p.symbol, p.date, p.close, p.volume, p.prev_close,
                t.rsi_14, t.sma_20, t.sma_50, t.sma_200,
                t.ema_12, t.ema_26, t.macd, t.macd_signal,
                t.bollinger_upper, t.bollinger_lower, t.atr_14, t.adx_14,
                t.stoch_k, t.stoch_d, t.cci_20, t.williams_r, t.cmf,
                f.revenue, f.operating_margin, f.gross_margin,
                f.net_profit, f.net_profit_margin,
                f.eps, f.ebitda, f.roe, f.roa, f.roic, f.debt_to_equity,
                f.interest_coverage, f.current_ratio, f.quick_ratio,
                f.free_cash_flow, f.operating_cash_flow, f.dividend_payout_ratio,
                s.promoter_holding, s.promoter_pledging,
                s.fii_holding, s.dii_holding, s.public_holding,
                d.daily_return_pct, d.return_5d_pct, d.return_20d_pct,
                d.return_60d_pct, d.week_52_high, d.week_52_low,
                d.distance_from_52w_high, d.volume_ratio,
                v.market_cap, v.enterprise_value, v.pe_ratio, v.pe_ratio_forward,
                v.peg_ratio, v.pb_ratio, v.ps_ratio, v.ev_to_ebitda,
                v.ev_to_sales, v.dividend_yield, v.fcf_yield, v.earnings_yield,
                r.beta_1y, r.beta_3y, r.max_drawdown_1y,
                r.sharpe_ratio_1y, r.sortino_ratio_1y, r.rolling_volatility_30d
            FROM latest_prices p
            LEFT JOIN latest_tech t ON p.symbol = t.symbol
            LEFT JOIN latest_fund f ON p.symbol = f.symbol
            LEFT JOIN latest_share s ON p.symbol = s.symbol
            LEFT JOIN latest_derived d ON p.symbol = d.symbol
            LEFT JOIN latest_val v ON p.symbol = v.symbol
            LEFT JOIN latest_risk r ON p.symbol = r.symbol
            {where}
            ORDER BY {sort_col} {sort_dir} NULLS LAST
            LIMIT {limit}
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics for monitoring."""
        async with self._pool.acquire() as conn:
            stats = {}
            for table in [
                "prices_daily", "derived_metrics_daily", "technical_indicators",
                "ml_features_daily", "risk_metrics", "valuation_daily",
                "fundamentals_quarterly", "shareholding_quarterly",
                "corporate_actions", "macro_indicators", "derivatives_daily",
                "intraday_metrics", "weekly_metrics", "schema_migrations",
            ]:
                row_count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                size = await conn.fetchval(
                    f"SELECT pg_size_pretty(pg_total_relation_size('{table}'))"
                )
                stats[table] = {"rows": row_count, "size": size}
            
            stats["pool"] = {
                "size": self._pool.get_size(),
                "min_size": self._pool.get_min_size(),
                "max_size": self._pool.get_max_size(),
                "free_size": self._pool.get_idle_size(),
            }
            
            return stats


# Module-level singleton
_ts_store: Optional[TimeSeriesStore] = None


async def init_timeseries_store(dsn: str = "postgresql://localhost:5432/stockpulse_ts") -> TimeSeriesStore:
    """Initialize and return the global time-series store singleton."""
    global _ts_store
    _ts_store = TimeSeriesStore(dsn=dsn)
    await _ts_store.initialize()
    return _ts_store


def get_timeseries_store() -> Optional[TimeSeriesStore]:
    """Get the global time-series store instance."""
    return _ts_store
