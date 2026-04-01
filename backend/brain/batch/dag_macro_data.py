"""
DAG: Macro Data — Fetch and store macro-economic indicators.

Schedule: 17:30 IST (post-market)

Steps:
    1. Fetch India VIX, INR/USD, Crude Oil from YFinance
    2. Fetch RBI/macro data from environment or API
    3. Store in MongoDB macro_indicators collection
    4. Calculate derived indicators
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

logger = logging.getLogger("brain.batch.dag_macro_data")

IST = timezone(timedelta(hours=5, minutes=30))


async def dag_macro_data(**context) -> Dict[str, Any]:
    """
    Execute the macro data pipeline.

    Context:
        db: MongoDB database instance
    """
    db = context.get("db")
    if db is None:
        raise ValueError("MongoDB 'db' not provided in context")

    results = {
        "dag": "macro_data",
        "started_at": datetime.now(IST).isoformat(),
        "indicators_updated": 0,
        "errors": [],
    }

    try:
        from brain.features.data_fetchers import fetch_macro_data_yfinance

        macro_data = await fetch_macro_data_yfinance()

        if macro_data:
            collection = db["macro_indicators"]
            today = datetime.now(IST).strftime("%Y-%m-%d")

            doc = {
                "date": today,
                **macro_data,
                "source": "yfinance",
                "updated_at": datetime.now(IST).isoformat(),
            }

            await collection.update_one(
                {"date": today},
                {"$set": doc},
                upsert=True
            )
            results["indicators_updated"] = len(macro_data)

            # Also store in a "latest" document for quick access
            await collection.update_one(
                {"_type": "latest"},
                {"$set": {**doc, "_type": "latest"}},
                upsert=True
            )

            logger.info("Macro DAG: updated %d indicators", len(macro_data))
        else:
            results["errors"].append("No macro data fetched")

    except Exception as e:
        results["errors"].append(str(e))
        logger.exception("Macro DAG error")

    results["completed_at"] = datetime.now(IST).isoformat()
    return results
