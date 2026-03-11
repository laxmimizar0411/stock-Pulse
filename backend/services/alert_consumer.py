"""
Alert Queue Consumer for StockPulse

Background task that consumes alerts from the Redis alert_queue (LIST)
using BLPOP and processes them (e.g., logging, future notification dispatch).

Usage:
    from services.alert_consumer import start_alert_consumer, stop_alert_consumer

    # Start during app startup
    await start_alert_consumer()

    # Stop during app shutdown
    await stop_alert_consumer()
"""

import asyncio
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_consumer_task: Optional[asyncio.Task] = None
_running = False

ALERT_QUEUE_KEY = "alert_queue"
BLPOP_TIMEOUT = 5  # seconds to wait per BLPOP cycle


async def _consume_alerts():
    """Background loop that BLPOPs from alert_queue and processes alerts."""
    global _running

    try:
        import redis as redis_lib
    except ImportError:
        logger.warning("redis package not installed, alert consumer disabled")
        return

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

    # Create a dedicated Redis connection for blocking operations
    try:
        r = redis_lib.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=BLPOP_TIMEOUT + 2,
        )
        r.ping()
        logger.info("Alert consumer connected to Redis")
    except Exception as e:
        logger.warning(f"Alert consumer: Redis not available ({e}), consumer disabled")
        return

    _running = True
    while _running:
        try:
            # BLPOP blocks until an item is available or timeout expires
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: r.blpop(ALERT_QUEUE_KEY, timeout=BLPOP_TIMEOUT)
            )
            if result is None:
                # Timeout, no alert — loop again
                continue

            _key, raw_payload = result
            try:
                alert = json.loads(raw_payload)
            except json.JSONDecodeError:
                logger.warning(f"Alert consumer: invalid JSON in queue: {raw_payload[:200]}")
                continue

            # Process the alert
            _process_alert(alert)

        except asyncio.CancelledError:
            logger.info("Alert consumer cancelled")
            break
        except Exception as e:
            logger.warning(f"Alert consumer error: {e}")
            # Brief pause before retrying on unexpected errors
            await asyncio.sleep(2)

    try:
        r.close()
    except Exception:
        pass
    logger.info("Alert consumer stopped")


def _process_alert(alert: dict):
    """
    Process a single alert from the queue.

    Currently logs the alert. Extend this to dispatch notifications
    (email, push, WebSocket, etc.) when notification channels are implemented.
    """
    alert_type = alert.get("type", "unknown")
    symbol = alert.get("symbol", "N/A")
    message = alert.get("message", "")
    logger.info(f"Alert processed: type={alert_type} symbol={symbol} msg={message}")


async def start_alert_consumer():
    """Start the alert consumer background task."""
    global _consumer_task
    if _consumer_task is not None and not _consumer_task.done():
        logger.debug("Alert consumer already running")
        return
    _consumer_task = asyncio.create_task(_consume_alerts())
    logger.info("Alert consumer background task started")


async def stop_alert_consumer():
    """Stop the alert consumer background task."""
    global _running, _consumer_task
    _running = False
    if _consumer_task is not None:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass
        _consumer_task = None
    logger.info("Alert consumer background task stopped")
