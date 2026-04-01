"""
Seed sample OHLCV data into MongoDB for Brain testing.
Uses a geometric Brownian motion model to generate realistic stock data.
"""

import asyncio
import math
import os
import random
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient

IST = timezone(timedelta(hours=5, minutes=30))

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGO_DB_NAME", "stockpulse")

# Stocks with realistic starting prices and volatilities
STOCKS = {
    "RELIANCE": {"price": 2850, "vol": 0.018, "avg_volume": 12_000_000},
    "TCS": {"price": 3900, "vol": 0.015, "avg_volume": 3_500_000},
    "HDFCBANK": {"price": 1650, "vol": 0.016, "avg_volume": 8_000_000},
    "INFY": {"price": 1500, "vol": 0.017, "avg_volume": 6_000_000},
    "ICICIBANK": {"price": 1200, "vol": 0.019, "avg_volume": 10_000_000},
    "SBIN": {"price": 750, "vol": 0.022, "avg_volume": 15_000_000},
    "TATAMOTORS": {"price": 700, "vol": 0.025, "avg_volume": 7_000_000},
    "ITC": {"price": 430, "vol": 0.013, "avg_volume": 9_000_000},
    "BHARTIARTL": {"price": 1550, "vol": 0.016, "avg_volume": 4_000_000},
    "KOTAKBANK": {"price": 1750, "vol": 0.017, "avg_volume": 3_000_000},
}


def generate_ohlcv(symbol: str, config: dict, days: int = 500):
    """Generate realistic OHLCV data using geometric Brownian motion."""
    records = []
    price = config["price"]
    vol = config["vol"]
    avg_vol = config["avg_volume"]
    drift = 0.0002  # Slight upward drift

    start_date = datetime.now(IST) - timedelta(days=days)

    for i in range(days):
        day = start_date + timedelta(days=i)
        # Skip weekends
        if day.weekday() >= 5:
            continue

        # GBM price simulation
        ret = random.gauss(drift, vol)
        price = price * math.exp(ret)

        # Generate OHLC from close
        intraday_vol = vol * 0.6
        high_pct = abs(random.gauss(0, intraday_vol))
        low_pct = abs(random.gauss(0, intraday_vol))
        open_pct = random.gauss(0, intraday_vol * 0.3)

        close = round(price, 2)
        open_price = round(close * (1 + open_pct), 2)
        high = round(max(close, open_price) * (1 + high_pct), 2)
        low = round(min(close, open_price) * (1 - low_pct), 2)

        # Volume with some randomness
        vol_factor = 1 + random.gauss(0, 0.3)
        volume = max(100000, int(avg_vol * abs(vol_factor)))
        delivery_vol = int(volume * random.uniform(0.3, 0.7))

        records.append({
            "symbol": symbol,
            "date": day.replace(hour=15, minute=30, second=0, microsecond=0),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "delivery_volume": delivery_vol,
            "delivery_pct": round(delivery_vol / volume * 100, 2),
            "source": "seed_data",
        })

    return records


async def seed():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    collection = db["stock_prices"]
    total = 0

    for symbol, config in STOCKS.items():
        # Check if data already exists
        count = await collection.count_documents({"symbol": symbol})
        if count > 100:
            print(f"  {symbol}: already has {count} records, skipping")
            continue

        records = generate_ohlcv(symbol, config, days=500)
        if records:
            await collection.insert_many(records)
            total += len(records)
            print(f"  {symbol}: inserted {len(records)} OHLCV records")

    # Create indexes
    await collection.create_index([("symbol", 1), ("date", 1)], unique=True)
    await collection.create_index("symbol")
    await collection.create_index("date")

    print(f"\nTotal: {total} records seeded into stock_prices collection")
    print("Indexes created: symbol+date (unique), symbol, date")

    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
