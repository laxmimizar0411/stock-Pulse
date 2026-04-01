"""
Performance Metrics Suite for Backtesting.

Comprehensive metrics:
- CAGR, Sharpe, Sortino, Calmar, Omega, Information Ratio
- Profit Factor, R-Multiple, Expectancy
- Max DD, Max DD Duration, Ulcer Index
- Monthly/yearly return tables
"""

import logging
import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("brain.backtesting.performance_metrics")


def compute_full_metrics(
    equity_curve: np.ndarray,
    benchmark_curve: Optional[np.ndarray] = None,
    risk_free_rate: float = 0.06,
    periods_per_year: int = 252,
) -> Dict[str, Any]:
    """
    Compute comprehensive performance metrics.

    Args:
        equity_curve: Portfolio equity values.
        benchmark_curve: Benchmark equity values (for IR, alpha, beta).
        risk_free_rate: Annual risk-free rate (6% for India).
        periods_per_year: Trading days per year.
    """
    if len(equity_curve) < 2:
        return {"error": "Insufficient data"}

    returns = np.diff(equity_curve) / equity_curve[:-1]
    returns = returns[~np.isnan(returns) & ~np.isinf(returns)]
    n = len(returns)
    years = n / periods_per_year

    rf_daily = risk_free_rate / periods_per_year
    excess = returns - rf_daily

    # === Return metrics ===
    total_return = (equity_curve[-1] / equity_curve[0] - 1) * 100
    cagr = ((equity_curve[-1] / equity_curve[0]) ** (1 / years) - 1) * 100 if years > 0 else 0

    # Annualized volatility
    ann_vol = np.std(returns) * np.sqrt(periods_per_year) * 100

    # === Risk-adjusted metrics ===
    sharpe = np.mean(excess) / np.std(excess) * np.sqrt(periods_per_year) if np.std(excess) > 0 else 0

    downside = excess[excess < 0]
    sortino = np.mean(excess) / np.std(downside) * np.sqrt(periods_per_year) if len(downside) > 0 and np.std(downside) > 0 else 0

    # === Drawdown metrics ===
    peak = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - peak) / peak
    max_dd = np.min(drawdown) * 100

    calmar = cagr / abs(max_dd) if abs(max_dd) > 0 else 0

    # Max DD duration
    dd_durations = []
    in_dd = False
    dd_start = 0
    for i in range(len(drawdown)):
        if drawdown[i] < 0 and not in_dd:
            in_dd = True
            dd_start = i
        elif drawdown[i] >= 0 and in_dd:
            in_dd = False
            dd_durations.append(i - dd_start)
    if in_dd:
        dd_durations.append(len(drawdown) - dd_start)
    max_dd_duration = max(dd_durations) if dd_durations else 0

    # Ulcer Index
    ulcer_index = np.sqrt(np.mean(drawdown ** 2)) * 100

    # Omega Ratio (threshold = 0)
    threshold = 0
    above = returns[returns > threshold] - threshold
    below = threshold - returns[returns <= threshold]
    omega = np.sum(above) / np.sum(below) if np.sum(below) > 0 else float('inf')

    # === Benchmark-relative metrics ===
    info_ratio = 0
    alpha = 0
    beta = 0
    if benchmark_curve is not None and len(benchmark_curve) == len(equity_curve):
        bench_returns = np.diff(benchmark_curve) / benchmark_curve[:-1]
        bench_returns = bench_returns[:n]
        tracking_error = np.std(returns - bench_returns)
        info_ratio = np.mean(returns - bench_returns) / tracking_error * np.sqrt(periods_per_year) if tracking_error > 0 else 0

        cov = np.cov(returns, bench_returns)
        beta = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 0
        alpha = (np.mean(returns) - rf_daily - beta * (np.mean(bench_returns) - rf_daily)) * periods_per_year * 100

    # === Distribution metrics ===
    skewness = float(pd.Series(returns).skew())
    kurtosis = float(pd.Series(returns).kurtosis())
    var_95 = float(np.percentile(returns, 5)) * 100
    cvar_95 = float(np.mean(returns[returns <= np.percentile(returns, 5)])) * 100 if len(returns[returns <= np.percentile(returns, 5)]) > 0 else 0

    return {
        "total_return_pct": round(total_return, 4),
        "cagr_pct": round(cagr, 4),
        "annualized_volatility_pct": round(ann_vol, 4),
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "calmar_ratio": round(calmar, 4),
        "omega_ratio": round(omega, 4) if not math.isinf(omega) else None,
        "information_ratio": round(info_ratio, 4),
        "alpha_pct": round(alpha, 4),
        "beta": round(beta, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "max_dd_duration_days": max_dd_duration,
        "ulcer_index": round(ulcer_index, 4),
        "var_95_pct": round(var_95, 4),
        "cvar_95_pct": round(cvar_95, 4),
        "skewness": round(skewness, 4),
        "kurtosis": round(kurtosis, 4),
        "risk_free_rate": risk_free_rate,
        "trading_days": n,
        "years": round(years, 2),
    }


def compute_trade_metrics(trades: List[Dict]) -> Dict[str, Any]:
    """Compute trade-level statistics."""
    if not trades:
        return {"total_trades": 0}

    pnl = [t.get("pnl_pct", 0) for t in trades]
    winners = [p for p in pnl if p > 0]
    losers = [p for p in pnl if p < 0]
    hold_days = [t.get("hold_days", 0) for t in trades]

    win_rate = len(winners) / len(pnl) * 100 if pnl else 0
    avg_win = np.mean(winners) if winners else 0
    avg_loss = np.mean(losers) if losers else 0
    profit_factor = abs(sum(winners) / sum(losers)) if sum(losers) != 0 else None

    # Expectancy
    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss) if pnl else 0

    # R-Multiple (average win / average loss)
    r_multiple = abs(avg_win / avg_loss) if avg_loss != 0 else None

    # Consecutive wins/losses
    max_consec_wins = max_consec_losses = cur_wins = cur_losses = 0
    for p in pnl:
        if p > 0:
            cur_wins += 1
            cur_losses = 0
            max_consec_wins = max(max_consec_wins, cur_wins)
        else:
            cur_losses += 1
            cur_wins = 0
            max_consec_losses = max(max_consec_losses, cur_losses)

    return {
        "total_trades": len(pnl),
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "win_rate_pct": round(win_rate, 2),
        "avg_win_pct": round(avg_win, 4),
        "avg_loss_pct": round(avg_loss, 4),
        "best_trade_pct": round(max(pnl), 4) if pnl else 0,
        "worst_trade_pct": round(min(pnl), 4) if pnl else 0,
        "profit_factor": round(profit_factor, 4) if profit_factor and not math.isinf(profit_factor) else None,
        "expectancy_pct": round(expectancy, 4),
        "r_multiple": round(r_multiple, 4) if r_multiple and not math.isinf(r_multiple) else None,
        "avg_hold_days": round(np.mean(hold_days), 1) if hold_days else 0,
        "max_hold_days": max(hold_days) if hold_days else 0,
        "max_consecutive_wins": max_consec_wins,
        "max_consecutive_losses": max_consec_losses,
    }
