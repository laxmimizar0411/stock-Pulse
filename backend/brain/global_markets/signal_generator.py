"""
Pre-Market Signal Generator

Generates swing trading signals based on overnight global market movements.
Publishes signals by 8:30 AM IST before Indian market open (9:15 AM IST).
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import numpy as np

from .sector_mappings import aggregate_sector_impacts

logger = logging.getLogger(__name__)

# IST timezone
IST = timezone(timedelta(hours=5, minutes=30))


class PreMarketSignalGenerator:
    """
    Generates pre-market swing signals based on overnight global data.
    
    Signal types:
    - Sector rotation signals (based on global correlations)
    - Breakout alerts (>2σ divergence)
    - Pre-market sentiment (bullish/bearish/neutral)
    """
    
    def __init__(self):
        self.last_signal_time: Optional[datetime] = None
        self.latest_signals: List[Dict[str, Any]] = []
        
    def generate_premarket_signals(
        self,
        global_changes: Dict[str, float],
        correlations: Dict[str, Dict[str, float]],
        breakouts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate pre-market signals from overnight data.
        
        Args:
            global_changes: Percentage changes in global markets
            correlations: Correlation matrix data
            breakouts: Detected correlation breakouts
            
        Returns:
            Dictionary of signals and analysis
        """
        logger.info("Generating pre-market signals...")
        
        # 1. Calculate sector impacts
        sector_impacts = aggregate_sector_impacts(global_changes)
        
        # 2. Determine market sentiment
        sentiment = self._calculate_market_sentiment(global_changes)
        
        # 3. Generate sector-specific signals
        sector_signals = self._generate_sector_signals(sector_impacts)
        
        # 4. Identify key movers
        key_movers = self._identify_key_movers(global_changes)
        
        # 5. Breakout signals
        breakout_signals = self._format_breakout_signals(breakouts)
        
        # 6. Overall recommendation
        overall_recommendation = self._generate_overall_recommendation(
            sentiment,
            sector_signals,
            key_movers
        )
        
        signals = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_at_ist": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
            "market_sentiment": sentiment,
            "overall_recommendation": overall_recommendation,
            "sector_signals": sector_signals,
            "key_global_movers": key_movers,
            "breakout_alerts": breakout_signals,
            "raw_global_changes": global_changes,
            "correlation_data": correlations
        }
        
        self.latest_signals = sector_signals
        self.last_signal_time = datetime.now(timezone.utc)
        
        logger.info(f"✅ Generated {len(sector_signals)} sector signals")
        
        return signals
    
    def _calculate_market_sentiment(
        self,
        global_changes: Dict[str, float]
    ) -> Dict[str, Any]:
        """Calculate overall market sentiment from global moves."""
        if not global_changes:
            return {
                "score": 0,
                "label": "neutral",
                "confidence": 0.0
            }
        
        # Weight different markets for Indian sentiment
        weights = {
            "SP500": 0.25,
            "NASDAQ": 0.15,
            "DOW": 0.10,
            "SGX_NIFTY": 0.20,  # Highest weight - direct proxy
            "NIKKEI": 0.10,
            "HANGSENG": 0.10,
            "CRUDE_WTI": -0.05,  # Negative weight (hurts India)
            "DXY": -0.05,        # Negative weight (EM outflows)
        }
        
        # Calculate weighted sentiment
        sentiment_score = 0
        total_weight = 0
        
        for market, weight in weights.items():
            if market in global_changes:
                sentiment_score += global_changes[market] * weight
                total_weight += abs(weight)
        
        # Normalize
        if total_weight > 0:
            sentiment_score = sentiment_score / total_weight * 100  # Scale to percentage
        
        # Determine label
        if sentiment_score > 0.5:
            label = "bullish"
        elif sentiment_score < -0.5:
            label = "bearish"
        else:
            label = "neutral"
        
        # Confidence based on magnitude
        confidence = min(abs(sentiment_score) / 2, 100) / 100  # Cap at 1.0
        
        return {
            "score": round(sentiment_score, 2),
            "label": label,
            "confidence": round(confidence, 2),
            "interpretation": self._interpret_sentiment(label, sentiment_score)
        }
    
    def _interpret_sentiment(self, label: str, score: float) -> str:
        """Interpret sentiment score into actionable text."""
        if label == "bullish":
            if score > 1.5:
                return "Strong positive overnight momentum. Consider gap-up opening with buying interest."
            else:
                return "Moderate positive overnight sentiment. Watch for confirmation at open."
        elif label == "bearish":
            if score < -1.5:
                return "Strong negative overnight pressure. Expect gap-down opening with selling pressure."
            else:
                return "Moderate negative sentiment. Watch for support levels at open."
        else:
            return "Neutral overnight session. Await domestic cues for direction."
    
    def _generate_sector_signals(
        self,
        sector_impacts: Dict[str, Dict[str, float]]
    ) -> List[Dict[str, Any]]:
        """Generate actionable sector signals."""
        signals = []
        
        for sector, data in sector_impacts.items():
            total_impact = data["total_impact_pct"]
            
            # Only generate signals for significant impacts (>0.5%)
            if abs(total_impact) < 0.5:
                continue
            
            # Determine signal
            if total_impact > 1.5:
                signal_type = "strong_buy"
                action = "ACCUMULATE"
            elif total_impact > 0.5:
                signal_type = "buy"
                action = "BUY"
            elif total_impact < -1.5:
                signal_type = "strong_sell"
                action = "AVOID"
            elif total_impact < -0.5:
                signal_type = "sell"
                action = "REDUCE"
            else:
                signal_type = "neutral"
                action = "HOLD"
            
            signals.append({
                "sector": sector,
                "signal": signal_type,
                "action": action,
                "expected_impact_pct": round(total_impact, 2),
                "top_drivers": data["contributing_markets"][:3],  # Top 3 drivers
                "confidence": min(abs(total_impact) / 3 * 100, 100)  # Higher impact = higher confidence
            })
        
        # Sort by absolute impact
        signals.sort(key=lambda x: abs(x["expected_impact_pct"]), reverse=True)
        
        return signals
    
    def _identify_key_movers(
        self,
        global_changes: Dict[str, float],
        threshold: float = 1.0
    ) -> List[Dict[str, Any]]:
        """Identify significant overnight movers."""
        movers = []
        
        for market, change_pct in global_changes.items():
            if abs(change_pct) >= threshold:
                movers.append({
                    "market": market,
                    "change_pct": round(change_pct, 2),
                    "direction": "up" if change_pct > 0 else "down",
                    "magnitude": "high" if abs(change_pct) > 2 else "moderate"
                })
        
        # Sort by absolute change
        movers.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
        
        return movers
    
    def _format_breakout_signals(
        self,
        breakouts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Format correlation breakouts into signals."""
        signals = []
        
        for breakout in breakouts[:5]:  # Top 5 breakouts
            signals.append({
                "type": "correlation_breakout",
                "market_pair": f"{breakout['market1']} - {breakout['market2']}",
                "current_correlation": round(breakout['current_correlation'], 3),
                "divergence_sigma": round(breakout['divergence_std'], 2),
                "breakout_type": breakout['breakout_type'],
                "alert": f"{breakout['divergence_std']:.1f}σ divergence detected"
            })
        
        return signals
    
    def _generate_overall_recommendation(
        self,
        sentiment: Dict[str, Any],
        sector_signals: List[Dict[str, Any]],
        key_movers: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate overall pre-market recommendation."""
        # Count bullish vs bearish sector signals
        bullish_count = sum(1 for s in sector_signals if s["signal"] in ["buy", "strong_buy"])
        bearish_count = sum(1 for s in sector_signals if s["signal"] in ["sell", "strong_sell"])
        
        # Overall bias
        if sentiment["label"] == "bullish" and bullish_count > bearish_count:
            bias = "bullish"
            action = "Look for long opportunities in outperforming sectors"
        elif sentiment["label"] == "bearish" and bearish_count > bullish_count:
            bias = "bearish"
            action = "Exercise caution; consider reducing exposure or shorting weak sectors"
        else:
            bias = "mixed"
            action = "Selective approach; focus on sector-specific opportunities"
        
        # Top sectors to watch
        top_sectors = [s["sector"] for s in sector_signals[:5]]
        
        return {
            "bias": bias,
            "action": action,
            "sentiment_score": sentiment["score"],
            "sentiment_confidence": sentiment["confidence"],
            "bullish_sectors_count": bullish_count,
            "bearish_sectors_count": bearish_count,
            "top_sectors_to_watch": top_sectors,
            "key_overnight_movers": len(key_movers)
        }
    
    def should_run_premarket_update(self) -> bool:
        """
        Check if it's time for pre-market signal update.
        
        Runs between 7:00 AM - 9:00 AM IST (before market open at 9:15 AM)
        """
        now_ist = datetime.now(IST)
        hour = now_ist.hour
        
        # Run between 7 AM and 9 AM IST
        if 7 <= hour < 9:
            # Check if we haven't run in the last hour
            if self.last_signal_time is None:
                return True
            
            time_since_last = (datetime.now(timezone.utc) - self.last_signal_time).total_seconds()
            if time_since_last > 3600:  # 1 hour
                return True
        
        return False
    
    def get_latest_signals(self) -> Dict[str, Any]:
        """Get the most recent signals."""
        return {
            "signals": self.latest_signals,
            "generated_at": self.last_signal_time.isoformat() if self.last_signal_time else None,
            "is_current": self._is_signal_current()
        }
    
    def _is_signal_current(self) -> bool:
        """Check if latest signals are still current (< 4 hours old)."""
        if self.last_signal_time is None:
            return False
        
        age_hours = (datetime.now(timezone.utc) - self.last_signal_time).total_seconds() / 3600
        return age_hours < 4
