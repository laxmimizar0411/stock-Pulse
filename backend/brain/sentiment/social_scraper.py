"""
Social Media Sentiment Scraper — Phase 3.2

Scrapes social sentiment from:
1. Reddit r/IndianStreetBets, r/IndiaInvestments (via public JSON API)
2. TradingView India ideas (via public RSS/scraping)
3. StockTwits-style Indian finance forums

Each post: {post_id, title, body, source, author, score, published_at, symbols}

Note: Twitter/X API requires premium access ($100+/month), so we use
Reddit + TradingView which provide free public APIs.
"""

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class SocialPost:
    """A scraped social media post."""
    post_id: str = ""
    title: str = ""
    body: str = ""
    url: str = ""
    source: str = ""  # "reddit", "tradingview", "moneycontrol_forum"
    subreddit: str = ""
    author: str = ""
    score: int = 0  # upvotes - downvotes
    num_comments: int = 0
    published_at: Optional[datetime] = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    symbols: List[str] = field(default_factory=list)
    raw_text: str = ""
    sentiment_relevant: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.post_id and self.url:
            self.post_id = hashlib.md5(self.url.encode()).hexdigest()
        if not self.raw_text:
            self.raw_text = f"{self.title}. {self.body}".strip()


# Reddit subreddits for Indian stock market discussion
REDDIT_SUBREDDITS = [
    "IndianStreetBets",
    "IndiaInvestments",
    "DalalStreetTalks",
    "IndianStockMarket",
]

# User-Agent for Reddit public API (required)
REDDIT_USER_AGENT = "StockPulse:v1.0 (by /u/stockpulse_bot)"


async def _fetch_reddit_subreddit(
    session: aiohttp.ClientSession,
    subreddit: str,
    sort: str = "hot",
    limit: int = 25,
    time_filter: str = "day",
) -> List[SocialPost]:
    """Fetch posts from a Reddit subreddit using the public JSON API."""
    posts = []
    
    try:
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
        params = {"limit": limit, "t": time_filter, "raw_json": "1"}
        headers = {"User-Agent": REDDIT_USER_AGENT}

        async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 429:
                logger.warning(f"Reddit rate limited for r/{subreddit}")
                return []
            if resp.status != 200:
                logger.warning(f"Reddit API returned {resp.status} for r/{subreddit}")
                return []

            data = await resp.json()

        children = data.get("data", {}).get("children", [])
        
        for child in children:
            post_data = child.get("data", {})
            
            # Skip stickied/pinned posts and non-text posts
            if post_data.get("stickied", False):
                continue
            
            title = post_data.get("title", "").strip()
            body = post_data.get("selftext", "").strip()
            
            if not title:
                continue
            
            # Parse timestamp
            created_utc = post_data.get("created_utc", 0)
            published = datetime.fromtimestamp(created_utc, tz=timezone.utc) if created_utc else None

            post = SocialPost(
                post_id=post_data.get("id", ""),
                title=title,
                body=body[:1000],  # Limit body length
                url=f"https://www.reddit.com{post_data.get('permalink', '')}",
                source="reddit",
                subreddit=subreddit,
                author=post_data.get("author", ""),
                score=post_data.get("score", 0),
                num_comments=post_data.get("num_comments", 0),
                published_at=published,
                metadata={
                    "upvote_ratio": post_data.get("upvote_ratio", 0),
                    "link_flair_text": post_data.get("link_flair_text", ""),
                    "is_self": post_data.get("is_self", True),
                },
            )
            posts.append(post)

    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching r/{subreddit}")
    except Exception as e:
        logger.error(f"Error fetching r/{subreddit}: {e}")

    return posts


async def _fetch_reddit_search(
    session: aiohttp.ClientSession,
    query: str,
    subreddit: str = "IndianStreetBets",
    limit: int = 15,
) -> List[SocialPost]:
    """Search Reddit for posts about a specific stock/topic."""
    posts = []
    
    try:
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {
            "q": query,
            "restrict_sr": "1",
            "sort": "relevance",
            "t": "week",
            "limit": limit,
            "raw_json": "1",
        }
        headers = {"User-Agent": REDDIT_USER_AGENT}

        async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

        children = data.get("data", {}).get("children", [])
        
        for child in children:
            post_data = child.get("data", {})
            title = post_data.get("title", "").strip()
            if not title:
                continue

            created_utc = post_data.get("created_utc", 0)
            published = datetime.fromtimestamp(created_utc, tz=timezone.utc) if created_utc else None

            post = SocialPost(
                post_id=post_data.get("id", ""),
                title=title,
                body=post_data.get("selftext", "")[:1000],
                url=f"https://www.reddit.com{post_data.get('permalink', '')}",
                source="reddit",
                subreddit=subreddit,
                author=post_data.get("author", ""),
                score=post_data.get("score", 0),
                num_comments=post_data.get("num_comments", 0),
                published_at=published,
            )
            posts.append(post)

    except Exception as e:
        logger.error(f"Error searching Reddit for '{query}': {e}")

    return posts


def _extract_symbols_from_social(text: str) -> List[str]:
    """Extract stock symbols from social media text (e.g., $RELIANCE, NIFTY, etc.)."""
    symbols = []
    
    # Pattern 1: $SYMBOL format (common on social media)
    dollar_pattern = re.findall(r"\$([A-Z]{2,15})", text.upper())
    symbols.extend(dollar_pattern)
    
    # Pattern 2: Known Indian stock tickers in ALL CAPS
    # Only match if surrounded by non-alpha chars
    known_tickers = {
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK",
        "AXISBANK", "WIPRO", "HCLTECH", "TECHM", "BAJFINANCE", "MARUTI",
        "TATAMOTORS", "TATASTEEL", "TITAN", "ASIANPAINT", "LT", "SUNPHARMA",
        "DRREDDY", "BHARTIARTL", "ITC", "HINDUNILVR", "ADANIENT", "ADANIPORTS",
        "POWERGRID", "NTPC", "ONGC", "COALINDIA", "ULTRACEMCO", "NESTLEIND",
        "BRITANNIA", "CIPLA", "GRASIM", "INDUSINDBK", "EICHERMOT", "HEROMOTOCO",
        "JSWSTEEL", "HINDALCO", "VEDL", "ZOMATO", "PAYTM", "NIFTY", "BANKNIFTY",
        "SENSEX", "IRCTC", "TATAPOWER", "ADANIGREEN", "DIVISLAB",
    }
    
    text_upper = text.upper()
    for ticker in known_tickers:
        # Word boundary match
        pattern = r"\b" + re.escape(ticker) + r"\b"
        if re.search(pattern, text_upper):
            if ticker not in symbols:
                symbols.append(ticker)
    
    return symbols


class SocialScraper:
    """
    Social media sentiment scraper for Indian stock market.
    
    Sources:
    - Reddit: r/IndianStreetBets, r/IndiaInvestments, r/DalalStreetTalks
    - TradingView India (via RSS if available)
    
    Usage:
        scraper = SocialScraper()
        posts = await scraper.fetch_all()
        symbol_posts = await scraper.fetch_for_symbol("RELIANCE")
    """

    def __init__(
        self,
        subreddits: Optional[List[str]] = None,
        max_age_hours: int = 72,
        max_posts_per_source: int = 50,
    ):
        self._subreddits = subreddits or REDDIT_SUBREDDITS
        self._max_age = timedelta(hours=max_age_hours)
        self._max_per_source = max_posts_per_source
        self._seen_ids: Set[str] = set()
        self._post_cache: List[SocialPost] = []
        self._last_fetch: Optional[datetime] = None
        self._min_fetch_interval = timedelta(minutes=10)  # Rate limit
        self._stats = {
            "total_fetched": 0,
            "reddit_posts": 0,
            "symbols_extracted": 0,
            "fetch_errors": 0,
        }

    async def fetch_all(self, force: bool = False) -> List[SocialPost]:
        """
        Fetch posts from all configured social sources.
        Returns deduplicated, time-filtered posts sorted by score.
        """
        now = datetime.now(timezone.utc)

        # Rate limit
        if not force and self._last_fetch:
            elapsed = now - self._last_fetch
            if elapsed < self._min_fetch_interval:
                return self._post_cache

        all_posts = []

        async with aiohttp.ClientSession() as session:
            # Fetch from Reddit subreddits
            tasks = []
            for sub in self._subreddits:
                tasks.append(_fetch_reddit_subreddit(session, sub, sort="hot", limit=25))
                # Also get "new" posts for recent activity
                tasks.append(_fetch_reddit_subreddit(session, sub, sort="new", limit=15))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    self._stats["fetch_errors"] += 1
                    logger.error(f"Social fetch error: {result}")
                    continue
                all_posts.extend(result)

        # Deduplicate
        unique = []
        for post in all_posts:
            if post.post_id not in self._seen_ids:
                self._seen_ids.add(post.post_id)
                unique.append(post)

        # Filter by age
        cutoff = now - self._max_age
        fresh = [
            p for p in unique
            if p.published_at is None or p.published_at >= cutoff
        ]

        # Extract symbols from text
        for post in fresh:
            post.symbols = _extract_symbols_from_social(post.raw_text)
            self._stats["symbols_extracted"] += len(post.symbols)

        # Sort by score (most upvoted first)
        fresh.sort(key=lambda p: p.score, reverse=True)

        # Limit per source
        source_counts: Dict[str, int] = {}
        limited = []
        for post in fresh:
            key = f"{post.source}_{post.subreddit}"
            count = source_counts.get(key, 0)
            if count < self._max_per_source:
                limited.append(post)
                source_counts[key] = count + 1

        self._post_cache = limited
        self._last_fetch = now
        self._stats["total_fetched"] += len(limited)
        self._stats["reddit_posts"] = len([p for p in limited if p.source == "reddit"])

        logger.info(
            f"Social scraper: {len(limited)} posts from {len(self._subreddits)} subreddits "
            f"({len(all_posts)} total, {len(unique)} unique)"
        )

        return limited

    async def fetch_for_symbol(self, symbol: str) -> List[SocialPost]:
        """Fetch social posts relevant to a specific symbol."""
        # First check cache
        all_posts = await self.fetch_all()
        
        symbol_upper = symbol.upper().replace(".NS", "").replace(".BSE", "")
        relevant = [p for p in all_posts if symbol_upper in p.symbols]

        # If few results, do a targeted search
        if len(relevant) < 5:
            async with aiohttp.ClientSession() as session:
                for sub in self._subreddits[:2]:  # Search top 2 subreddits
                    search_results = await _fetch_reddit_search(session, symbol_upper, sub)
                    for post in search_results:
                        if post.post_id not in self._seen_ids:
                            self._seen_ids.add(post.post_id)
                            post.symbols = _extract_symbols_from_social(post.raw_text)
                            if symbol_upper not in post.symbols:
                                post.symbols.append(symbol_upper)
                            relevant.append(post)

        return relevant

    def get_cached_posts(self) -> List[SocialPost]:
        """Return cached post list without fetching."""
        return self._post_cache

    def clear_cache(self):
        """Clear the post cache."""
        self._post_cache = []
        self._seen_ids = set()
        self._last_fetch = None

    def get_stats(self) -> Dict[str, Any]:
        """Return scraper statistics."""
        source_counts = {}
        for post in self._post_cache:
            key = f"{post.source}/{post.subreddit}" if post.subreddit else post.source
            source_counts[key] = source_counts.get(key, 0) + 1

        return {
            "total_cached": len(self._post_cache),
            "sources": source_counts,
            "seen_ids": len(self._seen_ids),
            "last_fetch": self._last_fetch.isoformat() if self._last_fetch else None,
            "subreddits": self._subreddits,
            "stats": self._stats,
        }
