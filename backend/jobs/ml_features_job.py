#!/usr/bin/env python3
"""
ML Features Job for StockPulse.

Populates PostgreSQL ``ml_features_daily`` from prices_daily, then runs the
Brain ``FeaturePipeline`` for the same symbol universe and upserts into
``brain_features`` (Phase 1).

Usage:
    python -m jobs.ml_features_job              # Last 60 calendar days
    python -m jobs.ml_features_job --days 30    # Last 30 calendar days
"""

import asyncio
import argparse
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)


def _stddev(values: List[float]) -> float:
    """Population standard deviation helper."""
    n = len(values)
    if n == 0:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    return var ** 0.5


async def _fetch_price_history(conn, days: int) -> Dict[str, List[Tuple[date, float, float]]]:
    """
    Fetch price/volume history for the last `days + 40` days (for rolling windows).
    Returns dict[symbol] -> list[(date, close, volume)], sorted by date ascending.
    """
    window = days + 40  # extra lookback for 10/20-day metrics
    rows = await conn.fetch(
        """
        SELECT symbol, date, close, volume
        FROM prices_daily
        WHERE date >= CURRENT_DATE - $1::int
        ORDER BY symbol, date ASC
        """,
        window,
    )
    by_symbol: Dict[str, List[Tuple[date, float, float]]] = defaultdict(list)
    for r in rows:
        if r["close"] is None:
            continue
        by_symbol[r["symbol"]].append((r["date"], float(r["close"]), float(r["volume"] or 0)))
    return by_symbol


async def run_brain_features_pipeline_batch(ts_store, symbols: List[str]) -> int:
    """
    Compute Brain FeaturePipeline vectors for ``symbols`` and upsert ``brain_features``.
    """
    if not symbols:
        return 0
    try:
        from brain.features.feature_pipeline import FeaturePipeline
        from brain.features.timeseries_fetchers import build_timeseries_fetchers
    except ImportError as e:
        logger.warning("Brain feature pipeline unavailable: %s", e)
        return 0

    pf, ff, mf, mkf = build_timeseries_fetchers(ts_store)
    pipe = FeaturePipeline(
        price_fetcher=pf,
        fundamental_fetcher=ff,
        macro_fetcher=mf,
        market_fetcher=mkf,
    )
    await pipe.initialize()
    results = await pipe.compute_all_symbols(symbols)
    batch: List[Dict[str, Any]] = []
    for sym, feats in results.items():
        if not feats:
            continue
        as_of = await ts_store.get_latest_price_date(sym)
        if as_of is None:
            continue
        batch.append(
            {
                "symbol": sym,
                "as_of_date": as_of,
                "features": feats,
                "feature_count": len(feats),
            }
        )
    if not batch:
        return 0
    n = await ts_store.upsert_brain_features(batch)
    logger.info("Brain features: upserted %s symbol rows", n)
    return n


async def run_ml_features_job(
    ts_store,
    days: int = 60,
    *,
    run_brain_pipeline: bool = True,
) -> Dict[str, int]:
    """
    Build ml_features_daily rows for the last `days` calendar days using prices_daily.

    Features populated:
      - realized_volatility_10d, realized_volatility_20d
      - return_1d_pct, return_3d_pct, return_10d_pct
      - price_vs_sma20_pct, price_vs_sma50_pct
      - volume_zscore (20d window)
      - trading_day_of_week

    Remaining fields (macro/sentiment context) are left as NULL for now; they can be
    enriched later by upstream ETL or a more advanced feature pipeline.
    """
    empty = {"ml_features_daily": 0, "brain_features": 0}
    if not ts_store or not getattr(ts_store, "_is_initialized", False):
        logger.warning("TimeSeriesStore not available, skipping ml_features job")
        return empty

    async with ts_store._pool.acquire() as conn:
        history = await _fetch_price_history(conn, days=days)

    if not history:
        logger.info("No prices_daily history available for ml_features job")
        return empty

    cutoff = date.today() - timedelta(days=days)
    records: List[Dict[str, Any]] = []

    for symbol, series in history.items():
        if len(series) < 5:
            continue
        # series is sorted by date ASC
        closes = [c for (_, c, _) in series]
        volumes = [v for (_, _, v) in series]

        # Precompute daily returns in percent
        returns_pct: List[float] = [0.0]
        for i in range(1, len(closes)):
            prev = closes[i - 1]
            curr = closes[i]
            if prev:
                r = (curr / prev - 1.0) * 100.0
            else:
                r = 0.0
            returns_pct.append(r)

        # Rolling window helpers
        for idx, (d, close, vol) in enumerate(series):
            if d < cutoff:
                continue

            # 10d / 20d realized volatility of daily returns
            rv10 = None
            rv20 = None
            if idx >= 1:
                window_start_10 = max(0, idx - 9)
                window_rets_10 = returns_pct[window_start_10 : idx + 1]
                if len(window_rets_10) >= 5:
                    rv10 = round(_stddev(window_rets_10), 4)

                window_start_20 = max(0, idx - 19)
                window_rets_20 = returns_pct[window_start_20 : idx + 1]
                if len(window_rets_20) >= 10:
                    rv20 = round(_stddev(window_rets_20), 4)

            # Point-in-time returns
            r1 = returns_pct[idx] if idx >= 0 else None
            r3 = None
            r10 = None
            if idx >= 3 and closes[idx - 3]:
                r3 = round((closes[idx] / closes[idx - 3] - 1.0) * 100.0, 4)
            if idx >= 10 and closes[idx - 10]:
                r10 = round((closes[idx] / closes[idx - 10] - 1.0) * 100.0, 4)

            # Price vs SMA20 / SMA50
            sma20 = None
            sma50 = None
            if idx >= 19:
                sma20 = sum(closes[idx - 19 : idx + 1]) / 20.0
            if idx >= 49:
                sma50 = sum(closes[idx - 49 : idx + 1]) / 50.0

            vs_sma20 = None
            vs_sma50 = None
            if sma20:
                vs_sma20 = round((close / sma20 - 1.0) * 100.0, 4)
            if sma50:
                vs_sma50 = round((close / sma50 - 1.0) * 100.0, 4)

            # Volume Z-score over 20-day window
            vol_z = None
            if idx >= 19:
                window_vols = volumes[idx - 19 : idx + 1]
                mean_v = sum(window_vols) / len(window_vols)
                std_v = _stddev(window_vols)
                if std_v > 0:
                    vol_z = round((vol - mean_v) / std_v, 4)

            # Trading day of week (0=Monday .. 6=Sunday)
            dow = d.weekday()

            records.append(
                {
                    "symbol": symbol,
                    "date": d.isoformat(),
                    "realized_volatility_10d": rv10,
                    "realized_volatility_20d": rv20,
                    "return_1d_pct": round(r1, 4) if r1 is not None else None,
                    "return_3d_pct": r3,
                    "return_10d_pct": r10,
                    "momentum_rank_sector": None,
                    "price_vs_sma20_pct": vs_sma20,
                    "price_vs_sma50_pct": vs_sma50,
                    "volume_zscore": vol_z,
                    "volatility_percentile_1y": None,
                    "turnover_20d_avg": None,
                    "free_float_market_cap": None,
                    "days_since_earnings": None,
                    "days_to_earnings": None,
                    "trading_day_of_week": dow,
                    "nifty_50_return_1m": None,
                    "fii_net_activity_daily": None,
                    "dii_net_activity_daily": None,
                    "sp500_return_1d": None,
                    "nasdaq_return_1d": None,
                }
            )

    count_ml = 0
    if records:
        count_ml = await ts_store.upsert_ml_features(records)
        logger.info("ML features: upserted %s records", count_ml)
    else:
        logger.info("No ml_features_daily rows in date window; skipping ml_features upsert")

    brain_n = 0
    if run_brain_pipeline:
        try:
            brain_n = await run_brain_features_pipeline_batch(
                ts_store, sorted(history.keys())
            )
        except Exception:
            logger.exception("Brain feature pipeline batch failed")

    return {"ml_features_daily": count_ml, "brain_features": brain_n}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Populate ml_features_daily from prices_daily")
    parser.add_argument(
        "--days",
        type=int,
        default=60,
        help="Process last N calendar days of data (default: 60)",
    )
    parser.add_argument(
        "--skip-brain",
        action="store_true",
        help="Skip Brain FeaturePipeline / brain_features upsert",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    from services.timeseries_store import TimeSeriesStore

    dsn = os.environ.get("TIMESERIES_DSN", "postgresql://localhost:5432/stockpulse_ts")
    ts_store = TimeSeriesStore(dsn=dsn)
    await ts_store.initialize()
    try:
        n = await run_ml_features_job(
            ts_store,
            days=args.days,
            run_brain_pipeline=not args.skip_brain,
        )
        print(
            f"ml_features_daily: {n['ml_features_daily']} records | "
            f"brain_features: {n['brain_features']} symbols"
        )
    finally:
        await ts_store.close()


if __name__ == "__main__":
    asyncio.run(main())

