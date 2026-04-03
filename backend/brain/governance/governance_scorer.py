"""Corporate Governance Scoring — Phase 3.6

Scores companies on governance quality using:
1. Promoter holding & pledge percentage
2. Board independence ratio
3. Auditor reputation & tenure
4. Related-party transaction ratio
5. Regulatory compliance history
6. Dividend consistency
7. Management turnover
8. Disclosure quality

Scoring: 0-100 scale, higher = better governance.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GovernanceScore:
    """Corporate governance score for a company."""
    symbol: str
    total_score: float = 0.0  # 0-100
    grade: str = "NA"  # A+, A, B+, B, C+, C, D
    components: Dict[str, float] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "total_score": round(self.total_score, 2),
            "grade": self.grade,
            "components": {k: round(v, 2) for k, v in self.components.items()},
            "flags": self.flags,
            "computed_at": self.computed_at.isoformat(),
        }


def _score_to_grade(score: float) -> str:
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B+"
    if score >= 60:
        return "B"
    if score >= 50:
        return "C+"
    if score >= 40:
        return "C"
    return "D"


class GovernanceScorer:
    """Corporate governance scoring engine."""

    def __init__(self):
        self._stats = {"scores_computed": 0}

    def score(
        self,
        symbol: str,
        promoter_holding_pct: float = 50.0,
        promoter_pledge_pct: float = 0.0,
        board_independence_ratio: float = 0.5,
        big4_auditor: bool = True,
        auditor_tenure_years: int = 3,
        related_party_txn_pct: float = 5.0,
        regulatory_penalties: int = 0,
        dividend_consistency_years: int = 5,
        mgmt_turnover_3yr: int = 1,
        timely_disclosures: bool = True,
    ) -> GovernanceScore:
        """Compute governance score."""
        components = {}
        flags = []

        # 1. Promoter holding (20 pts max)
        if promoter_holding_pct >= 60:
            components["promoter_holding"] = 20.0
        elif promoter_holding_pct >= 40:
            components["promoter_holding"] = 15.0
        elif promoter_holding_pct >= 25:
            components["promoter_holding"] = 10.0
        else:
            components["promoter_holding"] = 5.0
            flags.append("Low promoter holding")

        # 2. Promoter pledge (15 pts max, inverse)
        if promoter_pledge_pct == 0:
            components["promoter_pledge"] = 15.0
        elif promoter_pledge_pct < 10:
            components["promoter_pledge"] = 10.0
        elif promoter_pledge_pct < 25:
            components["promoter_pledge"] = 5.0
        else:
            components["promoter_pledge"] = 0.0
            flags.append(f"High promoter pledge: {promoter_pledge_pct}%")

        # 3. Board independence (15 pts)
        if board_independence_ratio >= 0.5:
            components["board_independence"] = 15.0
        elif board_independence_ratio >= 0.33:
            components["board_independence"] = 10.0
        else:
            components["board_independence"] = 5.0
            flags.append("Low board independence")

        # 4. Auditor quality (10 pts)
        aud_score = 5.0 if big4_auditor else 2.0
        if 3 <= auditor_tenure_years <= 10:
            aud_score += 5.0
        elif auditor_tenure_years > 10:
            aud_score += 2.0
            flags.append("Long auditor tenure (>10 years)")
        components["auditor_quality"] = aud_score

        # 5. Related-party transactions (10 pts, inverse)
        if related_party_txn_pct < 2:
            components["related_party_txn"] = 10.0
        elif related_party_txn_pct < 5:
            components["related_party_txn"] = 7.0
        elif related_party_txn_pct < 10:
            components["related_party_txn"] = 4.0
        else:
            components["related_party_txn"] = 0.0
            flags.append(f"High related-party transactions: {related_party_txn_pct}%")

        # 6. Regulatory compliance (10 pts)
        if regulatory_penalties == 0:
            components["regulatory_compliance"] = 10.0
        elif regulatory_penalties <= 2:
            components["regulatory_compliance"] = 5.0
        else:
            components["regulatory_compliance"] = 0.0
            flags.append(f"Multiple regulatory penalties: {regulatory_penalties}")

        # 7. Dividend consistency (10 pts)
        if dividend_consistency_years >= 10:
            components["dividend_consistency"] = 10.0
        elif dividend_consistency_years >= 5:
            components["dividend_consistency"] = 7.0
        elif dividend_consistency_years >= 3:
            components["dividend_consistency"] = 4.0
        else:
            components["dividend_consistency"] = 2.0

        # 8. Management stability (5 pts)
        if mgmt_turnover_3yr <= 1:
            components["management_stability"] = 5.0
        elif mgmt_turnover_3yr <= 3:
            components["management_stability"] = 3.0
        else:
            components["management_stability"] = 0.0
            flags.append("High management turnover")

        # 9. Disclosure quality (5 pts)
        components["disclosure_quality"] = 5.0 if timely_disclosures else 2.0

        total = sum(components.values())

        result = GovernanceScore(
            symbol=symbol,
            total_score=total,
            grade=_score_to_grade(total),
            components=components,
            flags=flags,
        )

        self._stats["scores_computed"] += 1
        return result

    def get_stats(self) -> Dict[str, Any]:
        return self._stats
