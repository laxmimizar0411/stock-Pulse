"""
PostgreSQL Control & Monitoring Service for StockPulse.

Provides:
- PostgreSQL status checks (running/stopped)
- Start/stop control via system commands
- Resource monitoring: CPU, RAM, storage, active connections
- Connection pool statistics
"""

import asyncio
import logging
import os
import platform
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PgControlService:
    """
    Controls and monitors a local PostgreSQL instance.

    Designed for local development: uses system commands to start/stop
    PostgreSQL and reads /proc or pg_stat for resource metrics.
    """

    def __init__(self, dsn: str = "postgresql://localhost:5432/stockpulse_ts"):
        self._dsn = dsn
        self._pool = None  # set externally from the TimeSeriesStore

    def set_pool(self, pool):
        """Inject the asyncpg pool from TimeSeriesStore."""
        self._pool = pool

    # ------------------------------------------------------------------
    #  Status
    # ------------------------------------------------------------------

    async def get_status(self) -> Dict[str, Any]:
        """Check if PostgreSQL is running and reachable."""
        result = {
            "running": False,
            "reachable": False,
            "version": None,
            "uptime_seconds": None,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        # Check via process list
        try:
            proc = await asyncio.create_subprocess_exec(
                "pgrep", "-x", "postgres",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            result["running"] = proc.returncode == 0
        except Exception:
            # Fallback: try pg_isready
            try:
                proc = await asyncio.create_subprocess_exec(
                    "pg_isready", "-q",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                result["running"] = proc.returncode == 0
            except Exception:
                pass

        # Check reachability via pool or direct connection
        if self._pool:
            try:
                async with self._pool.acquire() as conn:
                    version = await conn.fetchval("SELECT version()")
                    result["reachable"] = True
                    result["version"] = version

                    uptime = await conn.fetchval(
                        "SELECT EXTRACT(EPOCH FROM (now() - pg_postmaster_start_time()))::int "
                        "FROM pg_stat_activity LIMIT 1"
                    )
                    result["uptime_seconds"] = uptime
            except Exception as e:
                logger.debug(f"Pool query failed: {e}")
        else:
            try:
                import asyncpg
                conn = await asyncio.wait_for(
                    asyncpg.connect(self._dsn), timeout=5
                )
                version = await conn.fetchval("SELECT version()")
                result["reachable"] = True
                result["version"] = version
                await conn.close()
            except Exception:
                pass

        return result

    # ------------------------------------------------------------------
    #  Start / Stop
    # ------------------------------------------------------------------

    async def start_postgres(self) -> Dict[str, Any]:
        """Start the local PostgreSQL service."""
        commands = [
            ["sudo", "pg_ctlcluster", "14", "main", "start"],
            ["sudo", "pg_ctlcluster", "16", "main", "start"],
            ["sudo", "pg_ctlcluster", "15", "main", "start"],
            ["sudo", "service", "postgresql", "start"],
            ["pg_ctl", "-D", "/var/lib/postgresql/data", "start"],
        ]
        return await self._run_control_commands(commands, "start")

    async def stop_postgres(self) -> Dict[str, Any]:
        """Stop the local PostgreSQL service."""
        commands = [
            ["sudo", "pg_ctlcluster", "14", "main", "stop"],
            ["sudo", "pg_ctlcluster", "16", "main", "stop"],
            ["sudo", "pg_ctlcluster", "15", "main", "stop"],
            ["sudo", "service", "postgresql", "stop"],
            ["pg_ctl", "-D", "/var/lib/postgresql/data", "stop", "-m", "fast"],
        ]
        return await self._run_control_commands(commands, "stop")

    async def _run_control_commands(
        self, commands: list, action: str
    ) -> Dict[str, Any]:
        """Try multiple commands until one succeeds."""
        last_error = ""
        for cmd in commands:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=30
                )
                if proc.returncode == 0:
                    return {
                        "success": True,
                        "action": action,
                        "message": f"PostgreSQL {action} successful",
                        "output": stdout.decode("utf-8", errors="replace").strip(),
                    }
                last_error = stderr.decode("utf-8", errors="replace").strip()
            except FileNotFoundError:
                continue
            except asyncio.TimeoutError:
                last_error = f"Command timed out: {' '.join(cmd)}"
            except Exception as e:
                last_error = str(e)

        return {
            "success": False,
            "action": action,
            "message": f"PostgreSQL {action} failed. You may need to {action} it manually.",
            "error": last_error,
            "hint": f"Try: sudo service postgresql {action}",
        }

    # ------------------------------------------------------------------
    #  Resource Monitoring
    # ------------------------------------------------------------------

    async def get_resource_usage(self) -> Dict[str, Any]:
        """Get CPU, RAM, storage, and connection metrics for PostgreSQL."""
        resources: Dict[str, Any] = {
            "cpu": await self._get_cpu_usage(),
            "memory": await self._get_memory_usage(),
            "storage": await self._get_storage_usage(),
            "connections": await self._get_connection_info(),
            "pool": self._get_pool_stats(),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        return resources

    async def _get_cpu_usage(self) -> Dict[str, Any]:
        """Get CPU usage of PostgreSQL processes."""
        result = {"percentage": 0.0, "process_count": 0, "available": False}
        try:
            proc = await asyncio.create_subprocess_exec(
                "ps", "aux",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            lines = stdout.decode("utf-8", errors="replace").splitlines()

            total_cpu = 0.0
            count = 0
            for line in lines:
                if "postgres" in line.lower() and "grep" not in line.lower():
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            total_cpu += float(parts[2])
                            count += 1
                        except ValueError:
                            pass

            result["percentage"] = round(total_cpu, 2)
            result["process_count"] = count
            result["available"] = True
        except Exception as e:
            logger.debug(f"CPU usage check failed: {e}")

        return result

    async def _get_memory_usage(self) -> Dict[str, Any]:
        """Get RAM usage of PostgreSQL processes."""
        result = {
            "rss_mb": 0.0,
            "percentage": 0.0,
            "shared_buffers_mb": None,
            "available": False,
        }
        try:
            proc = await asyncio.create_subprocess_exec(
                "ps", "aux",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            lines = stdout.decode("utf-8", errors="replace").splitlines()

            total_mem_pct = 0.0
            total_rss = 0
            for line in lines:
                if "postgres" in line.lower() and "grep" not in line.lower():
                    parts = line.split()
                    if len(parts) >= 6:
                        try:
                            total_mem_pct += float(parts[3])
                            total_rss += int(parts[5])
                        except (ValueError, IndexError):
                            pass

            result["rss_mb"] = round(total_rss / 1024, 2)
            result["percentage"] = round(total_mem_pct, 2)
            result["available"] = True
        except Exception as e:
            logger.debug(f"Memory usage check failed: {e}")

        # Get shared_buffers from PostgreSQL if pool available
        if self._pool:
            try:
                async with self._pool.acquire() as conn:
                    val = await conn.fetchval("SHOW shared_buffers")
                    result["shared_buffers_mb"] = val
            except Exception:
                pass

        return result

    async def _get_storage_usage(self) -> Dict[str, Any]:
        """Get storage usage of PostgreSQL databases."""
        result = {
            "database_size": None,
            "database_size_bytes": 0,
            "tables": {},
            "data_directory": None,
            "disk_total_gb": 0,
            "disk_used_gb": 0,
            "disk_free_gb": 0,
            "disk_usage_pct": 0,
            "available": False,
        }

        # Get disk usage for root filesystem
        try:
            total, used, free = shutil.disk_usage("/")
            result["disk_total_gb"] = round(total / (1024**3), 2)
            result["disk_used_gb"] = round(used / (1024**3), 2)
            result["disk_free_gb"] = round(free / (1024**3), 2)
            result["disk_usage_pct"] = round(used / total * 100, 2) if total else 0
        except Exception:
            pass

        if not self._pool:
            return result

        try:
            async with self._pool.acquire() as conn:
                # Total database size
                db_size = await conn.fetchval(
                    "SELECT pg_size_pretty(pg_database_size(current_database()))"
                )
                db_size_bytes = await conn.fetchval(
                    "SELECT pg_database_size(current_database())"
                )
                result["database_size"] = db_size
                result["database_size_bytes"] = db_size_bytes

                # Per-table sizes
                rows = await conn.fetch("""
                    SELECT
                        relname AS table_name,
                        pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
                        pg_total_relation_size(relid) AS total_bytes,
                        pg_size_pretty(pg_relation_size(relid)) AS data_size,
                        pg_size_pretty(pg_indexes_size(relid)) AS index_size,
                        n_live_tup AS row_count
                    FROM pg_stat_user_tables
                    ORDER BY pg_total_relation_size(relid) DESC
                """)
                for row in rows:
                    result["tables"][row["table_name"]] = {
                        "total_size": row["total_size"],
                        "total_bytes": row["total_bytes"],
                        "data_size": row["data_size"],
                        "index_size": row["index_size"],
                        "row_count": row["row_count"],
                    }

                # Data directory
                data_dir = await conn.fetchval("SHOW data_directory")
                result["data_directory"] = data_dir
                result["available"] = True
        except Exception as e:
            logger.debug(f"Storage query failed: {e}")

        return result

    async def _get_connection_info(self) -> Dict[str, Any]:
        """Get active connections and related metrics."""
        result = {
            "active": 0,
            "idle": 0,
            "idle_in_transaction": 0,
            "total": 0,
            "max_connections": 0,
            "connections_by_state": {},
            "connections_by_database": {},
            "available": False,
        }

        if not self._pool:
            return result

        try:
            async with self._pool.acquire() as conn:
                # Connection states
                rows = await conn.fetch("""
                    SELECT state, count(*) as cnt
                    FROM pg_stat_activity
                    WHERE backend_type = 'client backend'
                    GROUP BY state
                """)
                for row in rows:
                    state = row["state"] or "unknown"
                    result["connections_by_state"][state] = row["cnt"]
                    if state == "active":
                        result["active"] = row["cnt"]
                    elif state == "idle":
                        result["idle"] = row["cnt"]
                    elif state == "idle in transaction":
                        result["idle_in_transaction"] = row["cnt"]

                result["total"] = sum(result["connections_by_state"].values())

                # By database
                db_rows = await conn.fetch("""
                    SELECT datname, count(*) as cnt
                    FROM pg_stat_activity
                    WHERE backend_type = 'client backend'
                    GROUP BY datname
                """)
                for row in db_rows:
                    result["connections_by_database"][row["datname"]] = row["cnt"]

                # Max connections
                max_conn = await conn.fetchval("SHOW max_connections")
                result["max_connections"] = int(max_conn)
                result["available"] = True
        except Exception as e:
            logger.debug(f"Connection info query failed: {e}")

        return result

    def _get_pool_stats(self) -> Dict[str, Any]:
        """Get asyncpg connection pool statistics."""
        if not self._pool:
            return {"available": False}

        try:
            return {
                "size": self._pool.get_size(),
                "min_size": self._pool.get_min_size(),
                "max_size": self._pool.get_max_size(),
                "idle": self._pool.get_idle_size(),
                "available": True,
            }
        except Exception:
            return {"available": False}

    # ------------------------------------------------------------------
    #  Comprehensive health check
    # ------------------------------------------------------------------

    async def get_health(self) -> Dict[str, Any]:
        """Combined status + resource usage."""
        status = await self.get_status()
        resources = await self.get_resource_usage() if status["reachable"] else {}
        return {
            "status": status,
            "resources": resources,
        }
