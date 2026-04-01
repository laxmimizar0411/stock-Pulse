"""
Data Normalizer — Canonical data format converter for Stock Pulse Brain.

Converts raw data from any extractor (YFinance, Dhan, Groww, NSE Bhavcopy)
into the canonical OHLCVBar and TickData Pydantic schemas defined in
brain.schemas.market_data.

Usage:
    normalizer = DataNormalizer()
    bars = normalizer.normalize_ohlcv(raw_df, source="yfinance", symbol="RELIANCE")
    tick = normalizer.normalize_tick(raw_dict, source="dhan", symbol="TCS")
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from brain.schemas.market_data import Exchange, OHLCVBar, TickData

logger = logging.getLogger("brain.ingestion.normalizer")

# IST timezone offset
IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# Column mappings per data source
# ---------------------------------------------------------------------------

SOURCE_COLUMN_MAPS: Dict[str, Dict[str, str]] = {
    "yfinance": {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
        "Date": "date",
        "Adj Close": "adj_close",
    },
    "dhan": {
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "start_Time": "date",
    },
    "groww": {
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "ltp": "ltp",
    },
    "nse_bhavcopy": {
        "OPEN": "open",
        "HIGH": "high",
        "LOW": "low",
        "CLOSE": "close",
        "TOTTRDQTY": "volume",
        "TIMESTAMP": "date",
        "SYMBOL": "symbol",
        "DELIV_QTY": "delivery_volume",
        "DELIV_PER": "delivery_pct",
    },
    "screener": {
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
    },
}

# ---------------------------------------------------------------------------
# Exchange inference based on symbol suffix/convention
# ---------------------------------------------------------------------------

def _infer_exchange(symbol: str) -> Exchange:
    """Infer exchange from symbol suffix or convention."""
    s = symbol.upper()
    if s.endswith(".NS") or s.endswith(".NSE"):
        return Exchange.NSE
    elif s.endswith(".BO") or s.endswith(".BSE") or s.endswith(".BOM"):
        return Exchange.BSE
    # Default to NSE for Indian stocks
    return Exchange.NSE


def _clean_symbol(symbol: str) -> str:
    """Remove exchange suffixes from symbol."""
    s = symbol.upper()
    for suffix in [".NS", ".NSE", ".BO", ".BSE", ".BOM"]:
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    return s


class DataNormalizer:
    """
    Converts raw market data from various sources into canonical Brain schemas.
    """

    def normalize_ohlcv(
        self,
        raw_df: pd.DataFrame,
        source: str,
        symbol: str,
        timeframe: str = "1d",
    ) -> List[OHLCVBar]:
        """
        Normalize a raw OHLCV DataFrame into a list of canonical OHLCVBar objects.

        Args:
            raw_df: Raw DataFrame from any extractor.
            source: Data source identifier (yfinance, dhan, groww, nse_bhavcopy).
            symbol: Stock symbol (e.g. RELIANCE.NS, RELIANCE).
            timeframe: Candle timeframe (1m, 5m, 15m, 1h, 1d).

        Returns:
            List of OHLCVBar Pydantic models, sorted by timestamp ascending.
        """
        if raw_df is None or raw_df.empty:
            logger.warning("Empty DataFrame for %s from %s", symbol, source)
            return []

        df = raw_df.copy()
        exchange = _infer_exchange(symbol)
        clean_sym = _clean_symbol(symbol)

        # Apply column mapping
        col_map = SOURCE_COLUMN_MAPS.get(source, {})
        if col_map:
            rename_map = {}
            for raw_col, canonical_col in col_map.items():
                if raw_col in df.columns:
                    rename_map[raw_col] = canonical_col
            df.rename(columns=rename_map, inplace=True)

        # Ensure lowercase column names
        df.columns = [c.lower() for c in df.columns]

        # Ensure required columns exist
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            logger.error(
                "Missing columns %s for %s from %s. Available: %s",
                missing, symbol, source, list(df.columns),
            )
            return []

        # Handle date/index
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        elif isinstance(df.index, pd.DatetimeIndex):
            df["date"] = df.index
            df.reset_index(drop=True, inplace=True)
        else:
            # Use integer index as fallback
            df["date"] = pd.Timestamp.now(tz=IST)

        # Ensure timezone-aware timestamps (localize to IST if naive)
        if df["date"].dt.tz is None:
            df["date"] = df["date"].dt.tz_localize(IST)
        else:
            df["date"] = df["date"].dt.tz_convert(IST)

        # Handle NaN/inf
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)

        # Drop rows with NaN prices
        df.dropna(subset=["open", "high", "low", "close"], inplace=True)

        # Sort by date ascending
        df.sort_values("date", inplace=True)

        # Convert to OHLCVBar list
        bars: List[OHLCVBar] = []
        for _, row in df.iterrows():
            bar = OHLCVBar(
                symbol=clean_sym,
                exchange=exchange,
                timeframe=timeframe,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                vwap=float(row["vwap"]) if "vwap" in row and pd.notna(row.get("vwap")) else None,
                delivery_volume=int(row["delivery_volume"]) if "delivery_volume" in row and pd.notna(row.get("delivery_volume")) else None,
                delivery_pct=float(row["delivery_pct"]) if "delivery_pct" in row and pd.notna(row.get("delivery_pct")) else None,
                timestamp=row["date"].to_pydatetime(),
                source=source,
            )
            bars.append(bar)

        logger.info(
            "Normalized %d OHLCV bars for %s from %s (%s)",
            len(bars), clean_sym, source, timeframe,
        )
        return bars

    def normalize_tick(
        self,
        raw_data: Dict,
        source: str,
        symbol: str,
    ) -> Optional[TickData]:
        """
        Normalize a raw tick/LTP update dict into a canonical TickData object.

        Args:
            raw_data: Raw tick data dict from a broker WebSocket or API.
            source: Data source identifier.
            symbol: Stock symbol.

        Returns:
            TickData Pydantic model, or None if data is invalid.
        """
        try:
            exchange = _infer_exchange(symbol)
            clean_sym = _clean_symbol(symbol)

            # Extract LTP — try common field names
            ltp = None
            for key in ["ltp", "last_price", "lastPrice", "close", "lp", "price"]:
                if key in raw_data and raw_data[key] is not None:
                    ltp = float(raw_data[key])
                    break

            if ltp is None or ltp <= 0:
                logger.warning("No valid LTP in tick data for %s from %s", symbol, source)
                return None

            # Extract timestamp
            ts = None
            for key in ["timestamp", "exchange_timestamp", "time", "ltt", "last_trade_time"]:
                if key in raw_data and raw_data[key] is not None:
                    try:
                        ts = pd.Timestamp(raw_data[key])
                        if ts.tz is None:
                            ts = ts.tz_localize(IST)
                        break
                    except Exception:
                        continue
            if ts is None:
                ts = pd.Timestamp.now(tz=IST)

            return TickData(
                symbol=clean_sym,
                exchange=exchange,
                ltp=ltp,
                volume=int(raw_data.get("volume", raw_data.get("vol", 0)) or 0),
                timestamp=ts.to_pydatetime(),
                bid=float(raw_data["bid"]) if "bid" in raw_data and raw_data.get("bid") else None,
                ask=float(raw_data["ask"]) if "ask" in raw_data and raw_data.get("ask") else None,
                bid_qty=int(raw_data["bid_qty"]) if "bid_qty" in raw_data and raw_data.get("bid_qty") else None,
                ask_qty=int(raw_data["ask_qty"]) if "ask_qty" in raw_data and raw_data.get("ask_qty") else None,
                oi=int(raw_data["oi"]) if "oi" in raw_data and raw_data.get("oi") else None,
                source=source,
            )

        except Exception:
            logger.exception("Error normalizing tick for %s from %s", symbol, source)
            return None

    def normalize_dataframe_to_canonical(
        self,
        raw_df: pd.DataFrame,
        source: str,
    ) -> pd.DataFrame:
        """
        Normalize column names of a raw DataFrame to canonical format.
        Returns a DataFrame with standard column names (no Pydantic conversion).
        Useful for batch processing pipelines.
        """
        if raw_df is None or raw_df.empty:
            return pd.DataFrame()

        df = raw_df.copy()
        col_map = SOURCE_COLUMN_MAPS.get(source, {})
        if col_map:
            rename_map = {k: v for k, v in col_map.items() if k in df.columns}
            df.rename(columns=rename_map, inplace=True)

        df.columns = [c.lower() for c in df.columns]
        return df
