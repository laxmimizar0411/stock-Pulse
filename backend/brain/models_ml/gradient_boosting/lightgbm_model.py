"""
LightGBM Direction Classifier

Faster training alternative to XGBoost with native categorical support.
Used as an ensemble member alongside XGBoost.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
    logger.info("lightgbm not available; LightGBM model will use fallback")

try:
    from sklearn.metrics import accuracy_score, f1_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


class LightGBMDirectionModel:
    """
    LightGBM classifier for stock direction prediction.

    Complements XGBoost in the ensemble — faster training,
    handles categoricals (sector, market_cap_category) natively.
    """

    DIRECTION_MAP = {0: "DOWN", 1: "NEUTRAL", 2: "UP"}
    REVERSE_MAP = {"DOWN": 0, "NEUTRAL": 1, "UP": 2}

    def __init__(self, params: Optional[Dict] = None):
        self.model_name = "lightgbm_direction_5d"
        self.model_version = "0.1.0"
        self.trained_at: Optional[datetime] = None
        self.metrics: Dict[str, float] = {}
        self.feature_names: List[str] = []
        self._model = None

        self.params = params or {
            "objective": "multiclass",
            "num_class": 3,
            "metric": "multi_logloss",
            "max_depth": 7,
            "learning_rate": 0.05,
            "n_estimators": 300,
            "num_leaves": 63,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_samples": 20,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "random_state": 42,
            "verbose": -1,
        }

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: Optional[List[str]] = None,
        categorical_features: Optional[List[str]] = None,
        eval_set: Optional[Tuple[np.ndarray, np.ndarray]] = None,
    ) -> Dict[str, float]:
        """Train the LightGBM model."""
        if not LIGHTGBM_AVAILABLE:
            logger.warning("LightGBM not available, skipping training")
            return {"error": "lightgbm not installed"}

        self.feature_names = feature_names or [f"f{i}" for i in range(X.shape[1])]

        if y.dtype == object or isinstance(y[0], str):
            y = np.array([self.REVERSE_MAP.get(str(v), 1) for v in y])

        n_estimators = self.params.pop("n_estimators", 300)
        self._model = lgb.LGBMClassifier(
            n_estimators=n_estimators,
            **self.params,
        )

        fit_params = {}
        if eval_set is not None:
            X_val, y_val = eval_set
            if y_val.dtype == object or isinstance(y_val[0], str):
                y_val = np.array([self.REVERSE_MAP.get(str(v), 1) for v in y_val])
            fit_params["eval_set"] = [(X_val, y_val)]

        if categorical_features:
            fit_params["categorical_feature"] = categorical_features

        self._model.fit(X, y, **fit_params)
        self.params["n_estimators"] = n_estimators
        self.trained_at = datetime.now(timezone.utc)

        y_pred = self._model.predict(X)
        self.metrics = self._compute_metrics(y, y_pred)
        self.metrics["n_samples"] = len(y)

        logger.info(
            "LightGBM trained: accuracy=%.3f, f1_macro=%.3f on %d samples",
            self.metrics.get("accuracy", 0),
            self.metrics.get("f1_macro", 0),
            len(y),
        )
        return self.metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._model is None:
            return np.full(X.shape[0], 1)
        return self._model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self._model is None:
            return np.full((X.shape[0], 3), 1 / 3)
        return self._model.predict_proba(X)

    def predict_signal(self, features: Dict[str, float]) -> Dict[str, Any]:
        """Predict for a single stock."""
        if not self.is_trained:
            return {
                "direction": "HOLD",
                "probability": 0.5,
                "predicted_return_pct": 0.0,
                "model_name": self.model_name,
            }

        X = np.array([[features.get(f, 0.0) for f in self.feature_names]])
        probs = self.predict_proba(X)[0]
        pred_class = int(np.argmax(probs))
        direction = self.DIRECTION_MAP[pred_class]
        estimated_return = (probs[2] - probs[0]) * 3.0

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
        }

    def get_feature_importance(self) -> Dict[str, float]:
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
        if self._model is None:
            return {"error": "model not trained"}
        if y.dtype == object or isinstance(y[0], str):
            y = np.array([self.REVERSE_MAP.get(str(v), 1) for v in y])
        y_pred = self._model.predict(X)
        return self._compute_metrics(y, y_pred)

    def _compute_metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
        if not SKLEARN_AVAILABLE:
            correct = np.sum(y_true == y_pred)
            return {"accuracy": float(correct / len(y_true))}
        return {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
            "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        }

    def save(self, path: str):
        if self._model is None:
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

    def export_onnx(self, path: str) -> bool:
        """
        Export model to ONNX format for ultra-fast inference (5-20ms).
        
        ONNX Runtime provides 2-5x faster inference compared to native LightGBM.
        Useful for production deployment with high-throughput requirements.
        
        Args:
            path: Output path for .onnx file
            
        Returns:
            True if export successful, False otherwise
        """
        if self._model is None:
            logger.error("Cannot export untrained model to ONNX")
            return False
        
        try:
            # Try importing onnxmltools
            import onnxmltools
            from onnxmltools.convert.common.data_types import FloatTensorType
            
            # Prepare input type specification
            n_features = len(self.feature_names) if self.feature_names else self._model.n_features_
            initial_type = [('float_input', FloatTensorType([None, n_features]))]
            
            # Convert to ONNX
            onnx_model = onnxmltools.convert_lightgbm(
                self._model,
                initial_types=initial_type,
                target_opset=12,
            )
            
            # Save to disk
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
            onnxmltools.utils.save_model(onnx_model, path)
            
            logger.info(f"LightGBM model exported to ONNX: {path}")
            logger.info("  Expected inference speedup: 2-5x (5-20ms per prediction)")
            return True
            
        except ImportError as e:
            logger.warning(f"ONNX export failed - missing dependencies: {e}")
            logger.info("Install with: pip install onnxmltools onnxruntime")
            return False
        except Exception as e:
            logger.exception(f"ONNX export failed: {e}")
            return False

    @classmethod
    def load(cls, path: str) -> "LightGBMDirectionModel":
        import joblib
        data = joblib.load(path)
        instance = cls(params=data.get("params"))
        instance._model = data["model"]
        instance.feature_names = data.get("feature_names", [])
        instance.metrics = data.get("metrics", {})
        instance.trained_at = data.get("trained_at")
        instance.model_version = data.get("model_version", "0.1.0")
        return instance

    def get_info(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "trained_at": self.trained_at.isoformat() if self.trained_at else None,
            "is_trained": self.is_trained,
            "n_features": len(self.feature_names),
            "metrics": self.metrics,
            "onnx_exportable": True,
        }
