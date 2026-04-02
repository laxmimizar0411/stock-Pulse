"""
Position Sizing Calculator with Kelly Criterion

Implements regime-aware position sizing using:
- Kelly Criterion for optimal bet sizing
- ATR-based stop losses
- Drawdown-based capital escalation rules

Capital Escalation Rules (from RiskConfig):
- 10% drawdown → halve all positions
- 15% drawdown → halt new entries
- 20% drawdown → kill all positions (100% cash)
"""

import logging
from typing import Dict, Optional

from brain.config import RiskConfig, get_brain_config
from brain.models.events import MarketRegime, SignalTimeframe

logger = logging.getLogger(__name__)


class PositionSizer:
    """
    Kelly Criterion-based position sizer with regime and drawdown awareness.
    
    Position size = Kelly fraction * Account * (Win rate * (1 + Reward/Risk) - 1) / (Reward/Risk)
    """
    
    def __init__(self, risk_config: Optional[RiskConfig] = None):
        """
        Args:
            risk_config: Risk configuration from BrainConfig
        """
        self.risk_config = risk_config or get_brain_config().risk
        
        # Current portfolio state
        self._account_value = 100000.0  # Default starting capital
        self._peak_value = 100000.0
        self._current_drawdown = 0.0
        self._positions_halved = False
        self._new_entries_halted = False
        self._kill_switch_active = False
    
    def calculate_position_size(
        self,
        signal_confidence: float,
        win_rate: float,
        risk_reward_ratio: float,
        entry_price: float,
        stop_loss: float,
        regime: Optional[MarketRegime] = None,
        timeframe: SignalTimeframe = SignalTimeframe.SWING,
    ) -> Dict:
        """
        Calculate optimal position size using Kelly Criterion.
        
        Args:
            signal_confidence: Signal confidence (0-100)
            win_rate: Historical win rate for this strategy (0-1)
            risk_reward_ratio: Expected reward/risk ratio
            entry_price: Entry price
            stop_loss: Stop loss price
            regime: Current market regime
            timeframe: Signal timeframe (day/swing/positional)
            
        Returns:
            Dict with:
            - position_size_pct: % of account to allocate
            - position_size_shares: Number of shares (if account_value set)
            - kelly_fraction: Kelly fraction used
            - max_position_size_pct: Max allowed by risk rules
            - capital_at_risk: Capital at risk per share
            - reason: Explanation of sizing decision
        """
        # Check kill switch
        if self._kill_switch_active:
            return {
                "position_size_pct": 0.0,
                "position_size_shares": 0,
                "kelly_fraction": 0.0,
                "max_position_size_pct": 0.0,
                "capital_at_risk": 0.0,
                "reason": "Kill switch active (20% drawdown reached)"
            }
        
        # Check halt on new entries
        if self._new_entries_halted:
            return {
                "position_size_pct": 0.0,
                "position_size_shares": 0,
                "kelly_fraction": 0.0,
                "max_position_size_pct": 0.0,
                "capital_at_risk": 0.0,
                "reason": "New entries halted (15% drawdown reached)"
            }
        
        # Get regime-specific Kelly fraction
        kelly_fraction = self._get_kelly_fraction(regime)
        
        # Calculate Kelly optimal percentage
        # Kelly % = Kelly fraction * ((Win rate * (1 + R/R)) - 1) / (R/R)
        if risk_reward_ratio <= 0 or win_rate <= 0:
            kelly_pct = 0.0
        else:
            kelly_numerator = (win_rate * (1 + risk_reward_ratio)) - 1
            kelly_pct = kelly_fraction * (kelly_numerator / risk_reward_ratio)
        
        # Adjust based on confidence (scale down if low confidence)
        confidence_multiplier = signal_confidence / 100.0
        kelly_pct *= confidence_multiplier
        
        # Apply position size limits
        max_position_pct = self.risk_config.max_single_position_pct
        kelly_pct = max(0.0, min(kelly_pct, max_position_pct))
        
        # Apply halving if 10% drawdown reached
        if self._positions_halved:
            kelly_pct *= 0.5
        
        # Calculate capital at risk per share
        capital_at_risk = abs(entry_price - stop_loss)
        
        # Calculate number of shares
        if capital_at_risk > 0:
            position_value = (kelly_pct / 100.0) * self._account_value
            shares = int(position_value / entry_price)
        else:
            shares = 0
        
        # Get ATR multiplier for this timeframe
        atr_multiplier = self._get_atr_multiplier(timeframe)
        
        return {
            "position_size_pct": round(kelly_pct, 2),
            "position_size_shares": shares,
            "kelly_fraction": kelly_fraction,
            "max_position_size_pct": max_position_pct,
            "capital_at_risk": round(capital_at_risk, 2),
            "atr_multiplier": atr_multiplier,
            "regime": regime.value if regime else "unknown",
            "drawdown_pct": round(self._current_drawdown * 100, 2),
            "positions_halved": self._positions_halved,
            "reason": self._get_sizing_reason(kelly_pct, confidence_multiplier, regime)
        }
    
    def _get_kelly_fraction(self, regime: Optional[MarketRegime]) -> float:
        """Get Kelly fraction based on regime."""
        if regime == MarketRegime.BEAR:
            return self.risk_config.kelly_fraction_bear  # 0.25 (Quarter Kelly)
        return self.risk_config.kelly_fraction  # 0.5 (Half Kelly)
    
    def _get_atr_multiplier(self, timeframe: SignalTimeframe) -> float:
        """Get ATR multiplier for stop loss calculation."""
        if timeframe == SignalTimeframe.INTRADAY:
            return self.risk_config.atr_multiplier_day  # 2.0
        elif timeframe == SignalTimeframe.SWING:
            return self.risk_config.atr_multiplier_swing  # 2.5
        elif timeframe == SignalTimeframe.POSITIONAL:
            return self.risk_config.atr_multiplier_positional  # 3.5
        return 2.5  # Default
    
    def _get_sizing_reason(self, kelly_pct: float, confidence_mult: float, regime: Optional[MarketRegime]) -> str:
        """Generate human-readable sizing explanation."""
        parts = []
        
        if kelly_pct == 0:
            parts.append("Position size zero")
        elif kelly_pct < 1:
            parts.append("Very small position (< 1%)")
        elif kelly_pct < 5:
            parts.append("Small position (1-5%)")
        elif kelly_pct < 10:
            parts.append("Medium position (5-10%)")
        else:
            parts.append("Large position (> 10%)")
        
        if confidence_mult < 0.5:
            parts.append("reduced due to low confidence")
        
        if regime == MarketRegime.BEAR:
            parts.append("using quarter Kelly (bear regime)")
        elif regime == MarketRegime.BULL:
            parts.append("using half Kelly (bull regime)")
        
        if self._positions_halved:
            parts.append("HALVED due to 10% drawdown")
        
        return " - ".join(parts) if parts else "Normal sizing"
    
    def update_account_value(self, new_value: float):
        """
        Update account value and check drawdown triggers.
        
        Args:
            new_value: Current account value
        """
        self._account_value = new_value
        
        # Update peak
        if new_value > self._peak_value:
            self._peak_value = new_value
            # Reset drawdown flags if new peak reached
            if self._positions_halved or self._new_entries_halted:
                logger.info("New equity peak reached - resetting drawdown flags")
                self._positions_halved = False
                self._new_entries_halted = False
                self._kill_switch_active = False
        
        # Calculate drawdown
        if self._peak_value > 0:
            self._current_drawdown = (self._peak_value - new_value) / self._peak_value
        else:
            self._current_drawdown = 0.0
        
        # Check drawdown rules
        self._apply_drawdown_rules()
    
    def _apply_drawdown_rules(self):
        """Apply capital escalation rules based on drawdown."""
        dd_pct = self._current_drawdown * 100
        
        # 20% drawdown → kill switch
        if dd_pct >= self.risk_config.drawdown_kill_pct and not self._kill_switch_active:
            self._kill_switch_active = True
            logger.critical(f"KILL SWITCH ACTIVATED: {dd_pct:.1f}% drawdown - closing all positions")
        
        # 15% drawdown → halt new entries
        elif dd_pct >= self.risk_config.drawdown_halt_pct and not self._new_entries_halted:
            self._new_entries_halted = True
            logger.warning(f"NEW ENTRIES HALTED: {dd_pct:.1f}% drawdown")
        
        # 10% drawdown → halve positions
        elif dd_pct >= self.risk_config.drawdown_halve_pct and not self._positions_halved:
            self._positions_halved = True
            logger.warning(f"POSITIONS HALVED: {dd_pct:.1f}% drawdown")
    
    def get_current_state(self) -> Dict:
        """Get current position sizing state."""
        return {
            "account_value": self._account_value,
            "peak_value": self._peak_value,
            "current_drawdown_pct": round(self._current_drawdown * 100, 2),
            "positions_halved": self._positions_halved,
            "new_entries_halted": self._new_entries_halted,
            "kill_switch_active": self._kill_switch_active,
            "kelly_fraction_default": self.risk_config.kelly_fraction,
            "kelly_fraction_bear": self.risk_config.kelly_fraction_bear,
            "max_single_position_pct": self.risk_config.max_single_position_pct,
        }
    
    def reset_drawdown_flags(self):
        """Manually reset drawdown flags (use with caution)."""
        self._positions_halved = False
        self._new_entries_halted = False
        self._kill_switch_active = False
        logger.info("Drawdown flags manually reset")
