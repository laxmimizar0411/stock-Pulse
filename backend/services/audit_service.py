import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


def emit_audit_event(actor: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload, sort_keys=True, default=str)
    payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "payload_hash": payload_hash,
    }
    logger.info("audit_event %s", json.dumps(event))
    return event
