"""
Data Fetchers — Connect FeaturePipeline to real data sources.

Provides async callback functions that the FeaturePipeline uses to fetch:
  - OHLCV price data (from MongoDB / YFinance)
  - Fundamental data (from MongoDB / Screener)
  - Macro economic data (from MongoDB / YFinance)
  - Market context data (NIFTY benchmark, sector data)

Designed to work with whatever data stores are available in the current
environment, with graceful fallbacks.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("brain.features.data_fetchers")

IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# YFinance fetcher (works without any external DB)
# ---------------------------------------------------------------------------


async def fetch_price_data_yfinance(symbol: str, days: int = 365) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV data from YFinance for a given symbol.
    Returns a DataFrame with columns: date, open, high, low, close, volume
    sorted by date ascending.
    """
    try:
        import yfinance as yf

        ticker_symbol = f"{symbol}.NS"  # NSE suffix
        end = datetime.now(IST)
        start = end - timedelta(days=days)

        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))

        if df is None or df.empty:
            # Try BSE suffix
            ticker_symbol = f"{symbol}.BO"
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))

        if df is None or df.empty:
            logger.warning("No YFinance data for %s", symbol)
            return None

        df = df.reset_index()
        result = pd.DataFrame({
            "date": pd.to_datetime(df["Date"]).dt.tz_localize(None),
            "open": df["Open"].astype(float),
            "high": df["High"].astype(float),
            "low": df["Low"].astype(float),
            "close": df["Close"].astype(float),
            "volume": df["Volume"].astype(float),
        })

        # Add delivery_volume placeholder (not available from YFinance)
        result["delivery_volume"] = np.nan

        result = result.sort_values("date").reset_index(drop=True)
        logger.info("Fetched %d OHLCV rows for %s from YFinance", len(result), symbol)
        return result

    except Exception:
        logger.exception("Error fetching YFinance data for %s", symbol)
        return None


async def fetch_fundamental_data_yfinance(symbol: str) -> Dict[str, Any]:
    """
    Fetch fundamental data from YFinance.
    Returns a dict compatible with compute_all_fundamental_features().
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(f"{symbol}.NS")
        info = ticker.info or {}

        # Get financials
        financials = ticker.financials
        balance_sheet = ticker.balance_sheet
        cashflow = ticker.cashflow

        result = {
            "symbol": symbol,
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE", 0),
            "pb_ratio": info.get("priceToBook", 0),
            "dividend_yield": info.get("dividendYield", 0),
            "roe": info.get("returnOnEquity", 0),
            "roce": info.get("returnOnAssets", 0),  # Approximation
            "eps": info.get("trailingEps", 0),
            "book_value": info.get("bookValue", 0),
            "debt_to_equity": info.get("debtToEquity", 0),
            "current_ratio": info.get("currentRatio", 0),
            "revenue_growth": info.get("revenueGrowth", 0),
            "earnings_growth": info.get("earningsGrowth", 0),
            "operating_margin": info.get("operatingMargins", 0),
            "profit_margin": info.get("profitMargins", 0),
            "gross_margin": info.get("grossMargins", 0),
            "free_cash_flow": info.get("freeCashflow", 0),
            "total_revenue": info.get("totalRevenue", 0),
            "total_debt": info.get("totalDebt", 0),
            "total_assets": info.get("totalAssets", 0),
            "shares_outstanding": info.get("sharesOutstanding", 0),

            # Quarterly data for Piotroski
            "net_income_current": 0,
            "net_income_previous": 0,
            "total_assets_current": info.get("totalAssets", 0),
            "total_assets_previous": 0,
            "cfo_current": info.get("operatingCashflow", 0),
            "long_term_debt_current": info.get("totalDebt", 0),
            "long_term_debt_previous": 0,
            "current_ratio_current": info.get("currentRatio", 0),
            "current_ratio_previous": 0,
            "shares_current": info.get("sharesOutstanding", 0),
            "shares_previous": info.get("sharesOutstanding", 0),
            "gross_margin_current": info.get("grossMargins", 0),
            "gross_margin_previous": 0,
            "asset_turnover_current": 0,
            "asset_turnover_previous": 0,

            # Holdings data
            "promoter_holding_current": 0,
            "promoter_holding_previous": 0,
            "fii_holding_current": 0,
            "fii_holding_previous": 0,
            "dii_holding_current": 0,
            "dii_holding_previous": 0,

            # Revenue history for growth consistency
            "revenue_history": [],

            # ROCE history
            "roce_history": [],

            # Working capital
            "current_assets": 0,
            "current_liabilities": 0,
            "working_capital": 0,
            "sales": info.get("totalRevenue", 0),
            "retained_earnings": 0,
            "ebit": 0,
            "market_value_equity": info.get("marketCap", 0),
            "total_liabilities": 0,

            # Beneish
            "receivables_current": 0,
            "receivables_previous": 0,
            "depreciation_current": 0,
            "depreciation_previous": 0,
            "sga_current": 0,
            "sga_previous": 0,
        }

        # Extract financials if available
        if financials is not None and not financials.empty:
            try:
                cols = financials.columns
                if len(cols) >= 2:
                    result["net_income_current"] = float(financials.loc["Net Income", cols[0]]) if "Net Income" in financials.index else 0
                    result["net_income_previous"] = float(financials.loc["Net Income", cols[1]]) if "Net Income" in financials.index else 0
                    result["ebit"] = float(financials.loc["EBIT", cols[0]]) if "EBIT" in financials.index else 0
                    result["total_revenue"] = float(financials.loc["Total Revenue", cols[0]]) if "Total Revenue" in financials.index else result["total_revenue"]

                    # Revenue history
                    if "Total Revenue" in financials.index:
                        result["revenue_history"] = [
                            float(financials.loc["Total Revenue", c])
                            for c in cols[:5] if pd.notna(financials.loc["Total Revenue", c])
                        ]
            except Exception:
                pass

        if balance_sheet is not None and not balance_sheet.empty:
            try:
                cols = balance_sheet.columns
                if len(cols) >= 2:
                    result["total_assets_current"] = float(balance_sheet.loc["Total Assets", cols[0]]) if "Total Assets" in balance_sheet.index else result["total_assets_current"]
                    result["total_assets_previous"] = float(balance_sheet.loc["Total Assets", cols[1]]) if "Total Assets" in balance_sheet.index else 0
                    result["current_assets"] = float(balance_sheet.loc["Current Assets", cols[0]]) if "Current Assets" in balance_sheet.index else 0
                    result["current_liabilities"] = float(balance_sheet.loc["Current Liabilities", cols[0]]) if "Current Liabilities" in balance_sheet.index else 0
                    result["total_liabilities"] = float(balance_sheet.loc["Total Liabilities Net Minority Interest", cols[0]]) if "Total Liabilities Net Minority Interest" in balance_sheet.index else 0
                    result["working_capital"] = result["current_assets"] - result["current_liabilities"]
            except Exception:
                pass

        logger.info("Fetched fundamental data for %s from YFinance", symbol)
        return result

    except Exception:
        logger.exception("Error fetching fundamental data for %s", symbol)
        return {}


async def fetch_macro_data_yfinance() -> Dict[str, Any]:
    """
    Fetch macro economic indicators from YFinance and environment config.
    Returns a dict compatible with compute_all_macro_features().
    """
    try:
        import yfinance as yf

        result = {
            # RBI data (from env or defaults)
            "repo_rate_current": float(os.getenv("MACRO_RBI_REPO_RATE", "6.5")),
            "repo_rate_6m_ago": float(os.getenv("MACRO_RBI_REPO_RATE_6M", "6.5")),
            "cpi_inflation": float(os.getenv("MACRO_CPI_INFLATION", "4.2")),
            "iip_growth": float(os.getenv("MACRO_IIP_GROWTH", "3.1")),
        }

        # INR/USD from YFinance
        try:
            inr = yf.Ticker("INR=X")
            inr_hist = inr.history(period="60d")
            if inr_hist is not None and not inr_hist.empty:
                closes = inr_hist["Close"].values
                result["inr_usd_current"] = float(closes[-1])
                if len(closes) >= 30:
                    result["inr_usd_30d_ago"] = float(closes[-30])
                else:
                    result["inr_usd_30d_ago"] = float(closes[0])
        except Exception:
            result["inr_usd_current"] = 83.5
            result["inr_usd_30d_ago"] = 83.0

        # Crude Oil
        try:
            crude = yf.Ticker("CL=F")
            crude_hist = crude.history(period="60d")
            if crude_hist is not None and not crude_hist.empty:
                closes = crude_hist["Close"].values
                result["crude_oil_current"] = float(closes[-1])
                if len(closes) >= 30:
                    result["crude_oil_30d_ago"] = float(closes[-30])
                else:
                    result["crude_oil_30d_ago"] = float(closes[0])
        except Exception:
            result["crude_oil_current"] = 75.0
            result["crude_oil_30d_ago"] = 73.0

        # India VIX
        try:
            vix = yf.Ticker("^INDIAVIX")
            vix_hist = vix.history(period="5d")
            if vix_hist is not None and not vix_hist.empty:
                result["vix_level"] = float(vix_hist["Close"].values[-1])
            else:
                result["vix_level"] = 14.0
        except Exception:
            result["vix_level"] = 14.0

        # FII/DII flows (defaults - real data from MongoDB/Dhan when available)
        result["fii_net_flow_7d"] = 0.0
        result["fii_net_flow_30d"] = 0.0
        result["dii_net_flow_7d"] = 0.0
        result["dii_net_flow_30d"] = 0.0

        logger.info("Fetched macro data: INR=%.2f, Crude=%.2f, VIX=%.2f",
                    result.get("inr_usd_current", 0),
                    result.get("crude_oil_current", 0),
                    result.get("vix_level", 0))
        return result

    except Exception:
        logger.exception("Error fetching macro data")
        return {}


async def fetch_market_data_yfinance(symbol: str) -> Dict[str, Any]:
    """
    Fetch market context data (NIFTY 50 benchmark, sector info).
    Returns a dict compatible with cross-sectional features.
    """
    try:
        import yfinance as yf

        result = {"symbol": symbol}

        # NIFTY 50 index
        try:
            nifty = yf.Ticker("^NSEI")
            nifty_hist = nifty.history(period="1y")
            if nifty_hist is not None and not nifty_hist.empty:
                nifty_df = nifty_hist.reset_index()
                result["nifty_prices"] = pd.DataFrame({
                    "date": pd.to_datetime(nifty_df["Date"]).dt.tz_localize(None),
                    "close": nifty_df["Close"].astype(float),
                    "volume": nifty_df["Volume"].astype(float),
                }).sort_values("date").to_dict("records")
        except Exception:
            result["nifty_prices"] = []

        # Sector mapping (basic)
        sector_map = _get_sector_for_symbol(symbol)
        result["sector"] = sector_map.get("sector", "Unknown")
        result["sector_stocks"] = sector_map.get("peers", [])

        logger.info("Fetched market context for %s (sector: %s)", symbol, result["sector"])
        return result

    except Exception:
        logger.exception("Error fetching market data for %s", symbol)
        return {}


# ---------------------------------------------------------------------------
# MongoDB-backed fetchers (use existing MongoDB data)
# ---------------------------------------------------------------------------


class MongoDataFetchers:
    """
    Data fetchers backed by MongoDB.
    Uses data already collected by the Stock-Pulse extraction pipeline.
    Falls back to YFinance when MongoDB data is unavailable.
    """

    def __init__(self, db):
        """
        Args:
            db: Motor async MongoDB database instance.
        """
        self.db = db

    async def fetch_price_data(self, symbol: str, days: int = 365) -> Optional[pd.DataFrame]:
        """Fetch OHLCV from MongoDB, fallback to YFinance."""
        try:
            # Try MongoDB first
            collection = self.db["stock_prices"]
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            cursor = collection.find(
                {"symbol": symbol.upper(), "date": {"$gte": cutoff}},
                {"_id": 0, "date": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "delivery_volume": 1}
            ).sort("date", 1)

            rows = await cursor.to_list(length=5000)
            if rows and len(rows) > 20:
                df = pd.DataFrame(rows)
                df["date"] = pd.to_datetime(df["date"])
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                if "delivery_volume" not in df.columns:
                    df["delivery_volume"] = np.nan
                logger.info("Fetched %d price rows for %s from MongoDB", len(df), symbol)
                return df
        except Exception:
            logger.debug("MongoDB price fetch failed for %s, falling back to YFinance", symbol)

        # Fallback to YFinance
        return await fetch_price_data_yfinance(symbol, days)

    async def fetch_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamental data from MongoDB, fallback to YFinance."""
        try:
            collection = self.db["stock_fundamentals"]
            doc = await collection.find_one(
                {"symbol": symbol.upper()},
                {"_id": 0}
            )
            if doc and doc.get("market_cap"):
                logger.info("Fetched fundamentals for %s from MongoDB", symbol)
                return doc
        except Exception:
            logger.debug("MongoDB fundamentals fetch failed for %s", symbol)

        return await fetch_fundamental_data_yfinance(symbol)

    async def fetch_macro_data(self) -> Dict[str, Any]:
        """Fetch macro data from MongoDB, fallback to YFinance."""
        try:
            collection = self.db["macro_indicators"]
            doc = await collection.find_one(
                {},
                {"_id": 0},
                sort=[("date", -1)]
            )
            if doc and doc.get("vix_level"):
                logger.info("Fetched macro data from MongoDB")
                return doc
        except Exception:
            logger.debug("MongoDB macro fetch failed, falling back to YFinance")

        return await fetch_macro_data_yfinance()

    async def fetch_market_data(self, symbol: str) -> Dict[str, Any]:
        """Fetch market context from MongoDB, fallback to YFinance."""
        return await fetch_market_data_yfinance(symbol)


# ---------------------------------------------------------------------------
# Sector mapping utility
# ---------------------------------------------------------------------------

SECTOR_MAP = {
    "IT": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM", "COFORGE", "MPHASIS", "PERSISTENT"],
    "Banking": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK", "BANDHANBNK", "PNB", "BANKBARODA", "IDFCFIRSTB"],
    "Pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP", "LUPIN", "AUROPHARMA", "BIOCON"],
    "Auto": ["MARUTI", "TATAMOTORS", "M&M", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT", "ASHOKLEY", "TVSMOTOR"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "MARICO", "GODREJCP", "COLPAL", "TATACONSUM"],
    "Metals": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "COALINDIA", "NMDC", "SAIL"],
    "Realty": ["DLF", "GODREJPROP", "OBEROIRLTY", "PHOENIXLTD", "PRESTIGE", "BRIGADE"],
    "Energy": ["RELIANCE", "ONGC", "BPCL", "IOC", "NTPC", "POWERGRID", "ADANIGREEN", "TATAPOWER"],
    "Finance": ["BAJFINANCE", "BAJAJFINSV", "HDFCLIFE", "SBILIFE", "ICICIPRULI", "MUTHOOTFIN", "CHOLAFIN"],
    "Telecom": ["BHARTIARTL", "IDEA", "INDUSTOWER"],
    "Cement": ["ULTRACEMCO", "SHREECEM", "AMBUJACEM", "ACC", "DALMIACEM"],
    "Infra": ["LTTS", "LT", "ADANIENT", "ADANIPORTS", "SIEMENS", "ABB"],
}


def _get_sector_for_symbol(symbol: str) -> Dict[str, Any]:
    """Get sector and peer list for a symbol."""
    sym = symbol.upper()
    for sector, stocks in SECTOR_MAP.items():
        if sym in stocks:
            return {"sector": sector, "peers": stocks}
    return {"sector": "Unknown", "peers": []}
