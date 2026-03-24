from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class RiskPolicy:
    max_position_notional: float = 2_000_000.0
    max_daily_loss_pct: float = 3.0
    max_sector_exposure_pct: float = 30.0
    allowed_sides: tuple = ("BUY", "SELL")


class RiskService:
    """Pre-trade risk checks for paper/live execution paths."""

    def __init__(self, policy: RiskPolicy | None = None):
        self.policy = policy or RiskPolicy()

    def pre_trade_check(
        self,
        order: Dict[str, Any],
        portfolio_state: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        portfolio_state = portfolio_state or {}
        checks: List[Dict[str, Any]] = []

        side = str(order.get("side", "")).upper()
        quantity = int(order.get("quantity", 0) or 0)
        price = float(order.get("price", 0) or 0)
        notional = quantity * price if price > 0 else 0.0

        checks.append(
            {
                "name": "valid_side",
                "passed": side in self.policy.allowed_sides,
                "message": "Side must be BUY or SELL",
            }
        )
        checks.append(
            {
                "name": "positive_quantity",
                "passed": quantity > 0,
                "message": "Quantity must be positive",
            }
        )
        checks.append(
            {
                "name": "max_position_notional",
                "passed": notional <= self.policy.max_position_notional,
                "message": f"Notional exceeds {self.policy.max_position_notional}",
                "value": notional,
            }
        )

        daily_loss_pct = float(portfolio_state.get("daily_loss_pct", 0.0) or 0.0)
        checks.append(
            {
                "name": "daily_loss_guard",
                "passed": daily_loss_pct < self.policy.max_daily_loss_pct,
                "message": f"Daily loss limit breached ({daily_loss_pct:.2f}%)",
            }
        )

        passed = all(c["passed"] for c in checks)
        return {"passed": passed, "checks": checks}
