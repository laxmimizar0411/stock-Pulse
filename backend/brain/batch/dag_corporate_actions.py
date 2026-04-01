"""
DAG: Corporate Actions — Track dividends, splits, bonuses, rights issues.

Schedule: 17:30 IST (post-market)

Steps:
    1. Fetch corporate actions from NSE/BSE
    2. Parse and categorize (dividend, split, bonus, rights)
    3. Store in MongoDB corporate_actions collection
    4. Update price normalization factors
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

logger = logging.getLogger("brain.batch.dag_corporate_actions")

IST = timezone(timedelta(hours=5, minutes=30))


async def dag_corporate_actions(**context) -> Dict[str, Any]:
    """
    Execute the corporate actions pipeline.

    Context:
        db: MongoDB database instance
    """
    db = context.get("db")
    if db is None:
        raise ValueError("MongoDB 'db' not provided in context")

    results = {
        "dag": "corporate_actions",
        "started_at": datetime.now(IST).isoformat(),
        "actions_found": 0,
        "actions_stored": 0,
        "errors": [],
    }

    try:
        collection = db["corporate_actions"]

        # Try fetching from YFinance actions
        try:
            import yfinance as yf
            from brain.batch.dag_fundamentals import DEFAULT_SYMBOLS

            for symbol in DEFAULT_SYMBOLS[:10]:  # Process top 10 for efficiency
                try:
                    ticker = yf.Ticker(f"{symbol}.NS")

                    # Dividends
                    dividends = ticker.dividends
                    if dividends is not None and len(dividends) > 0:
                        recent_divs = dividends[dividends.index >= (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")]
                        for date_idx, amount in recent_divs.items():
                            doc = {
                                "symbol": symbol.upper(),
                                "action_type": "dividend",
                                "ex_date": str(date_idx.date()),
                                "amount": float(amount),
                                "currency": "INR",
                                "source": "yfinance",
                                "updated_at": datetime.now(IST).isoformat(),
                            }
                            await collection.update_one(
                                {"symbol": doc["symbol"], "action_type": "dividend", "ex_date": doc["ex_date"]},
                                {"$set": doc},
                                upsert=True
                            )
                            results["actions_found"] += 1
                            results["actions_stored"] += 1

                    # Stock Splits
                    splits = ticker.splits
                    if splits is not None and len(splits) > 0:
                        recent_splits = splits[splits.index >= (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")]
                        for date_idx, ratio in recent_splits.items():
                            if ratio != 1.0:
                                doc = {
                                    "symbol": symbol.upper(),
                                    "action_type": "split",
                                    "ex_date": str(date_idx.date()),
                                    "ratio": float(ratio),
                                    "source": "yfinance",
                                    "updated_at": datetime.now(IST).isoformat(),
                                }
                                await collection.update_one(
                                    {"symbol": doc["symbol"], "action_type": "split", "ex_date": doc["ex_date"]},
                                    {"$set": doc},
                                    upsert=True
                                )
                                results["actions_found"] += 1
                                results["actions_stored"] += 1

                except Exception as e:
                    results["errors"].append(f"{symbol}: {str(e)}")

        except ImportError:
            results["errors"].append("YFinance not available")

        logger.info(
            "Corporate Actions DAG: found %d, stored %d",
            results["actions_found"],
            results["actions_stored"],
        )

    except Exception as e:
        results["errors"].append(str(e))
        logger.exception("Corporate Actions DAG error")

    results["completed_at"] = datetime.now(IST).isoformat()
    return results
