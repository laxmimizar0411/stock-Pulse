"""
Portfolio Risk Analytics

Computes Value at Risk (VaR), Conditional VaR (Expected Shortfall),
maximum drawdown, and Monte Carlo portfolio simulation.
"""

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class PortfolioRiskAnalyzer:
    """
    Portfolio-level risk metrics computation.

    Methods:
    - Historical VaR
    - Parametric VaR (Variance-Covariance)
    - Monte Carlo VaR
    - CVaR (Expected Shortfall)
    - Maximum Drawdown
    """

    def compute_var_historical(
        self,
        returns: np.ndarray,
        confidence: float = 0.95,
    ) -> float:
        """
        Historical simulation VaR.

        Simply takes the percentile of actual returns.
        """
        if len(returns) < 10:
            return 0.0
        return float(-np.percentile(returns, (1 - confidence) * 100))

    def compute_var_parametric(
        self,
        returns: np.ndarray,
        confidence: float = 0.95,
    ) -> float:
        """
        Parametric (Variance-Covariance) VaR.

        Assumes normally distributed returns.
        VaR = -( mu + z * sigma )
        """
        if len(returns) < 10:
            return 0.0

        mu = np.mean(returns)
        sigma = np.std(returns, ddof=1)

        # Z-score for confidence level
        from scipy.stats import norm
        z = norm.ppf(1 - confidence)

        return float(-(mu + z * sigma))

    def compute_var_monte_carlo(
        self,
        returns: np.ndarray,
        confidence: float = 0.95,
        n_simulations: int = 10000,
        horizon_days: int = 1,
    ) -> float:
        """
        Monte Carlo VaR using bootstrapped returns.
        """
        if len(returns) < 10:
            return 0.0

        mu = np.mean(returns)
        sigma = np.std(returns, ddof=1)

        # Simulate future returns
        rng = np.random.default_rng(42)
        simulated = rng.normal(mu * horizon_days, sigma * math.sqrt(horizon_days), n_simulations)

        return float(-np.percentile(simulated, (1 - confidence) * 100))

    def compute_cvar(
        self,
        returns: np.ndarray,
        confidence: float = 0.95,
    ) -> float:
        """
        Conditional VaR (Expected Shortfall).

        Average of losses beyond VaR threshold.
        """
        if len(returns) < 10:
            return 0.0

        var = self.compute_var_historical(returns, confidence)
        tail_losses = returns[returns < -var]

        if len(tail_losses) == 0:
            return var

        return float(-np.mean(tail_losses))

    def compute_max_drawdown(
        self,
        portfolio_values: np.ndarray,
    ) -> Dict[str, float]:
        """
        Compute maximum drawdown and duration.

        Returns max drawdown %, peak, trough, and duration in periods.
        """
        if len(portfolio_values) < 2:
            return {"max_drawdown_pct": 0.0, "duration": 0}

        cummax = np.maximum.accumulate(portfolio_values)
        drawdowns = (portfolio_values - cummax) / cummax

        max_dd = float(np.min(drawdowns))
        max_dd_idx = int(np.argmin(drawdowns))

        # Find peak before max drawdown
        peak_idx = int(np.argmax(portfolio_values[:max_dd_idx + 1])) if max_dd_idx > 0 else 0

        # Find recovery (if any)
        peak_value = portfolio_values[peak_idx]
        recovery_idx = None
        for i in range(max_dd_idx, len(portfolio_values)):
            if portfolio_values[i] >= peak_value:
                recovery_idx = i
                break

        duration = (recovery_idx - peak_idx) if recovery_idx else (len(portfolio_values) - peak_idx)

        return {
            "max_drawdown_pct": round(abs(max_dd) * 100, 2),
            "peak_idx": peak_idx,
            "trough_idx": max_dd_idx,
            "recovery_idx": recovery_idx,
            "duration_periods": duration,
            "current_drawdown_pct": round(abs(float(drawdowns[-1])) * 100, 2),
        }

    def compute_portfolio_metrics(
        self,
        returns: np.ndarray,
        portfolio_values: Optional[np.ndarray] = None,
        risk_free_rate: float = 0.07,
    ) -> Dict[str, float]:
        """
        Comprehensive portfolio risk metrics.

        Args:
            returns: Daily return series
            portfolio_values: Portfolio value series (for drawdown)
            risk_free_rate: Annual risk-free rate (default 7% for India FD rate)
        """
        if len(returns) < 20:
            return {"error": "insufficient data", "n_observations": len(returns)}

        daily_rf = risk_free_rate / 252

        # VaR
        var_95 = self.compute_var_historical(returns, 0.95)
        var_99 = self.compute_var_historical(returns, 0.99)
        cvar_95 = self.compute_cvar(returns, 0.95)

        # Returns
        mean_daily = float(np.mean(returns))
        annualized_return = mean_daily * 252
        annualized_vol = float(np.std(returns, ddof=1)) * math.sqrt(252)

        # Sharpe Ratio
        sharpe = (annualized_return - risk_free_rate) / annualized_vol if annualized_vol > 0 else 0

        # Sortino Ratio (downside deviation only)
        downside_returns = returns[returns < daily_rf]
        downside_std = float(np.std(downside_returns, ddof=1)) * math.sqrt(252) if len(downside_returns) > 1 else annualized_vol
        sortino = (annualized_return - risk_free_rate) / downside_std if downside_std > 0 else 0

        # Drawdown
        dd_metrics = {}
        if portfolio_values is not None and len(portfolio_values) >= 2:
            dd_metrics = self.compute_max_drawdown(portfolio_values)
        else:
            # Reconstruct from returns
            cumulative = np.cumprod(1 + returns)
            dd_metrics = self.compute_max_drawdown(cumulative)

        # Calmar Ratio
        max_dd = dd_metrics.get("max_drawdown_pct", 0) / 100
        calmar = annualized_return / max_dd if max_dd > 0 else 0

        # Win rate
        winning_days = np.sum(returns > 0)
        total_days = len(returns)
        win_rate = float(winning_days / total_days) if total_days > 0 else 0

        # Profit factor
        gross_profit = float(np.sum(returns[returns > 0]))
        gross_loss = float(abs(np.sum(returns[returns < 0])))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        return {
            "var_95_daily": round(var_95 * 100, 3),
            "var_99_daily": round(var_99 * 100, 3),
            "cvar_95_daily": round(cvar_95 * 100, 3),
            "annualized_return_pct": round(annualized_return * 100, 2),
            "annualized_volatility_pct": round(annualized_vol * 100, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "calmar_ratio": round(calmar, 3),
            "max_drawdown_pct": dd_metrics.get("max_drawdown_pct", 0),
            "current_drawdown_pct": dd_metrics.get("current_drawdown_pct", 0),
            "win_rate": round(win_rate * 100, 1),
            "profit_factor": round(profit_factor, 3),
            "n_observations": len(returns),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
