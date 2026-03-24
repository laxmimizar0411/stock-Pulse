"""
Brain API Routes — Health, status, and Kafka management endpoints.

These routes expose the Brain's health, configuration, and event system
status to the dashboard and monitoring tools.
"""

import logging
from fastapi import APIRouter, HTTPException

from brain.engine import brain_engine
from brain.events.topics import ALL_TOPICS, get_topic_names

logger = logging.getLogger("brain.routes")

router = APIRouter(prefix="/api/brain", tags=["Brain"])


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
    """
    Send a test message to the system health topic.
    Useful for verifying Kafka connectivity.
    """
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
        "mode": "live" if brain_engine.kafka.is_connected else "stub",
    }
