"""Regulatory Event Calendar — Phase 3.9

Tracks and alerts on key regulatory and market events:
1. SEBI board meetings and circular dates
2. RBI monetary policy dates
3. Union Budget date
4. GST council meetings
5. F&O expiry dates (monthly, weekly)
6. Corporate earnings seasons
7. Index rebalancing dates
8. Tax deadlines (advance tax, ITR)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    """A regulatory or market event."""
    event_id: str = ""
    title: str = ""
    event_type: str = ""  # "rbi", "sebi", "expiry", "earnings", "budget", "tax"
    date: Optional[date] = None
    description: str = ""
    impact: str = "medium"  # "high", "medium", "low"
    affected_sectors: List[str] = field(default_factory=list)
    recurring: bool = False
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "type": self.event_type,
            "date": str(self.date) if self.date else None,
            "description": self.description,
            "impact": self.impact,
            "affected_sectors": self.affected_sectors,
            "recurring": self.recurring,
            "source": self.source,
        }


# Recurring events template for a fiscal year
def _generate_recurring_events(year: int) -> List[CalendarEvent]:
    """Generate recurring regulatory events for a fiscal year."""
    events = []

    # RBI Monetary Policy (bi-monthly, 6 per year)
    rbi_months = [2, 4, 6, 8, 10, 12]
    for i, m in enumerate(rbi_months):
        events.append(CalendarEvent(
            event_id=f"rbi_policy_{year}_{m}",
            title=f"RBI Monetary Policy - {['Feb','Apr','Jun','Aug','Oct','Dec'][i]} {year}",
            event_type="rbi",
            date=date(year, m, 6),  # Approximate
            description="RBI interest rate decision and monetary policy statement",
            impact="high",
            affected_sectors=["banking", "nbfc", "real_estate", "auto"],
            recurring=True,
            source="RBI",
        ))

    # Union Budget (Feb 1)
    events.append(CalendarEvent(
        event_id=f"budget_{year}",
        title=f"Union Budget {year}",
        event_type="budget",
        date=date(year, 2, 1),
        description="Annual Union Budget presentation",
        impact="high",
        affected_sectors=["all"],
        recurring=True,
        source="Finance Ministry",
    ))

    # Monthly F&O Expiry (last Thursday of each month)
    for m in range(1, 13):
        # Find last Thursday
        last_day = date(year, m + 1, 1) - timedelta(days=1) if m < 12 else date(year, 12, 31)
        while last_day.weekday() != 3:  # Thursday
            last_day -= timedelta(days=1)
        events.append(CalendarEvent(
            event_id=f"fno_expiry_{year}_{m:02d}",
            title=f"F&O Monthly Expiry - {last_day.strftime('%b %Y')}",
            event_type="expiry",
            date=last_day,
            description="Monthly F&O expiry. Expect increased volatility.",
            impact="medium",
            affected_sectors=["all"],
            recurring=True,
            source="NSE",
        ))

    # Advance Tax Deadlines
    for m, label in [(6, "Q1"), (9, "Q2"), (12, "Q3"), (3, "Q4")]:
        y = year if m >= 4 else year + 1
        events.append(CalendarEvent(
            event_id=f"advance_tax_{y}_{label}",
            title=f"Advance Tax Deadline - {label} FY{year}-{year+1-2000}",
            event_type="tax",
            date=date(y, m, 15),
            description=f"{label} advance tax installment deadline",
            impact="low",
            affected_sectors=["all"],
            recurring=True,
            source="Income Tax Dept",
        ))

    # NIFTY 50 rebalancing (March and September)
    for m, label in [(3, "March"), (9, "September")]:
        events.append(CalendarEvent(
            event_id=f"nifty_rebalance_{year}_{m}",
            title=f"NIFTY 50 Index Rebalancing - {label} {year}",
            event_type="sebi",
            date=date(year, m, 28),
            description="Semi-annual NIFTY 50 index reconstitution",
            impact="medium",
            affected_sectors=["all"],
            recurring=True,
            source="NSE Indices",
        ))

    # Earnings Seasons
    for m, q in [(4, "Q4"), (7, "Q1"), (10, "Q2"), (1, "Q3")]:
        y = year if m >= 4 else year + 1
        events.append(CalendarEvent(
            event_id=f"earnings_{y}_{q}",
            title=f"Earnings Season - {q} FY{year}-{year+1-2000}",
            event_type="earnings",
            date=date(y, m, 15),
            description=f"{q} quarterly results season begins",
            impact="high",
            affected_sectors=["all"],
            recurring=True,
            source="BSE/NSE",
        ))

    return events


class RegulatoryCalendar:
    """Regulatory event calendar for Indian markets."""

    def __init__(self):
        self._events: List[CalendarEvent] = []
        self._stats = {"events_loaded": 0, "queries": 0}

    def initialize(self, years: Optional[List[int]] = None):
        """Load events for given years."""
        if years is None:
            current = datetime.now().year
            years = [current, current + 1]

        for year in years:
            self._events.extend(_generate_recurring_events(year))

        # Sort by date
        self._events.sort(key=lambda e: e.date or date.min)
        self._stats["events_loaded"] = len(self._events)
        logger.info(f"Regulatory Calendar: {len(self._events)} events loaded")

    def get_upcoming(self, days: int = 30, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get upcoming events within N days."""
        self._stats["queries"] += 1
        today = date.today()
        cutoff = today + timedelta(days=days)

        results = []
        for event in self._events:
            if event.date and today <= event.date <= cutoff:
                if event_type is None or event.event_type == event_type:
                    results.append(event.to_dict())

        return results

    def get_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        """Get all events of a type."""
        return [e.to_dict() for e in self._events if e.event_type == event_type]

    def add_event(self, event: CalendarEvent):
        """Add a custom event."""
        self._events.append(event)
        self._events.sort(key=lambda e: e.date or date.min)
        self._stats["events_loaded"] = len(self._events)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_events": len(self._events),
            **self._stats,
        }
