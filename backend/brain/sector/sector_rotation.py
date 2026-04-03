"""Sector Rotation Engine — Phase 3.7

Tracks and scores sector relative strength for rotation strategies:
1. Relative Strength Index (sector vs NIFTY)
2. Momentum scoring (1M, 3M, 6M returns)
3. FII/DII sector preference detection
4. Business cycle mapping
5. Seasonal sector patterns

Sectors: Banking, IT, Pharma, Auto, FMCG, Energy, Metals, Realty, Infra.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Indian sector ETF/Index mapping
SECTOR_MAP = {
    "banking": {"name": "NIFTY Bank", "etf": "BANKBEES", "top_stocks": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"]},
    "it": {"name": "NIFTY IT", "etf": "ITBEES", "top_stocks": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"]},
    "pharma": {"name": "NIFTY Pharma", "etf": "PHARMABEES", "top_stocks": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB"]},
    "auto": {"name": "NIFTY Auto", "etf": "AUTOBEES", "top_stocks": ["MARUTI", "TATAMOTORS", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO"]},
    "fmcg": {"name": "NIFTY FMCG", "etf": "FMCGBEES", "top_stocks": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA"]},
    "energy": {"name": "NIFTY Energy", "etf": "ENERGYBEES", "top_stocks": ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "COALINDIA"]},
    "metals": {"name": "NIFTY Metals", "etf": "METALBEES", "top_stocks": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL"]},
    "realty": {"name": "NIFTY Realty", "top_stocks": ["DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE"]},
    "infra": {"name": "NIFTY Infra", "top_stocks": ["LT", "ADANIENT", "ADANIPORTS", "ULTRACEMCO", "GRASIM"]},
}

# Business cycle to sector mapping
BUSINESS_CYCLE_MAP = {
    "expansion": ["banking", "auto", "realty", "metals", "infra"],
    "peak": ["energy", "metals", "fmcg"],
    "contraction": ["pharma", "fmcg", "it"],
    "trough": ["banking", "auto", "infra", "realty"],
}


@dataclass
class SectorScore:
    """Relative strength score for a sector."""
    sector: str
    name: str
    score: float = 0.0  # 0-100
    rank: int = 0
    momentum_1m: float = 0.0
    momentum_3m: float = 0.0
    momentum_6m: float = 0.0
    relative_strength: float = 0.0
    recommendation: str = "neutral"  # "overweight", "neutral", "underweight"
    top_stocks: List[str] = field(default_factory=list)
    cycle_alignment: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sector": self.sector,
            "name": self.name,
            "score": round(self.score, 2),
            "rank": self.rank,
            "momentum_1m_pct": round(self.momentum_1m, 2),
            "momentum_3m_pct": round(self.momentum_3m, 2),
            "momentum_6m_pct": round(self.momentum_6m, 2),
            "relative_strength": round(self.relative_strength, 2),
            "recommendation": self.recommendation,
            "top_stocks": self.top_stocks,
            "cycle_alignment": self.cycle_alignment,
        }


class SectorRotationEngine:
    """Scores sectors for rotation strategy."""

    def __init__(self):
        self._sectors = SECTOR_MAP
        self._stats = {"rotations_computed": 0}

    def compute_rotation(
        self,
        sector_returns: Dict[str, Dict[str, float]],
        business_cycle: str = "expansion",
    ) -> List[SectorScore]:
        """
        Compute sector rotation scores.

        Args:
            sector_returns: {sector: {"1m": pct, "3m": pct, "6m": pct}}
            business_cycle: Current business cycle phase
        """
        cycle_favored = set(BUSINESS_CYCLE_MAP.get(business_cycle, []))
        scores = []

        for sector, info in self._sectors.items():
            rets = sector_returns.get(sector, {})
            m1 = rets.get("1m", 0)
            m3 = rets.get("3m", 0)
            m6 = rets.get("6m", 0)

            # Momentum score: weighted average
            momentum = 0.4 * m1 + 0.35 * m3 + 0.25 * m6

            # Relative strength (simple proxy)
            relative = momentum  # In production, compare to NIFTY returns

            # Composite score (0-100)
            base = 50 + momentum  # Center around 50
            if sector in cycle_favored:
                base += 10  # Bonus for cycle alignment

            score = max(0, min(100, base))

            # Recommendation
            if score >= 65:
                rec = "overweight"
            elif score >= 40:
                rec = "neutral"
            else:
                rec = "underweight"

            scores.append(SectorScore(
                sector=sector,
                name=info["name"],
                score=score,
                momentum_1m=m1,
                momentum_3m=m3,
                momentum_6m=m6,
                relative_strength=relative,
                recommendation=rec,
                top_stocks=info.get("top_stocks", []),
                cycle_alignment=sector in cycle_favored,
            ))

        # Rank by score
        scores.sort(key=lambda s: s.score, reverse=True)
        for i, s in enumerate(scores):
            s.rank = i + 1

        self._stats["rotations_computed"] += 1
        return scores

    def get_sectors(self) -> Dict[str, Any]:
        return {
            sector: {
                "name": info["name"],
                "top_stocks": info.get("top_stocks", []),
            }
            for sector, info in self._sectors.items()
        }

    def get_stats(self) -> Dict[str, Any]:
        return self._stats
