"""
Meta-Labeling Model — Confidence probability prediction.

Meta-labeling is a two-layer ML approach where:
1. Primary model generates directional signals (BUY/SELL/HOLD)
2. Meta-labeling model predicts: "Should we take this trade?" (probability)

This allows:
- Filtering low-quality signals
- Position sizing based on confidence
- Better risk management

Architecture:
- Input: Primary model features + primary model prediction + market regime
- Output: Probability [0, 1] that the primary signal will be profitable

References:
- "Advances in Financial Machine Learning" (Lopez de Prado, 2018) - Chapter 3
"""

import logging
import numpy as np
from typing import Any, Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger("brain.signals.meta_labeling")

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import roc_auc_score, precision_score, recall_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available - meta-labeling disabled")


class MetaLabeler:
    """
    Meta-labeling model for signal confidence estimation.
    
    Predicts the probability that a primary signal will be profitable,
    enabling sophisticated filtering and position sizing strategies.
    
    Workflow:
    1. Primary model generates signal (e.g., XGBoost says BUY)
    2. Meta-labeler estimates: P(signal is profitable | features, regime, primary_pred)
    3. Trade execution decision:
       - P > 0.7: Take full position
       - 0.5 < P < 0.7: Take reduced position
       - P < 0.5: Skip trade
    """
    
    def __init__(self, model_params: Optional[Dict] = None):
        self.model_name = "meta_labeler_v1"
        self.model_version = "0.1.0"
        self.trained_at: Optional[datetime] = None
        self.metrics: Dict[str, float] = {}
        
        self._model = None
        self._is_trained = False
        
        # Default Random Forest params (can be replaced with XGBoost/LightGBM)
        self.params = model_params or {
            "n_estimators": 100,
            "max_depth": 5,
            "min_samples_split": 20,
            "min_samples_leaf": 10,
            "max_features": "sqrt",
            "random_state": 42,
        }
    
    @property
    def is_available(self) -> bool:
        """Check if dependencies are available."""
        return SKLEARN_AVAILABLE
    
    @property
    def is_trained(self) -> bool:
        """Check if model has been trained."""
        return self._is_trained
    
    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        primary_predictions: np.ndarray,
        **kwargs
    ) -> Dict[str, float]:
        """
        Train meta-labeling model.
        
        Args:
            X: Feature matrix (n_samples, n_features) - original features
            y: Binary labels (n_samples,) - 1 if primary signal was profitable, 0 otherwise
            primary_predictions: Primary model predictions (n_samples,) - directional predictions
            
        Returns:
            Training metrics dict
        """
        if not SKLEARN_AVAILABLE:
            return {"error": "scikit-learn not available"}
        
        if len(X) < 100:
            logger.warning("Insufficient data for meta-labeling (<100 samples)")
            return {"error": "Insufficient training data"}
        
        # Augment features with primary predictions
        X_meta = self._augment_features(X, primary_predictions)
        
        # Initialize and train Random Forest
        self._model = RandomForestClassifier(**self.params)
        self._model.fit(X_meta, y)
        
        # Compute metrics
        y_pred = self._model.predict(X_meta)
        y_proba = self._model.predict_proba(X_meta)[:, 1]
        
        self.metrics = {
            "accuracy": float(np.mean(y_pred == y)),
            "precision": float(precision_score(y, y_pred, zero_division=0)),
            "recall": float(recall_score(y, y_pred, zero_division=0)),
            "roc_auc": float(roc_auc_score(y, y_proba)) if len(np.unique(y)) > 1 else 0.0,
        }
        
        self._is_trained = True
        self.trained_at = datetime.now(timezone.utc)
        
        logger.info(f"Meta-labeler trained: AUC={self.metrics['roc_auc']:.3f}, "
                   f"Precision={self.metrics['precision']:.3f}")
        
        return self.metrics
    
    def predict(
        self,
        X: np.ndarray,
        primary_predictions: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Predict confidence probability for primary signals.
        
        Args:
            X: Feature matrix (n_samples, n_features)
            primary_predictions: Primary model predictions (n_samples,)
            
        Returns:
            Dict containing:
            - probabilities: Confidence scores [0, 1]
            - decisions: Binary take/skip decisions (based on 0.5 threshold)
            - confidence_bins: Count per confidence range
        """
        if not self._is_trained or self._model is None:
            return {"error": "Model not trained"}
        
        # Augment features
        X_meta = self._augment_features(X, primary_predictions)
        
        # Predict probabilities
        probabilities = self._model.predict_proba(X_meta)[:, 1]
        
        # Binary decisions (threshold at 0.5)
        decisions = (probabilities >= 0.5).astype(int)
        
        # Confidence binning
        bins = {
            "high (>0.7)": int(np.sum(probabilities > 0.7)),
            "medium (0.5-0.7)": int(np.sum((probabilities >= 0.5) & (probabilities <= 0.7))),
            "low (<0.5)": int(np.sum(probabilities < 0.5)),
        }
        
        return {
            "probabilities": probabilities.tolist(),
            "decisions": decisions.tolist(),
            "confidence_bins": bins,
            "mean_confidence": float(np.mean(probabilities)),
            "signals_approved": int(np.sum(decisions)),
            "signals_rejected": int(len(decisions) - np.sum(decisions)),
        }
    
    def _augment_features(self, X: np.ndarray, primary_predictions: np.ndarray) -> np.ndarray:
        """
        Augment feature matrix with primary model predictions.
        
        The meta-labeler needs to see both the raw features AND the primary
        model's prediction to learn when the primary model is overconfident.
        """
        # Reshape primary predictions if needed
        if primary_predictions.ndim == 1:
            primary_predictions = primary_predictions.reshape(-1, 1)
        
        # Concatenate features with primary predictions
        X_augmented = np.hstack([X, primary_predictions])
        
        return X_augmented
    
    def save(self, path: str):
        """Save meta-labeling model to disk."""
        if not self._is_trained or self._model is None:
            logger.warning("Cannot save untrained meta-labeling model")
            return
        
        import joblib
        import os
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        
        joblib.dump({
            "model": self._model,
            "params": self.params,
            "metrics": self.metrics,
            "trained_at": self.trained_at,
            "model_version": self.model_version,
        }, path)
        
        logger.info(f"Meta-labeling model saved to {path}")
    
    @classmethod
    def load(cls, path: str) -> "MetaLabeler":
        """Load meta-labeling model from disk."""
        import joblib
        data = joblib.load(path)
        
        instance = cls(model_params=data.get("params"))
        instance._model = data["model"]
        instance.metrics = data.get("metrics", {})
        instance.trained_at = data.get("trained_at")
        instance.model_version = data.get("model_version", "0.1.0")
        instance._is_trained = True
        
        logger.info(f"Meta-labeling model loaded from {path}")
        return instance
    
    def get_info(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "trained_at": self.trained_at.isoformat() if self.trained_at else None,
            "is_trained": self._is_trained,
            "is_available": self.is_available,
            "metrics": self.metrics,
            "architecture": "Random Forest (meta-labeling)",
        }
