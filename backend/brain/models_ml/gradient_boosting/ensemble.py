"""
Gradient Boosting Ensemble

Combines XGBoost and LightGBM predictions via probability averaging
for more robust directional predictions.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from brain.models_ml.gradient_boosting.xgboost_model import XGBoostDirectionModel
from brain.models_ml.gradient_boosting.lightgbm_model import LightGBMDirectionModel

logger = logging.getLogger(__name__)


class GradientBoostingEnsemble:
    """
    Ensemble of XGBoost + LightGBM for direction prediction.

    Combines via weighted probability averaging:
    - XGBoost: 55% weight (typically slightly better accuracy)
    - LightGBM: 45% weight (provides diversity)
    """

    def __init__(self, xgb_weight: float = 0.55, lgb_weight: float = 0.45):
        self.xgb_model = XGBoostDirectionModel()
        self.lgb_model = LightGBMDirectionModel()
        self.xgb_weight = xgb_weight
        self.lgb_weight = lgb_weight
        self.model_name = "gb_ensemble_direction_5d"
        self.model_version = "0.1.0"
        self.feature_names: List[str] = []
        self.trained_at: Optional[datetime] = None
        self.metrics: Dict[str, float] = {}

    @property
    def is_trained(self) -> bool:
        return self.xgb_model.is_trained or self.lgb_model.is_trained

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: Optional[List[str]] = None,
        eval_set=None,
    ) -> Dict[str, float]:
        """Train both models."""
        self.feature_names = feature_names or [f"f{i}" for i in range(X.shape[1])]

        xgb_metrics = self.xgb_model.train(X, y, feature_names=self.feature_names, eval_set=eval_set)
        lgb_metrics = self.lgb_model.train(X, y, feature_names=self.feature_names, eval_set=eval_set)

        # Ensemble metrics on training data
        y_pred = self.predict(X)
        if y.dtype == object or isinstance(y[0], str):
            y_enc = np.array([XGBoostDirectionModel.REVERSE_MAP.get(str(v), 1) for v in y])
        else:
            y_enc = y

        try:
            from sklearn.metrics import accuracy_score, f1_score
            self.metrics = {
                "accuracy": float(accuracy_score(y_enc, y_pred)),
                "f1_macro": float(f1_score(y_enc, y_pred, average="macro", zero_division=0)),
                "xgb_accuracy": xgb_metrics.get("accuracy", 0),
                "lgb_accuracy": lgb_metrics.get("accuracy", 0),
            }
        except ImportError:
            correct = float(np.sum(y_enc == y_pred))
            self.metrics = {"accuracy": correct / len(y_enc)}

        self.trained_at = datetime.now(timezone.utc)
        logger.info("Ensemble trained: accuracy=%.3f", self.metrics.get("accuracy", 0))
        return self.metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict using ensemble averaging."""
        probs = self.predict_proba(X)
        return np.argmax(probs, axis=1)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Weighted probability average."""
        probs = np.zeros((X.shape[0], 3))
        total_weight = 0

        if self.xgb_model.is_trained:
            probs += self.xgb_weight * self.xgb_model.predict_proba(X)
            total_weight += self.xgb_weight

        if self.lgb_model.is_trained:
            probs += self.lgb_weight * self.lgb_model.predict_proba(X)
            total_weight += self.lgb_weight

        if total_weight > 0:
            probs /= total_weight
        else:
            probs[:] = 1 / 3

        return probs

    def predict_signal(self, features: Dict[str, float]) -> Dict[str, Any]:
        """Predict for a single stock with ensemble averaging."""
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
        pred_class = int(np.argmax(probs))
        direction_map = {0: "DOWN", 1: "NEUTRAL", 2: "UP"}
        direction = direction_map[pred_class]
        estimated_return = (probs[2] - probs[0]) * 3.0

        # Get individual model predictions for transparency
        xgb_pred = self.xgb_model.predict_signal(features) if self.xgb_model.is_trained else None
        lgb_pred = self.lgb_model.predict_signal(features) if self.lgb_model.is_trained else None

        return {
            "direction": direction if direction != "NEUTRAL" else "HOLD",
            "probability": float(probs[pred_class]),
            "predicted_return_pct": round(estimated_return, 2),
            "class_probs": {
                "DOWN": round(float(probs[0]), 4),
                "NEUTRAL": round(float(probs[1]), 4),
                "UP": round(float(probs[2]), 4),
            },
            "model_name": self.model_name,
            "model_version": self.model_version,
            "sub_models": {
                "xgboost": xgb_pred,
                "lightgbm": lgb_pred,
            },
        }

    def get_feature_importance(self) -> Dict[str, float]:
        """Averaged feature importance from both models."""
        xgb_imp = self.xgb_model.get_feature_importance()
        lgb_imp = self.lgb_model.get_feature_importance()

        all_features = set(list(xgb_imp.keys()) + list(lgb_imp.keys()))
        combined = {}
        for f in all_features:
            combined[f] = (
                self.xgb_weight * xgb_imp.get(f, 0) +
                self.lgb_weight * lgb_imp.get(f, 0)
            )

        return dict(sorted(combined.items(), key=lambda x: x[1], reverse=True))

    def evaluate(self, X: np.ndarray, y: np.ndarray) -> Dict[str, float]:
        """Evaluate ensemble on test data."""
        y_pred = self.predict(X)
        if y.dtype == object or isinstance(y[0], str):
            y = np.array([XGBoostDirectionModel.REVERSE_MAP.get(str(v), 1) for v in y])

        try:
            from sklearn.metrics import accuracy_score, f1_score
            return {
                "accuracy": float(accuracy_score(y, y_pred)),
                "f1_macro": float(f1_score(y, y_pred, average="macro", zero_division=0)),
            }
        except ImportError:
            return {"accuracy": float(np.sum(y == y_pred) / len(y))}

    def save(self, directory: str):
        """Save both models."""
        import os
        os.makedirs(directory, exist_ok=True)
        self.xgb_model.save(os.path.join(directory, "xgboost_model.joblib"))
        self.lgb_model.save(os.path.join(directory, "lightgbm_model.joblib"))
        logger.info("Ensemble saved to %s", directory)

    @classmethod
    def load(cls, directory: str) -> "GradientBoostingEnsemble":
        """Load both models."""
        import os
        instance = cls()
        xgb_path = os.path.join(directory, "xgboost_model.joblib")
        lgb_path = os.path.join(directory, "lightgbm_model.joblib")
        if os.path.exists(xgb_path):
            instance.xgb_model = XGBoostDirectionModel.load(xgb_path)
        if os.path.exists(lgb_path):
            instance.lgb_model = LightGBMDirectionModel.load(lgb_path)
        instance.feature_names = instance.xgb_model.feature_names or instance.lgb_model.feature_names
        return instance

    def get_info(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "trained_at": self.trained_at.isoformat() if self.trained_at else None,
            "is_trained": self.is_trained,
            "metrics": self.metrics,
            "sub_models": {
                "xgboost": self.xgb_model.get_info(),
                "lightgbm": self.lgb_model.get_info(),
            },
        }
