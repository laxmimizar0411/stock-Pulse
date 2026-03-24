"""
Position Sizing Engine

Implements Fractional Kelly Criterion with regime-adaptive sizing
and volatility-adjusted position limits.

Half Kelly (default) captures ~75% of optimal growth with dramatically
reduced drawdown compared to full Kelly which can produce 50-70% drawdowns.
"""

import logging
import math
from typing import Any, Dict, Optional

from brain.config import get_brain_config
from brain.models.events import MarketRegime

logger = logging.getLogger(__name__)


class PositionSizer:
    """
    Computes optimal position sizes using Fractional Kelly Criterion.

    Kelly formula: K% = W - (1-W)/R
    where W = win probability, R = reward/risk ratio

    We use Half Kelly (K/2) by default, Quarter Kelly (K/4) in bear regime.
    """

    def __init__(self):
        self._config = get_brain_config().risk

    def compute_position_size(
        self,
        portfolio_value: float,
        entry_price: float,
        stop_loss: float,
        win_probability: float = 0.55,
        avg_win_loss_ratio: float = 1.5,
        regime: Optional[MarketRegime] = None,
        sector_current_exposure_pct: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Compute optimal position size.

        Args:
            portfolio_value: Total portfolio value in INR
            entry_price: Entry price per share
            stop_loss: Stop-loss price per share
            win_probability: Historical win rate (0-1)
            avg_win_loss_ratio: Average win / average loss
            regime: Current market regime
            sector_current_exposure_pct: Current sector exposure %

        Returns:
            Dict with shares, investment_amount, position_pct, kelly_fraction, etc.
        """
        if portfolio_value <= 0 or entry_price <= 0:
            return self._empty_result("invalid inputs")

        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            return self._empty_result("stop_loss equals entry_price")

        # Kelly Criterion
        kelly_pct = self._kelly_criterion(win_probability, avg_win_loss_ratio)

        # Apply fractional Kelly based on regime
        if regime == MarketRegime.BEAR:
            fraction = self._config.kelly_fraction_bear  # Quarter Kelly
        else:
            fraction = self._config.kelly_fraction  # Half Kelly

        adjusted_kelly = kelly_pct * fraction

        # Risk amount = portfolio * adjusted kelly %
        risk_amount = portfolio_value * adjusted_kelly

        # Shares from risk-based sizing: shares = risk_amount / risk_per_share
        shares_from_risk = int(risk_amount / risk_per_share)

        # Investment amount
        investment = shares_from_risk * entry_price
        position_pct = (investment / portfolio_value) * 100

        # Apply position limits
        max_position_pct = self._config.max_single_position_pct
        if position_pct > max_position_pct:
            investment = portfolio_value * (max_position_pct / 100)
            shares_from_risk = int(investment / entry_price)
            position_pct = max_position_pct

        # Check sector concentration
        max_sector_pct = self._config.max_sector_concentration_pct
        remaining_sector_room = max_sector_pct - sector_current_exposure_pct
        if position_pct > remaining_sector_room and remaining_sector_room > 0:
            position_pct = remaining_sector_room
            investment = portfolio_value * (position_pct / 100)
            shares_from_risk = int(investment / entry_price)

        # Ensure at least 1 share if we have a valid signal
        shares = max(shares_from_risk, 0)
        actual_investment = shares * entry_price
        actual_risk = shares * risk_per_share
        actual_position_pct = (actual_investment / portfolio_value) * 100 if portfolio_value > 0 else 0

        return {
            "shares": shares,
            "investment_amount": round(actual_investment, 2),
            "position_pct": round(actual_position_pct, 2),
            "risk_amount": round(actual_risk, 2),
            "risk_pct_of_portfolio": round((actual_risk / portfolio_value) * 100, 2) if portfolio_value > 0 else 0,
            "kelly_raw_pct": round(kelly_pct * 100, 2),
            "kelly_fraction": fraction,
            "kelly_adjusted_pct": round(adjusted_kelly * 100, 2),
            "risk_per_share": round(risk_per_share, 2),
            "regime": regime.value if regime else "unknown",
            "constraints_applied": {
                "max_position_limit": position_pct >= max_position_pct,
                "sector_concentration_limit": sector_current_exposure_pct + actual_position_pct >= max_sector_pct,
            },
        }

    def _kelly_criterion(self, win_prob: float, win_loss_ratio: float) -> float:
        """
        Compute Kelly Criterion percentage.

        K% = W - (1-W)/R
        where W = win probability, R = reward/risk ratio

        Returns a value between 0 and 1.
        """
        if win_loss_ratio <= 0:
            return 0.0

        kelly = win_prob - (1 - win_prob) / win_loss_ratio

        # Kelly can be negative (don't trade) or very high (dangerous)
        return max(0.0, min(kelly, 0.5))  # Cap at 50% even before fractional

    def compute_risk_per_trade(
        self,
        portfolio_value: float,
        regime: Optional[MarketRegime] = None,
    ) -> Dict[str, float]:
        """
        Compute maximum risk per trade.

        Standard: 1-2% of portfolio per trade.
        Bear regime: 0.5-1% per trade.
        """
        if regime == MarketRegime.BEAR:
            risk_pct = 0.01  # 1% in bear
        elif regime == MarketRegime.BULL:
            risk_pct = 0.02  # 2% in bull
        else:
            risk_pct = 0.015  # 1.5% default

        risk_amount = portfolio_value * risk_pct

        return {
            "risk_per_trade_pct": round(risk_pct * 100, 2),
            "risk_per_trade_amount": round(risk_amount, 2),
            "daily_loss_cap_pct": self._config.daily_loss_cap_pct,
            "daily_loss_cap_amount": round(portfolio_value * self._config.daily_loss_cap_pct / 100, 2),
        }

    def _empty_result(self, reason: str) -> Dict[str, Any]:
        return {
            "shares": 0,
            "investment_amount": 0,
            "position_pct": 0,
            "risk_amount": 0,
            "error": reason,
        }
