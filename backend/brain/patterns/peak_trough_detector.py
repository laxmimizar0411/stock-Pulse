"""
Peak and Trough Detector

Identifies local maxima (peaks) and minima (troughs) in price data.
Uses scipy.signal.find_peaks for robust detection.
"""

import logging
from typing import List, Tuple, Dict, Any
import numpy as np
from scipy.signal import find_peaks, argrelextrema
from datetime import datetime

logger = logging.getLogger(__name__)


class PeakTroughDetector:
    """
    Detects peaks (local maxima) and troughs (local minima) in price series.
    
    Uses adaptive parameters based on data characteristics.
    """
    
    def __init__(
        self,
        min_distance: int = 5,
        prominence_pct: float = 0.02  # 2% minimum prominence
    ):
        """
        Initialize peak/trough detector.
        
        Args:
            min_distance: Minimum distance between peaks/troughs
            prominence_pct: Minimum prominence as % of price range
        """
        self.min_distance = min_distance
        self.prominence_pct = prominence_pct
    
    def detect_peaks(
        self,
        prices: np.ndarray,
        timestamps: List[datetime] = None
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """
        Detect peaks (local maxima) in price series.
        
        Args:
            prices: Price array
            timestamps: Optional timestamp array
            
        Returns:
            Tuple of (peak_indices, peak_properties)
        """
        if len(prices) < self.min_distance * 2:
            return np.array([]), {}
        
        # Calculate prominence threshold
        price_range = np.max(prices) - np.min(prices)
        prominence_threshold = price_range * self.prominence_pct
        
        # Find peaks
        peak_indices, peak_properties = find_peaks(
            prices,
            distance=self.min_distance,
            prominence=prominence_threshold
        )
        
        return peak_indices, peak_properties
    
    def detect_troughs(
        self,
        prices: np.ndarray,
        timestamps: List[datetime] = None
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """
        Detect troughs (local minima) in price series.
        
        Args:
            prices: Price array
            timestamps: Optional timestamp array
            
        Returns:
            Tuple of (trough_indices, trough_properties)
        """
        if len(prices) < self.min_distance * 2:
            return np.array([]), {}
        
        # Invert prices to find troughs as peaks
        inverted_prices = -prices
        
        # Calculate prominence threshold
        price_range = np.max(prices) - np.min(prices)
        prominence_threshold = price_range * self.prominence_pct
        
        # Find troughs
        trough_indices, trough_properties = find_peaks(
            inverted_prices,
            distance=self.min_distance,
            prominence=prominence_threshold
        )
        
        return trough_indices, trough_properties
    
    def get_pivot_points(
        self,
        prices: np.ndarray,
        timestamps: List[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get all pivot points (peaks and troughs) with metadata.
        
        Args:
            prices: Price array
            timestamps: Optional timestamp array
            
        Returns:
            Dictionary with peaks and troughs information
        """
        # Detect peaks and troughs
        peak_indices, peak_props = self.detect_peaks(prices, timestamps)
        trough_indices, trough_props = self.detect_troughs(prices, timestamps)
        
        # Extract values
        peaks = []
        for idx in peak_indices:
            peaks.append({
                "index": int(idx),
                "price": float(prices[idx]),
                "timestamp": timestamps[idx] if timestamps else None,
                "type": "peak"
            })
        
        troughs = []
        for idx in trough_indices:
            troughs.append({
                "index": int(idx),
                "price": float(prices[idx]),
                "timestamp": timestamps[idx] if timestamps else None,
                "type": "trough"
            })
        
        # Combine and sort by index
        all_pivots = peaks + troughs
        all_pivots.sort(key=lambda x: x["index"])
        
        return {
            "peaks": peaks,
            "troughs": troughs,
            "all_pivots": all_pivots,
            "peak_count": len(peaks),
            "trough_count": len(troughs),
            "total_pivots": len(all_pivots)
        }
    
    def get_significant_pivots(
        self,
        prices: np.ndarray,
        timestamps: List[datetime] = None,
        top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get most significant pivot points by prominence.
        
        Args:
            prices: Price array
            timestamps: Optional timestamp array
            top_n: Number of top pivots to return
            
        Returns:
            List of most significant pivots
        """
        pivots = self.get_pivot_points(prices, timestamps)
        
        # Get peak and trough indices with prominence
        peak_indices, peak_props = self.detect_peaks(prices, timestamps)
        trough_indices, trough_props = self.detect_troughs(prices, timestamps)
        
        # Combine with prominence
        significant = []
        
        for i, idx in enumerate(peak_indices):
            significant.append({
                "index": int(idx),
                "price": float(prices[idx]),
                "timestamp": timestamps[idx] if timestamps else None,
                "type": "peak",
                "prominence": float(peak_props.get("prominences", [0])[i] if i < len(peak_props.get("prominences", [])) else 0)
            })
        
        for i, idx in enumerate(trough_indices):
            significant.append({
                "index": int(idx),
                "price": float(prices[idx]),
                "timestamp": timestamps[idx] if timestamps else None,
                "type": "trough",
                "prominence": float(trough_props.get("prominences", [0])[i] if i < len(trough_props.get("prominences", [])) else 0)
            })
        
        # Sort by prominence (descending)
        significant.sort(key=lambda x: x["prominence"], reverse=True)
        
        return significant[:top_n]
