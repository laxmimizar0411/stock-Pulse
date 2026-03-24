from typing import Any, Dict, List


def train_baseline_model(rows: List[Dict[str, Any]], horizon_days: int = 5) -> Dict[str, float]:
    """
    Placeholder baseline trainer.
    Produces deterministic metrics so API and registry paths are stable.
    """
    sample_count = len(rows)
    # Naive score proxy; to be replaced with true walk-forward training
    accuracy = 0.5 if sample_count < 50 else min(0.74, 0.5 + (sample_count / 5000.0))
    f1 = max(0.0, accuracy - 0.06)
    return {
        "sample_count": float(sample_count),
        "horizon_days": float(horizon_days),
        "accuracy": round(accuracy, 4),
        "f1": round(f1, 4),
    }
