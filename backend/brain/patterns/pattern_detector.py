"""
Chart Pattern Detector

Main orchestrator for chart pattern detection.
Combines peak/trough detection with pattern matching.
"""

import logging
from typing import List, Dict, Any, Optional
import numpy as np
from datetime import datetime, timezone
import time

from .peak_trough_detector import PeakTroughDetector
from .pattern_matchers import PatternMatcher

logger = logging.getLogger(__name__)


class ChartPatternDetector:
    """
    Main chart pattern detector.
    
    Orchestrates:
    1. Peak/trough detection
    2. Pattern matching
    3. Result aggregation
    
    Target: ~10ms per stock
    """
    
    def __init__(
        self,
        min_distance: int = 5,
        prominence_pct: float = 0.02,
        tolerance: float = 0.03
    ):
        """
        Initialize chart pattern detector.
        
        Args:
            min_distance: Minimum distance between pivots
            prominence_pct: Minimum prominence (2% default)
            tolerance: Pattern tolerance (3% default)
        """
        self.peak_trough_detector = PeakTroughDetector(
            min_distance=min_distance,
            prominence_pct=prominence_pct
        )
        self.pattern_matcher = PatternMatcher(tolerance=tolerance)
    
    def detect_patterns(
        self,
        prices: np.ndarray,
        timestamps: Optional[List[datetime]] = None,
        pattern_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Detect all chart patterns in price series.
        
        Args:
            prices: Price array (OHLCV close prices)
            timestamps: Optional timestamp array
            pattern_types: Specific patterns to detect (None = all)
            
        Returns:
            Dictionary with detected patterns and metadata
        """
        start_time = time.time()
        
        # Step 1: Detect peaks and troughs
        pivots = self.peak_trough_detector.get_pivot_points(prices, timestamps)
        
        peaks = pivots["peaks"]
        troughs = pivots["troughs"]
        
        # Step 2: Run pattern matchers
        all_patterns = []
        
        if pattern_types is None or "head_and_shoulders" in pattern_types:
            hs_patterns = self.pattern_matcher.detect_head_and_shoulders(
                prices, peaks, troughs
            )
            all_patterns.extend(hs_patterns)
        
        if pattern_types is None or "inverse_head_and_shoulders" in pattern_types:
            ihs_patterns = self.pattern_matcher.detect_inverse_head_and_shoulders(
                prices, peaks, troughs
            )
            all_patterns.extend(ihs_patterns)
        
        if pattern_types is None or "double_top" in pattern_types:
            dt_patterns = self.pattern_matcher.detect_double_top(
                prices, peaks, troughs
            )
            all_patterns.extend(dt_patterns)
        
        if pattern_types is None or "double_bottom" in pattern_types:
            db_patterns = self.pattern_matcher.detect_double_bottom(
                prices, peaks, troughs
            )
            all_patterns.extend(db_patterns)
        
        if pattern_types is None or "triangle" in pattern_types:
            triangle_patterns = self.pattern_matcher.detect_triangle(
                prices, peaks, troughs
            )
            all_patterns.extend(triangle_patterns)
        
        # Step 3: Sort by confidence
        all_patterns.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        
        # Execution time
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Step 4: Aggregate results
        result = {
            "patterns_detected": len(all_patterns),
            "patterns": all_patterns,
            "pivots": {
                "peaks": peaks,
                "troughs": troughs,
                "total": pivots["total_pivots"]
            },
            "execution_time_ms": round(execution_time_ms, 2),
            "data_points": len(prices),
            "detected_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Summary by pattern type
        pattern_summary = {}
        for p in all_patterns:
            pattern_name = p["pattern"]
            if pattern_name not in pattern_summary:
                pattern_summary[pattern_name] = 0
            pattern_summary[pattern_name] += 1
        
        result["pattern_summary"] = pattern_summary
        
        return result
    
    def detect_patterns_for_symbol(
        self,
        symbol: str,
        ohlcv_data: Dict[str, List[float]],
        pattern_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Detect patterns for a specific stock symbol.
        
        Args:
            symbol: Stock symbol
            ohlcv_data: Dictionary with 'close' prices and optional 'timestamps'
            pattern_types: Specific patterns to detect
            
        Returns:
            Detection results with symbol metadata
        """
        if "close" not in ohlcv_data:
            raise ValueError("ohlcv_data must contain 'close' prices")
        
        prices = np.array(ohlcv_data["close"])
        timestamps = ohlcv_data.get("timestamps")
        
        result = self.detect_patterns(prices, timestamps, pattern_types)
        result["symbol"] = symbol
        
        return result
    
    def get_actionable_signals(
        self,
        detection_result: Dict[str, Any],
        min_confidence: float = 0.65
    ) -> List[Dict[str, Any]]:
        """
        Extract actionable trading signals from detected patterns.
        
        Args:
            detection_result: Result from detect_patterns()
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of actionable signals
        """
        signals = []
        
        for pattern in detection_result.get("patterns", []):
            if pattern.get("confidence", 0) < min_confidence:
                continue
            
            pattern_type = pattern.get("type", "")
            
            if "bullish" in pattern_type:
                action = "BUY"
                bias = "bullish"
            elif "bearish" in pattern_type:
                action = "SELL"
                bias = "bearish"
            else:
                action = "WATCH"
                bias = "neutral"
            
            signals.append({
                "action": action,
                "bias": bias,
                "pattern": pattern["pattern"],
                "confidence": pattern["confidence"],
                "target": pattern.get("target"),
                "interpretation": pattern.get("interpretation"),
                "start_index": pattern.get("start_index"),
                "end_index": pattern.get("end_index")
            })
        
        return signals
    
    def get_detector_stats(self) -> Dict[str, Any]:
        """Get detector configuration and stats."""
        return {
            "min_distance": self.peak_trough_detector.min_distance,
            "prominence_pct": self.peak_trough_detector.prominence_pct,
            "tolerance": self.pattern_matcher.tolerance,
            "supported_patterns": [
                "head_and_shoulders",
                "inverse_head_and_shoulders",
                "double_top",
                "double_bottom",
                "ascending_triangle",
                "descending_triangle",
                "symmetric_triangle"
            ],
            "target_execution_time_ms": 10
        }
