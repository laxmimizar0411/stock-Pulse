"""
Market Data Service for StockPulse
Provides real-time and historical stock data from Indian markets (NSE/BSE)
Uses Yahoo Finance as primary data provider

Caches via Redis (CacheService) when available, with in-memory fallback.
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from functools import lru_cache
import json

logger = logging.getLogger(__name__)

# TTL constants (seconds)
CACHE_TTL_SECONDS = 60  # 1 minute cache for real-time data
HISTORICAL_CACHE_TTL = 3600  # 1 hour for historical data
INDICES_CACHE_TTL = 60  # 1 minute for market indices
FUNDAMENTALS_CACHE_TTL = 3600  # 1 hour for fundamentals

# In-memory fallback (used only when Redis is unavailable)
_price_cache: Dict[str, Dict] = {}
_cache_timestamps: Dict[str, datetime] = {}

# NSE stock symbols need .NS suffix for Yahoo Finance
# BSE stock symbols need .BO suffix
INDIAN_STOCK_SUFFIXES = {
    "NSE": ".NS",
    "BSE": ".BO"
}

# Major Indian indices
INDIAN_INDICES = {
    "NIFTY_50": "^NSEI",
    "SENSEX": "^BSESN",
    "NIFTY_BANK": "^NSEBANK",
    "INDIA_VIX": "^INDIAVIX"
}

# Popular Indian stocks mapping (symbol -> Yahoo Finance symbol)
STOCK_SYMBOL_MAP = {
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "INFY": "INFY.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "HINDUNILVR": "HINDUNILVR.NS",
    "ITC": "ITC.NS",
    "SBIN": "SBIN.NS",
    "BHARTIARTL": "BHARTIARTL.NS",
    "KOTAKBANK": "KOTAKBANK.NS",
    "LT": "LT.NS",
    "AXISBANK": "AXISBANK.NS",
    "ASIANPAINT": "ASIANPAINT.NS",
    "MARUTI": "MARUTI.NS",
    "SUNPHARMA": "SUNPHARMA.NS",
    "TITAN": "TITAN.NS",
    "BAJFINANCE": "BAJFINANCE.NS",
    "WIPRO": "WIPRO.NS",
    "ULTRACEMCO": "ULTRACEMCO.NS",
    "NESTLEIND": "NESTLEIND.NS",
    "HCLTECH": "HCLTECH.NS",
    "NTPC": "NTPC.NS",
    "TATASTEEL": "TATASTEEL.NS",
    "ONGC": "ONGC.NS",
    "JSWSTEEL": "JSWSTEEL.NS",
    "POWERGRID": "POWERGRID.NS",
    "TECHM": "TECHM.NS",
    "M&M": "M&M.NS",
    "ADANIENT": "ADANIENT.NS",
    "ADANIPORTS": "ADANIPORTS.NS",
    "COALINDIA": "COALINDIA.NS",
    "DRREDDY": "DRREDDY.NS",
    "DIVISLAB": "DIVISLAB.NS",
    "BAJAJFINSV": "BAJAJFINSV.NS",
    "TATAMOTORS": "TATAMOTORS.NS",
    "EICHERMOT": "EICHERMOT.NS",
    "BRITANNIA": "BRITANNIA.NS",
    "CIPLA": "CIPLA.NS",
    "GRASIM": "GRASIM.NS",
    "APOLLOHOSP": "APOLLOHOSP.NS",
    "HAVELLS": "HAVELLS.NS",
    "VOLTAS": "VOLTAS.NS",
    "TRENT": "TRENT.NS",
    "ZOMATO": "ZOMATO.NS",
    "PAYTM": "PAYTM.NS",
    "NYKAA": "NYKAA.NS",
}


def _get_cache():
    """Get the global CacheService if available."""
    try:
        from services.cache_service import get_cache_service
        return get_cache_service()
    except Exception:
        return None


def _cache_get(key: str) -> Optional[Any]:
    """Get from Redis (via CacheService) first, then in-memory fallback."""
    svc = _get_cache()
    if svc:
        result = svc.get(key)
        if result is not None:
            return result
    # In-memory fallback
    if key in _cache_timestamps:
        return _price_cache.get(key)
    return None


def _cache_set(key: str, value: Any, ttl: int) -> None:
    """Set in Redis (via CacheService) and in-memory fallback."""
    svc = _get_cache()
    if svc:
        svc.set(key, value, ttl)
    # Always keep in-memory copy as fallback
    _price_cache[key] = value
    _cache_timestamps[key] = datetime.now()


def get_yahoo_symbol(symbol: str, exchange: str = "NSE") -> str:
    """Convert Indian stock symbol to Yahoo Finance format"""
    # Check if already in map
    if symbol in STOCK_SYMBOL_MAP:
        return STOCK_SYMBOL_MAP[symbol]

    # Check if it's an index
    if symbol in INDIAN_INDICES:
        return INDIAN_INDICES[symbol]

    # Default: append NSE suffix
    suffix = INDIAN_STOCK_SUFFIXES.get(exchange, ".NS")
    return f"{symbol}{suffix}"


def is_cache_valid(cache_key: str, ttl: int = CACHE_TTL_SECONDS) -> bool:
    """Check if cached data is still valid (in-memory only check)."""
    if cache_key not in _cache_timestamps:
        return False
    age = (datetime.now() - _cache_timestamps[cache_key]).total_seconds()
    return age < ttl


async def get_stock_quote(symbol: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Get real-time stock quote for a symbol.
    Uses Redis cache (shared across instances) with in-memory fallback.
    """
    cache_key = f"mkt:quote:{symbol}"

    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    try:
        import yfinance as yf

        yahoo_symbol = get_yahoo_symbol(symbol)
        ticker = yf.Ticker(yahoo_symbol)

        # Get real-time info
        info = ticker.info

        if not info or 'regularMarketPrice' not in info:
            logger.warning(f"No data found for {symbol}")
            return None

        quote_data = {
            "symbol": symbol,
            "yahoo_symbol": yahoo_symbol,
            "name": info.get("longName") or info.get("shortName", symbol),
            "current_price": info.get("regularMarketPrice", 0),
            "previous_close": info.get("regularMarketPreviousClose", 0),
            "open": info.get("regularMarketOpen", 0),
            "high": info.get("regularMarketDayHigh", 0),
            "low": info.get("regularMarketDayLow", 0),
            "volume": info.get("regularMarketVolume", 0),
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE"),
            "pb_ratio": info.get("priceToBook"),
            "dividend_yield": info.get("dividendYield", 0) * 100 if info.get("dividendYield") else 0,
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0),
            "avg_volume": info.get("averageVolume", 0),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "timestamp": datetime.now().isoformat()
        }

        # Calculate price change
        if quote_data["previous_close"] and quote_data["previous_close"] > 0:
            quote_data["price_change"] = quote_data["current_price"] - quote_data["previous_close"]
            quote_data["price_change_percent"] = (quote_data["price_change"] / quote_data["previous_close"]) * 100
        else:
            quote_data["price_change"] = 0
            quote_data["price_change_percent"] = 0

        # Cache the result in Redis + in-memory
        _cache_set(cache_key, quote_data, CACHE_TTL_SECONDS)

        return quote_data

    except ImportError:
        logger.error("yfinance not installed. Run: pip install yfinance")
        return None
    except Exception as e:
        logger.error(f"Error fetching quote for {symbol}: {str(e)}")
        return None


async def get_historical_data(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
    use_cache: bool = True
) -> List[Dict[str, Any]]:
    """
    Get historical price data for a symbol.
    Uses Redis cache (shared across instances) with in-memory fallback.
    """
    cache_key = f"mkt:history:{symbol}:{period}:{interval}"

    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    try:
        import yfinance as yf

        yahoo_symbol = get_yahoo_symbol(symbol)
        ticker = yf.Ticker(yahoo_symbol)

        # Get historical data
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            logger.warning(f"No historical data found for {symbol}")
            return []

        # Convert to list of dicts
        history_data = []
        for date, row in hist.iterrows():
            history_data.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(row["Open"], 2),
                "high": round(row["High"], 2),
                "low": round(row["Low"], 2),
                "close": round(row["Close"], 2),
                "volume": int(row["Volume"])
            })

        # Cache the result
        _cache_set(cache_key, history_data, HISTORICAL_CACHE_TTL)

        return history_data

    except ImportError:
        logger.error("yfinance not installed. Run: pip install yfinance")
        return []
    except Exception as e:
        logger.error(f"Error fetching history for {symbol}: {str(e)}")
        return []


async def get_market_indices() -> Dict[str, Any]:
    """Get current values for major Indian market indices.
    Uses Redis cache (shared across instances) with in-memory fallback."""
    cache_key = "mkt:indices"

    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        import yfinance as yf

        indices_data = {}

        for name, yahoo_symbol in INDIAN_INDICES.items():
            try:
                ticker = yf.Ticker(yahoo_symbol)
                info = ticker.info

                current_price = info.get("regularMarketPrice", 0)
                previous_close = info.get("regularMarketPreviousClose", 0)

                change = current_price - previous_close if previous_close else 0
                change_percent = (change / previous_close * 100) if previous_close else 0

                indices_data[name.lower()] = {
                    "value": round(current_price, 2),
                    "change": round(change, 2),
                    "change_percent": round(change_percent, 2),
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Error fetching index {name}: {str(e)}")
                indices_data[name.lower()] = {
                    "value": 0,
                    "change": 0,
                    "change_percent": 0,
                    "error": str(e)
                }

        # Cache the result
        _cache_set(cache_key, indices_data, INDICES_CACHE_TTL)

        return indices_data

    except ImportError:
        logger.error("yfinance not installed")
        return {}
    except Exception as e:
        logger.error(f"Error fetching market indices: {str(e)}")
        return {}


async def get_bulk_quotes(symbols: List[str]) -> Dict[str, Dict]:
    """Get quotes for multiple symbols efficiently"""
    try:
        import yfinance as yf

        # Convert symbols to Yahoo format
        yahoo_symbols = [get_yahoo_symbol(s) for s in symbols]

        # Download all at once
        tickers = yf.Tickers(" ".join(yahoo_symbols))

        results = {}
        for i, symbol in enumerate(symbols):
            yahoo_sym = yahoo_symbols[i]
            try:
                info = tickers.tickers[yahoo_sym].info

                current_price = info.get("regularMarketPrice", 0)
                previous_close = info.get("regularMarketPreviousClose", 0)
                change = current_price - previous_close if previous_close else 0
                change_percent = (change / previous_close * 100) if previous_close else 0

                results[symbol] = {
                    "symbol": symbol,
                    "current_price": current_price,
                    "price_change": round(change, 2),
                    "price_change_percent": round(change_percent, 2),
                    "volume": info.get("regularMarketVolume", 0),
                    "name": info.get("longName") or info.get("shortName", symbol)
                }
            except Exception as e:
                logger.error(f"Error in bulk quote for {symbol}: {str(e)}")
                results[symbol] = None

        return results

    except ImportError:
        logger.error("yfinance not installed")
        return {}
    except Exception as e:
        logger.error(f"Error in bulk quotes: {str(e)}")
        return {}


async def get_stock_fundamentals(symbol: str) -> Optional[Dict[str, Any]]:
    """Get fundamental data for a stock.
    Uses Redis cache (shared across instances) with in-memory fallback."""
    cache_key = f"mkt:fundamentals:{symbol}"

    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        import yfinance as yf

        yahoo_symbol = get_yahoo_symbol(symbol)
        ticker = yf.Ticker(yahoo_symbol)
        info = ticker.info

        fundamentals = {
            "symbol": symbol,
            "revenue_ttm": info.get("totalRevenue", 0),
            "revenue_growth_yoy": info.get("revenueGrowth", 0) * 100 if info.get("revenueGrowth") else 0,
            "net_profit": info.get("netIncomeToCommon", 0),
            "eps": info.get("trailingEps", 0),
            "gross_margin": info.get("grossMargins", 0) * 100 if info.get("grossMargins") else 0,
            "operating_margin": info.get("operatingMargins", 0) * 100 if info.get("operatingMargins") else 0,
            "net_profit_margin": info.get("profitMargins", 0) * 100 if info.get("profitMargins") else 0,
            "roe": info.get("returnOnEquity", 0) * 100 if info.get("returnOnEquity") else 0,
            "roa": info.get("returnOnAssets", 0) * 100 if info.get("returnOnAssets") else 0,
            "debt_to_equity": info.get("debtToEquity", 0) / 100 if info.get("debtToEquity") else 0,
            "current_ratio": info.get("currentRatio", 0),
            "quick_ratio": info.get("quickRatio", 0),
            "free_cash_flow": info.get("freeCashflow", 0),
            "operating_cash_flow": info.get("operatingCashflow", 0),
        }

        # Cache the result
        _cache_set(cache_key, fundamentals, FUNDAMENTALS_CACHE_TTL)

        return fundamentals

    except ImportError:
        logger.error("yfinance not installed")
        return None
    except Exception as e:
        logger.error(f"Error fetching fundamentals for {symbol}: {str(e)}")
        return None


async def get_stock_financials(symbol: str) -> Optional[Dict[str, Any]]:
    """Get financial statements data"""
    try:
        import yfinance as yf

        yahoo_symbol = get_yahoo_symbol(symbol)
        ticker = yf.Ticker(yahoo_symbol)

        # Get financial statements
        income_stmt = ticker.income_stmt
        balance_sheet = ticker.balance_sheet
        cash_flow = ticker.cashflow

        return {
            "income_statement": income_stmt.to_dict() if not income_stmt.empty else {},
            "balance_sheet": balance_sheet.to_dict() if not balance_sheet.empty else {},
            "cash_flow": cash_flow.to_dict() if not cash_flow.empty else {}
        }

    except Exception as e:
        logger.error(f"Error fetching financials for {symbol}: {str(e)}")
        return None


def clear_cache():
    """Clear all cached data (in-memory and Redis market keys)"""
    global _price_cache, _cache_timestamps
    _price_cache = {}
    _cache_timestamps = {}
    svc = _get_cache()
    if svc:
        svc.delete_pattern("mkt:*")
    logger.info("Market data cache cleared")


def get_available_symbols() -> List[str]:
    """Get list of available stock symbols"""
    return list(STOCK_SYMBOL_MAP.keys())


# Check if real data service is available
def is_real_data_available() -> bool:
    """Check if yfinance is installed and working"""
    try:
        import yfinance
        return True
    except ImportError:
        return False
