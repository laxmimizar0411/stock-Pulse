"""
Sentiment Analysis Pipeline — Phase 3.2

Multi-source sentiment analysis for Indian stock market:
- FinBERT: Transformer-based financial sentiment (ProsusAI/finbert + Indian variant)
- VADER: Rule-based sentiment (fast fallback)
- LLM: Gemini-based contextual sentiment (Tier 2: gemini-2.0-flash)
- News scraping: RSS feeds from Indian financial news sources (ET, Moneycontrol, LiveMint)
- Social media: Reddit (r/IndianStreetBets, r/IndiaInvestments), TradingView India
- Entity extraction: Map articles to stock tickers
- Earnings call analyzer: Management vs Q&A tone divergence
- Aggregation: Weighted ensemble (0.5×FinBERT + 0.2×VADER + 0.3×LLM) with time-decay

NLP Pipeline per text:
  Language detect → Hindi→English translation → NER → Sentiment → Event extraction
"""

from brain.sentiment.finbert_analyzer import FinBERTAnalyzer, SentimentResult
from brain.sentiment.news_scraper import NewsScraper, NewsArticle
from brain.sentiment.entity_extractor import EntityExtractor, EntityMatch
from brain.sentiment.sentiment_aggregator import SentimentAggregator, SymbolSentiment
from brain.sentiment.social_scraper import SocialScraper, SocialPost
from brain.sentiment.earnings_analyzer import EarningsCallAnalyzer, EarningsCallAnalysis
from brain.sentiment.llm_sentiment import analyze_sentiment_llm, analyze_deep_llm, get_llm_status

__all__ = [
    "FinBERTAnalyzer", "SentimentResult",
    "NewsScraper", "NewsArticle",
    "EntityExtractor", "EntityMatch",
    "SentimentAggregator", "SymbolSentiment",
    "SocialScraper", "SocialPost",
    "EarningsCallAnalyzer", "EarningsCallAnalysis",
    "analyze_sentiment_llm", "analyze_deep_llm", "get_llm_status",
]
