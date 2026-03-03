#!/usr/bin/env python3
"""
StockPulse MongoDB Backup Script

Creates timestamped backups of the MongoDB database using mongodump,
with automatic rotation to keep disk usage bounded.

Features:
  - Full database dump via mongodump (BSON format)
  - Fallback to Python-based JSON export if mongodump unavailable
  - Automatic rotation: keeps last N backups (default 7)
  - Logs all operations for audit trail

Usage:
    python scripts/backup_mongodb.py                    # Run backup with defaults
    python scripts/backup_mongodb.py --keep 14          # Keep last 14 backups
    python scripts/backup_mongodb.py --output /tmp/bk   # Custom output directory
    python scripts/backup_mongodb.py --check             # Verify backup config only
"""

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mongodb_backup")

# Collections to back up (all 10 MongoDB collections)
COLLECTIONS = [
    "watchlist",
    "portfolio",
    "alerts",
    "stock_data",
    "price_history",
    "extraction_log",
    "quality_reports",
    "pipeline_jobs",
    "news_articles",
    "backtest_results",
]


def _mongodump_available() -> bool:
    """Check if mongodump CLI tool is installed."""
    try:
        result = subprocess.run(
            ["mongodump", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def backup_with_mongodump(
    mongo_url: str,
    db_name: str,
    output_dir: Path,
) -> bool:
    """Create backup using mongodump (preferred method - BSON format)."""
    logger.info(f"Running mongodump -> {output_dir}")

    cmd = [
        "mongodump",
        f"--uri={mongo_url}",
        f"--db={db_name}",
        f"--out={output_dir}",
        "--gzip",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            logger.info("mongodump completed successfully")
            return True
        else:
            logger.error(f"mongodump failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("mongodump timed out after 5 minutes")
        return False
    except Exception as e:
        logger.error(f"mongodump error: {e}")
        return False


async def backup_with_python(
    mongo_url: str,
    db_name: str,
    output_dir: Path,
) -> bool:
    """Fallback: export collections as JSON using Motor."""
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError:
        logger.error("motor not installed. Cannot perform Python-based backup.")
        return False

    logger.info(f"Running Python JSON export -> {output_dir}")

    try:
        client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
        await client.admin.command("ping")
        db = client[db_name]

        db_output = output_dir / db_name
        db_output.mkdir(parents=True, exist_ok=True)

        total_docs = 0
        for coll_name in COLLECTIONS:
            try:
                collection = db[coll_name]
                count = await collection.count_documents({})

                if count == 0:
                    logger.info(f"  {coll_name}: 0 documents (skipped)")
                    continue

                docs = await collection.find({}).to_list(length=None)

                # Convert ObjectId and datetime to string for JSON
                for doc in docs:
                    if "_id" in doc:
                        doc["_id"] = str(doc["_id"])
                    for key, val in doc.items():
                        if isinstance(val, datetime):
                            doc[key] = val.isoformat()

                out_file = db_output / f"{coll_name}.json"
                with open(out_file, "w") as f:
                    json.dump(docs, f, indent=2, default=str)

                total_docs += count
                logger.info(f"  {coll_name}: {count} documents exported")

            except Exception as e:
                logger.error(f"  Error exporting {coll_name}: {e}")

        # Write backup metadata
        metadata = {
            "backup_type": "python_json",
            "database": db_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "collections": COLLECTIONS,
            "total_documents": total_docs,
        }
        with open(output_dir / "backup_metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        client.close()
        logger.info(f"Python backup complete: {total_docs} total documents")
        return True

    except Exception as e:
        logger.error(f"Python backup failed: {e}")
        return False


def rotate_backups(backup_root: Path, keep: int) -> int:
    """Delete old backups, keeping only the most recent ``keep`` copies.

    Returns the number of backups deleted.
    """
    if not backup_root.exists():
        return 0

    # List all backup directories (named like mongo_backup_YYYYMMDD_HHMMSS)
    backups = sorted(
        [
            d
            for d in backup_root.iterdir()
            if d.is_dir() and d.name.startswith("mongo_backup_")
        ],
        key=lambda d: d.name,
        reverse=True,
    )

    to_delete = backups[keep:]
    deleted = 0
    for old_backup in to_delete:
        try:
            shutil.rmtree(old_backup)
            logger.info(f"  Deleted old backup: {old_backup.name}")
            deleted += 1
        except Exception as e:
            logger.warning(f"  Failed to delete {old_backup.name}: {e}")

    return deleted


async def run_backup(
    output_root: Path,
    keep: int = 7,
) -> bool:
    """Run a full MongoDB backup with rotation."""
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get(
        "MONGO_DB_NAME", os.environ.get("DB_NAME", "stockpulse")
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = output_root / f"mongo_backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 50)
    logger.info(f"StockPulse MongoDB Backup - {timestamp}")
    logger.info(f"  Database: {db_name}")
    logger.info(f"  Output:   {backup_dir}")
    logger.info(f"  Rotation: keep last {keep} backups")
    logger.info("=" * 50)

    # Prefer mongodump, fall back to Python export
    if _mongodump_available():
        success = backup_with_mongodump(mongo_url, db_name, backup_dir)
    else:
        logger.info("mongodump not found, using Python JSON export fallback")
        success = await backup_with_python(mongo_url, db_name, backup_dir)

    if success:
        # Rotate old backups
        deleted = rotate_backups(output_root, keep)
        if deleted:
            logger.info(f"Rotation: deleted {deleted} old backup(s)")

        # Calculate backup size
        total_size = sum(f.stat().st_size for f in backup_dir.rglob("*") if f.is_file())
        size_mb = total_size / (1024 * 1024)
        logger.info(f"Backup complete: {size_mb:.2f} MB")
    else:
        # Cleanup failed backup directory
        try:
            shutil.rmtree(backup_dir)
        except Exception:
            pass
        logger.error("Backup FAILED")

    return success


async def main() -> int:
    parser = argparse.ArgumentParser(description="StockPulse MongoDB Backup")
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT_DIR / os.environ.get("BACKUPS_DIR", "./backups")),
        help="Backup output directory",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=7,
        help="Number of recent backups to keep (default: 7)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify backup configuration only (no actual backup)",
    )
    args = parser.parse_args()

    output_root = Path(args.output)

    if args.check:
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get(
            "MONGO_DB_NAME", os.environ.get("DB_NAME", "stockpulse")
        )
        logger.info("Backup configuration check:")
        logger.info(f"  MongoDB URL:      {mongo_url}")
        logger.info(f"  Database:         {db_name}")
        logger.info(f"  Output directory: {output_root}")
        logger.info(f"  Keep backups:     {args.keep}")
        logger.info(f"  mongodump:        {'available' if _mongodump_available() else 'not found (will use Python fallback)'}")

        # List existing backups
        if output_root.exists():
            backups = sorted(
                [d for d in output_root.iterdir() if d.is_dir() and d.name.startswith("mongo_backup_")],
                reverse=True,
            )
            logger.info(f"  Existing backups: {len(backups)}")
            for b in backups[:5]:
                size = sum(f.stat().st_size for f in b.rglob("*") if f.is_file())
                logger.info(f"    {b.name} ({size / 1024 / 1024:.2f} MB)")
        return 0

    success = await run_backup(output_root, keep=args.keep)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
