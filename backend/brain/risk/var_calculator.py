"""Value at Risk (VaR) & CVaR Calculator — Phase 3.4

Three VaR methodologies:
1. Historical VaR — Empirical quantile of historical returns
2. Parametric VaR — Assumes normal distribution (μ, σ)
3. Monte Carlo VaR — Simulated return paths (10,000 scenarios)

Plus Conditional VaR (CVaR / Expected Shortfall):
  Average loss beyond VaR threshold.

All computations for Indian equities with INR denomination.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VaRResult:
    """Result of VaR computation."""
    symbol: str
    method: str  # "historical", "parametric", "monte_carlo"
    confidence_level: float = 0.95  # 95% confidence
    var_1d: float = 0.0  # 1-day VaR as fraction of portfolio
    var_10d: float = 0.0  # 10-day VaR
    cvar_1d: float = 0.0  # Conditional VaR (Expected Shortfall)
    cvar_10d: float = 0.0
    var_inr: float = 0.0  # VaR in INR (if portfolio value given)
    portfolio_value: float = 0.0
    n_observations: int = 0
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "method": self.method,
            "confidence_level": self.confidence_level,
            "var_1d": round(self.var_1d, 6),
            "var_10d": round(self.var_10d, 6),
            "cvar_1d": round(self.cvar_1d, 6),
            "cvar_10d": round(self.cvar_10d, 6),
            "var_1d_pct": round(self.var_1d * 100, 4),
            "var_10d_pct": round(self.var_10d * 100, 4),
            "cvar_1d_pct": round(self.cvar_1d * 100, 4),
            "cvar_10d_pct": round(self.cvar_10d * 100, 4),
            "var_inr": round(self.var_inr, 2),
            "portfolio_value": self.portfolio_value,
            "n_observations": self.n_observations,
            "computed_at": self.computed_at.isoformat(),
        }


def historical_var(
    returns: np.ndarray,
    confidence: float = 0.95,
) -> tuple:
    """Historical VaR & CVaR."""
    if len(returns) < 10:
        return 0.0, 0.0
    alpha = 1 - confidence
    var = -np.percentile(returns, alpha * 100)
    tail = returns[returns <= -var]
    cvar = -np.mean(tail) if len(tail) > 0 else var
    return float(var), float(cvar)


def parametric_var(
    returns: np.ndarray,
    confidence: float = 0.95,
) -> tuple:
    """Parametric (variance-covariance) VaR & CVaR assuming normal distribution."""
    if len(returns) < 10:
        return 0.0, 0.0
    from scipy import stats
    mu = np.mean(returns)
    sigma = np.std(returns, ddof=1)
    z = stats.norm.ppf(1 - confidence)
    var = -(mu + z * sigma)
    # CVaR for normal: μ + σ * φ(z) / (1-α)
    alpha = 1 - confidence
    cvar = -(mu - sigma * stats.norm.pdf(z) / alpha)
    return float(max(0, var)), float(max(0, cvar))


def monte_carlo_var(
    returns: np.ndarray,
    confidence: float = 0.95,
    n_simulations: int = 10000,
    horizon_days: int = 1,
) -> tuple:
    """Monte Carlo VaR & CVaR."""
    if len(returns) < 10:
        return 0.0, 0.0
    mu = np.mean(returns)
    sigma = np.std(returns, ddof=1)
    rng = np.random.default_rng(42)
    sim = rng.normal(mu * horizon_days, sigma * math.sqrt(horizon_days), n_simulations)
    alpha = 1 - confidence
    var = -np.percentile(sim, alpha * 100)
    tail = sim[sim <= -var]
    cvar = -np.mean(tail) if len(tail) > 0 else var
    return float(max(0, var)), float(max(0, cvar))


class VaRCalculator:
    """Multi-method VaR calculator for Indian equities."""

    def __init__(self, confidence: float = 0.95, mc_simulations: int = 10000):
        self._confidence = confidence
        self._mc_simulations = mc_simulations
        self._stats = {"calculations": 0}

    def calculate(
        self,
        symbol: str,
        returns: np.ndarray,
        portfolio_value: float = 1000000.0,
    ) -> Dict[str, VaRResult]:
        """Calculate VaR using all three methods."""
        results = {}
        sqrt_10 = math.sqrt(10)

        for method, fn in [
            ("historical", lambda r: historical_var(r, self._confidence)),
            ("parametric", lambda r: parametric_var(r, self._confidence)),
            ("monte_carlo", lambda r: monte_carlo_var(r, self._confidence, self._mc_simulations)),
        ]:
            try:
                var_1d, cvar_1d = fn(returns)
                result = VaRResult(
                    symbol=symbol,
                    method=method,
                    confidence_level=self._confidence,
                    var_1d=var_1d,
                    var_10d=var_1d * sqrt_10,
                    cvar_1d=cvar_1d,
                    cvar_10d=cvar_1d * sqrt_10,
                    var_inr=var_1d * portfolio_value,
                    portfolio_value=portfolio_value,
                    n_observations=len(returns),
                )
                results[method] = result
            except Exception as e:
                logger.error(f"VaR {method} failed for {symbol}: {e}")

        self._stats["calculations"] += 1
        return results

    def get_stats(self) -> Dict[str, Any]:
        return self._stats
