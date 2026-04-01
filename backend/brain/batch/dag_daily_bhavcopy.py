"""
DAG: Daily Bhavcopy — Download and process NSE Bhavcopy after market close.

Schedule: 16:30 IST (post-market)

Steps:
    1. Download CM-UDiFF bhavcopy from NSE
    2. Parse and validate OHLCV data
    3. Store in MongoDB stock_prices collection
    4. Update delivery volume metrics
    5. Publish to Kafka (when available)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

logger = logging.getLogger("brain.batch.dag_daily_bhavcopy")

IST = timezone(timedelta(hours=5, minutes=30))


async def dag_daily_bhavcopy(**context) -> Dict[str, Any]:
    """
    Execute the daily bhavcopy pipeline.

    Context:
        db: MongoDB database instance
        event_bus: Brain event bus (optional)
    """
    db = context.get("db")
    if db is None:
        raise ValueError("MongoDB 'db' not provided in context")

    results = {
        "dag": "daily_bhavcopy",
        "started_at": datetime.now(IST).isoformat(),
        "records_processed": 0,
        "records_stored": 0,
        "errors": [],
    }

    try:
        # Step 1: Try to use existing bhavcopy extractor
        try:
            from data_extraction.extractors.nse_bhavcopy_extractor import NSEBhavcopyExtractor
            extractor = NSEBhavcopyExtractor()
            bhavcopy_data = await extractor.extract()

            if bhavcopy_data and bhavcopy_data.get("data"):
                records = bhavcopy_data["data"]
                results["records_processed"] = len(records)

                # Step 2: Store in MongoDB
                collection = db["stock_prices_daily"]
                today = datetime.now(IST).strftime("%Y-%m-%d")

                bulk_ops = []
                for record in records:
                    symbol = record.get("symbol") or record.get("SYMBOL", "")
                    if not symbol:
                        continue

                    doc = {
                        "symbol": symbol.upper(),
                        "date": today,
                        "open": float(record.get("open") or record.get("OPEN", 0)),
                        "high": float(record.get("high") or record.get("HIGH", 0)),
                        "low": float(record.get("low") or record.get("LOW", 0)),
                        "close": float(record.get("close") or record.get("CLOSE", 0)),
                        "volume": int(float(record.get("volume") or record.get("TOTTRDQTY", 0))),
                        "delivery_volume": int(float(record.get("delivery_volume") or record.get("DELIV_QTY", 0))),
                        "delivery_pct": float(record.get("delivery_pct") or record.get("DELIV_PER", 0)),
                        "turnover": float(record.get("turnover") or record.get("TOTTRDVAL", 0)),
                        "source": "nse_bhavcopy",
                        "updated_at": datetime.now(IST).isoformat(),
                    }
                    bulk_ops.append(doc)

                if bulk_ops:
                    # Upsert by symbol + date
                    for doc in bulk_ops:
                        await collection.update_one(
                            {"symbol": doc["symbol"], "date": doc["date"]},
                            {"$set": doc},
                            upsert=True
                        )
                    results["records_stored"] = len(bulk_ops)

                logger.info("Bhavcopy DAG: stored %d records", len(bulk_ops))
            else:
                results["errors"].append("No bhavcopy data returned from extractor")

        except ImportError:
            results["errors"].append("NSE Bhavcopy extractor not available")
            logger.warning("NSE Bhavcopy extractor not available")

    except Exception as e:
        results["errors"].append(str(e))
        logger.exception("Bhavcopy DAG error")

    results["completed_at"] = datetime.now(IST).isoformat()
    return results
