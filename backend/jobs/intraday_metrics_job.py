#!/usr/bin/env python3
"""
Intraday Metrics Job for StockPulse.

Populates PostgreSQL intraday_metrics with end-of-day snapshots derived from
daily data (technical_indicators + prices_daily). When a live intraday feed
is available, it can replace or augment this job.

Each row: one (symbol, timestamp) per symbol per trading day, with
rsi_hourly = rsi_14, macd_crossover_hourly = macd, vwap_intraday = vwap or close,
advance_decline_ratio for the day (optional), sectoral_heatmap / india_vix = null.

Usage:
    python -m jobs.intraday_metrics_job           # Latest trading day
    python -m jobs.intraday_metrics_job --days 5  # Last 5 trading days
"""

import asyncio
import argparse
import logging
import os
import sys
from datetime import datetime, date, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from jobs import with_retry

logger = logging.getLogger(__name__)

# EOD time for NSE (15:30 IST = UTC+5:30)
EOD_HOUR, EOD_MINUTE = 15, 30
IST = timezone(timedelta(hours=5, minutes=30))


def _eod_utc(d: date) -> datetime:
    """Return EOD 15:30 IST as timezone-aware UTC datetime."""
    local = datetime.combine(d, time(EOD_HOUR, EOD_MINUTE), tzinfo=IST)
    return local.astimezone(timezone.utc)


async def _advance_decline_ratio(conn, d: date) -> Optional[float]:
    """Ratio of advancing (close > open) to declining (close < open) symbols; None if no data."""
    rows = await conn.fetch(
        """
        SELECT
            COUNT(*) FILTER (WHERE close > open) AS advancing,
            COUNT(*) FILTER (WHERE close < open) AS declining
        FROM prices_daily
        WHERE date = $1 AND open > 0
        """,
        d,
    )
    if not rows or (rows[0]["advancing"] is None and rows[0]["declining"] is None):
        return None
    adv = int(rows[0]["advancing"] or 0)
    dec = int(rows[0]["declining"] or 0)
    if dec == 0:
        return float(adv) if adv else None
    return round(adv / dec, 4)


async def run_intraday_metrics_job(ts_store, days: int = 1) -> int:
    """
    Build intraday_metrics rows from latest daily technicals and prices.
    Uses one row per symbol per date with timestamp = EOD (15:30 IST).
    Returns number of records upserted.
    """
    if not ts_store or not getattr(ts_store, "_is_initialized", False):
        logger.warning("TimeSeriesStore not available")
        return 0

    records: List[Dict[str, Any]] = []
    async with ts_store._pool.acquire() as conn:
        # Distinct (symbol, date) from technical_indicators with latest N days
        cursor = await conn.fetch(
            """
            SELECT t.symbol, t.date,
                   t.rsi_14 AS rsi_hourly, t.macd AS macd_crossover_hourly
            FROM technical_indicators t
            WHERE t.date >= (CURRENT_DATE - $1::int)
            ORDER BY t.symbol, t.date DESC
            """,
            days,
        )
        # One row per (symbol, date) — take latest per symbol per date (already DESC)
        seen: set = set()
        for row in cursor:
            key = (row["symbol"], row["date"])
            if key in seen:
                continue
            seen.add(key)
            d = row["date"]
            ts = _eod_utc(d)
            vwap_val = await conn.fetchval(
                "SELECT vwap FROM prices_daily WHERE symbol = $1 AND date = $2",
                row["symbol"], d,
            )
            if vwap_val is None:
                vwap_val = await conn.fetchval(
                    "SELECT close FROM prices_daily WHERE symbol = $1 AND date = $2",
                    row["symbol"], d,
                )
            records.append({
                "symbol": row["symbol"],
                "timestamp": ts.isoformat(),
                "rsi_hourly": float(row["rsi_hourly"]) if row["rsi_hourly"] is not None else None,
                "macd_crossover_hourly": float(row["macd_crossover_hourly"]) if row["macd_crossover_hourly"] is not None else None,
                "vwap_intraday": float(vwap_val) if vwap_val is not None else None,
                "advance_decline_ratio": None,  # set per-date below
                "sectoral_heatmap": None,
                "india_vix": None,
            })

        # Set advance_decline_ratio for all rows of the same date
        by_date: Dict[date, Optional[float]] = {}
        for r in records:
            d = r["timestamp"][:10]  # YYYY-MM-DD
            d_parsed = datetime.strptime(d, "%Y-%m-%d").date()
            if d_parsed not in by_date:
                by_date[d_parsed] = await _advance_decline_ratio(conn, d_parsed)
            r["advance_decline_ratio"] = by_date[d_parsed]

    if not records:
        logger.info("No intraday_metrics records to upsert")
        return 0

    @with_retry(max_retries=3)
    async def _upsert_with_retry():
        return await ts_store.upsert_intraday_metrics(records)

    count = await _upsert_with_retry()
    logger.info("Intraday metrics: upserted %s records", count)
    return count
    # Retry transient failures when writing to PostgreSQL
    attempts = 0
    last_exc: Optional[BaseException] = None
    while attempts < 3:
        try:
            count = await ts_store.upsert_intraday_metrics(records)
            logger.info("Intraday metrics: upserted %s records", count)
            last_exc = None
            return count
        except Exception as e:
            attempts += 1
            last_exc = e
            delay = 0.5 * (2 ** (attempts - 1))
            logger.warning(
                "upsert_intraday_metrics failed (attempt %s/3), retrying in %.2fs: %s",
                attempts, delay, e,
            )
            await asyncio.sleep(delay)

    logger.error("upsert_intraday_metrics failed after retries", exc_info=last_exc)
    raise last_exc


async def main():
    parser = argparse.ArgumentParser(description="Populate intraday_metrics from daily technicals/prices")
    parser.add_argument("--days", type=int, default=1, help="Process last N calendar days of data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    from services.timeseries_store import TimeSeriesStore
    dsn = os.environ.get("TIMESERIES_DSN", "postgresql://localhost:5432/stockpulse_ts")
    ts_store = TimeSeriesStore(dsn=dsn)
    await ts_store.initialize()
    try:
        n = await run_intraday_metrics_job(ts_store, days=args.days)
        print(f"Intraday metrics: {n} records upserted")
    finally:
        await ts_store.close()


if __name__ == "__main__":
    asyncio.run(main())
