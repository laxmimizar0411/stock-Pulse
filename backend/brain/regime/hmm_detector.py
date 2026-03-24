"""
HMM-Based Market Regime Detector

Uses a 3-state Gaussian Hidden Markov Model to classify the market into
BULL, BEAR, or SIDEWAYS regimes.  Falls back to a simple rule-based
detector when hmmlearn is not installed.
"""

import logging
import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from brain.config import RegimeConfig, get_brain_config
from brain.models.events import MarketRegime

try:
    from hmmlearn.hmm import GaussianHMM

    _HAS_HMMLEARN = True
except ImportError:
    _HAS_HMMLEARN = False

try:
    import joblib
except ImportError:
    joblib = None  # type: ignore[assignment]

import pickle

logger = logging.getLogger(__name__)


class HMMRegimeDetector:
    """
    3-state Gaussian HMM regime detector.

    Feature columns (by convention):
        0 - daily_returns
        1 - rolling_volatility_20d
        2 - vix
        3 - fii_dii_flow_momentum

    After training, HMM states are mapped to MarketRegime values:
        - Highest mean return  -> BULL
        - Lowest mean return   -> BEAR
        - Middle               -> SIDEWAYS
    """

    def __init__(self, config: Optional[RegimeConfig] = None):
        self._config = config or get_brain_config().regime
        self.n_states: int = self._config.n_states
        self.model: Any = None  # GaussianHMM or None
        self._regime_map: Dict[int, MarketRegime] = {}
        self._trained: bool = False
        self._use_hmm: bool = _HAS_HMMLEARN

        if not _HAS_HMMLEARN:
            logger.warning(
                "hmmlearn not installed; falling back to rule-based regime detection."
            )

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, features: np.ndarray) -> None:
        """
        Train the HMM on a feature matrix.

        Args:
            features: Array of shape (n_samples, n_features).
                      Columns: daily_returns, rolling_vol_20d, vix, fii_dii_flow.
        """
        if features.ndim == 1:
            features = features.reshape(-1, 1)

        if self._use_hmm:
            self._train_hmm(features)
        else:
            logger.info("Rule-based detector does not require training.")
            self._trained = True

    def _train_hmm(self, features: np.ndarray) -> None:
        """Fit a GaussianHMM and map states to regimes."""
        self.model = GaussianHMM(
            n_components=self.n_states,
            covariance_type="full",
            n_iter=200,
            random_state=42,
            tol=1e-4,
        )

        self.model.fit(features)
        self._map_states_to_regimes()
        self._trained = True
        logger.info(
            "HMM trained on %d observations with %d states.",
            features.shape[0],
            self.n_states,
        )

    def _map_states_to_regimes(self) -> None:
        """
        Map HMM hidden-state indices to MarketRegime based on the mean
        of the first feature (daily returns).
        """
        means = self.model.means_[:, 0]  # first column = daily_returns
        sorted_indices = np.argsort(means)

        # Lowest mean -> BEAR, middle -> SIDEWAYS, highest -> BULL
        self._regime_map = {
            int(sorted_indices[0]): MarketRegime.BEAR,
            int(sorted_indices[-1]): MarketRegime.BULL,
        }
        for idx in sorted_indices[1:-1]:
            self._regime_map[int(idx)] = MarketRegime.SIDEWAYS

        logger.info("State-to-regime mapping: %s", self._regime_map)

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict_regime(
        self, features: np.ndarray
    ) -> Tuple[MarketRegime, Dict[str, float]]:
        """
        Predict the current market regime.

        Args:
            features: Feature matrix. The last row is used for prediction.

        Returns:
            Tuple of (regime, probability_dict) where probability_dict has
            keys ``bull_prob``, ``bear_prob``, ``sideways_prob``.
        """
        if features.ndim == 1:
            features = features.reshape(-1, 1)

        if self._use_hmm and self._trained and self.model is not None:
            return self._predict_hmm(features)
        return self._predict_rule_based(features)

    def _predict_hmm(
        self, features: np.ndarray
    ) -> Tuple[MarketRegime, Dict[str, float]]:
        """Predict using the trained HMM."""
        posteriors = self.model.predict_proba(features)
        last_probs = posteriors[-1]

        # Aggregate probabilities per regime
        prob_dict: Dict[str, float] = {
            "bull_prob": 0.0,
            "bear_prob": 0.0,
            "sideways_prob": 0.0,
        }
        for state_idx, regime in self._regime_map.items():
            key = f"{regime.value}_prob"
            prob_dict[key] += float(last_probs[state_idx])

        # Determine current regime from most-probable state
        current_state = int(np.argmax(last_probs))
        current_regime = self._regime_map.get(current_state, MarketRegime.SIDEWAYS)

        return current_regime, prob_dict

    def _predict_rule_based(
        self, features: np.ndarray
    ) -> Tuple[MarketRegime, Dict[str, float]]:
        """
        Rule-based fallback when hmmlearn is unavailable.

        Rules (using the last row of features):
            - BULL:  50-day SMA slope (approx. from returns) positive AND VIX < 20
            - BEAR:  slope negative AND VIX > 22
            - SIDEWAYS: otherwise

        The slope is approximated by the mean of the last 50 daily returns
        (column 0).  VIX is column 2.
        """
        n = features.shape[0]
        lookback = min(50, n)
        recent_returns = features[-lookback:, 0]
        slope = float(np.mean(recent_returns))

        # VIX: use column 2 if available, else assume neutral
        vix = float(features[-1, 2]) if features.shape[1] > 2 else 18.0

        if slope > 0 and vix < 20:
            regime = MarketRegime.BULL
            probs = {"bull_prob": 0.60, "bear_prob": 0.10, "sideways_prob": 0.30}
        elif slope < 0 and vix > 22:
            regime = MarketRegime.BEAR
            probs = {"bull_prob": 0.10, "bear_prob": 0.60, "sideways_prob": 0.30}
        else:
            regime = MarketRegime.SIDEWAYS
            probs = {"bull_prob": 0.25, "bear_prob": 0.25, "sideways_prob": 0.50}

        return regime, probs

    # ------------------------------------------------------------------
    # Transition matrix
    # ------------------------------------------------------------------

    def get_transition_matrix(self) -> np.ndarray:
        """
        Return the HMM transition matrix (n_states x n_states).

        Falls back to an identity-like matrix for rule-based mode.
        """
        if self._use_hmm and self.model is not None:
            return self.model.transmat_.copy()

        # Fallback: equal-probability transition matrix
        mat = np.full((self.n_states, self.n_states), 1.0 / self.n_states)
        return mat

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_regime_history(
        self,
        features: np.ndarray,
        dates: Optional[List[date]] = None,
    ) -> List[Tuple[date, MarketRegime, Dict[str, float]]]:
        """
        Decode regime for every row and return a time-indexed history.

        Args:
            features: Feature matrix (n_samples, n_features).
            dates: Optional list of dates aligned with feature rows.
                   If not provided, sequential date indices are generated.

        Returns:
            List of (date, regime, probability_dict) tuples.
        """
        if features.ndim == 1:
            features = features.reshape(-1, 1)

        n = features.shape[0]

        if dates is None:
            from datetime import timedelta

            base = date.today()
            dates = [base - timedelta(days=n - 1 - i) for i in range(n)]

        history: List[Tuple[date, MarketRegime, Dict[str, float]]] = []

        if self._use_hmm and self._trained and self.model is not None:
            posteriors = self.model.predict_proba(features)
            states = self.model.predict(features)

            for i in range(n):
                probs = posteriors[i]
                prob_dict: Dict[str, float] = {
                    "bull_prob": 0.0,
                    "bear_prob": 0.0,
                    "sideways_prob": 0.0,
                }
                for state_idx, regime in self._regime_map.items():
                    key = f"{regime.value}_prob"
                    prob_dict[key] += float(probs[state_idx])

                regime = self._regime_map.get(int(states[i]), MarketRegime.SIDEWAYS)
                history.append((dates[i], regime, prob_dict))
        else:
            # Rule-based: evaluate each point using a rolling window
            for i in range(n):
                window = features[max(0, i - 49) : i + 1]
                regime, probs = self._predict_rule_based(window)
                history.append((dates[i], regime, probs))

        return history

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Save detector state to disk."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        state = {
            "n_states": self.n_states,
            "use_hmm": self._use_hmm,
            "trained": self._trained,
            "regime_map": {k: v.value for k, v in self._regime_map.items()},
            "model": self.model,
        }
        if joblib is not None:
            joblib.dump(state, path)
        else:
            with open(path, "wb") as fh:
                pickle.dump(state, fh)
        logger.info("HMMRegimeDetector saved to %s", path)

    def load(self, path: str) -> None:
        """Load detector state from disk."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Detector file not found: {path}")

        if joblib is not None:
            state = joblib.load(path)
        else:
            with open(path, "rb") as fh:
                state = pickle.load(fh)
        self.n_states = state["n_states"]
        self._use_hmm = state["use_hmm"] and _HAS_HMMLEARN
        self._trained = state["trained"]
        self._regime_map = {
            int(k): MarketRegime(v) for k, v in state["regime_map"].items()
        }
        self.model = state["model"]
        logger.info("HMMRegimeDetector loaded from %s", path)
