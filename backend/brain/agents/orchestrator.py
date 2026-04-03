"""
Agent Orchestrator — Phase 3.3

LangGraph-style orchestration of the multi-agent pipeline:

  Stage 1: 4 Analyst Agents (parallel) → Technical, Fundamental, Macro, Event-Driven
  Stage 2: Bull/Bear Researchers (parallel) → Present both sides
  Stage 3: Synthesizer → Combine all perspectives
  Stage 4: Trader Agent → Generate trade plan
  Stage 5: Risk Agent → Review with veto power
  Stage 6: Report Generator → Human-readable report

Uses LangGraph StateGraph for orchestration flow.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from brain.agents.gemini_llm import GeminiLLM, get_gemini_tier1, get_gemini_tier2
from brain.agents.analyst_agents import (
    TechnicalAnalystAgent,
    FundamentalAnalystAgent,
    MacroAnalystAgent,
    EventDrivenAnalystAgent,
)
from brain.agents.research_agents import BullResearcherAgent, BearResearcherAgent
from brain.agents.synthesizer_agent import SynthesizerAgent
from brain.agents.trader_agent import TraderAgent
from brain.agents.risk_agent import RiskAgent
from brain.agents.report_agent import ReportGeneratorAgent

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """Complete result from the agent orchestration pipeline."""
    symbol: str
    final_signal: str = "HOLD"
    final_confidence: float = 0.5
    risk_decision: str = "APPROVE"
    analyst_results: List[Dict[str, Any]] = field(default_factory=list)
    bull_case: Dict[str, Any] = field(default_factory=dict)
    bear_case: Dict[str, Any] = field(default_factory=dict)
    synthesis: Dict[str, Any] = field(default_factory=dict)
    trade_plan: Dict[str, Any] = field(default_factory=dict)
    risk_review: Dict[str, Any] = field(default_factory=dict)
    report: Dict[str, Any] = field(default_factory=dict)
    total_latency_ms: float = 0.0
    stages_completed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "final_signal": self.final_signal,
            "final_confidence": round(self.final_confidence, 4),
            "risk_decision": self.risk_decision,
            "analyst_results": self.analyst_results,
            "bull_case": self.bull_case,
            "bear_case": self.bear_case,
            "synthesis": self.synthesis,
            "trade_plan": self.trade_plan,
            "risk_review": self.risk_review,
            "report": self.report,
            "total_latency_ms": round(self.total_latency_ms, 1),
            "stages_completed": self.stages_completed,
            "errors": self.errors,
            "timestamp": self.timestamp.isoformat(),
        }


class AgentOrchestrator:
    """
    Orchestrates the multi-agent pipeline using a LangGraph-style state machine.

    Pipeline:
      Stage 1: Analysts (parallel)   → 4 specialist analyses
      Stage 2: Researchers (parallel) → Bull + Bear perspectives
      Stage 3: Synthesizer            → Combined recommendation
      Stage 4: Trader                 → Trade execution plan
      Stage 5: Risk Agent             → Approve / Modify / Veto
      Stage 6: Report Generator       → Human-readable report
    """

    def __init__(self):
        # Initialize LLMs
        self._tier1 = get_gemini_tier1()
        self._tier2 = get_gemini_tier2()

        # Initialize agents
        self._technical = TechnicalAnalystAgent(self._tier1)
        self._fundamental = FundamentalAnalystAgent(self._tier1)
        self._macro = MacroAnalystAgent(self._tier1)
        self._event_driven = EventDrivenAnalystAgent(self._tier1)

        self._bull = BullResearcherAgent(self._tier1)
        self._bear = BearResearcherAgent(self._tier1)

        self._synthesizer = SynthesizerAgent(self._tier1)
        self._trader = TraderAgent(self._tier1)
        self._risk = RiskAgent(self._tier1)
        self._report_gen = ReportGeneratorAgent(self._tier2)  # Tier 2 for formatting

        self._stats = {
            "total_runs": 0,
            "vetoed_trades": 0,
            "approved_trades": 0,
            "modified_trades": 0,
            "avg_latency_ms": 0.0,
        }

    @property
    def is_available(self) -> bool:
        return self._tier1.is_available

    async def analyze_symbol(
        self,
        symbol: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> OrchestratorResult:
        """
        Run the full multi-agent analysis pipeline for a symbol.

        Args:
            symbol: Stock symbol (e.g., "RELIANCE")
            context: Optional context dict with features, sentiment, regime, etc.

        Returns:
            OrchestratorResult with all agent outputs
        """
        start = time.time()
        result = OrchestratorResult(symbol=symbol)
        ctx = context or {}

        if not self.is_available:
            result.errors.append("LLM not available (no API key)")
            return result

        try:
            # ---- Stage 1: Analyst Agents (parallel) ----
            logger.info(f"[{symbol}] Stage 1: Running 4 analyst agents...")
            analyst_tasks = [
                self._technical.analyze(symbol, ctx),
                self._fundamental.analyze(symbol, ctx),
                self._macro.analyze(symbol, ctx),
                self._event_driven.analyze(symbol, ctx),
            ]
            analyst_outputs = await asyncio.gather(*analyst_tasks, return_exceptions=True)

            analyst_results = []
            for output in analyst_outputs:
                if isinstance(output, Exception):
                    result.errors.append(f"Analyst error: {output}")
                    continue
                analyst_results.append(output.to_dict())

            result.analyst_results = analyst_results
            result.stages_completed.append("analysts")
            logger.info(f"[{symbol}] Stage 1 complete: {len(analyst_results)} analysts")

            # ---- Stage 2: Bull/Bear Researchers (parallel) ----
            logger.info(f"[{symbol}] Stage 2: Running bull/bear researchers...")
            research_ctx = {**ctx, "analyst_results": analyst_results}

            bull_task = self._bull.analyze(symbol, research_ctx)
            bear_task = self._bear.analyze(symbol, research_ctx)
            bull_result, bear_result = await asyncio.gather(bull_task, bear_task, return_exceptions=True)

            if isinstance(bull_result, Exception):
                result.errors.append(f"Bull researcher error: {bull_result}")
                result.bull_case = {}
            else:
                result.bull_case = bull_result.to_dict()

            if isinstance(bear_result, Exception):
                result.errors.append(f"Bear researcher error: {bear_result}")
                result.bear_case = {}
            else:
                result.bear_case = bear_result.to_dict()

            result.stages_completed.append("researchers")
            logger.info(f"[{symbol}] Stage 2 complete")

            # ---- Stage 3: Synthesizer ----
            logger.info(f"[{symbol}] Stage 3: Synthesizing...")
            synth_ctx = {
                **ctx,
                "all_results": analyst_results + [
                    result.bull_case, result.bear_case
                ],
            }
            synth_result = await self._synthesizer.analyze(symbol, synth_ctx)
            result.synthesis = synth_result.to_dict()
            result.stages_completed.append("synthesizer")
            logger.info(f"[{symbol}] Stage 3 complete: {synth_result.signal} ({synth_result.confidence:.2f})")

            # ---- Stage 4: Trader Agent ----
            logger.info(f"[{symbol}] Stage 4: Generating trade plan...")
            trader_ctx = {
                **ctx,
                "synthesis": synth_result.to_dict(),
                "current_price": ctx.get("current_price", "unknown"),
            }
            trader_result = await self._trader.analyze(symbol, trader_ctx)
            result.trade_plan = trader_result.to_dict()
            result.stages_completed.append("trader")
            logger.info(f"[{symbol}] Stage 4 complete: {trader_result.signal}")

            # ---- Stage 5: Risk Agent (Veto Power) ----
            logger.info(f"[{symbol}] Stage 5: Risk review...")
            risk_ctx = {
                **ctx,
                "trade_plan": trader_result.to_dict(),
            }
            risk_result = await self._risk.analyze(symbol, risk_ctx)
            result.risk_review = risk_result.to_dict()
            result.risk_decision = risk_result.analysis.get("decision", "APPROVE")
            result.stages_completed.append("risk")
            logger.info(f"[{symbol}] Stage 5 complete: {result.risk_decision}")

            # Apply risk decision
            if result.risk_decision == "VETO":
                result.final_signal = "HOLD"
                result.final_confidence = risk_result.confidence
                self._stats["vetoed_trades"] += 1
            elif result.risk_decision == "MODIFY":
                result.final_signal = synth_result.signal
                result.final_confidence = synth_result.confidence * 0.8  # Reduce confidence
                self._stats["modified_trades"] += 1
            else:
                result.final_signal = synth_result.signal
                result.final_confidence = synth_result.confidence
                self._stats["approved_trades"] += 1

            # ---- Stage 6: Report Generator ----
            logger.info(f"[{symbol}] Stage 6: Generating report...")
            report_ctx = {
                "synthesis": synth_result.to_dict(),
                "trade_plan": trader_result.to_dict(),
                "risk_review": risk_result.to_dict(),
                "analyst_results": analyst_results,
                "bull_case": result.bull_case,
                "bear_case": result.bear_case,
            }
            report_result = await self._report_gen.analyze(symbol, report_ctx)
            result.report = report_result.to_dict()
            result.stages_completed.append("report")
            logger.info(f"[{symbol}] Stage 6 complete")

        except Exception as e:
            logger.exception(f"Orchestrator pipeline failed for {symbol}")
            result.errors.append(f"Pipeline error: {str(e)}")

        result.total_latency_ms = (time.time() - start) * 1000
        self._stats["total_runs"] += 1
        self._stats["avg_latency_ms"] = (
            (self._stats["avg_latency_ms"] * (self._stats["total_runs"] - 1)
             + result.total_latency_ms)
            / self._stats["total_runs"]
        )

        logger.info(
            f"[{symbol}] Pipeline COMPLETE: {result.final_signal} "
            f"(confidence: {result.final_confidence:.2f}, "
            f"risk: {result.risk_decision}, "
            f"latency: {result.total_latency_ms:.0f}ms)"
        )

        return result

    def get_stats(self) -> Dict[str, Any]:
        return {
            "orchestrator": self._stats,
            "tier1_llm": self._tier1.get_stats(),
            "tier2_llm": self._tier2.get_stats(),
            "agents": {
                "technical": self._technical.get_stats(),
                "fundamental": self._fundamental.get_stats(),
                "macro": self._macro.get_stats(),
                "event_driven": self._event_driven.get_stats(),
                "bull": self._bull.get_stats(),
                "bear": self._bear.get_stats(),
                "synthesizer": self._synthesizer.get_stats(),
                "trader": self._trader.get_stats(),
                "risk": self._risk.get_stats(),
                "report": self._report_gen.get_stats(),
            },
        }
