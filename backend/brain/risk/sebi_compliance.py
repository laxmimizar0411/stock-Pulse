"""SEBI Margin & Compliance Engine — Phase 3.4

Implements SEBI margin requirements for Indian equity trading:
1. VAR-based margin (as per SEBI circular)
2. Extreme Loss Margin (ELM)
3. Mark-to-Market (MTM) margin
4. Concentration margin for large positions
5. Delivery margin for T+1 settlement

Also checks:
- Position limits per SEBI rules
- Group-wise margin categories (Group I, II, III)
- Circuit breaker thresholds
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# SEBI margin categories by group
SEBI_MARGIN_GROUPS = {
    "group_1": {
        "name": "Group I (FnO)",
        "var_margin_pct": 10.0,
        "elm_pct": 3.5,
        "delivery_margin_pct": 20.0,
        "circuit_limit_pct": 20.0,
    },
    "group_2": {
        "name": "Group II",
        "var_margin_pct": 20.0,
        "elm_pct": 5.0,
        "delivery_margin_pct": 40.0,
        "circuit_limit_pct": 10.0,
    },
    "group_3": {
        "name": "Group III",
        "var_margin_pct": 35.0,
        "elm_pct": 5.0,
        "delivery_margin_pct": 75.0,
        "circuit_limit_pct": 5.0,
    },
}

# NIFTY 50 stocks are in Group I
GROUP_1_STOCKS = {
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR",
    "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT", "AXISBANK",
    "WIPRO", "HCLTECH", "ASIANPAINT", "MARUTI", "TITAN", "SUNPHARMA",
    "BAJFINANCE", "TATAMOTORS", "TATASTEEL", "NTPC", "POWERGRID",
    "ONGC", "TECHM", "ULTRACEMCO", "NESTLEIND", "DRREDDY",
    "ADANIENT", "ADANIPORTS", "BAJAJFINSV", "COALINDIA", "BRITANNIA",
    "CIPLA", "GRASIM", "DIVISLAB", "INDUSINDBK", "EICHERMOT",
    "HEROMOTOCO", "JSWSTEEL", "HINDALCO", "M&M",
}


@dataclass
class SEBIMarginResult:
    """SEBI margin calculation result."""
    symbol: str
    group: str
    trade_value: float = 0.0
    var_margin: float = 0.0
    elm_margin: float = 0.0
    total_initial_margin: float = 0.0
    delivery_margin: float = 0.0
    mtm_margin: float = 0.0
    concentration_margin: float = 0.0
    total_margin_required: float = 0.0
    margin_pct: float = 0.0
    circuit_limit_pct: float = 0.0
    compliant: bool = True
    violations: List[str] = field(default_factory=list)
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "group": self.group,
            "trade_value": round(self.trade_value, 2),
            "var_margin": round(self.var_margin, 2),
            "elm_margin": round(self.elm_margin, 2),
            "total_initial_margin": round(self.total_initial_margin, 2),
            "delivery_margin": round(self.delivery_margin, 2),
            "mtm_margin": round(self.mtm_margin, 2),
            "concentration_margin": round(self.concentration_margin, 2),
            "total_margin_required": round(self.total_margin_required, 2),
            "margin_pct": round(self.margin_pct, 4),
            "circuit_limit_pct": self.circuit_limit_pct,
            "compliant": self.compliant,
            "violations": self.violations,
            "computed_at": self.computed_at.isoformat(),
        }


class SEBIComplianceEngine:
    """SEBI margin and compliance checks."""

    def __init__(self):
        self._stats = {"checks": 0, "violations": 0}

    def _get_group(self, symbol: str) -> str:
        sym = symbol.upper().replace(".NS", "").replace(".BSE", "")
        if sym in GROUP_1_STOCKS:
            return "group_1"
        return "group_2"  # Default to Group II for unknown stocks

    def calculate_margin(
        self,
        symbol: str,
        trade_value: float,
        is_delivery: bool = True,
        current_price: float = 0.0,
        prev_close: float = 0.0,
        portfolio_value: float = 0.0,
    ) -> SEBIMarginResult:
        """Calculate SEBI-mandated margin requirements."""
        group = self._get_group(symbol)
        group_config = SEBI_MARGIN_GROUPS[group]

        result = SEBIMarginResult(
            symbol=symbol,
            group=group_config["name"],
            trade_value=trade_value,
            circuit_limit_pct=group_config["circuit_limit_pct"],
        )

        # 1. VAR Margin
        result.var_margin = trade_value * group_config["var_margin_pct"] / 100

        # 2. Extreme Loss Margin (ELM)
        result.elm_margin = trade_value * group_config["elm_pct"] / 100

        # 3. Total Initial Margin = VAR + ELM
        result.total_initial_margin = result.var_margin + result.elm_margin

        # 4. Delivery Margin (for delivery trades)
        if is_delivery:
            result.delivery_margin = trade_value * group_config["delivery_margin_pct"] / 100

        # 5. Mark-to-Market Margin (if price available)
        if current_price > 0 and prev_close > 0:
            price_change = abs(current_price - prev_close) / prev_close
            quantity = trade_value / current_price if current_price > 0 else 0
            result.mtm_margin = quantity * abs(current_price - prev_close)

        # 6. Concentration Margin (if position > 10% of portfolio)
        if portfolio_value > 0:
            concentration = trade_value / portfolio_value
            if concentration > 0.10:
                result.concentration_margin = trade_value * 0.05  # Additional 5%

        # Total
        result.total_margin_required = (
            result.total_initial_margin +
            result.delivery_margin +
            result.mtm_margin +
            result.concentration_margin
        )
        result.margin_pct = result.total_margin_required / trade_value if trade_value > 0 else 0

        # Compliance checks
        result.violations = []

        # Check circuit breaker
        if current_price > 0 and prev_close > 0:
            change_pct = abs((current_price - prev_close) / prev_close) * 100
            if change_pct >= group_config["circuit_limit_pct"]:
                result.violations.append(
                    f"Circuit breaker: price changed {change_pct:.1f}% "
                    f"(limit: {group_config['circuit_limit_pct']}%)"
                )

        # Check concentration limit
        if portfolio_value > 0:
            conc = trade_value / portfolio_value
            if conc > 0.20:  # SEBI concentration limit
                result.violations.append(
                    f"Concentration: {conc*100:.1f}% of portfolio (limit: 20%)"
                )

        result.compliant = len(result.violations) == 0

        self._stats["checks"] += 1
        if not result.compliant:
            self._stats["violations"] += 1

        return result

    def get_stats(self) -> Dict[str, Any]:
        return self._stats
