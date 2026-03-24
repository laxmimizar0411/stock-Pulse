import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


class EventBusService:
    """
    Lightweight event bus abstraction.
    This is intentionally provider-agnostic so Kafka/NATS can be attached later.
    """

    def __init__(self):
        self._enabled = False

    def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        event = {
            "topic": topic,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        logger.info("event_bus_publish %s", json.dumps(event, default=str))

    def health(self) -> Dict[str, Any]:
        return {"enabled": self._enabled, "mode": "log_only"}
