"""
LLM Multi-Agent System — Phase 3.3

2-Tier Gemini LLM Routing:
  Tier 1: gemini-2.5-flash (deep analysis — analyst agents, synthesizer)
  Tier 2: gemini-2.0-flash (extraction — data extraction, formatting)

Agent Roster:
  1. Technical Analyst Agent
  2. Fundamental Analyst Agent
  3. Macro Analyst Agent
  4. Event-Driven Analyst Agent
  5. Bull Researcher Agent
  6. Bear Researcher Agent
  7. Synthesizer Agent
  8. Trader Agent
  9. Risk Agent (veto power)
  10. Report Generator Agent
"""

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
from brain.agents.orchestrator import AgentOrchestrator

__all__ = [
    "GeminiLLM", "get_gemini_tier1", "get_gemini_tier2",
    "TechnicalAnalystAgent", "FundamentalAnalystAgent",
    "MacroAnalystAgent", "EventDrivenAnalystAgent",
    "BullResearcherAgent", "BearResearcherAgent",
    "SynthesizerAgent", "TraderAgent", "RiskAgent",
    "ReportGeneratorAgent", "AgentOrchestrator",
]
