"""
Correlation Engine

Computes rolling EWMA correlation matrix for global markets.
Cost-effective alternative to DCC-GARCH.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import numpy as np
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CorrelationEngine:
    """
    EWMA (Exponentially Weighted Moving Average) Correlation Engine.
    
    More efficient than DCC-GARCH while capturing time-varying correlations.
    Uses Pandas ewm() with span parameter for decay.
    """
    
    def __init__(self, span: int = 60, min_periods: int = 20):
        """
        Initialize correlation engine.
        
        Args:
            span: EWMA span (half-life = span * ln(2))
            min_periods: Minimum periods required for calculation
        """
        self.span = span
        self.min_periods = min_periods
        self.correlation_matrix: Optional[pd.DataFrame] = None
        self.last_update: Optional[datetime] = None
        
    def compute_ewma_correlation(
        self,
        market_data: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """
        Compute EWMA correlation matrix from market data.
        
        Args:
            market_data: Dictionary of market DataFrames with 'Close' column
            
        Returns:
            Correlation matrix as DataFrame
        """
        if not market_data:
            raise ValueError("No market data provided")
        
        # Extract closing prices
        prices_dict = {}
        for name, df in market_data.items():
            if not df.empty and 'Close' in df.columns:
                # Ensure index is datetime
                if 'Date' in df.columns:
                    df = df.set_index('Date')
                
                prices_dict[name] = df['Close']
        
        if not prices_dict:
            raise ValueError("No valid price data found")
        
        # Combine into single DataFrame
        prices_df = pd.DataFrame(prices_dict)
        
        # Drop NaN rows (different market holidays)
        prices_df = prices_df.dropna()
        
        if len(prices_df) < self.min_periods:
            raise ValueError(f"Insufficient data: {len(prices_df)} rows < {self.min_periods} min_periods")
        
        # Calculate returns
        returns = prices_df.pct_change().dropna()
        
        # Compute EWMA covariance matrix
        ewma_cov = returns.ewm(span=self.span, min_periods=self.min_periods).cov()
        
        # Extract the latest covariance matrix
        # ewm().cov() returns a MultiIndex DataFrame with (date, asset) as index
        # We need to get the last date's covariance matrix
        n_assets = len(returns.columns)
        
        # Get the last n_assets rows which correspond to the latest date
        latest_cov = ewma_cov.iloc[-n_assets:].values
        
        # Convert covariance to correlation
        std_devs = np.sqrt(np.diag(latest_cov))
        std_matrix = np.outer(std_devs, std_devs)
        
        # Avoid division by zero
        std_matrix[std_matrix == 0] = 1
        
        correlation_values = latest_cov / std_matrix
        
        # Create a proper DataFrame with market names as index and columns
        correlation_matrix = pd.DataFrame(
            correlation_values,
            index=returns.columns,
            columns=returns.columns
        )
        
        # Store results
        self.correlation_matrix = correlation_matrix
        self.last_update = datetime.now(timezone.utc)
        
        logger.info(f"✅ EWMA correlation matrix computed: {correlation_matrix.shape}")
        
        return correlation_matrix
    
    def get_correlations_with_market(
        self,
        market_name: str,
        threshold: float = 0.5
    ) -> Dict[str, float]:
        """
        Get correlations of a specific market with all others.
        
        Args:
            market_name: Name of the market
            threshold: Minimum correlation threshold to include
            
        Returns:
            Dictionary of market correlations above threshold
        """
        if self.correlation_matrix is None:
            return {}
        
        if market_name not in self.correlation_matrix.columns:
            logger.warning(f"Market {market_name} not found in correlation matrix")
            return {}
        
        correlations = self.correlation_matrix[market_name].to_dict()
        
        # Filter by threshold and remove self-correlation
        filtered = {
            k: v for k, v in correlations.items()
            if k != market_name and abs(v) >= threshold
        }
        
        # Sort by absolute correlation
        sorted_corr = dict(sorted(
            filtered.items(),
            key=lambda x: abs(x[1]),
            reverse=True
        ))
        
        return sorted_corr
    
    def find_top_correlations(
        self,
        top_n: int = 10,
        exclude_self: bool = True
    ) -> List[Tuple[str, str, float]]:
        """
        Find top N correlated pairs.
        
        Args:
            top_n: Number of top pairs to return
            exclude_self: Exclude self-correlations
            
        Returns:
            List of tuples (market1, market2, correlation)
        """
        if self.correlation_matrix is None:
            return []
        
        # Get upper triangle (avoid duplicates)
        mask = np.triu(np.ones_like(self.correlation_matrix, dtype=bool), k=1 if exclude_self else 0)
        
        # Extract values
        pairs = []
        for i, market1 in enumerate(self.correlation_matrix.index):
            for j, market2 in enumerate(self.correlation_matrix.columns):
                if mask[i, j]:
                    corr = self.correlation_matrix.iloc[i, j]
                    pairs.append((market1, market2, float(corr)))
        
        # Sort by absolute correlation
        pairs.sort(key=lambda x: abs(x[2]), reverse=True)
        
        return pairs[:top_n]
    
    def detect_correlation_breakouts(
        self,
        historical_corr: Optional[pd.DataFrame] = None,
        std_threshold: float = 2.0
    ) -> List[Dict[str, Any]]:
        """
        Detect correlation breakouts (>2σ divergence from historical).
        
        Args:
            historical_corr: Historical correlation matrix for comparison
            std_threshold: Standard deviation threshold (default 2.0)
            
        Returns:
            List of breakout events
        """
        if self.correlation_matrix is None:
            return []
        
        breakouts = []
        
        # If no historical data, use own data to compute mean/std
        if historical_corr is None:
            # Use current matrix as baseline (simplified)
            mean_corr = self.correlation_matrix.mean().mean()
            std_corr = self.correlation_matrix.std().std()
        else:
            # Compare with historical
            diff = self.correlation_matrix - historical_corr
            mean_corr = diff.mean().mean()
            std_corr = diff.std().std()
        
        # Find pairs with >2σ divergence
        for i, market1 in enumerate(self.correlation_matrix.index):
            for j, market2 in enumerate(self.correlation_matrix.columns):
                if i < j:  # Upper triangle only
                    current_corr = self.correlation_matrix.iloc[i, j]
                    
                    # Check if divergence is significant
                    divergence = abs(current_corr - mean_corr)
                    if divergence > std_threshold * std_corr:
                        breakouts.append({
                            "market1": market1,
                            "market2": market2,
                            "current_correlation": float(current_corr),
                            "mean_correlation": float(mean_corr),
                            "divergence_std": float(divergence / std_corr if std_corr > 0 else 0),
                            "breakout_type": "positive" if current_corr > mean_corr else "negative"
                        })
        
        # Sort by divergence
        breakouts.sort(key=lambda x: x['divergence_std'], reverse=True)
        
        if breakouts:
            logger.info(f"⚠️ Detected {len(breakouts)} correlation breakouts (>{std_threshold}σ)")
        
        return breakouts
    
    def get_india_relevant_correlations(self) -> Dict[str, Any]:
        """
        Get correlations most relevant to Indian markets.
        
        Focus on:
        - SGX NIFTY (direct proxy)
        - Asian markets (regional influence)
        - Crude oil (energy sector impact)
        - DXY (EM flows impact)
        """
        if self.correlation_matrix is None:
            return {}
        
        india_proxies = ['SGX_NIFTY', 'NIKKEI', 'HANGSENG', 'CRUDE_WTI', 'CRUDE_BRENT', 'DXY', 'MSCI_EM']
        
        relevant_corr = {}
        for proxy in india_proxies:
            if proxy in self.correlation_matrix.columns:
                corr_with_others = self.get_correlations_with_market(proxy, threshold=0.3)
                if corr_with_others:
                    relevant_corr[proxy] = corr_with_others
        
        return {
            "india_proxy_correlations": relevant_corr,
            "computed_at": self.last_update.isoformat() if self.last_update else None
        }
    
    def get_correlation_summary(self) -> Dict[str, Any]:
        """Get summary statistics of correlation matrix."""
        if self.correlation_matrix is None:
            return {
                "status": "not_computed",
                "matrix_size": 0,
                "last_update": None
            }
        
        # Flatten upper triangle (excluding diagonal)
        mask = np.triu(np.ones_like(self.correlation_matrix, dtype=bool), k=1)
        upper_triangle = self.correlation_matrix.values[mask]
        
        return {
            "status": "computed",
            "matrix_size": self.correlation_matrix.shape[0],
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "statistics": {
                "mean_correlation": float(np.mean(upper_triangle)),
                "median_correlation": float(np.median(upper_triangle)),
                "std_correlation": float(np.std(upper_triangle)),
                "min_correlation": float(np.min(upper_triangle)),
                "max_correlation": float(np.max(upper_triangle)),
                "positive_correlations_pct": float(np.sum(upper_triangle > 0) / len(upper_triangle) * 100),
                "strong_correlations_pct": float(np.sum(np.abs(upper_triangle) > 0.7) / len(upper_triangle) * 100)
            },
            "span": self.span,
            "min_periods": self.min_periods
        }
