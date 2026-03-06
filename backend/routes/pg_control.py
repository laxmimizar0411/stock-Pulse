"""
PostgreSQL Control & Monitoring API Routes.

Provides endpoints for:
- Checking PostgreSQL status (running/stopped)
- Starting/stopping local PostgreSQL
- Resource monitoring (CPU, RAM, storage, connections)
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/database/postgres-control", tags=["postgres-control"])

_pg_control_service = None


def init_pg_control_router(pg_control_service):
    """Initialize the router with the PgControlService instance."""
    global _pg_control_service
    _pg_control_service = pg_control_service


def _svc():
    if _pg_control_service is None:
        raise HTTPException(status_code=503, detail="PostgreSQL control service not initialized")
    return _pg_control_service


class ControlAction(BaseModel):
    action: str  # "start" or "stop"


# ------------------------------------------------------------------
#  Status
# ------------------------------------------------------------------

@router.get("/status")
async def get_postgres_status():
    """Check if PostgreSQL is running and reachable."""
    try:
        return await _svc().get_status()
    except Exception as e:
        logger.error(f"PostgreSQL status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
#  Start / Stop
# ------------------------------------------------------------------

@router.post("/toggle")
async def toggle_postgres(body: ControlAction):
    """Start or stop the local PostgreSQL instance."""
    svc = _svc()
    action = body.action.lower()

    if action == "start":
        try:
            result = await svc.start_postgres()
            return result
        except Exception as e:
            logger.error(f"PostgreSQL start error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    elif action == "stop":
        try:
            result = await svc.stop_postgres()
            return result
        except Exception as e:
            logger.error(f"PostgreSQL stop error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'start' or 'stop'.")


# ------------------------------------------------------------------
#  Resource Monitoring
# ------------------------------------------------------------------

@router.get("/resources")
async def get_resource_usage():
    """Get CPU, RAM, storage, and connection metrics for PostgreSQL."""
    try:
        return await _svc().get_resource_usage()
    except Exception as e:
        logger.error(f"Resource monitoring error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def get_postgres_health():
    """Combined status + resource usage."""
    try:
        return await _svc().get_health()
    except Exception as e:
        logger.error(f"PostgreSQL health error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
