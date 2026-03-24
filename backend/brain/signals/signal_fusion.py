"""
Signal Fusion Engine

Combines multiple signal sources into a unified Brain signal
with confidence scoring and regime-conditional weight adjustment.

The fusion follows the Brain spec:
- Technical: 30% (default)
- Sentiment: 25%
- Fundamental: 20%
- Volume: 15%
- Macro: 10%

Weights dynamically shift based on market regime and context.
"""

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from brain.config import BrainConfig, get_brain_config
from brain.models.events import (
    ContributingFactor,
    MarketRegime,
    RiskLevel,
    SignalDirection,
    SignalEvent,
    SignalTimeframe,
)
from brain.signals.signal_generator import RawSignal

logger = logging.getLogger(__name__)


class SignalFusionEngine:
    """
    Multi-signal fusion engine that combines individual signal sources
    into unified trading signals with confidence scoring.
    """

    def __init__(self, config: Optional[BrainConfig] = None):
        self._config = config or get_brain_config()
        self._active_signals: Dict[str, SignalEvent] = {}  # symbol -> latest signal

    def fuse_signals(
        self,
        symbol: str,
        raw_signals: List[RawSignal],
        regime: Optional[MarketRegime] = None,
        stock_info: Optional[Dict[str, Any]] = None,
        current_price: float = 0.0,
    ) -> SignalEvent:
        """
        Fuse multiple raw signals into a single unified signal.

        Args:
            symbol: Stock ticker
            raw_signals: List of RawSignal from each source
            regime: Current market regime (affects weights)
            stock_info: Stock metadata (company name, sector, etc.)
            current_price: Current stock price for target/stop computation
        """
        stock_info = stock_info or {}

        # Get base weights from config
        weights = self._get_regime_adjusted_weights(regime)

        # Build signal map
        signal_map: Dict[str, RawSignal] = {}
        for sig in raw_signals:
            signal_map[sig.source] = sig

        # Compute weighted fusion
        weighted_score = 0.0
        total_weight = 0.0
        contributing_factors = []

        source_weight_map = {
            "technical": weights["technical"],
            "sentiment": weights["sentiment"],
            "fundamental": weights["fundamental"],
            "volume": weights["volume"],
            "macro": weights["macro"],
            "ml_model": weights.get("ml_model", 0.0),
        }

        for source, weight in source_weight_map.items():
            sig = signal_map.get(source)
            if sig is None or sig.confidence == 0:
                continue

            # Effective weight = base weight * signal confidence
            effective_weight = weight * sig.confidence
            weighted_score += sig.score * effective_weight
            total_weight += effective_weight

            contributing_factors.append(ContributingFactor(
                name=source,
                score=sig.score,
                weight=effective_weight,
                description=self._describe_signal(source, sig),
            ))

        # Normalize
        if total_weight > 0:
            final_score = weighted_score / total_weight
        else:
            final_score = 0.0

        # Convert score to direction
        direction = self._score_to_direction(final_score)

        # Compute confidence (0-100%)
        confidence = self._compute_confidence(final_score, raw_signals, regime)

        # Determine timeframe
        timeframe = self._determine_timeframe(raw_signals)

        # Compute target and stop loss
        target_price, stop_loss = self._compute_price_targets(
            direction, current_price, raw_signals, regime
        )

        # Risk-reward ratio
        if direction == SignalDirection.BUY and current_price > 0 and stop_loss > 0:
            risk = current_price - stop_loss
            reward = target_price - current_price
            rr_ratio = reward / risk if risk > 0 else 0
        elif direction == SignalDirection.SELL and current_price > 0 and stop_loss > 0:
            risk = stop_loss - current_price
            reward = current_price - target_price
            rr_ratio = reward / risk if risk > 0 else 0
        else:
            rr_ratio = 0.0

        # Risk level
        risk_level = self._assess_risk_level(confidence, regime, raw_signals)

        # Build explanation
        explanation = self._build_explanation(
            symbol, direction, confidence, contributing_factors, regime
        )

        signal = SignalEvent(
            symbol=symbol,
            company=stock_info.get("name", ""),
            sector=stock_info.get("sector", ""),
            direction=direction,
            confidence=confidence,
            timeframe=timeframe,
            entry_price=current_price,
            target_price=round(target_price, 2),
            stop_loss=round(stop_loss, 2),
            risk_reward_ratio=round(rr_ratio, 2),
            risk_level=risk_level,
            contributing_factors=contributing_factors,
            explanation=explanation,
            regime_at_signal=regime,
        )

        # Store as active signal
        self._active_signals[symbol] = signal
        return signal

    def _get_regime_adjusted_weights(
        self, regime: Optional[MarketRegime]
    ) -> Dict[str, float]:
        """Adjust fusion weights based on market regime."""
        cfg = self._config.fusion_weights
        weights = {
            "technical": cfg.technical,
            "sentiment": cfg.sentiment,
            "fundamental": cfg.fundamental,
            "volume": cfg.volume,
            "macro": cfg.macro,
        }

        if regime == MarketRegime.BULL:
            # Trending market: technical dominates
            weights["technical"] *= 1.3
            weights["fundamental"] *= 0.8
            weights["macro"] *= 0.8
        elif regime == MarketRegime.BEAR:
            # Risk-off: fundamental and macro more important
            weights["fundamental"] *= 1.4
            weights["macro"] *= 1.3
            weights["technical"] *= 0.7
            weights["sentiment"] *= 1.2
        elif regime == MarketRegime.SIDEWAYS:
            # Mean-reversion friendly
            weights["technical"] *= 1.1
            weights["volume"] *= 1.2

        # Normalize to sum to 1
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def _score_to_direction(self, score: float) -> SignalDirection:
        """Convert a [-1, +1] score to a signal direction."""
        if score > 0.15:
            return SignalDirection.BUY
        elif score < -0.15:
            return SignalDirection.SELL
        return SignalDirection.HOLD

    def _compute_confidence(
        self,
        final_score: float,
        signals: List[RawSignal],
        regime: Optional[MarketRegime],
    ) -> float:
        """
        Compute overall confidence (0-100%).

        Based on:
        - Magnitude of final score
        - Agreement between signals
        - Number of confirming data sources
        - Regime favorability
        """
        # Base confidence from score magnitude
        score_confidence = min(abs(final_score) * 100, 50)

        # Agreement bonus: signals pointing the same direction
        if signals:
            valid = [s for s in signals if s.confidence > 0]
            if valid:
                same_direction = sum(
                    1 for s in valid
                    if (s.score > 0) == (final_score > 0) and abs(s.score) > 0.05
                )
                agreement_pct = same_direction / len(valid)
                agreement_bonus = agreement_pct * 30
            else:
                agreement_bonus = 0
        else:
            agreement_bonus = 0

        # Data completeness bonus
        source_count = sum(1 for s in signals if s.confidence > 0)
        completeness_bonus = min(source_count / 5.0, 1.0) * 20

        confidence = score_confidence + agreement_bonus + completeness_bonus

        # Regime penalty for contrarian signals
        if regime == MarketRegime.BEAR and final_score > 0.3:
            confidence *= 0.8  # buy signal in bear market = lower confidence
        elif regime == MarketRegime.BULL and final_score < -0.3:
            confidence *= 0.85  # sell signal in bull market = slightly lower

        return round(min(confidence, 100.0), 1)

    def _determine_timeframe(self, signals: List[RawSignal]) -> SignalTimeframe:
        """Determine signal timeframe based on which signals are strongest."""
        tech_sig = next((s for s in signals if s.source == "technical"), None)
        fund_sig = next((s for s in signals if s.source == "fundamental"), None)

        if fund_sig and fund_sig.confidence > 0.7 and abs(fund_sig.score) > 0.5:
            return SignalTimeframe.INVESTMENT
        if tech_sig and tech_sig.confidence > 0.7:
            return SignalTimeframe.SWING
        return SignalTimeframe.POSITIONAL

    def _compute_price_targets(
        self,
        direction: SignalDirection,
        current_price: float,
        signals: List[RawSignal],
        regime: Optional[MarketRegime],
    ) -> Tuple[float, float]:
        """Compute target price and stop loss based on ATR or percentage."""
        if current_price <= 0:
            return 0.0, 0.0

        # Get ATR from technical signals if available
        tech_sig = next((s for s in signals if s.source == "technical"), None)
        atr = None
        if tech_sig and tech_sig.details:
            atr = tech_sig.details.get("atr_14") or tech_sig.details.get("atr")

        # Default to percentage-based if no ATR
        if atr is None or atr <= 0:
            atr = current_price * 0.02  # 2% of price as proxy

        # Multiplier based on regime
        if regime == MarketRegime.BEAR:
            stop_mult = 2.5
            target_mult = 3.0
        elif regime == MarketRegime.BULL:
            stop_mult = 2.0
            target_mult = 4.0
        else:
            stop_mult = 2.0
            target_mult = 3.5

        if direction == SignalDirection.BUY:
            stop_loss = current_price - (atr * stop_mult)
            target_price = current_price + (atr * target_mult)
        elif direction == SignalDirection.SELL:
            stop_loss = current_price + (atr * stop_mult)
            target_price = current_price - (atr * target_mult)
        else:
            stop_loss = current_price * 0.95
            target_price = current_price * 1.05

        return target_price, stop_loss

    def _assess_risk_level(
        self,
        confidence: float,
        regime: Optional[MarketRegime],
        signals: List[RawSignal],
    ) -> RiskLevel:
        """Assess the risk level of the signal."""
        if confidence > 75 and regime in (MarketRegime.BULL, None):
            return RiskLevel.LOW
        elif confidence < 45 or regime == MarketRegime.BEAR:
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM

    def _describe_signal(self, source: str, signal: RawSignal) -> str:
        """Generate a short description for a contributing factor."""
        direction = "bullish" if signal.score > 0 else "bearish" if signal.score < 0 else "neutral"
        strength = abs(signal.score)
        if strength > 0.7:
            intensity = "strongly"
        elif strength > 0.3:
            intensity = "moderately"
        else:
            intensity = "mildly"
        return f"{source.replace('_', ' ').title()}: {intensity} {direction} ({signal.score:+.2f})"

    def _build_explanation(
        self,
        symbol: str,
        direction: SignalDirection,
        confidence: float,
        factors: List[ContributingFactor],
        regime: Optional[MarketRegime],
    ) -> str:
        """Build a natural language explanation of the signal."""
        sorted_factors = sorted(factors, key=lambda f: abs(f.score * f.weight), reverse=True)

        parts = [f"{direction.value} signal for {symbol} with {confidence:.0f}% confidence."]

        if sorted_factors:
            top = sorted_factors[0]
            parts.append(f"Driven primarily by {top.description}.")

        if len(sorted_factors) > 1:
            supporting = [f.name for f in sorted_factors[1:3] if f.score * sorted_factors[0].score > 0]
            if supporting:
                parts.append(f"Supported by {', '.join(supporting)}.")

            opposing = [f.name for f in sorted_factors[1:] if f.score * sorted_factors[0].score < 0]
            if opposing:
                parts.append(f"Caution: opposing signals from {', '.join(opposing)}.")

        if regime:
            parts.append(f"Market regime: {regime.value}.")

        return " ".join(parts)

    def get_signal(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get the latest signal for a symbol."""
        signal = self._active_signals.get(symbol)
        if signal is None:
            return None
        return self._signal_to_dict(signal)

    async def get_signals(
        self,
        sector: Optional[str] = None,
        confidence_min: float = 40.0,
        direction: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get filtered active signals."""
        results = []
        for symbol, signal in self._active_signals.items():
            if signal.confidence < confidence_min:
                continue
            if sector and signal.sector.lower() != sector.lower():
                continue
            if direction and signal.direction.value != direction.upper():
                continue
            results.append(self._signal_to_dict(signal))

        results.sort(key=lambda s: s["confidence"], reverse=True)
        return results[:limit]

    def _signal_to_dict(self, signal: SignalEvent) -> Dict[str, Any]:
        """Convert a SignalEvent to API-friendly dict."""
        return {
            "signal_id": signal.signal_id,
            "timestamp": signal.timestamp.isoformat(),
            "symbol": signal.symbol,
            "company": signal.company,
            "sector": signal.sector,
            "direction": signal.direction.value,
            "confidence": signal.confidence,
            "timeframe": signal.timeframe.value,
            "entry_price": signal.entry_price,
            "target_price": signal.target_price,
            "stop_loss": signal.stop_loss,
            "risk_reward_ratio": signal.risk_reward_ratio,
            "risk_level": signal.risk_level.value,
            "contributing_factors": [
                {
                    "name": f.name,
                    "score": f.score,
                    "weight": f.weight,
                    "description": f.description,
                }
                for f in signal.contributing_factors
            ],
            "explanation": signal.explanation,
            "regime": signal.regime_at_signal.value if signal.regime_at_signal else None,
        }
