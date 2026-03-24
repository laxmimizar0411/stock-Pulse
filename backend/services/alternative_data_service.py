from datetime import datetime, timezone
from typing import Dict, Any


def build_alt_data_features(symbol: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Normalizes alternative-data payloads to a stable schema.
    """
    payload = payload or {}
    return {
        "symbol": symbol.upper(),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "google_trends_score": float(payload.get("google_trends_score", 0.0) or 0.0),
        "social_sentiment_score": float(payload.get("social_sentiment_score", 0.0) or 0.0),
        "regulatory_event_count_30d": int(payload.get("regulatory_event_count_30d", 0) or 0),
    }
