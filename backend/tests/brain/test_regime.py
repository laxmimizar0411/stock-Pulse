"""
Tests for Phase 3.1 — HMM Market Regime Detection.

Covers:
- HMM detector training and prediction
- K-Means / GMM detectors
- CUSUM change-point detection
- Regime Router model weighting
- Position Sizer with Kelly Criterion and drawdown rules
- Ensemble consensus logic
"""

import sys
from pathlib import Path

import numpy as np
import pytest

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.models.events import MarketRegime, SignalTimeframe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bull_features(n: int = 300) -> np.ndarray:
    """Simulate bull market: positive returns, low volatility."""
    rng = np.random.RandomState(42)
    daily_returns = rng.normal(0.001, 0.008, n)       # slightly positive mean
    rolling_vol = rng.uniform(0.005, 0.012, n)         # low vol
    vix = rng.uniform(10, 18, n)                       # low VIX
    fii_dii = rng.uniform(500, 2000, n)                # positive FII flows
    inr_usd = rng.uniform(0.011, 0.013, n)             # stable INR
    return np.column_stack([daily_returns, rolling_vol, vix, fii_dii, inr_usd])


def _make_bear_features(n: int = 300) -> np.ndarray:
    """Simulate bear market: negative returns, high volatility."""
    rng = np.random.RandomState(99)
    daily_returns = rng.normal(-0.002, 0.02, n)        # negative mean
    rolling_vol = rng.uniform(0.015, 0.035, n)         # high vol
    vix = rng.uniform(25, 40, n)                       # high VIX (>22 threshold)
    fii_dii = rng.uniform(-3000, -500, n)              # FII outflows
    inr_usd = rng.uniform(0.010, 0.012, n)             # weakening INR
    return np.column_stack([daily_returns, rolling_vol, vix, fii_dii, inr_usd])


def _make_mixed_features(n: int = 600) -> np.ndarray:
    """Simulate mixed market with regime transitions."""
    bull = _make_bull_features(n // 3)
    bear = _make_bear_features(n // 3)
    sideways_rng = np.random.RandomState(55)
    sideways_n = n - 2 * (n // 3)
    sideways = np.column_stack([
        sideways_rng.normal(0.0, 0.01, sideways_n),
        sideways_rng.uniform(0.008, 0.015, sideways_n),
        sideways_rng.uniform(14, 22, sideways_n),
        sideways_rng.uniform(-500, 500, sideways_n),
        sideways_rng.uniform(0.011, 0.013, sideways_n),
    ])
    return np.vstack([bull, sideways, bear])


# ===========================================================================
# HMM Detector Tests
# ===========================================================================

class TestHMMRegimeDetector:

    def test_init_defaults(self):
        from brain.regime.hmm_detector import HMMRegimeDetector
        det = HMMRegimeDetector()
        assert det.n_states == 3
        assert det._trained is False

    def test_rule_based_fallback_bull(self):
        """Rule-based detector should identify bull conditions."""
        from brain.regime.hmm_detector import HMMRegimeDetector
        det = HMMRegimeDetector()
        det._use_hmm = False  # force rule-based
        det._trained = True

        features = _make_bull_features(100)
        regime, probs = det.predict_regime(features)

        assert regime == MarketRegime.BULL
        assert probs["bull_prob"] > probs["bear_prob"]

    def test_rule_based_fallback_bear(self):
        """Rule-based detector should identify bear conditions."""
        from brain.regime.hmm_detector import HMMRegimeDetector
        det = HMMRegimeDetector()
        det._use_hmm = False
        det._trained = True

        # Construct clearly bearish data: strongly negative returns + high VIX
        n = 100
        features = np.column_stack([
            np.full(n, -0.01),              # clearly negative returns
            np.full(n, 0.03),               # high volatility
            np.full(n, 30.0),               # VIX > 22
            np.zeros(n),                    # FII flow
            np.full(n, 0.012),              # INR/USD
        ])
        regime, probs = det.predict_regime(features)

        assert regime == MarketRegime.BEAR
        assert probs["bear_prob"] > probs["bull_prob"]

    def test_train_and_predict(self):
        """Train HMM on mixed data and verify it returns valid regimes."""
        from brain.regime.hmm_detector import HMMRegimeDetector, _HAS_HMMLEARN
        if not _HAS_HMMLEARN:
            pytest.skip("hmmlearn not installed")

        det = HMMRegimeDetector()
        features = _make_mixed_features(600)
        det.train(features)

        assert det._trained is True
        assert len(det._regime_map) == 3

        # Predict on bull segment
        regime, probs = det.predict_regime(_make_bull_features(100))
        assert regime in (MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS)
        assert abs(sum(probs.values()) - 1.0) < 0.05  # probabilities sum to ~1

    def test_transition_matrix(self):
        """Transition matrix should be valid stochastic matrix."""
        from brain.regime.hmm_detector import HMMRegimeDetector
        det = HMMRegimeDetector()
        mat = det.get_transition_matrix()
        assert mat.shape == (3, 3)
        # Each row sums to ~1
        for row in mat:
            assert abs(sum(row) - 1.0) < 0.01

    def test_regime_history(self):
        """get_regime_history should return entries for all rows."""
        from brain.regime.hmm_detector import HMMRegimeDetector
        det = HMMRegimeDetector()
        det._use_hmm = False
        det._trained = True

        features = _make_bull_features(50)
        history = det.get_regime_history(features)

        assert len(history) == 50
        for dt, regime, probs in history:
            assert regime in (MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS)

    def test_save_and_load(self, tmp_path):
        """Verify save/load roundtrip preserves state."""
        from brain.regime.hmm_detector import HMMRegimeDetector
        det = HMMRegimeDetector()
        det._use_hmm = False
        det._trained = True

        path = str(tmp_path / "hmm_model.pkl")
        det.save(path)

        det2 = HMMRegimeDetector()
        det2.load(path)
        assert det2._trained is True
        assert det2.n_states == 3


# ===========================================================================
# K-Means Detector Tests
# ===========================================================================

class TestKMeansRegimeDetector:

    def test_init(self):
        from brain.regime.kmeans_gmm_detector import KMeansRegimeDetector
        det = KMeansRegimeDetector(n_clusters=3)
        assert det.n_clusters == 3
        assert det._trained is False

    def test_train_and_predict(self):
        from brain.regime.kmeans_gmm_detector import KMeansRegimeDetector, _HAS_SKLEARN
        if not _HAS_SKLEARN:
            pytest.skip("scikit-learn not installed")

        det = KMeansRegimeDetector()
        features = _make_mixed_features(600)
        det.train(features)

        assert det._trained is True
        assert len(det._cluster_to_regime) == 3

        regime, probs = det.predict_regime(_make_bull_features(50))
        assert regime in (MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS)
        assert "bull_prob" in probs

    def test_untrained_returns_sideways(self):
        from brain.regime.kmeans_gmm_detector import KMeansRegimeDetector
        det = KMeansRegimeDetector()
        regime, probs = det.predict_regime(np.zeros((10, 5)))
        assert regime == MarketRegime.SIDEWAYS


# ===========================================================================
# GMM Detector Tests
# ===========================================================================

class TestGMMRegimeDetector:

    def test_train_and_predict(self):
        from brain.regime.kmeans_gmm_detector import GMMRegimeDetector, _HAS_SKLEARN
        if not _HAS_SKLEARN:
            pytest.skip("scikit-learn not installed")

        det = GMMRegimeDetector()
        features = _make_mixed_features(600)
        det.train(features)

        assert det._trained is True
        assert len(det._component_to_regime) == 3

        regime, probs = det.predict_regime(_make_bear_features(50))
        assert regime in (MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS)

        # GMM provides soft probabilities that sum to ~1
        total = probs["bull_prob"] + probs["bear_prob"] + probs["sideways_prob"]
        assert abs(total - 1.0) < 0.05


# ===========================================================================
# CUSUM Detector Tests
# ===========================================================================

class TestCUSUMDetector:

    def test_init(self):
        from brain.regime.cusum_detector import CUSUMDetector
        det = CUSUMDetector(window_size=50, threshold_multiplier=4.0)
        assert det._initialized is False
        assert det._current_regime == MarketRegime.SIDEWAYS

    def test_needs_window_to_initialize(self):
        from brain.regime.cusum_detector import CUSUMDetector
        det = CUSUMDetector(window_size=10)

        # Not enough data yet
        for i in range(9):
            changed, _ = det.update(0.001, 0.01)
            assert changed is False
            assert det._initialized is False

        # 10th observation should initialize
        changed, _ = det.update(0.001, 0.01)
        assert det._initialized is True

    def test_detects_return_increase(self):
        """Large positive returns should trigger change detection."""
        from brain.regime.cusum_detector import CUSUMDetector
        det = CUSUMDetector(window_size=20, threshold_multiplier=3.0)

        # Initialize with normal returns
        rng = np.random.RandomState(42)
        for _ in range(20):
            det.update(rng.normal(0, 0.01), 0.01)

        # Now inject large positive returns
        detected = False
        for _ in range(50):
            changed, change_type = det.update(0.05, 0.01)
            if changed:
                detected = True
                assert change_type == "return_increase"
                break

        assert detected, "CUSUM should detect large return increase"

    def test_detects_return_decrease(self):
        """Large negative returns should trigger change detection."""
        from brain.regime.cusum_detector import CUSUMDetector
        det = CUSUMDetector(window_size=20, threshold_multiplier=3.0)

        rng = np.random.RandomState(42)
        for _ in range(20):
            det.update(rng.normal(0, 0.01), 0.01)

        detected = False
        for _ in range(50):
            changed, change_type = det.update(-0.05, 0.01)
            if changed:
                detected = True
                assert change_type == "return_decrease"
                break

        assert detected, "CUSUM should detect large return decrease"

    def test_detects_volatility_spike(self):
        """Sudden volatility increase should trigger detection."""
        from brain.regime.cusum_detector import CUSUMDetector
        det = CUSUMDetector(window_size=20, threshold_multiplier=3.0)

        # Normal vol baseline
        for _ in range(20):
            det.update(0.0, 0.01)

        # Inject high volatility
        detected = False
        for _ in range(50):
            changed, change_type = det.update(0.0, 0.10)
            if changed:
                detected = True
                assert change_type == "volatility_spike"
                break

        assert detected, "CUSUM should detect volatility spike"

    def test_suggest_regime(self):
        from brain.regime.cusum_detector import CUSUMDetector
        det = CUSUMDetector()
        assert det.suggest_regime("return_increase") == MarketRegime.BULL
        assert det.suggest_regime("return_decrease") == MarketRegime.BEAR
        assert det.suggest_regime("volatility_spike") == MarketRegime.BEAR
        assert det.suggest_regime(None) == MarketRegime.SIDEWAYS

    def test_get_statistics(self):
        from brain.regime.cusum_detector import CUSUMDetector
        det = CUSUMDetector()
        stats = det.get_statistics()
        assert "initialized" in stats
        assert "current_regime" in stats
        assert stats["initialized"] is False

    def test_reset(self):
        from brain.regime.cusum_detector import CUSUMDetector
        det = CUSUMDetector(window_size=5)
        for _ in range(10):
            det.update(0.01, 0.01)
        assert det._initialized is True

        det.reset()
        assert det._initialized is False
        assert len(det._return_window) == 0


# ===========================================================================
# Regime Router Tests
# ===========================================================================

class TestRegimeRouter:

    def test_init(self):
        from brain.regime.regime_router import RegimeRouter
        router = RegimeRouter(model_manager=None)
        assert len(router.regime_model_weights) == 3

    def test_bull_weights_favor_xgboost(self):
        from brain.regime.regime_router import RegimeRouter
        router = RegimeRouter()
        weights = router.get_regime_weights(MarketRegime.BULL)
        assert weights["xgboost_direction"] > weights["garch_volatility"]

    def test_bear_weights_favor_garch(self):
        from brain.regime.regime_router import RegimeRouter
        router = RegimeRouter()
        weights = router.get_regime_weights(MarketRegime.BEAR)
        assert weights["garch_volatility"] > weights["xgboost_direction"]

    def test_sideways_weights_balanced(self):
        from brain.regime.regime_router import RegimeRouter
        router = RegimeRouter()
        weights = router.get_regime_weights(MarketRegime.SIDEWAYS)
        assert weights["xgboost_direction"] == weights["lightgbm_direction"]

    def test_blend_predictions(self):
        from brain.regime.regime_router import RegimeRouter
        router = RegimeRouter()

        predictions = {
            "xgboost_direction": [2.0],   # BUY
            "lightgbm_direction": [2.0],  # BUY
            "garch_volatility": [1.0],    # HOLD
        }
        weights = {"xgboost_direction": 0.5, "lightgbm_direction": 0.35, "garch_volatility": 0.15}
        blended = router._blend_predictions(predictions, weights)

        # (2*0.5 + 2*0.35 + 1*0.15) / 1.0 = 1.85
        assert abs(blended - 1.85) < 0.01

    def test_prediction_to_direction(self):
        from brain.regime.regime_router import RegimeRouter
        router = RegimeRouter()
        assert router._prediction_to_direction(2.0) == "BUY"
        assert router._prediction_to_direction(0.0) == "SELL"
        assert router._prediction_to_direction(1.0) == "HOLD"

    def test_no_model_manager_returns_error(self):
        import asyncio
        from brain.regime.regime_router import RegimeRouter
        router = RegimeRouter(model_manager=None)
        result = asyncio.get_event_loop().run_until_complete(
            router.route_prediction(np.zeros((1, 5)), MarketRegime.BULL)
        )
        assert "error" in result

    def test_update_regime_weights_normalizes(self):
        from brain.regime.regime_router import RegimeRouter
        router = RegimeRouter()
        router.update_regime_weights(MarketRegime.BULL, {
            "xgboost_direction": 2.0,
            "lightgbm_direction": 1.0,
            "garch_volatility": 1.0,
        })
        weights = router.get_regime_weights(MarketRegime.BULL)
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01

    def test_get_stats(self):
        from brain.regime.regime_router import RegimeRouter
        router = RegimeRouter()
        stats = router.get_stats()
        assert "routing_calls" in stats
        assert "regime_strategies" in stats


# ===========================================================================
# Position Sizer Tests
# ===========================================================================

class TestPositionSizer:

    def test_init_defaults(self):
        from brain.regime.position_sizer import PositionSizer
        sizer = PositionSizer()
        state = sizer.get_current_state()
        assert state["kelly_fraction_default"] == 0.5
        assert state["kelly_fraction_bear"] == 0.25
        assert state["kill_switch_active"] is False

    def test_basic_position_size(self):
        from brain.regime.position_sizer import PositionSizer
        sizer = PositionSizer()
        result = sizer.calculate_position_size(
            signal_confidence=70.0,
            win_rate=0.55,
            risk_reward_ratio=2.0,
            entry_price=100.0,
            stop_loss=95.0,
            regime=MarketRegime.BULL,
            timeframe=SignalTimeframe.SWING,
        )
        assert result["position_size_pct"] >= 0
        assert result["kelly_fraction"] == 0.5  # Half Kelly in bull
        assert result["capital_at_risk"] == 5.0  # 100 - 95
        assert result["regime"] == "bull"

    def test_bear_regime_uses_quarter_kelly(self):
        from brain.regime.position_sizer import PositionSizer
        sizer = PositionSizer()
        result = sizer.calculate_position_size(
            signal_confidence=70.0,
            win_rate=0.55,
            risk_reward_ratio=2.0,
            entry_price=100.0,
            stop_loss=95.0,
            regime=MarketRegime.BEAR,
        )
        assert result["kelly_fraction"] == 0.25  # Quarter Kelly in bear

    def test_drawdown_10pct_halves_positions(self):
        from brain.regime.position_sizer import PositionSizer
        sizer = PositionSizer()
        sizer.update_account_value(100000)  # peak

        # Drop to 89000 = 11% drawdown
        sizer.update_account_value(89000)
        assert sizer._positions_halved is True

        result = sizer.calculate_position_size(
            signal_confidence=80.0,
            win_rate=0.6,
            risk_reward_ratio=2.0,
            entry_price=100.0,
            stop_loss=95.0,
            regime=MarketRegime.BULL,
        )
        assert result["positions_halved"] is True

    def test_drawdown_15pct_halts_entries(self):
        from brain.regime.position_sizer import PositionSizer
        sizer = PositionSizer()
        sizer.update_account_value(100000)
        sizer.update_account_value(84000)  # 16% drawdown
        assert sizer._new_entries_halted is True

        result = sizer.calculate_position_size(
            signal_confidence=80.0,
            win_rate=0.6,
            risk_reward_ratio=2.0,
            entry_price=100.0,
            stop_loss=95.0,
        )
        assert result["position_size_pct"] == 0.0
        assert "halted" in result["reason"].lower()

    def test_drawdown_20pct_kill_switch(self):
        from brain.regime.position_sizer import PositionSizer
        sizer = PositionSizer()
        sizer.update_account_value(100000)
        sizer.update_account_value(79000)  # 21% drawdown
        assert sizer._kill_switch_active is True

        result = sizer.calculate_position_size(
            signal_confidence=90.0,
            win_rate=0.7,
            risk_reward_ratio=3.0,
            entry_price=100.0,
            stop_loss=90.0,
        )
        assert result["position_size_pct"] == 0.0
        assert "kill switch" in result["reason"].lower()

    def test_new_peak_resets_drawdown_flags(self):
        from brain.regime.position_sizer import PositionSizer
        sizer = PositionSizer()
        sizer.update_account_value(100000)
        sizer.update_account_value(89000)  # trigger halve
        assert sizer._positions_halved is True

        sizer.update_account_value(105000)  # new peak
        assert sizer._positions_halved is False
        assert sizer._peak_value == 105000

    def test_atr_multipliers(self):
        from brain.regime.position_sizer import PositionSizer
        sizer = PositionSizer()

        result_day = sizer.calculate_position_size(
            signal_confidence=70.0, win_rate=0.55, risk_reward_ratio=2.0,
            entry_price=100.0, stop_loss=95.0,
            timeframe=SignalTimeframe.INTRADAY,
        )
        assert result_day["atr_multiplier"] == 2.0

        result_swing = sizer.calculate_position_size(
            signal_confidence=70.0, win_rate=0.55, risk_reward_ratio=2.0,
            entry_price=100.0, stop_loss=95.0,
            timeframe=SignalTimeframe.SWING,
        )
        assert result_swing["atr_multiplier"] == 2.5

        result_pos = sizer.calculate_position_size(
            signal_confidence=70.0, win_rate=0.55, risk_reward_ratio=2.0,
            entry_price=100.0, stop_loss=95.0,
            timeframe=SignalTimeframe.POSITIONAL,
        )
        assert result_pos["atr_multiplier"] == 3.5

    def test_zero_win_rate_returns_zero(self):
        from brain.regime.position_sizer import PositionSizer
        sizer = PositionSizer()
        result = sizer.calculate_position_size(
            signal_confidence=80.0, win_rate=0.0, risk_reward_ratio=2.0,
            entry_price=100.0, stop_loss=95.0,
        )
        assert result["position_size_pct"] == 0.0

    def test_manual_reset_drawdown_flags(self):
        from brain.regime.position_sizer import PositionSizer
        sizer = PositionSizer()
        sizer._kill_switch_active = True
        sizer.reset_drawdown_flags()
        assert sizer._kill_switch_active is False


# ===========================================================================
# Regime Store Tests
# ===========================================================================

class TestRegimeStore:

    @pytest.mark.asyncio
    async def test_no_cache_returns_none(self):
        from brain.regime.regime_store import RegimeStore
        store = RegimeStore(cache_service=None)
        result = await store.get_current_regime()
        assert result is None

    @pytest.mark.asyncio
    async def test_no_cache_history_returns_empty(self):
        from brain.regime.regime_store import RegimeStore
        store = RegimeStore(cache_service=None)
        history = await store.get_history(days=30)
        assert history == []

    @pytest.mark.asyncio
    async def test_save_regime_no_cache_no_error(self):
        """save_regime should not raise when no cache is configured."""
        from brain.regime.regime_store import RegimeStore
        from datetime import date
        store = RegimeStore(cache_service=None)
        # Should complete without error
        await store.save_regime(
            regime=MarketRegime.BULL,
            probabilities={"bull_prob": 0.7, "bear_prob": 0.1, "sideways_prob": 0.2},
            regime_date=date.today(),
        )


# ===========================================================================
# Integration: __init__.py imports
# ===========================================================================

class TestRegimeModuleImports:

    def test_all_exports_importable(self):
        from brain.regime import (
            HMMRegimeDetector,
            KMeansRegimeDetector,
            GMMRegimeDetector,
            CUSUMDetector,
            RegimeRouter,
            PositionSizer,
            RegimeStore,
        )
        assert HMMRegimeDetector is not None
        assert KMeansRegimeDetector is not None
        assert GMMRegimeDetector is not None
        assert CUSUMDetector is not None
        assert RegimeRouter is not None
        assert PositionSizer is not None
        assert RegimeStore is not None

    def test_all_list(self):
        from brain import regime
        assert hasattr(regime, "__all__")
        assert len(regime.__all__) == 7
