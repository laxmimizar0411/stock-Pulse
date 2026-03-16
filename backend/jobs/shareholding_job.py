#!/usr/bin/env python3
"""
Shareholding Job for StockPulse.

Populates PostgreSQL shareholding_quarterly from extracted shareholding_history
stored in MongoDB (stock_data.shareholding_history) and/or latest shareholding
fields on each stock document.

This provides a quarterly shareholding pipeline that mirrors the Screener.in
shareholding pattern view (Promoters, FIIs, DIIs, Public, etc.).

Usage:
    python -m jobs.shareholding_job              # All stocks, latest 4 quarters
    python -m jobs.shareholding_job --symbol TCS # Single symbol only
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)


def _parse_quarter_end(period: str) -> Optional[datetime]:
    """
    Parse period labels like 'Mar 2024' or 'Q4 FY24' into a quarter-end date.
    For now we support 'Mon YYYY' style (as used by Screener).
    """
    if not period:
        return None
    text = period.strip()
    # Try formats like 'Mar 2024'
    for fmt in ("%b %Y", "%b-%Y"):
        try:
            dt = datetime.strptime(text, fmt)
            # approximate quarter-end as last day of month (safe for ordering)
            return dt
        except ValueError:
            continue
    return None


def _normalize_history_entry(symbol: str, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a raw shareholding_history entry into shareholding_quarterly schema."""
    period = entry.get("period") or entry.get("quarter") or ""
    dt = _parse_quarter_end(period)
    if not dt:
        return None

    def _pct(key: str) -> Optional[float]:
        val = entry.get(key)
        if val is None:
            return None
        try:
            if isinstance(val, str):
                val = val.replace("%", "").strip()
            return float(val)
        except (ValueError, TypeError):
            return None

    return {
        "symbol": symbol,
        "quarter_end": dt.date().isoformat(),
        "promoter_holding": _pct("Promoters") or _pct("promoter_holding"),
        "promoter_pledging": _pct("Promoter Pledge") or _pct("promoter_pledging"),
        "fii_holding": _pct("FIIs") or _pct("fii_holding"),
        "dii_holding": _pct("DIIs") or _pct("dii_holding"),
        "public_holding": _pct("Public") or _pct("public_holding"),
        # Changes and holder counts are derived by calculation engine; use keys if present.
        "promoter_holding_change": _pct("promoter_holding_change"),
        "fii_holding_change": _pct("fii_holding_change"),
        "num_shareholders": entry.get("num_shareholders"),
        "mf_holding": _pct("mf_holding"),
        "insurance_holding": _pct("insurance_holding"),
    }


async def _fetch_shareholding_docs(
    mongo_url: str,
    db_name: str,
    symbol: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch stock_data documents with shareholding_history from MongoDB."""
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError:
        logger.error("motor not installed. Cannot run shareholding job.")
        return []

    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    try:
        await client.admin.command("ping")
    except Exception as e:
        logger.error("MongoDB not reachable for shareholding job: %s", e)
        return []

    db = client[db_name]
    coll = db["stock_data"]

    query: Dict[str, Any] = {"shareholding_history": {"$exists": True, "$ne": []}}
    if symbol:
        query["symbol"] = symbol.upper()

    cursor = coll.find(query, {"symbol": 1, "shareholding_history": 1})
    docs: List[Dict[str, Any]] = []
    async for doc in cursor:
        docs.append({"symbol": doc.get("symbol"), "shareholding_history": doc.get("shareholding_history", [])})

    client.close()
    return docs


async def run_shareholding_job(ts_store, symbol: Optional[str] = None) -> int:
    """
    Populate shareholding_quarterly from MongoDB stock_data.shareholding_history.
    If symbol is provided, restricts to that symbol.
    """
    if not ts_store or not getattr(ts_store, "_is_initialized", False):
        logger.warning("TimeSeriesStore not available, skipping shareholding job")
        return 0

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB_NAME", os.environ.get("DB_NAME", "stockpulse"))

    docs = await _fetch_shareholding_docs(mongo_url, db_name, symbol=symbol)
    if not docs:
        logger.info("No shareholding_history documents found in MongoDB")
        return 0

    records: List[Dict[str, Any]] = []
    for doc in docs:
        sym = doc.get("symbol")
        history = doc.get("shareholding_history") or []
        # Keep only the last 8 quarters to avoid massive backfill
        for entry in history[-8:]:
            rec = _normalize_history_entry(sym, entry)
            if rec:
                records.append(rec)

    if not records:
        logger.info("No normalized shareholding records to upsert")
        return 0

    count = await ts_store.upsert_shareholding(records)
    logger.info("Shareholding: upserted %s quarterly records", count)
    return count


async def main() -> None:
    parser = argparse.ArgumentParser(description="Populate shareholding_quarterly from MongoDB shareholding_history")
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Optional symbol to restrict processing (default: all symbols)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    from services.timeseries_store import TimeSeriesStore

    dsn = os.environ.get("TIMESERIES_DSN", "postgresql://localhost:5432/stockpulse_ts")
    ts_store = TimeSeriesStore(dsn=dsn)
    await ts_store.initialize()
    try:
        n = await run_shareholding_job(ts_store, symbol=args.symbol)
        print(f"Shareholding: {n} quarterly records upserted")
    finally:
        await ts_store.close()


if __name__ == "__main__":
    asyncio.run(main())

