"""
Macro Features

Macro-economic feature transformations for the Indian market context.
All functions accept a dict of macro indicators and return Dict[str, float].

Expected keys in the input dict (missing keys handled gracefully):
    repo_rate_current, repo_rate_6m_ago,
    inr_usd_current, inr_usd_30d_ago,
    crude_oil_current, crude_oil_30d_ago,
    vix_current,
    fii_net_flows (list of daily net flows, most recent last),
    dii_net_flows (list of daily net flows, most recent last)
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


def _safe_get(data: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """Safely extract a numeric value from a dict."""
    val = data.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_get_list(data: Dict[str, Any], key: str) -> List[float]:
    """Safely extract a list of floats from a dict."""
    val = data.get(key)
    if not val or not isinstance(val, (list, tuple)):
        return []
    result = []
    for v in val:
        try:
            result.append(float(v))
        except (ValueError, TypeError):
            pass
    return result


def compute_repo_rate_change(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Repo rate change: current vs 6 months ago.

    Positive change = tightening, negative = easing.
    """
    result: Dict[str, float] = {}
    try:
        current = _safe_get(data, "repo_rate_current")
        prev = _safe_get(data, "repo_rate_6m_ago")

        result["repo_rate_current"] = round(float(current), 4)
        result["repo_rate_change_6m"] = round(float(current - prev), 4)

    except Exception:
        logger.exception("Error computing repo rate change")
        result["repo_rate_current"] = float("nan")
        result["repo_rate_change_6m"] = float("nan")
    return result


def compute_inr_usd_roc(data: Dict[str, Any]) -> Dict[str, float]:
    """
    INR/USD rate of change over 30 days.

    Positive = INR depreciation (negative for markets).
    """
    result: Dict[str, float] = {}
    try:
        current = _safe_get(data, "inr_usd_current")
        prev = _safe_get(data, "inr_usd_30d_ago")

        if prev > 0:
            roc = (current / prev - 1.0) * 100.0
            result["inr_usd_roc_30d"] = round(float(roc), 4)
        else:
            result["inr_usd_roc_30d"] = float("nan")

        result["inr_usd_current"] = round(float(current), 4)

    except Exception:
        logger.exception("Error computing INR/USD ROC")
        result["inr_usd_roc_30d"] = float("nan")
        result["inr_usd_current"] = float("nan")
    return result


def compute_crude_oil_roc(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Crude oil price rate of change over 30 days.

    Rising crude is generally negative for Indian equities.
    """
    result: Dict[str, float] = {}
    try:
        current = _safe_get(data, "crude_oil_current")
        prev = _safe_get(data, "crude_oil_30d_ago")

        if prev > 0:
            roc = (current / prev - 1.0) * 100.0
            result["crude_oil_roc_30d"] = round(float(roc), 4)
        else:
            result["crude_oil_roc_30d"] = float("nan")

        result["crude_oil_current"] = round(float(current), 4)

    except Exception:
        logger.exception("Error computing crude oil ROC")
        result["crude_oil_roc_30d"] = float("nan")
        result["crude_oil_current"] = float("nan")
    return result


def compute_vix_features(data: Dict[str, Any]) -> Dict[str, float]:
    """
    VIX level and regime classification.

    Regimes:
        0 = Low volatility (VIX < 15)
        1 = Normal (15 <= VIX <= 25)
        2 = High volatility (VIX > 25)
    """
    result: Dict[str, float] = {}
    try:
        vix = _safe_get(data, "vix_current")

        result["vix_level"] = round(float(vix), 4)

        if vix < 15.0:
            result["vix_regime"] = 0.0
        elif vix <= 25.0:
            result["vix_regime"] = 1.0
        else:
            result["vix_regime"] = 2.0

    except Exception:
        logger.exception("Error computing VIX features")
        result["vix_level"] = float("nan")
        result["vix_regime"] = float("nan")
    return result


def compute_fii_dii_flows(data: Dict[str, Any]) -> Dict[str, float]:
    """
    FII and DII cumulative net flows (7-day and 30-day).

    Also computes the FII/DII flow ratio to measure relative institutional
    activity.
    """
    result: Dict[str, float] = {}
    try:
        fii_flows = _safe_get_list(data, "fii_net_flows")
        dii_flows = _safe_get_list(data, "dii_net_flows")

        # FII flows
        if len(fii_flows) >= 7:
            result["fii_net_flow_7d"] = round(float(sum(fii_flows[-7:])), 4)
        else:
            result["fii_net_flow_7d"] = round(float(sum(fii_flows)), 4) if fii_flows else float("nan")

        if len(fii_flows) >= 30:
            result["fii_net_flow_30d"] = round(float(sum(fii_flows[-30:])), 4)
        else:
            result["fii_net_flow_30d"] = round(float(sum(fii_flows)), 4) if fii_flows else float("nan")

        # DII flows
        if len(dii_flows) >= 7:
            result["dii_net_flow_7d"] = round(float(sum(dii_flows[-7:])), 4)
        else:
            result["dii_net_flow_7d"] = round(float(sum(dii_flows)), 4) if dii_flows else float("nan")

        if len(dii_flows) >= 30:
            result["dii_net_flow_30d"] = round(float(sum(dii_flows[-30:])), 4)
        else:
            result["dii_net_flow_30d"] = round(float(sum(dii_flows)), 4) if dii_flows else float("nan")

        # FII/DII flow ratio (30d)
        fii_30d = result.get("fii_net_flow_30d", float("nan"))
        dii_30d = result.get("dii_net_flow_30d", float("nan"))

        if (
            not np.isnan(fii_30d)
            and not np.isnan(dii_30d)
            and dii_30d != 0
        ):
            result["fii_dii_flow_ratio"] = round(float(fii_30d / dii_30d), 4)
        else:
            result["fii_dii_flow_ratio"] = float("nan")

    except Exception:
        logger.exception("Error computing FII/DII flows")
        result["fii_net_flow_7d"] = float("nan")
        result["fii_net_flow_30d"] = float("nan")
        result["dii_net_flow_7d"] = float("nan")
        result["dii_net_flow_30d"] = float("nan")
        result["fii_dii_flow_ratio"] = float("nan")
    return result


def compute_crude_sector_correlation(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Pearson correlation between equity (sector or index) daily returns and
    daily crude price changes over a shared window.

    Precomputed by the data layer into:
        crude_sector_return_correlation: float
    or pass aligned series:
        equity_daily_returns: list[float], crude_daily_returns: list[float]
    """
    result: Dict[str, float] = {"crude_sector_return_correlation": float("nan")}
    try:
        pre = data.get("crude_sector_return_correlation")
        if pre is not None:
            result["crude_sector_return_correlation"] = round(float(pre), 4)
            return result

        eq = data.get("equity_daily_returns")
        cr = data.get("crude_daily_returns")
        if (
            not eq
            or not cr
            or not isinstance(eq, (list, tuple))
            or not isinstance(cr, (list, tuple))
        ):
            return result
        a = np.array([float(x) for x in eq], dtype=float)
        b = np.array([float(x) for x in cr], dtype=float)
        n = min(len(a), len(b))
        if n < 10:
            return result
        a = a[-n:]
        b = b[-n:]
        if np.std(a) < 1e-12 or np.std(b) < 1e-12:
            return result
        corr = float(np.corrcoef(a, b)[0, 1])
        if np.isnan(corr):
            return result
        result["crude_sector_return_correlation"] = round(corr, 4)
    except Exception:
        logger.exception("Error computing crude-sector correlation")
    return result


def compute_all_macro_features(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Compute all macro features in a single call.

    Args:
        data: Dict of macro indicator values.

    Returns:
        Dict of feature name -> value.
    """
    features: Dict[str, float] = {}

    computations = [
        compute_repo_rate_change,
        compute_inr_usd_roc,
        compute_crude_oil_roc,
        compute_vix_features,
        compute_fii_dii_flows,
        compute_crude_sector_correlation,
    ]

    for fn in computations:
        try:
            result = fn(data)
            features.update(result)
        except Exception:
            logger.exception("Error in macro feature: %s", fn.__name__)

    return features
