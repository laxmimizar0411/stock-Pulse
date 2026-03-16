#!/usr/bin/env python3
"""
Derivatives (F&O) Job for StockPulse.

Populates PostgreSQL derivatives_daily from:
1. NSE F&O bhavcopy when available (archives.nseindia.com).
2. Fallback: one row per symbol per date from prices_daily with NULL F&O fields,
   so the table is queryable and ready for real F&O data.

Usage:
    python -m jobs.derivatives_job              # Today / last trading day
    python -m jobs.derivatives_job --date 2025-03-01
    python -m jobs.derivatives_job --days 5     # Last 5 trading days
"""

import asyncio
import argparse
import csv
import io
import logging
import os
import sys
import zipfile
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from jobs import with_retry

logger = logging.getLogger(__name__)

# NSE F&O bhavcopy: historical DERIVATIVES folder (example: fo28MAR2024bhav.csv.zip)
NSE_FO_BASE = "https://archives.nseindia.com/content/historical/DERIVATIVES"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.nseindia.com/",
}


def _safe_float(v: Any) -> Optional[float]:
    if v is None or v == "" or v == "-":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _safe_int(v: Any) -> Optional[int]:
    if v is None or v == "" or v == "-":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


async def _fetch_nse_fo_bhavcopy(target_date: date) -> Optional[List[Dict[str, Any]]]:
    """
    Download NSE F&O bhavcopy for target_date. Returns list of records
    (one per symbol per date) with keys matching derivatives_daily, or None if failed.
    """
    try:
        import aiohttp
    except ImportError:
        logger.warning("aiohttp not installed; cannot download NSE FO bhavcopy")
        return None

    # foDDMMMYYYYbhav.csv.zip, e.g. fo28MAR2024bhav.csv.zip
    day = target_date.strftime("%d")
    mon = target_date.strftime("%b").upper()  # MAR, APR
    year = target_date.strftime("%Y")
    month_dir = target_date.strftime("%b").capitalize()  # Mar, Apr
    filename = f"fo{day}{mon}{year}bhav.csv.zip"
    url = f"{NSE_FO_BASE}/{year}/{month_dir}/{filename}"

    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.debug("NSE FO bhavcopy %s returned %s", url, resp.status)
                    return None
                content = await resp.read()
    except Exception as e:
        logger.debug("NSE FO bhavcopy download failed: %s", e)
        return None

    # Parse ZIP CSV
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = [n for n in zf.namelist() if n.endswith(".csv")]
            if not names:
                return None
            with zf.open(names[0]) as f:
                text = f.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("NSE FO bhavcopy parse error: %s", e)
        return None

    # Aggregate by symbol (underlying). CSV may have SYMBOL, OPEN_INT, CLOSE, CONTRACTS, etc.
    # Some files have INSTRUMENT (FUTIDX, FUTSTK, OPTIDX, OPTSTK), EXPIRY_DT, etc.
    by_symbol: Dict[str, Dict[str, Any]] = {}
    date_str = target_date.isoformat()

    try:
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            # Underlying symbol: SYMBOL or TckrSymb
            sym = (row.get("SYMBOL") or row.get("TckrSymb") or "").strip()
            if not sym or sym in ("SYMBOL", "TckrSymb", "Symbol"):
                continue
            # Skip index names if we only want stocks (optional: keep NIFTY, BANKNIFTY for index F&O)
            if sym not in by_symbol:
                by_symbol[sym] = {
                    "symbol": sym,
                    "date": date_str,
                    "futures_oi": None,
                    "futures_oi_change_pct": None,
                    "futures_price_near": None,
                    "futures_basis_pct": None,
                    "fii_index_futures_long_oi": None,
                    "fii_index_futures_short_oi": None,
                    "options_call_oi_total": None,
                    "options_put_oi_total": None,
                    "put_call_ratio_oi": None,
                    "put_call_ratio_volume": None,
                    "options_max_pain_strike": None,
                    "iv_atm_pct": None,
                    "iv_percentile_1y": None,
                    "pcr_index_level": None,
                    "is_placeholder": False,
                }
            rec = by_symbol[sym]
            open_int = _safe_int(row.get("OPEN_INT") or row.get("Open_Interest") or row.get("OPEN_INTEGER"))
            close = _safe_float(row.get("CLOSE") or row.get("ClsPric"))
            if open_int is not None:
                rec["futures_oi"] = (rec["futures_oi"] or 0) + open_int
            if close is not None and rec["futures_price_near"] is None:
                rec["futures_price_near"] = close
    except Exception as e:
        logger.warning("NSE FO CSV parse error: %s", e)
        return None

    if not by_symbol:
        return None
    return list(by_symbol.values())


async def _fallback_from_prices(ts_store, target_dates: List[date]) -> List[Dict[str, Any]]:
    """Build minimal derivatives_daily rows (symbol, date, NULL F&O) from prices_daily.
    Records are marked with is_placeholder=True to distinguish from real F&O data."""
    if not ts_store or not getattr(ts_store, "_is_initialized", False):
        return []
    records = []
    async with ts_store._pool.acquire() as conn:
        for d in target_dates:
            date_str = d.isoformat()
            rows = await conn.fetch(
                "SELECT DISTINCT symbol FROM prices_daily WHERE date = $1",
                d,
            )
            for r in rows:
                records.append({
                    "symbol": r["symbol"],
                    "date": date_str,
                    "futures_oi": None,
                    "futures_oi_change_pct": None,
                    "futures_price_near": None,
                    "futures_basis_pct": None,
                    "fii_index_futures_long_oi": None,
                    "fii_index_futures_short_oi": None,
                    "options_call_oi_total": None,
                    "options_put_oi_total": None,
                    "put_call_ratio_oi": None,
                    "put_call_ratio_volume": None,
                    "options_max_pain_strike": None,
                    "iv_atm_pct": None,
                    "iv_percentile_1y": None,
                    "pcr_index_level": None,
                    "is_placeholder": True,
                })
    return records


async def run_derivatives_job(
    ts_store,
    target_date: Optional[date] = None,
    days: Optional[int] = None,
) -> int:
    """
    Run derivatives job for given date(s). If NSE FO bhavcopy is available, use it;
    else upsert placeholder rows from prices_daily. Returns number of records upserted.
    """
    if not ts_store or not getattr(ts_store, "_is_initialized", False):
        logger.warning("TimeSeriesStore not available")
        return 0

    if days is not None:
        # Last N trading days (simple: calendar days)
        end = date.today()
        target_dates = [end - timedelta(days=i) for i in range(days)]
    elif target_date is not None:
        target_dates = [target_date]
    else:
        target_dates = [date.today()]

    @with_retry(max_retries=3)
    async def _upsert_with_retry(recs):
        return await ts_store.upsert_derivatives(recs)

    total = 0
    for d in target_dates:
        records = await _fetch_nse_fo_bhavcopy(d)
        if not records:
            records = await _fallback_from_prices(ts_store, [d])
            if records:
                logger.info("Derivatives: using fallback from prices_daily for %s (%s symbols)", d, len(records))
        if records:
            try:
                n = await _upsert_with_retry(records)
                total += n
            except Exception as e:
                logger.error("Failed to upsert derivatives for %s after retries: %s", d, e)
    return total


async def main():
    parser = argparse.ArgumentParser(description="Populate derivatives_daily from NSE F&O or prices fallback")
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=None, help="Process last N days")
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
        n = await run_derivatives_job(ts_store, target_date=target, days=args.days)
        print(f"Derivatives: {n} records upserted")
    finally:
        await ts_store.close()


if __name__ == "__main__":
    asyncio.run(main())
