#!/usr/bin/env python3
"""
StockPulse PostgreSQL Backup Script

Creates timestamped backups of the PostgreSQL database using pg_dump,
with automatic rotation to keep disk usage bounded.

Features:
  - Full database dump via pg_dump (custom format)
  - Fallback to plain SQL dump if custom format fails
  - Automatic rotation: keeps last N backups (default 7)
  - Logs all operations for audit trail

Usage:
    python scripts/backup_postgresql.py                    # Run backup with defaults
    python scripts/backup_postgresql.py --keep 14          # Keep last 14 backups
    python scripts/backup_postgresql.py --output /tmp/bk   # Custom output directory
    python scripts/backup_postgresql.py --check            # Verify backup config only
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_dsn() -> str:
    """Get PostgreSQL DSN from environment."""
    return os.environ.get(
        "TIMESERIES_DSN", "postgresql://localhost:5432/stockpulse_ts"
    )


def parse_dsn(dsn: str) -> dict:
    """Parse PostgreSQL DSN into components."""
    from urllib.parse import urlparse
    parsed = urlparse(dsn)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "dbname": (parsed.path or "/stockpulse_ts").lstrip("/"),
        "user": parsed.username or "",
        "password": parsed.password or "",
    }


def check_pg_dump() -> bool:
    """Check if pg_dump is available."""
    try:
        result = subprocess.run(
            ["pg_dump", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            logger.info("pg_dump available: %s", result.stdout.strip())
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    logger.warning("pg_dump not found in PATH")
    return False


def run_backup(output_dir: Path, dsn: str) -> Path:
    """Run pg_dump and return the backup file path."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    parts = parse_dsn(dsn)

    backup_dir = output_dir / f"pg_backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_file = backup_dir / f"{parts['dbname']}_{timestamp}.dump"

    env = os.environ.copy()
    if parts["password"]:
        env["PGPASSWORD"] = parts["password"]

    cmd = [
        "pg_dump",
        "-h", parts["host"],
        "-p", parts["port"],
        "-Fc",  # Custom format (compressed, supports pg_restore)
        "-f", str(backup_file),
    ]
    if parts["user"]:
        cmd.extend(["-U", parts["user"]])
    cmd.append(parts["dbname"])

    logger.info("Running pg_dump: %s → %s", parts["dbname"], backup_file)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, env=env,
        )
        if result.returncode != 0:
            logger.error("pg_dump failed: %s", result.stderr)
            # Fallback to plain SQL
            backup_file = backup_dir / f"{parts['dbname']}_{timestamp}.sql"
            cmd_plain = [
                "pg_dump",
                "-h", parts["host"],
                "-p", parts["port"],
                "-Fp",  # Plain SQL format
                "-f", str(backup_file),
            ]
            if parts["user"]:
                cmd_plain.extend(["-U", parts["user"]])
            cmd_plain.append(parts["dbname"])

            result = subprocess.run(
                cmd_plain, capture_output=True, text=True, timeout=600, env=env,
            )
            if result.returncode != 0:
                raise RuntimeError(f"pg_dump plain format also failed: {result.stderr}")
            logger.info("Backup created (plain SQL): %s", backup_file)
        else:
            logger.info("Backup created (custom format): %s", backup_file)
    except FileNotFoundError:
        raise RuntimeError("pg_dump not found; install postgresql-client")

    # Write metadata
    meta_file = backup_dir / "metadata.txt"
    size = backup_file.stat().st_size
    meta_file.write_text(
        f"database: {parts['dbname']}\n"
        f"host: {parts['host']}:{parts['port']}\n"
        f"timestamp: {timestamp}\n"
        f"backup_file: {backup_file.name}\n"
        f"size_bytes: {size}\n"
        f"size_mb: {size / (1024 * 1024):.2f}\n"
    )

    logger.info("Backup size: %.2f MB", size / (1024 * 1024))
    return backup_dir


def rotate_backups(output_dir: Path, keep: int):
    """Remove old backups, keeping the most recent `keep` directories."""
    backup_dirs = sorted(
        [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("pg_backup_")],
        key=lambda d: d.name,
    )

    if len(backup_dirs) <= keep:
        logger.info("Rotation: %d backups exist, keeping all (limit: %d)", len(backup_dirs), keep)
        return

    to_remove = backup_dirs[: len(backup_dirs) - keep]
    for d in to_remove:
        logger.info("Removing old backup: %s", d.name)
        try:
            shutil.rmtree(d)
        except Exception as e:
            logger.warning("Failed to remove %s: %s", d, e)

    logger.info("Rotation complete: removed %d, kept %d", len(to_remove), keep)


def check_config():
    """Verify backup configuration without running backup."""
    dsn = get_dsn()
    parts = parse_dsn(dsn)
    logger.info("PostgreSQL host: %s:%s", parts["host"], parts["port"])
    logger.info("Database: %s", parts["dbname"])
    logger.info("User: %s", parts["user"] or "(default)")

    has_pg_dump = check_pg_dump()

    # Try connecting
    try:
        env = os.environ.copy()
        if parts["password"]:
            env["PGPASSWORD"] = parts["password"]
        cmd = ["pg_isready", "-h", parts["host"], "-p", parts["port"]]
        if parts["user"]:
            cmd.extend(["-U", parts["user"]])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=env)
        if result.returncode == 0:
            logger.info("PostgreSQL is accepting connections")
        else:
            logger.warning("PostgreSQL not ready: %s", result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("pg_isready not available; skipping connectivity check")

    if has_pg_dump:
        logger.info("Configuration OK — ready to backup")
    else:
        logger.warning("pg_dump not available — install postgresql-client")


def main():
    parser = argparse.ArgumentParser(description="StockPulse PostgreSQL Backup")
    parser.add_argument(
        "--output", type=str,
        default=str(Path(__file__).parent.parent / "backups" / "postgresql"),
        help="Output directory for backups",
    )
    parser.add_argument("--keep", type=int, default=7, help="Number of backups to keep")
    parser.add_argument("--check", action="store_true", help="Verify config only")
    args = parser.parse_args()

    if args.check:
        check_config()
        return

    dsn = get_dsn()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not check_pg_dump():
        logger.error("pg_dump is required but not found. Install postgresql-client.")
        sys.exit(1)

    try:
        backup_path = run_backup(output_dir, dsn)
        logger.info("Backup completed: %s", backup_path)
    except Exception as e:
        logger.error("Backup failed: %s", e)
        sys.exit(1)

    rotate_backups(output_dir, args.keep)
    logger.info("Done.")


if __name__ == "__main__":
    main()
