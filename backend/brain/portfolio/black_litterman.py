"""
Black-Litterman Portfolio Optimizer

Combines market equilibrium returns with AI-generated views from:
1. Chronos/TimesFM forecasts → expected return views
2. Sentiment scores → confidence adjustment
3. Risk metrics → view uncertainty
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class BlackLittermanOptimizer:
    """
    Black-Litterman model with AI-generated views.
    
    Combines:
    - Market equilibrium (CAPM-based implied returns)
    - AI views (forecast-based expected returns)
    - View confidence (sentiment-adjusted)
    - View uncertainty (risk-adjusted)
    
    Output: Posterior expected returns for mean-variance optimization.
    """
    
    def __init__(
        self,
        risk_free_rate: float = 0.065,  # 6.5% (India 10Y bond)
        market_risk_premium: float = 0.08,  # 8% equity risk premium
        tau: float = 0.025  # Scaling factor for uncertainty (2.5% of covariance)
    ):
        """
        Initialize Black-Litterman optimizer.
        
        Args:
            risk_free_rate: Risk-free rate (default: 6.5% India 10Y)
            market_risk_premium: Market risk premium (default: 8%)
            tau: Uncertainty scaling factor (default: 0.025)
        """
        self.risk_free_rate = risk_free_rate
        self.market_risk_premium = market_risk_premium
        self.tau = tau
        
    def compute_market_equilibrium_returns(
        self,
        market_cap_weights: np.ndarray,
        covariance_matrix: np.ndarray,
        risk_aversion: float = 2.5
    ) -> np.ndarray:
        """
        Compute implied equilibrium returns using reverse optimization.
        
        Formula: π = δ * Σ * w_mkt
        
        Args:
            market_cap_weights: Market capitalization weights
            covariance_matrix: Covariance matrix of returns
            risk_aversion: Risk aversion parameter (default: 2.5)
            
        Returns:
            Equilibrium expected returns
        """
        # Π = δ * Σ * w
        equilibrium_returns = risk_aversion * covariance_matrix @ market_cap_weights
        
        return equilibrium_returns
    
    def generate_views_from_forecasts(
        self,
        symbols: List[str],
        forecasts: Dict[str, float],
        sentiment_scores: Optional[Dict[str, float]] = None,
        risk_metrics: Optional[Dict[str, float]] = None
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate Black-Litterman views from AI forecasts.
        
        Args:
            symbols: List of stock symbols
            forecasts: Dictionary of {symbol: expected_return_pct}
            sentiment_scores: Dictionary of {symbol: sentiment_score} (-1 to 1)
            risk_metrics: Dictionary of {symbol: volatility or VaR}
            
        Returns:
            Tuple of (P matrix, Q vector, Omega matrix)
            - P: View picking matrix (k x n)
            - Q: View portfolio expected returns (k x 1)
            - Omega: View uncertainty matrix (k x k)
        """
        n_assets = len(symbols)
        views = []
        view_returns = []
        view_uncertainties = []
        
        for i, symbol in enumerate(symbols):
            if symbol in forecasts:
                # Absolute view: Asset i has expected return Q_i
                P_row = np.zeros(n_assets)
                P_row[i] = 1.0
                views.append(P_row)
                
                # Expected return from forecast (convert % to decimal)
                expected_return = forecasts[symbol] / 100.0
                view_returns.append(expected_return)
                
                # View confidence based on sentiment
                if sentiment_scores and symbol in sentiment_scores:
                    sentiment = sentiment_scores[symbol]
                    # Sentiment ranges -1 to 1, map to confidence 0.5 to 1.5
                    confidence = 1.0 + 0.5 * sentiment
                else:
                    confidence = 1.0
                
                # View uncertainty based on risk
                if risk_metrics and symbol in risk_metrics:
                    volatility = risk_metrics[symbol]
                    # Higher volatility = higher uncertainty
                    uncertainty = volatility ** 2
                else:
                    # Default uncertainty: 10% standard deviation
                    uncertainty = 0.10 ** 2
                
                # Adjust uncertainty by confidence
                # Higher confidence = lower uncertainty
                adjusted_uncertainty = uncertainty / confidence
                view_uncertainties.append(adjusted_uncertainty)
        
        if not views:
            # No views available, return empty
            return None, None, None
        
        # Construct matrices
        P = np.array(views)  # k x n
        Q = np.array(view_returns)  # k x 1
        Omega = np.diag(view_uncertainties)  # k x k
        
        return P, Q, Omega
    
    def compute_posterior_returns(
        self,
        equilibrium_returns: np.ndarray,
        covariance_matrix: np.ndarray,
        P: np.ndarray,
        Q: np.ndarray,
        Omega: np.ndarray
    ) -> np.ndarray:
        """
        Compute Black-Litterman posterior returns.
        
        Formula:
        E[R] = [(τΣ)^-1 + P'Ω^-1P]^-1 [(τΣ)^-1 π + P'Ω^-1 Q]
        
        Args:
            equilibrium_returns: Market equilibrium returns (π)
            covariance_matrix: Covariance matrix (Σ)
            P: View picking matrix
            Q: View returns vector
            Omega: View uncertainty matrix
            
        Returns:
            Posterior expected returns
        """
        # τΣ
        tau_sigma = self.tau * covariance_matrix
        
        # (τΣ)^-1
        tau_sigma_inv = np.linalg.inv(tau_sigma)
        
        # Ω^-1
        omega_inv = np.linalg.inv(Omega)
        
        # P'Ω^-1P
        middle_term = P.T @ omega_inv @ P
        
        # [(τΣ)^-1 + P'Ω^-1P]^-1
        posterior_variance_inv = tau_sigma_inv + middle_term
        posterior_variance = np.linalg.inv(posterior_variance_inv)
        
        # (τΣ)^-1 π
        equilibrium_term = tau_sigma_inv @ equilibrium_returns
        
        # P'Ω^-1 Q
        view_term = P.T @ omega_inv @ Q
        
        # Posterior returns
        posterior_returns = posterior_variance @ (equilibrium_term + view_term)
        
        return posterior_returns
    
    def optimize_portfolio(
        self,
        expected_returns: np.ndarray,
        covariance_matrix: np.ndarray,
        constraints: Optional[Dict[str, Any]] = None
    ) -> np.ndarray:
        """
        Mean-variance optimization given expected returns.
        
        Args:
            expected_returns: Expected returns vector
            covariance_matrix: Covariance matrix
            constraints: Portfolio constraints (e.g., max weight, min weight)
            
        Returns:
            Optimal portfolio weights
        """
        n_assets = len(expected_returns)
        
        # Objective: Maximize Sharpe ratio (or minimize negative Sharpe)
        def objective(weights):
            portfolio_return = weights @ expected_returns
            portfolio_variance = weights @ covariance_matrix @ weights
            portfolio_std = np.sqrt(portfolio_variance)
            
            # Sharpe ratio
            sharpe = (portfolio_return - self.risk_free_rate) / portfolio_std if portfolio_std > 0 else 0
            return -sharpe  # Minimize negative Sharpe
        
        # Constraints
        constraints_list = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}  # Weights sum to 1
        ]
        
        # Bounds: 0 <= weight <= max_weight
        max_weight = constraints.get('max_weight', 0.25) if constraints else 0.25
        min_weight = constraints.get('min_weight', 0.0) if constraints else 0.0
        bounds = tuple((min_weight, max_weight) for _ in range(n_assets))
        
        # Initial guess: equal weight
        x0 = np.ones(n_assets) / n_assets
        
        # Optimize
        result = minimize(
            objective,
            x0,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints_list,
            options={'maxiter': 1000}
        )
        
        if not result.success:
            logger.warning(f"Optimization did not converge: {result.message}")
        
        weights = result.x
        
        # Normalize to ensure sum = 1
        weights = weights / np.sum(weights)
        
        return weights
    
    def run_black_litterman(
        self,
        symbols: List[str],
        market_cap_weights: np.ndarray,
        covariance_matrix: np.ndarray,
        forecasts: Dict[str, float],
        sentiment_scores: Optional[Dict[str, float]] = None,
        risk_metrics: Optional[Dict[str, float]] = None,
        constraints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Complete Black-Litterman workflow.
        
        Args:
            symbols: List of stock symbols
            market_cap_weights: Market cap weights
            covariance_matrix: Covariance matrix
            forecasts: AI-generated return forecasts
            sentiment_scores: Sentiment scores for confidence
            risk_metrics: Risk metrics for uncertainty
            constraints: Portfolio constraints
            
        Returns:
            Dictionary with weights and analytics
        """
        # 1. Compute equilibrium returns
        equilibrium_returns = self.compute_market_equilibrium_returns(
            market_cap_weights,
            covariance_matrix
        )
        
        # 2. Generate views from AI forecasts
        P, Q, Omega = self.generate_views_from_forecasts(
            symbols,
            forecasts,
            sentiment_scores,
            risk_metrics
        )
        
        if P is None:
            # No views available, use equilibrium
            logger.warning("No views available, using equilibrium returns")
            posterior_returns = equilibrium_returns
        else:
            # 3. Compute posterior returns
            posterior_returns = self.compute_posterior_returns(
                equilibrium_returns,
                covariance_matrix,
                P,
                Q,
                Omega
            )
        
        # 4. Optimize portfolio
        optimal_weights = self.optimize_portfolio(
            posterior_returns,
            covariance_matrix,
            constraints
        )
        
        # 5. Compute portfolio statistics
        portfolio_return = optimal_weights @ posterior_returns
        portfolio_variance = optimal_weights @ covariance_matrix @ optimal_weights
        portfolio_std = np.sqrt(portfolio_variance)
        sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_std if portfolio_std > 0 else 0
        
        return {
            "symbols": symbols,
            "weights": optimal_weights.tolist(),
            "allocation": {
                symbol: float(weight)
                for symbol, weight in zip(symbols, optimal_weights)
            },
            "equilibrium_returns": equilibrium_returns.tolist(),
            "posterior_returns": posterior_returns.tolist(),
            "expected_return_annual": float(portfolio_return * 252),  # Annualized
            "volatility_annual": float(portfolio_std * np.sqrt(252)),
            "sharpe_ratio": float(sharpe_ratio * np.sqrt(252)),  # Annualized
            "views_count": len(Q) if Q is not None else 0,
            "computed_at": datetime.now(timezone.utc).isoformat()
        }
