"""Hierarchical Risk Parity (HRP) Portfolio — Phase 3.4

Implements the Marcos López de Prado HRP algorithm:
1. Cluster: Hierarchical clustering of correlation matrix
2. Quasi-Diagonalize: Reorder rows/columns to cluster form
3. Recursive Bipartition: Allocate risk inversely to variance

Benefits over Markowitz:
- No matrix inversion (numerically stable)
- Handles correlated assets well
- Out-of-sample robust
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class HRPResult:
    """Result of HRP portfolio optimization."""
    weights: Dict[str, float] = field(default_factory=dict)
    n_assets: int = 0
    cluster_order: List[str] = field(default_factory=list)
    portfolio_variance: float = 0.0
    portfolio_volatility: float = 0.0
    diversification_ratio: float = 0.0
    max_weight: float = 0.0
    min_weight: float = 0.0
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "weights": {k: round(v, 6) for k, v in self.weights.items()},
            "n_assets": self.n_assets,
            "cluster_order": self.cluster_order,
            "portfolio_variance": round(self.portfolio_variance, 8),
            "portfolio_volatility": round(self.portfolio_volatility, 6),
            "diversification_ratio": round(self.diversification_ratio, 4),
            "max_weight": round(self.max_weight, 6),
            "min_weight": round(self.min_weight, 6),
            "computed_at": self.computed_at.isoformat(),
        }


def _correlation_distance(corr: np.ndarray) -> np.ndarray:
    """Convert correlation matrix to distance matrix."""
    return np.sqrt(0.5 * (1 - corr))


def _hierarchical_cluster(dist: np.ndarray) -> List[List[int]]:
    """Simple agglomerative clustering using single linkage."""
    from scipy.cluster.hierarchy import linkage, leaves_list
    from scipy.spatial.distance import squareform
    condensed = squareform(dist, checks=False)
    link = linkage(condensed, method="single")
    order = list(leaves_list(link))
    return order, link


def _quasi_diagonalize(link: np.ndarray, n: int) -> List[int]:
    """Reorder correlation matrix to quasi-diagonal form."""
    from scipy.cluster.hierarchy import leaves_list
    return list(leaves_list(link))


def _recursive_bisection(
    cov: np.ndarray,
    sorted_ix: List[int],
) -> np.ndarray:
    """Recursive bisection to allocate inverse-variance weights."""
    n = len(sorted_ix)
    weights = np.ones(n)

    clusters = [sorted_ix]
    while clusters:
        new_clusters = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            mid = len(cluster) // 2
            left = cluster[:mid]
            right = cluster[mid:]

            # Variance of each sub-cluster
            var_left = _cluster_var(cov, left)
            var_right = _cluster_var(cov, right)

            # Allocate inversely proportional to variance
            total = var_left + var_right
            if total == 0:
                alpha = 0.5
            else:
                alpha = 1 - var_left / total

            for ix in left:
                weights[sorted_ix.index(ix)] *= alpha
            for ix in right:
                weights[sorted_ix.index(ix)] *= (1 - alpha)

            if len(left) > 1:
                new_clusters.append(left)
            if len(right) > 1:
                new_clusters.append(right)

        clusters = new_clusters

    return weights / weights.sum()


def _cluster_var(cov: np.ndarray, indices: List[int]) -> float:
    """Variance of an equal-weight sub-portfolio."""
    if len(indices) == 0:
        return 0.0
    sub_cov = cov[np.ix_(indices, indices)]
    n = len(indices)
    w = np.ones(n) / n
    return float(w @ sub_cov @ w)


class HRPOptimizer:
    """Hierarchical Risk Parity portfolio optimizer."""

    def __init__(self):
        self._stats = {"optimizations": 0}

    def optimize(
        self,
        returns: np.ndarray,
        symbols: List[str],
    ) -> HRPResult:
        """Run HRP optimization.

        Args:
            returns: (T, N) matrix of daily returns for N assets
            symbols: List of N symbol names

        Returns:
            HRPResult with weights per symbol
        """
        n = returns.shape[1]
        if n != len(symbols):
            raise ValueError(f"returns columns ({n}) != symbols ({len(symbols)})")
        if n < 2:
            return HRPResult(
                weights={symbols[0]: 1.0} if symbols else {},
                n_assets=n,
            )

        # 1. Covariance and correlation
        cov = np.cov(returns, rowvar=False)
        std = np.sqrt(np.diag(cov))
        std[std == 0] = 1e-10
        corr = cov / np.outer(std, std)
        np.fill_diagonal(corr, 1.0)
        corr = np.clip(corr, -1, 1)

        # 2. Distance matrix
        dist = _correlation_distance(corr)

        # 3. Hierarchical clustering
        sorted_ix, link = _hierarchical_cluster(dist)

        # 4. Quasi-diagonalize
        sorted_ix = _quasi_diagonalize(link, n)

        # 5. Recursive bisection
        weights = _recursive_bisection(cov, sorted_ix)

        # Map back to symbols
        weight_dict = {}
        for i, ix in enumerate(sorted_ix):
            weight_dict[symbols[ix]] = float(weights[i])

        # Portfolio metrics
        w_arr = np.array([weight_dict.get(s, 0) for s in symbols])
        port_var = float(w_arr @ cov @ w_arr)
        port_vol = float(np.sqrt(port_var))

        # Diversification ratio
        individual_vols = np.sqrt(np.diag(cov))
        weighted_sum_vols = float(np.sum(w_arr * individual_vols))
        div_ratio = weighted_sum_vols / port_vol if port_vol > 0 else 1.0

        result = HRPResult(
            weights=weight_dict,
            n_assets=n,
            cluster_order=[symbols[ix] for ix in sorted_ix],
            portfolio_variance=port_var,
            portfolio_volatility=port_vol,
            diversification_ratio=div_ratio,
            max_weight=float(np.max(weights)),
            min_weight=float(np.min(weights)),
        )

        self._stats["optimizations"] += 1
        return result

    def get_stats(self) -> Dict[str, Any]:
        return self._stats
