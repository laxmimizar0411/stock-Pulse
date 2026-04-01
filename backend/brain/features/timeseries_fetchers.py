"""
Async data fetchers wiring TimeSeriesStore into FeaturePipeline.

Builds OHLCV DataFrames, fundamental dicts, macro dicts, and market context
(including crude vs equity return correlation) from PostgreSQL.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _rows_to_ohlcv_df(rows: List[Dict[str, Any]]) -> Optional[pd.DataFrame]:
    """Convert prices_daily rows (newest-first) to ascending OHLCV DataFrame."""
    if not rows:
        return None
    rows = list(reversed(rows))
    df = pd.DataFrame(
        {
            "date": [r["date"] for r in rows],
            "open": [float(r.get("open") or 0) for r in rows],
            "high": [float(r.get("high") or 0) for r in rows],
            "low": [float(r.get("low") or 0) for r in rows],
            "close": [float(r.get("close") or 0) for r in rows],
            "volume": [float(r.get("volume") or 0) for r in rows],
        }
    )
    if df["close"].isna().all() or (df["close"] <= 0).all():
        return None
    return df


def _align_crude_equity_returns(
    macro_asc: List[Dict[str, Any]],
    price_asc: List[Dict[str, Any]],
    window: int = 60,
) -> Optional[float]:
    """Pearson correlation: equity daily returns vs crude daily % changes."""
    if len(macro_asc) < window + 2 or len(price_asc) < window + 2:
        return None
    crude_by_d: Dict[date, float] = {}
    for r in macro_asc:
        d = r.get("date")
        c = r.get("crude_brent_price")
        if d is not None and c is not None:
            crude_by_d[d if isinstance(d, date) else pd.Timestamp(d).date()] = float(c)

    eq_by_d: Dict[date, float] = {}
    for r in price_asc:
        d = r.get("date")
        cl = r.get("close")
        if d is not None and cl is not None:
            eq_by_d[d if isinstance(d, date) else pd.Timestamp(d).date()] = float(cl)

    common = sorted(set(crude_by_d.keys()) & set(eq_by_d.keys()))
    if len(common) < window + 2:
        return None
    common = common[-(window + 2) :]
    cr = [crude_by_d[d] for d in common]
    eq = [eq_by_d[d] for d in common]
    crude_rets = np.diff(cr) / np.clip(cr[:-1], 1e-8, None)
    eq_rets = np.diff(eq) / np.clip(eq[:-1], 1e-8, None)
    n = min(len(crude_rets), len(eq_rets))
    if n < window:
        return None
    a = crude_rets[-window:]
    b = eq_rets[-window:]
    if np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return None
    corr = float(np.corrcoef(a, b)[0, 1])
    return None if np.isnan(corr) else corr


def _fundamental_dict_from_rows(
    rows: List[Dict[str, Any]],
    share_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Map fundamentals_quarterly + shareholding rows to FeaturePipeline dict."""
    if not rows:
        return {}
    cur = rows[0]
    prev = rows[1] if len(rows) > 1 else {}

    def fnum(r: Dict, k: str, default: float = 0.0) -> float:
        v = r.get(k)
        if v is None:
            return default
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    rev = fnum(cur, "revenue")
    gp = fnum(cur, "gross_profit")
    op = fnum(cur, "operating_profit")
    rev_p = fnum(prev, "revenue")
    gp_p = fnum(prev, "gross_profit")
    op_p = fnum(prev, "operating_profit")

    opex = None
    if gp and op is not None:
        opex = gp - op
    opex_prev = None
    if gp_p and op_p is not None:
        opex_prev = gp_p - op_p

    data: Dict[str, Any] = {
        "net_income": fnum(cur, "net_profit"),
        "total_assets": fnum(cur, "total_assets"),
        "cfo": fnum(cur, "operating_cash_flow"),
        "current_assets": fnum(cur, "current_assets"),
        "current_liabilities": fnum(cur, "current_liabilities"),
        "gross_profit": gp,
        "revenue": rev,
        "gross_margin": fnum(cur, "gross_margin"),
        "asset_turnover": fnum(cur, "asset_turnover"),
        "leverage_ratio": fnum(cur, "long_term_debt") / fnum(cur, "total_assets")
        if fnum(cur, "total_assets")
        else 0.0,
        "current_ratio": fnum(cur, "current_ratio"),
        "shares_outstanding": 0.0,
        "shares_outstanding_prev": 0.0,
        "roa": fnum(cur, "roa"),
        "ebit": fnum(cur, "ebit"),
        "retained_earnings": fnum(cur, "reserves_and_surplus"),
        "market_cap": 0.0,
        "total_liabilities": fnum(cur, "total_debt"),
        "sales": rev,
        "margin_current": fnum(cur, "gross_margin"),
        "margin_3yr_avg": fnum(cur, "gross_margin"),
        "ebitda": fnum(cur, "ebitda"),
        "interest_expense": fnum(cur, "interest_expense"),
        "receivables": fnum(cur, "receivables"),
        "fixed_assets": fnum(cur, "fixed_assets"),
        "depreciation": fnum(cur, "depreciation"),
        "long_term_debt": fnum(cur, "long_term_debt"),
        "revenue_prev": rev_p,
        "receivables_prev": fnum(prev, "receivables"),
        "gross_margin_prev": fnum(prev, "gross_margin"),
        "total_assets_prev": fnum(prev, "total_assets"),
        "current_assets_prev": fnum(prev, "current_assets"),
        "fixed_assets_prev": fnum(prev, "fixed_assets"),
        "long_term_debt_prev": fnum(prev, "long_term_debt"),
        "total_liabilities_prev": fnum(prev, "total_debt"),
        "depreciation_prev": fnum(prev, "depreciation"),
    }
    if opex is not None:
        data["operating_expense"] = opex
    if opex_prev is not None:
        data["operating_expense_prev"] = opex_prev

    if prev:
        data["leverage_ratio_prev"] = (
            fnum(prev, "long_term_debt") / fnum(prev, "total_assets")
            if fnum(prev, "total_assets")
            else 0.0
        )
        data["current_ratio_prev"] = fnum(prev, "current_ratio")
        data["asset_turnover_prev"] = fnum(prev, "asset_turnover")
    else:
        data["leverage_ratio_prev"] = data["leverage_ratio"]
        data["current_ratio_prev"] = data["current_ratio"]
        data["asset_turnover_prev"] = data["asset_turnover"]

    if share_rows:
        sh0 = share_rows[0]
        sh1 = share_rows[1] if len(share_rows) > 1 else {}
        data["promoter_holding_current"] = fnum(sh0, "promoter_holding")
        data["promoter_holding_prev"] = fnum(sh1, "promoter_holding")
        data["fii_holding_current"] = fnum(sh0, "fii_holding")
        data["fii_holding_prev"] = fnum(sh1, "fii_holding")
        data["dii_holding_current"] = fnum(sh0, "dii_holding")
        data["dii_holding_prev"] = fnum(sh1, "dii_holding")
    else:
        data["promoter_holding_current"] = 0.0
        data["promoter_holding_prev"] = 0.0
        data["fii_holding_current"] = 0.0
        data["fii_holding_prev"] = 0.0
        data["dii_holding_current"] = 0.0
        data["dii_holding_prev"] = 0.0

    rg = cur.get("revenue_growth_yoy")
    if rg is not None:
        data["revenue_growth_rates"] = [float(rg)]
    return data


def build_timeseries_fetchers(ts_store: Any) -> Tuple[
    Callable[[str], Coroutine[Any, Any, Optional[pd.DataFrame]]],
    Callable[[str], Coroutine[Any, Any, Dict[str, Any]]],
    Callable[[], Coroutine[Any, Any, Dict[str, Any]]],
    Callable[[str], Coroutine[Any, Any, Dict[str, Any]]],
]:
    """
    Return (price_fetcher, fundamental_fetcher, macro_fetcher, market_fetcher)
    closures bound to ``ts_store``.
    """

    async def price_fetcher(symbol: str) -> Optional[pd.DataFrame]:
        rows = await ts_store.get_prices(symbol.upper(), limit=400)
        return _rows_to_ohlcv_df(rows)

    async def fundamental_fetcher(symbol: str) -> Dict[str, Any]:
        sym = symbol.upper()
        funds = await ts_store.get_fundamentals(sym, limit=4)
        sh = await ts_store.get_shareholding(sym, limit=4)
        return _fundamental_dict_from_rows(funds, sh)

    async def macro_fetcher() -> Dict[str, Any]:
        macro_desc = await ts_store.get_macro_indicators(limit=200)
        macro_asc = list(reversed(macro_desc))
        if not macro_asc:
            return {}

        latest = macro_asc[-1]
        idx_30 = max(0, len(macro_asc) - 31)
        idx_126 = max(0, len(macro_asc) - 127)

        def gv(row: Dict, key: str) -> float:
            v = row.get(key)
            if v is None:
                return 0.0
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0

        data: Dict[str, Any] = {
            "repo_rate_current": gv(latest, "rbi_repo_rate"),
            "repo_rate_6m_ago": gv(macro_asc[idx_126], "rbi_repo_rate"),
            "inr_usd_current": gv(latest, "usdinr_rate"),
            "inr_usd_30d_ago": gv(macro_asc[idx_30], "usdinr_rate"),
            "crude_oil_current": gv(latest, "crude_brent_price"),
            "crude_oil_30d_ago": gv(macro_asc[idx_30], "crude_brent_price"),
            "vix_current": 18.0,
            "fii_net_flows": [],
            "dii_net_flows": [],
        }

        bench_rows: List[Dict[str, Any]] = []
        for bsym in ("NIFTY", "^NSEI", "RELIANCE"):
            pr = await ts_store.get_prices(bsym, limit=220)
            if pr and len(pr) >= 80:
                bench_rows = list(reversed(pr))
                break
        if bench_rows:
            corr = _align_crude_equity_returns(macro_asc, bench_rows, window=60)
            if corr is not None:
                data["crude_sector_return_correlation"] = corr

        return data

    async def market_fetcher(symbol: str) -> Dict[str, Any]:
        sym = symbol.upper()
        nifty_prices: List[float] = []
        for bsym in ("NIFTY", "^NSEI", "RELIANCE"):
            pr = await ts_store.get_prices(bsym, limit=320)
            if pr and len(pr) >= 60:
                asc = list(reversed(pr))
                nifty_prices = [float(r["close"]) for r in asc]
                break

        val = await ts_store.get_valuation(sym, limit=1)
        sector_avg_dp = None
        if val:
            sector_avg_dp = val[0].get("sector_performance")

        return {
            "nifty_prices": nifty_prices,
            "sector_returns": {},
            "sector_avg_delivery_pct": sector_avg_dp,
        }

    return price_fetcher, fundamental_fetcher, macro_fetcher, market_fetcher
