"""
Technical Features

Extended technical indicators computed from OHLCV price data.
All functions accept a pandas DataFrame with columns:
    date, open, high, low, close, volume
sorted by date ascending, and return Dict[str, float] for the latest period.

These complement the existing TechnicalCalculator (RSI, MACD, Bollinger, SMA,
EMA) with additional indicators needed by the Brain's ML models.
"""

import logging
import math
from typing import Dict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_atr(df: pd.DataFrame, period: int = 14) -> Dict[str, float]:
    """Average True Range (14-period)."""
    result: Dict[str, float] = {}
    try:
        if len(df) < period + 1:
            return {"atr_14": float("nan")}

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values

        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )

        # Wilder's smoothing
        atr = np.mean(tr[:period])
        for i in range(period, len(tr)):
            atr = (atr * (period - 1) + tr[i]) / period

        result["atr_14"] = round(float(atr), 4)
    except Exception:
        logger.exception("Error computing ATR")
        result["atr_14"] = float("nan")
    return result


def compute_obv(df: pd.DataFrame) -> Dict[str, float]:
    """On Balance Volume."""
    result: Dict[str, float] = {}
    try:
        if len(df) < 2:
            return {"obv": float("nan")}

        close = df["close"].values
        volume = df["volume"].values

        obv = np.zeros(len(close))
        for i in range(1, len(close)):
            if close[i] > close[i - 1]:
                obv[i] = obv[i - 1] + volume[i]
            elif close[i] < close[i - 1]:
                obv[i] = obv[i - 1] - volume[i]
            else:
                obv[i] = obv[i - 1]

        result["obv"] = float(obv[-1])
        # OBV slope (normalized) over last 10 periods
        if len(obv) >= 10:
            obv_recent = obv[-10:]
            slope = (obv_recent[-1] - obv_recent[0]) / max(abs(obv_recent[0]), 1.0)
            result["obv_slope_10d"] = round(float(slope), 6)
        else:
            result["obv_slope_10d"] = float("nan")

    except Exception:
        logger.exception("Error computing OBV")
        result["obv"] = float("nan")
        result["obv_slope_10d"] = float("nan")
    return result


def compute_vwap_proxy(df: pd.DataFrame) -> Dict[str, float]:
    """
    VWAP proxy for daily data.

    For daily bars, compute cumulative VWAP = cumsum(close * volume) / cumsum(volume)
    and return the latest value plus the price-to-VWAP ratio.
    """
    result: Dict[str, float] = {}
    try:
        if len(df) < 1:
            return {"vwap": float("nan"), "price_vs_vwap_pct": float("nan")}

        close = df["close"].values
        volume = df["volume"].values.astype(float)

        # Use the last 20 bars for a rolling VWAP window
        window = min(20, len(df))
        c = close[-window:]
        v = volume[-window:]

        cum_vol = np.cumsum(v)
        cum_pv = np.cumsum(c * v)

        # Avoid division by zero
        if cum_vol[-1] > 0:
            vwap = cum_pv[-1] / cum_vol[-1]
        else:
            vwap = close[-1]

        result["vwap"] = round(float(vwap), 4)
        if vwap > 0:
            result["price_vs_vwap_pct"] = round(
                (float(close[-1]) / vwap - 1.0) * 100.0, 4
            )
        else:
            result["price_vs_vwap_pct"] = float("nan")

    except Exception:
        logger.exception("Error computing VWAP proxy")
        result["vwap"] = float("nan")
        result["price_vs_vwap_pct"] = float("nan")
    return result


def compute_adx(df: pd.DataFrame, period: int = 14) -> Dict[str, float]:
    """
    Average Directional Index (14-period).

    Returns ADX value plus +DI and -DI for trend strength and direction.
    """
    result: Dict[str, float] = {}
    try:
        n = len(df)
        if n < 2 * period + 1:
            return {
                "adx_14": float("nan"),
                "plus_di": float("nan"),
                "minus_di": float("nan"),
            }

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values

        plus_dm = np.zeros(n - 1)
        minus_dm = np.zeros(n - 1)
        tr = np.zeros(n - 1)

        for i in range(1, n):
            idx = i - 1
            up_move = high[i] - high[i - 1]
            down_move = low[i - 1] - low[i]

            plus_dm[idx] = max(up_move, 0.0) if up_move > down_move else 0.0
            minus_dm[idx] = max(down_move, 0.0) if down_move > up_move else 0.0

            tr[idx] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )

        # Wilder's smoothing
        atr_s = np.mean(tr[:period])
        plus_di_s = np.mean(plus_dm[:period])
        minus_di_s = np.mean(minus_dm[:period])

        dx_values = []
        latest_plus_di = 0.0
        latest_minus_di = 0.0

        for i in range(period, len(tr)):
            atr_s = (atr_s * (period - 1) + tr[i]) / period
            plus_di_s = (plus_di_s * (period - 1) + plus_dm[i]) / period
            minus_di_s = (minus_di_s * (period - 1) + minus_dm[i]) / period

            if atr_s > 0:
                latest_plus_di = (plus_di_s / atr_s) * 100
                latest_minus_di = (minus_di_s / atr_s) * 100
            else:
                latest_plus_di = 0.0
                latest_minus_di = 0.0

            di_sum = latest_plus_di + latest_minus_di
            if di_sum > 0:
                dx = abs(latest_plus_di - latest_minus_di) / di_sum * 100
                dx_values.append(dx)

        if len(dx_values) < period:
            return {
                "adx_14": float("nan"),
                "plus_di": float("nan"),
                "minus_di": float("nan"),
            }

        adx = np.mean(dx_values[:period])
        for dx in dx_values[period:]:
            adx = (adx * (period - 1) + dx) / period

        result["adx_14"] = round(float(adx), 4)
        result["plus_di"] = round(float(latest_plus_di), 4)
        result["minus_di"] = round(float(latest_minus_di), 4)

    except Exception:
        logger.exception("Error computing ADX")
        result["adx_14"] = float("nan")
        result["plus_di"] = float("nan")
        result["minus_di"] = float("nan")
    return result


def compute_stochastic(
    df: pd.DataFrame, k_period: int = 14, d_period: int = 3, smooth_k: int = 3
) -> Dict[str, float]:
    """Stochastic %K and %D (14, 3, 3)."""
    result: Dict[str, float] = {}
    try:
        if len(df) < k_period + smooth_k + d_period:
            return {"stoch_k": float("nan"), "stoch_d": float("nan")}

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values

        # Raw %K
        raw_k = np.full(len(close), np.nan)
        for i in range(k_period - 1, len(close)):
            h = np.max(high[i - k_period + 1: i + 1])
            l = np.min(low[i - k_period + 1: i + 1])
            if h != l:
                raw_k[i] = (close[i] - l) / (h - l) * 100.0
            else:
                raw_k[i] = 50.0

        # Smooth %K (SMA of raw %K)
        valid_k = raw_k[~np.isnan(raw_k)]
        if len(valid_k) < smooth_k:
            return {"stoch_k": float("nan"), "stoch_d": float("nan")}

        smooth_k_values = np.convolve(
            valid_k, np.ones(smooth_k) / smooth_k, mode="valid"
        )

        # %D (SMA of smooth %K)
        if len(smooth_k_values) < d_period:
            return {"stoch_k": float("nan"), "stoch_d": float("nan")}

        d_values = np.convolve(
            smooth_k_values, np.ones(d_period) / d_period, mode="valid"
        )

        result["stoch_k"] = round(float(smooth_k_values[-1]), 4)
        result["stoch_d"] = round(float(d_values[-1]), 4)

    except Exception:
        logger.exception("Error computing Stochastic")
        result["stoch_k"] = float("nan")
        result["stoch_d"] = float("nan")
    return result


def compute_williams_r(df: pd.DataFrame, period: int = 14) -> Dict[str, float]:
    """Williams %R (14-period)."""
    result: Dict[str, float] = {}
    try:
        if len(df) < period:
            return {"williams_r": float("nan")}

        high = df["high"].values[-period:]
        low = df["low"].values[-period:]
        close = df["close"].values[-1]

        highest = np.max(high)
        lowest = np.min(low)

        if highest != lowest:
            wr = (highest - close) / (highest - lowest) * -100.0
        else:
            wr = -50.0

        result["williams_r"] = round(float(wr), 4)

    except Exception:
        logger.exception("Error computing Williams %%R")
        result["williams_r"] = float("nan")
    return result


def compute_cci(df: pd.DataFrame, period: int = 20) -> Dict[str, float]:
    """Commodity Channel Index (20-period)."""
    result: Dict[str, float] = {}
    try:
        if len(df) < period:
            return {"cci_20": float("nan")}

        high = df["high"].values[-period:]
        low = df["low"].values[-period:]
        close = df["close"].values[-period:]

        tp = (high + low + close) / 3.0
        tp_mean = np.mean(tp)
        mean_dev = np.mean(np.abs(tp - tp_mean))

        if mean_dev > 0:
            cci = (tp[-1] - tp_mean) / (0.015 * mean_dev)
        else:
            cci = 0.0

        result["cci_20"] = round(float(cci), 4)

    except Exception:
        logger.exception("Error computing CCI")
        result["cci_20"] = float("nan")
    return result


def compute_ichimoku(
    df: pd.DataFrame, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52
) -> Dict[str, float]:
    """
    Ichimoku Cloud components.

    Returns tenkan_sen, kijun_sen, and price_vs_cloud (positive = above cloud).
    """
    result: Dict[str, float] = {}
    try:
        if len(df) < senkou_b:
            return {
                "ichimoku_tenkan": float("nan"),
                "ichimoku_kijun": float("nan"),
                "ichimoku_price_vs_cloud": float("nan"),
            }

        high = df["high"].values
        low = df["low"].values
        close_last = float(df["close"].values[-1])

        # Tenkan-sen (conversion line)
        tenkan_high = np.max(high[-tenkan:])
        tenkan_low = np.min(low[-tenkan:])
        tenkan_sen = (tenkan_high + tenkan_low) / 2.0

        # Kijun-sen (base line)
        kijun_high = np.max(high[-kijun:])
        kijun_low = np.min(low[-kijun:])
        kijun_sen = (kijun_high + kijun_low) / 2.0

        # Senkou Span A (leading span A) — average of tenkan & kijun
        senkou_a = (tenkan_sen + kijun_sen) / 2.0

        # Senkou Span B (leading span B)
        senkou_b_high = np.max(high[-senkou_b:])
        senkou_b_low = np.min(low[-senkou_b:])
        senkou_span_b = (senkou_b_high + senkou_b_low) / 2.0

        # Cloud top and bottom
        cloud_top = max(senkou_a, senkou_span_b)
        cloud_bottom = min(senkou_a, senkou_span_b)

        # Price vs cloud: percentage distance from nearest cloud boundary
        if close_last > cloud_top:
            price_vs_cloud = (close_last - cloud_top) / cloud_top * 100.0
        elif close_last < cloud_bottom:
            price_vs_cloud = (close_last - cloud_bottom) / cloud_bottom * 100.0
        else:
            # Inside cloud: express as fraction from bottom (-50 to +50 range)
            cloud_width = cloud_top - cloud_bottom
            if cloud_width > 0:
                price_vs_cloud = (
                    (close_last - cloud_bottom) / cloud_width - 0.5
                ) * 100.0
            else:
                price_vs_cloud = 0.0

        result["ichimoku_tenkan"] = round(float(tenkan_sen), 4)
        result["ichimoku_kijun"] = round(float(kijun_sen), 4)
        result["ichimoku_price_vs_cloud"] = round(float(price_vs_cloud), 4)

    except Exception:
        logger.exception("Error computing Ichimoku")
        result["ichimoku_tenkan"] = float("nan")
        result["ichimoku_kijun"] = float("nan")
        result["ichimoku_price_vs_cloud"] = float("nan")
    return result


def compute_roc(df: pd.DataFrame) -> Dict[str, float]:
    """Rate of Change (10-day and 20-day)."""
    result: Dict[str, float] = {}
    try:
        close = df["close"].values

        for period, key in [(10, "roc_10"), (20, "roc_20")]:
            if len(close) > period and close[-period - 1] != 0:
                roc = (close[-1] / close[-period - 1] - 1.0) * 100.0
                result[key] = round(float(roc), 4)
            else:
                result[key] = float("nan")

    except Exception:
        logger.exception("Error computing ROC")
        result["roc_10"] = float("nan")
        result["roc_20"] = float("nan")
    return result


def compute_mfi(df: pd.DataFrame, period: int = 14) -> Dict[str, float]:
    """Money Flow Index (14-period)."""
    result: Dict[str, float] = {}
    try:
        if len(df) < period + 1:
            return {"mfi_14": float("nan")}

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        volume = df["volume"].values.astype(float)

        tp = (high + low + close) / 3.0
        raw_mf = tp * volume

        positive_mf = 0.0
        negative_mf = 0.0

        # Look at the last `period` changes
        start = len(tp) - period
        for i in range(start, len(tp)):
            if tp[i] > tp[i - 1]:
                positive_mf += raw_mf[i]
            elif tp[i] < tp[i - 1]:
                negative_mf += raw_mf[i]

        if negative_mf > 0:
            mfr = positive_mf / negative_mf
            mfi = 100.0 - (100.0 / (1.0 + mfr))
        elif positive_mf > 0:
            mfi = 100.0
        else:
            mfi = 50.0

        result["mfi_14"] = round(float(mfi), 4)

    except Exception:
        logger.exception("Error computing MFI")
        result["mfi_14"] = float("nan")
    return result


def compute_delivery_pct(df: pd.DataFrame) -> Dict[str, float]:
    """
    Delivery percentage ratio.

    Expects an optional 'delivery_pct' column in the DataFrame.
    Returns latest value and its 20-day average for comparison.
    """
    result: Dict[str, float] = {}
    try:
        if "delivery_pct" not in df.columns:
            return {
                "delivery_pct": float("nan"),
                "delivery_pct_20d_avg": float("nan"),
            }

        dpct = df["delivery_pct"].dropna()
        if len(dpct) == 0:
            return {
                "delivery_pct": float("nan"),
                "delivery_pct_20d_avg": float("nan"),
            }

        result["delivery_pct"] = round(float(dpct.iloc[-1]), 4)

        if len(dpct) >= 20:
            result["delivery_pct_20d_avg"] = round(float(dpct.iloc[-20:].mean()), 4)
        else:
            result["delivery_pct_20d_avg"] = round(float(dpct.mean()), 4)

    except Exception:
        logger.exception("Error computing delivery percentage")
        result["delivery_pct"] = float("nan")
        result["delivery_pct_20d_avg"] = float("nan")
    return result


def _compute_rsi_series(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Compute full RSI series. Returns array of same length (NaN-padded)."""
    rsi = np.full(len(close), np.nan)
    if len(close) < period + 1:
        return rsi

    changes = np.diff(close)
    gains = np.where(changes > 0, changes, 0.0)
    losses = np.where(changes < 0, -changes, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def _frac_diff_weights(d: float, max_k: int = 200) -> np.ndarray:
    """Fixed-width fractional differentiation weights (López de Prado)."""
    w = [1.0]
    for k in range(1, max_k):
        w_next = -w[-1] * (d - k + 1) / k
        if abs(w_next) < 1e-5:
            break
        w.append(w_next)
    return np.array(w[::-1], dtype=float)


def compute_fractional_diff_log_close(
    df: pd.DataFrame, d: float = 0.4, width: int = 20
) -> Dict[str, float]:
    """
    Fractional differentiation of log(close) to reduce memory while preserving
    long-range dependence. Returns the latest filtered value.
    """
    result: Dict[str, float] = {"frac_diff_log_close": float("nan")}
    try:
        if len(df) < width + 5:
            return result
        close = df["close"].astype(float).values
        if np.any(close <= 0):
            return result
        log_p = np.log(close)
        w = _frac_diff_weights(d, max_k=width)
        if len(w) < 3:
            return result
        # Convolution: value at t uses log_p[t - len(w) + 1 : t + 1]
        series = np.full(len(log_p), np.nan)
        for t in range(len(w) - 1, len(log_p)):
            window = log_p[t - len(w) + 1 : t + 1]
            series[t] = float(np.dot(w, window))
        val = series[-1]
        if np.isnan(val):
            return result
        result["frac_diff_log_close"] = round(float(val), 6)
    except Exception:
        logger.exception("Error computing fractional diff log close")
    return result


def compute_rsi_divergence(df: pd.DataFrame, lookback: int = 20) -> Dict[str, float]:
    """
    RSI divergence signal.

    Bearish divergence: price making new high but RSI not (signal = -1).
    Bullish divergence: price making new low but RSI not (signal = +1).
    No divergence: signal = 0.
    """
    result: Dict[str, float] = {}
    try:
        if len(df) < lookback + 14:
            return {"rsi_divergence": 0.0}

        close = df["close"].values
        rsi = _compute_rsi_series(close, 14)

        recent_close = close[-lookback:]
        recent_rsi = rsi[-lookback:]

        # Check if latest close is at or near the high of lookback window
        price_at_high = close[-1] >= np.nanmax(recent_close) * 0.99
        price_at_low = close[-1] <= np.nanmin(recent_close) * 1.01

        # Check RSI position
        valid_rsi = recent_rsi[~np.isnan(recent_rsi)]
        if len(valid_rsi) < 5:
            return {"rsi_divergence": 0.0}

        rsi_at_high = rsi[-1] >= np.max(valid_rsi) * 0.99 if not np.isnan(rsi[-1]) else False
        rsi_at_low = rsi[-1] <= np.min(valid_rsi) * 1.01 if not np.isnan(rsi[-1]) else False

        divergence = 0.0
        if price_at_high and not rsi_at_high:
            divergence = -1.0  # Bearish divergence
        elif price_at_low and not rsi_at_low:
            divergence = 1.0   # Bullish divergence

        result["rsi_divergence"] = divergence

    except Exception:
        logger.exception("Error computing RSI divergence")
        result["rsi_divergence"] = 0.0
    return result


def compute_all_technical_features(df: pd.DataFrame) -> Dict[str, float]:
    """
    Compute all technical features in a single call.

    This is a convenience function that aggregates results from all
    individual technical feature functions.

    Args:
        df: OHLCV DataFrame with columns: date, open, high, low, close, volume.
            Sorted by date ascending.

    Returns:
        Dict of feature name -> value for the latest period.
    """
    features: Dict[str, float] = {}

    computations = [
        compute_atr,
        compute_obv,
        compute_vwap_proxy,
        compute_adx,
        compute_stochastic,
        compute_williams_r,
        compute_cci,
        compute_ichimoku,
        compute_roc,
        compute_mfi,
        compute_delivery_pct,
        compute_fractional_diff_log_close,
        compute_rsi_divergence,
    ]

    for fn in computations:
        try:
            result = fn(df)
            features.update(result)
        except Exception:
            logger.exception("Error in technical feature computation: %s", fn.__name__)

    return features
