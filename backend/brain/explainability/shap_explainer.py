"""
SHAP Explainability Engine

Provides SHAP-based explanations for ML model predictions,
translating feature attributions into natural language.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False
    logger.info("shap library not available; using fallback feature importance")


class ShapExplainer:
    """
    Generates SHAP-based explanations for model predictions.
    Falls back to model feature importance if SHAP is unavailable.
    """

    # Human-readable feature name mapping
    FEATURE_NAMES = {
        "rsi_14": "RSI (14-day)",
        "macd_histogram": "MACD Histogram",
        "price_vs_sma50_pct": "Price vs 50-day SMA",
        "price_vs_sma200_pct": "Price vs 200-day SMA",
        "bollinger_pct_b": "Bollinger Band Position",
        "atr_14": "Average True Range",
        "adx_14": "ADX Trend Strength",
        "volume_zscore": "Volume Z-Score",
        "roc_10": "Rate of Change (10-day)",
        "mfi_14": "Money Flow Index",
        "roe": "Return on Equity",
        "revenue_growth_yoy": "Revenue Growth (YoY)",
        "debt_to_equity": "Debt-to-Equity Ratio",
        "pe_ratio": "P/E Ratio",
        "net_profit_margin": "Net Profit Margin",
        "promoter_holding": "Promoter Holding %",
        "piotroski_f_score": "Piotroski F-Score",
        "altman_z_score": "Altman Z-Score",
        "vix_level": "India VIX",
        "fii_net_flow_7d": "FII Net Flow (7-day)",
        "crude_oil_roc_30d": "Crude Oil Change (30-day)",
        "inr_usd_roc_30d": "INR/USD Change (30-day)",
        "relative_strength_vs_nifty": "Relative Strength vs NIFTY",
        "rolling_beta_60d": "Beta (60-day)",
        "delivery_pct": "Delivery %",
        "realized_volatility_20d": "Realized Volatility (20-day)",
    }

    def __init__(self):
        self._explainer = None
        self._model = None

    def set_model(self, model, X_background=None):
        """
        Set the model to explain.

        Args:
            model: A trained model with predict/predict_proba method
            X_background: Background dataset for SHAP (100-500 samples)
        """
        self._model = model

        if SHAP_AVAILABLE and X_background is not None:
            try:
                if hasattr(model, 'predict_proba'):
                    self._explainer = shap.TreeExplainer(model)
                else:
                    self._explainer = shap.KernelExplainer(
                        model.predict, X_background[:100]
                    )
                logger.info("SHAP explainer initialized")
            except Exception as e:
                logger.warning("Failed to init SHAP explainer: %s", e)
                self._explainer = None

    def explain(
        self,
        features: Dict[str, float],
        prediction: Dict[str, Any],
        feature_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate explanation for a single prediction.

        Returns dict with shap_values, top bullish/bearish factors, and text explanation.
        """
        if not features:
            return self._empty_explanation(prediction)

        feature_names = feature_names or list(features.keys())
        feature_values = np.array([features.get(f, 0.0) for f in feature_names]).reshape(1, -1)

        # Get SHAP values
        shap_values = self._compute_shap_values(feature_values, feature_names)

        # Separate bullish (positive) and bearish (negative) factors
        bullish = []
        bearish = []

        for name, shap_val in sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True):
            readable_name = self.FEATURE_NAMES.get(name, name.replace("_", " ").title())
            raw_value = features.get(name, 0.0)

            entry = {
                "feature": name,
                "readable_name": readable_name,
                "shap_value": round(shap_val, 4),
                "raw_value": round(raw_value, 4) if isinstance(raw_value, float) else raw_value,
            }

            if shap_val > 0:
                bullish.append(entry)
            elif shap_val < 0:
                bearish.append(entry)

        # Build natural language explanation
        direction = prediction.get("direction", "HOLD")
        confidence = prediction.get("probability", 0.5) * 100
        text = self._build_text_explanation(direction, confidence, bullish[:3], bearish[:3])

        return {
            "symbol": prediction.get("symbol", ""),
            "prediction_direction": direction,
            "prediction_confidence": round(confidence, 1),
            "shap_values": shap_values,
            "top_bullish_factors": bullish[:5],
            "top_bearish_factors": bearish[:5],
            "natural_language_explanation": text,
            "model_name": prediction.get("model_name", ""),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _compute_shap_values(
        self,
        X: np.ndarray,
        feature_names: List[str],
    ) -> Dict[str, float]:
        """Compute SHAP values or fall back to feature importance."""
        if self._explainer is not None and SHAP_AVAILABLE:
            try:
                sv = self._explainer.shap_values(X)
                if isinstance(sv, list):
                    sv = sv[1]  # positive class for binary
                values = sv[0] if len(sv.shape) > 1 else sv
                return {
                    name: float(val)
                    for name, val in zip(feature_names, values)
                }
            except Exception as e:
                logger.warning("SHAP computation failed, using fallback: %s", e)

        # Fallback: use model feature importance if available
        if self._model is not None and hasattr(self._model, 'feature_importances_'):
            importances = self._model.feature_importances_
            # Sign based on feature value vs median (heuristic)
            return {
                name: float(imp) * (1.0 if X[0, i] > 0 else -1.0)
                for i, (name, imp) in enumerate(zip(feature_names, importances))
                if i < len(importances)
            }

        # Last resort: uniform importance
        n = len(feature_names)
        return {name: 1.0 / n for name in feature_names}

    def _build_text_explanation(
        self,
        direction: str,
        confidence: float,
        top_bullish: List[Dict],
        top_bearish: List[Dict],
    ) -> str:
        """Build natural language explanation from SHAP factors."""
        parts = []

        if direction == "BUY":
            parts.append(f"BUY signal ({confidence:.0f}% confidence)")
        elif direction == "SELL":
            parts.append(f"SELL signal ({confidence:.0f}% confidence)")
        else:
            parts.append(f"HOLD signal ({confidence:.0f}% confidence)")

        if top_bullish:
            bull_names = [f["readable_name"] for f in top_bullish[:2]]
            parts.append(f"driven by {', '.join(bull_names)}")

        if top_bearish:
            bear_names = [f["readable_name"] for f in top_bearish[:2]]
            parts.append(f"despite headwinds from {', '.join(bear_names)}")

        return " ".join(parts) + "."

    def _empty_explanation(self, prediction: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "symbol": prediction.get("symbol", ""),
            "prediction_direction": prediction.get("direction", "HOLD"),
            "prediction_confidence": 0.0,
            "shap_values": {},
            "top_bullish_factors": [],
            "top_bearish_factors": [],
            "natural_language_explanation": "Insufficient data for explanation.",
            "model_name": "",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
