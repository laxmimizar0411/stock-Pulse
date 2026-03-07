"""
StockPulse Pipeline Integration Test

Tests the full data pipeline: Groww API -> Redis cache -> PostgreSQL -> MongoDB

Usage:
    python test_pipeline.py                # Full pipeline test
    python test_pipeline.py --db-only      # Test database connections only
    python test_pipeline.py --api-only     # Test Groww API only (no DB)
"""
import asyncio
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Ensure imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(__file__).parent / ".env")


async def test_databases():
    """Test all database connections."""
    results = {}
    print("\n" + "=" * 50)
    print("DATABASE CONNECTION TESTS")
    print("=" * 50)

    # --- MongoDB ---
    print("\n[1/3] Testing MongoDB...")
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.getenv("MONGO_DB_NAME", "stockpulse")
        client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=3000)
        await client.admin.command("ping")
        collections = await client[db_name].list_collection_names()
        print(f"  OK  MongoDB connected. DB: {db_name}, Collections: {len(collections)}")
        for c in sorted(collections):
            count = await client[db_name][c].count_documents({})
            print(f"       - {c}: {count} documents")
        results["mongodb"] = True
        client.close()
    except Exception as e:
        print(f"  FAIL MongoDB: {e}")
        results["mongodb"] = False

    # --- Redis ---
    print("\n[2/3] Testing Redis...")
    try:
        import redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        r = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=3)
        r.ping()
        info = r.info("memory")
        print(f"  OK  Redis connected. Version: {info.get('redis_version')}, "
              f"Memory: {info.get('used_memory_human')}, Keys: {r.dbsize()}")
        results["redis"] = True
        r.close()
    except Exception as e:
        print(f"  WARN Redis not available: {e}")
        print("       (Redis is optional — app uses in-memory fallback)")
        results["redis"] = False

    # --- PostgreSQL ---
    print("\n[3/3] Testing PostgreSQL...")
    try:
        import asyncpg
        dsn = os.getenv("TIMESERIES_DSN", "postgresql://localhost:5432/stockpulse_ts")
        conn = await asyncpg.connect(dsn)
        version = await conn.fetchval("SELECT version()")
        print(f"  OK  PostgreSQL connected: {version[:60]}...")

        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        expected = [
            "prices_daily", "derived_metrics_daily", "technical_indicators",
            "ml_features_daily", "risk_metrics", "valuation_daily",
            "fundamentals_quarterly", "shareholding_quarterly",
            "corporate_actions", "macro_indicators", "derivatives_daily",
            "intraday_metrics", "weekly_metrics", "schema_migrations",
        ]
        table_names = [t["table_name"] for t in tables]
        for name in expected:
            if name in table_names:
                rows = await conn.fetchval(f"SELECT COUNT(*) FROM {name}")
                print(f"       - {name}: {rows} rows")
            else:
                print(f"       - {name}: MISSING (run: python setup_databases.py)")
        await conn.close()
        results["postgresql"] = True
    except Exception as e:
        print(f"  FAIL PostgreSQL: {e}")
        print("       (Run: python setup_databases.py --postgres)")
        results["postgresql"] = False

    return results


async def test_groww_api():
    """Test Groww API authentication and data extraction."""
    print("\n" + "=" * 50)
    print("GROWW API PIPELINE TEST")
    print("=" * 50)

    grow_totp_token = os.getenv("GROW_TOTP_TOKEN")
    grow_secret_key = os.getenv("GROW_SECRET_KEY")

    if not grow_totp_token or not grow_secret_key:
        print("  SKIP GROW_TOTP_TOKEN or GROW_SECRET_KEY not set in .env")
        return False

    from data_extraction.extractors.grow_extractor import GrowwAPIExtractor

    print("\n[1/3] Authenticating with Groww API (TOTP)...")
    extractor = GrowwAPIExtractor(totp_token=grow_totp_token, secret_key=grow_secret_key)
    try:
        await extractor.initialize()
        print(f"  OK  Authenticated. Access token obtained.")
    except Exception as e:
        print(f"  FAIL Authentication failed: {e}")
        await extractor.close()
        return False

    print("\n[2/3] Fetching single quote (RELIANCE)...")
    try:
        result = await extractor.get_stock_quote("RELIANCE")
        if result.status.value == "success":
            data = result.data
            print(f"  OK  RELIANCE quote received:")
            print(f"       Price: {data.get('current_price')}")
            print(f"       Open: {data.get('open')}, High: {data.get('high')}, "
                  f"Low: {data.get('low')}, Close: {data.get('close')}")
            print(f"       Volume: {data.get('volume')}")
            print(f"       Change: {data.get('price_change')} ({data.get('price_change_percent')}%)")
        else:
            print(f"  FAIL Quote failed: {result.error}")
    except Exception as e:
        print(f"  FAIL Quote exception: {e}")

    print("\n[3/3] Fetching bulk quotes (5 symbols)...")
    test_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    try:
        results = await extractor.extract_bulk_quotes(test_symbols)
        success_count = sum(1 for r in results.values() if r.status.value == "success")
        fail_count = sum(1 for r in results.values() if r.status.value == "failed")
        print(f"  Results: {success_count} success, {fail_count} failed out of {len(test_symbols)}")
        for sym, res in results.items():
            if res.status.value == "success":
                print(f"       OK  {sym}: Rs {res.data.get('current_price', 'N/A')}")
            else:
                print(f"       FAIL {sym}: {res.error}")
    except Exception as e:
        print(f"  FAIL Bulk extraction exception: {e}")

    print(f"\n  API Metrics: {json.dumps(extractor.get_metrics(), indent=2)}")
    await extractor.close()
    return True


async def test_full_pipeline():
    """Test the full pipeline with database persistence."""
    print("\n" + "=" * 50)
    print("FULL PIPELINE TEST (API + DB)")
    print("=" * 50)

    grow_totp_token = os.getenv("GROW_TOTP_TOKEN")
    grow_secret_key = os.getenv("GROW_SECRET_KEY")

    if not grow_totp_token or not grow_secret_key:
        print("  SKIP GROW_TOTP_TOKEN or GROW_SECRET_KEY not set")
        return

    from motor.motor_asyncio import AsyncIOMotorClient
    from services.pipeline_service import DataPipelineService
    from data_extraction.extractors.grow_extractor import GrowwAPIExtractor

    # Connect MongoDB
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB_NAME", "stockpulse")
    try:
        client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=3000)
        await client.admin.command("ping")
        db = client[db_name]
    except Exception as e:
        print(f"  FAIL MongoDB connection failed: {e}")
        return

    # Connect PostgreSQL (optional)
    ts_store = None
    try:
        from services.timeseries_store import TimeSeriesStore
        dsn = os.getenv("TIMESERIES_DSN", "postgresql://localhost:5432/stockpulse_ts")
        ts_store = TimeSeriesStore(dsn=dsn)
        await ts_store.initialize()
        print("  PostgreSQL bridge: ACTIVE")
    except Exception as e:
        print(f"  PostgreSQL bridge: DISABLED ({e})")

    # Initialize pipeline
    extractor = GrowwAPIExtractor(totp_token=grow_totp_token, secret_key=grow_secret_key, db=db)
    pipeline = DataPipelineService(db=db, grow_extractor=extractor, ts_store=ts_store)

    print("\n  Initializing pipeline (this may start the scheduler)...")
    pipeline.AUTO_START_SCHEDULER = False  # Don't auto-start for testing
    await pipeline.initialize()

    print(f"  Pipeline status: {pipeline.status.value}")
    print(f"  Tracked symbols: {len(pipeline.DEFAULT_SYMBOLS)}")

    # Run a small test extraction
    test_symbols = ["RELIANCE", "TCS", "INFY"]
    print(f"\n  Running extraction for {test_symbols}...")
    job = await pipeline.run_extraction(symbols=test_symbols)

    print(f"\n  Job result:")
    print(f"    Status: {job.status.value}")
    print(f"    Successful: {job.successful_symbols}/{job.total_symbols}")
    print(f"    Failed: {job.failed_symbols}")
    if job.errors:
        for err in job.errors[:5]:
            print(f"    Error: {err}")

    # Check if data reached PostgreSQL
    if ts_store:
        try:
            stats = await ts_store.get_stats()
            print(f"\n  PostgreSQL stats after extraction:")
            for table, info in stats.items():
                if table != "pool":
                    print(f"    {table}: {info.get('rows', 0)} rows")
        except Exception as e:
            print(f"  PostgreSQL stats error: {e}")

    # Cleanup
    await extractor.close()
    if ts_store:
        await ts_store.close()
    client.close()


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--all"

    if mode in ("--all", "--db-only"):
        db_results = await test_databases()

    if mode in ("--all", "--api-only"):
        await test_groww_api()

    if mode == "--all":
        await test_full_pipeline()

    print("\n" + "=" * 50)
    print("TEST COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
