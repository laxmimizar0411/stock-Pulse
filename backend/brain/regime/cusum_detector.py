"""
CUSUM Change-Point Detection for Market Regime Transitions

Detects structural breaks in market behavior using CUmulative SUM (CUSUM) statistics.
Useful for identifying regime transitions in real-time without requiring full retraining.

Algorithm:
- Monitors cumulative sum of deviations from historical mean
- Triggers regime change when CUSUM exceeds threshold
- Provides early warning of regime shifts

References:
- Page, E.S. (1954). "Continuous Inspection Schemes"
- Basseville, M. & Nikiforov, I.V. (1993). "Detection of Abrupt Changes"
"""

import logging
from collections import deque
from typing import Dict, Optional, Tuple

import numpy as np

from brain.models.events import MarketRegime

logger = logging.getLogger(__name__)


class CUSUMDetector:
    """
    CUSUM-based change-point detector for regime transitions.
    
    Monitors daily returns and volatility for structural breaks that indicate
    regime changes. Provides real-time alerts without requiring model retraining.
    """
    
    def __init__(
        self,
        window_size: int = 50,
        threshold_multiplier: float = 4.0,
        drift: float = 0.5,
    ):
        """
        Args:
            window_size: Number of observations for baseline statistics
            threshold_multiplier: CUSUM threshold = threshold_multiplier * std(baseline)
            drift: Drift term to reduce sensitivity (typically 0.5 * std)
        """
        self.window_size = window_size
        self.threshold_multiplier = threshold_multiplier
        self.drift = drift
        
        # Rolling windows for returns and volatility
        self._return_window = deque(maxlen=window_size)
        self._volatility_window = deque(maxlen=window_size)
        
        # CUSUM statistics
        self._cusum_high_return = 0.0
        self._cusum_low_return = 0.0
        self._cusum_high_vol = 0.0
        
        # Baseline statistics
        self._baseline_return_mean = 0.0
        self._baseline_return_std = 1.0
        self._baseline_vol_mean = 1.0
        self._baseline_vol_std = 0.5
        
        # Current regime
        self._current_regime = MarketRegime.SIDEWAYS
        self._change_points: list = []
        
        self._initialized = False
    
    def update(self, daily_return: float, volatility: float) -> Tuple[bool, Optional[str]]:
        """
        Update CUSUM statistics with new observation.
        
        Args:
            daily_return: Daily return (e.g., 0.02 for +2%)
            volatility: Rolling volatility (e.g., 0.015 for 1.5% daily vol)
            
        Returns:
            Tuple of (change_detected, change_type)
            - change_detected: True if regime transition detected
            - change_type: "return_increase", "return_decrease", "volatility_spike", or None
        """
        # Add to rolling windows
        self._return_window.append(daily_return)
        self._volatility_window.append(volatility)
        
        # Initialize baseline statistics once we have enough data
        if not self._initialized and len(self._return_window) >= self.window_size:
            self._compute_baseline_statistics()
            self._initialized = True
        
        if not self._initialized:
            return False, None
        
        # Compute CUSUM statistics
        change_detected, change_type = self._update_cusum(daily_return, volatility)
        
        # Reset CUSUM if change detected
        if change_detected:
            self._cusum_high_return = 0.0
            self._cusum_low_return = 0.0
            self._cusum_high_vol = 0.0
            self._compute_baseline_statistics()  # Update baseline
            self._change_points.append({
                "change_type": change_type,
                "cusum_value": max(abs(self._cusum_high_return), abs(self._cusum_low_return), abs(self._cusum_high_vol))
            })
        
        return change_detected, change_type
    
    def _compute_baseline_statistics(self):
        """Compute mean and std for baseline period."""
        returns = np.array(self._return_window)
        volatilities = np.array(self._volatility_window)
        
        self._baseline_return_mean = np.mean(returns)
        self._baseline_return_std = np.std(returns)
        if self._baseline_return_std < 1e-6:
            self._baseline_return_std = 0.01  # Prevent division by zero
        
        self._baseline_vol_mean = np.mean(volatilities)
        self._baseline_vol_std = np.std(volatilities)
        if self._baseline_vol_std < 1e-6:
            self._baseline_vol_std = 0.005
        
        logger.debug(
            f"CUSUM baseline: return_mean={self._baseline_return_mean:.4f}, "
            f"return_std={self._baseline_return_std:.4f}, "
            f"vol_mean={self._baseline_vol_mean:.4f}"
        )
    
    def _update_cusum(self, daily_return: float, volatility: float) -> Tuple[bool, Optional[str]]:
        """Update CUSUM statistics and detect changes."""
        # Standardize observations
        return_z = (daily_return - self._baseline_return_mean) / self._baseline_return_std
        vol_z = (volatility - self._baseline_vol_mean) / self._baseline_vol_std
        
        # Update CUSUM for returns (detect mean shifts)
        self._cusum_high_return = max(0, self._cusum_high_return + return_z - self.drift)
        self._cusum_low_return = min(0, self._cusum_low_return + return_z + self.drift)
        
        # Update CUSUM for volatility (detect variance increases)
        self._cusum_high_vol = max(0, self._cusum_high_vol + vol_z - self.drift)
        
        # Check thresholds
        threshold = self.threshold_multiplier
        
        if abs(self._cusum_high_return) > threshold:
            logger.info(f"CUSUM detected return increase: {self._cusum_high_return:.2f}")
            return True, "return_increase"
        
        if abs(self._cusum_low_return) > threshold:
            logger.info(f"CUSUM detected return decrease: {self._cusum_low_return:.2f}")
            return True, "return_decrease"
        
        if abs(self._cusum_high_vol) > threshold:
            logger.info(f"CUSUM detected volatility spike: {self._cusum_high_vol:.2f}")
            return True, "volatility_spike"
        
        return False, None
    
    def suggest_regime(self, change_type: Optional[str] = None) -> MarketRegime:
        """
        Suggest regime based on recent change-point detection.
        
        Args:
            change_type: Type of change detected
            
        Returns:
            Suggested MarketRegime
        """
        if change_type == "return_increase":
            return MarketRegime.BULL
        elif change_type == "return_decrease":
            return MarketRegime.BEAR
        elif change_type == "volatility_spike":
            # High volatility often indicates bearish or transitional regime
            return MarketRegime.BEAR
        
        # No change or no signal → default to current regime
        return self._current_regime
    
    def get_current_regime(self) -> MarketRegime:
        """Get the current regime tracked by CUSUM."""
        return self._current_regime
    
    def set_current_regime(self, regime: MarketRegime):
        """Update the current regime."""
        self._current_regime = regime
    
    def get_statistics(self) -> Dict:
        """Get current CUSUM statistics for monitoring."""
        return {
            "initialized": self._initialized,
            "window_size": len(self._return_window),
            "cusum_high_return": float(self._cusum_high_return),
            "cusum_low_return": float(self._cusum_low_return),
            "cusum_high_vol": float(self._cusum_high_vol),
            "baseline_return_mean": float(self._baseline_return_mean),
            "baseline_return_std": float(self._baseline_return_std),
            "baseline_vol_mean": float(self._baseline_vol_mean),
            "change_points_detected": len(self._change_points),
            "current_regime": self._current_regime.value,
        }
    
    def reset(self):
        """Reset CUSUM detector (useful after confirmed regime change)."""
        self._cusum_high_return = 0.0
        self._cusum_low_return = 0.0
        self._cusum_high_vol = 0.0
        self._return_window.clear()
        self._volatility_window.clear()
        self._initialized = False
        logger.info("CUSUM detector reset")
