"""
Fundamental Features

Derived fundamental features from stock data dictionaries. These transform
raw financial statement data into quantitative signals for the ML models.

All functions accept a dict of fundamental metrics and return Dict[str, float].

Expected keys in the input dict (missing keys handled gracefully):
    net_income, total_assets, cfo (cash from operations), total_liabilities,
    current_assets, current_liabilities, shares_outstanding,
    shares_outstanding_prev, gross_profit, revenue, revenue_prev,
    gross_margin, gross_margin_prev, asset_turnover, asset_turnover_prev,
    roa, roa_prev, leverage_ratio, leverage_ratio_prev,
    current_ratio, current_ratio_prev, market_cap, ebit, retained_earnings,
    working_capital, total_debt, sales, margin_current, margin_3yr_avg,
    promoter_holding_current, promoter_holding_prev,
    fii_holding_current, fii_holding_prev,
    dii_holding_current, dii_holding_prev,
    revenue_growth_rates (list of annual growth rates),
    roce_values (list of 3 yearly ROCE values, oldest first),
    ebitda, interest_expense
"""

import logging
import math
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


def compute_piotroski_f_score(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Piotroski F-Score (0-9).

    Nine binary signals for financial strength:
    1. Positive net income
    2. Positive ROA
    3. Positive CFO
    4. CFO > Net Income (earnings quality)
    5. Lower leverage (long-term debt / total assets) vs prior year
    6. Higher current ratio vs prior year
    7. No dilution (shares outstanding not increased)
    8. Higher gross margin vs prior year
    9. Higher asset turnover vs prior year
    """
    result: Dict[str, float] = {}
    try:
        score = 0

        # 1. Positive net income
        net_income = _safe_get(data, "net_income")
        positive_net_income = 1 if net_income > 0 else 0
        score += positive_net_income

        # 2. Positive ROA
        roa = _safe_get(data, "roa")
        positive_roa = 1 if roa > 0 else 0
        score += positive_roa

        # 3. Positive CFO
        cfo = _safe_get(data, "cfo")
        positive_cfo = 1 if cfo > 0 else 0
        score += positive_cfo

        # 4. CFO > Net Income (accruals check)
        cfo_gt_ni = 1 if cfo > net_income else 0
        score += cfo_gt_ni

        # 5. Lower leverage
        leverage = _safe_get(data, "leverage_ratio")
        leverage_prev = _safe_get(data, "leverage_ratio_prev")
        lower_leverage = 1 if leverage < leverage_prev else 0
        score += lower_leverage

        # 6. Higher current ratio
        cr = _safe_get(data, "current_ratio")
        cr_prev = _safe_get(data, "current_ratio_prev")
        higher_cr = 1 if cr > cr_prev else 0
        score += higher_cr

        # 7. No dilution
        shares = _safe_get(data, "shares_outstanding")
        shares_prev = _safe_get(data, "shares_outstanding_prev")
        no_dilution = 1 if shares <= shares_prev or shares_prev == 0 else 0
        score += no_dilution

        # 8. Higher gross margin
        gm = _safe_get(data, "gross_margin")
        gm_prev = _safe_get(data, "gross_margin_prev")
        higher_gm = 1 if gm > gm_prev else 0
        score += higher_gm

        # 9. Higher asset turnover
        at = _safe_get(data, "asset_turnover")
        at_prev = _safe_get(data, "asset_turnover_prev")
        higher_at = 1 if at > at_prev else 0
        score += higher_at

        result["piotroski_f_score"] = float(score)

        # Also expose individual components
        result["piotroski_positive_net_income"] = float(positive_net_income)
        result["piotroski_positive_roa"] = float(positive_roa)
        result["piotroski_positive_cfo"] = float(positive_cfo)
        result["piotroski_cfo_gt_net_income"] = float(cfo_gt_ni)
        result["piotroski_lower_leverage"] = float(lower_leverage)
        result["piotroski_higher_current_ratio"] = float(higher_cr)
        result["piotroski_no_dilution"] = float(no_dilution)
        result["piotroski_higher_gross_margin"] = float(higher_gm)
        result["piotroski_higher_asset_turnover"] = float(higher_at)

    except Exception:
        logger.exception("Error computing Piotroski F-Score")
        result["piotroski_f_score"] = float("nan")
    return result


def compute_altman_z_score(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Altman Z-Score for bankruptcy prediction.

    Z = 1.2*(WC/TA) + 1.4*(RE/TA) + 3.3*(EBIT/TA) + 0.6*(MVE/TL) + 1.0*(Sales/TA)

    Interpretation:
        Z > 2.99: Safe zone
        1.81 < Z < 2.99: Grey zone
        Z < 1.81: Distress zone
    """
    result: Dict[str, float] = {}
    try:
        ta = _safe_get(data, "total_assets")
        if ta <= 0:
            result["altman_z_score"] = float("nan")
            result["altman_z_zone"] = float("nan")
            return result

        wc = _safe_get(data, "working_capital")
        re = _safe_get(data, "retained_earnings")
        ebit = _safe_get(data, "ebit")
        mve = _safe_get(data, "market_cap")
        tl = _safe_get(data, "total_liabilities")
        sales = _safe_get(data, "sales", _safe_get(data, "revenue"))

        z = (
            1.2 * (wc / ta)
            + 1.4 * (re / ta)
            + 3.3 * (ebit / ta)
            + (0.6 * (mve / tl) if tl > 0 else 0.0)
            + 1.0 * (sales / ta)
        )

        result["altman_z_score"] = round(float(z), 4)

        # Zone encoding: 0 = distress, 1 = grey, 2 = safe
        if z > 2.99:
            result["altman_z_zone"] = 2.0
        elif z > 1.81:
            result["altman_z_zone"] = 1.0
        else:
            result["altman_z_zone"] = 0.0

    except Exception:
        logger.exception("Error computing Altman Z-Score")
        result["altman_z_score"] = float("nan")
        result["altman_z_zone"] = float("nan")
    return result


def compute_earnings_quality(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Earnings quality ratio: CFO / Net Income.

    Values > 1.0 indicate high-quality earnings backed by cash flows.
    Values < 1.0 or negative suggest accrual-driven earnings.
    """
    result: Dict[str, float] = {}
    try:
        cfo = _safe_get(data, "cfo")
        ni = _safe_get(data, "net_income")

        if ni != 0:
            eq = cfo / ni
            result["earnings_quality"] = round(float(eq), 4)
        else:
            # If net income is zero, quality is undefined but CFO > 0 is good
            result["earnings_quality"] = float("nan") if cfo == 0 else float("inf") if cfo > 0 else float("-inf")

    except Exception:
        logger.exception("Error computing earnings quality")
        result["earnings_quality"] = float("nan")
    return result


def compute_margin_trajectory(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Margin trajectory: current margin vs 3-year average.

    Positive values indicate improving margins.
    """
    result: Dict[str, float] = {}
    try:
        current = _safe_get(data, "margin_current")
        avg_3yr = _safe_get(data, "margin_3yr_avg")

        if avg_3yr != 0:
            trajectory = (current - avg_3yr) / abs(avg_3yr) * 100.0
            result["margin_trajectory_pct"] = round(float(trajectory), 4)
        else:
            result["margin_trajectory_pct"] = float("nan")

        result["margin_current"] = round(float(current), 4)
        result["margin_3yr_avg"] = round(float(avg_3yr), 4)

    except Exception:
        logger.exception("Error computing margin trajectory")
        result["margin_trajectory_pct"] = float("nan")
        result["margin_current"] = float("nan")
        result["margin_3yr_avg"] = float("nan")
    return result


def compute_promoter_holding_change(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Promoter holding QoQ change.

    Falling promoter holding can be a negative signal.
    """
    result: Dict[str, float] = {}
    try:
        current = _safe_get(data, "promoter_holding_current")
        prev = _safe_get(data, "promoter_holding_prev")

        change = current - prev
        result["promoter_holding_current"] = round(float(current), 4)
        result["promoter_holding_change_qoq"] = round(float(change), 4)

    except Exception:
        logger.exception("Error computing promoter holding change")
        result["promoter_holding_current"] = float("nan")
        result["promoter_holding_change_qoq"] = float("nan")
    return result


def compute_institutional_holding_change(data: Dict[str, Any]) -> Dict[str, float]:
    """
    FII and DII holding QoQ change.

    Rising institutional holding is generally a positive signal.
    """
    result: Dict[str, float] = {}
    try:
        fii_current = _safe_get(data, "fii_holding_current")
        fii_prev = _safe_get(data, "fii_holding_prev")
        dii_current = _safe_get(data, "dii_holding_current")
        dii_prev = _safe_get(data, "dii_holding_prev")

        result["fii_holding_change_qoq"] = round(float(fii_current - fii_prev), 4)
        result["dii_holding_change_qoq"] = round(float(dii_current - dii_prev), 4)
        result["fii_holding_current"] = round(float(fii_current), 4)
        result["dii_holding_current"] = round(float(dii_current), 4)

    except Exception:
        logger.exception("Error computing institutional holding change")
        result["fii_holding_change_qoq"] = float("nan")
        result["dii_holding_change_qoq"] = float("nan")
        result["fii_holding_current"] = float("nan")
        result["dii_holding_current"] = float("nan")
    return result


def compute_revenue_growth_consistency(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Revenue growth consistency: standard deviation of annual growth rates.

    Lower std dev = more consistent growth (desirable).
    Also returns the mean growth rate.
    """
    result: Dict[str, float] = {}
    try:
        growth_rates = data.get("revenue_growth_rates")
        if not growth_rates or not isinstance(growth_rates, (list, tuple)):
            return {
                "revenue_growth_consistency": float("nan"),
                "revenue_growth_mean": float("nan"),
            }

        rates = [float(r) for r in growth_rates if r is not None]
        if len(rates) < 2:
            return {
                "revenue_growth_consistency": float("nan"),
                "revenue_growth_mean": round(float(rates[0]), 4) if rates else float("nan"),
            }

        arr = np.array(rates)
        result["revenue_growth_consistency"] = round(float(np.std(arr)), 4)
        result["revenue_growth_mean"] = round(float(np.mean(arr)), 4)

    except Exception:
        logger.exception("Error computing revenue growth consistency")
        result["revenue_growth_consistency"] = float("nan")
        result["revenue_growth_mean"] = float("nan")
    return result


def compute_beneish_m_score(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Beneish M-Score (8-variable model, Beneish 1999).

    M > -1.74 suggests higher earnings-manipulation risk (non-manipulators
    typically score below this threshold). Uses period t vs t-1 ratios.

    Expected keys (optional; missing components yield NaN for full score):
        revenue, revenue_prev, receivables, receivables_prev,
        gross_margin, gross_margin_prev (as ratios 0–1 if stored as %, pass /100),
        total_assets, total_assets_prev, current_assets, fixed_assets,
        current_assets_prev, fixed_assets_prev,
        long_term_debt, long_term_debt_prev, total_liabilities, total_liabilities_prev,
        depreciation, depreciation_prev, net_income, operating_cash_flow,
        operating_expense, operating_expense_prev (SG&A proxy),
    """
    result: Dict[str, float] = {"beneish_m_score": float("nan"), "beneish_manipulation_risk": float("nan")}

    def _ratio(num: float, den: float) -> float:
        if den == 0:
            return float("nan")
        return num / den

    try:
        sales = _safe_get(data, "revenue")
        sales_prev = _safe_get(data, "revenue_prev")
        rec = _safe_get(data, "receivables")
        rec_prev = _safe_get(data, "receivables_prev")
        ta = _safe_get(data, "total_assets")
        ta_prev = _safe_get(data, "total_assets_prev")
        ca = _safe_get(data, "current_assets")
        ppe = _safe_get(data, "fixed_assets")
        ca_prev = _safe_get(data, "current_assets_prev")
        ppe_prev = _safe_get(data, "fixed_assets_prev")
        ltd = _safe_get(data, "long_term_debt")
        ltd_prev = _safe_get(data, "long_term_debt_prev")
        tl = _safe_get(data, "total_liabilities")
        tl_prev = _safe_get(data, "total_liabilities_prev")
        dep = _safe_get(data, "depreciation")
        dep_prev = _safe_get(data, "depreciation_prev")
        ni = _safe_get(data, "net_income")
        cfo = _safe_get(data, "operating_cash_flow")
        gm = _safe_get(data, "gross_margin")
        gm_prev = _safe_get(data, "gross_margin_prev")
        opex = data.get("operating_expense")
        opex_prev = data.get("operating_expense_prev")

        # Gross margin as ratio if given as percentage
        if gm > 1.5:
            gm /= 100.0
        if gm_prev > 1.5:
            gm_prev /= 100.0

        dsri = _ratio(_ratio(rec, sales), _ratio(rec_prev, sales_prev)) if sales and sales_prev else float("nan")
        gmi = _ratio(gm_prev, gm) if gm and gm_prev else float("nan")

        aqi_cur = 1.0 - _ratio(ca + ppe, ta) if ta else float("nan")
        aqi_prev = 1.0 - _ratio(ca_prev + ppe_prev, ta_prev) if ta_prev else float("nan")
        aqi = _ratio(aqi_cur, aqi_prev) if not (np.isnan(aqi_cur) or np.isnan(aqi_prev)) else float("nan")

        sgi = _ratio(sales, sales_prev) if sales_prev else float("nan")

        dep_rate = _ratio(dep, dep + ppe) if (dep + ppe) else float("nan")
        dep_rate_prev = _ratio(dep_prev, dep_prev + ppe_prev) if (dep_prev + ppe_prev) else float("nan")
        depi = _ratio(dep_rate_prev, dep_rate) if dep_rate and dep_rate_prev else float("nan")

        if (
            opex is None
            or opex_prev is None
            or sales <= 0
            or sales_prev <= 0
        ):
            sgai = float("nan")
        else:
            sgai = _ratio(_ratio(float(opex_prev), sales_prev), _ratio(float(opex), sales))

        tata = _ratio(ni - cfo, ta) if ta else float("nan")

        lvgi = _ratio(_ratio(ltd + tl, ta), _ratio(ltd_prev + tl_prev, ta_prev)) if ta and ta_prev else float("nan")

        components = [dsri, gmi, aqi, sgi, depi, sgai, tata, lvgi]
        if any(np.isnan(c) for c in components):
            return result

        m = (
            -4.84
            + 0.92 * dsri
            + 0.528 * gmi
            + 0.404 * aqi
            + 0.892 * sgi
            + 0.115 * depi
            - 0.172 * sgai
            + 4.679 * tata
            - 0.327 * lvgi
        )
        result["beneish_m_score"] = round(float(m), 4)
        result["beneish_manipulation_risk"] = 1.0 if m > -1.74 else 0.0
    except Exception:
        logger.exception("Error computing Beneish M-Score")
    return result


def compute_roce_trend(data: Dict[str, Any]) -> Dict[str, float]:
    """
    ROCE trend over 3 years.

    Returns the latest ROCE, the 3-year average, and the trend direction
    (slope of linear fit, normalized).
    """
    result: Dict[str, float] = {}
    try:
        roce_values = data.get("roce_values")
        if not roce_values or not isinstance(roce_values, (list, tuple)):
            return {
                "roce_latest": float("nan"),
                "roce_3yr_avg": float("nan"),
                "roce_trend": float("nan"),
            }

        values = [float(v) for v in roce_values if v is not None]
        if not values:
            return {
                "roce_latest": float("nan"),
                "roce_3yr_avg": float("nan"),
                "roce_trend": float("nan"),
            }

        result["roce_latest"] = round(float(values[-1]), 4)
        result["roce_3yr_avg"] = round(float(np.mean(values)), 4)

        if len(values) >= 2:
            # Simple linear regression slope
            x = np.arange(len(values), dtype=float)
            y = np.array(values, dtype=float)
            slope = float(np.polyfit(x, y, 1)[0])
            result["roce_trend"] = round(slope, 4)
        else:
            result["roce_trend"] = 0.0

    except Exception:
        logger.exception("Error computing ROCE trend")
        result["roce_latest"] = float("nan")
        result["roce_3yr_avg"] = float("nan")
        result["roce_trend"] = float("nan")
    return result


def compute_all_fundamental_features(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Compute all fundamental features in a single call.

    Args:
        data: Dict of fundamental metrics for a stock.

    Returns:
        Dict of feature name -> value.
    """
    features: Dict[str, float] = {}

    computations = [
        compute_piotroski_f_score,
        compute_altman_z_score,
        compute_beneish_m_score,
        compute_earnings_quality,
        compute_margin_trajectory,
        compute_promoter_holding_change,
        compute_institutional_holding_change,
        compute_revenue_growth_consistency,
        compute_roce_trend,
    ]

    for fn in computations:
        try:
            result = fn(data)
            features.update(result)
        except Exception:
            logger.exception("Error in fundamental feature: %s", fn.__name__)

    return features
