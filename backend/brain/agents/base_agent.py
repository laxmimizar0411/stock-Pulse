"""
Base Agent — Phase 3.3

Provides the abstract base class for all specialist agents.
Each agent has:
  - A role/persona prompt
  - Access to an LLM (Tier 1 or Tier 2)
  - An analyze() method that returns structured analysis
  - State tracking for the orchestrator
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from brain.agents.gemini_llm import GeminiLLM

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Standard result from any agent."""
    agent_name: str
    agent_type: str
    analysis: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    signal: str = "HOLD"  # BUY / SELL / HOLD
    reasoning: str = ""
    key_factors: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    latency_ms: float = 0.0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "signal": self.signal,
            "confidence": round(self.confidence, 4),
            "reasoning": self.reasoning,
            "key_factors": self.key_factors[:5],
            "risks": self.risks[:5],
            "analysis": self.analysis,
            "latency_ms": round(self.latency_ms, 1),
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


class BaseAgent(ABC):
    """Abstract base class for all agents in the multi-agent system."""

    def __init__(self, name: str, agent_type: str, llm: GeminiLLM):
        self._name = name
        self._agent_type = agent_type
        self._llm = llm
        self._call_count = 0
        self._total_latency = 0.0

    @property
    def name(self) -> str:
        return self._name

    @property
    def agent_type(self) -> str:
        return self._agent_type

    @abstractmethod
    def _build_prompt(self, symbol: str, context: Dict[str, Any]) -> str:
        """Build the analysis prompt. Must be implemented by subclasses."""
        ...

    @abstractmethod
    def _parse_response(self, response: Dict[str, Any]) -> AgentResult:
        """Parse the LLM response into AgentResult. Must be implemented by subclasses."""
        ...

    async def analyze(self, symbol: str, context: Dict[str, Any]) -> AgentResult:
        """Run analysis for a symbol with given context."""
        start = time.time()
        try:
            prompt = self._build_prompt(symbol, context)
            response = await self._llm.generate_json(prompt)

            result = self._parse_response(response)
            result.latency_ms = (time.time() - start) * 1000
            result.agent_name = self._name
            result.agent_type = self._agent_type

            self._call_count += 1
            self._total_latency += result.latency_ms

            return result

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.error(f"Agent {self._name} failed for {symbol}: {e}")
            return AgentResult(
                agent_name=self._name,
                agent_type=self._agent_type,
                error=str(e),
                latency_ms=elapsed,
            )

    def get_stats(self) -> Dict[str, Any]:
        return {
            "name": self._name,
            "type": self._agent_type,
            "calls": self._call_count,
            "avg_latency_ms": (
                self._total_latency / self._call_count
                if self._call_count > 0 else 0
            ),
            "llm": self._llm.get_stats() if self._llm else {},
        }
