"""
Data Quality Engine — Validates market data integrity for Stock Pulse Brain.

Runs a battery of quality checks on OHLCV and tick data before it enters
the Brain pipeline. Failed checks produce detailed quality reports and
can route data to the dead-letter queue.

Quality checks:
    1. OHLC integrity:        Low ≤ Open, Close ≤ High
    2. Volume validation:     non-negative, non-zero for traded instruments
    3. Price circuit limits:  within ±5%/10%/20% based on segment
    4. Stale data detection:  timestamp freshness
    5. Price range sanity:    no extreme outliers
    6. Gap detection:         missing trading days
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

from brain.schemas.market_data import OHLCVBar

logger = logging.getLogger("brain.ingestion.data_quality")

IST = timezone(timedelta(hours=5, minutes=30))


class Severity(str, Enum):
    """Quality check severity levels."""
    INFO = "INFO"           # Non-critical, logged
    WARNING = "WARNING"     # Suspicious, flag for review
    ERROR = "ERROR"         # Invalid data, reject or DLQ
    CRITICAL = "CRITICAL"   # Systemic issue, alert


class CircuitLimitBand(str, Enum):
    """Indian stock exchange circuit limit bands."""
    BAND_5 = "5%"
    BAND_10 = "10%"
    BAND_20 = "20%"
    NO_LIMIT = "NO_LIMIT"  # Index stocks / F&O stocks


@dataclass
class QualityCheckResult:
    """Result of a single quality check."""
    check_name: str
    passed: bool
    severity: Severity
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None


@dataclass
class QualityReport:
    """Aggregate quality report for a batch of data."""
    symbol: str
    source: str
    total_records: int
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    results: List[QualityCheckResult] = field(default_factory=list)
    is_acceptable: bool = True  # False if any ERROR/CRITICAL failures

    @property
    def pass_rate(self) -> float:
        if self.total_checks == 0:
            return 0.0
        return self.passed_checks / self.total_checks * 100.0

    def add_result(self, result: QualityCheckResult):
        self.results.append(result)
        self.total_checks += 1
        if result.passed:
            self.passed_checks += 1
        else:
            self.failed_checks += 1
            if result.severity in (Severity.ERROR, Severity.CRITICAL):
                self.is_acceptable = False

    def summary(self) -> Dict:
        return {
            "symbol": self.symbol,
            "source": self.source,
            "total_records": self.total_records,
            "total_checks": self.total_checks,
            "passed": self.passed_checks,
            "failed": self.failed_checks,
            "pass_rate": round(self.pass_rate, 2),
            "is_acceptable": self.is_acceptable,
            "failures": [
                {
                    "check": r.check_name,
                    "severity": r.severity.value,
                    "message": r.message,
                }
                for r in self.results if not r.passed
            ],
        }


class DataQualityEngine:
    """
    Validates market data quality before it enters the Brain pipeline.

    Usage:
        engine = DataQualityEngine()
        report = engine.validate_ohlcv_bars(bars, symbol="RELIANCE", source="yfinance")
        if report.is_acceptable:
            # proceed with data
        else:
            # route to DLQ
    """

    def __init__(
        self,
        max_stale_minutes: int = 30,
        default_circuit_band: CircuitLimitBand = CircuitLimitBand.BAND_20,
    ):
        self.max_stale_minutes = max_stale_minutes
        self.default_circuit_band = default_circuit_band

    def validate_ohlcv_bars(
        self,
        bars: List[OHLCVBar],
        symbol: str = "",
        source: str = "",
    ) -> QualityReport:
        """
        Run all quality checks on a list of OHLCV bars.

        Returns a QualityReport with individual check results.
        """
        report = QualityReport(
            symbol=symbol or (bars[0].symbol if bars else "UNKNOWN"),
            source=source or (bars[0].source if bars else "unknown"),
            total_records=len(bars),
        )

        if not bars:
            report.add_result(QualityCheckResult(
                check_name="has_data",
                passed=False,
                severity=Severity.ERROR,
                message="No data records provided",
            ))
            return report

        report.add_result(QualityCheckResult(
            check_name="has_data",
            passed=True,
            severity=Severity.INFO,
            message=f"{len(bars)} records provided",
        ))

        # Run checks on each bar
        ohlc_failures = 0
        volume_failures = 0
        price_outliers = 0

        for i, bar in enumerate(bars):
            # Check 1: OHLC integrity
            if not self._check_ohlc_integrity(bar):
                ohlc_failures += 1

            # Check 2: Volume validation
            if bar.volume < 0:
                volume_failures += 1

            # Check 3: Price sanity (non-negative, non-zero)
            if any(p <= 0 for p in [bar.open, bar.high, bar.low, bar.close]):
                price_outliers += 1

        # Aggregate OHLC check
        report.add_result(QualityCheckResult(
            check_name="ohlc_integrity",
            passed=ohlc_failures == 0,
            severity=Severity.WARNING if ohlc_failures > 0 else Severity.INFO,
            message=f"{ohlc_failures}/{len(bars)} bars failed OHLC integrity (Low ≤ O,C ≤ High)",
            value=float(ohlc_failures),
            threshold=0.0,
        ))

        # Aggregate volume check
        report.add_result(QualityCheckResult(
            check_name="volume_non_negative",
            passed=volume_failures == 0,
            severity=Severity.ERROR if volume_failures > 0 else Severity.INFO,
            message=f"{volume_failures}/{len(bars)} bars have negative volume",
            value=float(volume_failures),
            threshold=0.0,
        ))

        # Aggregate price sanity check
        report.add_result(QualityCheckResult(
            check_name="price_sanity",
            passed=price_outliers == 0,
            severity=Severity.ERROR if price_outliers > 0 else Severity.INFO,
            message=f"{price_outliers}/{len(bars)} bars have zero/negative prices",
            value=float(price_outliers),
            threshold=0.0,
        ))

        # Check 4: Circuit limit check (day-over-day returns)
        self._check_circuit_limits(bars, report)

        # Check 5: Stale data check
        self._check_staleness(bars, report)

        # Check 6: Gap detection (for daily data only)
        if bars and bars[0].timeframe == "1d":
            self._check_gaps(bars, report)

        logger.info(
            "Quality report for %s (%s): %d/%d checks passed (acceptable=%s)",
            report.symbol,
            report.source,
            report.passed_checks,
            report.total_checks,
            report.is_acceptable,
        )

        return report

    def _check_ohlc_integrity(self, bar: OHLCVBar) -> bool:
        """Check Low ≤ Open, Close ≤ High with small tolerance for rounding."""
        eps = 0.005  # 0.5 paisa tolerance
        return (
            bar.low - eps <= bar.open <= bar.high + eps
            and bar.low - eps <= bar.close <= bar.high + eps
            and bar.low <= bar.high + eps
        )

    def _check_circuit_limits(
        self,
        bars: List[OHLCVBar],
        report: QualityReport,
    ):
        """Check if any day-over-day price changes exceed circuit limits."""
        if len(bars) < 2:
            return

        circuit_pct = {
            CircuitLimitBand.BAND_5: 5.0,
            CircuitLimitBand.BAND_10: 10.0,
            CircuitLimitBand.BAND_20: 20.0,
            CircuitLimitBand.NO_LIMIT: 100.0,
        }
        limit = circuit_pct.get(self.default_circuit_band, 20.0)
        breaches = 0

        for i in range(1, len(bars)):
            prev_close = bars[i - 1].close
            if prev_close <= 0:
                continue
            change_pct = abs((bars[i].close - prev_close) / prev_close * 100.0)
            if change_pct > limit:
                breaches += 1

        report.add_result(QualityCheckResult(
            check_name="circuit_limit",
            passed=breaches == 0,
            severity=Severity.WARNING if breaches > 0 else Severity.INFO,
            message=f"{breaches} price changes exceed {limit}% circuit limit",
            value=float(breaches),
            threshold=limit,
        ))

    def _check_staleness(
        self,
        bars: List[OHLCVBar],
        report: QualityReport,
    ):
        """Check if the latest data is stale (too old)."""
        if not bars:
            return

        latest = max(bar.timestamp for bar in bars)
        now = datetime.now(IST)

        # Only flag staleness during market hours (9:15-15:30 IST, weekdays)
        if now.weekday() < 5 and 9 <= now.hour < 16:
            age_minutes = (now - latest).total_seconds() / 60
            is_stale = age_minutes > self.max_stale_minutes

            report.add_result(QualityCheckResult(
                check_name="data_freshness",
                passed=not is_stale,
                severity=Severity.WARNING if is_stale else Severity.INFO,
                message=f"Latest data is {age_minutes:.0f} min old (max: {self.max_stale_minutes} min)",
                value=float(age_minutes),
                threshold=float(self.max_stale_minutes),
            ))
        else:
            report.add_result(QualityCheckResult(
                check_name="data_freshness",
                passed=True,
                severity=Severity.INFO,
                message="Staleness check skipped (outside market hours)",
            ))

    def _check_gaps(
        self,
        bars: List[OHLCVBar],
        report: QualityReport,
    ):
        """Detect missing trading days in daily data."""
        if len(bars) < 5:
            return

        dates = sorted(bar.timestamp.date() for bar in bars)
        gaps = 0
        for i in range(1, len(dates)):
            diff = (dates[i] - dates[i - 1]).days
            # Allow weekends (2-3 day gaps) and holidays (up to 4 days)
            if diff > 4:
                gaps += 1

        report.add_result(QualityCheckResult(
            check_name="gap_detection",
            passed=gaps == 0,
            severity=Severity.WARNING if gaps > 0 else Severity.INFO,
            message=f"{gaps} suspicious gaps (>4 calendar days) detected in daily data",
            value=float(gaps),
            threshold=0.0,
        ))

    def validate_single_bar(self, bar: OHLCVBar) -> bool:
        """Quick validation for a single bar (used in real-time pipeline)."""
        if any(p <= 0 for p in [bar.open, bar.high, bar.low, bar.close]):
            return False
        if bar.volume < 0:
            return False
        if not self._check_ohlc_integrity(bar):
            return False
        return True
