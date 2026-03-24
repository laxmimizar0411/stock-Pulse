from typing import Dict, Any


def compute_options_signal(derivatives_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Baseline options intelligence:
    - PCR bands
    - IV regime
    - simple strategy hint
    """
    pcr = float(derivatives_row.get("put_call_ratio_oi") or 1.0)
    iv = float(derivatives_row.get("iv_atm_pct") or 0.0)
    if pcr > 1.2:
        bias = "BULLISH"
    elif pcr < 0.7:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    if iv >= 25:
        iv_regime = "HIGH"
    elif iv >= 15:
        iv_regime = "MEDIUM"
    else:
        iv_regime = "LOW"

    strategy = "IRON_CONDOR" if bias == "NEUTRAL" and iv_regime == "HIGH" else "DIRECTIONAL_SPREAD"
    return {"bias": bias, "iv_regime": iv_regime, "strategy_hint": strategy}
