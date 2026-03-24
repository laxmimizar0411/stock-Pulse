"""
Sentiment Analysis Pipeline (Phase 4)

Multi-source sentiment analysis for Indian stock market:
- FinBERT: Transformer-based financial sentiment (primary)
- VADER: Rule-based sentiment (fast fallback)
- LLM: GPT-4o contextual sentiment via existing llm_service
- News scraping: RSS feeds from Indian financial news sources
- Entity extraction: Map articles to stock tickers
- Aggregation: Weighted ensemble with time-decay
"""
