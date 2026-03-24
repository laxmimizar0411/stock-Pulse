"""
Capital Protection Engine

Implements escalating protection measures based on portfolio drawdown:
- 10% drawdown → halve position sizes
- 15% drawdown → halt all new entries
- 20% drawdown → close all positions (kill switch)
- Daily loss cap at 2-3% of capital
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from brain.config import get_brain_config
from brain.models.events import RiskBreachEvent

logger = logging.getLogger(__name__)


class ProtectionLevel(str, Enum):
    NORMAL = "NORMAL"
    REDUCED = "REDUCED"          # 10% drawdown: halve positions
    HALTED = "HALTED"            # 15% drawdown: no new entries
    EMERGENCY = "EMERGENCY"      # 20% drawdown: close all


class CapitalProtectionEngine:
    """
    Escalating capital protection based on drawdown levels.

    The engine monitors portfolio drawdown and daily P&L,
    automatically adjusting position sizing and blocking
    new entries when thresholds are breached.
    """

    def __init__(self):
        self._config = get_brain_config().risk
        self._current_level = ProtectionLevel.NORMAL
        self._peak_value: float = 0.0
        self._daily_pnl: float = 0.0
        self._breach_history: List[Dict[str, Any]] = []

    @property
    def current_level(self) -> ProtectionLevel:
        return self._current_level

    @property
    def position_size_multiplier(self) -> float:
        """Multiplier applied to position sizes based on protection level."""
        multipliers = {
            ProtectionLevel.NORMAL: 1.0,
            ProtectionLevel.REDUCED: 0.5,
            ProtectionLevel.HALTED: 0.0,
            ProtectionLevel.EMERGENCY: 0.0,
        }
        return multipliers[self._current_level]

    @property
    def new_entries_allowed(self) -> bool:
        return self._current_level in (ProtectionLevel.NORMAL, ProtectionLevel.REDUCED)

    def update(
        self,
        portfolio_value: float,
        daily_pnl: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Update protection state with current portfolio value.

        Args:
            portfolio_value: Current portfolio value
            daily_pnl: Today's P&L (positive or negative)

        Returns:
            Current protection status and any breach events
        """
        breaches = []

        # Track peak
        if portfolio_value > self._peak_value:
            self._peak_value = portfolio_value

        # Compute drawdown
        drawdown_pct = 0.0
        if self._peak_value > 0:
            drawdown_pct = ((self._peak_value - portfolio_value) / self._peak_value) * 100

        # Update daily P&L
        self._daily_pnl = daily_pnl
        daily_pnl_pct = (daily_pnl / portfolio_value) * 100 if portfolio_value > 0 else 0

        # Check drawdown escalation
        previous_level = self._current_level

        if drawdown_pct >= self._config.drawdown_kill_pct:
            self._current_level = ProtectionLevel.EMERGENCY
            if previous_level != ProtectionLevel.EMERGENCY:
                breaches.append(self._create_breach(
                    "drawdown_kill_switch",
                    "EMERGENCY",
                    drawdown_pct,
                    self._config.drawdown_kill_pct,
                    "ALL POSITIONS CLOSED - 20% drawdown kill switch activated",
                ))
        elif drawdown_pct >= self._config.drawdown_halt_pct:
            self._current_level = ProtectionLevel.HALTED
            if previous_level not in (ProtectionLevel.HALTED, ProtectionLevel.EMERGENCY):
                breaches.append(self._create_breach(
                    "drawdown_halt",
                    "CRITICAL",
                    drawdown_pct,
                    self._config.drawdown_halt_pct,
                    "NEW ENTRIES HALTED - 15% drawdown threshold breached",
                ))
        elif drawdown_pct >= self._config.drawdown_halve_pct:
            self._current_level = ProtectionLevel.REDUCED
            if previous_level == ProtectionLevel.NORMAL:
                breaches.append(self._create_breach(
                    "drawdown_reduce",
                    "WARNING",
                    drawdown_pct,
                    self._config.drawdown_halve_pct,
                    "POSITIONS HALVED - 10% drawdown threshold breached",
                ))
        else:
            self._current_level = ProtectionLevel.NORMAL

        # Check daily loss cap
        if daily_pnl_pct < -self._config.daily_loss_cap_pct:
            if self._current_level == ProtectionLevel.NORMAL:
                self._current_level = ProtectionLevel.HALTED
            breaches.append(self._create_breach(
                "daily_loss_cap",
                "CRITICAL",
                abs(daily_pnl_pct),
                self._config.daily_loss_cap_pct,
                f"DAILY LOSS CAP BREACHED - Lost {abs(daily_pnl_pct):.1f}% today",
            ))

        # Log breaches
        for breach in breaches:
            self._breach_history.append(breach)
            logger.warning("Capital protection breach: %s", breach["action_taken"])

        return {
            "protection_level": self._current_level.value,
            "drawdown_pct": round(drawdown_pct, 2),
            "peak_value": round(self._peak_value, 2),
            "current_value": round(portfolio_value, 2),
            "daily_pnl": round(daily_pnl, 2),
            "daily_pnl_pct": round(daily_pnl_pct, 2),
            "position_size_multiplier": self.position_size_multiplier,
            "new_entries_allowed": self.new_entries_allowed,
            "breaches": breaches,
            "thresholds": {
                "halve_at": self._config.drawdown_halve_pct,
                "halt_at": self._config.drawdown_halt_pct,
                "kill_at": self._config.drawdown_kill_pct,
                "daily_cap": self._config.daily_loss_cap_pct,
            },
        }

    def reset(self, new_peak: float = 0.0):
        """Reset protection state (e.g., after manual review)."""
        self._current_level = ProtectionLevel.NORMAL
        self._peak_value = new_peak
        self._daily_pnl = 0.0
        logger.info("Capital protection reset to NORMAL, peak=%.2f", new_peak)

    def get_breach_history(self) -> List[Dict[str, Any]]:
        return self._breach_history[-50:]  # Last 50 breaches

    def _create_breach(
        self, breach_type: str, severity: str, current: float, threshold: float, action: str
    ) -> Dict[str, Any]:
        return {
            "breach_type": breach_type,
            "severity": severity,
            "current_value": round(current, 2),
            "threshold": threshold,
            "action_taken": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "protection_level": self._current_level.value,
        }
