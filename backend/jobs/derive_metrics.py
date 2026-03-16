#!/usr/bin/env python3
"""
Derived Metrics Computation Job for StockPulse.

Reads from prices_daily (and optionally technical_indicators, fundamentals_quarterly)
to compute derived_metrics_daily and weekly_metrics, then upserts them into PostgreSQL.

Usage:
    python -m jobs.derive_metrics                    # Compute for all symbols
    python -m jobs.derive_metrics --symbols TCS,INFY # Specific symbols
    python -m jobs.derive_metrics --weekly           # Also compute weekly metrics

Can also be called programmatically after a pipeline run:
    from jobs.derive_metrics import compute_derived_metrics
    await compute_derived_metrics(ts_store)
"""

import asyncio
import argparse
import hashlib
import logging
import os
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure imports work from backend/
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from jobs import with_retry

logger = logging.getLogger(__name__)


def _symbol_lock_id(symbol: str) -> int:
    """Generate a stable advisory lock ID from a symbol name."""
    # Use first 8 bytes of hash as a signed 64-bit int for pg_advisory_lock
    h = hashlib.sha256(f"derive_metrics:{symbol}".encode()).digest()
    return int.from_bytes(h[:8], "big", signed=True)

async def _retry_async(op_name: str, coro, max_attempts: int = 3, base_delay: float = 0.5) -> Any:
    """
    Simple retry helper with exponential backoff for transient failures.
    Logs warnings on retries and re-raises the last exception on failure.
    """
    attempt = 0
    last_exc: Optional[BaseException] = None
    while attempt < max_attempts:
        try:
            return await coro()
        except Exception as e:
            last_exc = e
            attempt += 1
            if attempt >= max_attempts:
                logger.error("%s failed after %s attempts", op_name, attempt, exc_info=e)
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning("%s failed (attempt %s/%s), retrying in %.2fs: %s",
                           op_name, attempt, max_attempts, delay, e)
            await asyncio.sleep(delay)

async def compute_derived_metrics(
    ts_store,
    symbols: Optional[List[str]] = None,
    lookback_days: int = 260,
) -> int:
    """
    Compute derived_metrics_daily from prices_daily for each symbol.

    Computes:
    - daily_return_pct: (close - prev_close) / prev_close * 100
    - return_5d_pct, return_20d_pct, return_60d_pct: rolling returns
    - day_range_pct: (high - low) / low * 100
    - gap_percentage: (open - prev_close) / prev_close * 100
    - week_52_high, week_52_low: rolling 252-day max/min close
    - distance_from_52w_high: (close - 52w_high) / 52w_high * 100
    - volume_ratio: volume / avg_volume_20d
    - avg_volume_20d: 20-day average volume

    Returns the number of records upserted.
    """
    if not ts_store or not ts_store._is_initialized:
        logger.warning("TimeSeriesStore not available, skipping derived metrics")
        return 0

    # Get distinct symbols from prices_daily
    async with ts_store._pool.acquire() as conn:
        if symbols:
            sym_rows = await conn.fetch(
                "SELECT DISTINCT symbol FROM prices_daily WHERE symbol = ANY($1) ORDER BY symbol",
                symbols,
            )
        else:
            sym_rows = await conn.fetch(
                "SELECT DISTINCT symbol FROM prices_daily ORDER BY symbol"
            )

    all_symbols = [r["symbol"] for r in sym_rows]
    logger.info(f"Computing derived metrics for {len(all_symbols)} symbols")

    total_upserted = 0

    @with_retry(max_retries=3)
    async def _process_symbol(sym: str) -> int:
        """Compute and upsert derived metrics for a single symbol with advisory lock."""
        lock_id = _symbol_lock_id(sym)
        async with ts_store._pool.acquire() as conn:
            # Try advisory lock — skip if another worker is processing this symbol
            acquired = await conn.fetchval("SELECT pg_try_advisory_lock($1)", lock_id)
            if not acquired:
                logger.debug("Skipping %s — advisory lock held by another worker", sym)
                return 0
            try:
                prices = await ts_store.get_prices(sym, limit=lookback_days)
                if len(prices) < 2:
                    return 0

                prices.sort(key=lambda p: p["date"])

                derived_records = []
                closes = [float(p.get("close") or 0) for p in prices]
                volumes = [int(p.get("volume") or 0) for p in prices]

                for i, p in enumerate(prices):
                    close = closes[i]
                    if close <= 0:
                        continue

                    rec = {
                        "symbol": sym,
                        "date": p["date"].isoformat() if hasattr(p["date"], "isoformat") else str(p["date"]),
                    }

                    if i > 0 and closes[i - 1] > 0:
                        rec["daily_return_pct"] = round((close - closes[i - 1]) / closes[i - 1] * 100, 4)

                    for n, key in [(5, "return_5d_pct"), (20, "return_20d_pct"), (60, "return_60d_pct")]:
                        if i >= n and closes[i - n] > 0:
                            rec[key] = round((close - closes[i - n]) / closes[i - n] * 100, 4)

                    high = float(p.get("high") or 0)
                    low = float(p.get("low") or 0)
                    if low > 0:
                        rec["day_range_pct"] = round((high - low) / low * 100, 4)

                    open_price = float(p.get("open") or 0)
                    prev_close = float(p.get("prev_close") or (closes[i - 1] if i > 0 else 0))
                    if prev_close > 0 and open_price > 0:
                        rec["gap_percentage"] = round((open_price - prev_close) / prev_close * 100, 4)

                    lookback_252 = max(0, i - 252)
                    window_closes = closes[lookback_252 : i + 1]
                    if window_closes:
                        w52_high = max(window_closes)
                        w52_low = min(window_closes)
                        rec["week_52_high"] = round(w52_high, 2)
                        rec["week_52_low"] = round(w52_low, 2)
                        if w52_high > 0:
                            rec["distance_from_52w_high"] = round((close - w52_high) / w52_high * 100, 4)

                    if i >= 20:
                        avg_vol = sum(volumes[i - 20 : i]) / 20
                        rec["avg_volume_20d"] = int(avg_vol)
                        if avg_vol > 0:
                            rec["volume_ratio"] = round(volumes[i] / avg_vol, 4)

                    derived_records.append(rec)

                if derived_records:
                    return await ts_store.upsert_derived_metrics(derived_records)
                return 0
            finally:
                await conn.execute("SELECT pg_advisory_unlock($1)", lock_id)

    for symbol in all_symbols:
        try:
            count = await _process_symbol(symbol)
            total_upserted += count
        except Exception as e:
            logger.warning(f"Error computing derived metrics for {symbol}: {e}")

    logger.info(f"Derived metrics: {total_upserted} records upserted for {len(all_symbols)} symbols")
    return total_upserted


async def compute_weekly_metrics(
    ts_store,
    symbols: Optional[List[str]] = None,
    weeks: int = 104,
) -> int:
    """
    Compute weekly_metrics from prices_daily and technical_indicators.

    Computes:
    - sma_weekly_crossover: whether weekly SMA50 > SMA200 (from daily data)

    Returns the number of records upserted.
    """
    if not ts_store or not ts_store._is_initialized:
        return 0

    async with ts_store._pool.acquire() as conn:
        if symbols:
            sym_rows = await conn.fetch(
                "SELECT DISTINCT symbol FROM prices_daily WHERE symbol = ANY($1)", symbols
            )
        else:
            sym_rows = await conn.fetch("SELECT DISTINCT symbol FROM prices_daily")

    all_symbols = [r["symbol"] for r in sym_rows]
    total = 0

    @with_retry(max_retries=3)
    async def _process_weekly_symbol(sym: str) -> int:
        """Compute and upsert weekly metrics for a single symbol with advisory lock."""
        lock_id = _symbol_lock_id(f"weekly:{sym}")
        async with ts_store._pool.acquire() as conn:
            acquired = await conn.fetchval("SELECT pg_try_advisory_lock($1)", lock_id)
            if not acquired:
                logger.debug("Skipping weekly %s — advisory lock held", sym)
                return 0
            try:
                prices = await ts_store.get_prices(sym, limit=weeks * 7)
                if len(prices) < 50:
                    return 0

                prices.sort(key=lambda p: p["date"])

                week_buckets: Dict[str, List] = {}
                for p in prices:
                    d = p["date"]
                    if hasattr(d, "isocalendar"):
                        monday = d - timedelta(days=d.weekday())
                        key = monday.isoformat()
                    else:
                        continue
                    week_buckets.setdefault(key, []).append(p)

                records = []
                closes_all = [float(p.get("close") or 0) for p in prices]

                for week_start_str, week_prices in sorted(week_buckets.items()):
                    if not week_prices:
                        continue

                    last_day = week_prices[-1]
                    last_idx = None
                    for idx_w, p in enumerate(prices):
                        if p["date"] == last_day["date"] and p.get("symbol") == sym:
                            last_idx = idx_w
                            break
                    if last_idx is None or last_idx < 200:
                        continue

                    sma50 = sum(closes_all[last_idx - 49 : last_idx + 1]) / 50
                    sma200 = sum(closes_all[last_idx - 199 : last_idx + 1]) / 200

                    records.append({
                        "symbol": sym,
                        "week_start": week_start_str,
                        "sma_weekly_crossover": sma50 > sma200,
                    })

                if records:
                    return await ts_store.upsert_weekly_metrics(records)
                return 0
            finally:
                await conn.execute("SELECT pg_advisory_unlock($1)", lock_id)

    for symbol in all_symbols:
        try:
            count = await _process_weekly_symbol(symbol)
            total += count
        except Exception as e:
            logger.warning(f"Error computing weekly metrics for {symbol}: {e}")

    logger.info(f"Weekly metrics: {total} records upserted for {len(all_symbols)} symbols")
    return total


async def main():
    parser = argparse.ArgumentParser(description="Compute derived metrics from prices_daily")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols")
    parser.add_argument("--weekly", action="store_true", help="Also compute weekly metrics")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    from services.timeseries_store import TimeSeriesStore

    dsn = os.environ.get("TIMESERIES_DSN", "postgresql://localhost:5432/stockpulse_ts")
    ts_store = TimeSeriesStore(dsn=dsn)
    await ts_store.initialize()

    symbols = args.symbols.split(",") if args.symbols else None

    count = await compute_derived_metrics(ts_store, symbols=symbols)
    print(f"Derived metrics: {count} records upserted")

    if args.weekly:
        wcount = await compute_weekly_metrics(ts_store, symbols=symbols)
        print(f"Weekly metrics: {wcount} records upserted")

    await ts_store.close()


if __name__ == "__main__":
    asyncio.run(main())
