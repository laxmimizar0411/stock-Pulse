"""
Financial Entity Extractor

Maps news articles to stock tickers using:
1. Direct symbol/company name matching against a known universe
2. NSE/BSE symbol aliases and common abbreviations
3. Sector-level classification when no direct match found

This avoids requiring spaCy NER for basic entity resolution —
the known-universe approach is more reliable for Indian stocks.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class EntityMatch:
    """A matched entity in text."""
    symbol: str
    company_name: str
    match_type: str  # "symbol", "company_name", "alias", "sector"
    confidence: float  # [0, 1]
    matched_text: str = ""


# Common Indian stock aliases / short names used in news
# Maps lowercase alias -> NSE symbol
DEFAULT_ALIASES = {
    # Major indices
    "nifty": "NIFTY",
    "nifty50": "NIFTY",
    "sensex": "SENSEX",
    "bank nifty": "BANKNIFTY",
    "banknifty": "BANKNIFTY",
    # Large caps commonly in news
    "reliance": "RELIANCE",
    "ril": "RELIANCE",
    "reliance industries": "RELIANCE",
    "tcs": "TCS",
    "tata consultancy": "TCS",
    "infosys": "INFY",
    "infy": "INFY",
    "hdfc bank": "HDFCBANK",
    "hdfcbank": "HDFCBANK",
    "hdfc": "HDFCBANK",
    "icici bank": "ICICIBANK",
    "icici": "ICICIBANK",
    "sbi": "SBIN",
    "state bank": "SBIN",
    "state bank of india": "SBIN",
    "kotak": "KOTAKBANK",
    "kotak mahindra": "KOTAKBANK",
    "axis bank": "AXISBANK",
    "axis": "AXISBANK",
    "wipro": "WIPRO",
    "hcl tech": "HCLTECH",
    "hcltech": "HCLTECH",
    "hcl technologies": "HCLTECH",
    "tech mahindra": "TECHM",
    "techm": "TECHM",
    "bajaj finance": "BAJFINANCE",
    "bajfinance": "BAJFINANCE",
    "bajaj finserv": "BAJAJFINSV",
    "maruti": "MARUTI",
    "maruti suzuki": "MARUTI",
    "tata motors": "TATAMOTORS",
    "tata steel": "TATASTEEL",
    "tata power": "TATAPOWER",
    "titan": "TITAN",
    "asian paints": "ASIANPAINT",
    "larsen": "LT",
    "l&t": "LT",
    "larsen & toubro": "LT",
    "sun pharma": "SUNPHARMA",
    "sun pharmaceutical": "SUNPHARMA",
    "dr reddy": "DRREDDY",
    "dr reddys": "DRREDDY",
    "bharti airtel": "BHARTIARTL",
    "airtel": "BHARTIARTL",
    "itc": "ITC",
    "hindustan unilever": "HINDUNILVR",
    "hul": "HINDUNILVR",
    "adani enterprises": "ADANIENT",
    "adani ports": "ADANIPORTS",
    "adani green": "ADANIGREEN",
    "adani": "ADANIENT",
    "power grid": "POWERGRID",
    "ntpc": "NTPC",
    "ongc": "ONGC",
    "coal india": "COALINDIA",
    "ultratech": "ULTRACEMCO",
    "ultratech cement": "ULTRACEMCO",
    "nestle india": "NESTLEIND",
    "nestle": "NESTLEIND",
    "britannia": "BRITANNIA",
    "divis lab": "DIVISLAB",
    "cipla": "CIPLA",
    "grasim": "GRASIM",
    "indusind bank": "INDUSINDBK",
    "indusind": "INDUSINDBK",
    "m&m": "M&M",
    "mahindra": "M&M",
    "mahindra and mahindra": "M&M",
    "eicher motors": "EICHERMOT",
    "eicher": "EICHERMOT",
    "hero motocorp": "HEROMOTOCO",
    "hero": "HEROMOTOCO",
    "bajaj auto": "BAJAJ-AUTO",
    "jsw steel": "JSWSTEEL",
    "jsw": "JSWSTEEL",
    "hindalco": "HINDALCO",
    "vedanta": "VEDL",
    "zomato": "ZOMATO",
    "paytm": "PAYTM",
}

# Sector keywords for sector-level classification
SECTOR_KEYWORDS = {
    "banking": ["bank", "banking", "npa", "credit growth", "deposit", "loan"],
    "it": ["it", "software", "digital", "cloud", "saas", "ai"],
    "pharma": ["pharma", "drug", "fda", "usfda", "clinical trial", "api"],
    "auto": ["auto", "vehicle", "ev", "electric vehicle", "car", "two-wheeler"],
    "fmcg": ["fmcg", "consumer", "packaged goods", "food", "beverages"],
    "energy": ["oil", "gas", "crude", "petroleum", "refinery", "energy"],
    "metals": ["steel", "metal", "mining", "aluminium", "copper", "iron ore"],
    "realty": ["real estate", "realty", "housing", "property", "construction"],
    "telecom": ["telecom", "5g", "spectrum", "broadband", "mobile"],
    "infra": ["infrastructure", "road", "highway", "railway", "metro"],
}


class EntityExtractor:
    """
    Extracts stock tickers from news text using known-universe matching.

    Usage:
        extractor = EntityExtractor()
        extractor.load_universe({"RELIANCE": "Reliance Industries Ltd", ...})
        matches = extractor.extract("Reliance reports record quarterly profit")
    """

    def __init__(self):
        # symbol -> company_name mapping
        self._universe: Dict[str, str] = {}
        # lowercase company name -> symbol
        self._name_to_symbol: Dict[str, str] = {}
        # lowercase alias -> symbol
        self._aliases: Dict[str, str] = dict(DEFAULT_ALIASES)
        # Pre-compiled patterns for faster matching
        self._symbol_pattern: Optional[re.Pattern] = None

    def load_universe(self, universe: Dict[str, str]):
        """
        Load the stock universe for entity matching.

        Args:
            universe: Dict of symbol -> company_name
                      e.g. {"RELIANCE": "Reliance Industries Ltd"}
        """
        self._universe = universe
        self._name_to_symbol = {}

        for symbol, name in universe.items():
            # Index by lowercase name for fuzzy matching
            self._name_to_symbol[name.lower()] = symbol
            # Also index partial names (first two words)
            words = name.lower().split()
            if len(words) >= 2:
                short = " ".join(words[:2])
                if short not in self._name_to_symbol:
                    self._name_to_symbol[short] = symbol

        # Build regex for symbol matching (word-boundary match)
        if universe:
            escaped = [re.escape(s) for s in universe.keys()]
            self._symbol_pattern = re.compile(
                r"\b(" + "|".join(escaped) + r")\b",
                re.IGNORECASE,
            )

        logger.info(f"Entity extractor loaded {len(universe)} symbols")

    def add_aliases(self, aliases: Dict[str, str]):
        """Add custom aliases (lowercase text -> symbol)."""
        self._aliases.update(aliases)

    def extract(self, text: str) -> List[EntityMatch]:
        """
        Extract stock entities from text.

        Returns matches sorted by confidence (highest first).
        """
        if not text:
            return []

        matches: Dict[str, EntityMatch] = {}  # symbol -> best match
        text_lower = text.lower()

        # 1. Direct symbol match (highest confidence)
        if self._symbol_pattern:
            for m in self._symbol_pattern.finditer(text):
                symbol = m.group().upper()
                if symbol in self._universe:
                    matches[symbol] = EntityMatch(
                        symbol=symbol,
                        company_name=self._universe.get(symbol, ""),
                        match_type="symbol",
                        confidence=0.95,
                        matched_text=m.group(),
                    )

        # 2. Alias match
        for alias, symbol in self._aliases.items():
            if alias in text_lower:
                # Ensure it's not a substring of a longer word
                idx = text_lower.find(alias)
                before = text_lower[idx - 1] if idx > 0 else " "
                after = text_lower[idx + len(alias)] if idx + len(alias) < len(text_lower) else " "
                if not before.isalnum() and not after.isalnum():
                    if symbol not in matches or matches[symbol].confidence < 0.85:
                        matches[symbol] = EntityMatch(
                            symbol=symbol,
                            company_name=self._universe.get(symbol, alias),
                            match_type="alias",
                            confidence=0.85,
                            matched_text=alias,
                        )

        # 3. Company name match
        for name, symbol in self._name_to_symbol.items():
            if len(name) >= 4 and name in text_lower:
                if symbol not in matches or matches[symbol].confidence < 0.80:
                    matches[symbol] = EntityMatch(
                        symbol=symbol,
                        company_name=self._universe.get(symbol, name),
                        match_type="company_name",
                        confidence=0.80,
                        matched_text=name,
                    )

        # Sort by confidence
        result = sorted(matches.values(), key=lambda m: m.confidence, reverse=True)
        return result

    def extract_sectors(self, text: str) -> List[str]:
        """Extract sector mentions from text."""
        text_lower = text.lower()
        sectors = []

        for sector, keywords in SECTOR_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    sectors.append(sector)
                    break

        return sectors

    def map_articles_to_symbols(
        self, articles: List[Any]
    ) -> Dict[str, List[Any]]:
        """
        Map a list of articles to symbols.

        Args:
            articles: List of NewsArticle objects (must have .raw_text and .symbols attrs)

        Returns:
            Dict of symbol -> list of articles mentioning that symbol
        """
        symbol_articles: Dict[str, List[Any]] = {}

        for article in articles:
            text = getattr(article, "raw_text", "") or ""
            matches = self.extract(text)

            # Update article's symbols list
            article_symbols = getattr(article, "symbols", [])
            for match in matches:
                if match.symbol not in article_symbols:
                    article_symbols.append(match.symbol)

            # Build reverse index
            for match in matches:
                if match.symbol not in symbol_articles:
                    symbol_articles[match.symbol] = []
                symbol_articles[match.symbol].append(article)

        return symbol_articles

    def get_universe_size(self) -> int:
        """Return the number of symbols in the universe."""
        return len(self._universe)
