"""
Trader Agent — Phase 3.3

Converts the synthesized recommendation into an actionable trade plan:
- Entry price / entry zone
- Position sizing suggestion
- Stop-loss level
- Target levels (T1, T2, T3)
- Time horizon
- Order type recommendation

Uses Tier 1 (gemini-2.5-flash).
"""

import logging
from typing import Any, Dict

from brain.agents.base_agent import BaseAgent, AgentResult
from brain.agents.gemini_llm import GeminiLLM

logger = logging.getLogger(__name__)


class TraderAgent(BaseAgent):
    """Converts analysis into actionable trade execution plan."""

    def __init__(self, llm: GeminiLLM):
        super().__init__("Trader", "trader", llm)

    def _build_prompt(self, symbol: str, context: Dict[str, Any]) -> str:
        synthesis = context.get("synthesis", {})
        current_price = context.get("current_price", "unknown")
        regime = context.get("regime", "unknown")
        position_size_pct = context.get("position_size_pct", 5.0)

        return f"""You are a Trader Agent for Indian equities. Convert the synthesis into a trade plan.

Symbol: {symbol}
Current Price: {current_price}
Market Regime: {regime}
Suggested Position Size: {position_size_pct}% of portfolio

Synthesis:
  Signal: {synthesis.get('signal', 'HOLD')}
  Confidence: {synthesis.get('confidence', 0.5)}
  Reasoning: {synthesis.get('reasoning', '')}
  Key Factors: {synthesis.get('key_factors', [])}
  Risks: {synthesis.get('risks', [])}

Generate a trade plan as JSON:
{{
  "action": "BUY" or "SELL" or "HOLD" or "WAIT",
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<2-3 sentence trade rationale>",
  "entry_price": <float or null>,
  "stop_loss": <float or null>,
  "target_1": <float or null>,
  "target_2": <float or null>,
  "target_3": <float or null>,
  "position_size_pct": <float>,
  "order_type": "MARKET" or "LIMIT" or "SL" or "SL-LIMIT",
  "time_horizon_days": <int>,
  "risk_reward_ratio": <float>,
  "key_factors": ["factor1", "factor2"],
  "risks": ["risk1", "risk2"]
}}

IMPORTANT: Return ONLY the JSON, no markdown."""

    def _parse_response(self, response: Dict[str, Any]) -> AgentResult:
        return AgentResult(
            agent_name=self._name,
            agent_type=self._agent_type,
            signal=response.get("action", "HOLD"),
            confidence=float(response.get("confidence", 0.5)),
            reasoning=response.get("reasoning", ""),
            key_factors=response.get("key_factors", []),
            risks=response.get("risks", []),
            analysis={
                "entry_price": response.get("entry_price"),
                "stop_loss": response.get("stop_loss"),
                "target_1": response.get("target_1"),
                "target_2": response.get("target_2"),
                "target_3": response.get("target_3"),
                "position_size_pct": response.get("position_size_pct", 5.0),
                "order_type": response.get("order_type", "LIMIT"),
                "time_horizon_days": response.get("time_horizon_days", 30),
                "risk_reward_ratio": response.get("risk_reward_ratio", 0),
            },
        )
