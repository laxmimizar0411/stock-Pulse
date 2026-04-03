"""Risk Management Engine — Phase 3.4

Unified risk management with:
- VaR (Historical + Parametric + Monte Carlo) + CVaR
- Stress Testing (2008 GFC, COVID 2020, Demonetization 2016)
- SEBI Margin Compliance
- HRP Portfolio Optimization

Previously existing modules:
- capital_protection.py — Drawdown control
- indian_costs.py — Indian market cost model
- portfolio_risk.py — Portfolio-level risk metrics
- position_sizer.py — Position sizing (Kelly)
- stop_loss_engine.py — Stop-loss strategies
"""

from brain.risk.var_calculator import VaRCalculator, VaRResult
from brain.risk.stress_testing import StressTestEngine, StressTestResult, HISTORICAL_SCENARIOS
from brain.risk.sebi_compliance import SEBIComplianceEngine, SEBIMarginResult
from brain.risk.hrp_portfolio import HRPOptimizer, HRPResult

__all__ = [
    "VaRCalculator", "VaRResult",
    "StressTestEngine", "StressTestResult", "HISTORICAL_SCENARIOS",
    "SEBIComplianceEngine", "SEBIMarginResult",
    "HRPOptimizer", "HRPResult",
]
