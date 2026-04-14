"""
Phase 5.6: Chart Pattern Detection

Rule-based pattern detection for technical analysis.
Target: ~10ms per stock with interpretable output.
"""

from .peak_trough_detector import PeakTroughDetector
from .pattern_matchers import PatternMatcher
from .pattern_detector import ChartPatternDetector

__all__ = [
    "PeakTroughDetector",
    "PatternMatcher",
    "ChartPatternDetector",
]
