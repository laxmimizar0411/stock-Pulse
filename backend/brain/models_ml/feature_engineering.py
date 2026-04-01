"""
Feature Engineering Pipeline for ML Models.

Prepares raw features for model training:
1. Missing value handling (forward-fill, median imputation)
2. Log transformation for skewed features
3. Scaling (StandardScaler / RobustScaler)
4. Correlation filtering (remove >0.95 correlated pairs)
5. Target variable creation (forward returns)

Designed for swing-trading: creates 5d, 10d, 20d forward return targets.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("brain.models_ml.feature_engineering")

try:
    from sklearn.preprocessing import StandardScaler, RobustScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


def create_target_labels(prices: pd.Series, horizon: int = 5,
                         up_threshold: float = 0.01,
                         down_threshold: float = -0.01) -> pd.Series:
    """
    Create direction labels from price series.

    Args:
        prices: Close prices series.
        horizon: Forward-looking period in days.
        up_threshold: Return above this = UP (default 1%).
        down_threshold: Return below this = DOWN (default -1%).

    Returns:
        Series with labels: 2=UP, 1=NEUTRAL, 0=DOWN
    """
    forward_returns = prices.pct_change(horizon).shift(-horizon)

    labels = pd.Series(1, index=prices.index, dtype=int)  # NEUTRAL default
    labels[forward_returns > up_threshold] = 2  # UP
    labels[forward_returns < down_threshold] = 0  # DOWN

    return labels


def create_regression_target(prices: pd.Series, horizon: int = 5) -> pd.Series:
    """Create forward return regression target."""
    return prices.pct_change(horizon).shift(-horizon) * 100  # Percentage return


def prepare_features(
    features_dict: Dict[str, Any],
    feature_names: Optional[List[str]] = None,
) -> Tuple[np.ndarray, List[str]]:
    """
    Convert feature dictionary to numpy array for model input.

    Returns:
        (feature_array, feature_names)
    """
    if feature_names is None:
        feature_names = sorted(features_dict.keys())

    values = []
    valid_names = []
    for name in feature_names:
        val = features_dict.get(name)
        if val is not None and not (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
            values.append(float(val))
            valid_names.append(name)
        else:
            values.append(0.0)  # Impute missing with 0
            valid_names.append(name)

    return np.array(values).reshape(1, -1), valid_names


def build_training_dataset(
    price_df: pd.DataFrame,
    features_over_time: Dict[str, Dict[str, float]],
    horizon: int = 5,
    up_threshold: float = 0.01,
    down_threshold: float = -0.01,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Build a training dataset from historical price data and features.

    Args:
        price_df: DataFrame with 'date' and 'close' columns.
        features_over_time: Dict mapping date_str -> features_dict.
        horizon: Forward-looking period for target.

    Returns:
        (X, y, feature_names) where X has shape (n_samples, n_features).
    """
    if price_df is None or price_df.empty:
        return np.array([]), np.array([]), []

    price_df = price_df.sort_values("date").reset_index(drop=True)
    closes = price_df["close"].values

    # Create labels
    labels = create_target_labels(
        pd.Series(closes),
        horizon=horizon,
        up_threshold=up_threshold,
        down_threshold=down_threshold,
    )

    # If we have time-varying features, align them
    if features_over_time:
        dates = price_df["date"].astype(str).tolist()
        all_feature_names = set()
        for feat_dict in features_over_time.values():
            all_feature_names.update(feat_dict.keys())
        feature_names = sorted(all_feature_names)

        X_rows = []
        y_rows = []
        for i, date_str in enumerate(dates):
            if date_str in features_over_time and not np.isnan(labels.iloc[i]):
                row, _ = prepare_features(features_over_time[date_str], feature_names)
                X_rows.append(row.flatten())
                y_rows.append(int(labels.iloc[i]))

        if X_rows:
            return np.array(X_rows), np.array(y_rows), feature_names

    # Fallback: Use price-based features only
    feature_names, X, y = _build_price_features(price_df, labels)
    return X, y, feature_names


def _build_price_features(
    df: pd.DataFrame,
    labels: pd.Series,
) -> Tuple[List[str], np.ndarray, np.ndarray]:
    """
    Build features purely from price/volume data.
    Used when pre-computed features aren't available.
    """
    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    volumes = df["volume"].values

    n = len(closes)
    features = {}

    # Returns
    returns_1d = np.zeros(n)
    returns_1d[1:] = (closes[1:] - closes[:-1]) / closes[:-1]
    features["return_1d"] = returns_1d

    returns_5d = np.zeros(n)
    returns_5d[5:] = (closes[5:] - closes[:-5]) / closes[:-5]
    features["return_5d"] = returns_5d

    returns_20d = np.zeros(n)
    returns_20d[20:] = (closes[20:] - closes[:-20]) / closes[:-20]
    features["return_20d"] = returns_20d

    # Volatility (20-day rolling std of returns)
    vol = pd.Series(returns_1d).rolling(20).std().values
    features["volatility_20d"] = np.nan_to_num(vol)

    # RSI(14)
    features["rsi_14"] = _compute_rsi(closes, 14)

    # MACD
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = ema12 - ema26
    macd_signal = _ema(macd_line, 9)
    features["macd_histogram"] = macd_line - macd_signal

    # Bollinger position
    sma20 = pd.Series(closes).rolling(20).mean().values
    std20 = pd.Series(closes).rolling(20).std().values
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20
    bb_width = np.where(sma20 > 0, (bb_upper - bb_lower) / sma20, 0)
    bb_pos = np.where(bb_upper - bb_lower > 0, (closes - bb_lower) / (bb_upper - bb_lower), 0.5)
    features["bb_width"] = np.nan_to_num(bb_width)
    features["bb_position"] = np.nan_to_num(bb_pos)

    # ATR(14)
    features["atr_14"] = _compute_atr(highs, lows, closes, 14)

    # Volume ratio
    vol_sma = pd.Series(volumes.astype(float)).rolling(20).mean().values
    vol_ratio = np.where(vol_sma > 0, volumes / vol_sma, 1.0)
    features["volume_ratio"] = np.nan_to_num(vol_ratio)

    # OBV direction
    obv = np.zeros(n)
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            obv[i] = obv[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            obv[i] = obv[i - 1] - volumes[i]
        else:
            obv[i] = obv[i - 1]
    obv_sma = pd.Series(obv).rolling(20).mean().values
    features["obv_trend"] = np.nan_to_num(np.where(obv_sma != 0, (obv - obv_sma) / np.abs(obv_sma + 1e-10), 0))

    # Moving average alignment
    sma50 = pd.Series(closes).rolling(50).mean().values
    sma200 = pd.Series(closes).rolling(200).mean().values
    features["ma_alignment"] = np.nan_to_num(np.where(sma200 > 0, (sma50 - sma200) / sma200, 0))

    # Price momentum rank (position in 52-week range)
    high_252 = pd.Series(highs).rolling(252).max().values
    low_252 = pd.Series(lows).rolling(252).min().values
    rng = high_252 - low_252
    features["price_position_52w"] = np.nan_to_num(np.where(rng > 0, (closes - low_252) / rng, 0.5))

    # Body ratio (candle body / range)
    candle_range = highs - lows
    body = np.abs(closes - opens)
    features["body_ratio"] = np.nan_to_num(np.where(candle_range > 0, body / candle_range, 0))

    # Build matrix
    feature_names = sorted(features.keys())
    X_rows = []
    y_rows = []

    start_idx = 200  # Need 200 bars for SMA200
    for i in range(start_idx, n):
        if np.isnan(labels.iloc[i]):
            continue
        row = [features[name][i] for name in feature_names]
        if any(np.isnan(row)) or any(np.isinf(row)):
            continue
        X_rows.append(row)
        y_rows.append(int(labels.iloc[i]))

    return feature_names, np.array(X_rows), np.array(y_rows)


def _compute_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Compute RSI."""
    n = len(closes)
    rsi = np.full(n, 50.0)
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average."""
    result = np.zeros_like(data, dtype=float)
    result[0] = data[0]
    multiplier = 2.0 / (period + 1)
    for i in range(1, len(data)):
        result[i] = data[i] * multiplier + result[i - 1] * (1 - multiplier)
    return result


def _compute_atr(highs, lows, closes, period=14):
    """Compute ATR."""
    n = len(closes)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    atr = pd.Series(tr).rolling(period).mean().values
    return np.nan_to_num(atr)


def filter_correlated_features(
    X: np.ndarray,
    feature_names: List[str],
    threshold: float = 0.95,
) -> Tuple[np.ndarray, List[str]]:
    """Remove features with correlation above threshold."""
    if len(feature_names) < 2:
        return X, feature_names

    corr = np.corrcoef(X.T)
    to_drop = set()

    for i in range(len(feature_names)):
        if i in to_drop:
            continue
        for j in range(i + 1, len(feature_names)):
            if j in to_drop:
                continue
            if abs(corr[i, j]) > threshold:
                to_drop.add(j)

    keep = [i for i in range(len(feature_names)) if i not in to_drop]
    return X[:, keep], [feature_names[i] for i in keep]
