#!/usr/bin/env python3
"""
StockPulse PostgreSQL Backup Script

Creates timestamped backups of the PostgreSQL time-series database using pg_dump,
with automatic rotation to keep disk usage bounded.

Features:
  - Full logical backup via pg_dump (custom or plain format)
  - Optional compression (gzip) for smaller footprint
  - Automatic rotation: keeps last N backups (default 7)
  - Logs all operations for audit trail

Usage:
    python scripts/backup_postgres.py                       # Run backup with defaults
    python scripts/backup_postgres.py --keep 14             # Keep last 14 backups
    python scripts/backup_postgres.py --output /tmp/pg_bk   # Custom output directory
    python scripts/backup_postgres.py --no-compress         # Disable gzip compression
    python scripts/backup_postgres.py --check               # Verify backup config only
"""

import argparse
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("postgres_backup")


def _pg_dump_available() -> bool:
    """Check if pg_dump CLI tool is installed."""
    try:
        result = subprocess.run(
            ["pg_dump", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def backup_with_pg_dump(
    dsn: str,
    output_file: Path,
    compress: bool = True,
) -> bool:
    """Create backup using pg_dump."""
    logger.info(f"Running pg_dump -> {output_file}")

    # If DSN is of the form postgresql://user:pass@host:port/db, pass via --dbname
    cmd = [
        "pg_dump",
        f"--dbname={dsn}",
        "--format=custom",  # compressed, suitable for pg_restore
    ]

    try:
        with open(output_file, "wb") as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                timeout=600,  # 10 minutes
            )
        if result.returncode != 0:
            logger.error("pg_dump failed: %s", result.stderr.decode("utf-8", errors="ignore"))
            return False
    except subprocess.TimeoutExpired:
        logger.error("pg_dump timed out after 10 minutes")
        return False
    except Exception as e:
        logger.error("pg_dump error: %s", e)
        return False

    # Optional gzip compression for the resulting file
    if compress:
        try:
            import gzip

            compressed_file = output_file.with_suffix(output_file.suffix + ".gz")
            logger.info("Compressing backup -> %s", compressed_file)
            with open(output_file, "rb") as f_in, gzip.open(compressed_file, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            output_file.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Compression failed (backup remains uncompressed): %s", e)

    return True


def rotate_backups(backup_root: Path, keep: int) -> int:
    """Delete old backups, keeping only the most recent ``keep`` copies.

    Returns the number of backups deleted.
    """
    if not backup_root.exists():
        return 0

    backups = sorted(
        [
            f
            for f in backup_root.iterdir()
            if f.is_file() and f.name.startswith("postgres_backup_")
        ],
        key=lambda f: f.name,
        reverse=True,
    )

    to_delete = backups[keep:]
    deleted = 0
    for old_backup in to_delete:
        try:
            old_backup.unlink()
            logger.info("  Deleted old backup: %s", old_backup.name)
            deleted += 1
        except Exception as e:
            logger.warning("  Failed to delete %s: %s", old_backup.name, e)

    return deleted


def run_backup(
    output_root: Path,
    keep: int = 7,
    compress: bool = True,
) -> bool:
    """Run a full PostgreSQL backup with rotation."""
    dsn = os.environ.get("TIMESERIES_DSN", "postgresql://localhost:5432/stockpulse_ts")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = output_root
    backup_root.mkdir(parents=True, exist_ok=True)

    backup_file = backup_root / f"postgres_backup_{timestamp}.dump"

    logger.info("=" * 50)
    logger.info("StockPulse PostgreSQL Backup - %s", timestamp)
    logger.info("  DSN:    %s", dsn)
    logger.info("  Output: %s", backup_file)
    logger.info("  Rotation: keep last %d backups", keep)
    logger.info("=" * 50)

    if not _pg_dump_available():
        logger.error("pg_dump not found in PATH. Install PostgreSQL client tools.")
        return False

    success = backup_with_pg_dump(dsn, backup_file, compress=compress)

    if success:
        deleted = rotate_backups(backup_root, keep)
        if deleted:
            logger.info("Rotation: deleted %d old backup(s)", deleted)

        if backup_file.exists():
            total_size = backup_file.stat().st_size
        else:
            # If compressed, look for .gz
            gzip_file = backup_file.with_suffix(backup_file.suffix + ".gz")
            total_size = gzip_file.stat().st_size if gzip_file.exists() else 0

        size_mb = total_size / (1024 * 1024) if total_size else 0.0
        logger.info("Backup complete: %.2f MB", size_mb)
    else:
        logger.error("PostgreSQL backup FAILED")

    return success


def main() -> None:
    parser = argparse.ArgumentParser(description="StockPulse PostgreSQL Backup Script")
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT_DIR / "backups" / "postgres"),
        help="Output directory for backups (default: ./backups/postgres)",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=7,
        help="Number of backups to keep (default: 7)",
    )
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="Disable gzip compression of the pg_dump output",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only verify configuration (pg_dump availability, output dir) without running a backup",
    )

    args = parser.parse_args()

    output_root = Path(args.output)
    keep = max(args.keep, 1)
    compress = not args.no_compress

    logger.info("Checking pg_dump availability...")
    if not _pg_dump_available():
        logger.error("pg_dump is not available. Install PostgreSQL client tools and re-run.")
        raise SystemExit(1)

    logger.info("Backup output directory: %s", output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    if args.check:
        logger.info("Configuration check successful. No backup executed (--check).")
        return

    success = run_backup(output_root=output_root, keep=keep, compress=compress)
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

