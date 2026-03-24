from datetime import datetime, timezone
from typing import Any, Dict
import uuid


class PaperBrokerAdapter:
    """Simple paper broker adapter for simulated order flow."""

    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        order_id = f"paper_{uuid.uuid4().hex[:12]}"
        return {
            "order_id": order_id,
            "status": "accepted",
            "filled_qty": int(order.get("quantity", 0) or 0),
            "avg_fill_price": float(order.get("price", 0) or 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "broker": "paper",
        }
