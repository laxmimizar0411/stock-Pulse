"""
GARCH Volatility Forecasting Model

Wraps the ``arch`` library for GARCH / EGARCH conditional volatility
estimation.  Falls back gracefully when arch is not installed.
"""

import logging
import warnings
from typing import Any, Dict, Optional

import numpy as np

from brain.models_ml.base_model import BaseBrainModel

logger = logging.getLogger(__name__)

try:
    from arch import arch_model as _arch_model

    _HAS_ARCH = True
except ImportError:
    _HAS_ARCH = False
    logger.warning(
        "arch library not installed; GARCHModel will use a naive volatility fallback."
    )


class GARCHModel(BaseBrainModel):
    """
    GARCH / EGARCH volatility forecasting model.

    Args:
        p: GARCH lag order for conditional variance.
        q: ARCH lag order for squared residuals.
        model_type: ``"GARCH"`` or ``"EGARCH"``.
    """

    def __init__(
        self,
        p: int = 1,
        q: int = 1,
        model_type: str = "GARCH",
    ):
        super().__init__(model_name="garch", model_version="0.1.0")
        if model_type not in ("GARCH", "EGARCH"):
            raise ValueError(f"model_type must be 'GARCH' or 'EGARCH', got {model_type!r}")

        self.p = p
        self.q = q
        self.model_type = model_type
        self._fitted_result: Any = None
        self._last_returns: Optional[np.ndarray] = None
        self._current_vol: Optional[float] = None

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, X: np.ndarray, y: np.ndarray, **kwargs) -> Dict[str, float]:
        """
        Fit the GARCH model on a returns series.

        Args:
            X: Ignored.
            y: 1-D returns series (percentage or decimal).
            **kwargs: Passed to arch fitting routine.

        Returns:
            Training metrics (log_likelihood, aic, bic).
        """
        returns = np.asarray(y).flatten()
        self._last_returns = returns

        if not _HAS_ARCH:
            vol = float(np.std(returns)) if len(returns) > 0 else 0.0
            self._current_vol = vol
            metrics = {"log_likelihood": float("nan"), "aic": float("nan"), "bic": float("nan")}
            self._mark_trained(metrics)
            logger.warning("arch library unavailable; trained with naive fallback (std=%.4f).", vol)
            return metrics

        vol_model = "GARCH" if self.model_type == "GARCH" else "EGARCH"

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            am = _arch_model(
                returns * 100,  # arch expects percentage returns
                vol=vol_model,
                p=self.p,
                q=self.q,
                mean="Constant",
                dist="Normal",
            )
            self._fitted_result = am.fit(disp="off", **kwargs)

        cond_vol = self._fitted_result.conditional_volatility
        self._current_vol = float(cond_vol.iloc[-1] / 100) if len(cond_vol) > 0 else 0.0

        metrics = {
            "log_likelihood": float(self._fitted_result.loglikelihood),
            "aic": float(self._fitted_result.aic),
            "bic": float(self._fitted_result.bic),
        }
        self._mark_trained(metrics)
        logger.info(
            "%s(%d,%d) trained. AIC=%.2f, current_vol=%.4f",
            self.model_type, self.p, self.q, metrics["aic"], self._current_vol,
        )
        return metrics

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, X: Optional[np.ndarray] = None, horizon: int = 5) -> np.ndarray:
        """
        Forecast volatility for the next *horizon* periods.

        Args:
            X: Ignored.
            horizon: Number of periods ahead.

        Returns:
            1-D array of annualized volatility forecasts (or conditional std).
        """
        if _HAS_ARCH and self._fitted_result is not None:
            forecasts = self._fitted_result.forecast(horizon=horizon)
            # variance forecasts -> standard deviation, convert back from pct
            variance = forecasts.variance.iloc[-1].values
            vol = np.sqrt(variance) / 100.0
            return vol

        # Naive fallback: repeat current vol estimate
        if self._current_vol is not None:
            return np.full(horizon, self._current_vol)
        return np.zeros(horizon)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, X: np.ndarray, y: np.ndarray) -> Dict[str, float]:
        """
        Compare predicted volatility against realized volatility.

        Args:
            X: Ignored.
            y: Realized returns for the evaluation period.

        Returns:
            Dict with RMSE, MAE of predicted vs realized rolling volatility.
        """
        y_actual = np.asarray(y).flatten()
        horizon = len(y_actual)
        predicted_vol = self.predict(horizon=horizon)

        # Compute realized volatility as rolling std (window = min(20, horizon))
        window = min(20, horizon)
        if horizon >= window:
            realized_vol = np.array([
                np.std(y_actual[max(0, i - window + 1) : i + 1])
                for i in range(horizon)
            ])
        else:
            realized_vol = np.full(horizon, np.std(y_actual) if horizon > 0 else 0.0)

        residuals = predicted_vol[:horizon] - realized_vol
        rmse = float(np.sqrt(np.mean(residuals ** 2)))
        mae = float(np.mean(np.abs(residuals)))

        metrics = {"rmse": rmse, "mae": mae}
        logger.info("GARCH evaluation: %s", {k: f"{v:.6f}" for k, v in metrics.items()})
        return metrics

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def get_current_volatility(self) -> float:
        """
        Return the latest conditional volatility estimate.

        Returns:
            Current volatility as a decimal (e.g. 0.015 for 1.5%).
        """
        if self._current_vol is not None:
            return self._current_vol
        return 0.0

    # ------------------------------------------------------------------
    # Serialization hooks
    # ------------------------------------------------------------------

    def _get_state(self) -> Dict[str, Any]:
        return {
            "p": self.p,
            "q": self.q,
            "model_type": self.model_type,
            "fitted_result": self._fitted_result,
            "last_returns": self._last_returns,
            "current_vol": self._current_vol,
        }

    def _set_state(self, state: Dict[str, Any]) -> None:
        self.p = state.get("p", 1)
        self.q = state.get("q", 1)
        self.model_type = state.get("model_type", "GARCH")
        self._fitted_result = state.get("fitted_result")
        self._last_returns = state.get("last_returns")
        self._current_vol = state.get("current_vol")
