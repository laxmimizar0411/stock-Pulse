#!/usr/bin/env python3
"""
Valuation Job for StockPulse.

Computes daily valuation metrics in valuation_daily by combining:
  - Latest quarterly fundamentals (EPS, book value, free cash flow, etc.)
  - Latest daily market data (price, shares outstanding, market cap)

This job is a baseline valuation engine when upstream extractors do not
provide valuation fields directly via the pipeline service.

Usage:
    python -m jobs.valuation_job              # Today
    python -m jobs.valuation_job --date 2025-03-01
    python -m jobs.valuation_job --days 5     # Last 5 trading days
"""

import asyncio
import argparse
import logging
import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)


async def _get_trading_dates(conn, target_date: Optional[date], days: Optional[int]) -> List[date]:
    """Resolve target trading dates from prices_daily."""
    if days is not None:
        rows = await conn.fetch(
            """
            SELECT DISTINCT date
            FROM prices_daily
            WHERE date <= CURRENT_DATE
            ORDER BY date DESC
            LIMIT $1
            """,
            days,
        )
        return [r["date"] for r in rows]
    if target_date is not None:
        rows = await conn.fetch(
            "SELECT DISTINCT date FROM prices_daily WHERE date = $1",
            target_date,
        )
        return [r["date"] for r in rows]

    # Default: latest trading day
    rows = await conn.fetch(
        """
        SELECT DISTINCT date
        FROM prices_daily
        WHERE date <= CURRENT_DATE
        ORDER BY date DESC
        LIMIT 1
        """
    )
    return [r["date"] for r in rows]


async def _fetch_latest_fundamentals(conn) -> Dict[str, Dict[str, Any]]:
    """
    Fetch latest fundamentals_quarterly per symbol.
    Returns dict[symbol] -> row dict.
    """
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (symbol)
            symbol, period_end, eps, book_value_per_share,
            free_cash_flow, net_profit, total_equity
        FROM fundamentals_quarterly
        WHERE period_type = 'quarterly'
        ORDER BY symbol, period_end DESC
        """
    )
    by_symbol: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        by_symbol[r["symbol"]] = dict(r)
    return by_symbol


async def _fetch_price_snapshot(
    conn,
    d: date,
) -> Dict[str, Dict[str, Any]]:
    """
    Fetch price snapshot for a given date.
    Returns dict[symbol] -> {close, market_cap, pe_ratio, pb_ratio, dividend_yield, ps_ratio}.
    """
    rows = await conn.fetch(
        """
        SELECT symbol, close, market_cap, pe_ratio, pb_ratio,
               dividend_yield, ps_ratio
        FROM derived_metrics_daily
        WHERE date = $1
        """,
        d,
    )
    snap: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        snap[r["symbol"]] = dict(r)
    return snap


def _safe_ratio(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None:
        return None
    try:
        if den == 0:
            return None
        return float(num) / float(den)
    except Exception:
        return None


async def run_valuation_job(
    ts_store,
    target_date: Optional[date] = None,
    days: Optional[int] = None,
) -> int:
    """
    Compute valuation_daily rows for given date(s) using latest fundamentals_quarterly
    and daily market data from derived_metrics_daily.
    """
    if not ts_store or not getattr(ts_store, "_is_initialized", False):
        logger.warning("TimeSeriesStore not available, skipping valuation job")
        return 0

    async with ts_store._pool.acquire() as conn:
        dates = await _get_trading_dates(conn, target_date, days)
        if not dates:
            logger.info("No trading dates found for valuation job")
            return 0

        fundamentals = await _fetch_latest_fundamentals(conn)

        total = 0
        for d in dates:
            snap = await _fetch_price_snapshot(conn, d)
            if not snap:
                logger.info("No derived_metrics_daily rows for %s", d)
                continue

            records: List[Dict[str, Any]] = []
            for symbol, price_data in snap.items():
                fund = fundamentals.get(symbol, {})
                close = price_data.get("close")
                market_cap = price_data.get("market_cap")
                pe = price_data.get("pe_ratio")
                pb = price_data.get("pb_ratio")
                dy = price_data.get("dividend_yield")
                ps = price_data.get("ps_ratio")

                eps = fund.get("eps")
                book = fund.get("book_value_per_share")
                fcf = fund.get("free_cash_flow")
                net_profit = fund.get("net_profit")
                total_equity = fund.get("total_equity")

                # If extractor already provided P/E/P/B etc., use them.
                pe_ratio = pe
                pb_ratio = pb
                ps_ratio = ps
                earnings_yield = None

                # Derive P/E from price and EPS if missing.
                if pe_ratio is None and eps is not None and close:
                    if eps != 0:
                        pe_ratio = round(close / float(eps), 2)

                # Earnings yield as inverse of P/E.
                if pe_ratio and pe_ratio != 0:
                    earnings_yield = round(100.0 / float(pe_ratio), 4)

                # Derive P/B from price and book value if missing.
                if pb_ratio is None and book is not None and close:
                    if book != 0:
                        pb_ratio = round(close / float(book), 2)

                # FCF yield from free cash flow and market cap (if available).
                fcf_yield = None
                if fcf is not None and market_cap:
                    fcf_yield = round((float(fcf) / float(market_cap)) * 100.0, 4) if market_cap != 0 else None

                # EV and EV/EBITDA can be derived later when debt/cash and EBITDA are wired through;
                # for now, use values from pipeline if present in price_data (if extractor provided them).
                enterprise_value = price_data.get("enterprise_value")
                ev_to_ebitda = price_data.get("ev_to_ebitda")
                ev_to_sales = price_data.get("ev_to_sales")

                record = {
                    "symbol": symbol,
                    "date": d.isoformat(),
                    "market_cap": market_cap,
                    "enterprise_value": enterprise_value,
                    "pe_ratio": pe_ratio,
                    "pe_ratio_forward": price_data.get("pe_ratio_forward"),
                    "peg_ratio": price_data.get("peg_ratio"),
                    "pb_ratio": pb_ratio,
                    "ps_ratio": ps_ratio,
                    "ev_to_ebitda": ev_to_ebitda,
                    "ev_to_sales": ev_to_sales,
                    "dividend_yield": dy,
                    "fcf_yield": fcf_yield,
                    "earnings_yield": earnings_yield,
                    "sector_avg_pe": price_data.get("sector_avg_pe"),
                    "sector_avg_roe": price_data.get("sector_avg_roe"),
                    "industry_avg_pe": price_data.get("industry_avg_pe"),
                    "historical_pe_median": price_data.get("historical_pe_median"),
                    "sector_performance": price_data.get("sector_performance"),
                }
                records.append(record)

            if records:
                n = await ts_store.upsert_valuation(records)
                total += n
                logger.info("Valuation: upserted %s records for %s", n, d)

    return total


async def main() -> None:
    parser = argparse.ArgumentParser(description="Populate valuation_daily from fundamentals and daily market data")
    parser.add_argument("--date", type=str, default=None, help="Single trading date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=None, help="Process last N trading days")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    from services.timeseries_store import TimeSeriesStore

    dsn = os.environ.get("TIMESERIES_DSN", "postgresql://localhost:5432/stockpulse_ts")
    ts_store = TimeSeriesStore(dsn=dsn)
    await ts_store.initialize()
    try:
        target = None
        if args.date:
            target = datetime.strptime(args.date, "%Y-%m-%d").date()
        n = await run_valuation_job(ts_store, target_date=target, days=args.days)
        print(f"Valuation: {n} records upserted")
    finally:
        await ts_store.close()


if __name__ == "__main__":
    asyncio.run(main())

