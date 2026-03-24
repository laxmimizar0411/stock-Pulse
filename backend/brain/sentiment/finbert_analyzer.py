"""
FinBERT Sentiment Analyzer

Uses ProsusAI/finbert (or fallback to VADER) for financial sentiment
classification of news headlines and article text.

Outputs per-text: sentiment_score [-1, +1], positive/negative/neutral
probabilities, and a label.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy-loaded globals to avoid import cost at startup
_finbert_pipeline = None
_vader_analyzer = None


@dataclass
class SentimentResult:
    """Result from a single text sentiment analysis."""
    text: str
    label: str  # "positive", "negative", "neutral"
    score: float  # [-1, +1]
    positive_prob: float = 0.0
    negative_prob: float = 0.0
    neutral_prob: float = 0.0
    model_used: str = "finbert"
    metadata: Dict[str, Any] = field(default_factory=dict)


def _load_finbert():
    """Lazy-load the FinBERT pipeline."""
    global _finbert_pipeline
    if _finbert_pipeline is not None:
        return _finbert_pipeline

    try:
        from transformers import pipeline as hf_pipeline

        _finbert_pipeline = hf_pipeline(
            "sentiment-analysis",
            model="ProsusAI/finbert",
            tokenizer="ProsusAI/finbert",
            top_k=3,  # return all 3 labels with probabilities
            truncation=True,
            max_length=512,
        )
        logger.info("FinBERT model loaded successfully")
        return _finbert_pipeline
    except Exception as e:
        logger.warning(f"Failed to load FinBERT, will use VADER fallback: {e}")
        return None


def _load_vader():
    """Lazy-load VADER sentiment analyzer."""
    global _vader_analyzer
    if _vader_analyzer is not None:
        return _vader_analyzer

    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        _vader_analyzer = SentimentIntensityAnalyzer()
        logger.info("VADER analyzer loaded successfully")
        return _vader_analyzer
    except ImportError:
        logger.warning("vaderSentiment not installed, VADER fallback unavailable")
        return None


def _finbert_analyze(texts: List[str]) -> List[SentimentResult]:
    """Run FinBERT on a batch of texts."""
    pipe = _load_finbert()
    if pipe is None:
        return []

    results = []
    try:
        # FinBERT pipeline handles batching internally
        outputs = pipe(texts, batch_size=16)

        for text, output in zip(texts, outputs):
            probs = {item["label"]: item["score"] for item in output}
            pos = probs.get("positive", 0.0)
            neg = probs.get("negative", 0.0)
            neu = probs.get("neutral", 0.0)

            # Composite score: [-1, +1]
            score = pos - neg

            # Determine label from highest probability
            label = max(probs, key=probs.get)

            results.append(SentimentResult(
                text=text[:200],
                label=label,
                score=score,
                positive_prob=pos,
                negative_prob=neg,
                neutral_prob=neu,
                model_used="finbert",
            ))

    except Exception as e:
        logger.error(f"FinBERT inference failed: {e}")
        return []

    return results


def _vader_analyze(texts: List[str]) -> List[SentimentResult]:
    """Run VADER on a batch of texts (fast fallback)."""
    analyzer = _load_vader()
    if analyzer is None:
        return _rule_based_analyze(texts)

    results = []
    for text in texts:
        scores = analyzer.polarity_scores(text)
        compound = scores["compound"]  # [-1, +1]

        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"

        # Map VADER scores to probabilities
        pos = scores["pos"]
        neg = scores["neg"]
        neu = scores["neu"]

        results.append(SentimentResult(
            text=text[:200],
            label=label,
            score=compound,
            positive_prob=pos,
            negative_prob=neg,
            neutral_prob=neu,
            model_used="vader",
        ))

    return results


def _rule_based_analyze(texts: List[str]) -> List[SentimentResult]:
    """
    Simple rule-based fallback when no ML models are available.
    Uses financial keyword matching.
    """
    POSITIVE_KEYWORDS = {
        "surge", "rally", "gain", "profit", "growth", "bullish", "upgrade",
        "outperform", "beat", "record", "high", "strong", "boost", "rise",
        "buy", "accumulate", "dividend", "bonus", "breakout", "expansion",
        "positive", "optimistic", "recovery", "momentum", "upside",
    }
    NEGATIVE_KEYWORDS = {
        "crash", "fall", "loss", "decline", "bearish", "downgrade",
        "underperform", "miss", "low", "weak", "drop", "sell",
        "debt", "fraud", "scam", "bankruptcy", "default", "warning",
        "negative", "pessimistic", "recession", "correction", "downside",
        "slump", "plunge", "slash", "cut", "concern", "risk",
    }

    results = []
    for text in texts:
        words = set(text.lower().split())
        pos_count = len(words & POSITIVE_KEYWORDS)
        neg_count = len(words & NEGATIVE_KEYWORDS)
        total = pos_count + neg_count

        if total == 0:
            score = 0.0
            label = "neutral"
        else:
            score = (pos_count - neg_count) / total
            label = "positive" if score > 0.1 else "negative" if score < -0.1 else "neutral"

        # Approximate probabilities
        if total > 0:
            pos_prob = pos_count / total
            neg_prob = neg_count / total
        else:
            pos_prob = 0.0
            neg_prob = 0.0
        neu_prob = 1.0 - pos_prob - neg_prob

        results.append(SentimentResult(
            text=text[:200],
            label=label,
            score=max(-1.0, min(1.0, score)),
            positive_prob=pos_prob,
            negative_prob=neg_prob,
            neutral_prob=max(0.0, neu_prob),
            model_used="rule_based",
        ))

    return results


class FinBERTAnalyzer:
    """
    Financial sentiment analyzer using FinBERT with VADER fallback.

    Usage:
        analyzer = FinBERTAnalyzer()
        results = analyzer.analyze(["Company reports strong quarterly earnings"])
    """

    def __init__(self, use_finbert: bool = True, use_vader: bool = True):
        self._use_finbert = use_finbert
        self._use_vader = use_vader
        self._initialized = False

    def initialize(self):
        """Pre-load models (optional; they lazy-load on first use)."""
        if self._use_finbert:
            _load_finbert()
        if self._use_vader:
            _load_vader()
        self._initialized = True

    def analyze(self, texts: List[str]) -> List[SentimentResult]:
        """
        Analyze sentiment for a list of texts.

        Tries FinBERT first, falls back to VADER, then rule-based.
        """
        if not texts:
            return []

        # Clean texts
        clean_texts = [t.strip() for t in texts if t and t.strip()]
        if not clean_texts:
            return []

        # Try FinBERT
        if self._use_finbert:
            results = _finbert_analyze(clean_texts)
            if results:
                return results

        # Fallback to VADER
        if self._use_vader:
            results = _vader_analyze(clean_texts)
            if results:
                return results

        # Last resort: rule-based
        return _rule_based_analyze(clean_texts)

    def analyze_single(self, text: str) -> SentimentResult:
        """Analyze a single text."""
        results = self.analyze([text])
        if results:
            return results[0]
        return SentimentResult(
            text=text[:200],
            label="neutral",
            score=0.0,
            neutral_prob=1.0,
            model_used="none",
        )

    def get_model_info(self) -> Dict[str, Any]:
        """Return info about loaded models."""
        return {
            "finbert_loaded": _finbert_pipeline is not None,
            "vader_loaded": _vader_analyzer is not None,
            "use_finbert": self._use_finbert,
            "use_vader": self._use_vader,
        }
