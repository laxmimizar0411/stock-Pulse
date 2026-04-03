"""SHAP + LIME Explainability Engine — Phase 3.10

Provides model-agnostic explainability:
1. SHAP (SHapley Additive exPlanations) — feature importance with direction
2. LIME (Local Interpretable Model-agnostic Explanations) — local surrogate
3. Natural Language Explanations — human-readable reasoning via Gemini LLM
4. Feature contribution waterfall visualization data

Works with XGBoost, LightGBM, and any sklearn-compatible model.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ExplainabilityResult:
    """Result of model explainability analysis."""
    symbol: str
    model_name: str
    prediction: str = ""  # "BUY", "SELL", "HOLD"
    confidence: float = 0.0

    # SHAP results
    shap_values: Dict[str, float] = field(default_factory=dict)
    shap_base_value: float = 0.0
    top_positive_features: List[Dict[str, Any]] = field(default_factory=list)
    top_negative_features: List[Dict[str, Any]] = field(default_factory=list)

    # LIME results
    lime_weights: Dict[str, float] = field(default_factory=dict)

    # Natural language explanation
    nl_explanation: str = ""

    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "model_name": self.model_name,
            "prediction": self.prediction,
            "confidence": round(self.confidence, 4),
            "shap": {
                "values": {k: round(v, 6) for k, v in self.shap_values.items()},
                "base_value": round(self.shap_base_value, 6),
                "top_positive": self.top_positive_features[:5],
                "top_negative": self.top_negative_features[:5],
            },
            "lime": {
                "weights": {k: round(v, 6) for k, v in self.lime_weights.items()},
            },
            "nl_explanation": self.nl_explanation,
            "computed_at": self.computed_at.isoformat(),
        }


class ExplainabilityEngine:
    """SHAP + LIME + NL explainability for ML models."""

    def __init__(self, llm_fn=None):
        self._llm_fn = llm_fn  # Gemini LLM function for NL explanations
        self._stats = {"explanations": 0}

    def explain_prediction(
        self,
        symbol: str,
        model: Any,
        model_name: str,
        features: np.ndarray,
        feature_names: List[str],
        prediction: str = "",
        confidence: float = 0.0,
    ) -> ExplainabilityResult:
        """Generate SHAP-based explanation for a model prediction."""
        result = ExplainabilityResult(
            symbol=symbol,
            model_name=model_name,
            prediction=prediction,
            confidence=confidence,
        )

        try:
            import shap

            # SHAP TreeExplainer for tree-based models
            explainer = shap.TreeExplainer(model)
            shap_values_raw = explainer.shap_values(features.reshape(1, -1))

            # Handle multi-class output
            if isinstance(shap_values_raw, list):
                sv = shap_values_raw[1] if len(shap_values_raw) > 1 else shap_values_raw[0]
            else:
                sv = shap_values_raw

            sv = sv.flatten()

            # Map to feature names
            shap_dict = {}
            for i, name in enumerate(feature_names):
                if i < len(sv):
                    shap_dict[name] = float(sv[i])

            result.shap_values = shap_dict
            result.shap_base_value = float(
                explainer.expected_value[1]
                if isinstance(explainer.expected_value, (list, np.ndarray)) and len(explainer.expected_value) > 1
                else float(explainer.expected_value) if not isinstance(explainer.expected_value, (list, np.ndarray))
                else float(explainer.expected_value[0])
            )

            # Top positive and negative
            sorted_features = sorted(shap_dict.items(), key=lambda x: x[1], reverse=True)
            result.top_positive_features = [
                {"feature": name, "shap_value": round(val, 6), "direction": "positive"}
                for name, val in sorted_features if val > 0
            ][:5]
            result.top_negative_features = [
                {"feature": name, "shap_value": round(val, 6), "direction": "negative"}
                for name, val in sorted_features[::-1] if val < 0
            ][:5]

        except Exception as e:
            logger.warning(f"SHAP explanation failed for {symbol}: {e}")
            # Fallback: use feature importance from model
            try:
                if hasattr(model, 'feature_importances_'):
                    imp = model.feature_importances_
                    for i, name in enumerate(feature_names):
                        if i < len(imp):
                            result.shap_values[name] = float(imp[i])
            except Exception:
                pass

        # LIME explanation (simplified)
        try:
            self._lime_explain(result, model, features, feature_names)
        except Exception as e:
            logger.debug(f"LIME fallback for {symbol}: {e}")

        self._stats["explanations"] += 1
        return result

    def _lime_explain(
        self,
        result: ExplainabilityResult,
        model: Any,
        features: np.ndarray,
        feature_names: List[str],
    ):
        """Simple LIME-like local perturbation explanation."""
        n_samples = 100
        rng = np.random.default_rng(42)

        # Generate perturbed samples
        X_perturbed = np.tile(features, (n_samples, 1))
        noise = rng.normal(0, 0.1, X_perturbed.shape)
        X_perturbed += noise * np.abs(features)

        # Get predictions for perturbed samples
        try:
            if hasattr(model, 'predict_proba'):
                preds = model.predict_proba(X_perturbed)[:, 1]
            else:
                preds = model.predict(X_perturbed)

            # Simple linear regression to get feature weights
            from numpy.linalg import lstsq
            # Normalize
            X_norm = (X_perturbed - X_perturbed.mean(axis=0)) / (X_perturbed.std(axis=0) + 1e-10)
            weights, _, _, _ = lstsq(X_norm, preds, rcond=None)

            for i, name in enumerate(feature_names):
                if i < len(weights):
                    result.lime_weights[name] = float(weights[i])
        except Exception:
            pass

    async def generate_nl_explanation(
        self,
        result: ExplainabilityResult,
    ) -> str:
        """Generate natural language explanation using LLM."""
        if not self._llm_fn:
            return self._generate_rule_based_explanation(result)

        try:
            top_pos = ", ".join(
                f"{f['feature']} (+{f['shap_value']:.4f})"
                for f in result.top_positive_features[:3]
            )
            top_neg = ", ".join(
                f"{f['feature']} ({f['shap_value']:.4f})"
                for f in result.top_negative_features[:3]
            )

            prompt = f"""Explain this stock prediction in simple terms for an Indian retail investor:

Stock: {result.symbol}
Prediction: {result.prediction} (Confidence: {result.confidence:.0%})
Model: {result.model_name}

Top factors pushing BUY: {top_pos}
Top factors pushing SELL: {top_neg}

Provide a 3-4 sentence explanation in plain English."""

            explanation = await self._llm_fn(prompt)
            result.nl_explanation = explanation
            return explanation

        except Exception as e:
            logger.warning(f"LLM explanation failed: {e}")
            return self._generate_rule_based_explanation(result)

    def _generate_rule_based_explanation(self, result: ExplainabilityResult) -> str:
        """Generate a simple rule-based explanation."""
        pos = result.top_positive_features[:3]
        neg = result.top_negative_features[:3]

        parts = [f"The model predicts {result.prediction} for {result.symbol} "
                 f"with {result.confidence:.0%} confidence."]

        if pos:
            factors = ", ".join(f["feature"] for f in pos)
            parts.append(f"Key bullish factors: {factors}.")
        if neg:
            factors = ", ".join(f["feature"] for f in neg)
            parts.append(f"Key bearish factors: {factors}.")

        explanation = " ".join(parts)
        result.nl_explanation = explanation
        return explanation

    def get_stats(self) -> Dict[str, Any]:
        return self._stats
