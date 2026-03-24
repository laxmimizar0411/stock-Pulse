"""
News Scraper for Indian Financial Markets

Fetches articles from RSS feeds of major Indian financial news sources:
- Moneycontrol
- Economic Times Markets
- LiveMint Markets
- Business Standard Markets

Each article: {title, summary, url, source, published_at, symbol_mentions}
"""

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class NewsArticle:
    """A scraped news article."""
    article_id: str = ""
    title: str = ""
    summary: str = ""
    url: str = ""
    source: str = ""
    published_at: Optional[datetime] = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    symbols: List[str] = field(default_factory=list)
    raw_text: str = ""  # title + summary combined for analysis
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.article_id and self.url:
            self.article_id = hashlib.md5(self.url.encode()).hexdigest()
        if not self.raw_text:
            self.raw_text = f"{self.title}. {self.summary}".strip()


# Indian financial news RSS feeds
RSS_FEEDS = {
    "moneycontrol": [
        "https://www.moneycontrol.com/rss/marketreports.xml",
        "https://www.moneycontrol.com/rss/stocksinnews.xml",
        "https://www.moneycontrol.com/rss/results.xml",
    ],
    "economic_times": [
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    ],
    "livemint": [
        "https://www.livemint.com/rss/markets",
        "https://www.livemint.com/rss/companies",
    ],
    "business_standard": [
        "https://www.business-standard.com/rss/markets-106.rss",
        "https://www.business-standard.com/rss/companies-101.rss",
    ],
}


def _parse_feed(feed_url: str, source: str) -> List[NewsArticle]:
    """Parse a single RSS feed and return articles."""
    try:
        import feedparser

        feed = feedparser.parse(feed_url)
        articles = []

        for entry in feed.entries[:20]:  # limit per feed
            title = entry.get("title", "").strip()
            if not title:
                continue

            summary = entry.get("summary", "") or entry.get("description", "")
            # Strip HTML tags from summary
            summary = re.sub(r"<[^>]+>", " ", summary).strip()
            summary = re.sub(r"\s+", " ", summary)[:500]

            # Parse publication date
            published = None
            for date_field in ("published_parsed", "updated_parsed"):
                parsed = entry.get(date_field)
                if parsed:
                    try:
                        from time import mktime
                        published = datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
                    except Exception:
                        pass
                    break

            url = entry.get("link", "")
            article = NewsArticle(
                title=title,
                summary=summary,
                url=url,
                source=source,
                published_at=published,
            )
            articles.append(article)

        return articles

    except ImportError:
        logger.warning("feedparser not installed, RSS scraping unavailable")
        return []
    except Exception as e:
        logger.error(f"Failed to parse feed {feed_url}: {e}")
        return []


class NewsScraper:
    """
    Async news scraper for Indian financial news.

    Fetches articles from configured RSS feeds with deduplication
    and rate limiting.
    """

    def __init__(
        self,
        feeds: Optional[Dict[str, List[str]]] = None,
        max_age_hours: int = 48,
        max_articles_per_source: int = 30,
    ):
        self._feeds = feeds or RSS_FEEDS
        self._max_age = timedelta(hours=max_age_hours)
        self._max_per_source = max_articles_per_source
        self._seen_ids: Set[str] = set()
        self._article_cache: List[NewsArticle] = []
        self._last_fetch: Optional[datetime] = None
        self._min_fetch_interval = timedelta(minutes=5)

    async def fetch_all(self, force: bool = False) -> List[NewsArticle]:
        """
        Fetch articles from all configured RSS feeds.

        Returns deduplicated, time-filtered articles sorted by recency.
        Uses asyncio to parallelize feed parsing across sources.
        """
        now = datetime.now(timezone.utc)

        # Rate limit fetches
        if not force and self._last_fetch:
            elapsed = now - self._last_fetch
            if elapsed < self._min_fetch_interval:
                logger.debug("Skipping fetch, too soon since last fetch")
                return self._article_cache

        all_articles = []
        loop = asyncio.get_event_loop()

        # Parse feeds in parallel using thread pool (feedparser is sync)
        tasks = []
        for source, urls in self._feeds.items():
            for url in urls:
                tasks.append(loop.run_in_executor(None, _parse_feed, url, source))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Feed fetch error: {result}")
                continue
            all_articles.extend(result)

        # Deduplicate by article_id
        unique = []
        for article in all_articles:
            if article.article_id not in self._seen_ids:
                self._seen_ids.add(article.article_id)
                unique.append(article)

        # Filter by age
        cutoff = now - self._max_age
        fresh = [
            a for a in unique
            if a.published_at is None or a.published_at >= cutoff
        ]

        # Sort by published date (newest first)
        fresh.sort(
            key=lambda a: a.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        # Limit per source
        source_counts: Dict[str, int] = {}
        limited = []
        for article in fresh:
            count = source_counts.get(article.source, 0)
            if count < self._max_per_source:
                limited.append(article)
                source_counts[article.source] = count + 1

        self._article_cache = limited
        self._last_fetch = now

        logger.info(
            f"Fetched {len(limited)} articles from {len(self._feeds)} sources "
            f"({len(all_articles)} total, {len(unique)} unique)"
        )

        return limited

    async def fetch_for_symbol(self, symbol: str) -> List[NewsArticle]:
        """
        Fetch articles relevant to a specific symbol.

        First fetches all articles, then filters by symbol mention
        in title or summary.
        """
        articles = await self.fetch_all()

        # Simple keyword matching — entity_extractor does the real mapping
        symbol_upper = symbol.upper().replace(".NS", "").replace(".BSE", "")
        relevant = []

        for article in articles:
            text = article.raw_text.upper()
            if symbol_upper in text:
                if symbol_upper not in article.symbols:
                    article.symbols.append(symbol_upper)
                relevant.append(article)

        return relevant

    def get_cached_articles(self) -> List[NewsArticle]:
        """Return the cached article list without fetching."""
        return self._article_cache

    def clear_cache(self):
        """Clear the article cache and seen IDs."""
        self._article_cache = []
        self._seen_ids = set()
        self._last_fetch = None

    def get_stats(self) -> Dict[str, Any]:
        """Return scraper statistics."""
        source_counts = {}
        for article in self._article_cache:
            source_counts[article.source] = source_counts.get(article.source, 0) + 1

        return {
            "total_cached": len(self._article_cache),
            "sources": source_counts,
            "seen_ids": len(self._seen_ids),
            "last_fetch": self._last_fetch.isoformat() if self._last_fetch else None,
            "configured_feeds": {
                source: len(urls) for source, urls in self._feeds.items()
            },
        }
