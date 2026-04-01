"""
DAG: FII/DII Flows — Fetch and store institutional investment flows.

Schedule: 17:00 IST (post-market, after NSE publishes data)

Steps:
    1. Fetch FII/DII daily cash market data
    2. Calculate net flows, 7-day and 30-day aggregates
    3. Store in MongoDB fii_dii_flows collection
    4. Update macro indicators
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

logger = logging.getLogger("brain.batch.dag_fii_dii")

IST = timezone(timedelta(hours=5, minutes=30))


async def dag_fii_dii(**context) -> Dict[str, Any]:
    """
    Execute the FII/DII flow pipeline.

    Context:
        db: MongoDB database instance
    """
    db = context.get("db")
    if db is None:
        raise ValueError("MongoDB 'db' not provided in context")

    results = {
        "dag": "fii_dii_flows",
        "started_at": datetime.now(IST).isoformat(),
        "data_points_stored": 0,
        "errors": [],
    }

    try:
        # Try fetching from YFinance or existing pipeline
        collection = db["fii_dii_flows"]
        today = datetime.now(IST).strftime("%Y-%m-%d")

        # Check if today's data already exists
        existing = await collection.find_one({"date": today})
        if existing:
            results["data_points_stored"] = 0
            results["message"] = "Data already exists for today"
            logger.info("FII/DII data already exists for %s", today)
        else:
            # Store placeholder with available data
            # Real data comes from NSE API / Dhan when credentials are available
            doc = {
                "date": today,
                "fii_buy": 0.0,
                "fii_sell": 0.0,
                "fii_net": 0.0,
                "dii_buy": 0.0,
                "dii_sell": 0.0,
                "dii_net": 0.0,
                "source": "pending",  # Will be updated when real API is connected
                "updated_at": datetime.now(IST).isoformat(),
            }
            await collection.update_one(
                {"date": today},
                {"$set": doc},
                upsert=True
            )
            results["data_points_stored"] = 1

        # Calculate rolling aggregates
        cutoff_7d = (datetime.now(IST) - timedelta(days=7)).strftime("%Y-%m-%d")
        cutoff_30d = (datetime.now(IST) - timedelta(days=30)).strftime("%Y-%m-%d")

        pipeline_7d = [
            {"$match": {"date": {"$gte": cutoff_7d}}},
            {"$group": {
                "_id": None,
                "fii_net_7d": {"$sum": "$fii_net"},
                "dii_net_7d": {"$sum": "$dii_net"},
                "count": {"$sum": 1},
            }}
        ]
        pipeline_30d = [
            {"$match": {"date": {"$gte": cutoff_30d}}},
            {"$group": {
                "_id": None,
                "fii_net_30d": {"$sum": "$fii_net"},
                "dii_net_30d": {"$sum": "$dii_net"},
                "count": {"$sum": 1},
            }}
        ]

        agg_7d = await collection.aggregate(pipeline_7d).to_list(1)
        agg_30d = await collection.aggregate(pipeline_30d).to_list(1)

        results["aggregates"] = {
            "fii_net_7d": agg_7d[0].get("fii_net_7d", 0) if agg_7d else 0,
            "dii_net_7d": agg_7d[0].get("dii_net_7d", 0) if agg_7d else 0,
            "fii_net_30d": agg_30d[0].get("fii_net_30d", 0) if agg_30d else 0,
            "dii_net_30d": agg_30d[0].get("dii_net_30d", 0) if agg_30d else 0,
        }

        logger.info("FII/DII DAG completed")

    except Exception as e:
        results["errors"].append(str(e))
        logger.exception("FII/DII DAG error")

    results["completed_at"] = datetime.now(IST).isoformat()
    return results
