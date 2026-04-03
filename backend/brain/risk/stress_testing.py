"""Stress Testing Engine — Phase 3.4

Historical stress scenarios for Indian market context:
1. Global Financial Crisis (2008) — ~60% drawdown in NIFTY
2. COVID-19 Crash (March 2020) — ~38% drawdown in 1 month
3. Demonetization (Nov 2016) — ~6% drawdown, sector-specific impacts
4. Taper Tantrum (2013) — ~12% drawdown, rupee depreciation
5. IL&FS Crisis (2018) — ~15% drawdown, NBFC liquidity crisis

Custom scenarios can also be defined.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class StressScenario:
    """Definition of a stress scenario."""
    name: str
    description: str
    year: int
    nifty_drawdown_pct: float  # How much NIFTY fell
    duration_days: int
    sector_impacts: Dict[str, float] = field(default_factory=dict)  # sector -> multiplier
    fx_impact_pct: float = 0.0  # INR depreciation %
    volatility_spike_factor: float = 1.0  # How much VIX spiked
    recovery_days: int = 0


# Pre-defined historical stress scenarios
HISTORICAL_SCENARIOS = {
    "gfc_2008": StressScenario(
        name="Global Financial Crisis 2008",
        description="Lehman collapse, global credit freeze. NIFTY fell ~60% from peak.",
        year=2008,
        nifty_drawdown_pct=-60.0,
        duration_days=365,
        sector_impacts={
            "banking": 1.3, "finance": 1.4, "real_estate": 1.5,
            "metals": 1.6, "it": 1.1, "pharma": 0.7,
            "fmcg": 0.6, "auto": 1.3, "energy": 1.4,
        },
        fx_impact_pct=-20.0,
        volatility_spike_factor=4.0,
        recovery_days=450,
    ),
    "covid_2020": StressScenario(
        name="COVID-19 Crash (March 2020)",
        description="Pandemic lockdown panic. NIFTY fell ~38% in 1 month.",
        year=2020,
        nifty_drawdown_pct=-38.0,
        duration_days=33,
        sector_impacts={
            "aviation": 2.0, "hospitality": 1.8, "auto": 1.3,
            "banking": 1.4, "pharma": 0.5, "it": 0.8,
            "fmcg": 0.7, "energy": 1.5, "real_estate": 1.3,
        },
        fx_impact_pct=-8.0,
        volatility_spike_factor=5.0,
        recovery_days=120,
    ),
    "demonetization_2016": StressScenario(
        name="Demonetization (Nov 2016)",
        description="500/1000 rupee notes banned. Selective sector impact.",
        year=2016,
        nifty_drawdown_pct=-6.3,
        duration_days=45,
        sector_impacts={
            "real_estate": 2.5, "nbfc": 1.5, "banking": 1.2,
            "consumer": 1.3, "auto": 1.4, "pharma": 0.8,
            "it": 0.6, "digital_payments": -0.5,  # benefited
        },
        fx_impact_pct=-2.0,
        volatility_spike_factor=1.8,
        recovery_days=90,
    ),
    "taper_tantrum_2013": StressScenario(
        name="Taper Tantrum (2013)",
        description="Fed taper fears. FII outflows, rupee crash.",
        year=2013,
        nifty_drawdown_pct=-12.0,
        duration_days=60,
        sector_impacts={
            "banking": 1.5, "finance": 1.4, "it": 0.7,
            "pharma": 0.6, "metals": 1.3, "auto": 1.2,
        },
        fx_impact_pct=-15.0,
        volatility_spike_factor=2.5,
        recovery_days=180,
    ),
    "ilfs_2018": StressScenario(
        name="IL&FS Crisis (2018)",
        description="NBFC liquidity crisis. Credit freeze in shadow banking.",
        year=2018,
        nifty_drawdown_pct=-15.0,
        duration_days=90,
        sector_impacts={
            "nbfc": 2.5, "housing_finance": 2.0, "banking": 1.3,
            "real_estate": 1.5, "auto": 1.2, "it": 0.8,
            "pharma": 0.7, "fmcg": 0.6,
        },
        fx_impact_pct=-5.0,
        volatility_spike_factor=2.0,
        recovery_days=150,
    ),
}


@dataclass
class StressTestResult:
    """Result of a stress test."""
    symbol: str
    scenario_name: str
    portfolio_value: float = 0.0
    stressed_value: float = 0.0
    loss_amount: float = 0.0
    loss_pct: float = 0.0
    sector_multiplier: float = 1.0
    scenario_details: Dict[str, Any] = field(default_factory=dict)
    recovery_estimate_days: int = 0
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "scenario": self.scenario_name,
            "portfolio_value": round(self.portfolio_value, 2),
            "stressed_value": round(self.stressed_value, 2),
            "loss_amount": round(self.loss_amount, 2),
            "loss_pct": round(self.loss_pct, 4),
            "sector_multiplier": round(self.sector_multiplier, 2),
            "recovery_estimate_days": self.recovery_estimate_days,
            "scenario_details": self.scenario_details,
            "computed_at": self.computed_at.isoformat(),
        }


class StressTestEngine:
    """Runs historical stress tests on portfolios."""

    def __init__(self):
        self._scenarios = HISTORICAL_SCENARIOS
        self._stats = {"tests_run": 0}

    def run_stress_test(
        self,
        symbol: str,
        portfolio_value: float = 1000000.0,
        sector: str = "general",
        scenario_names: Optional[List[str]] = None,
    ) -> Dict[str, StressTestResult]:
        """Run stress tests for given scenarios."""
        if scenario_names is None:
            scenario_names = list(self._scenarios.keys())

        results = {}
        for name in scenario_names:
            scenario = self._scenarios.get(name)
            if not scenario:
                continue

            # Get sector-specific impact multiplier
            sector_mult = scenario.sector_impacts.get(sector.lower(), 1.0)

            # Apply stress: base drawdown × sector multiplier
            drawdown_pct = scenario.nifty_drawdown_pct * sector_mult
            stressed_value = portfolio_value * (1 + drawdown_pct / 100)
            loss = portfolio_value - stressed_value

            result = StressTestResult(
                symbol=symbol,
                scenario_name=scenario.name,
                portfolio_value=portfolio_value,
                stressed_value=max(0, stressed_value),
                loss_amount=loss,
                loss_pct=drawdown_pct / 100,
                sector_multiplier=sector_mult,
                recovery_estimate_days=int(scenario.recovery_days * sector_mult),
                scenario_details={
                    "year": scenario.year,
                    "description": scenario.description,
                    "nifty_drawdown_pct": scenario.nifty_drawdown_pct,
                    "duration_days": scenario.duration_days,
                    "fx_impact_pct": scenario.fx_impact_pct,
                    "volatility_spike_factor": scenario.volatility_spike_factor,
                },
            )
            results[name] = result

        self._stats["tests_run"] += 1
        return results

    def get_available_scenarios(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": key,
                "name": s.name,
                "year": s.year,
                "nifty_drawdown_pct": s.nifty_drawdown_pct,
                "description": s.description,
            }
            for key, s in self._scenarios.items()
        ]

    def get_stats(self) -> Dict[str, Any]:
        return self._stats
