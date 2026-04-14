"""
Combined Black-Litterman + HRP Optimizer

Two-step optimization:
1. Black-Litterman generates view-driven weights
2. HRP overlay adjusts weights to cap correlation exposure
"""

import logging
from typing import List, Dict, Optional, Any
import numpy as np
from datetime import datetime, timezone

from .black_litterman import BlackLittermanOptimizer
from .hrp_optimizer import HRPOptimizer

logger = logging.getLogger(__name__)


class CombinedOptimizer:
    """
    Combined BL+HRP portfolio optimizer.
    
    Strategy:
    1. Black-Litterman: Generate weights based on AI views
    2. HRP: Adjust weights to respect risk clustering
    3. Blend: Combine both approaches (default 70% BL, 30% HRP)
    
    Benefits:
    - View-driven allocation (BL)
    - Risk diversification (HRP)
    - Caps correlation exposure
    - Robust to estimation error
    """
    
    def __init__(
        self,
        bl_weight: float = 0.7,
        hrp_weight: float = 0.3,
        risk_free_rate: float = 0.065,
        market_risk_premium: float = 0.08
    ):
        """
        Initialize combined optimizer.
        
        Args:
            bl_weight: Weight for BL allocation (default: 0.7)
            hrp_weight: Weight for HRP allocation (default: 0.3)
            risk_free_rate: Risk-free rate
            market_risk_premium: Market risk premium
        """
        if abs(bl_weight + hrp_weight - 1.0) > 1e-6:
            raise ValueError("bl_weight + hrp_weight must equal 1.0")
        
        self.bl_weight = bl_weight
        self.hrp_weight = hrp_weight
        
        self.bl_optimizer = BlackLittermanOptimizer(
            risk_free_rate=risk_free_rate,
            market_risk_premium=market_risk_premium
        )
        self.hrp_optimizer = HRPOptimizer()
    
    def optimize_combined(
        self,
        symbols: List[str],
        market_cap_weights: np.ndarray,
        correlation_matrix: np.ndarray,
        covariance_matrix: np.ndarray,
        forecasts: Dict[str, float],
        sentiment_scores: Optional[Dict[str, float]] = None,
        risk_metrics: Optional[Dict[str, float]] = None,
        constraints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run combined BL+HRP optimization.
        
        Args:
            symbols: Stock symbols
            market_cap_weights: Market cap weights
            correlation_matrix: Correlation matrix
            covariance_matrix: Covariance matrix
            forecasts: AI-generated forecasts
            sentiment_scores: Sentiment scores
            risk_metrics: Risk metrics
            constraints: Portfolio constraints
            
        Returns:
            Combined portfolio weights and analytics
        """
        logger.info("Running combined BL+HRP optimization...")
        
        # 1. Black-Litterman optimization
        bl_result = self.bl_optimizer.run_black_litterman(
            symbols=symbols,
            market_cap_weights=market_cap_weights,
            covariance_matrix=covariance_matrix,
            forecasts=forecasts,
            sentiment_scores=sentiment_scores,
            risk_metrics=risk_metrics,
            constraints=constraints
        )
        
        bl_weights = np.array(bl_result["weights"])
        
        # 2. HRP optimization
        hrp_result = self.hrp_optimizer.optimize(
            correlation_matrix=correlation_matrix,
            covariance_matrix=covariance_matrix,
            symbols=symbols
        )
        
        hrp_weights = np.array(hrp_result["weights"])
        
        # 3. Combine weights
        combined_weights = (
            self.bl_weight * bl_weights +
            self.hrp_weight * hrp_weights
        )
        
        # Normalize
        combined_weights = combined_weights / np.sum(combined_weights)
        
        # 4. Apply constraints to combined weights
        if constraints:
            combined_weights = self._apply_constraints(combined_weights, constraints)
        
        # 5. Compute portfolio statistics
        portfolio_return = combined_weights @ np.array(bl_result["posterior_returns"])
        portfolio_variance = combined_weights @ covariance_matrix @ combined_weights
        portfolio_std = np.sqrt(portfolio_variance)
        
        sharpe_ratio = (portfolio_return - self.bl_optimizer.risk_free_rate) / portfolio_std if portfolio_std > 0 else 0
        
        # 6. Compute diversification metrics
        diversification_ratio = self._compute_diversification_ratio(
            combined_weights,
            covariance_matrix
        )
        
        effective_n = self._compute_effective_n(combined_weights)
        
        return {
            "symbols": symbols,
            "weights": combined_weights.tolist(),
            "allocation": {
                symbol: float(weight)
                for symbol, weight in zip(symbols, combined_weights)
            },
            "bl_weights": bl_weights.tolist(),
            "hrp_weights": hrp_weights.tolist(),
            "bl_contribution": self.bl_weight,
            "hrp_contribution": self.hrp_weight,
            "expected_return_annual": float(portfolio_return * 252),
            "volatility_annual": float(portfolio_std * np.sqrt(252)),
            "sharpe_ratio": float(sharpe_ratio * np.sqrt(252)),
            "diversification_ratio": float(diversification_ratio),
            "effective_n_stocks": float(effective_n),
            "max_weight": float(np.max(combined_weights)),
            "min_weight": float(np.min(combined_weights[combined_weights > 0])) if np.any(combined_weights > 0) else 0.0,
            "views_count": bl_result["views_count"],
            "computed_at": datetime.now(timezone.utc).isoformat()
        }
    
    def _apply_constraints(
        self,
        weights: np.ndarray,
        constraints: Dict[str, Any]
    ) -> np.ndarray:
        """Apply portfolio constraints to weights."""
        max_weight = constraints.get('max_weight', 1.0)
        min_weight = constraints.get('min_weight', 0.0)
        
        # Clip weights
        weights = np.clip(weights, min_weight, max_weight)
        
        # Renormalize
        weights = weights / np.sum(weights)
        
        return weights
    
    def _compute_diversification_ratio(
        self,
        weights: np.ndarray,
        covariance_matrix: np.ndarray
    ) -> float:
        """
        Compute diversification ratio.
        
        DR = (weighted average of volatilities) / (portfolio volatility)
        
        Higher is better (more diversified).
        """
        # Individual volatilities
        individual_vols = np.sqrt(np.diag(covariance_matrix))
        
        # Weighted average volatility
        weighted_avg_vol = weights @ individual_vols
        
        # Portfolio volatility
        portfolio_vol = np.sqrt(weights @ covariance_matrix @ weights)
        
        if portfolio_vol > 0:
            dr = weighted_avg_vol / portfolio_vol
        else:
            dr = 1.0
        
        return dr
    
    def _compute_effective_n(self, weights: np.ndarray) -> float:
        """
        Compute effective number of stocks (Herfindahl index).
        
        Effective N = 1 / sum(w_i^2)
        
        Ranges from 1 (concentrated) to N (equal weight).
        """
        effective_n = 1.0 / np.sum(weights ** 2)
        return effective_n
    
    def compare_strategies(
        self,
        symbols: List[str],
        market_cap_weights: np.ndarray,
        correlation_matrix: np.ndarray,
        covariance_matrix: np.ndarray,
        forecasts: Dict[str, float],
        sentiment_scores: Optional[Dict[str, float]] = None,
        risk_metrics: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Compare BL, HRP, and Combined strategies side-by-side.
        
        Returns:
            Comparison of all three strategies
        """
        # Run all three optimizations
        bl_result = self.bl_optimizer.run_black_litterman(
            symbols, market_cap_weights, covariance_matrix,
            forecasts, sentiment_scores, risk_metrics
        )
        
        hrp_result = self.hrp_optimizer.optimize(
            correlation_matrix, covariance_matrix, symbols
        )
        
        combined_result = self.optimize_combined(
            symbols, market_cap_weights, correlation_matrix,
            covariance_matrix, forecasts, sentiment_scores, risk_metrics
        )
        
        return {
            "strategies": {
                "black_litterman": {
                    "weights": bl_result["allocation"],
                    "expected_return": bl_result["expected_return_annual"],
                    "volatility": bl_result["volatility_annual"],
                    "sharpe_ratio": bl_result["sharpe_ratio"]
                },
                "hrp": {
                    "weights": hrp_result["allocation"],
                    "volatility": hrp_result["volatility_annual"]
                },
                "combined_bl_hrp": {
                    "weights": combined_result["allocation"],
                    "expected_return": combined_result["expected_return_annual"],
                    "volatility": combined_result["volatility_annual"],
                    "sharpe_ratio": combined_result["sharpe_ratio"],
                    "diversification_ratio": combined_result["diversification_ratio"],
                    "effective_n_stocks": combined_result["effective_n_stocks"]
                }
            },
            "recommendation": self._select_best_strategy(bl_result, combined_result),
            "computed_at": datetime.now(timezone.utc).isoformat()
        }
    
    def _select_best_strategy(
        self,
        bl_result: Dict[str, Any],
        combined_result: Dict[str, Any]
    ) -> str:
        """Select best strategy based on Sharpe ratio."""
        bl_sharpe = bl_result["sharpe_ratio"]
        combined_sharpe = combined_result["sharpe_ratio"]
        
        if combined_sharpe > bl_sharpe * 1.1:  # 10% improvement
            return "combined_bl_hrp"
        elif bl_sharpe > combined_sharpe * 1.1:
            return "black_litterman"
        else:
            return "combined_bl_hrp"  # Default to combined for diversification
