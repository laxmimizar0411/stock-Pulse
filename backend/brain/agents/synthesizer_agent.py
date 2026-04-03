"""
Synthesizer Agent — Phase 3.3

Combines all analyst and researcher perspectives into a single
cohesive recommendation with confidence-weighted consensus.

Uses Tier 1 (gemini-2.5-flash) for deep reasoning.
"""

import logging
from typing import Any, Dict, List

from brain.agents.base_agent import BaseAgent, AgentResult
from brain.agents.gemini_llm import GeminiLLM

logger = logging.getLogger(__name__)


class SynthesizerAgent(BaseAgent):
    """Synthesizes all agent perspectives into a final recommendation."""

    def __init__(self, llm: GeminiLLM):
        super().__init__("Synthesizer", "synthesizer", llm)

    def _build_prompt(self, symbol: str, context: Dict[str, Any]) -> str:
        all_results = context.get("all_results", [])

        reports = []
        for r in all_results:
            reports.append(
                f"  {r.get('agent_name', 'Agent')} ({r.get('agent_type', 'unknown')}): "
                f"{r.get('signal', 'HOLD')} (confidence: {r.get('confidence', 0):.2f})\n"
                f"    Reasoning: {r.get('reasoning', 'N/A')}\n"
                f"    Key factors: {r.get('key_factors', [])}"
            )
        reports_text = "\n\n".join(reports)

        return f"""You are the Synthesizer Agent. You receive analyses from multiple specialist agents
and must produce a SINGLE, well-reasoned final recommendation for {symbol}.

Agent Reports:
{reports_text}

Market Regime: {context.get('regime', 'unknown')}
Overall Sentiment: {context.get('sentiment_score', 'N/A')}

Rules:
1. Weight analyst confidence — higher confidence agents get more weight
2. If bull and bear cases are equally strong, recommend HOLD
3. Consider market regime when weighting signals
4. Your confidence should reflect the consensus strength

Provide your synthesis as a JSON object:
{{
  "signal": "BUY" or "SELL" or "HOLD",
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<3-5 sentence synthesized reasoning>",
  "key_factors": ["top factor 1", "top factor 2", "top factor 3"],
  "risks": ["top risk 1", "top risk 2"],
  "bull_bear_balance": <float -1 to +1, where -1=strong bear, +1=strong bull>,
  "consensus_strength": "strong" or "moderate" or "weak" or "divided",
  "time_horizon": "short_term" or "medium_term" or "long_term",
  "price_target_direction": "up" or "down" or "flat"
}}

IMPORTANT: Return ONLY the JSON, no markdown."""

    def _parse_response(self, response: Dict[str, Any]) -> AgentResult:
        return AgentResult(
            agent_name=self._name,
            agent_type=self._agent_type,
            signal=response.get("signal", "HOLD"),
            confidence=float(response.get("confidence", 0.5)),
            reasoning=response.get("reasoning", ""),
            key_factors=response.get("key_factors", []),
            risks=response.get("risks", []),
            analysis={
                "bull_bear_balance": response.get("bull_bear_balance", 0),
                "consensus_strength": response.get("consensus_strength", "moderate"),
                "time_horizon": response.get("time_horizon", "medium_term"),
                "price_target_direction": response.get("price_target_direction", "flat"),
            },
        )
