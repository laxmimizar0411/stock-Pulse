"""
Bull / Bear Researcher Agents — Phase 3.3

Present both sides of the investment thesis:
- Bull Researcher: Makes the strongest case FOR buying
- Bear Researcher: Makes the strongest case AGAINST buying

Both use Tier 1 (gemini-2.5-flash) for deep reasoning.
"""

import logging
from typing import Any, Dict

from brain.agents.base_agent import BaseAgent, AgentResult
from brain.agents.gemini_llm import GeminiLLM

logger = logging.getLogger(__name__)


class BullResearcherAgent(BaseAgent):
    """Makes the strongest case for buying a stock."""

    def __init__(self, llm: GeminiLLM):
        super().__init__("BullResearcher", "researcher", llm)

    def _build_prompt(self, symbol: str, context: Dict[str, Any]) -> str:
        analyst_results = context.get("analyst_results", [])
        analyst_summary = "\n".join(
            f"- {r.get('agent_name', 'Agent')}: {r.get('signal', 'HOLD')} "
            f"(confidence: {r.get('confidence', 0):.2f}) — {r.get('reasoning', '')}"
            for r in analyst_results
        )

        return f"""You are a Bull Researcher. Your job is to make the STRONGEST possible case 
for BUYING {symbol} based on the analyst reports below.

Analyst Reports:
{analyst_summary}

Additional Context:
Sentiment: {str(context.get('sentiment', {}))[:300]}
Regime: {context.get('regime', 'unknown')}

Present the bull case as a JSON object:
{{
  "signal": "BUY",
  "confidence": <float 0.0 to 1.0 — how strong is the bull case>,
  "reasoning": "<3-4 sentence bull thesis>",
  "key_factors": ["bullish factor 1", "bullish factor 2", "bullish factor 3"],
  "catalysts": ["near-term catalyst 1", "catalyst 2"],
  "target_upside_pct": <estimated upside percentage>,
  "conviction": "high" or "medium" or "low"
}}

IMPORTANT: Return ONLY the JSON, no markdown."""

    def _parse_response(self, response: Dict[str, Any]) -> AgentResult:
        return AgentResult(
            agent_name=self._name,
            agent_type=self._agent_type,
            signal="BUY",
            confidence=float(response.get("confidence", 0.5)),
            reasoning=response.get("reasoning", ""),
            key_factors=response.get("key_factors", []),
            risks=[],
            analysis={
                "catalysts": response.get("catalysts", []),
                "target_upside_pct": response.get("target_upside_pct", 0),
                "conviction": response.get("conviction", "medium"),
            },
        )


class BearResearcherAgent(BaseAgent):
    """Makes the strongest case against buying a stock."""

    def __init__(self, llm: GeminiLLM):
        super().__init__("BearResearcher", "researcher", llm)

    def _build_prompt(self, symbol: str, context: Dict[str, Any]) -> str:
        analyst_results = context.get("analyst_results", [])
        analyst_summary = "\n".join(
            f"- {r.get('agent_name', 'Agent')}: {r.get('signal', 'HOLD')} "
            f"(confidence: {r.get('confidence', 0):.2f}) — {r.get('reasoning', '')}"
            for r in analyst_results
        )

        return f"""You are a Bear Researcher. Your job is to make the STRONGEST possible case 
AGAINST buying {symbol} (i.e., for SELLING or avoiding it).

Analyst Reports:
{analyst_summary}

Additional Context:
Sentiment: {str(context.get('sentiment', {}))[:300]}
Regime: {context.get('regime', 'unknown')}

Present the bear case as a JSON object:
{{
  "signal": "SELL",
  "confidence": <float 0.0 to 1.0 — how strong is the bear case>,
  "reasoning": "<3-4 sentence bear thesis>",
  "key_factors": ["bearish factor 1", "bearish factor 2", "bearish factor 3"],
  "risks": ["key risk 1", "key risk 2", "key risk 3"],
  "target_downside_pct": <estimated downside percentage>,
  "conviction": "high" or "medium" or "low"
}}

IMPORTANT: Return ONLY the JSON, no markdown."""

    def _parse_response(self, response: Dict[str, Any]) -> AgentResult:
        return AgentResult(
            agent_name=self._name,
            agent_type=self._agent_type,
            signal="SELL",
            confidence=float(response.get("confidence", 0.5)),
            reasoning=response.get("reasoning", ""),
            key_factors=response.get("key_factors", []),
            risks=response.get("risks", []),
            analysis={
                "target_downside_pct": response.get("target_downside_pct", 0),
                "conviction": response.get("conviction", "medium"),
            },
        )
