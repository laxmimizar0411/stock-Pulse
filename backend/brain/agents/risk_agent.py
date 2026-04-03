"""
Risk Agent (Veto Power) — Phase 3.3

The Risk Agent reviews the trade plan and can:
1. APPROVE — trade proceeds as planned
2. MODIFY — adjust position size, stops, targets
3. VETO — block the trade entirely

Veto triggers:
- Drawdown limit exceeded
- Concentration risk too high
- Market regime extremely volatile
- Stop-loss too wide relative to position
- Correlation with existing positions

Uses Tier 1 (gemini-2.5-flash).
"""

import logging
from typing import Any, Dict

from brain.agents.base_agent import BaseAgent, AgentResult
from brain.agents.gemini_llm import GeminiLLM

logger = logging.getLogger(__name__)


class RiskAgent(BaseAgent):
    """Reviews trade plans with veto power."""

    def __init__(self, llm: GeminiLLM):
        super().__init__("RiskAgent", "risk", llm)

    def _build_prompt(self, symbol: str, context: Dict[str, Any]) -> str:
        trade_plan = context.get("trade_plan", {})
        portfolio = context.get("portfolio", {})
        regime = context.get("regime", "unknown")
        drawdown = context.get("current_drawdown_pct", 0)

        return f"""You are the Risk Agent with VETO POWER for an Indian equity trading system.
Your primary job is CAPITAL PROTECTION. You can approve, modify, or veto any trade.

Proposed Trade:
  Symbol: {symbol}
  Action: {trade_plan.get('signal', 'HOLD')}
  Entry: {trade_plan.get('analysis', {}).get('entry_price', 'N/A')}
  Stop-Loss: {trade_plan.get('analysis', {}).get('stop_loss', 'N/A')}
  Targets: T1={trade_plan.get('analysis', {}).get('target_1', 'N/A')}, 
           T2={trade_plan.get('analysis', {}).get('target_2', 'N/A')}
  Position Size: {trade_plan.get('analysis', {}).get('position_size_pct', 5)}%
  Confidence: {trade_plan.get('confidence', 0.5)}
  Reasoning: {trade_plan.get('reasoning', '')}

Risk Context:
  Market Regime: {regime}
  Current Drawdown: {drawdown}%
  Portfolio: {str(portfolio)[:500]}

VETO RULES:
1. VETO if drawdown > 15% and trade is a BUY
2. VETO if position size > 10% for single stock
3. VETO if stop-loss > 8% from entry
4. VETO if regime is 'crisis' and trade is a BUY
5. MODIFY if risk/reward < 1.5

Provide your decision as JSON:
{{
  "decision": "APPROVE" or "MODIFY" or "VETO",
  "signal": "BUY" or "SELL" or "HOLD",
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<2-3 sentence risk assessment>",
  "key_factors": ["risk factor 1", "risk factor 2"],
  "risks": ["identified risk 1", "identified risk 2"],
  "veto_reason": "<reason if vetoed, else null>",
  "modifications": {{
    "adjusted_position_size_pct": <float or null>,
    "adjusted_stop_loss": <float or null>,
    "adjusted_target": <float or null>
  }},
  "risk_score": <float 0.0 to 1.0, where 1.0 is highest risk>,
  "max_loss_pct": <estimated max loss percentage>
}}

IMPORTANT: Return ONLY the JSON, no markdown."""

    def _parse_response(self, response: Dict[str, Any]) -> AgentResult:
        decision = response.get("decision", "APPROVE")

        # If vetoed, override signal to HOLD
        if decision == "VETO":
            signal = "HOLD"
        else:
            signal = response.get("signal", "HOLD")

        return AgentResult(
            agent_name=self._name,
            agent_type=self._agent_type,
            signal=signal,
            confidence=float(response.get("confidence", 0.5)),
            reasoning=response.get("reasoning", ""),
            key_factors=response.get("key_factors", []),
            risks=response.get("risks", []),
            analysis={
                "decision": decision,
                "veto_reason": response.get("veto_reason"),
                "modifications": response.get("modifications", {}),
                "risk_score": response.get("risk_score", 0.5),
                "max_loss_pct": response.get("max_loss_pct", 0),
            },
        )
