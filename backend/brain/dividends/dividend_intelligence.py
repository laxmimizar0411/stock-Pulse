"""Dividend Intelligence Engine — Phase 3.8

Analyzes dividend patterns for Indian stocks:
1. Dividend yield analysis and ranking
2. Payout ratio trends (consistency)
3. Dividend growth rate (CAGR)
4. Ex-date calendar
5. Dividend sustainability score
6. Sector comparison
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DividendRecord:
    """A single dividend record."""
    symbol: str
    ex_date: Optional[date] = None
    amount_per_share: float = 0.0
    dividend_type: str = "final"  # "interim", "final", "special"
    face_value: float = 10.0
    payout_ratio_pct: float = 0.0


@dataclass
class DividendAnalysis:
    """Comprehensive dividend analysis."""
    symbol: str
    current_yield_pct: float = 0.0
    trailing_12m_dividend: float = 0.0
    dividend_growth_5yr_cagr: float = 0.0
    payout_ratio_pct: float = 0.0
    consecutive_dividend_years: int = 0
    sustainability_score: float = 0.0  # 0-100
    grade: str = "NA"  # "Aristocrat", "Consistent", "Growing", "Irregular", "Non-payer"
    upcoming_ex_dates: List[Dict[str, Any]] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "current_yield_pct": round(self.current_yield_pct, 2),
            "trailing_12m_dividend": round(self.trailing_12m_dividend, 2),
            "dividend_growth_5yr_cagr": round(self.dividend_growth_5yr_cagr, 2),
            "payout_ratio_pct": round(self.payout_ratio_pct, 2),
            "consecutive_dividend_years": self.consecutive_dividend_years,
            "sustainability_score": round(self.sustainability_score, 2),
            "grade": self.grade,
            "upcoming_ex_dates": self.upcoming_ex_dates[:5],
            "history": self.history[:10],
            "computed_at": self.computed_at.isoformat(),
        }


class DividendIntelligence:
    """Dividend analysis and intelligence engine."""

    def __init__(self):
        self._stats = {"analyses": 0}

    def analyze(
        self,
        symbol: str,
        current_price: float = 100.0,
        dividends: Optional[List[DividendRecord]] = None,
        eps: float = 10.0,
        consecutive_years: int = 5,
    ) -> DividendAnalysis:
        """Analyze dividend profile."""
        if dividends is None:
            dividends = []

        # Calculate trailing 12M dividend
        trailing = sum(d.amount_per_share for d in dividends[:4])  # Last 4 entries

        # Current yield
        yield_pct = (trailing / current_price * 100) if current_price > 0 else 0

        # Payout ratio
        payout = (trailing / eps * 100) if eps > 0 else 0

        # Growth CAGR (simple proxy)
        if len(dividends) >= 6:
            recent = sum(d.amount_per_share for d in dividends[:2])
            old = sum(d.amount_per_share for d in dividends[-2:])
            if old > 0 and recent > 0:
                years = min(5, len(dividends) // 2)
                growth = ((recent / old) ** (1 / max(years, 1)) - 1) * 100
            else:
                growth = 0
        else:
            growth = 0

        # Sustainability score
        sustainability = 0.0
        if consecutive_years >= 10:
            sustainability += 40
        elif consecutive_years >= 5:
            sustainability += 25
        elif consecutive_years >= 3:
            sustainability += 15

        if 20 <= payout <= 60:
            sustainability += 30  # Healthy payout
        elif payout < 20:
            sustainability += 15  # Conservative
        elif payout <= 80:
            sustainability += 10  # High but manageable

        if growth > 5:
            sustainability += 20
        elif growth > 0:
            sustainability += 10

        if yield_pct >= 2:
            sustainability += 10
        elif yield_pct >= 1:
            sustainability += 5

        # Grade
        if consecutive_years >= 10 and growth > 0:
            grade = "Aristocrat"
        elif consecutive_years >= 5:
            grade = "Consistent"
        elif growth > 10:
            grade = "Growing"
        elif consecutive_years >= 1:
            grade = "Irregular"
        else:
            grade = "Non-payer"

        result = DividendAnalysis(
            symbol=symbol,
            current_yield_pct=yield_pct,
            trailing_12m_dividend=trailing,
            dividend_growth_5yr_cagr=growth,
            payout_ratio_pct=payout,
            consecutive_dividend_years=consecutive_years,
            sustainability_score=min(100, sustainability),
            grade=grade,
            history=[
                {
                    "ex_date": str(d.ex_date) if d.ex_date else None,
                    "amount": d.amount_per_share,
                    "type": d.dividend_type,
                }
                for d in dividends[:10]
            ],
        )

        self._stats["analyses"] += 1
        return result

    def get_stats(self) -> Dict[str, Any]:
        return self._stats
