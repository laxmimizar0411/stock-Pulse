"""
Tests for Stock Pulse Brain Sentiment Pipeline (Phase 4).

Tests FinBERT analyzer, news scraper, entity extractor,
sentiment aggregator, and signal generator integration.
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest


# ==================== FinBERT Analyzer Tests ====================

class TestFinBERTAnalyzer:
    def test_rule_based_fallback_positive(self):
        """Rule-based should detect positive financial keywords."""
        from brain.sentiment.finbert_analyzer import _rule_based_analyze

        results = _rule_based_analyze(["Company reports strong profit growth and rally"])
        assert len(results) == 1
        assert results[0].label == "positive"
        assert results[0].score > 0
        assert results[0].model_used == "rule_based"

    def test_rule_based_fallback_negative(self):
        """Rule-based should detect negative financial keywords."""
        from brain.sentiment.finbert_analyzer import _rule_based_analyze

        results = _rule_based_analyze(["Stock crash amid fraud concerns and bankruptcy risk"])
        assert len(results) == 1
        assert results[0].label == "negative"
        assert results[0].score < 0

    def test_rule_based_fallback_neutral(self):
        """Rule-based should return neutral for non-financial text."""
        from brain.sentiment.finbert_analyzer import _rule_based_analyze

        results = _rule_based_analyze(["The weather is nice today"])
        assert len(results) == 1
        assert results[0].label == "neutral"
        assert results[0].score == 0.0

    def test_rule_based_empty_input(self):
        """Empty input should return empty list."""
        from brain.sentiment.finbert_analyzer import _rule_based_analyze

        results = _rule_based_analyze([])
        assert results == []

    def test_rule_based_score_bounds(self):
        """Scores should be bounded to [-1, +1]."""
        from brain.sentiment.finbert_analyzer import _rule_based_analyze

        results = _rule_based_analyze(["surge rally gain profit growth bullish upgrade outperform beat record"])
        assert len(results) == 1
        assert -1.0 <= results[0].score <= 1.0

    def test_sentiment_result_dataclass(self):
        """SentimentResult should store all fields correctly."""
        from brain.sentiment.finbert_analyzer import SentimentResult

        result = SentimentResult(
            text="test text",
            label="positive",
            score=0.85,
            positive_prob=0.9,
            negative_prob=0.05,
            neutral_prob=0.05,
            model_used="finbert",
        )
        assert result.text == "test text"
        assert result.label == "positive"
        assert result.score == 0.85

    def test_analyzer_class_empty_input(self):
        """Analyzer should handle empty input gracefully."""
        from brain.sentiment.finbert_analyzer import FinBERTAnalyzer

        analyzer = FinBERTAnalyzer(use_finbert=False, use_vader=False)
        results = analyzer.analyze([])
        assert results == []

    def test_analyzer_single_text(self):
        """analyze_single should return a SentimentResult."""
        from brain.sentiment.finbert_analyzer import FinBERTAnalyzer

        analyzer = FinBERTAnalyzer(use_finbert=False, use_vader=False)
        result = analyzer.analyze_single("Company reports strong profit growth")
        assert result.label in ("positive", "negative", "neutral")
        assert -1.0 <= result.score <= 1.0

    def test_analyzer_model_info(self):
        """get_model_info should return model status dict."""
        from brain.sentiment.finbert_analyzer import FinBERTAnalyzer

        analyzer = FinBERTAnalyzer(use_finbert=True, use_vader=True)
        info = analyzer.get_model_info()
        assert "finbert_loaded" in info
        assert "vader_loaded" in info
        assert info["use_finbert"] is True

    def test_analyzer_batch(self):
        """Analyzer should process multiple texts."""
        from brain.sentiment.finbert_analyzer import FinBERTAnalyzer

        analyzer = FinBERTAnalyzer(use_finbert=False, use_vader=False)
        results = analyzer.analyze([
            "Stock surges on strong earnings",
            "Market crash amid global concerns",
            "Company announces regular dividend",
        ])
        assert len(results) == 3


# ==================== News Scraper Tests ====================

class TestNewsScraper:
    def test_news_article_dataclass(self):
        """NewsArticle should auto-generate ID from URL."""
        from brain.sentiment.news_scraper import NewsArticle

        article = NewsArticle(
            title="Test headline",
            url="https://example.com/article/123",
            source="test",
        )
        assert article.article_id != ""
        assert article.raw_text == "Test headline."

    def test_news_article_raw_text(self):
        """raw_text should combine title and summary."""
        from brain.sentiment.news_scraper import NewsArticle

        article = NewsArticle(
            title="Headline",
            summary="Some details here",
            url="https://example.com/1",
            source="test",
        )
        assert article.raw_text == "Headline. Some details here"

    def test_scraper_defaults(self):
        """Scraper should initialize with default feeds."""
        from brain.sentiment.news_scraper import NewsScraper, RSS_FEEDS

        scraper = NewsScraper()
        stats = scraper.get_stats()
        assert stats["total_cached"] == 0
        assert len(stats["configured_feeds"]) == len(RSS_FEEDS)

    def test_scraper_custom_feeds(self):
        """Scraper should accept custom feed config."""
        from brain.sentiment.news_scraper import NewsScraper

        scraper = NewsScraper(feeds={"custom": ["https://example.com/rss"]})
        stats = scraper.get_stats()
        assert "custom" in stats["configured_feeds"]

    def test_scraper_cache_operations(self):
        """clear_cache should reset state."""
        from brain.sentiment.news_scraper import NewsScraper

        scraper = NewsScraper()
        scraper._seen_ids.add("test-id")
        scraper.clear_cache()
        assert len(scraper._seen_ids) == 0
        assert scraper._last_fetch is None

    @pytest.mark.asyncio
    async def test_scraper_fetch_for_symbol(self):
        """fetch_for_symbol should filter by symbol mention."""
        from brain.sentiment.news_scraper import NewsScraper, NewsArticle

        scraper = NewsScraper(feeds={})  # no real feeds
        # Inject some cached articles
        scraper._article_cache = [
            NewsArticle(title="RELIANCE posts strong Q3 results", url="u1", source="t"),
            NewsArticle(title="Market overview for the week", url="u2", source="t"),
            NewsArticle(title="TCS wins major deal", url="u3", source="t"),
        ]
        scraper._last_fetch = datetime.now(timezone.utc)

        results = await scraper.fetch_for_symbol("RELIANCE")
        assert len(results) == 1
        assert "RELIANCE" in results[0].symbols


# ==================== Entity Extractor Tests ====================

class TestEntityExtractor:
    def test_default_aliases(self):
        """Default aliases should include major Indian stocks."""
        from brain.sentiment.entity_extractor import EntityExtractor

        extractor = EntityExtractor()
        matches = extractor.extract("Reliance Industries reports Q3 results")
        assert any(m.symbol == "RELIANCE" for m in matches)

    def test_alias_matching(self):
        """Should match common abbreviations."""
        from brain.sentiment.entity_extractor import EntityExtractor

        extractor = EntityExtractor()
        matches = extractor.extract("TCS wins major deal from global client")
        assert any(m.symbol == "TCS" for m in matches)

    def test_multiple_entities(self):
        """Should extract multiple entities from one text."""
        from brain.sentiment.entity_extractor import EntityExtractor

        extractor = EntityExtractor()
        matches = extractor.extract("Infosys and TCS lead IT sector rally today")
        symbols = {m.symbol for m in matches}
        assert "INFY" in symbols
        assert "TCS" in symbols

    def test_universe_loading(self):
        """Should load custom universe for matching."""
        from brain.sentiment.entity_extractor import EntityExtractor

        extractor = EntityExtractor()
        extractor.load_universe({
            "TESTSTOCK": "Test Stock Ltd",
            "ANOTHER": "Another Company Pvt Ltd",
        })
        assert extractor.get_universe_size() == 2

    def test_symbol_match_in_universe(self):
        """Should match symbols from loaded universe."""
        from brain.sentiment.entity_extractor import EntityExtractor

        extractor = EntityExtractor()
        extractor.load_universe({"HDFCBANK": "HDFC Bank Ltd"})
        matches = extractor.extract("HDFCBANK Q3 results beat estimates")
        assert any(m.symbol == "HDFCBANK" and m.match_type == "symbol" for m in matches)

    def test_sector_extraction(self):
        """Should identify sector mentions."""
        from brain.sentiment.entity_extractor import EntityExtractor

        extractor = EntityExtractor()
        sectors = extractor.extract_sectors("Banking sector sees credit growth amid rising NPA concerns")
        assert "banking" in sectors

    def test_no_match(self):
        """Should return empty list for unrelated text."""
        from brain.sentiment.entity_extractor import EntityExtractor

        extractor = EntityExtractor()
        extractor.load_universe({"RELIANCE": "Reliance Industries"})
        matches = extractor.extract("The weather is sunny today")
        # Only alias matches possible, not universe matches
        assert all(m.match_type != "symbol" for m in matches)

    def test_map_articles_to_symbols(self):
        """Should map articles to symbols via entity extraction."""
        from brain.sentiment.entity_extractor import EntityExtractor
        from brain.sentiment.news_scraper import NewsArticle

        extractor = EntityExtractor()
        articles = [
            NewsArticle(title="Reliance Q3 profit up 20%", url="u1", source="t"),
            NewsArticle(title="TCS wins mega deal", url="u2", source="t"),
            NewsArticle(title="Market rally continues", url="u3", source="t"),
        ]

        result = extractor.map_articles_to_symbols(articles)
        assert "RELIANCE" in result
        assert "TCS" in result
        assert len(result.get("RELIANCE", [])) == 1

    def test_entity_match_confidence(self):
        """Symbol matches should have higher confidence than aliases."""
        from brain.sentiment.entity_extractor import EntityExtractor

        extractor = EntityExtractor()
        extractor.load_universe({"RELIANCE": "Reliance Industries Ltd"})
        matches = extractor.extract("RELIANCE stock is reliance on strong fundamentals")
        # Should have at least one match
        assert len(matches) >= 1
        # Symbol match should be highest confidence
        best = matches[0]
        assert best.confidence >= 0.85


# ==================== Sentiment Aggregator Tests ====================

class TestSentimentAggregator:
    def test_time_decay_weight(self):
        """Time decay should halve weight at half-life."""
        from brain.sentiment.sentiment_aggregator import _time_decay_weight

        now = datetime.now(timezone.utc)
        # At time 0: weight = 1.0
        w0 = _time_decay_weight(now, now, half_life_hours=24.0)
        assert abs(w0 - 1.0) < 0.01

        # At half-life: weight ≈ 0.5
        half_life_ago = now - timedelta(hours=24)
        w_half = _time_decay_weight(half_life_ago, now, half_life_hours=24.0)
        assert abs(w_half - 0.5) < 0.05

        # Very old: weight near 0
        old = now - timedelta(hours=168)
        w_old = _time_decay_weight(old, now, half_life_hours=24.0)
        assert w_old < 0.01

    def test_time_decay_none_date(self):
        """None published_at should return default weight."""
        from brain.sentiment.sentiment_aggregator import _time_decay_weight

        now = datetime.now(timezone.utc)
        w = _time_decay_weight(None, now)
        assert w == 0.5

    def test_symbol_sentiment_to_dict(self):
        """SymbolSentiment.to_dict() should produce API-friendly output."""
        from brain.sentiment.sentiment_aggregator import SymbolSentiment

        s = SymbolSentiment(
            symbol="RELIANCE",
            score=0.65,
            positive_prob=0.75,
            negative_prob=0.10,
            neutral_prob=0.15,
            article_count=8,
            label="positive",
            source_breakdown={"finbert": 0.7, "vader": 0.5},
            latest_headlines=["Q3 profit surges"],
        )
        d = s.to_dict()
        assert d["symbol"] == "RELIANCE"
        assert d["sentiment_score"] == 0.65
        assert d["label"] == "positive"
        assert d["article_count"] == 8
        assert "finbert" in d["source_breakdown"]
        assert "computed_at" in d

    @pytest.mark.asyncio
    async def test_aggregator_no_articles(self):
        """Should return neutral sentiment when no articles found."""
        from brain.sentiment.sentiment_aggregator import SentimentAggregator

        # Use scraper that returns no articles
        mock_scraper = MagicMock()
        mock_scraper.fetch_for_symbol = AsyncMock(return_value=[])
        mock_scraper.get_stats = MagicMock(return_value={})

        agg = SentimentAggregator(scraper=mock_scraper)
        result = await agg.compute_sentiment("RELIANCE")

        assert result.symbol == "RELIANCE"
        assert result.score == 0.0
        assert result.label == "neutral"
        assert result.article_count == 0

    @pytest.mark.asyncio
    async def test_aggregator_with_articles(self):
        """Should aggregate sentiment from articles."""
        from brain.sentiment.sentiment_aggregator import SentimentAggregator
        from brain.sentiment.news_scraper import NewsArticle
        from brain.sentiment.finbert_analyzer import FinBERTAnalyzer

        now = datetime.now(timezone.utc)
        articles = [
            NewsArticle(
                title="Reliance reports record quarterly profit surge",
                url="u1", source="test",
                published_at=now - timedelta(hours=2),
            ),
            NewsArticle(
                title="Reliance strong growth and expansion plans",
                url="u2", source="test",
                published_at=now - timedelta(hours=5),
            ),
        ]

        mock_scraper = MagicMock()
        mock_scraper.fetch_for_symbol = AsyncMock(return_value=articles)
        mock_scraper.get_stats = MagicMock(return_value={})

        # Use rule-based only (no model deps)
        analyzer = FinBERTAnalyzer(use_finbert=False, use_vader=False)

        agg = SentimentAggregator(scraper=mock_scraper, analyzer=analyzer)
        result = await agg.compute_sentiment("RELIANCE")

        assert result.symbol == "RELIANCE"
        assert result.article_count == 2
        assert result.score > 0  # positive articles
        assert result.label == "positive"

    @pytest.mark.asyncio
    async def test_aggregator_market_sentiment(self):
        """Should compute market-wide sentiment."""
        from brain.sentiment.sentiment_aggregator import SentimentAggregator
        from brain.sentiment.news_scraper import NewsArticle
        from brain.sentiment.finbert_analyzer import FinBERTAnalyzer

        articles = [
            NewsArticle(title="Markets rally on FII inflows", url="u1", source="t"),
            NewsArticle(title="Nifty hits record high", url="u2", source="t"),
        ]

        mock_scraper = MagicMock()
        mock_scraper.fetch_all = AsyncMock(return_value=articles)
        mock_scraper.get_stats = MagicMock(return_value={})

        analyzer = FinBERTAnalyzer(use_finbert=False, use_vader=False)
        agg = SentimentAggregator(scraper=mock_scraper, analyzer=analyzer)
        result = await agg.compute_market_sentiment()

        assert result.symbol == "MARKET"
        assert result.article_count == 2

    def test_get_sentiment_for_signal(self):
        """get_sentiment_for_signal should return signal-compatible dict."""
        from brain.sentiment.sentiment_aggregator import (
            SentimentAggregator,
            SymbolSentiment,
        )

        agg = SentimentAggregator()
        agg._cache["RELIANCE"] = SymbolSentiment(
            symbol="RELIANCE",
            score=0.5,
            positive_prob=0.7,
            negative_prob=0.15,
            neutral_prob=0.15,
            article_count=6,
            label="positive",
        )

        data = agg.get_sentiment_for_signal("RELIANCE")
        assert data["sentiment_score"] == 0.5
        assert data["article_count"] == 6
        assert data["label"] == "positive"

    def test_get_sentiment_for_signal_missing(self):
        """Should return empty dict for uncached symbol."""
        from brain.sentiment.sentiment_aggregator import SentimentAggregator

        agg = SentimentAggregator()
        data = agg.get_sentiment_for_signal("UNKNOWN")
        assert data == {}

    @pytest.mark.asyncio
    async def test_aggregator_caching(self):
        """Should use cached result within TTL."""
        from brain.sentiment.sentiment_aggregator import SentimentAggregator
        from brain.sentiment.news_scraper import NewsArticle
        from brain.sentiment.finbert_analyzer import FinBERTAnalyzer

        articles = [
            NewsArticle(title="Positive earnings report", url="u1", source="t"),
        ]

        mock_scraper = MagicMock()
        mock_scraper.fetch_for_symbol = AsyncMock(return_value=articles)
        mock_scraper.get_stats = MagicMock(return_value={})

        analyzer = FinBERTAnalyzer(use_finbert=False, use_vader=False)
        agg = SentimentAggregator(scraper=mock_scraper, analyzer=analyzer)

        # First call
        r1 = await agg.compute_sentiment("TEST")
        # Second call (should use cache)
        r2 = await agg.compute_sentiment("TEST")

        assert r1.computed_at == r2.computed_at  # same cached result
        # Scraper called only once
        assert mock_scraper.fetch_for_symbol.call_count == 1

    def test_aggregator_stats(self):
        """get_stats should return pipeline statistics."""
        from brain.sentiment.sentiment_aggregator import SentimentAggregator

        mock_scraper = MagicMock()
        mock_scraper.get_stats = MagicMock(return_value={"total_cached": 0})

        analyzer = MagicMock()
        analyzer.get_model_info = MagicMock(return_value={"finbert_loaded": False})

        extractor = MagicMock()
        extractor.get_universe_size = MagicMock(return_value=50)

        agg = SentimentAggregator(
            scraper=mock_scraper, analyzer=analyzer, extractor=extractor
        )
        stats = agg.get_stats()
        assert "cached_symbols" in stats
        assert "scraper" in stats
        assert "analyzer" in stats


# ==================== Signal Generator Integration Tests ====================

class TestSentimentSignalIntegration:
    def test_sentiment_signal_with_data(self):
        """Sentiment signal should produce valid score and confidence from aggregator data."""
        from brain.signals.signal_generator import generate_sentiment_signal

        signal = generate_sentiment_signal({
            "sentiment_score": 0.6,
            "article_count": 8,
            "positive_prob": 0.75,
            "negative_prob": 0.10,
            "neutral_prob": 0.15,
            "label": "positive",
        })

        assert signal.source == "sentiment"
        assert signal.score > 0
        assert signal.confidence > 0
        assert -1.0 <= signal.score <= 1.0
        assert 0.0 <= signal.confidence <= 1.0

    def test_sentiment_signal_no_data(self):
        """No data should return zero confidence."""
        from brain.signals.signal_generator import generate_sentiment_signal

        signal = generate_sentiment_signal(None)
        assert signal.source == "sentiment"
        assert signal.score == 0.0
        assert signal.confidence == 0.0

    def test_sentiment_signal_empty_dict(self):
        """Empty dict should return zero confidence."""
        from brain.signals.signal_generator import generate_sentiment_signal

        signal = generate_sentiment_signal({})
        assert signal.confidence == 0.0

    def test_sentiment_signal_zero_articles(self):
        """Zero articles should return zero confidence."""
        from brain.signals.signal_generator import generate_sentiment_signal

        signal = generate_sentiment_signal({
            "sentiment_score": 0.5,
            "article_count": 0,
        })
        assert signal.confidence == 0.0

    def test_sentiment_signal_many_articles(self):
        """More articles should increase confidence."""
        from brain.signals.signal_generator import generate_sentiment_signal

        sig_few = generate_sentiment_signal({
            "sentiment_score": 0.5,
            "article_count": 2,
            "positive_prob": 0.7,
            "negative_prob": 0.15,
        })
        sig_many = generate_sentiment_signal({
            "sentiment_score": 0.5,
            "article_count": 15,
            "positive_prob": 0.7,
            "negative_prob": 0.15,
        })

        assert sig_many.confidence > sig_few.confidence

    def test_sentiment_signal_negative(self):
        """Negative sentiment should produce negative score."""
        from brain.signals.signal_generator import generate_sentiment_signal

        signal = generate_sentiment_signal({
            "sentiment_score": -0.7,
            "article_count": 5,
            "positive_prob": 0.1,
            "negative_prob": 0.8,
            "neutral_prob": 0.1,
        })

        assert signal.score < 0
        assert signal.confidence > 0


# ==================== Config Tests ====================

class TestSentimentConfig:
    def test_sentiment_config_defaults(self):
        """SentimentConfig should have sensible defaults."""
        from brain.config import SentimentConfig

        cfg = SentimentConfig()
        assert cfg.half_life_hours == 24.0
        assert cfg.finbert_weight == 0.50
        assert cfg.vader_weight == 0.20
        assert cfg.llm_weight == 0.30
        assert abs(cfg.finbert_weight + cfg.vader_weight + cfg.llm_weight - 1.0) < 0.001

    def test_sentiment_enabled_in_brain_config(self):
        """Sentiment module should be enabled by default now."""
        from brain.config import BrainConfig

        config = BrainConfig()
        assert config.modules.sentiment_enabled is True
        assert hasattr(config, "sentiment")
        assert config.sentiment.half_life_hours == 24.0

    def test_sentiment_config_env_override(self):
        """SentimentConfig values should be overridable via env."""
        import os
        os.environ["BRAIN_SENTIMENT_HALF_LIFE_HOURS"] = "12.0"
        os.environ["BRAIN_SENTIMENT_FINBERT_ENABLED"] = "false"

        try:
            from brain.config import BrainConfig, reset_brain_config
            reset_brain_config()
            config = BrainConfig.from_env()
            assert config.sentiment.half_life_hours == 12.0
            assert config.sentiment.finbert_enabled is False
        finally:
            os.environ.pop("BRAIN_SENTIMENT_HALF_LIFE_HOURS", None)
            os.environ.pop("BRAIN_SENTIMENT_FINBERT_ENABLED", None)
            reset_brain_config()
