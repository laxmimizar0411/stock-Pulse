"""
Model Manager — Centralized ML model lifecycle management.

Handles training, saving, loading, prediction, and experiment tracking.
Uses MongoDB as a lightweight MLflow alternative for experiment logs.

Usage:
    manager = ModelManager(db=mongo_db)
    await manager.train_model("xgboost_direction", X_train, y_train)
    pred = await manager.predict("xgboost_direction", X_test)
"""

import asyncio
import json
import logging
import os
import pickle
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("brain.models_ml.model_manager")

IST = timezone(timedelta(hours=5, minutes=30))
MODELS_DIR = Path(os.getenv("MODELS_DIR", "./models"))
MODELS_DIR.mkdir(parents=True, exist_ok=True)


class ExperimentRun:
    """Tracks a single model training experiment."""

    def __init__(self, model_name: str, run_id: str = None):
        import uuid
        self.run_id = run_id or str(uuid.uuid4())[:8]
        self.model_name = model_name
        self.started_at = datetime.now(IST)
        self.completed_at: Optional[datetime] = None
        self.params: Dict[str, Any] = {}
        self.metrics: Dict[str, float] = {}
        self.tags: Dict[str, str] = {}
        self.status = "running"
        self.duration_s: Optional[float] = None
        self.artifact_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "model_name": self.model_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_s": self.duration_s,
            "status": self.status,
            "params": self.params,
            "metrics": self.metrics,
            "tags": self.tags,
            "artifact_path": self.artifact_path,
        }


class ModelManager:
    """
    Centralized model manager for all Brain ML models.

    Provides:
    - Training orchestration with experiment tracking
    - Model persistence (pickle + optional ONNX)
    - Prediction serving
    - Walk-forward validation
    - Hyperparameter optimization via Optuna
    """

    def __init__(self, db=None):
        self._db = db
        self._models: Dict[str, Any] = {}  # model_name -> trained model instance
        self._experiments: List[ExperimentRun] = []
        self._stats = {
            "models_trained": 0,
            "predictions_served": 0,
            "total_training_time_s": 0.0,
        }

    async def train_xgboost(self, X: np.ndarray, y: np.ndarray,
                            feature_names: List[str] = None,
                            params: Dict = None) -> Dict[str, Any]:
        """Train XGBoost direction classifier."""
        from brain.models_ml.gradient_boosting.xgboost_model import XGBoostDirectionModel

        experiment = ExperimentRun("xgboost_direction")

        try:
            model = XGBoostDirectionModel(params=params)
            experiment.params = model.params.copy()

            # Split for evaluation (last 20%)
            split = int(len(X) * 0.8)
            X_train, X_val = X[:split], X[split:]
            y_train, y_val = y[:split], y[split:]

            metrics = model.train(X_train, y_train, feature_names=feature_names,
                                  eval_set=(X_val, y_val))
            experiment.metrics = metrics
            experiment.status = "completed"

            # Save model
            model_path = MODELS_DIR / "xgboost_direction.pkl"
            with open(model_path, "wb") as f:
                pickle.dump(model, f)
            experiment.artifact_path = str(model_path)

            self._models["xgboost_direction"] = model
            logger.info("XGBoost trained: accuracy=%.4f, f1_macro=%.4f",
                        metrics.get("accuracy", 0), metrics.get("f1_macro", 0))

        except Exception as e:
            experiment.status = "failed"
            experiment.metrics["error"] = str(e)
            logger.exception("XGBoost training failed")

        experiment.completed_at = datetime.now(IST)
        experiment.duration_s = (experiment.completed_at - experiment.started_at).total_seconds()
        self._experiments.append(experiment)
        self._stats["models_trained"] += 1
        self._stats["total_training_time_s"] += experiment.duration_s or 0

        # Log to MongoDB
        await self._log_experiment(experiment)

        return experiment.to_dict()

    async def train_lightgbm(self, X: np.ndarray, y: np.ndarray,
                             feature_names: List[str] = None,
                             params: Dict = None) -> Dict[str, Any]:
        """Train LightGBM direction classifier."""
        from brain.models_ml.gradient_boosting.lightgbm_model import LightGBMDirectionModel

        experiment = ExperimentRun("lightgbm_direction")

        try:
            model = LightGBMDirectionModel(params=params)
            experiment.params = model.params.copy()

            split = int(len(X) * 0.8)
            X_train, X_val = X[:split], X[split:]
            y_train, y_val = y[:split], y[split:]

            metrics = model.train(X_train, y_train, feature_names=feature_names,
                                  eval_set=(X_val, y_val))
            experiment.metrics = metrics
            experiment.status = "completed"

            model_path = MODELS_DIR / "lightgbm_direction.pkl"
            with open(model_path, "wb") as f:
                pickle.dump(model, f)
            experiment.artifact_path = str(model_path)

            self._models["lightgbm_direction"] = model
            logger.info("LightGBM trained: accuracy=%.4f", metrics.get("accuracy", 0))

        except Exception as e:
            experiment.status = "failed"
            experiment.metrics["error"] = str(e)
            logger.exception("LightGBM training failed")

        experiment.completed_at = datetime.now(IST)
        experiment.duration_s = (experiment.completed_at - experiment.started_at).total_seconds()
        self._experiments.append(experiment)
        self._stats["models_trained"] += 1
        self._stats["total_training_time_s"] += experiment.duration_s or 0

        await self._log_experiment(experiment)
        return experiment.to_dict()

    async def train_garch(self, returns: np.ndarray) -> Dict[str, Any]:
        """Train GARCH(1,1) volatility model."""
        from brain.models_ml.statistical.garch_model import GARCHModel

        experiment = ExperimentRun("garch_volatility")

        try:
            model = GARCHModel(p=1, q=1, model_type="GARCH")
            # GARCHModel.train takes X (ignored) and y (returns)
            metrics = model.train(X=np.array([]), y=returns)
            experiment.metrics = {k: v for k, v in metrics.items()
                                  if not (isinstance(v, float) and (np.isnan(v) or np.isinf(v)))}
            experiment.status = "completed"

            model_path = MODELS_DIR / "garch_volatility.pkl"
            with open(model_path, "wb") as f:
                pickle.dump(model, f)
            experiment.artifact_path = str(model_path)

            self._models["garch_volatility"] = model
            logger.info("GARCH trained: aic=%.2f", metrics.get("aic", 0))

        except Exception as e:
            experiment.status = "failed"
            experiment.metrics["error"] = str(e)
            logger.exception("GARCH training failed")

        experiment.completed_at = datetime.now(IST)
        experiment.duration_s = (experiment.completed_at - experiment.started_at).total_seconds()
        self._experiments.append(experiment)
        self._stats["models_trained"] += 1

        await self._log_experiment(experiment)
        return experiment.to_dict()

    async def train_ensemble(self, X: np.ndarray, y: np.ndarray,
                             feature_names: List[str] = None) -> Dict[str, Any]:
        """Train the full gradient boosting ensemble (XGBoost + LightGBM)."""
        results = {
            "xgboost": await self.train_xgboost(X, y, feature_names),
            "lightgbm": await self.train_lightgbm(X, y, feature_names),
        }
        return results

    async def predict(self, model_name: str, X: np.ndarray) -> Dict[str, Any]:
        """Get prediction from a trained model."""
        model = self._models.get(model_name)

        if model is None:
            # Try loading from disk
            model = self._load_model(model_name)

        if model is None:
            return {"error": f"Model '{model_name}' not found or not trained"}

        try:
            if model_name == "garch_volatility":
                result = model.forecast(horizon=5)
                self._stats["predictions_served"] += 1
                return {
                    "model": model_name,
                    "prediction": result,
                }
            else:
                predictions = model.predict(X)
                probabilities = model.predict_proba(X) if hasattr(model, "predict_proba") else None
                self._stats["predictions_served"] += 1
                return {
                    "model": model_name,
                    "predictions": predictions.tolist() if isinstance(predictions, np.ndarray) else predictions,
                    "probabilities": probabilities.tolist() if probabilities is not None and isinstance(probabilities, np.ndarray) else probabilities,
                }
        except Exception as e:
            logger.exception("Prediction error for %s", model_name)
            return {"error": str(e)}

    def _load_model(self, model_name: str):
        """Load model from disk."""
        model_path = MODELS_DIR / f"{model_name}.pkl"
        if model_path.exists():
            try:
                with open(model_path, "rb") as f:
                    model = pickle.load(f)
                self._models[model_name] = model
                logger.info("Loaded model from %s", model_path)
                return model
            except Exception:
                logger.exception("Error loading model %s", model_name)
        return None

    async def _log_experiment(self, experiment: ExperimentRun):
        """Log experiment to MongoDB."""
        if self._db is None:
            return
        try:
            await self._db["brain_experiments"].insert_one(experiment.to_dict())
        except Exception:
            logger.debug("Failed to log experiment to MongoDB")

    def get_loaded_models(self) -> List[str]:
        """Get list of currently loaded model names."""
        return list(self._models.keys())

    def get_experiment_history(self, limit: int = 20) -> List[dict]:
        """Get recent experiment history."""
        return [e.to_dict() for e in reversed(self._experiments[-limit:])]

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "loaded_models": self.get_loaded_models(),
            "total_experiments": len(self._experiments),
        }
