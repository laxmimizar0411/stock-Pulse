"""
Stop-Loss Engine

ATR-volatility hybrid stop-loss computation with regime-adaptive multipliers
and Chandelier Exit trailing stops.
"""

import logging
from typing import Any, Dict, Optional

from brain.config import get_brain_config
from brain.models.events import MarketRegime

logger = logging.getLogger(__name__)


class StopLossEngine:
    """
    Computes stop-loss and trailing stop levels using ATR-based methods.

    The hybrid ATR-volatility stop:
        Stop = Entry - (ATR(14) * Multiplier)

    Multiplier varies by timeframe and regime:
    - Day trading: 1.5-2x (tighter)
    - Swing: 2-3x
    - Positional: 3-4x
    - Bear regime: wider multipliers for more room

    Research shows 2x ATR stops reduce max drawdown by ~32% vs fixed % stops.
    """

    def __init__(self):
        self._config = get_brain_config().risk

    def compute_stop_loss(
        self,
        entry_price: float,
        atr: float,
        direction: str = "BUY",
        timeframe: str = "swing",
        regime: Optional[MarketRegime] = None,
    ) -> Dict[str, float]:
        """
        Compute stop-loss level.

        Args:
            entry_price: Entry price
            atr: ATR(14) value
            direction: "BUY" or "SELL"
            timeframe: "intraday", "swing", "positional", "investment"
            regime: Current market regime

        Returns:
            Dict with stop_loss, atr_multiplier, risk_amount, risk_pct
        """
        if atr <= 0 or entry_price <= 0:
            # Fallback to percentage-based
            pct = 0.05 if direction == "BUY" else 0.05
            stop = entry_price * (1 - pct) if direction == "BUY" else entry_price * (1 + pct)
            return {
                "stop_loss": round(stop, 2),
                "atr_multiplier": 0,
                "risk_amount": round(abs(entry_price - stop), 2),
                "risk_pct": round(pct * 100, 2),
                "method": "percentage_fallback",
            }

        multiplier = self._get_multiplier(timeframe, regime)

        if direction == "BUY":
            stop_loss = entry_price - (atr * multiplier)
            # Floor: never more than 8% from entry
            floor = entry_price * 0.92
            stop_loss = max(stop_loss, floor)
        else:
            stop_loss = entry_price + (atr * multiplier)
            # Ceiling: never more than 8% from entry
            ceiling = entry_price * 1.08
            stop_loss = min(stop_loss, ceiling)

        risk_amount = abs(entry_price - stop_loss)
        risk_pct = (risk_amount / entry_price) * 100

        return {
            "stop_loss": round(stop_loss, 2),
            "atr_multiplier": multiplier,
            "atr_value": round(atr, 2),
            "risk_amount": round(risk_amount, 2),
            "risk_pct": round(risk_pct, 2),
            "method": "atr_hybrid",
        }

    def compute_trailing_stop(
        self,
        highest_price_since_entry: float,
        atr: float,
        direction: str = "BUY",
        timeframe: str = "swing",
        regime: Optional[MarketRegime] = None,
    ) -> float:
        """
        Compute Chandelier Exit trailing stop.

        Chandelier Exit: Highest_High_Since_Entry - ATR * Multiplier

        The trailing stop only moves in the favorable direction.
        """
        multiplier = self._get_multiplier(timeframe, regime)

        if direction == "BUY":
            return round(highest_price_since_entry - (atr * multiplier), 2)
        else:
            return round(highest_price_since_entry + (atr * multiplier), 2)

    def compute_target_price(
        self,
        entry_price: float,
        stop_loss: float,
        risk_reward_ratio: float = 2.5,
        direction: str = "BUY",
    ) -> float:
        """Compute target price based on risk-reward ratio."""
        risk = abs(entry_price - stop_loss)
        reward = risk * risk_reward_ratio

        if direction == "BUY":
            return round(entry_price + reward, 2)
        else:
            return round(entry_price - reward, 2)

    def _get_multiplier(
        self, timeframe: str, regime: Optional[MarketRegime]
    ) -> float:
        """Get ATR multiplier based on timeframe and regime."""
        base_multipliers = {
            "intraday": self._config.atr_multiplier_day,
            "swing": self._config.atr_multiplier_swing,
            "positional": self._config.atr_multiplier_positional,
            "investment": self._config.atr_multiplier_positional + 0.5,
        }

        multiplier = base_multipliers.get(timeframe, self._config.atr_multiplier_swing)

        # Regime adjustment
        if regime == MarketRegime.BEAR:
            multiplier *= 1.3  # wider stops in bear market
        elif regime == MarketRegime.BULL:
            multiplier *= 0.9  # tighter stops in bull market (protect profits)

        return round(multiplier, 2)
