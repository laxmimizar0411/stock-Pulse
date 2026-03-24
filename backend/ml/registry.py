from datetime import datetime, timezone
from typing import Any, Dict
import uuid

_registry: Dict[str, Dict[str, Any]] = {}


def register_model_version(model_name: str, metrics: Dict[str, float]) -> str:
    version = f"{model_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    _registry[version] = {
        "model_name": model_name,
        "metrics": metrics,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    return version


def get_model_registry() -> Dict[str, Dict[str, Any]]:
    return _registry
