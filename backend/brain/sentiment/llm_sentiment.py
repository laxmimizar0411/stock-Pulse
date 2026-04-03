"""
Gemini LLM Sentiment Service — Phase 3.2

Provides LLM-based sentiment analysis using Google Gemini models:
- Tier 2 (gemini-2.0-flash, FREE): Used for sentiment extraction (lightweight)
- Tier 1 (gemini-2.5-flash): Used for deep analysis when needed

Part of the sentiment ensemble: 0.5×FinBERT + 0.2×VADER + 0.3×LLM(Gemini)
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_gemini_client = None


def _get_gemini_client():
    """Lazy-load Gemini client."""
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client

    try:
        import google.generativeai as genai

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set, LLM sentiment unavailable")
            return None

        genai.configure(api_key=api_key)
        _gemini_client = genai
        logger.info("✅ Gemini client initialized for LLM sentiment")
        return _gemini_client

    except Exception as e:
        logger.warning(f"Failed to initialize Gemini client: {e}")
        return None


async def analyze_sentiment_llm(
    symbol: str,
    headlines: List[str],
    model_name: Optional[str] = None,
) -> Optional[float]:
    """
    Analyze sentiment of headlines using Gemini LLM.
    
    Returns a sentiment score between -1.0 (very negative) and +1.0 (very positive),
    or None if analysis fails.
    
    Uses Tier 2 (gemini-2.0-flash) by default for cost efficiency.
    """
    genai = _get_gemini_client()
    if genai is None:
        return None

    if not headlines:
        return None

    model = model_name or os.environ.get("GEMINI_TIER2_MODEL", "gemini-2.0-flash")

    # Build prompt
    headlines_text = "\n".join(f"- {h}" for h in headlines[:10])
    prompt = f"""You are a financial sentiment analyst specializing in the Indian stock market.

Analyze these recent news headlines about {symbol} and provide a sentiment score.

Headlines:
{headlines_text}

Respond with ONLY a JSON object (no markdown, no explanation):
{{"score": <float between -1.0 and 1.0>, "label": "<positive|negative|neutral>", "reason": "<one sentence>"}}

Score guide: -1.0 = extremely bearish, -0.5 = bearish, 0.0 = neutral, 0.5 = bullish, 1.0 = extremely bullish"""

    try:
        gen_model = genai.GenerativeModel(model)
        response = gen_model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=200,
            ),
        )

        text = response.text.strip()
        
        # Parse JSON response
        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)
        score = float(data.get("score", 0.0))
        score = max(-1.0, min(1.0, score))

        logger.debug(f"LLM sentiment for {symbol}: {score:.2f} ({data.get('label', 'neutral')})")
        return score

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse Gemini sentiment response: {e}")
        return None
    except Exception as e:
        logger.warning(f"Gemini sentiment analysis failed for {symbol}: {e}")
        return None


async def analyze_deep_llm(
    prompt: str,
    model_name: Optional[str] = None,
) -> Optional[str]:
    """
    Deep analysis using Tier 1 Gemini model.
    Used for earnings call analysis and complex financial reasoning.
    
    Returns raw text response from the model.
    """
    genai = _get_gemini_client()
    if genai is None:
        return None

    model = model_name or os.environ.get("GEMINI_TIER1_MODEL", "gemini-2.5-flash")

    try:
        gen_model = genai.GenerativeModel(model)
        response = gen_model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.3,
                max_output_tokens=1000,
            ),
        )
        return response.text.strip()

    except Exception as e:
        logger.warning(f"Gemini deep analysis failed: {e}")
        return None


async def get_llm_status() -> Dict[str, Any]:
    """Get LLM service status."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    return {
        "provider": "google_gemini",
        "api_key_configured": bool(api_key),
        "tier1_model": os.environ.get("GEMINI_TIER1_MODEL", "gemini-2.5-flash"),
        "tier2_model": os.environ.get("GEMINI_TIER2_MODEL", "gemini-2.0-flash"),
        "client_initialized": _gemini_client is not None,
    }
