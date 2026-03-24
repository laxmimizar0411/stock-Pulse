"""
Confidence Scorer

Computes a confidence score (0-100%) for trading signals
based on signal alignment, data quality, regime, and historical accuracy.

This replaces the random-based scoring in the original scoring_engine.py.
"""

import logging
import math
from typing import Dict, List, Optional

from brain.models.events import MarketRegime
from brain.signals.signal_generator import RawSignal

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """
    Multi-factor confidence scoring engine.

    Components:
    - Technical alignment (30%): Do RSI, MACD, MAs agree?
    - Sentiment strength (25%): FinBERT consistency across sources
    - Fundamental support (20%): Valuation relative to sector
    - Volume confirmation (15%): Above-average volume confirming move
    - Macro headwinds (10%): Opposing macro factors as penalty
    """

    COMPONENT_WEIGHTS = {
        "technical_alignment": 0.30,
        "sentiment_strength": 0.25,
        "fundamental_support": 0.20,
        "volume_confirmation": 0.15,
        "macro_headwinds": 0.10,
    }

    def compute_confidence(
        self,
        signals: List[RawSignal],
        regime: Optional[MarketRegime] = None,
        signal_direction: float = 0.0,
    ) -> Dict[str, float]:
        """
        Compute a detailed confidence breakdown.

        Returns:
            Dict with 'total' (0-100) and per-component scores.
        """
        components = {}

        # Technical alignment
        tech = next((s for s in signals if s.source == "technical"), None)
        if tech and tech.confidence > 0:
            components["technical_alignment"] = self._score_technical_alignment(tech, signal_direction)
        else:
            components["technical_alignment"] = 0.0

        # Sentiment strength
        sentiment = next((s for s in signals if s.source == "sentiment"), None)
        if sentiment and sentiment.confidence > 0:
            components["sentiment_strength"] = self._score_sentiment(sentiment, signal_direction)
        else:
            components["sentiment_strength"] = 0.0

        # Fundamental support
        fundamental = next((s for s in signals if s.source == "fundamental"), None)
        if fundamental and fundamental.confidence > 0:
            components["fundamental_support"] = self._score_fundamental(fundamental, signal_direction)
        else:
            components["fundamental_support"] = 0.0

        # Volume confirmation
        volume = next((s for s in signals if s.source == "volume"), None)
        if volume and volume.confidence > 0:
            components["volume_confirmation"] = self._score_volume(volume, signal_direction)
        else:
            components["volume_confirmation"] = 0.0

        # Macro headwinds (penalty for opposing macro)
        macro = next((s for s in signals if s.source == "macro"), None)
        if macro and macro.confidence > 0:
            components["macro_headwinds"] = self._score_macro(macro, signal_direction)
        else:
            components["macro_headwinds"] = 50.0  # neutral if no data

        # Weighted total
        total = sum(
            components[k] * self.COMPONENT_WEIGHTS[k]
            for k in self.COMPONENT_WEIGHTS
        )

        # Regime adjustment
        if regime == MarketRegime.BEAR and signal_direction > 0:
            total *= 0.85  # buying in bear market
        elif regime == MarketRegime.BULL and signal_direction < 0:
            total *= 0.90  # selling in bull market

        # Sigmoid transform to ensure 0-100 range with good distribution
        total = self._sigmoid_scale(total, center=50, steepness=0.08)

        components["total"] = round(total, 1)
        return components

    def _score_technical_alignment(self, signal: RawSignal, direction: float) -> float:
        """Score how well technical indicators align with the signal direction."""
        details = signal.details or {}
        scores = []

        for key in ["rsi", "macd", "ma_alignment", "bollinger", "momentum"]:
            if key in details and isinstance(details[key], dict):
                sub_score = details[key].get("score", 0)
                # Agreement with overall direction
                if direction != 0:
                    agreement = 1.0 if (sub_score > 0) == (direction > 0) else 0.0
                else:
                    agreement = 0.5
                scores.append(agreement * 100)

        if not scores:
            return abs(signal.score) * 100 * signal.confidence

        return sum(scores) / len(scores)

    def _score_sentiment(self, signal: RawSignal, direction: float) -> float:
        """Score sentiment alignment and strength."""
        # Agreement with direction
        if direction == 0:
            return 50.0

        agrees = (signal.score > 0) == (direction > 0)
        strength = abs(signal.score) * signal.confidence * 100

        return strength if agrees else max(0, 50 - strength)

    def _score_fundamental(self, signal: RawSignal, direction: float) -> float:
        """Score fundamental support."""
        if direction > 0:
            # Buying: fundamental should be positive
            return max(0, (signal.score + 1) / 2 * 100 * signal.confidence)
        elif direction < 0:
            # Selling: fundamental should be negative
            return max(0, (1 - signal.score) / 2 * 100 * signal.confidence)
        return 50.0

    def _score_volume(self, signal: RawSignal, direction: float) -> float:
        """Score volume confirmation."""
        details = signal.details or {}
        volume_ratio = details.get("volume_ratio", 1.0)

        # High volume confirming direction = good
        confirms = (signal.score > 0) == (direction > 0) if direction != 0 else True

        if volume_ratio > 2.0 and confirms:
            return 90.0
        elif volume_ratio > 1.5 and confirms:
            return 75.0
        elif volume_ratio > 1.0:
            return 60.0
        elif volume_ratio < 0.5:
            return 20.0  # low volume = low confidence
        return 50.0

    def _score_macro(self, signal: RawSignal, direction: float) -> float:
        """Score macro environment (higher = more favorable)."""
        if direction == 0:
            return 50.0

        # Macro supporting the direction
        agrees = (signal.score > 0) == (direction > 0)
        strength = abs(signal.score) * signal.confidence * 100

        return strength if agrees else max(0, 50 - strength * 0.5)

    @staticmethod
    def _sigmoid_scale(x: float, center: float = 50, steepness: float = 0.08) -> float:
        """Scale a value through sigmoid for smooth 0-100 mapping."""
        try:
            scaled = 100 / (1 + math.exp(-steepness * (x - center)))
        except OverflowError:
            scaled = 0.0 if x < center else 100.0
        return max(0.0, min(100.0, scaled))
