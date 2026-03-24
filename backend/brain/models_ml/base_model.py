"""
Base Brain ML Model

Abstract base class for all Brain ML models. Provides a consistent
interface for training, prediction, evaluation, and serialization.
"""

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

try:
    import joblib
except ImportError:
    joblib = None  # type: ignore[assignment]

import pickle

from brain.config import get_brain_config

logger = logging.getLogger(__name__)


class BaseBrainModel(ABC):
    """Abstract base class for all Brain ML models."""

    def __init__(
        self,
        model_name: str = "unnamed",
        model_version: str = "0.1.0",
    ):
        self.model_name: str = model_name
        self.model_version: str = model_version
        self.trained_at: Optional[datetime] = None
        self.metrics: Dict[str, float] = {}
        self._config = get_brain_config()

    @abstractmethod
    def train(self, X: np.ndarray, y: np.ndarray, **kwargs) -> Dict[str, float]:
        """
        Train the model on the given data.

        Args:
            X: Feature matrix (n_samples, n_features).
            y: Target array (n_samples,).
            **kwargs: Additional training parameters.

        Returns:
            Dictionary of training metrics.
        """
        ...

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Generate predictions for the given input.

        Args:
            X: Feature matrix (n_samples, n_features).

        Returns:
            Predictions array.
        """
        ...

    @abstractmethod
    def evaluate(self, X: np.ndarray, y: np.ndarray) -> Dict[str, float]:
        """
        Evaluate the model on the given data.

        Args:
            X: Feature matrix.
            y: True target values.

        Returns:
            Dictionary of evaluation metrics.
        """
        ...

    def save(self, path: Optional[str] = None) -> str:
        """
        Save the model to disk using joblib.

        Args:
            path: File path. If None, uses default storage path from config.

        Returns:
            The path the model was saved to.
        """
        if path is None:
            storage_dir = self._config.model_storage_path
            os.makedirs(storage_dir, exist_ok=True)
            path = os.path.join(
                storage_dir,
                f"{self.model_name}_v{self.model_version}.joblib",
            )
        else:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        state = {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "trained_at": self.trained_at,
            "metrics": self.metrics,
            "class_name": self.__class__.__name__,
            "model_state": self._get_state(),
        }

        if joblib is not None:
            joblib.dump(state, path)
        else:
            with open(path, "wb") as fh:
                pickle.dump(state, fh)
        logger.info(
            "Saved model '%s' v%s to %s", self.model_name, self.model_version, path
        )
        return path

    @classmethod
    def load(cls, path: str) -> "BaseBrainModel":
        """
        Load a model from disk.

        Args:
            path: Path to the saved model file.

        Returns:
            An instance of the model.

        Raises:
            FileNotFoundError: If the path does not exist.
            ValueError: If the saved class does not match.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model file not found: {path}")

        if joblib is not None:
            state = joblib.load(path)
        else:
            with open(path, "rb") as fh:
                state = pickle.load(fh)

        # Create a new instance via the subclass
        instance = cls.__new__(cls)
        instance.model_name = state["model_name"]
        instance.model_version = state["model_version"]
        instance.trained_at = state["trained_at"]
        instance.metrics = state.get("metrics", {})
        instance._config = get_brain_config()
        instance._set_state(state["model_state"])

        logger.info(
            "Loaded model '%s' v%s from %s",
            instance.model_name,
            instance.model_version,
            path,
        )
        return instance

    def get_info(self) -> Dict[str, Any]:
        """Return model metadata dictionary."""
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "class": self.__class__.__name__,
            "trained_at": self.trained_at.isoformat() if self.trained_at else None,
            "metrics": self.metrics,
        }

    # ------------------------------------------------------------------
    # Subclass hooks for serialization
    # ------------------------------------------------------------------

    def _get_state(self) -> Dict[str, Any]:
        """
        Return internal state for serialization. Subclasses should override
        this to include their fitted model objects.
        """
        return {}

    def _set_state(self, state: Dict[str, Any]) -> None:
        """
        Restore internal state from a loaded dict. Subclasses should override.
        """
        pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mark_trained(self, metrics: Dict[str, float]) -> None:
        """Record training timestamp and metrics."""
        self.trained_at = datetime.now(timezone.utc)
        self.metrics = metrics

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"name={self.model_name!r} version={self.model_version!r} "
            f"trained={self.trained_at is not None}>"
        )
