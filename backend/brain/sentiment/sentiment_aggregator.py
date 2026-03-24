"""
Sentiment Aggregator

Ensembles multiple sentiment sources into a single per-symbol score:
  0.50 × FinBERT   (transformer-based financial sentiment)
  0.20 × VADER     (rule-based, fast)
  0.30 × LLM       (contextual, via existing llm_service)

Features:
- Time-decay weighting: recent articles weighted more heavily
- Per-symbol daily aggregation with rolling window
- Market-wide sentiment from all articles
- Publishes SentimentEvent to the Brain event bus
"""

import asyncio
import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Optional

from brain.models.events import SentimentEvent
from brain.sentiment.finbert_analyzer import FinBERTAnalyzer, SentimentResult
from brain.sentiment.news_scraper import NewsScraper, NewsArticle
from brain.sentiment.entity_extractor import EntityExtractor

logger = logging.getLogger(__name__)


@dataclass
class SymbolSentiment:
    """Aggregated sentiment for a single symbol."""
    symbol: str
    score: float = 0.0  # [-1, +1]
    positive_prob: float = 0.0
    negative_prob: float = 0.0
    neutral_prob: float = 0.0
    article_count: int = 0
    source_breakdown: Dict[str, float] = field(default_factory=dict)
    label: str = "neutral"
    latest_headlines: List[str] = field(default_factory=list)
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "sentiment_score": round(self.score, 4),
            "label": self.label,
            "positive_prob": round(self.positive_prob, 4),
            "negative_prob": round(self.negative_prob, 4),
            "neutral_prob": round(self.neutral_prob, 4),
            "article_count": self.article_count,
            "source_breakdown": {
                k: round(v, 4) for k, v in self.source_breakdown.items()
            },
            "latest_headlines": self.latest_headlines[:5],
            "computed_at": self.computed_at.isoformat(),
        }


def _time_decay_weight(
    published_at: Optional[datetime],
    now: datetime,
    half_life_hours: float = 24.0,
) -> float:
    """
    Exponential time-decay weight.
    Articles at half_life_hours old get weight 0.5.
    """
    if published_at is None:
        return 0.5  # unknown age gets default weight

    age_hours = (now - published_at).total_seconds() / 3600.0
    if age_hours < 0:
        age_hours = 0
    return math.exp(-0.693 * age_hours / half_life_hours)  # ln(2) ≈ 0.693


class SentimentAggregator:
    """
    Central sentiment pipeline that:
    1. Scrapes news via NewsScraper
    2. Maps articles to symbols via EntityExtractor
    3. Runs FinBERT + VADER analysis
    4. Aggregates with time-decay weighting
    5. Publishes SentimentEvent to event bus
    """

    # Ensemble weights
    FINBERT_WEIGHT = 0.50
    VADER_WEIGHT = 0.20
    LLM_WEIGHT = 0.30

    def __init__(
        self,
        scraper: Optional[NewsScraper] = None,
        analyzer: Optional[FinBERTAnalyzer] = None,
        extractor: Optional[EntityExtractor] = None,
        event_bus: Optional[Any] = None,
        llm_sentiment_fn: Optional[Callable[..., Coroutine]] = None,
        half_life_hours: float = 24.0,
    ):
        self._scraper = scraper or NewsScraper()
        self._analyzer = analyzer or FinBERTAnalyzer()
        self._extractor = extractor or EntityExtractor()
        self._event_bus = event_bus
        self._llm_sentiment_fn = llm_sentiment_fn
        self._half_life_hours = half_life_hours

        # Cache: symbol -> SymbolSentiment
        self._cache: Dict[str, SymbolSentiment] = {}
        self._market_sentiment: Optional[SymbolSentiment] = None
        self._last_full_compute: Optional[datetime] = None

    def initialize(self, stock_universe: Optional[Dict[str, str]] = None):
        """
        Initialize the aggregator.

        Args:
            stock_universe: Dict of symbol -> company_name for entity extraction
        """
        if stock_universe:
            self._extractor.load_universe(stock_universe)
        self._analyzer.initialize()
        logger.info("SentimentAggregator initialized")

    async def compute_sentiment(
        self, symbol: str, force_refresh: bool = False
    ) -> SymbolSentiment:
        """
        Compute aggregated sentiment for a single symbol.

        Steps:
        1. Fetch articles (from cache or fresh scrape)
        2. Filter articles relevant to symbol
        3. Run FinBERT + VADER on article texts
        4. Optionally run LLM sentiment
        5. Aggregate with time-decay and ensemble weights
        """
        # Check cache (5-minute TTL)
        if not force_refresh and symbol in self._cache:
            cached = self._cache[symbol]
            age = (datetime.now(timezone.utc) - cached.computed_at).total_seconds()
            if age < 300:  # 5 minutes
                return cached

        # Fetch articles
        articles = await self._scraper.fetch_for_symbol(symbol)

        if not articles:
            # No articles: return neutral with low confidence
            result = SymbolSentiment(
                symbol=symbol,
                score=0.0,
                neutral_prob=1.0,
                label="neutral",
                article_count=0,
            )
            self._cache[symbol] = result
            return result

        # Extract texts for analysis
        texts = [a.raw_text for a in articles if a.raw_text]

        # Run FinBERT analysis
        finbert_results = self._analyzer.analyze(texts)

        # Run VADER analysis (separate call to get VADER-specific scores)
        from brain.sentiment.finbert_analyzer import _vader_analyze
        vader_results = _vader_analyze(texts)

        # Optionally run LLM sentiment
        llm_score = None
        if self._llm_sentiment_fn and len(texts) > 0:
            try:
                # Send top 5 headlines to LLM for contextual analysis
                top_headlines = [a.title for a in articles[:5]]
                llm_score = await self._llm_sentiment_fn(symbol, top_headlines)
            except Exception as e:
                logger.warning(f"LLM sentiment failed for {symbol}: {e}")

        # Aggregate with time-decay
        now = datetime.now(timezone.utc)
        result = self._aggregate_scores(
            symbol=symbol,
            articles=articles,
            finbert_results=finbert_results,
            vader_results=vader_results,
            llm_score=llm_score,
            now=now,
        )

        # Cache result
        self._cache[symbol] = result

        # Publish event
        await self._publish_event(result)

        return result

    async def compute_market_sentiment(self) -> SymbolSentiment:
        """
        Compute overall market sentiment from all recent articles.
        """
        articles = await self._scraper.fetch_all()

        if not articles:
            return SymbolSentiment(
                symbol="MARKET",
                score=0.0,
                neutral_prob=1.0,
                label="neutral",
                article_count=0,
            )

        texts = [a.raw_text for a in articles if a.raw_text]
        finbert_results = self._analyzer.analyze(texts)

        from brain.sentiment.finbert_analyzer import _vader_analyze
        vader_results = _vader_analyze(texts)

        now = datetime.now(timezone.utc)
        result = self._aggregate_scores(
            symbol="MARKET",
            articles=articles,
            finbert_results=finbert_results,
            vader_results=vader_results,
            llm_score=None,
            now=now,
        )

        self._market_sentiment = result
        return result

    async def compute_all_symbols(
        self, symbols: List[str], batch_size: int = 10
    ) -> Dict[str, SymbolSentiment]:
        """
        Compute sentiment for multiple symbols.
        Fetches articles once, then maps to symbols.
        """
        # Fetch all articles first
        all_articles = await self._scraper.fetch_all(force=True)

        # Map articles to symbols
        symbol_articles = self._extractor.map_articles_to_symbols(all_articles)

        results = {}
        for symbol in symbols:
            articles = symbol_articles.get(symbol, [])
            if not articles:
                results[symbol] = SymbolSentiment(
                    symbol=symbol,
                    score=0.0,
                    neutral_prob=1.0,
                    label="neutral",
                )
                continue

            texts = [a.raw_text for a in articles if hasattr(a, "raw_text")]
            finbert_results = self._analyzer.analyze(texts)

            from brain.sentiment.finbert_analyzer import _vader_analyze
            vader_results = _vader_analyze(texts)

            now = datetime.now(timezone.utc)
            result = self._aggregate_scores(
                symbol=symbol,
                articles=articles,
                finbert_results=finbert_results,
                vader_results=vader_results,
                llm_score=None,
                now=now,
            )
            results[symbol] = result
            self._cache[symbol] = result

        self._last_full_compute = datetime.now(timezone.utc)
        logger.info(f"Computed sentiment for {len(results)} symbols")
        return results

    def _aggregate_scores(
        self,
        symbol: str,
        articles: List[NewsArticle],
        finbert_results: List[SentimentResult],
        vader_results: List[SentimentResult],
        llm_score: Optional[float],
        now: datetime,
    ) -> SymbolSentiment:
        """
        Aggregate multiple sentiment sources with time-decay weighting.

        Ensemble: 0.50 × FinBERT + 0.20 × VADER + 0.30 × LLM
        If LLM unavailable, redistribute weight: 0.65 × FinBERT + 0.35 × VADER
        """
        # Time-decay weighted aggregation for FinBERT
        finbert_score = 0.0
        finbert_pos = 0.0
        finbert_neg = 0.0
        finbert_neu = 0.0
        finbert_weight_sum = 0.0

        for i, result in enumerate(finbert_results):
            pub_time = articles[i].published_at if i < len(articles) else None
            weight = _time_decay_weight(pub_time, now, self._half_life_hours)
            finbert_score += result.score * weight
            finbert_pos += result.positive_prob * weight
            finbert_neg += result.negative_prob * weight
            finbert_neu += result.neutral_prob * weight
            finbert_weight_sum += weight

        if finbert_weight_sum > 0:
            finbert_score /= finbert_weight_sum
            finbert_pos /= finbert_weight_sum
            finbert_neg /= finbert_weight_sum
            finbert_neu /= finbert_weight_sum

        # Time-decay weighted aggregation for VADER
        vader_score = 0.0
        vader_weight_sum = 0.0

        for i, result in enumerate(vader_results):
            pub_time = articles[i].published_at if i < len(articles) else None
            weight = _time_decay_weight(pub_time, now, self._half_life_hours)
            vader_score += result.score * weight
            vader_weight_sum += weight

        if vader_weight_sum > 0:
            vader_score /= vader_weight_sum

        # Determine ensemble weights
        if llm_score is not None:
            fb_w = self.FINBERT_WEIGHT
            vd_w = self.VADER_WEIGHT
            llm_w = self.LLM_WEIGHT
        else:
            # Redistribute LLM weight
            fb_w = 0.65
            vd_w = 0.35
            llm_w = 0.0

        # Final ensemble score
        final_score = fb_w * finbert_score + vd_w * vader_score
        if llm_score is not None:
            final_score += llm_w * llm_score
        final_score = max(-1.0, min(1.0, final_score))

        # Determine label
        if final_score > 0.1:
            label = "positive"
        elif final_score < -0.1:
            label = "negative"
        else:
            label = "neutral"

        # Source breakdown
        source_breakdown = {
            "finbert": finbert_score,
            "vader": vader_score,
        }
        if llm_score is not None:
            source_breakdown["llm"] = llm_score

        # Headlines
        headlines = [a.title for a in articles[:5] if a.title]

        return SymbolSentiment(
            symbol=symbol,
            score=final_score,
            positive_prob=finbert_pos,
            negative_prob=finbert_neg,
            neutral_prob=finbert_neu,
            article_count=len(articles),
            source_breakdown=source_breakdown,
            label=label,
            latest_headlines=headlines,
        )

    async def _publish_event(self, sentiment: SymbolSentiment):
        """Publish a SentimentEvent to the Brain event bus."""
        if self._event_bus is None:
            return

        event = SentimentEvent(
            symbol=sentiment.symbol,
            sentiment_score=sentiment.score,
            positive_prob=sentiment.positive_prob,
            negative_prob=sentiment.negative_prob,
            neutral_prob=sentiment.neutral_prob,
            article_count=sentiment.article_count,
            source_breakdown=sentiment.source_breakdown,
        )

        try:
            await self._event_bus.publish("sentiment.update", event)
        except Exception as e:
            logger.error(f"Failed to publish sentiment event: {e}")

    # ---- API-facing methods (called from routes) ----

    async def get_sentiment(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get sentiment for a symbol (API-friendly dict)."""
        result = await self.compute_sentiment(symbol)
        return result.to_dict()

    async def get_market_sentiment(self) -> Dict[str, Any]:
        """Get market-wide sentiment (API-friendly dict)."""
        result = await self.compute_market_sentiment()
        return result.to_dict()

    def get_sentiment_for_signal(self, symbol: str) -> Dict[str, float]:
        """
        Get sentiment data formatted for the signal generator.

        Returns dict compatible with generate_sentiment_signal().
        """
        cached = self._cache.get(symbol)
        if cached is None:
            return {}

        return {
            "sentiment_score": cached.score,
            "positive_prob": cached.positive_prob,
            "negative_prob": cached.negative_prob,
            "neutral_prob": cached.neutral_prob,
            "article_count": cached.article_count,
            "label": cached.label,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregator statistics."""
        return {
            "cached_symbols": len(self._cache),
            "scraper": self._scraper.get_stats(),
            "analyzer": self._analyzer.get_model_info(),
            "entity_extractor_universe_size": self._extractor.get_universe_size(),
            "last_full_compute": (
                self._last_full_compute.isoformat()
                if self._last_full_compute else None
            ),
        }
