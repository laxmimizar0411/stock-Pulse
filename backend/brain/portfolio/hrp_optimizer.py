"""
Hierarchical Risk Parity (HRP) Optimizer

Risk-based portfolio allocation using hierarchical clustering.
Diversifies without relying on expected returns.
"""

import logging
from typing import List, Optional, Dict, Any
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, dendrogram
from scipy.spatial.distance import squareform
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class HRPOptimizer:
    """
    Hierarchical Risk Parity portfolio optimizer.
    
    Algorithm:
    1. Compute distance matrix from correlation
    2. Hierarchical clustering (single linkage)
    3. Quasi-diagonalization (sort by clusters)
    4. Recursive bisection for weight allocation
    
    Benefits:
    - No expected returns needed
    - Robust to estimation error
    - Natural diversification via clustering
    - Caps correlation exposure
    """
    
    def __init__(self):
        """Initialize HRP optimizer."""
        pass
    
    def compute_distance_matrix(self, correlation_matrix: np.ndarray) -> np.ndarray:
        """
        Convert correlation to distance matrix.
        
        Distance = sqrt(0.5 * (1 - correlation))
        
        Args:
            correlation_matrix: Correlation matrix
            
        Returns:
            Distance matrix
        """
        # Ensure correlation is valid
        correlation_matrix = np.clip(correlation_matrix, -1, 1)
        
        # Convert to distance
        distance_matrix = np.sqrt(0.5 * (1 - correlation_matrix))
        
        return distance_matrix
    
    def cluster_assets(
        self,
        distance_matrix: np.ndarray,
        method: str = 'single'
    ) -> np.ndarray:
        """
        Hierarchical clustering of assets.
        
        Args:
            distance_matrix: Distance matrix
            method: Linkage method ('single', 'complete', 'average', 'ward')
            
        Returns:
            Linkage matrix
        """
        # Convert to condensed form for scipy
        distance_condensed = squareform(distance_matrix, checks=False)
        
        # Hierarchical clustering
        linkage_matrix = linkage(distance_condensed, method=method)
        
        return linkage_matrix
    
    def quasi_diagonalize(
        self,
        linkage_matrix: np.ndarray,
        n_assets: int
    ) -> List[int]:
        """
        Sort assets by hierarchical clustering order (quasi-diagonalization).
        
        Args:
            linkage_matrix: Linkage matrix from clustering
            n_assets: Number of assets
            
        Returns:
            Sorted indices
        """
        # Get dendrogram order without plotting
        dend = dendrogram(linkage_matrix, no_plot=True)
        sorted_indices = dend['leaves']
        
        return sorted_indices
    
    def recursive_bisection(
        self,
        covariance_matrix: np.ndarray,
        sorted_indices: List[int]
    ) -> np.ndarray:
        """
        Recursive bisection to allocate weights.
        
        Args:
            covariance_matrix: Covariance matrix
            sorted_indices: Sorted asset indices from clustering
            
        Returns:
            HRP weights
        """
        n_assets = len(sorted_indices)
        weights = np.ones(n_assets)
        
        # Recursive bisection
        clusters = [sorted_indices]
        
        while len(clusters) > 0:
            # Pop first cluster
            cluster = clusters.pop(0)
            
            if len(cluster) == 1:
                # Single asset, nothing to split
                continue
            
            # Split cluster into two sub-clusters
            mid = len(cluster) // 2
            left_cluster = cluster[:mid]
            right_cluster = cluster[mid:]
            
            # Compute cluster variances
            left_cov = covariance_matrix[np.ix_(left_cluster, left_cluster)]
            right_cov = covariance_matrix[np.ix_(right_cluster, right_cluster)]
            
            # Inverse-variance weights within each cluster
            left_weights = np.ones(len(left_cluster))
            right_weights = np.ones(len(right_cluster))
            
            # Cluster-level variance
            left_variance = left_weights @ left_cov @ left_weights
            right_variance = right_weights @ right_cov @ right_weights
            
            # Allocate between clusters (inverse variance)
            total_inv_var = 1.0 / left_variance + 1.0 / right_variance
            left_allocation = (1.0 / left_variance) / total_inv_var
            right_allocation = (1.0 / right_variance) / total_inv_var
            
            # Update weights
            weights[left_cluster] *= left_allocation
            weights[right_cluster] *= right_allocation
            
            # Add sub-clusters to queue
            clusters.extend([left_cluster, right_cluster])
        
        # Normalize
        weights = weights / np.sum(weights)
        
        return weights
    
    def optimize(
        self,
        correlation_matrix: np.ndarray,
        covariance_matrix: np.ndarray,
        symbols: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Complete HRP optimization.
        
        Args:
            correlation_matrix: Correlation matrix
            covariance_matrix: Covariance matrix
            symbols: List of stock symbols (optional)
            
        Returns:
            HRP weights and analytics
        """
        n_assets = correlation_matrix.shape[0]
        
        if symbols is None:
            symbols = [f"Asset_{i}" for i in range(n_assets)]
        
        # 1. Compute distance matrix
        distance_matrix = self.compute_distance_matrix(correlation_matrix)
        
        # 2. Hierarchical clustering
        linkage_matrix = self.cluster_assets(distance_matrix)
        
        # 3. Quasi-diagonalize
        sorted_indices = self.quasi_diagonalize(linkage_matrix, n_assets)
        
        # 4. Recursive bisection
        weights = np.zeros(n_assets)
        sorted_weights = self.recursive_bisection(covariance_matrix, sorted_indices)
        
        # Map back to original order
        for i, idx in enumerate(sorted_indices):
            weights[idx] = sorted_weights[i]
        
        # 5. Compute portfolio statistics
        portfolio_variance = weights @ covariance_matrix @ weights
        portfolio_std = np.sqrt(portfolio_variance)
        
        return {
            "symbols": symbols,
            "weights": weights.tolist(),
            "allocation": {
                symbol: float(weight)
                for symbol, weight in zip(symbols, weights)
            },
            "volatility_annual": float(portfolio_std * np.sqrt(252)),
            "sorted_indices": sorted_indices,
            "computed_at": datetime.now(timezone.utc).isoformat()
        }
    
    def get_cluster_composition(
        self,
        linkage_matrix: np.ndarray,
        symbols: List[str],
        n_clusters: int = 3
    ) -> Dict[int, List[str]]:
        """
        Get cluster composition.
        
        Args:
            linkage_matrix: Linkage matrix
            symbols: Stock symbols
            n_clusters: Number of clusters to extract
            
        Returns:
            Dictionary of cluster assignments
        """
        from scipy.cluster.hierarchy import fcluster
        
        # Extract flat clusters
        cluster_labels = fcluster(linkage_matrix, n_clusters, criterion='maxclust')
        
        # Group symbols by cluster
        clusters = {}
        for i, label in enumerate(cluster_labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(symbols[i])
        
        return clusters
