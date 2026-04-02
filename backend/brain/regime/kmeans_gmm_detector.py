"""
K-Means and GMM Market Regime Detectors

Complementary regime detection using clustering algorithms:
- K-Means: Hard clustering with Euclidean distance
- GMM (Gaussian Mixture Model): Soft clustering with probability distributions

These provide alternative perspectives to HMM for regime detection consensus.
"""

import logging
import os
from typing import Any, Dict, Optional, Tuple

import numpy as np

from brain.models.events import MarketRegime

logger = logging.getLogger(__name__)

try:
    from sklearn.cluster import KMeans
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import StandardScaler
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False
    logger.warning("scikit-learn not available - KMeans/GMM detectors disabled")


class KMeansRegimeDetector:
    """
    K-Means clustering regime detector.
    
    Uses hard clustering to assign market states based on feature similarity.
    Simple and fast, but doesn't capture temporal dynamics like HMM.
    """
    
    def __init__(self, n_clusters: int = 3, random_state: int = 42):
        self.n_clusters = n_clusters
        self.random_state = random_state
        self.model = None
        self.scaler = StandardScaler() if _HAS_SKLEARN else None
        self._trained = False
        self._cluster_to_regime: Dict[int, MarketRegime] = {}
    
    def train(self, features: np.ndarray) -> None:
        """
        Train K-Means clustering on feature matrix.
        
        Args:
            features: Array of shape (n_samples, n_features)
        """
        if not _HAS_SKLEARN:
            logger.warning("scikit-learn not available, skipping K-Means training")
            return
        
        if features.ndim == 1:
            features = features.reshape(-1, 1)
        
        # Standardize features
        features_scaled = self.scaler.fit_transform(features)
        
        # Train K-Means
        self.model = KMeans(
            n_clusters=self.n_clusters,
            random_state=self.random_state,
            n_init=10,
            max_iter=300
        )
        self.model.fit(features_scaled)
        
        # Map clusters to regimes based on mean returns (column 0)
        self._map_clusters_to_regimes(features)
        
        self._trained = True
        logger.info(f"K-Means trained on {features.shape[0]} samples with {self.n_clusters} clusters")
    
    def _map_clusters_to_regimes(self, features: np.ndarray) -> None:
        """Map cluster IDs to market regimes based on average returns."""
        cluster_labels = self.model.labels_
        
        # Calculate average return for each cluster
        cluster_means = {}
        for cluster_id in range(self.n_clusters):
            mask = cluster_labels == cluster_id
            cluster_returns = features[mask, 0]  # First column = daily returns
            cluster_means[cluster_id] = np.mean(cluster_returns)
        
        # Sort clusters by mean return
        sorted_clusters = sorted(cluster_means.items(), key=lambda x: x[1])
        
        # Map: lowest mean → BEAR, highest → BULL, middle → SIDEWAYS
        self._cluster_to_regime[sorted_clusters[0][0]] = MarketRegime.BEAR
        self._cluster_to_regime[sorted_clusters[-1][0]] = MarketRegime.BULL
        
        for cluster_id, _ in sorted_clusters[1:-1]:
            self._cluster_to_regime[cluster_id] = MarketRegime.SIDEWAYS
        
        logger.info(f"K-Means cluster-to-regime mapping: {self._cluster_to_regime}")
    
    def predict_regime(self, features: np.ndarray) -> Tuple[MarketRegime, Dict[str, float]]:
        """
        Predict current regime using K-Means.
        
        Args:
            features: Feature matrix (uses last row for prediction)
            
        Returns:
            Tuple of (regime, probability_dict)
        """
        if not self._trained or self.model is None:
            return MarketRegime.SIDEWAYS, {
                "bull_prob": 0.33,
                "bear_prob": 0.33,
                "sideways_prob": 0.34
            }
        
        if features.ndim == 1:
            features = features.reshape(-1, 1)
        
        # Scale and predict
        features_scaled = self.scaler.transform(features)
        cluster = self.model.predict(features_scaled[-1].reshape(1, -1))[0]
        
        # Get regime
        regime = self._cluster_to_regime.get(int(cluster), MarketRegime.SIDEWAYS)
        
        # K-Means is hard clustering, so assign high probability to predicted regime
        if regime == MarketRegime.BULL:
            probs = {"bull_prob": 0.80, "bear_prob": 0.10, "sideways_prob": 0.10}
        elif regime == MarketRegime.BEAR:
            probs = {"bull_prob": 0.10, "bear_prob": 0.80, "sideways_prob": 0.10}
        else:
            probs = {"bull_prob": 0.15, "bear_prob": 0.15, "sideways_prob": 0.70}
        
        return regime, probs
    
    @property
    def is_available(self) -> bool:
        return _HAS_SKLEARN
    
    @property
    def is_trained(self) -> bool:
        return self._trained


class GMMRegimeDetector:
    """
    Gaussian Mixture Model regime detector.
    
    Uses soft clustering with probability distributions. Better than K-Means
    for capturing uncertainty and overlapping regimes.
    """
    
    def __init__(self, n_components: int = 3, random_state: int = 42):
        self.n_components = n_components
        self.random_state = random_state
        self.model = None
        self.scaler = StandardScaler() if _HAS_SKLEARN else None
        self._trained = False
        self._component_to_regime: Dict[int, MarketRegime] = {}
    
    def train(self, features: np.ndarray) -> None:
        """
        Train GMM on feature matrix.
        
        Args:
            features: Array of shape (n_samples, n_features)
        """
        if not _HAS_SKLEARN:
            logger.warning("scikit-learn not available, skipping GMM training")
            return
        
        if features.ndim == 1:
            features = features.reshape(-1, 1)
        
        # Standardize features
        features_scaled = self.scaler.fit_transform(features)
        
        # Train GMM
        self.model = GaussianMixture(
            n_components=self.n_components,
            covariance_type='full',
            random_state=self.random_state,
            max_iter=200,
            n_init=10
        )
        self.model.fit(features_scaled)
        
        # Map components to regimes
        self._map_components_to_regimes(features)
        
        self._trained = True
        logger.info(f"GMM trained on {features.shape[0]} samples with {self.n_components} components")
        logger.info(f"GMM converged: {self.model.converged_}, AIC: {self.model.aic(features_scaled):.2f}")
    
    def _map_components_to_regimes(self, features: np.ndarray) -> None:
        """Map GMM components to market regimes based on mean returns."""
        # Get component means (in original feature space)
        component_means_scaled = self.model.means_
        component_means = self.scaler.inverse_transform(component_means_scaled)
        
        # Extract return means (column 0)
        return_means = {i: component_means[i, 0] for i in range(self.n_components)}
        
        # Sort by return
        sorted_components = sorted(return_means.items(), key=lambda x: x[1])
        
        # Map: lowest → BEAR, highest → BULL, middle → SIDEWAYS
        self._component_to_regime[sorted_components[0][0]] = MarketRegime.BEAR
        self._component_to_regime[sorted_components[-1][0]] = MarketRegime.BULL
        
        for component_id, _ in sorted_components[1:-1]:
            self._component_to_regime[component_id] = MarketRegime.SIDEWAYS
        
        logger.info(f"GMM component-to-regime mapping: {self._component_to_regime}")
    
    def predict_regime(self, features: np.ndarray) -> Tuple[MarketRegime, Dict[str, float]]:
        """
        Predict current regime using GMM with soft probabilities.
        
        Args:
            features: Feature matrix (uses last row for prediction)
            
        Returns:
            Tuple of (regime, probability_dict)
        """
        if not self._trained or self.model is None:
            return MarketRegime.SIDEWAYS, {
                "bull_prob": 0.33,
                "bear_prob": 0.33,
                "sideways_prob": 0.34
            }
        
        if features.ndim == 1:
            features = features.reshape(-1, 1)
        
        # Scale and predict probabilities
        features_scaled = self.scaler.transform(features)
        component_probs = self.model.predict_proba(features_scaled[-1].reshape(1, -1))[0]
        
        # Aggregate probabilities by regime
        regime_probs = {
            "bull_prob": 0.0,
            "bear_prob": 0.0,
            "sideways_prob": 0.0
        }
        
        for component_id, prob in enumerate(component_probs):
            regime = self._component_to_regime.get(component_id, MarketRegime.SIDEWAYS)
            key = f"{regime.value}_prob"
            regime_probs[key] += float(prob)
        
        # Determine most likely regime
        if regime_probs["bull_prob"] > regime_probs["bear_prob"] and regime_probs["bull_prob"] > regime_probs["sideways_prob"]:
            current_regime = MarketRegime.BULL
        elif regime_probs["bear_prob"] > regime_probs["sideways_prob"]:
            current_regime = MarketRegime.BEAR
        else:
            current_regime = MarketRegime.SIDEWAYS
        
        return current_regime, regime_probs
    
    @property
    def is_available(self) -> bool:
        return _HAS_SKLEARN
    
    @property
    def is_trained(self) -> bool:
        return self._trained
