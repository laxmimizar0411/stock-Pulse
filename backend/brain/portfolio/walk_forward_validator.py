"""
Walk-Forward Validator

Rolling train/test validation for portfolio strategies.
Target: Sharpe ratio > 2.0
"""

import logging
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class WalkForwardValidator:
    """
    Walk-forward validation for portfolio optimization.
    
    Strategy:
    - Rolling 12-month train / 1-month test
    - Monthly retraining
    - Out-of-sample performance tracking
    
    Target: Sharpe ratio > 2.0
    """
    
    def __init__(
        self,
        train_months: int = 12,
        test_months: int = 1,
        target_sharpe: float = 2.0
    ):
        """
        Initialize walk-forward validator.
        
        Args:
            train_months: Training window in months
            test_months: Test window in months  
            target_sharpe: Target Sharpe ratio (annualized)
        """
        self.train_months = train_months
        self.test_months = test_months
        self.target_sharpe = target_sharpe
    
    def validate_portfolio(
        self,
        returns_df: pd.DataFrame,
        weights: np.ndarray,
        test_start_idx: int,
        test_end_idx: int
    ) -> Dict[str, Any]:
        """
        Validate portfolio on out-of-sample test period.
        
        Args:
            returns_df: DataFrame of stock returns (rows=dates, cols=stocks)
            weights: Portfolio weights
            test_start_idx: Test period start index
            test_end_idx: Test period end index
            
        Returns:
            Performance metrics
        """
        # Extract test period returns
        test_returns = returns_df.iloc[test_start_idx:test_end_idx]
        
        # Compute portfolio returns
        portfolio_returns = (test_returns @ weights).values
        
        # Performance metrics
        mean_return = np.mean(portfolio_returns)
        std_return = np.std(portfolio_returns)
        
        # Annualized metrics (assuming daily returns)
        annual_return = mean_return * 252
        annual_vol = std_return * np.sqrt(252)
        sharpe = annual_return / annual_vol if annual_vol > 0 else 0
        
        # Cumulative return
        cumulative_return = np.prod(1 + portfolio_returns) - 1
        
        # Max drawdown
        cumulative_wealth = np.cumprod(1 + portfolio_returns)
        running_max = np.maximum.accumulate(cumulative_wealth)
        drawdown = (cumulative_wealth - running_max) / running_max
        max_drawdown = np.min(drawdown)
        
        return {
            "annual_return": float(annual_return),
            "annual_volatility": float(annual_vol),
            "sharpe_ratio": float(sharpe),
            "cumulative_return": float(cumulative_return),
            "max_drawdown": float(max_drawdown),
            "days_tested": len(portfolio_returns),
            "meets_target": sharpe >= self.target_sharpe
        }
    
    def run_walk_forward(
        self,
        returns_df: pd.DataFrame,
        optimizer_func: callable,
        optimizer_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run walk-forward validation.
        
        Args:
            returns_df: DataFrame of returns
            optimizer_func: Function that returns optimal weights
            optimizer_params: Parameters for optimizer
            
        Returns:
            Walk-forward results
        """
        n_periods = len(returns_df)
        train_days = self.train_months * 21  # Approximate trading days
        test_days = self.test_months * 21
        
        results = []
        
        # Rolling windows
        current_idx = train_days
        while current_idx + test_days <= n_periods:
            # Train period
            train_start = current_idx - train_days
            train_end = current_idx
            train_data = returns_df.iloc[train_start:train_end]
            
            # Optimize on train data
            try:
                weights = optimizer_func(train_data, **optimizer_params)
                
                # Test period
                test_start = train_end
                test_end = test_start + test_days
                
                # Validate
                metrics = self.validate_portfolio(
                    returns_df,
                    weights,
                    test_start,
                    test_end
                )
                
                metrics["train_start_date"] = returns_df.index[train_start]
                metrics["train_end_date"] = returns_df.index[train_end - 1]
                metrics["test_start_date"] = returns_df.index[test_start]
                metrics["test_end_date"] = returns_df.index[test_end - 1]
                
                results.append(metrics)
                
            except Exception as e:
                logger.error(f"Walk-forward iteration failed: {str(e)}")
            
            # Move to next test period
            current_idx += test_days
        
        if not results:
            return {
                "total_iterations": 0,
                "avg_sharpe": 0,
                "meets_target_pct": 0
            }
        
        # Aggregate results
        sharpe_ratios = [r["sharpe_ratio"] for r in results]
        annual_returns = [r["annual_return"] for r in results]
        max_drawdowns = [r["max_drawdown"] for r in results]
        
        return {
            "total_iterations": len(results),
            "avg_sharpe_ratio": float(np.mean(sharpe_ratios)),
            "median_sharpe_ratio": float(np.median(sharpe_ratios)),
            "min_sharpe_ratio": float(np.min(sharpe_ratios)),
            "max_sharpe_ratio": float(np.max(sharpe_ratios)),
            "avg_annual_return": float(np.mean(annual_returns)),
            "avg_max_drawdown": float(np.mean(max_drawdowns)),
            "meets_target_pct": float(np.sum([r["meets_target"] for r in results]) / len(results) * 100),
            "target_sharpe": self.target_sharpe,
            "train_months": self.train_months,
            "test_months": self.test_months,
            "detailed_results": results,
            "computed_at": datetime.now(timezone.utc).isoformat()
        }
    
    def get_summary_statistics(
        self,
        walk_forward_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get summary statistics from walk-forward results."""
        return {
            "total_test_periods": walk_forward_results["total_iterations"],
            "average_sharpe_ratio": walk_forward_results["avg_sharpe_ratio"],
            "target_sharpe_ratio": walk_forward_results["target_sharpe"],
            "meets_target": walk_forward_results["avg_sharpe_ratio"] >= walk_forward_results["target_sharpe"],
            "periods_meeting_target": f"{walk_forward_results['meets_target_pct']:.1f}%",
            "average_annual_return": f"{walk_forward_results['avg_annual_return']*100:.2f}%",
            "average_max_drawdown": f"{walk_forward_results['avg_max_drawdown']*100:.2f}%",
            "sharpe_ratio_range": f"{walk_forward_results['min_sharpe_ratio']:.2f} to {walk_forward_results['max_sharpe_ratio']:.2f}"
        }
