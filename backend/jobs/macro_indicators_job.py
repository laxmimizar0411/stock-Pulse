#!/usr/bin/env python3
"""
Macro Indicators Job for StockPulse.

Fetches macro economic data (USD/INR, commodities, optional RBI metrics)
and upserts into PostgreSQL macro_indicators table.

Data sources:
- yfinance: USD/INR (INR=X or USDINR=X), Brent crude (BZ=F), Gold (GC=F),
  Copper (HG=F), Steel (no single global ticker — optional env override).
- RBI/CPI/IIP: Optional env vars or config for repo rate, CPI, IIP (see .env.example).

Usage:
    python -m jobs.macro_indicators_job              # Last 90 days
    python -m jobs.macro_indicators_job --days 30     # Last 30 days
"""

import asyncio
import argparse
import logging
import os
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from jobs import with_retry

logger = logging.getLogger(__name__)

# yfinance symbols for macro data (daily)
MACRO_TICKERS = {
    "usdinr_rate": "INR=X",      # USD/INR
    "crude_brent_price": "BZ=F", # Brent crude
    "gold_price": "GC=F",        # Gold
    "copper_price": "HG=F",      # Copper
}
# Steel: no universal yfinance ticker; use env MACRO_STEEL_TICKER or leave None


def _fetch_series_yf(ticker: str, start: date, end: date) -> List[Dict[str, Any]]:
    """Fetch daily series from yfinance. Returns list of {date, value}."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed; pip install yfinance")
        return []
    try:
        obj = yf.Ticker(ticker)
        df = obj.history(start=start, end=end + timedelta(days=1), auto_adjust=True)
        if df is None or df.empty:
            return []
        out = []
        for dt, row in df.iterrows():
            d = dt.date() if hasattr(dt, "date") else dt
            close = float(row.get("Close", 0) or 0)
            if close and close == close:  # not NaN
                out.append({"date": d, "value": round(close, 4)})
        return out
    except Exception as e:
        logger.warning("yfinance fetch %s failed: %s", ticker, e)
        return []


def _get_rbi_overrides() -> Dict[str, Optional[float]]:
    """Optional: read RBI repo, CPI, IIP from env (e.g. for manual or external ETL)."""
    out = {}
    for key, env_key in [
        ("rbi_repo_rate", "MACRO_RBI_REPO_RATE"),
        ("cpi_inflation", "MACRO_CPI_INFLATION"),
        ("iip_growth", "MACRO_IIP_GROWTH"),
    ]:
        v = os.environ.get(env_key)
        if v is not None and str(v).strip():
            try:
                out[key] = float(v)
            except ValueError:
                pass
    return out


async def fetch_macro_records(days: int = 90) -> List[Dict[str, Any]]:
    """
    Fetch macro data for the last `days` days.
    Returns list of dicts with keys: date, cpi_inflation, iip_growth, rbi_repo_rate,
    usdinr_rate, crude_brent_price, gold_price, steel_price, copper_price.
    """
    end = date.today()
    start = end - timedelta(days=days)

    # Run yfinance in thread to avoid blocking
    loop = asyncio.get_event_loop()
    by_date: Dict[date, Dict[str, Any]] = {}

    for field_name, ticker in MACRO_TICKERS.items():
        series = await loop.run_in_executor(
            None, lambda t=ticker, s=start, e=end: _fetch_series_yf(t, s, e)
        )
        for item in series:
            d = item["date"]
            if d not in by_date:
                by_date[d] = {"date": d, "cpi_inflation": None, "iip_growth": None,
                              "rbi_repo_rate": None, "usdinr_rate": None,
                              "crude_brent_price": None, "gold_price": None,
                              "steel_price": None, "copper_price": None}
            by_date[d][field_name] = item["value"]

    # Optional steel ticker from env
    steel_ticker = os.environ.get("MACRO_STEEL_TICKER", "").strip()
    if steel_ticker:
        series = await loop.run_in_executor(
            None, lambda: _fetch_series_yf(steel_ticker, start, end)
        )
        for item in series:
            d = item["date"]
            if d not in by_date:
                by_date[d] = {"date": d, "cpi_inflation": None, "iip_growth": None,
                              "rbi_repo_rate": None, "usdinr_rate": None,
                              "crude_brent_price": None, "gold_price": None,
                              "steel_price": None, "copper_price": None}
            by_date[d]["steel_price"] = item["value"]

    # Optional RBI overrides: apply to latest date only (monthly-style usage)
    rbi = _get_rbi_overrides()
    if rbi and by_date:
        latest = max(by_date.keys())
        for k, v in rbi.items():
            by_date[latest][k] = v

    records = [by_date[d] for d in sorted(by_date.keys())]
    for r in records:
        r["date"] = r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"])
    return records


async def run_macro_indicators_job(ts_store, days: int = 90) -> int:
    """Fetch macro data and upsert into PostgreSQL. Returns number of records upserted."""
    if not ts_store or not getattr(ts_store, "_is_initialized", False):
        logger.warning("TimeSeriesStore not available, skipping macro indicators job")
        return 0
    records = await fetch_macro_records(days=days)
    if not records:
        logger.info("No macro records fetched")
        return 0

    @with_retry(max_retries=3)
    async def _upsert_with_retry():
        return await ts_store.upsert_macro_indicators(records)

    count = await _upsert_with_retry()
    logger.info("Macro indicators: upserted %s records", count)
    return count


async def main():
    parser = argparse.ArgumentParser(description="Fetch and store macro indicators")
    parser.add_argument("--days", type=int, default=90, help="Number of days to fetch")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    from services.timeseries_store import TimeSeriesStore
    dsn = os.environ.get("TIMESERIES_DSN", "postgresql://localhost:5432/stockpulse_ts")
    ts_store = TimeSeriesStore(dsn=dsn)
    await ts_store.initialize()
    try:
        n = await run_macro_indicators_job(ts_store, days=args.days)
        print(f"Macro indicators: {n} records upserted")
    finally:
        await ts_store.close()


if __name__ == "__main__":
    asyncio.run(main())
