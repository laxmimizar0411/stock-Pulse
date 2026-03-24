from typing import Any, Dict

from services.broker_adapters.paper_broker import PaperBrokerAdapter
from services.risk_service import RiskService


class OrderExecutionService:
    """Routes orders through risk checks then broker adapter."""

    def __init__(
        self,
        risk_service: RiskService | None = None,
        broker: PaperBrokerAdapter | None = None,
    ):
        self.risk_service = risk_service or RiskService()
        self.broker = broker or PaperBrokerAdapter()

    def place_order(
        self,
        order: Dict[str, Any],
        portfolio_state: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        risk_result = self.risk_service.pre_trade_check(order, portfolio_state=portfolio_state)
        if not risk_result["passed"]:
            return {
                "status": "rejected",
                "message": "Risk checks failed",
                "risk_checks": risk_result,
            }

        execution = self.broker.place_order(order)
        return {
            "status": "accepted",
            "message": "Order accepted by broker adapter",
            "risk_checks": risk_result,
            "execution": execution,
        }
