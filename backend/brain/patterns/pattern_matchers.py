"""
Pattern Matchers

Rule-based geometric pattern detection for technical analysis.
Target: ~10ms per stock with interpretable output.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


class PatternMatcher:
    """
    Rule-based pattern matcher for chart patterns.
    
    Detects:
    - Head & Shoulders (top/bottom)
    - Double/Triple Tops/Bottoms
    - Triangles (ascending/descending/symmetric)
    - Flags & Pennants
    - Cup & Handle
    - Wedges (rising/falling)
    """
    
    def __init__(self, tolerance: float = 0.03):
        """
        Initialize pattern matcher.
        
        Args:
            tolerance: Price level tolerance (default 3%)
        """
        self.tolerance = tolerance
    
    def detect_head_and_shoulders(
        self,
        prices: np.ndarray,
        peaks: List[Dict[str, Any]],
        troughs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Detect Head & Shoulders pattern (bearish reversal).
        
        Pattern:
        - Left shoulder (peak)
        - Head (higher peak)
        - Right shoulder (peak ~same as left)
        - Neckline (support connecting troughs)
        """
        patterns = []
        
        if len(peaks) < 3 or len(troughs) < 2:
            return patterns
        
        # Try all combinations of 3 consecutive peaks
        for i in range(len(peaks) - 2):
            left_shoulder = peaks[i]
            head = peaks[i + 1]
            right_shoulder = peaks[i + 2]
            
            # Head must be higher than shoulders
            if head["price"] <= max(left_shoulder["price"], right_shoulder["price"]):
                continue
            
            # Shoulders should be roughly equal height
            shoulder_diff = abs(left_shoulder["price"] - right_shoulder["price"])
            avg_shoulder = (left_shoulder["price"] + right_shoulder["price"]) / 2
            
            if shoulder_diff / avg_shoulder > self.tolerance:
                continue
            
            # Find troughs between shoulders (neckline)
            neck_troughs = [
                t for t in troughs
                if left_shoulder["index"] < t["index"] < right_shoulder["index"]
            ]
            
            if len(neck_troughs) < 2:
                continue
            
            # Neckline level
            neckline = np.mean([t["price"] for t in neck_troughs[:2]])
            
            patterns.append({
                "pattern": "head_and_shoulders",
                "type": "bearish_reversal",
                "confidence": self._calculate_hs_confidence(left_shoulder, head, right_shoulder, neckline),
                "left_shoulder": left_shoulder["price"],
                "head": head["price"],
                "right_shoulder": right_shoulder["price"],
                "neckline": float(neckline),
                "target": float(neckline - (head["price"] - neckline)),
                "start_index": left_shoulder["index"],
                "end_index": right_shoulder["index"],
                "interpretation": f"H&S: left shoulder {left_shoulder['price']:.2f}, head {head['price']:.2f}, right shoulder {right_shoulder['price']:.2f}, neckline {neckline:.2f}"
            })
        
        return patterns
    
    def detect_inverse_head_and_shoulders(
        self,
        prices: np.ndarray,
        peaks: List[Dict[str, Any]],
        troughs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Detect Inverse Head & Shoulders pattern (bullish reversal)."""
        patterns = []
        
        if len(troughs) < 3 or len(peaks) < 2:
            return patterns
        
        for i in range(len(troughs) - 2):
            left_shoulder = troughs[i]
            head = troughs[i + 1]
            right_shoulder = troughs[i + 2]
            
            if head["price"] >= min(left_shoulder["price"], right_shoulder["price"]):
                continue
            
            shoulder_diff = abs(left_shoulder["price"] - right_shoulder["price"])
            avg_shoulder = (left_shoulder["price"] + right_shoulder["price"]) / 2
            
            if shoulder_diff / avg_shoulder > self.tolerance:
                continue
            
            neck_peaks = [
                p for p in peaks
                if left_shoulder["index"] < p["index"] < right_shoulder["index"]
            ]
            
            if len(neck_peaks) < 2:
                continue
            
            neckline = np.mean([p["price"] for p in neck_peaks[:2]])
            
            patterns.append({
                "pattern": "inverse_head_and_shoulders",
                "type": "bullish_reversal",
                "confidence": self._calculate_hs_confidence(left_shoulder, head, right_shoulder, neckline),
                "left_shoulder": left_shoulder["price"],
                "head": head["price"],
                "right_shoulder": right_shoulder["price"],
                "neckline": float(neckline),
                "target": float(neckline + (neckline - head["price"])),
                "start_index": left_shoulder["index"],
                "end_index": right_shoulder["index"],
                "interpretation": f"Inverse H&S: left shoulder {left_shoulder['price']:.2f}, head {head['price']:.2f}, right shoulder {right_shoulder['price']:.2f}, neckline {neckline:.2f}"
            })
        
        return patterns
    
    def detect_double_top(
        self,
        prices: np.ndarray,
        peaks: List[Dict[str, Any]],
        troughs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Detect Double Top pattern (bearish reversal)."""
        patterns = []
        
        if len(peaks) < 2 or len(troughs) < 1:
            return patterns
        
        for i in range(len(peaks) - 1):
            first_peak = peaks[i]
            second_peak = peaks[i + 1]
            
            price_diff = abs(first_peak["price"] - second_peak["price"])
            avg_price = (first_peak["price"] + second_peak["price"]) / 2
            
            if price_diff / avg_price > self.tolerance:
                continue
            
            between_troughs = [
                t for t in troughs
                if first_peak["index"] < t["index"] < second_peak["index"]
            ]
            
            if not between_troughs:
                continue
            
            support = min(t["price"] for t in between_troughs)
            
            patterns.append({
                "pattern": "double_top",
                "type": "bearish_reversal",
                "confidence": 0.75,
                "first_peak": first_peak["price"],
                "second_peak": second_peak["price"],
                "support": float(support),
                "target": float(support - (avg_price - support)),
                "start_index": first_peak["index"],
                "end_index": second_peak["index"],
                "interpretation": f"Double Top: peaks at {first_peak['price']:.2f} and {second_peak['price']:.2f}, support {support:.2f}"
            })
        
        return patterns
    
    def detect_double_bottom(
        self,
        prices: np.ndarray,
        peaks: List[Dict[str, Any]],
        troughs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Detect Double Bottom pattern (bullish reversal)."""
        patterns = []
        
        if len(troughs) < 2 or len(peaks) < 1:
            return patterns
        
        for i in range(len(troughs) - 1):
            first_trough = troughs[i]
            second_trough = troughs[i + 1]
            
            price_diff = abs(first_trough["price"] - second_trough["price"])
            avg_price = (first_trough["price"] + second_trough["price"]) / 2
            
            if price_diff / avg_price > self.tolerance:
                continue
            
            between_peaks = [
                p for p in peaks
                if first_trough["index"] < p["index"] < second_trough["index"]
            ]
            
            if not between_peaks:
                continue
            
            resistance = max(p["price"] for p in between_peaks)
            
            patterns.append({
                "pattern": "double_bottom",
                "type": "bullish_reversal",
                "confidence": 0.75,
                "first_trough": first_trough["price"],
                "second_trough": second_trough["price"],
                "resistance": float(resistance),
                "target": float(resistance + (resistance - avg_price)),
                "start_index": first_trough["index"],
                "end_index": second_trough["index"],
                "interpretation": f"Double Bottom: troughs at {first_trough['price']:.2f} and {second_trough['price']:.2f}, resistance {resistance:.2f}"
            })
        
        return patterns
    
    def detect_triangle(
        self,
        prices: np.ndarray,
        peaks: List[Dict[str, Any]],
        troughs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Detect Triangle patterns (ascending/descending/symmetric)."""
        patterns = []
        
        if len(peaks) < 2 or len(troughs) < 2:
            return patterns
        
        recent_peaks = peaks[-3:] if len(peaks) >= 3 else peaks
        recent_troughs = troughs[-3:] if len(troughs) >= 3 else troughs
        
        if len(recent_peaks) < 2 or len(recent_troughs) < 2:
            return patterns
        
        peak_prices = [p["price"] for p in recent_peaks]
        trough_prices = [t["price"] for t in recent_troughs]
        
        peak_trend = np.polyfit([p["index"] for p in recent_peaks], peak_prices, 1)[0]
        trough_trend = np.polyfit([t["index"] for t in recent_troughs], trough_prices, 1)[0]
        
        if abs(peak_trend) < 0.01 and trough_trend > 0.01:
            triangle_type = "ascending"
            bias = "bullish_continuation"
        elif abs(trough_trend) < 0.01 and peak_trend < -0.01:
            triangle_type = "descending"
            bias = "bearish_continuation"
        elif abs(peak_trend + trough_trend) < 0.02:
            triangle_type = "symmetric"
            bias = "neutral"
        else:
            return patterns
        
        patterns.append({
            "pattern": f"{triangle_type}_triangle",
            "type": bias,
            "confidence": 0.65,
            "upper_trendline_slope": float(peak_trend),
            "lower_trendline_slope": float(trough_trend),
            "apex_price": float(np.mean([peak_prices[-1], trough_prices[-1]])),
            "start_index": min(recent_peaks[0]["index"], recent_troughs[0]["index"]),
            "end_index": max(recent_peaks[-1]["index"], recent_troughs[-1]["index"]),
            "interpretation": f"{triangle_type.capitalize()} Triangle: converging trendlines, {bias} bias"
        })
        
        return patterns
    
    def _calculate_hs_confidence(
        self,
        left_shoulder: Dict,
        head: Dict,
        right_shoulder: Dict,
        neckline: float
    ) -> float:
        """Calculate confidence score for H&S pattern."""
        avg_shoulder_price = (left_shoulder["price"] + right_shoulder["price"]) / 2
        shoulder_symmetry = 1 - abs(left_shoulder["price"] - right_shoulder["price"]) / avg_shoulder_price
        
        head_prominence = abs(head["price"] - avg_shoulder_price) / avg_shoulder_price
        
        confidence = (shoulder_symmetry * 0.6 + min(head_prominence / 0.1, 1.0) * 0.4)
        
        return min(max(confidence, 0.5), 0.95)
