"""
Market Regime Detection — Phase 3.1

Detects bull/bear/sideways regimes using multiple complementary methods:
- HMM (Gaussian Hidden Markov Model) — primary temporal detector
- K-Means / GMM — clustering-based confirmation
- CUSUM — real-time change-point detection

Exports regime routing, position sizing, and persistence utilities.
"""

from brain.regime.hmm_detector import HMMRegimeDetector
from brain.regime.kmeans_gmm_detector import GMMRegimeDetector, KMeansRegimeDetector
from brain.regime.cusum_detector import CUSUMDetector
from brain.regime.regime_router import RegimeRouter
from brain.regime.position_sizer import PositionSizer
from brain.regime.regime_store import RegimeStore

__all__ = [
    "HMMRegimeDetector",
    "KMeansRegimeDetector",
    "GMMRegimeDetector",
    "CUSUMDetector",
    "RegimeRouter",
    "PositionSizer",
    "RegimeStore",
]
