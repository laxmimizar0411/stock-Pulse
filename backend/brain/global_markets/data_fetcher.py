"""
Global Markets Data Fetcher

Fetches overnight data for global markets that influence Indian markets.
Data source: YFinance (free, no API key required)
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Global market tickers
GLOBAL_TICKERS = {
    # US Indices
    "SP500": "^GSPC",           # S&P 500
    "NASDAQ": "^IXIC",          # NASDAQ Composite
    "DOW": "^DJI",              # Dow Jones Industrial Average
    
    # Asian Indices
    "SGX_NIFTY": "^NSEI",       # SGX NIFTY (use NSE NIFTY as proxy)
    "NIKKEI": "^N225",          # Nikkei 225
    "HANGSENG": "^HSI",         # Hang Seng
    
    # Commodities
    "CRUDE_WTI": "CL=F",        # Crude Oil WTI Futures
    "CRUDE_BRENT": "BZ=F",      # Brent Crude Futures
    "GOLD": "GC=F",             # Gold Futures
    
    # Currencies & Bonds
    "DXY": "DX-Y.NYB",          # US Dollar Index
    "US_10Y": "^TNX",           # US 10-Year Treasury Yield
    
    # Emerging Markets
    "MSCI_EM": "EEM",           # MSCI Emerging Markets ETF
}


class GlobalMarketsFetcher:
    """
    Fetches overnight global markets data for correlation analysis.
    
    Updates:
    - Pre-market: Fetches data from previous close
    - Intraday: Can fetch real-time data during market hours
    """
    
    def __init__(self):
        self.tickers = GLOBAL_TICKERS
        self.cache: Dict[str, pd.DataFrame] = {}
        self.last_fetch_time: Optional[datetime] = None
        self.cache_ttl_seconds = 300  # 5 minutes
        
    async def fetch_overnight_data(
        self,
        lookback_days: int = 30
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch overnight data for all global markets.
        
        Args:
            lookback_days: Number of days of historical data to fetch
            
        Returns:
            Dictionary mapping market name to DataFrame with OHLCV data
        """
        # Check cache
        if self._is_cache_valid():
            logger.info("Using cached global markets data")
            return self.cache
        
        logger.info(f"Fetching overnight data for {len(self.tickers)} global markets...")
        
        # Fetch data in parallel
        tasks = []
        for name, ticker in self.tickers.items():
            tasks.append(self._fetch_single_ticker(name, ticker, lookback_days))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        data = {}
        for i, (name, ticker) in enumerate(self.tickers.items()):
            if isinstance(results[i], Exception):
                logger.error(f"Failed to fetch {name} ({ticker}): {results[i]}")
                continue
            
            if results[i] is not None and not results[i].empty:
                data[name] = results[i]
        
        # Update cache
        self.cache = data
        self.last_fetch_time = datetime.now(timezone.utc)
        
        logger.info(f"✅ Fetched data for {len(data)}/{len(self.tickers)} markets")
        
        return data
    
    async def _fetch_single_ticker(
        self,
        name: str,
        ticker: str,
        lookback_days: int
    ) -> Optional[pd.DataFrame]:
        """Fetch data for a single ticker."""
        try:
            import yfinance as yf
            
            # Run yfinance in thread pool (blocking operation)
            df = await asyncio.to_thread(
                self._fetch_ticker_sync,
                ticker,
                lookback_days
            )
            
            if df is not None and not df.empty:
                # Add metadata
                df['market'] = name
                df['ticker'] = ticker
                return df
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching {name} ({ticker}): {str(e)}")
            return None
    
    def _fetch_ticker_sync(self, ticker: str, lookback_days: int) -> Optional[pd.DataFrame]:
        """Synchronous ticker fetch."""
        try:
            import yfinance as yf
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days)
            
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(start=start_date, end=end_date)
            
            if df.empty:
                return None
            
            # Reset index to make Date a column
            df = df.reset_index()
            
            return df
            
        except Exception as e:
            logger.error(f"yfinance fetch error for {ticker}: {str(e)}")
            return None
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self.cache or self.last_fetch_time is None:
            return False
        
        age_seconds = (datetime.now(timezone.utc) - self.last_fetch_time).total_seconds()
        return age_seconds < self.cache_ttl_seconds
    
    def get_latest_close_prices(self) -> Dict[str, float]:
        """
        Get latest closing prices for all markets.
        
        Returns:
            Dictionary mapping market name to latest close price
        """
        if not self.cache:
            return {}
        
        latest_prices = {}
        for name, df in self.cache.items():
            if not df.empty and 'Close' in df.columns:
                latest_prices[name] = float(df['Close'].iloc[-1])
        
        return latest_prices
    
    def get_percentage_changes(self, periods: int = 1) -> Dict[str, float]:
        """
        Get percentage changes for all markets.
        
        Args:
            periods: Number of periods for change calculation (1 = daily)
            
        Returns:
            Dictionary mapping market name to percentage change
        """
        if not self.cache:
            return {}
        
        changes = {}
        for name, df in self.cache.items():
            if not df.empty and 'Close' in df.columns and len(df) > periods:
                current = df['Close'].iloc[-1]
                previous = df['Close'].iloc[-1 - periods]
                pct_change = ((current - previous) / previous) * 100
                changes[name] = float(pct_change)
        
        return changes
    
    def get_market_summary(self) -> Dict[str, Any]:
        """Get summary of all markets."""
        if not self.cache:
            return {
                "markets_count": 0,
                "last_update": None,
                "available_markets": []
            }
        
        latest_prices = self.get_latest_close_prices()
        daily_changes = self.get_percentage_changes(periods=1)
        
        return {
            "markets_count": len(self.cache),
            "last_update": self.last_fetch_time.isoformat() if self.last_fetch_time else None,
            "available_markets": list(self.cache.keys()),
            "latest_prices": latest_prices,
            "daily_changes_pct": daily_changes,
            "cache_valid": self._is_cache_valid()
        }
    
    async def get_market_status(self) -> Dict[str, Any]:
        """
        Get current market status (open/closed based on time).
        
        Returns market session information.
        """
        now = datetime.now(timezone.utc)
        
        # Market hours (UTC)
        us_market_open = now.replace(hour=14, minute=30, second=0, microsecond=0)  # 9:30 AM ET
        us_market_close = now.replace(hour=21, minute=0, second=0, microsecond=0)  # 4:00 PM ET
        
        asian_market_open = now.replace(hour=1, minute=0, second=0, microsecond=0)  # ~9:00 AM Asia
        asian_market_close = now.replace(hour=8, minute=0, second=0, microsecond=0)  # ~4:00 PM Asia
        
        india_market_open = now.replace(hour=3, minute=45, second=0, microsecond=0)  # 9:15 AM IST
        india_market_close = now.replace(hour=10, minute=0, second=0, microsecond=0)  # 3:30 PM IST
        
        return {
            "current_utc": now.isoformat(),
            "us_markets": {
                "is_open": us_market_open <= now <= us_market_close,
                "open_time_utc": us_market_open.isoformat(),
                "close_time_utc": us_market_close.isoformat()
            },
            "asian_markets": {
                "is_open": asian_market_open <= now <= asian_market_close,
                "open_time_utc": asian_market_open.isoformat(),
                "close_time_utc": asian_market_close.isoformat()
            },
            "indian_markets": {
                "is_open": india_market_open <= now <= india_market_close,
                "open_time_utc": india_market_open.isoformat(),
                "close_time_utc": india_market_close.isoformat()
            }
        }
    
    def clear_cache(self):
        """Clear cached data."""
        self.cache = {}
        self.last_fetch_time = None
        logger.info("Global markets cache cleared")
