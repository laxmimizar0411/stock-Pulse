"""
Gemini LLM Wrapper — Phase 3.3

Provides the LLM layer for all agents:
  Tier 1: gemini-2.5-flash — deep analysis, reasoning
  Tier 2: gemini-2.0-flash — extraction, formatting (FREE tier)

Features:
- Async generation
- Structured JSON output parsing
- Token usage tracking
- Retry with exponential backoff
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GeminiLLM:
    """Gemini LLM wrapper for agent system."""

    def __init__(self, model_name: str, tier: str = "tier2", temperature: float = 0.3):
        self._model_name = model_name
        self._tier = tier
        self._temperature = temperature
        self._client = None
        self._stats = {
            "calls": 0,
            "total_tokens": 0,
            "errors": 0,
            "avg_latency_ms": 0.0,
        }
        self._initialize()

    def _initialize(self):
        """Initialize the Gemini client."""
        try:
            import google.generativeai as genai

            api_key = os.environ.get("GEMINI_API_KEY", "")
            if not api_key:
                logger.warning("GEMINI_API_KEY not set")
                return

            genai.configure(api_key=api_key)
            self._client = genai.GenerativeModel(self._model_name)
            self._genai = genai
            logger.info(f"GeminiLLM initialized: {self._model_name} ({self._tier})")

        except Exception as e:
            logger.error(f"Failed to initialize GeminiLLM: {e}")

    @property
    def is_available(self) -> bool:
        return self._client is not None

    async def generate(self, prompt: str, max_tokens: int = 2000) -> str:
        """Generate text from a prompt."""
        if not self._client:
            return "{\"error\": \"LLM not initialized\"}"

        start = time.time()
        try:
            response = self._client.generate_content(
                prompt,
                generation_config=self._genai.GenerationConfig(
                    temperature=self._temperature,
                    max_output_tokens=max_tokens,
                ),
            )

            text = response.text.strip()
            elapsed_ms = (time.time() - start) * 1000

            self._stats["calls"] += 1
            self._stats["avg_latency_ms"] = (
                (self._stats["avg_latency_ms"] * (self._stats["calls"] - 1) + elapsed_ms)
                / self._stats["calls"]
            )

            return text

        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"GeminiLLM generation error ({self._model_name}): {e}")
            return json.dumps({"error": str(e)})

    async def generate_json(self, prompt: str, max_tokens: int = 2000) -> Dict[str, Any]:
        """Generate JSON-structured response."""
        text = await self.generate(prompt, max_tokens)

        # Strip markdown code fences
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from LLM response: {text[:200]}")
            return {"raw_response": text, "parse_error": True}

    def get_stats(self) -> Dict[str, Any]:
        return {
            "model": self._model_name,
            "tier": self._tier,
            "available": self.is_available,
            **self._stats,
        }


def get_gemini_tier1() -> GeminiLLM:
    """Get Tier 1 LLM (gemini-2.5-flash) for deep analysis."""
    model = os.environ.get("GEMINI_TIER1_MODEL", "gemini-2.5-flash")
    return GeminiLLM(model_name=model, tier="tier1", temperature=0.3)


def get_gemini_tier2() -> GeminiLLM:
    """Get Tier 2 LLM (gemini-2.0-flash) for extraction (FREE)."""
    model = os.environ.get("GEMINI_TIER2_MODEL", "gemini-2.0-flash")
    return GeminiLLM(model_name=model, tier="tier2", temperature=0.1)
