"""
Brain API Routes — Phase 1: Data Foundation & Event Infrastructure.

Endpoints:
    Health & Status:
        GET  /api/brain/health          — Full health check
        GET  /api/brain/config          — Config summary

    Feature Pipeline:
        GET  /api/brain/features/{symbol}          — Get/compute features for a symbol
        POST /api/brain/features/compute           — Trigger feature computation
        POST /api/brain/features/batch             — Batch compute for multiple symbols
        GET  /api/brain/features/status             — Feature pipeline status

    Data Quality:
        GET  /api/brain/data-quality/{symbol}      — Data quality report

    Batch Scheduler:
        GET  /api/brain/batch/status                — Scheduler status
        GET  /api/brain/batch/history               — Recent DAG run history
        POST /api/brain/batch/trigger/{dag_name}    — Trigger a specific DAG

    Kafka:
        GET  /api/brain/kafka/topics    — List Kafka topics
        GET  /api/brain/kafka/stats     — Kafka statistics

    Storage:
        GET  /api/brain/storage/status  — Storage layer status

    Ingestion:
        GET  /api/brain/ingestion/status — Ingestion pipeline status
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from brain.engine import brain_engine
from brain.events.topics import ALL_TOPICS

logger = logging.getLogger("brain.routes")

router = APIRouter(prefix="/api/brain", tags=["Brain"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class ComputeFeaturesRequest(BaseModel):
    symbol: str
    force_refresh: bool = False


class BatchComputeRequest(BaseModel):
    symbols: List[str]


class TriggerDagRequest(BaseModel):
    params: Optional[dict] = None


# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------

@router.get("/health")
async def brain_health():
    """Get Brain health status including all subsystems."""
    return await brain_engine.health_check()


@router.get("/config")
async def brain_config_summary():
    """Get Brain configuration summary (non-sensitive)."""
    return brain_engine.get_config_summary()


# ---------------------------------------------------------------------------
# Feature Pipeline
# ---------------------------------------------------------------------------

@router.get("/features/status")
async def feature_pipeline_status():
    """Get feature pipeline status and statistics."""
    if not brain_engine.feature_pipeline:
        return {"status": "not_initialized", "message": "Feature pipeline has not been started"}

    return {
        "status": "ready",
        "stats": brain_engine.feature_pipeline.get_stats(),
        "registered_features": brain_engine.feature_pipeline.registry.feature_count,
        "categories": brain_engine.feature_pipeline.registry.categories,
    }


@router.get("/features/{symbol}")
async def get_features(
    symbol: str,
    compute: bool = Query(False, description="Compute fresh features if not cached"),
):
    """
    Get computed features for a symbol.

    If compute=true, will fetch data and compute fresh features.
    Otherwise returns previously computed features from MongoDB.
    """
    symbol = symbol.upper().strip()

    if compute:
        if not brain_engine.feature_pipeline:
            raise HTTPException(status_code=503, detail="Feature pipeline not initialized")

        try:
            features = await brain_engine.compute_features(symbol)
            return {
                "symbol": symbol,
                "features": features,
                "feature_count": len(features),
                "source": "computed_fresh",
            }
        except Exception as e:
            logger.exception("Error computing features for %s", symbol)
            raise HTTPException(status_code=500, detail=f"Feature computation failed: {str(e)}")

    # Try stored features
    stored = await brain_engine.get_stored_features(symbol)
    if stored:
        return {
            "symbol": symbol,
            "features": stored.get("features", {}),
            "feature_count": stored.get("feature_count", 0),
            "computed_at": stored.get("computed_at"),
            "source": "cached",
        }

    return {
        "symbol": symbol,
        "features": {},
        "feature_count": 0,
        "source": "not_computed",
        "message": f"No features computed yet for {symbol}. Use ?compute=true to compute.",
    }


@router.post("/features/compute")
async def compute_features(request: ComputeFeaturesRequest):
    """Trigger feature computation for a single symbol."""
    if not brain_engine.feature_pipeline:
        raise HTTPException(status_code=503, detail="Feature pipeline not initialized")

    symbol = request.symbol.upper().strip()

    if request.force_refresh and brain_engine.feature_pipeline:
        brain_engine.feature_pipeline.invalidate_cache(symbol)

    try:
        features = await brain_engine.compute_features(symbol)
        return {
            "success": True,
            "symbol": symbol,
            "feature_count": len(features),
            "features": features,
        }
    except Exception as e:
        logger.exception("Error computing features for %s", symbol)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/features/batch")
async def batch_compute_features(request: BatchComputeRequest):
    """Trigger batch feature computation for multiple symbols."""
    if not brain_engine.feature_pipeline:
        raise HTTPException(status_code=503, detail="Feature pipeline not initialized")

    if len(request.symbols) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 symbols per batch")

    symbols = [s.upper().strip() for s in request.symbols]

    try:
        results = await brain_engine.compute_features_batch(symbols)
        return {
            "success": True,
            "total_symbols": len(symbols),
            "computed": sum(1 for v in results.values() if v),
            "failed": sum(1 for v in results.values() if not v),
            "results": {
                sym: {
                    "feature_count": len(features),
                    "features": features,
                }
                for sym, features in results.items()
            },
        }
    except Exception as e:
        logger.exception("Error in batch feature computation")
        raise HTTPException(status_code=500, detail=str(e))




# ---------------------------------------------------------------------------
# Data Quality
# ---------------------------------------------------------------------------

@router.get("/data-quality/{symbol}")
async def data_quality_report(symbol: str):
    """Get data quality report for a symbol."""
    symbol = symbol.upper().strip()

    try:
        report = await brain_engine.run_data_quality_check(symbol)
        return {
            "symbol": symbol,
            "report": report,
        }
    except Exception as e:
        logger.exception("Error running data quality check for %s", symbol)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Batch Scheduler
# ---------------------------------------------------------------------------

@router.get("/batch/status")
async def batch_scheduler_status():
    """Get batch scheduler status and DAG definitions."""
    if not brain_engine.batch_scheduler:
        return {"status": "not_initialized", "message": "Batch scheduler has not been started"}

    return brain_engine.batch_scheduler.get_status()


@router.get("/batch/history")
async def batch_run_history(limit: int = Query(20, ge=1, le=100)):
    """Get recent DAG run history."""
    if not brain_engine.batch_scheduler:
        return {"history": [], "message": "Batch scheduler not initialized"}

    return {"history": brain_engine.batch_scheduler.get_history(limit=limit)}


@router.post("/batch/trigger/{dag_name}")
async def trigger_dag(dag_name: str, request: Optional[TriggerDagRequest] = None):
    """Manually trigger a specific DAG."""
    if not brain_engine.batch_scheduler:
        raise HTTPException(status_code=503, detail="Batch scheduler not initialized")

    extra_kwargs = request.params if request and request.params else {}

    run = await brain_engine.batch_scheduler.trigger_dag(dag_name, **extra_kwargs)
    if run is None:
        raise HTTPException(status_code=404, detail=f"DAG '{dag_name}' not found")

    return {
        "success": run.status.value == "success",
        "run": run.to_dict(),
    }


# ---------------------------------------------------------------------------
# Kafka Event System
# ---------------------------------------------------------------------------

@router.get("/kafka/topics")
async def list_kafka_topics():
    """List all defined Kafka topics with their configurations."""
    return {
        "topics": [
            {
                "name": t.name,
                "partitions": t.partitions,
                "replication_factor": t.replication_factor,
                "retention_hours": t.retention_ms / (60 * 60 * 1000)
                if t.retention_ms > 0
                else "infinite",
                "compression": t.compression,
                "description": t.description,
            }
            for t in ALL_TOPICS
        ],
        "total_topics": len(ALL_TOPICS),
    }


@router.get("/kafka/stats")
async def kafka_stats():
    """Get Kafka producer/consumer statistics."""
    if not brain_engine.kafka:
        raise HTTPException(status_code=503, detail="Kafka not initialized")
    return brain_engine.kafka.get_stats()


@router.post("/kafka/produce-test")
async def kafka_produce_test():
    """Send a test message to the system health topic."""
    if not brain_engine.kafka:
        raise HTTPException(status_code=503, detail="Kafka not initialized")

    success = await brain_engine.kafka.produce(
        topic="stockpulse.system.health",
        key="test",
        value={
            "type": "health_check",
            "message": "Brain Kafka connectivity test",
        },
    )

    return {
        "success": success,
        "mode": "live" if brain_engine.kafka._connected else "stub",
    }


# ---------------------------------------------------------------------------
# Storage Layer
# ---------------------------------------------------------------------------

@router.get("/storage/status")
async def storage_status():
    """Get storage layer status."""
    if not brain_engine.minio_client:
        return {"status": "not_initialized", "message": "Storage layer not started"}

    return {
        "status": "connected" if brain_engine.minio_client._connected else "local_fallback",
        "mode": "minio" if brain_engine.minio_client._connected else "filesystem",
        "stats": brain_engine.minio_client._stats,
    }


# ---------------------------------------------------------------------------
# Ingestion Pipeline
# ---------------------------------------------------------------------------

@router.get("/ingestion/status")
async def ingestion_status():
    """Get ingestion pipeline status."""
    status = {
        "kafka_connected": bool(brain_engine.kafka and brain_engine.kafka._connected),
        "kafka_mode": "live" if (brain_engine.kafka and brain_engine.kafka._connected) else "stub",
        "data_quality_available": brain_engine.data_quality is not None,
        "normalizer_available": True,  # Always available (brain.ingestion.normalizer)
        "sources": {
            "yfinance": True,   # Always available
            "nse_bhavcopy": True,  # Extractor exists
            "dhan": False,      # Needs API credentials
            "groww": True,      # Extractor exists
            "screener": True,   # Extractor exists
        },
    }

    # Check Dhan credentials
    import os
    if os.getenv("DHAN_ACCESS_TOKEN") and os.getenv("DHAN_CLIENT_ID"):
        status["sources"]["dhan"] = True

    return status


# ---------------------------------------------------------------------------
# Phase 1 Summary
# ---------------------------------------------------------------------------

@router.get("/phase1/summary")
async def phase1_summary():
    """Get a comprehensive Phase 1 implementation summary."""
    return {
        "phase": "Phase 1: Data Foundation & Event Infrastructure",
        "status": "active",
        "components": {
            "kafka_event_bus": {
                "status": "stub_mode" if not (brain_engine.kafka and brain_engine.kafka._connected) else "connected",
                "description": "Event streaming backbone (KRaft mode, no ZooKeeper)",
                "topics_defined": len(ALL_TOPICS),
            },
            "feature_pipeline": {
                "status": "ready" if brain_engine.feature_pipeline else "not_initialized",
                "description": "Computes technical, fundamental, macro, cross-sectional features",
                "features_registered": brain_engine.feature_pipeline.registry.feature_count if brain_engine.feature_pipeline else 0,
            },
            "feature_store": {
                "status": "ready" if brain_engine.feature_store else "not_initialized",
                "description": "Redis+PostgreSQL feature store (MongoDB fallback in dev)",
                "mode": "mongodb_fallback",
            },
            "batch_scheduler": {
                "status": "running" if (brain_engine.batch_scheduler and brain_engine.batch_scheduler._running) else "stopped",
                "description": "Lightweight Airflow alternative for post-market batch DAGs",
                "dags": list(brain_engine.batch_scheduler._dags.keys()) if brain_engine.batch_scheduler else [],
            },
            "storage_layer": {
                "status": "ready" if brain_engine.minio_client else "not_initialized",
                "description": "MinIO/S3-compatible object storage for Parquet archival",
                "mode": "minio" if (brain_engine.minio_client and brain_engine.minio_client._connected) else "local_fallback",
            },
            "data_quality": {
                "status": "ready" if brain_engine.data_quality else "not_initialized",
                "description": "OHLCV integrity validation, circuit limit checks",
            },
            "ingestion": {
                "status": "ready",
                "description": "Data normalization from YFinance, Dhan, Groww, NSE Bhavcopy",
                "normalizer": True,
                "kafka_bridge": True,
            },
        },
        "api_endpoints": [
            "GET  /api/brain/health",
            "GET  /api/brain/features/{symbol}?compute=true",
            "POST /api/brain/features/compute",
            "POST /api/brain/features/batch",
            "GET  /api/brain/features/status",
            "GET  /api/brain/data-quality/{symbol}",
            "GET  /api/brain/batch/status",
            "GET  /api/brain/batch/history",
            "POST /api/brain/batch/trigger/{dag_name}",
            "GET  /api/brain/kafka/topics",
            "GET  /api/brain/storage/status",
            "GET  /api/brain/ingestion/status",
        ],
    }
