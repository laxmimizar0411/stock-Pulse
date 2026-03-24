"""
ARIMA Baseline Model

Univariate ARIMA model wrapping statsmodels for price/return forecasting.
Falls back gracefully when statsmodels is not installed.
"""

import logging
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import numpy as np

from brain.models_ml.base_model import BaseBrainModel

logger = logging.getLogger(__name__)

try:
    from statsmodels.tsa.arima.model import ARIMA as _StatsARIMA

    _HAS_STATSMODELS = True
except ImportError:
    _HAS_STATSMODELS = False
    logger.warning(
        "statsmodels not installed; ARIMAModel will use a naive fallback."
    )


class ARIMAModel(BaseBrainModel):
    """
    Univariate ARIMA model for time-series forecasting.

    Args:
        order: (p, d, q) ARIMA order.
        auto_order: If True and order is not specified, select order via AIC.
    """

    def __init__(
        self,
        order: Tuple[int, int, int] = (5, 1, 0),
        auto_order: bool = False,
    ):
        super().__init__(model_name="arima", model_version="0.1.0")
        self.order = order
        self.auto_order = auto_order
        self._fitted_model: Any = None
        self._last_series: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, X: np.ndarray, y: np.ndarray, **kwargs) -> Dict[str, float]:
        """
        Fit the ARIMA model.

        Args:
            X: Ignored for univariate ARIMA.
            y: 1-D price or returns series.
            **kwargs: Passed to statsmodels ARIMA.fit().

        Returns:
            Training metrics (AIC, BIC).
        """
        series = np.asarray(y).flatten()
        self._last_series = series

        if not _HAS_STATSMODELS:
            metrics = {"aic": float("nan"), "bic": float("nan")}
            self._mark_trained(metrics)
            logger.warning("statsmodels unavailable; trained with naive fallback.")
            return metrics

        if self.auto_order:
            self.order = self._select_order(series)
            logger.info("Auto-selected ARIMA order: %s", self.order)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = _StatsARIMA(series, order=self.order)
            self._fitted_model = model.fit()

        metrics = {
            "aic": float(self._fitted_model.aic),
            "bic": float(self._fitted_model.bic),
        }
        self._mark_trained(metrics)
        logger.info("ARIMA%s trained. AIC=%.2f BIC=%.2f", self.order, metrics["aic"], metrics["bic"])
        return metrics

    def _select_order(self, series: np.ndarray) -> Tuple[int, int, int]:
        """Simple AIC-based order selection over a small grid."""
        best_aic = float("inf")
        best_order = (1, 1, 0)

        for p in range(0, 6):
            for q in range(0, 3):
                for d in (0, 1):
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore")
                            fit = _StatsARIMA(series, order=(p, d, q)).fit()
                            if fit.aic < best_aic:
                                best_aic = fit.aic
                                best_order = (p, d, q)
                    except Exception:
                        continue

        return best_order

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, X: Optional[np.ndarray] = None, steps: int = 5) -> np.ndarray:
        """
        Forecast the next *steps* periods.

        Args:
            X: Ignored.
            steps: Number of periods to forecast.

        Returns:
            1-D array of forecasted values.
        """
        if _HAS_STATSMODELS and self._fitted_model is not None:
            forecast = self._fitted_model.forecast(steps=steps)
            return np.asarray(forecast)

        # Naive fallback: repeat last value
        if self._last_series is not None and len(self._last_series) > 0:
            return np.full(steps, self._last_series[-1])
        return np.zeros(steps)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, X: np.ndarray, y: np.ndarray) -> Dict[str, float]:
        """
        Evaluate forecast accuracy on held-out data.

        Args:
            X: Ignored.
            y: True values for the forecast horizon.

        Returns:
            Dict with RMSE, MAE, MAPE.
        """
        y_true = np.asarray(y).flatten()
        y_pred = self.predict(steps=len(y_true))

        residuals = y_true - y_pred
        rmse = float(np.sqrt(np.mean(residuals ** 2)))
        mae = float(np.mean(np.abs(residuals)))

        # MAPE: avoid division by zero
        nonzero = np.abs(y_true) > 1e-8
        if nonzero.any():
            mape = float(np.mean(np.abs(residuals[nonzero] / y_true[nonzero])) * 100)
        else:
            mape = float("nan")

        metrics = {"rmse": rmse, "mae": mae, "mape": mape}
        logger.info("ARIMA evaluation: %s", {k: f"{v:.4f}" for k, v in metrics.items()})
        return metrics

    # ------------------------------------------------------------------
    # Serialization hooks
    # ------------------------------------------------------------------

    def _get_state(self) -> Dict[str, Any]:
        return {
            "order": self.order,
            "auto_order": self.auto_order,
            "fitted_model": self._fitted_model,
            "last_series": self._last_series,
        }

    def _set_state(self, state: Dict[str, Any]) -> None:
        self.order = state.get("order", (5, 1, 0))
        self.auto_order = state.get("auto_order", False)
        self._fitted_model = state.get("fitted_model")
        self._last_series = state.get("last_series")
