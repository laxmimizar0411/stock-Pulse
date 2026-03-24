"""
Cross-Sectional Features

Relative and cross-sectional features that compare a stock against
its benchmark (NIFTY 50) and sector peers.

Functions accept price data + market data and return Dict[str, float].

Expected market_data dict keys:
    nifty_prices: list of floats (close prices, oldest first, aligned dates)
    sector_returns: dict mapping symbol -> 20d return for sector peers
    sector_avg_delivery_pct: float (sector average delivery %)
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_relative_strength_vs_nifty(
    price_data: pd.DataFrame,
    market_data: Dict[str, Any],
    period: int = 20,
) -> Dict[str, float]:
    """
    Relative strength vs NIFTY 50 over the given period.

    RS = (stock_return / nifty_return) where both are period-day returns.
    Values > 1 mean stock outperformed NIFTY.
    """
    result: Dict[str, float] = {}
    try:
        nifty_prices = market_data.get("nifty_prices")
        if nifty_prices is None or len(nifty_prices) <= period:
            return {"relative_strength_vs_nifty": float("nan")}

        close = price_data["close"].values
        if len(close) <= period:
            return {"relative_strength_vs_nifty": float("nan")}

        nifty = np.array(nifty_prices, dtype=float)

        stock_ret = (close[-1] / close[-period - 1] - 1.0) if close[-period - 1] != 0 else 0.0
        nifty_ret = (nifty[-1] / nifty[-period - 1] - 1.0) if nifty[-period - 1] != 0 else 0.0

        if nifty_ret != 0:
            rs = stock_ret / nifty_ret
        elif stock_ret > 0:
            rs = float("inf")
        elif stock_ret < 0:
            rs = float("-inf")
        else:
            rs = 1.0

        # Clamp extreme values
        rs = max(-10.0, min(10.0, rs))
        result["relative_strength_vs_nifty"] = round(float(rs), 4)

    except Exception:
        logger.exception("Error computing relative strength vs NIFTY")
        result["relative_strength_vs_nifty"] = float("nan")
    return result


def compute_rolling_beta(
    price_data: pd.DataFrame,
    market_data: Dict[str, Any],
    period: int = 60,
) -> Dict[str, float]:
    """
    Rolling beta vs NIFTY 50 over the given period (default 60 days).

    Beta = Cov(stock, market) / Var(market) using daily returns.
    """
    result: Dict[str, float] = {}
    try:
        nifty_prices = market_data.get("nifty_prices")
        if nifty_prices is None or len(nifty_prices) < period + 1:
            return {"rolling_beta_60d": float("nan")}

        close = price_data["close"].values
        if len(close) < period + 1:
            return {"rolling_beta_60d": float("nan")}

        nifty = np.array(nifty_prices, dtype=float)

        # Daily returns for the last `period` days
        stock_returns = np.diff(close[-period - 1:]) / close[-period - 1:-1]
        nifty_returns = np.diff(nifty[-period - 1:]) / nifty[-period - 1:-1]

        # Handle zero denominators
        stock_returns = np.nan_to_num(stock_returns, nan=0.0)
        nifty_returns = np.nan_to_num(nifty_returns, nan=0.0)

        var_market = np.var(nifty_returns)
        if var_market > 0:
            cov = np.cov(stock_returns, nifty_returns)[0, 1]
            beta = cov / var_market
        else:
            beta = 1.0

        result["rolling_beta_60d"] = round(float(beta), 4)

    except Exception:
        logger.exception("Error computing rolling beta")
        result["rolling_beta_60d"] = float("nan")
    return result


def compute_sector_momentum_rank(
    price_data: pd.DataFrame,
    market_data: Dict[str, Any],
    symbol: str = "",
) -> Dict[str, float]:
    """
    Sector momentum rank (normalized 0-1).

    Compares this stock's 20d return against sector peers.
    1.0 = best in sector, 0.0 = worst.
    """
    result: Dict[str, float] = {}
    try:
        sector_returns = market_data.get("sector_returns")
        if not sector_returns or not isinstance(sector_returns, dict):
            return {"sector_momentum_rank": float("nan")}

        close = price_data["close"].values
        if len(close) <= 20:
            return {"sector_momentum_rank": float("nan")}

        stock_ret = (close[-1] / close[-21] - 1.0) * 100.0 if close[-21] != 0 else 0.0

        # Gather all sector returns
        all_returns = list(sector_returns.values())
        if symbol and symbol not in sector_returns:
            all_returns.append(stock_ret)

        if len(all_returns) < 2:
            return {"sector_momentum_rank": float("nan")}

        sorted_returns = sorted(all_returns)
        rank = sorted_returns.index(
            min(sorted_returns, key=lambda x: abs(x - stock_ret))
        )
        normalized = rank / (len(sorted_returns) - 1) if len(sorted_returns) > 1 else 0.5

        result["sector_momentum_rank"] = round(float(normalized), 4)

    except Exception:
        logger.exception("Error computing sector momentum rank")
        result["sector_momentum_rank"] = float("nan")
    return result


def compute_volume_ratio(price_data: pd.DataFrame) -> Dict[str, float]:
    """
    Volume ratio vs 20-day average.

    Values > 1.0 indicate above-average volume (potential breakout/breakdown).
    """
    result: Dict[str, float] = {}
    try:
        volume = price_data["volume"].values.astype(float)

        if len(volume) < 20:
            return {"volume_ratio_vs_20d_avg": float("nan")}

        avg_20d = np.mean(volume[-20:])
        current = volume[-1]

        if avg_20d > 0:
            ratio = current / avg_20d
        else:
            ratio = 1.0

        result["volume_ratio_vs_20d_avg"] = round(float(ratio), 4)

    except Exception:
        logger.exception("Error computing volume ratio")
        result["volume_ratio_vs_20d_avg"] = float("nan")
    return result


def compute_52w_range_position(price_data: pd.DataFrame) -> Dict[str, float]:
    """
    Price distance from 52-week high and low as percentages.

    distance_from_52w_high: negative % (how far below the high)
    distance_from_52w_low: positive % (how far above the low)
    """
    result: Dict[str, float] = {}
    try:
        close = price_data["close"].values

        # 252 trading days ~ 1 year
        lookback = min(252, len(close))
        if lookback < 20:
            return {
                "price_distance_from_52w_high_pct": float("nan"),
                "price_distance_from_52w_low_pct": float("nan"),
            }

        window = close[-lookback:]
        high_52w = np.max(window)
        low_52w = np.min(window)
        current = close[-1]

        if high_52w > 0:
            dist_high = (current / high_52w - 1.0) * 100.0
        else:
            dist_high = 0.0

        if low_52w > 0:
            dist_low = (current / low_52w - 1.0) * 100.0
        else:
            dist_low = 0.0

        result["price_distance_from_52w_high_pct"] = round(float(dist_high), 4)
        result["price_distance_from_52w_low_pct"] = round(float(dist_low), 4)

    except Exception:
        logger.exception("Error computing 52-week range position")
        result["price_distance_from_52w_high_pct"] = float("nan")
        result["price_distance_from_52w_low_pct"] = float("nan")
    return result


def compute_delivery_pct_vs_sector(
    price_data: pd.DataFrame,
    market_data: Dict[str, Any],
) -> Dict[str, float]:
    """
    Delivery percentage vs sector average.

    Values > 1.0 indicate higher-than-sector-average delivery (stronger conviction).
    """
    result: Dict[str, float] = {}
    try:
        if "delivery_pct" not in price_data.columns:
            return {"delivery_pct_vs_sector_avg": float("nan")}

        dpct = price_data["delivery_pct"].dropna()
        if len(dpct) == 0:
            return {"delivery_pct_vs_sector_avg": float("nan")}

        sector_avg = market_data.get("sector_avg_delivery_pct")
        if sector_avg is None or float(sector_avg) <= 0:
            return {"delivery_pct_vs_sector_avg": float("nan")}

        current_dpct = float(dpct.iloc[-1])
        ratio = current_dpct / float(sector_avg)

        result["delivery_pct_vs_sector_avg"] = round(float(ratio), 4)

    except Exception:
        logger.exception("Error computing delivery pct vs sector")
        result["delivery_pct_vs_sector_avg"] = float("nan")
    return result


def compute_all_cross_sectional_features(
    price_data: pd.DataFrame,
    market_data: Dict[str, Any],
    symbol: str = "",
) -> Dict[str, float]:
    """
    Compute all cross-sectional features in a single call.

    Args:
        price_data: OHLCV DataFrame sorted by date ascending.
        market_data: Dict with market-wide data (nifty_prices, sector_returns, etc.).
        symbol: Stock ticker for sector ranking.

    Returns:
        Dict of feature name -> value.
    """
    features: Dict[str, float] = {}

    try:
        features.update(compute_relative_strength_vs_nifty(price_data, market_data))
    except Exception:
        logger.exception("Error in relative strength computation")

    try:
        features.update(compute_rolling_beta(price_data, market_data))
    except Exception:
        logger.exception("Error in rolling beta computation")

    try:
        features.update(compute_sector_momentum_rank(price_data, market_data, symbol))
    except Exception:
        logger.exception("Error in sector momentum rank computation")

    try:
        features.update(compute_volume_ratio(price_data))
    except Exception:
        logger.exception("Error in volume ratio computation")

    try:
        features.update(compute_52w_range_position(price_data))
    except Exception:
        logger.exception("Error in 52w range computation")

    try:
        features.update(compute_delivery_pct_vs_sector(price_data, market_data))
    except Exception:
        logger.exception("Error in delivery pct vs sector computation")

    return features
