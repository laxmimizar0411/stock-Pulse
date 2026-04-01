"""
DAG: Fundamentals — Fetch and store fundamental data for tracked stocks.

Schedule: 18:00 IST (daily, post-market)

Steps:
    1. Get list of tracked symbols from MongoDB
    2. Fetch fundamental data from YFinance / Screener
    3. Store/update in MongoDB stock_fundamentals collection
    4. Compute and store derived fundamental features
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger("brain.batch.dag_fundamentals")

IST = timezone(timedelta(hours=5, minutes=30))

# Default tracked symbols (NIFTY 50 core)
DEFAULT_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK",
    "LT", "AXISBANK", "BAJFINANCE", "ASIANPAINT", "MARUTI",
    "TATAMOTORS", "SUNPHARMA", "TITAN", "WIPRO", "HCLTECH",
    "ULTRACEMCO", "NESTLEIND", "POWERGRID", "NTPC", "TECHM",
    "TATASTEEL", "DRREDDY", "BAJAJFINSV", "INDUSINDBK", "M&M",
]


async def dag_fundamentals(**context) -> Dict[str, Any]:
    """
    Execute the fundamentals update pipeline.

    Context:
        db: MongoDB database instance
        symbols: Optional list of symbols to process
    """
    db = context.get("db")
    if db is None:
        raise ValueError("MongoDB 'db' not provided in context")

    symbols = context.get("symbols", DEFAULT_SYMBOLS)
    batch_size = context.get("batch_size", 5)

    results = {
        "dag": "fundamentals",
        "started_at": datetime.now(IST).isoformat(),
        "symbols_processed": 0,
        "symbols_updated": 0,
        "symbols_failed": 0,
        "errors": [],
    }

    try:
        from brain.features.data_fetchers import fetch_fundamental_data_yfinance
        import asyncio

        collection = db["stock_fundamentals"]

        # Process in batches to avoid rate limiting
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            tasks = [fetch_fundamental_data_yfinance(sym) for sym in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for sym, data in zip(batch, batch_results):
                results["symbols_processed"] += 1

                if isinstance(data, Exception):
                    results["symbols_failed"] += 1
                    results["errors"].append(f"{sym}: {str(data)}")
                    continue

                if data and data.get("market_cap"):
                    data["updated_at"] = datetime.now(IST).isoformat()
                    data["symbol"] = sym.upper()
                    await collection.update_one(
                        {"symbol": sym.upper()},
                        {"$set": data},
                        upsert=True
                    )
                    results["symbols_updated"] += 1
                else:
                    results["symbols_failed"] += 1

            # Small delay between batches to be polite to APIs
            if i + batch_size < len(symbols):
                await asyncio.sleep(2)

        logger.info(
            "Fundamentals DAG: processed %d, updated %d, failed %d",
            results["symbols_processed"],
            results["symbols_updated"],
            results["symbols_failed"],
        )

    except Exception as e:
        results["errors"].append(str(e))
        logger.exception("Fundamentals DAG error")

    results["completed_at"] = datetime.now(IST).isoformat()
    return results
