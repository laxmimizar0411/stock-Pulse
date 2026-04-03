"""
Analyst Agents — Phase 3.3

4 specialist analyst agents:
1. Technical Analyst — chart patterns, indicators, support/resistance
2. Fundamental Analyst — financials, valuations, earnings quality
3. Macro Analyst — macro economy, interest rates, FII/DII flows
4. Event-Driven Analyst — news events, corporate actions, regulatory

All use Tier 1 (gemini-2.5-flash) for deep analysis.
"""

import logging
from typing import Any, Dict

from brain.agents.base_agent import BaseAgent, AgentResult
from brain.agents.gemini_llm import GeminiLLM

logger = logging.getLogger(__name__)


class TechnicalAnalystAgent(BaseAgent):
    """Analyzes price action, chart patterns, and technical indicators."""

    def __init__(self, llm: GeminiLLM):
        super().__init__("TechnicalAnalyst", "analyst", llm)

    def _build_prompt(self, symbol: str, context: Dict[str, Any]) -> str:
        features = context.get("features", {})
        price_data = context.get("price_data", {})
        regime = context.get("regime", "unknown")

        return f"""You are an expert Technical Analyst specializing in Indian equities (NSE/BSE).

Analyze {symbol} using the following data:

Current Market Regime: {regime}
Price Data: {str(price_data)[:1000]}
Technical Features: {str(features)[:1500]}

Provide your analysis as a JSON object:
{{
  "signal": "BUY" or "SELL" or "HOLD",
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<2-3 sentence technical analysis>",
  "key_factors": ["factor1", "factor2", "factor3"],
  "risks": ["risk1", "risk2"],
  "support_level": <float or null>,
  "resistance_level": <float or null>,
  "trend": "bullish" or "bearish" or "sideways",
  "momentum": "strong" or "moderate" or "weak",
  "pattern": "<detected chart pattern or 'none'>"
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
                "support_level": response.get("support_level"),
                "resistance_level": response.get("resistance_level"),
                "trend": response.get("trend", "unknown"),
                "momentum": response.get("momentum", "unknown"),
                "pattern": response.get("pattern", "none"),
            },
        )


class FundamentalAnalystAgent(BaseAgent):
    """Analyzes financial statements, valuations, and earnings quality."""

    def __init__(self, llm: GeminiLLM):
        super().__init__("FundamentalAnalyst", "analyst", llm)

    def _build_prompt(self, symbol: str, context: Dict[str, Any]) -> str:
        financials = context.get("financials", {})
        valuations = context.get("valuations", {})
        sector = context.get("sector", "unknown")

        return f"""You are an expert Fundamental Analyst specializing in Indian equities.

Analyze {symbol} (Sector: {sector}) using:

Financial Data: {str(financials)[:1500]}
Valuation Metrics: {str(valuations)[:1000]}

Provide your analysis as a JSON object:
{{
  "signal": "BUY" or "SELL" or "HOLD",
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<2-3 sentence fundamental analysis>",
  "key_factors": ["factor1", "factor2", "factor3"],
  "risks": ["risk1", "risk2"],
  "fair_value_estimate": <float or null>,
  "earnings_quality": "high" or "medium" or "low",
  "growth_outlook": "strong" or "moderate" or "weak",
  "valuation_status": "undervalued" or "fairly_valued" or "overvalued"
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
                "fair_value_estimate": response.get("fair_value_estimate"),
                "earnings_quality": response.get("earnings_quality", "medium"),
                "growth_outlook": response.get("growth_outlook", "moderate"),
                "valuation_status": response.get("valuation_status", "fairly_valued"),
            },
        )


class MacroAnalystAgent(BaseAgent):
    """Analyzes macro economy, interest rates, FII/DII flows, currency."""

    def __init__(self, llm: GeminiLLM):
        super().__init__("MacroAnalyst", "analyst", llm)

    def _build_prompt(self, symbol: str, context: Dict[str, Any]) -> str:
        macro_data = context.get("macro_data", {})
        fii_dii = context.get("fii_dii", {})
        sector = context.get("sector", "unknown")

        return f"""You are an expert Macro Analyst specializing in Indian markets.

Analyze {symbol} (Sector: {sector}) in the context of:

Macro Data: {str(macro_data)[:1500]}
FII/DII Flows: {str(fii_dii)[:800]}

Provide your analysis as a JSON object:
{{
  "signal": "BUY" or "SELL" or "HOLD",
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<2-3 sentence macro analysis with impact on {symbol}>",
  "key_factors": ["factor1", "factor2", "factor3"],
  "risks": ["risk1", "risk2"],
  "rate_impact": "positive" or "negative" or "neutral",
  "flow_direction": "inflow" or "outflow" or "mixed",
  "currency_impact": "positive" or "negative" or "neutral",
  "sector_tailwind": true or false
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
                "rate_impact": response.get("rate_impact", "neutral"),
                "flow_direction": response.get("flow_direction", "mixed"),
                "currency_impact": response.get("currency_impact", "neutral"),
                "sector_tailwind": response.get("sector_tailwind", False),
            },
        )


class EventDrivenAnalystAgent(BaseAgent):
    """Analyzes news events, corporate actions, and regulatory changes."""

    def __init__(self, llm: GeminiLLM):
        super().__init__("EventDrivenAnalyst", "analyst", llm)

    def _build_prompt(self, symbol: str, context: Dict[str, Any]) -> str:
        news = context.get("news_headlines", [])
        sentiment = context.get("sentiment", {})
        corporate_actions = context.get("corporate_actions", [])

        news_text = "\n".join(f"- {h}" for h in news[:10])

        return f"""You are an expert Event-Driven Analyst specializing in Indian equities.

Analyze {symbol} based on recent events:

Recent News Headlines:
{news_text}

Sentiment Data: {str(sentiment)[:500]}
Corporate Actions: {str(corporate_actions)[:500]}

Provide your analysis as a JSON object:
{{
  "signal": "BUY" or "SELL" or "HOLD",
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<2-3 sentence event-driven analysis>",
  "key_factors": ["factor1", "factor2", "factor3"],
  "risks": ["risk1", "risk2"],
  "event_impact": "very_positive" or "positive" or "neutral" or "negative" or "very_negative",
  "catalyst_type": "earnings" or "corporate_action" or "regulatory" or "market_event" or "none",
  "time_sensitivity": "immediate" or "short_term" or "medium_term" or "long_term"
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
                "event_impact": response.get("event_impact", "neutral"),
                "catalyst_type": response.get("catalyst_type", "none"),
                "time_sensitivity": response.get("time_sensitivity", "medium_term"),
            },
        )
