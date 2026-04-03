"""
FinBERT Sentiment Analyzer — Phase 3.2

Primary: ProsusAI/finbert (general financial English)
Indian variant: kdave/FineTuned_Finbert (fine-tuned for Indian financial text)
Fallback chain: FinBERT → VADER → rule-based keywords

NLP pipeline per text:
  1. Language detection (langdetect)
  2. Hindi → English translation (deep-translator) if needed
  3. Text cleaning / truncation
  4. Sentiment inference (FinBERT or VADER)

Loads once at startup, processes articles on-demand (50-200ms each on CPU).
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy-loaded globals to avoid import cost at startup
_finbert_pipeline = None
_finbert_indian_pipeline = None
_vader_analyzer = None
_translator = None
_model_load_attempted = False
_indian_model_load_attempted = False


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
    language_detected: str = "en"
    was_translated: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


def _clean_text(text: str) -> str:
    """Clean text for sentiment analysis."""
    if not text:
        return ""
    # Remove URLs
    text = re.sub(r"http\S+|www\.\S+", "", text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Truncate to ~500 chars (FinBERT max is 512 tokens)
    if len(text) > 600:
        text = text[:600]
    return text


def _detect_language(text: str) -> str:
    """Detect language of text. Returns ISO 639-1 code."""
    try:
        from langdetect import detect
        lang = detect(text)
        return lang
    except Exception:
        return "en"  # default to English


def _translate_to_english(text: str, source_lang: str = "hi") -> str:
    """Translate non-English text to English using deep-translator."""
    global _translator
    try:
        from deep_translator import GoogleTranslator
        if _translator is None:
            _translator = GoogleTranslator(source="auto", target="en")
        # deep-translator has a 5000 char limit per call
        if len(text) > 4500:
            text = text[:4500]
        translated = _translator.translate(text)
        return translated if translated else text
    except Exception as e:
        logger.debug(f"Translation failed for {source_lang} text: {e}")
        return text  # return original on failure


def _preprocess_text(text: str) -> tuple:
    """
    Full NLP preprocessing pipeline:
    1. Clean text
    2. Detect language
    3. Translate if non-English (Hindi, etc.)
    
    Returns: (processed_text, language, was_translated)
    """
    cleaned = _clean_text(text)
    if not cleaned:
        return "", "en", False

    lang = _detect_language(cleaned)
    was_translated = False

    if lang != "en":
        translated = _translate_to_english(cleaned, source_lang=lang)
        if translated != cleaned:
            was_translated = True
            cleaned = translated

    return cleaned, lang, was_translated


def _load_finbert():
    """Lazy-load the ProsusAI/finbert pipeline."""
    global _finbert_pipeline, _model_load_attempted
    if _finbert_pipeline is not None:
        return _finbert_pipeline
    if _model_load_attempted:
        return None

    _model_load_attempted = True
    try:
        from transformers import pipeline as hf_pipeline, AutoTokenizer, AutoModelForSequenceClassification
        import torch

        logger.info("Loading ProsusAI/finbert model (this may take 30-60s on first run)...")

        # Load with explicit device for CPU
        model = AutoModelForSequenceClassification.from_pretrained(
            "ProsusAI/finbert",
            torch_dtype=torch.float32,
        )
        tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")

        _finbert_pipeline = hf_pipeline(
            "sentiment-analysis",
            model=model,
            tokenizer=tokenizer,
            top_k=3,  # return all 3 labels with probabilities
            truncation=True,
            max_length=512,
            device=-1,  # CPU
        )
        logger.info("✅ ProsusAI/finbert model loaded successfully")
        return _finbert_pipeline

    except Exception as e:
        logger.warning(f"Failed to load ProsusAI/finbert: {e}")
        return None


def _load_finbert_indian():
    """Lazy-load the kdave/FineTuned_Finbert (Indian variant) pipeline."""
    global _finbert_indian_pipeline, _indian_model_load_attempted
    if _finbert_indian_pipeline is not None:
        return _finbert_indian_pipeline
    if _indian_model_load_attempted:
        return None

    _indian_model_load_attempted = True
    try:
        from transformers import pipeline as hf_pipeline, AutoTokenizer, AutoModelForSequenceClassification
        import torch

        logger.info("Loading kdave/FineTuned_Finbert (Indian variant)...")

        model = AutoModelForSequenceClassification.from_pretrained(
            "kdave/FineTuned_Finbert",
            torch_dtype=torch.float32,
        )
        tokenizer = AutoTokenizer.from_pretrained("kdave/FineTuned_Finbert")

        _finbert_indian_pipeline = hf_pipeline(
            "sentiment-analysis",
            model=model,
            tokenizer=tokenizer,
            top_k=3,
            truncation=True,
            max_length=512,
            device=-1,
        )
        logger.info("✅ kdave/FineTuned_Finbert (Indian variant) loaded successfully")
        return _finbert_indian_pipeline

    except Exception as e:
        logger.warning(f"Failed to load Indian FinBERT variant: {e}")
        return None


def _load_vader():
    """Lazy-load VADER sentiment analyzer."""
    global _vader_analyzer
    if _vader_analyzer is not None:
        return _vader_analyzer

    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        _vader_analyzer = SentimentIntensityAnalyzer()
        logger.info("✅ VADER analyzer loaded successfully")
        return _vader_analyzer
    except ImportError:
        logger.warning("vaderSentiment not installed, VADER fallback unavailable")
        return None


def _finbert_analyze_batch(texts: List[str], use_indian: bool = False) -> List[SentimentResult]:
    """Run FinBERT on a batch of texts."""
    if use_indian:
        pipe = _load_finbert_indian()
        model_name = "finbert_indian"
    else:
        pipe = _load_finbert()
        model_name = "finbert"

    if pipe is None:
        return []

    results = []
    try:
        # Process in smaller batches to manage memory
        batch_size = 8
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            outputs = pipe(batch, batch_size=len(batch))

            for text, output in zip(batch, outputs):
                # Handle both list and dict output formats
                if isinstance(output, list):
                    probs = {item["label"].lower(): item["score"] for item in output}
                else:
                    probs = {output["label"].lower(): output["score"]}

                pos = probs.get("positive", 0.0)
                neg = probs.get("negative", 0.0)
                neu = probs.get("neutral", 0.0)

                # Composite score: [-1, +1]
                score = pos - neg
                label = max(probs, key=probs.get)

                results.append(SentimentResult(
                    text=text[:200],
                    label=label,
                    score=score,
                    positive_prob=pos,
                    negative_prob=neg,
                    neutral_prob=neu,
                    model_used=model_name,
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

        results.append(SentimentResult(
            text=text[:200],
            label=label,
            score=compound,
            positive_prob=scores["pos"],
            negative_prob=scores["neg"],
            neutral_prob=scores["neu"],
            model_used="vader",
        ))

    return results


def _rule_based_analyze(texts: List[str]) -> List[SentimentResult]:
    """
    Simple rule-based fallback when no ML models are available.
    Uses financial keyword matching with Indian market terms.
    """
    POSITIVE_KEYWORDS = {
        "surge", "rally", "gain", "profit", "growth", "bullish", "upgrade",
        "outperform", "beat", "record", "high", "strong", "boost", "rise",
        "buy", "accumulate", "dividend", "bonus", "breakout", "expansion",
        "positive", "optimistic", "recovery", "momentum", "upside",
        "tgt", "target", "overweight", "add", "subscribe",
        # Indian market specific
        "nifty high", "sensex record", "fii buying", "dii support",
        "rupee strengthens", "results beat", "order win", "capex",
    }
    NEGATIVE_KEYWORDS = {
        "crash", "fall", "loss", "decline", "bearish", "downgrade",
        "underperform", "miss", "low", "weak", "drop", "sell",
        "debt", "fraud", "scam", "bankruptcy", "default", "warning",
        "negative", "pessimistic", "recession", "correction", "downside",
        "slump", "plunge", "slash", "cut", "concern", "risk",
        "reduce", "underweight", "avoid",
        # Indian market specific
        "npa", "fii selling", "rupee weakens", "sebi penalty",
        "gst raid", "ed probe", "margin call", "circuit breaker",
    }

    results = []
    for text in texts:
        text_lower = text.lower()
        words = set(text_lower.split())
        pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
        neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)
        total = pos_count + neg_count

        if total == 0:
            score, label = 0.0, "neutral"
        else:
            score = (pos_count - neg_count) / total
            label = "positive" if score > 0.1 else "negative" if score < -0.1 else "neutral"

        pos_prob = pos_count / max(total, 1)
        neg_prob = neg_count / max(total, 1)
        neu_prob = max(0.0, 1.0 - pos_prob - neg_prob)

        results.append(SentimentResult(
            text=text[:200],
            label=label,
            score=max(-1.0, min(1.0, score)),
            positive_prob=pos_prob,
            negative_prob=neg_prob,
            neutral_prob=neu_prob,
            model_used="rule_based",
        ))

    return results


class FinBERTAnalyzer:
    """
    Financial sentiment analyzer with full NLP pipeline:
    1. Language detection + Hindi→English translation
    2. FinBERT (ProsusAI/finbert) primary analysis
    3. FinBERT Indian variant (kdave/FineTuned_Finbert) for Indian text
    4. VADER fallback
    5. Rule-based fallback
    
    Usage:
        analyzer = FinBERTAnalyzer()
        results = analyzer.analyze(["Company reports strong quarterly earnings"])
    """

    def __init__(self, use_finbert: bool = True, use_indian_variant: bool = True, use_vader: bool = True):
        self._use_finbert = use_finbert
        self._use_indian_variant = use_indian_variant
        self._use_vader = use_vader
        self._initialized = False
        self._stats = {
            "texts_analyzed": 0,
            "finbert_calls": 0,
            "vader_calls": 0,
            "translations": 0,
            "errors": 0,
        }

    def initialize(self):
        """Pre-load models (optional; they lazy-load on first use)."""
        if self._use_finbert:
            _load_finbert()
        if self._use_indian_variant:
            _load_finbert_indian()
        if self._use_vader:
            _load_vader()
        self._initialized = True

    def analyze(self, texts: List[str], use_indian_model: bool = False) -> List[SentimentResult]:
        """
        Analyze sentiment for a list of texts with full NLP pipeline.
        
        Pipeline: clean → detect language → translate if needed → FinBERT/VADER → results
        """
        if not texts:
            return []

        # Preprocess all texts through NLP pipeline
        processed_texts = []
        lang_info = []
        for text in texts:
            if not text or not text.strip():
                continue
            processed, lang, translated = _preprocess_text(text)
            if processed:
                processed_texts.append(processed)
                lang_info.append((lang, translated))
                if translated:
                    self._stats["translations"] += 1

        if not processed_texts:
            return []

        results = []

        # Try FinBERT (Indian variant or standard)
        if self._use_finbert:
            if use_indian_model and self._use_indian_variant:
                results = _finbert_analyze_batch(processed_texts, use_indian=True)
            if not results:
                results = _finbert_analyze_batch(processed_texts, use_indian=False)
            if results:
                self._stats["finbert_calls"] += 1

        # Fallback to VADER
        if not results and self._use_vader:
            results = _vader_analyze(processed_texts)
            if results:
                self._stats["vader_calls"] += 1

        # Last resort: rule-based
        if not results:
            results = _rule_based_analyze(processed_texts)

        # Enrich results with language info
        for i, result in enumerate(results):
            if i < len(lang_info):
                result.language_detected = lang_info[i][0]
                result.was_translated = lang_info[i][1]

        self._stats["texts_analyzed"] += len(results)
        return results

    def analyze_single(self, text: str) -> SentimentResult:
        """Analyze a single text."""
        results = self.analyze([text])
        if results:
            return results[0]
        return SentimentResult(
            text=text[:200], label="neutral", score=0.0,
            neutral_prob=1.0, model_used="none",
        )

    def analyze_vader_only(self, texts: List[str]) -> List[SentimentResult]:
        """Run VADER analysis only (used for ensemble component)."""
        clean_texts = [_clean_text(t) for t in texts if t]
        clean_texts = [t for t in clean_texts if t]
        if not clean_texts:
            return []
        return _vader_analyze(clean_texts)

    def get_model_info(self) -> Dict[str, Any]:
        """Return info about loaded models."""
        return {
            "finbert_loaded": _finbert_pipeline is not None,
            "finbert_indian_loaded": _finbert_indian_pipeline is not None,
            "vader_loaded": _vader_analyzer is not None,
            "use_finbert": self._use_finbert,
            "use_indian_variant": self._use_indian_variant,
            "use_vader": self._use_vader,
            "initialized": self._initialized,
            "stats": self._stats,
        }
