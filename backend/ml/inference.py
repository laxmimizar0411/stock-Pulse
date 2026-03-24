from typing import Any, Dict


def infer_direction(feature_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic baseline inference from feature snapshot.
    """
    rsi = float(feature_row.get("rsi_14") or 50.0)
    momentum = float(feature_row.get("return_10d_pct") or 0.0)
    if rsi < 35 and momentum > -3:
        direction = "UP"
        confidence = 0.67
    elif rsi > 70 and momentum < 2:
        direction = "DOWN"
        confidence = 0.64
    else:
        direction = "NEUTRAL"
        confidence = 0.54
    return {"direction": direction, "confidence": confidence}
