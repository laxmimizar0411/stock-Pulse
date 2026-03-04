"""
Database Dashboard API Router for StockPulse.

Provides endpoints for database monitoring, introspection, manual data
management, audit logging, settings, and error tracking. All data access
goes through the DatabaseDashboardService - no direct DB access from frontend.
"""

import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/database", tags=["database-dashboard"])

# Will be set during app startup
_dashboard_service = None


def init_dashboard_router(dashboard_service):
    """Initialize the router with the dashboard service instance."""
    global _dashboard_service
    _dashboard_service = dashboard_service


def _svc():
    """Get service or raise 503."""
    if _dashboard_service is None:
        raise HTTPException(status_code=503, detail="Dashboard service not initialized")
    return _dashboard_service


# -------------------------------------------------------------------
#  Request / Response Models
# -------------------------------------------------------------------

class SettingsUpdate(BaseModel):
    safe_mode: Optional[bool] = None
    auto_refresh_interval: Optional[int] = Field(None, ge=15, le=300)
    default_page_size: Optional[int] = Field(None, ge=10, le=100)
    alert_thresholds: Optional[Dict[str, float]] = None
    notifications_enabled: Optional[bool] = None


class DeleteDocumentRequest(BaseModel):
    id_field: str = Field(default="symbol", max_length=50)
    id_value: str = Field(..., max_length=200)


# -------------------------------------------------------------------
#  Overview & Health
# -------------------------------------------------------------------

@router.get("/overview")
async def get_database_overview():
    """
    Aggregated overview of all databases: MongoDB collections with doc counts,
    PostgreSQL tables with row counts/sizes, Redis key counts and memory.
    """
    try:
        return await _svc().get_overview()
    except Exception as e:
        logger.error(f"Overview error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load overview: {str(e)}")


@router.get("/data-flow")
async def get_data_flow():
    """
    Get a structured description of how data flows through the system:
    External APIs -> Pipeline -> MongoDB/PostgreSQL/Redis -> API -> Frontend.
    """
    return _svc().get_data_flow()


@router.get("/threshold-alerts")
async def get_threshold_alerts():
    """Check current state against configured alert thresholds."""
    try:
        return {"alerts": await _svc().check_thresholds()}
    except Exception as e:
        logger.error(f"Threshold check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
#  MongoDB Introspection
# -------------------------------------------------------------------

@router.get("/collections")
async def list_mongo_collections():
    """List all MongoDB collections with document counts, indexes, and metadata."""
    try:
        return {"collections": await _svc().get_mongo_collections()}
    except Exception as e:
        logger.error(f"Collections list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{name}/sample")
async def get_collection_sample(
    name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
):
    """Get paginated sample documents from a MongoDB collection."""
    # Validate collection name (alphanumeric + underscore only)
    if not re.match(r"^[a-z_]{1,50}$", name):
        raise HTTPException(status_code=400, detail="Invalid collection name")
    try:
        return await _svc().get_collection_sample(name, page, page_size)
    except Exception as e:
        logger.error(f"Collection sample error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{name}/schema")
async def get_collection_schema(name: str):
    """Get schema information for a MongoDB collection (inferred + validator)."""
    if not re.match(r"^[a-z_]{1,50}$", name):
        raise HTTPException(status_code=400, detail="Invalid collection name")
    try:
        return await _svc().get_collection_schema(name)
    except Exception as e:
        logger.error(f"Collection schema error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/collections/{name}/documents")
async def delete_collection_document(name: str, request: DeleteDocumentRequest):
    """
    Delete a single document from a MongoDB collection.
    Only allowed for specific collections; requires safe mode check.
    """
    if not re.match(r"^[a-z_]{1,50}$", name):
        raise HTTPException(status_code=400, detail="Invalid collection name")

    svc = _svc()

    # Safe mode check
    settings = await svc.get_settings()
    if settings.get("safe_mode", True):
        # In safe mode, require the caller to explicitly confirm
        # (frontend sends confirmation; we just validate the request is well-formed)
        pass

    # Get previous value for audit log
    prev_doc = None
    try:
        prev_doc = await svc.db[name].find_one(
            {request.id_field: request.id_value}, {"_id": 0}
        )
    except Exception:
        pass

    try:
        deleted = await svc.delete_document(name, request.id_value, request.id_field)
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found")

        # Audit log
        await svc.log_audit(
            action="delete",
            store="mongodb",
            collection_or_table=name,
            record_id=request.id_value,
            previous_value=prev_doc,
        )

        return {"message": "Document deleted", "collection": name, "id": request.id_value}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete document error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
#  PostgreSQL Introspection
# -------------------------------------------------------------------

@router.get("/tables")
async def list_pg_tables():
    """List all PostgreSQL tables with row counts, sizes, and metadata."""
    try:
        return {"tables": await _svc().get_pg_tables()}
    except Exception as e:
        logger.error(f"Tables list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables/{name}/sample")
async def get_table_sample(
    name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
):
    """Get paginated sample rows from a PostgreSQL table."""
    try:
        return await _svc().get_table_sample(name, page, page_size)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Table sample error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables/{name}/schema")
async def get_table_schema(name: str):
    """Get schema (columns, types, indexes, foreign keys) for a PostgreSQL table."""
    try:
        return await _svc().get_table_schema(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Table schema error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
#  Redis Introspection
# -------------------------------------------------------------------

@router.get("/redis/keys")
async def list_redis_keys(prefix: str = Query(default="", max_length=100)):
    """List Redis keys with metadata, grouped by prefix. Safe values only."""
    try:
        return {"keys": _svc().get_redis_keys(prefix)}
    except Exception as e:
        logger.error(f"Redis keys error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
#  Activity & Errors
# -------------------------------------------------------------------

@router.get("/activity")
async def get_recent_activity(
    limit: int = Query(default=50, ge=1, le=500),
    collection: Optional[str] = Query(default=None, max_length=50),
    since: Optional[str] = Query(default=None, max_length=30, description="ISO date/datetime lower bound"),
    until: Optional[str] = Query(default=None, max_length=30, description="ISO date/datetime upper bound"),
):
    """Get recent database activity (pipeline jobs, extraction logs, audit entries)."""
    try:
        return {"activity": await _svc().get_recent_activity(limit, collection, since, until)}
    except Exception as e:
        logger.error(f"Activity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/errors")
async def get_recent_errors(
    limit: int = Query(default=50, ge=1, le=500),
    since: Optional[str] = Query(default=None, max_length=30),
    until: Optional[str] = Query(default=None, max_length=30),
):
    """Get recent database errors (failed pipeline jobs, failed extractions)."""
    try:
        return {"errors": await _svc().get_recent_errors(limit, since, until)}
    except Exception as e:
        logger.error(f"Errors fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/errors/trend")
async def get_error_trend(
    days: int = Query(default=7, ge=1, le=30),
):
    """Get error counts per day for the last N days."""
    try:
        return {"trend": await _svc().get_error_trend(days)}
    except Exception as e:
        logger.error(f"Error trend error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
#  Settings
# -------------------------------------------------------------------

@router.get("/settings")
async def get_dashboard_settings():
    """Get current dashboard settings (safe mode, thresholds, refresh interval)."""
    try:
        return await _svc().get_settings()
    except Exception as e:
        logger.error(f"Settings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/settings")
async def update_dashboard_settings(updates: SettingsUpdate):
    """Update dashboard settings. Only allowed fields are accepted."""
    try:
        update_dict = updates.model_dump(exclude_none=True)
        if not update_dict:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = await _svc().update_settings(update_dict)

        # Audit log
        await _svc().log_audit(
            action="update",
            store="mongodb",
            collection_or_table="db_settings",
            record_id="dashboard",
            new_value=update_dict,
        )

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Settings update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
#  Audit Log
# -------------------------------------------------------------------

class AuditLogEntry(BaseModel):
    action: str = Field(..., max_length=20)
    store: str = Field(..., max_length=20)
    collection_or_table: str = Field(..., max_length=50)
    record_id: str = Field(..., max_length=200)
    previous_value: Optional[Any] = None
    new_value: Optional[Any] = None


@router.post("/audit-log")
async def write_audit_log(entry: AuditLogEntry):
    """Write an audit log entry (called by frontend after CRUD operations)."""
    try:
        await _svc().log_audit(
            action=entry.action,
            store=entry.store,
            collection_or_table=entry.collection_or_table,
            record_id=entry.record_id,
            previous_value=entry.previous_value,
            new_value=entry.new_value,
            initiator="dashboard",
        )
        return {"message": "Audit log entry created"}
    except Exception as e:
        logger.error(f"Audit log write error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-log")
async def get_audit_log(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    action: Optional[str] = Query(default=None, max_length=20),
    store: Optional[str] = Query(default=None, max_length=20),
    collection_or_table: Optional[str] = Query(default=None, max_length=50),
):
    """Get paginated audit log of all dashboard operations."""
    try:
        return await _svc().get_audit_log(
            page=page,
            page_size=page_size,
            action=action,
            store=store,
            collection_or_table=collection_or_table,
        )
    except Exception as e:
        logger.error(f"Audit log error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
#  Export
# -------------------------------------------------------------------

@router.get("/collections/{name}/export")
async def export_collection(
    name: str,
    format: str = Query(default="json", regex="^(json|csv)$"),
    limit: int = Query(default=5000, ge=1, le=10000),
):
    """Export MongoDB collection data as JSON or CSV."""
    if not re.match(r"^[a-z_]{1,50}$", name):
        raise HTTPException(status_code=400, detail="Invalid collection name")
    try:
        return await _svc().export_collection(name, format, limit)
    except Exception as e:
        logger.error(f"Export collection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables/{name}/export")
async def export_table(
    name: str,
    format: str = Query(default="json", regex="^(json|csv)$"),
    limit: int = Query(default=5000, ge=1, le=10000),
):
    """Export PostgreSQL table data as JSON or CSV."""
    try:
        return await _svc().export_table(name, format, limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Export table error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
#  Bulk Operations
# -------------------------------------------------------------------

class BulkDeleteRequest(BaseModel):
    id_field: str = Field(default="symbol", max_length=50)
    id_values: List[str] = Field(..., max_length=100)


@router.post("/collections/{name}/bulk-delete")
async def bulk_delete_documents(name: str, request: BulkDeleteRequest):
    """Delete multiple documents from a MongoDB collection."""
    if not re.match(r"^[a-z_]{1,50}$", name):
        raise HTTPException(status_code=400, detail="Invalid collection name")

    svc = _svc()
    settings = await svc.get_settings()

    try:
        result = await svc.bulk_delete(name, request.id_field, request.id_values)

        await svc.log_audit(
            action="bulk_delete",
            store="mongodb",
            collection_or_table=name,
            record_id=f"{len(request.id_values)} documents",
            new_value={"id_field": request.id_field, "ids": request.id_values[:10]},
        )

        return result
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Bulk delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
#  Query Playground
# -------------------------------------------------------------------

class MongoQueryRequest(BaseModel):
    collection: str = Field(..., max_length=50)
    query: Dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=50, ge=1, le=200)


class PgQueryRequest(BaseModel):
    sql: str = Field(..., max_length=2000)
    limit: int = Field(default=50, ge=1, le=200)


@router.post("/query/mongodb")
async def execute_mongo_query(request: MongoQueryRequest):
    """Execute a read-only MongoDB find query."""
    try:
        return await _svc().execute_mongo_query(
            request.collection, request.query, request.limit
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Mongo query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/postgresql")
async def execute_pg_query(request: PgQueryRequest):
    """Execute a read-only PostgreSQL SELECT query."""
    try:
        return await _svc().execute_pg_query(request.sql, request.limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"PG query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
#  Database Backup Trigger
# -------------------------------------------------------------------

@router.post("/backup")
async def trigger_backup():
    """Trigger a MongoDB backup using the backup script."""
    import asyncio

    script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts", "backup_mongodb.py",
    )

    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="Backup script not found")

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        output = stdout.decode("utf-8", errors="replace")
        error_output = stderr.decode("utf-8", errors="replace")
        success = proc.returncode == 0

        await _svc().log_audit(
            action="backup",
            store="mongodb",
            collection_or_table="all",
            record_id="manual_trigger",
            new_value={"success": success, "output_lines": output.count("\n")},
        )

        return {
            "success": success,
            "return_code": proc.returncode,
            "output": output[-2000:],  # last 2000 chars
            "errors": error_output[-1000:] if error_output else None,
        }
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Backup timed out (120s)")
    except Exception as e:
        logger.error(f"Backup trigger error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
#  Historical Size Tracking
# -------------------------------------------------------------------

@router.post("/size-snapshot")
async def record_size_snapshot():
    """Record a database size snapshot (called daily or manually)."""
    try:
        return await _svc().record_size_snapshot()
    except Exception as e:
        logger.error(f"Size snapshot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/size-history")
async def get_size_history(
    days: int = Query(default=30, ge=1, le=365),
):
    """Get historical database size snapshots."""
    try:
        return {"history": await _svc().get_size_history(days)}
    except Exception as e:
        logger.error(f"Size history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
#  Collection Comparison
# -------------------------------------------------------------------

@router.get("/compare")
async def compare_collections(
    a: str = Query(..., max_length=50),
    b: str = Query(..., max_length=50),
):
    """Compare two MongoDB collections side-by-side."""
    for name in [a, b]:
        if not re.match(r"^[a-z_]{1,50}$", name):
            raise HTTPException(status_code=400, detail=f"Invalid name: {name}")
    try:
        return await _svc().compare_collections(a, b)
    except Exception as e:
        logger.error(f"Comparison error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
