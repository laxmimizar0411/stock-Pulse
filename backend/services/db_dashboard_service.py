"""
Database Dashboard Service for StockPulse.

Provides database introspection, monitoring, audit logging, and settings
management for the Database Dashboard UI. All database access is via this
service - the frontend never connects directly.
"""

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------

# MongoDB collections with metadata
MONGO_COLLECTION_META = {
    "watchlist": {
        "description": "User watchlist of stocks to monitor",
        "sources": ["Watchlist API (user actions)"],
        "consumers": ["Watchlist page", "Dashboard", "Alerts"],
        "ttl": None,
    },
    "portfolio": {
        "description": "User portfolio holdings and transactions",
        "sources": ["Portfolio API (user actions)"],
        "consumers": ["Portfolio page", "Dashboard", "Reports"],
        "ttl": None,
    },
    "alerts": {
        "description": "Price alerts and notification rules",
        "sources": ["Alerts API (user actions)"],
        "consumers": ["Alerts page", "Alert checker background task"],
        "ttl": None,
    },
    "stock_data": {
        "description": "Comprehensive stock data from extraction pipeline",
        "sources": ["Extraction Pipeline", "Groww API", "Yahoo Finance"],
        "consumers": ["Stock Analyzer", "Screener", "Dashboard"],
        "ttl": None,
    },
    "price_history": {
        "description": "Historical price data (MongoDB-side complement to PostgreSQL)",
        "sources": ["Extraction Pipeline", "NSE Bhavcopy"],
        "consumers": ["Charts", "Backtest engine"],
        "ttl": None,
    },
    "extraction_log": {
        "description": "Log of individual extraction attempts per source/symbol",
        "sources": ["Extraction Pipeline"],
        "consumers": ["Data Pipeline page", "Database Dashboard"],
        "ttl": "90 days",
    },
    "quality_reports": {
        "description": "Data quality assessment reports per stock",
        "sources": ["Quality assessment engine"],
        "consumers": ["Data Pipeline page", "Stock Analyzer"],
        "ttl": "90 days",
    },
    "pipeline_jobs": {
        "description": "Pipeline execution job records",
        "sources": ["Data Pipeline service"],
        "consumers": ["Data Pipeline page", "Database Dashboard"],
        "ttl": "90 days",
    },
    "news_articles": {
        "description": "News articles with sentiment analysis",
        "sources": ["News aggregator", "Manual entry"],
        "consumers": ["News Hub", "Dashboard", "Stock Analyzer"],
        "ttl": None,
    },
    "backtest_results": {
        "description": "Saved backtesting strategy results",
        "sources": ["Backtest engine"],
        "consumers": ["Backtest page", "Reports"],
        "ttl": None,
    },
}

# PostgreSQL tables with metadata
PG_TABLE_META = {
    "prices_daily": {
        "description": "Daily OHLCV prices with delivery data",
        "sources": ["NSE Bhavcopy", "Extraction Pipeline"],
        "consumers": ["Charts", "Technical analysis", "Screener", "Backtest"],
        "primary_key": "(symbol, date)",
    },
    "technical_indicators": {
        "description": "Daily technical indicators computed from OHLCV",
        "sources": ["Technical computation engine (from prices_daily)"],
        "consumers": ["Stock Analyzer", "Screener", "Alerts"],
        "primary_key": "(symbol, date)",
    },
    "fundamentals_quarterly": {
        "description": "Quarterly income statement, balance sheet, cash flow",
        "sources": ["Screener.in", "Extraction Pipeline"],
        "consumers": ["Stock Analyzer", "Screener", "Reports"],
        "primary_key": "(symbol, period_end, period_type)",
    },
    "shareholding_quarterly": {
        "description": "Quarterly shareholding pattern (promoter, FII, DII)",
        "sources": ["Screener.in", "NSE filings"],
        "consumers": ["Stock Analyzer", "Screener"],
        "primary_key": "(symbol, quarter_end)",
    },
}

# Redis prefixes considered safe for value preview
REDIS_SAFE_PREFIXES = [
    "price:", "analysis:", "stock_list", "market:overview",
    "pipeline:", "news:", "ws:price:", "top_gainers", "top_losers",
    "alert_queue", "stock:",
]

# Collections that allow single-document delete from dashboard
DELETABLE_COLLECTIONS = {
    "watchlist", "portfolio", "alerts", "news_articles",
    "backtest_results", "extraction_log", "pipeline_jobs",
    "quality_reports",
}

# Default dashboard settings
DEFAULT_SETTINGS = {
    "safe_mode": True,
    "auto_refresh_interval": 30,
    "default_page_size": 25,
    "alert_thresholds": {
        "mongo_size_warn_gb": 5.0,
        "pg_size_warn_gb": 10.0,
        "redis_memory_warn_mb": 512,
        "connection_pool_warn_pct": 80,
        "error_rate_warn_per_hour": 10,
    },
    "notifications_enabled": True,
}

SETTINGS_ALLOWED_FIELDS = {
    "safe_mode", "auto_refresh_interval", "default_page_size",
    "alert_thresholds", "notifications_enabled",
}


class DatabaseDashboardService:
    """Core service for the Database Dashboard."""

    def __init__(self, mongo_db, ts_store=None, cache=None):
        self.db = mongo_db
        self.ts_store = ts_store
        self.cache = cache
        self._schema_cache: Dict[str, Any] = {}
        self._schema_cache_time: Dict[str, float] = {}
        self._schema_cache_ttl = 300  # 5 minutes

    # ===============================================================
    #  Overview
    # ===============================================================

    async def get_overview(self) -> Dict[str, Any]:
        """Get aggregated overview of all databases."""
        overview = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mongodb": await self._get_mongo_overview(),
            "postgresql": await self._get_pg_overview(),
            "redis": self._get_redis_overview(),
        }
        return overview

    async def _get_mongo_overview(self) -> Dict[str, Any]:
        try:
            await self.db.command("ping")
            collections = await self.db.list_collection_names()
            coll_stats = {}
            total_docs = 0
            for name in sorted(collections):
                count = await self.db[name].count_documents({})
                coll_stats[name] = {
                    "documents": count,
                    "description": MONGO_COLLECTION_META.get(name, {}).get("description", ""),
                    "ttl": MONGO_COLLECTION_META.get(name, {}).get("ttl"),
                }
                total_docs += count

            # Try to get database stats for size info
            db_stats = {}
            try:
                stats = await self.db.command("dbStats")
                db_stats = {
                    "data_size_bytes": stats.get("dataSize", 0),
                    "storage_size_bytes": stats.get("storageSize", 0),
                    "index_size_bytes": stats.get("indexSize", 0),
                    "data_size_mb": round(stats.get("dataSize", 0) / (1024 * 1024), 2),
                    "storage_size_mb": round(stats.get("storageSize", 0) / (1024 * 1024), 2),
                }
            except Exception:
                pass

            return {
                "status": "connected",
                "collections_count": len(collections),
                "total_documents": total_docs,
                "collections": coll_stats,
                "size": db_stats,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _get_pg_overview(self) -> Dict[str, Any]:
        if not self.ts_store or not self.ts_store._is_initialized:
            return {"status": "not_initialized"}
        try:
            stats = await self.ts_store.get_stats()
            total_rows = sum(t.get("rows", 0) for t in stats.values() if isinstance(t, dict) and "rows" in t)
            tables = {}
            for name, info in stats.items():
                if name == "pool":
                    continue
                tables[name] = {
                    **info,
                    "description": PG_TABLE_META.get(name, {}).get("description", ""),
                    "primary_key": PG_TABLE_META.get(name, {}).get("primary_key", ""),
                }
            return {
                "status": "connected",
                "tables_count": len(tables),
                "total_rows": total_rows,
                "tables": tables,
                "pool": stats.get("pool", {}),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _get_redis_overview(self) -> Dict[str, Any]:
        if not self.cache:
            return {"status": "unavailable"}
        stats = self.cache.get_stats()
        return {
            "status": "connected" if self.cache.is_redis_available else "fallback",
            "backend": stats.get("backend", "unknown"),
            "key_count": stats.get("key_count", 0),
            "memory_used": stats.get("memory_used", "N/A"),
            "hit_rate": stats.get("hit_rate_percent", 0),
            "hits": stats.get("hits", 0),
            "misses": stats.get("misses", 0),
        }

    # ===============================================================
    #  MongoDB Introspection
    # ===============================================================

    async def get_mongo_collections(self) -> List[Dict[str, Any]]:
        """List all MongoDB collections with stats and metadata."""
        collections = await self.db.list_collection_names()
        result = []
        for name in sorted(collections):
            count = await self.db[name].count_documents({})
            meta = MONGO_COLLECTION_META.get(name, {})
            indexes = await self.db[name].index_information()
            result.append({
                "name": name,
                "documents": count,
                "indexes": len(indexes),
                "description": meta.get("description", ""),
                "sources": meta.get("sources", []),
                "consumers": meta.get("consumers", []),
                "ttl": meta.get("ttl"),
            })
        return result

    async def get_collection_sample(
        self, name: str, page: int = 1, page_size: int = 25
    ) -> Dict[str, Any]:
        """Get paginated sample documents from a MongoDB collection."""
        if page_size > 100:
            page_size = 100
        if page < 1:
            page = 1

        collection = self.db[name]
        total = await collection.count_documents({})
        skip = (page - 1) * page_size

        cursor = collection.find({}, {"_id": 0}).skip(skip).limit(page_size)
        docs = await cursor.to_list(length=page_size)

        return {
            "collection": name,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "documents": docs,
        }

    async def get_collection_schema(self, name: str) -> Dict[str, Any]:
        """Infer schema from sample documents + any JSON schema validator."""
        import time
        cache_key = f"mongo_schema_{name}"
        now = time.time()
        if cache_key in self._schema_cache and (now - self._schema_cache_time.get(cache_key, 0)) < self._schema_cache_ttl:
            return self._schema_cache[cache_key]

        schema_info: Dict[str, Any] = {"collection": name, "fields": {}}

        # Try to get existing JSON schema validator
        try:
            coll_info = await self.db.command("listCollections", filter={"name": name})
            for coll in coll_info.get("cursor", {}).get("firstBatch", []):
                options = coll.get("options", {})
                validator = options.get("validator", {})
                if validator:
                    schema_info["validator"] = validator
        except Exception:
            pass

        # Infer from sample documents
        sample = await self.db[name].find({}, {"_id": 0}).limit(10).to_list(length=10)
        field_types: Dict[str, Set[str]] = {}
        for doc in sample:
            for key, val in doc.items():
                t = type(val).__name__
                if key not in field_types:
                    field_types[key] = set()
                field_types[key].add(t)

        schema_info["fields"] = {k: list(v) for k, v in field_types.items()}
        schema_info["sample_count"] = len(sample)

        # Get index info
        indexes = await self.db[name].index_information()
        schema_info["indexes"] = {
            idx_name: {
                "keys": info.get("key", []),
                "unique": info.get("unique", False),
                "sparse": info.get("sparse", False),
            }
            for idx_name, info in indexes.items()
        }

        self._schema_cache[cache_key] = schema_info
        self._schema_cache_time[cache_key] = now
        return schema_info

    async def delete_document(
        self, collection: str, doc_id: str, id_field: str = "symbol"
    ) -> bool:
        """Delete a single document from a MongoDB collection."""
        if collection not in DELETABLE_COLLECTIONS:
            raise ValueError(f"Deletion not allowed for collection: {collection}")

        result = await self.db[collection].delete_one({id_field: doc_id})
        return result.deleted_count > 0

    # ===============================================================
    #  PostgreSQL Introspection
    # ===============================================================

    async def get_pg_tables(self) -> List[Dict[str, Any]]:
        """List PostgreSQL tables with stats."""
        if not self.ts_store or not self.ts_store._is_initialized:
            return []

        stats = await self.ts_store.get_stats()
        result = []
        for name, info in stats.items():
            if name == "pool":
                continue
            meta = PG_TABLE_META.get(name, {})
            result.append({
                "name": name,
                "rows": info.get("rows", 0),
                "size": info.get("size", "N/A"),
                "description": meta.get("description", ""),
                "sources": meta.get("sources", []),
                "consumers": meta.get("consumers", []),
                "primary_key": meta.get("primary_key", ""),
            })
        return result

    async def get_table_sample(
        self, name: str, page: int = 1, page_size: int = 25
    ) -> Dict[str, Any]:
        """Get paginated sample rows from a PostgreSQL table."""
        if page_size > 100:
            page_size = 100
        if page < 1:
            page = 1

        # Whitelist table names to prevent SQL injection
        allowed = set(PG_TABLE_META.keys())
        if name not in allowed:
            raise ValueError(f"Table not allowed: {name}")

        if not self.ts_store or not self.ts_store._is_initialized:
            return {"table": name, "total": 0, "documents": []}

        offset = (page - 1) * page_size
        async with self.ts_store._pool.acquire() as conn:
            total = await conn.fetchval(f"SELECT COUNT(*) FROM {name}")
            rows = await conn.fetch(
                f"SELECT * FROM {name} ORDER BY 1 DESC, 2 DESC LIMIT $1 OFFSET $2",
                page_size, offset,
            )
            docs = []
            for row in rows:
                doc = {}
                for key, val in dict(row).items():
                    if hasattr(val, "isoformat"):
                        doc[key] = val.isoformat()
                    elif isinstance(val, (int, float, str, bool, type(None))):
                        doc[key] = val
                    else:
                        doc[key] = str(val)
                docs.append(doc)

        return {
            "table": name,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "documents": docs,
        }

    async def get_table_schema(self, name: str) -> Dict[str, Any]:
        """Get PostgreSQL table schema from information_schema."""
        import time
        cache_key = f"pg_schema_{name}"
        now = time.time()
        if cache_key in self._schema_cache and (now - self._schema_cache_time.get(cache_key, 0)) < self._schema_cache_ttl:
            return self._schema_cache[cache_key]

        allowed = set(PG_TABLE_META.keys())
        if name not in allowed:
            raise ValueError(f"Table not allowed: {name}")

        if not self.ts_store or not self.ts_store._is_initialized:
            return {"table": name, "columns": []}

        async with self.ts_store._pool.acquire() as conn:
            columns = await conn.fetch(
                """
                SELECT column_name, data_type, is_nullable, column_default,
                       character_maximum_length, numeric_precision
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = $1
                ORDER BY ordinal_position
                """,
                name,
            )
            indexes = await conn.fetch(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = $1
                """,
                name,
            )
            # Get foreign keys
            fks = await conn.fetch(
                """
                SELECT
                    tc.constraint_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table,
                    ccu.column_name AS foreign_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_name = $1
                """,
                name,
            )

        schema = {
            "table": name,
            "columns": [
                {
                    "name": c["column_name"],
                    "type": c["data_type"],
                    "nullable": c["is_nullable"] == "YES",
                    "default": c["column_default"],
                    "max_length": c["character_maximum_length"],
                }
                for c in columns
            ],
            "indexes": [
                {"name": i["indexname"], "definition": i["indexdef"]}
                for i in indexes
            ],
            "foreign_keys": [dict(fk) for fk in fks],
            "primary_key": PG_TABLE_META.get(name, {}).get("primary_key", ""),
            "description": PG_TABLE_META.get(name, {}).get("description", ""),
        }

        self._schema_cache[cache_key] = schema
        self._schema_cache_time[cache_key] = now
        return schema

    # ===============================================================
    #  Redis Introspection
    # ===============================================================

    def get_redis_keys(self, prefix: str = "") -> List[Dict[str, Any]]:
        """List Redis keys grouped by prefix with metadata."""
        if not self.cache or not self.cache.is_redis_available:
            return []

        try:
            r = self.cache._redis
            pattern = f"{prefix}*" if prefix else "*"
            keys = []
            for key in r.scan_iter(match=pattern, count=200):
                if isinstance(key, bytes):
                    key = key.decode("utf-8")
                key_type = r.type(key)
                if isinstance(key_type, bytes):
                    key_type = key_type.decode("utf-8")
                ttl = r.ttl(key)

                key_info = {
                    "key": key,
                    "type": key_type,
                    "ttl": ttl if ttl > 0 else None,
                }

                # Only show values for safe prefixes
                is_safe = any(key.startswith(p) for p in REDIS_SAFE_PREFIXES)
                if is_safe:
                    try:
                        if key_type == "string":
                            val = r.get(key)
                            if isinstance(val, bytes):
                                val = val.decode("utf-8")
                            # Truncate long values
                            if val and len(val) > 500:
                                val = val[:500] + "...(truncated)"
                            key_info["value_preview"] = val
                        elif key_type == "list":
                            key_info["length"] = r.llen(key)
                        elif key_type == "set":
                            key_info["members"] = r.scard(key)
                        elif key_type == "zset":
                            key_info["members"] = r.zcard(key)
                        elif key_type == "hash":
                            key_info["fields"] = r.hlen(key)
                    except Exception:
                        pass
                else:
                    key_info["value_preview"] = "(hidden - potentially sensitive)"

                keys.append(key_info)
                if len(keys) >= 500:
                    break

            return keys
        except Exception as e:
            logger.warning(f"Failed to list Redis keys: {e}")
            return []

    # ===============================================================
    #  Activity & Errors
    # ===============================================================

    async def get_recent_activity(
        self, limit: int = 50, collection_filter: str = None
    ) -> List[Dict[str, Any]]:
        """Get recent database activity from extraction_log and pipeline_jobs."""
        if limit > 500:
            limit = 500

        activity = []

        # Pipeline jobs
        try:
            query = {}
            if collection_filter and collection_filter == "pipeline_jobs":
                pass  # no extra filter
            elif collection_filter:
                query = {"_skip": True}

            if not query.get("_skip"):
                cursor = (
                    self.db.pipeline_jobs
                    .find({}, {"_id": 0})
                    .sort("created_at", -1)
                    .limit(min(limit, 50))
                )
                jobs = await cursor.to_list(length=min(limit, 50))
                for job in jobs:
                    activity.append({
                        "type": "pipeline_job",
                        "collection": "pipeline_jobs",
                        "timestamp": job.get("created_at", ""),
                        "status": job.get("status", "unknown"),
                        "summary": f"Job {job.get('job_id', 'N/A')}: {job.get('status', 'unknown')}",
                        "details": {
                            "job_id": job.get("job_id"),
                            "symbols_count": job.get("total_symbols", 0),
                            "processed": job.get("processed_symbols", 0),
                        },
                    })
        except Exception as e:
            logger.warning(f"Failed to fetch pipeline jobs: {e}")

        # Extraction log entries
        try:
            if not collection_filter or collection_filter in ("extraction_log", None):
                cursor = (
                    self.db.extraction_log
                    .find({}, {"_id": 0})
                    .sort("started_at", -1)
                    .limit(min(limit, 50))
                )
                logs = await cursor.to_list(length=min(limit, 50))
                for log in logs:
                    activity.append({
                        "type": "extraction",
                        "collection": "extraction_log",
                        "timestamp": log.get("started_at", log.get("completed_at", "")),
                        "status": log.get("status", "unknown"),
                        "summary": f"Extraction {log.get('source', 'N/A')} / {log.get('symbol', 'N/A')}: {log.get('status', 'unknown')}",
                        "details": {
                            "source": log.get("source"),
                            "symbol": log.get("symbol"),
                            "duration_ms": log.get("duration_ms"),
                        },
                    })
        except Exception as e:
            logger.warning(f"Failed to fetch extraction logs: {e}")

        # Audit log entries
        try:
            if not collection_filter or collection_filter in ("audit_log", None):
                cursor = (
                    self.db.audit_log
                    .find({}, {"_id": 0})
                    .sort("timestamp", -1)
                    .limit(min(limit, 50))
                )
                audits = await cursor.to_list(length=min(limit, 50))
                for audit in audits:
                    activity.append({
                        "type": "audit",
                        "collection": "audit_log",
                        "timestamp": audit.get("timestamp", ""),
                        "status": "info",
                        "summary": f"{audit.get('action', 'N/A')} on {audit.get('collection_or_table', 'N/A')}: {audit.get('record_id', 'N/A')}",
                        "details": audit,
                    })
        except Exception as e:
            pass  # audit_log may not exist yet

        # Sort by timestamp descending
        activity.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return activity[:limit]

    async def get_recent_errors(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent errors from extraction_log and pipeline_jobs."""
        if limit > 500:
            limit = 500
        errors = []

        # Failed pipeline jobs
        try:
            cursor = (
                self.db.pipeline_jobs
                .find({"status": {"$in": ["failed", "error"]}}, {"_id": 0})
                .sort("created_at", -1)
                .limit(min(limit, 50))
            )
            jobs = await cursor.to_list(length=min(limit, 50))
            for job in jobs:
                errors.append({
                    "type": "pipeline_job",
                    "collection": "pipeline_jobs",
                    "timestamp": job.get("created_at", ""),
                    "severity": "error",
                    "message": f"Pipeline job {job.get('job_id', 'N/A')} failed",
                    "details": {
                        "job_id": job.get("job_id"),
                        "errors": job.get("errors", [])[:5],
                    },
                })
        except Exception as e:
            logger.warning(f"Failed to fetch error jobs: {e}")

        # Failed extractions
        try:
            cursor = (
                self.db.extraction_log
                .find({"status": {"$in": ["failed", "error"]}}, {"_id": 0})
                .sort("started_at", -1)
                .limit(min(limit, 50))
            )
            logs = await cursor.to_list(length=min(limit, 50))
            for log in logs:
                errors.append({
                    "type": "extraction",
                    "collection": "extraction_log",
                    "timestamp": log.get("started_at", ""),
                    "severity": "error",
                    "message": log.get("error_message", f"Extraction failed for {log.get('symbol', 'N/A')}"),
                    "details": {
                        "source": log.get("source"),
                        "symbol": log.get("symbol"),
                        "error_message": log.get("error_message"),
                    },
                })
        except Exception as e:
            logger.warning(f"Failed to fetch extraction errors: {e}")

        errors.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return errors[:limit]

    # ===============================================================
    #  Settings
    # ===============================================================

    async def get_settings(self) -> Dict[str, Any]:
        """Get dashboard settings from db_settings collection."""
        try:
            settings = await self.db.db_settings.find_one(
                {"_key": "dashboard"}, {"_id": 0}
            )
            if settings:
                settings.pop("_key", None)
                # Merge with defaults for any missing keys
                merged = {**DEFAULT_SETTINGS, **settings}
                return merged
            return {**DEFAULT_SETTINGS}
        except Exception as e:
            logger.warning(f"Failed to load settings: {e}")
            return {**DEFAULT_SETTINGS}

    async def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update dashboard settings."""
        # Validate fields
        safe_updates = {}
        for key, value in updates.items():
            if key not in SETTINGS_ALLOWED_FIELDS:
                continue
            # Type validation
            if key == "safe_mode" and isinstance(value, bool):
                safe_updates[key] = value
            elif key == "auto_refresh_interval" and isinstance(value, (int, float)):
                safe_updates[key] = max(15, min(300, int(value)))
            elif key == "default_page_size" and isinstance(value, int):
                safe_updates[key] = max(10, min(100, value))
            elif key == "alert_thresholds" and isinstance(value, dict):
                # Validate threshold values
                clean_thresholds = {}
                for tk, tv in value.items():
                    if isinstance(tv, (int, float)) and tv >= 0:
                        clean_thresholds[tk] = tv
                if clean_thresholds:
                    safe_updates["alert_thresholds"] = clean_thresholds
            elif key == "notifications_enabled" and isinstance(value, bool):
                safe_updates[key] = value

        if not safe_updates:
            raise ValueError("No valid settings to update")

        safe_updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        await self.db.db_settings.update_one(
            {"_key": "dashboard"},
            {"$set": safe_updates},
            upsert=True,
        )

        return await self.get_settings()

    # ===============================================================
    #  Audit Logging
    # ===============================================================

    async def log_audit(
        self,
        action: str,
        store: str,
        collection_or_table: str,
        record_id: str,
        previous_value: Any = None,
        new_value: Any = None,
        initiator: str = "dashboard",
    ) -> None:
        """Write an entry to the audit_log collection."""
        entry = {
            "action": action,
            "store": store,
            "collection_or_table": collection_or_table,
            "record_id": str(record_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "initiator": initiator,
        }
        if previous_value is not None:
            # Truncate large values
            prev_str = str(previous_value)
            entry["previous_value"] = prev_str[:2000] if len(prev_str) > 2000 else previous_value
        if new_value is not None:
            new_str = str(new_value)
            entry["new_value"] = new_str[:2000] if len(new_str) > 2000 else new_value

        try:
            await self.db.audit_log.insert_one(entry)
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

    async def get_audit_log(
        self, page: int = 1, page_size: int = 50,
        action: str = None, store: str = None, collection_or_table: str = None,
    ) -> Dict[str, Any]:
        """Get paginated audit log."""
        if page_size > 100:
            page_size = 100

        query: Dict[str, Any] = {}
        if action:
            query["action"] = action
        if store:
            query["store"] = store
        if collection_or_table:
            query["collection_or_table"] = collection_or_table

        total = await self.db.audit_log.count_documents(query)
        skip = (page - 1) * page_size

        cursor = (
            self.db.audit_log
            .find(query, {"_id": 0})
            .sort("timestamp", -1)
            .skip(skip)
            .limit(page_size)
        )
        entries = await cursor.to_list(length=page_size)

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "entries": entries,
        }

    # ===============================================================
    #  Alert Threshold Checks
    # ===============================================================

    async def check_thresholds(self) -> List[Dict[str, Any]]:
        """Check current state against configured alert thresholds."""
        settings = await self.get_settings()
        thresholds = settings.get("alert_thresholds", {})
        alerts = []

        # MongoDB size check
        try:
            stats = await self.db.command("dbStats")
            size_gb = stats.get("dataSize", 0) / (1024 ** 3)
            warn_gb = thresholds.get("mongo_size_warn_gb", 5.0)
            if size_gb > warn_gb:
                alerts.append({
                    "type": "storage",
                    "store": "mongodb",
                    "severity": "warning",
                    "message": f"MongoDB data size ({size_gb:.2f} GB) exceeds threshold ({warn_gb} GB)",
                    "current_value": round(size_gb, 2),
                    "threshold": warn_gb,
                })
        except Exception:
            pass

        # Redis memory check
        if self.cache and self.cache.is_redis_available:
            try:
                r = self.cache._redis
                info = r.info("memory")
                used_mb = info.get("used_memory", 0) / (1024 * 1024)
                warn_mb = thresholds.get("redis_memory_warn_mb", 512)
                if used_mb > warn_mb:
                    alerts.append({
                        "type": "memory",
                        "store": "redis",
                        "severity": "warning",
                        "message": f"Redis memory ({used_mb:.0f} MB) exceeds threshold ({warn_mb} MB)",
                        "current_value": round(used_mb, 0),
                        "threshold": warn_mb,
                    })
            except Exception:
                pass

        # PostgreSQL pool usage
        if self.ts_store and self.ts_store._is_initialized:
            try:
                pool = self.ts_store._pool
                total = pool.get_size()
                free = pool.get_idle_size()
                if total > 0:
                    used_pct = ((total - free) / total) * 100
                    warn_pct = thresholds.get("connection_pool_warn_pct", 80)
                    if used_pct > warn_pct:
                        alerts.append({
                            "type": "connection",
                            "store": "postgresql",
                            "severity": "warning",
                            "message": f"PostgreSQL pool usage ({used_pct:.0f}%) exceeds threshold ({warn_pct}%)",
                            "current_value": round(used_pct, 0),
                            "threshold": warn_pct,
                        })
            except Exception:
                pass

        return alerts

    # ===============================================================
    #  Data Flow Description
    # ===============================================================

    def get_data_flow(self) -> Dict[str, Any]:
        """Return a structured description of how data flows through the system."""
        return {
            "description": "StockPulse data flows from external APIs through the extraction pipeline into three database layers, then to the frontend.",
            "stages": [
                {
                    "stage": 1,
                    "name": "External Data Sources",
                    "description": "Market data fetched from external APIs",
                    "sources": ["Groww API", "Yahoo Finance (yfinance)", "NSE Bhavcopy", "Screener.in"],
                },
                {
                    "stage": 2,
                    "name": "Extraction Pipeline",
                    "description": "Raw data extracted, cleaned, normalized, and validated",
                    "components": ["PipelineOrchestrator", "GrowwExtractor", "NSEBhavcopyExtractor", "ScreenerExtractor"],
                    "outputs_to": ["MongoDB (stock_data, extraction_log, pipeline_jobs)", "PostgreSQL (prices_daily, technical_indicators)"],
                },
                {
                    "stage": 3,
                    "name": "Primary Storage",
                    "description": "Data stored across three database layers",
                    "stores": {
                        "MongoDB": "Entity/document store - stock data, user data (watchlist/portfolio/alerts), pipeline logs, news, backtest results",
                        "PostgreSQL": "Time-series store - daily OHLCV prices, technical indicators, quarterly fundamentals and shareholding",
                        "Redis": "Cache layer - live prices, analysis results, market overview, pipeline status",
                    },
                },
                {
                    "stage": 4,
                    "name": "API Layer (FastAPI)",
                    "description": "Backend serves data to frontend via REST API and WebSocket",
                    "endpoints": "70+ REST endpoints under /api, WebSocket at /ws/prices",
                },
                {
                    "stage": 5,
                    "name": "Frontend (React)",
                    "description": "User-facing dashboard, analyzers, and management tools",
                    "pages": ["Dashboard", "Stock Analyzer", "Screener", "Watchlist", "Portfolio", "Alerts", "Backtest", "News Hub", "Reports", "Data Pipeline", "Database Dashboard"],
                },
            ],
            "collection_flows": {
                name: {
                    "sources": meta.get("sources", []),
                    "consumers": meta.get("consumers", []),
                }
                for name, meta in MONGO_COLLECTION_META.items()
            },
            "table_flows": {
                name: {
                    "sources": meta.get("sources", []),
                    "consumers": meta.get("consumers", []),
                }
                for name, meta in PG_TABLE_META.items()
            },
        }
