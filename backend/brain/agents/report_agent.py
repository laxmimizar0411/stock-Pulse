"""
Report Generator Agent — Phase 3.3

Generates human-readable investment reports from the full analysis pipeline.
Uses Tier 2 (gemini-2.0-flash) for formatting (cost-efficient).
"""

import logging
from typing import Any, Dict

from brain.agents.base_agent import BaseAgent, AgentResult
from brain.agents.gemini_llm import GeminiLLM

logger = logging.getLogger(__name__)


class ReportGeneratorAgent(BaseAgent):
    """Generates structured investment reports."""

    def __init__(self, llm: GeminiLLM):
        super().__init__("ReportGenerator", "report", llm)

    def _build_prompt(self, symbol: str, context: Dict[str, Any]) -> str:
        synthesis = context.get("synthesis", {})
        trade_plan = context.get("trade_plan", {})
        risk_review = context.get("risk_review", {})
        analyst_results = context.get("analyst_results", [])
        bull_case = context.get("bull_case", {})
        bear_case = context.get("bear_case", {})

        analyst_summary = "\n".join(
            f"  - {r.get('agent_name', 'Agent')}: {r.get('signal', 'HOLD')} "
            f"(confidence: {r.get('confidence', 0):.2f})"
            for r in analyst_results
        )

        return f"""You are a Report Generator for an Indian stock analysis platform.
Generate a comprehensive yet concise investment report for {symbol}.

Final Recommendation:
  Signal: {synthesis.get('signal', 'HOLD')}
  Confidence: {synthesis.get('confidence', 0.5)}
  Reasoning: {synthesis.get('reasoning', '')}

Trade Plan:
  Action: {trade_plan.get('signal', 'HOLD')}
  Entry: {trade_plan.get('analysis', {}).get('entry_price', 'N/A')}
  Stop: {trade_plan.get('analysis', {}).get('stop_loss', 'N/A')}
  Target: {trade_plan.get('analysis', {}).get('target_1', 'N/A')}

Risk Review:
  Decision: {risk_review.get('analysis', {}).get('decision', 'N/A')}
  Risk Score: {risk_review.get('analysis', {}).get('risk_score', 'N/A')}
  Reasoning: {risk_review.get('reasoning', '')}

Analyst Views:
{analyst_summary}

Bull Case: {bull_case.get('reasoning', 'N/A')}
Bear Case: {bear_case.get('reasoning', 'N/A')}

Generate the report as JSON:
{{
  "signal": "BUY" or "SELL" or "HOLD",
  "confidence": <float>,
  "reasoning": "<executive summary in 3-4 sentences>",
  "key_factors": ["top 3 factors driving the recommendation"],
  "risks": ["top 3 risks to watch"],
  "report": {{
    "title": "<Report title>",
    "executive_summary": "<2-3 paragraph summary>",
    "technical_view": "<1 paragraph>",
    "fundamental_view": "<1 paragraph>",
    "bull_case": "<1 paragraph>",
    "bear_case": "<1 paragraph>",
    "trade_recommendation": "<1 paragraph with entry, stop, target>",
    "risk_assessment": "<1 paragraph>",
    "disclaimer": "This is AI-generated analysis for educational purposes only. Not financial advice. Consult a SEBI-registered advisor."
  }}
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
                "report": response.get("report", {}),
            },
        )
