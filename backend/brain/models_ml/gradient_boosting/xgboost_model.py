"""
XGBoost Direction Classifier

Predicts 5-day directional movement (UP/DOWN/NEUTRAL) for stocks
using the Brain feature vector. Includes SHAP value computation.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logger.info("xgboost not available; XGBoost model will use fallback")

try:
    from sklearn.preprocessing import LabelEncoder
    from sklearn.metrics import accuracy_score, f1_score, classification_report
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


class XGBoostDirectionModel:
    """
    XGBoost classifier for stock direction prediction.

    Target: 5-day forward return classified into:
    - UP: return > +1%
    - DOWN: return < -1%
    - NEUTRAL: -1% to +1%
    """

    DIRECTION_MAP = {0: "DOWN", 1: "NEUTRAL", 2: "UP"}
    REVERSE_MAP = {"DOWN": 0, "NEUTRAL": 1, "UP": 2}

    def __init__(self, params: Optional[Dict] = None):
        self.model_name = "xgboost_direction_5d"
        self.model_version = "0.1.0"
        self.trained_at: Optional[datetime] = None
        self.metrics: Dict[str, float] = {}
        self.feature_names: List[str] = []
        self._model = None
        self._label_encoder = LabelEncoder() if SKLEARN_AVAILABLE else None

        self.params = params or {
            "objective": "multi:softprob",
            "num_class": 3,
            "max_depth": 6,
            "learning_rate": 0.05,
            "n_estimators": 300,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 5,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "eval_metric": "mlogloss",
            "tree_method": "hist",
            "random_state": 42,
        }

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: Optional[List[str]] = None,
        eval_set: Optional[Tuple[np.ndarray, np.ndarray]] = None,
    ) -> Dict[str, float]:
        """
        Train the XGBoost model.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Labels array with values in {0, 1, 2} or {"DOWN", "NEUTRAL", "UP"}
            feature_names: Optional feature names
            eval_set: Optional (X_val, y_val) for early stopping
        """
        if not XGBOOST_AVAILABLE:
            logger.warning("XGBoost not available, skipping training")
            return {"error": "xgboost not installed"}

        self.feature_names = feature_names or [f"f{i}" for i in range(X.shape[1])]

        # Encode labels if strings
        if y.dtype == object or isinstance(y[0], str):
            y = np.array([self.REVERSE_MAP.get(str(v), 1) for v in y])

        # Build XGBoost classifier
        n_estimators = self.params.pop("n_estimators", 300)
        self._model = xgb.XGBClassifier(
            n_estimators=n_estimators,
            **self.params,
        )

        fit_params = {}
        if eval_set is not None:
            X_val, y_val = eval_set
            if y_val.dtype == object or isinstance(y_val[0], str):
                y_val = np.array([self.REVERSE_MAP.get(str(v), 1) for v in y_val])
            fit_params["eval_set"] = [(X_val, y_val)]
            fit_params["verbose"] = False

        self._model.fit(X, y, **fit_params)
        self.params["n_estimators"] = n_estimators
        self.trained_at = datetime.now(timezone.utc)

        # Compute training metrics
        y_pred = self._model.predict(X)
        self.metrics = self._compute_metrics(y, y_pred)
        self.metrics["n_samples"] = len(y)
        self.metrics["n_features"] = X.shape[1]

        logger.info(
            "XGBoost trained: accuracy=%.3f, f1_macro=%.3f on %d samples",
            self.metrics.get("accuracy", 0),
            self.metrics.get("f1_macro", 0),
            len(y),
        )
        return self.metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict direction labels."""
        if self._model is None:
            return np.full(X.shape[0], 1)  # NEUTRAL fallback
        return self._model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities."""
        if self._model is None:
            return np.full((X.shape[0], 3), 1 / 3)
        return self._model.predict_proba(X)

    def predict_signal(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Predict direction for a single stock given its feature vector.

        Returns: {direction, probability, predicted_return_pct, class_probs}
        """
        if not self.is_trained:
            return {
                "direction": "HOLD",
                "probability": 0.5,
                "predicted_return_pct": 0.0,
                "model_name": self.model_name,
                "model_version": self.model_version,
            }

        X = np.array([[features.get(f, 0.0) for f in self.feature_names]])
        probs = self.predict_proba(X)[0]

        # Direction is the class with highest probability
        pred_class = int(np.argmax(probs))
        direction = self.DIRECTION_MAP[pred_class]
        probability = float(probs[pred_class])

        # Estimated return magnitude from probabilities
        estimated_return = (probs[2] - probs[0]) * 3.0  # rough mapping

        return {
            "direction": direction if direction != "NEUTRAL" else "HOLD",
            "probability": probability,
            "predicted_return_pct": round(estimated_return, 2),
            "class_probs": {
                "DOWN": round(float(probs[0]), 4),
                "NEUTRAL": round(float(probs[1]), 4),
                "UP": round(float(probs[2]), 4),
            },
            "model_name": self.model_name,
            "model_version": self.model_version,
        }

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance scores."""
        if self._model is None:
            return {}
        importance = self._model.feature_importances_
        return {
            name: float(imp)
            for name, imp in sorted(
                zip(self.feature_names, importance),
                key=lambda x: x[1],
                reverse=True,
            )
        }

    def evaluate(self, X: np.ndarray, y: np.ndarray) -> Dict[str, float]:
        """Evaluate model on test data."""
        if self._model is None:
            return {"error": "model not trained"}

        if y.dtype == object or isinstance(y[0], str):
            y = np.array([self.REVERSE_MAP.get(str(v), 1) for v in y])

        y_pred = self._model.predict(X)
        return self._compute_metrics(y, y_pred)

    def _compute_metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
        """Compute classification metrics."""
        if not SKLEARN_AVAILABLE:
            correct = np.sum(y_true == y_pred)
            return {"accuracy": float(correct / len(y_true))}

        return {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
            "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        }

    def save(self, path: str):
        """Save model to disk."""
        if self._model is None:
            logger.warning("No model to save")
            return

        import joblib
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        joblib.dump({
            "model": self._model,
            "feature_names": self.feature_names,
            "params": self.params,
            "metrics": self.metrics,
            "trained_at": self.trained_at,
            "model_version": self.model_version,
        }, path)
        logger.info("XGBoost model saved to %s", path)

    @classmethod
    def load(cls, path: str) -> "XGBoostDirectionModel":
        """Load model from disk."""
        import joblib
        data = joblib.load(path)

        instance = cls(params=data.get("params"))
        instance._model = data["model"]
        instance.feature_names = data.get("feature_names", [])
        instance.metrics = data.get("metrics", {})
        instance.trained_at = data.get("trained_at")
        instance.model_version = data.get("model_version", "0.1.0")
        logger.info("XGBoost model loaded from %s", path)
        return instance

    def get_info(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "trained_at": self.trained_at.isoformat() if self.trained_at else None,
            "is_trained": self.is_trained,
            "n_features": len(self.feature_names),
            "metrics": self.metrics,
            "params": {k: v for k, v in self.params.items() if k != "random_state"},
        }
