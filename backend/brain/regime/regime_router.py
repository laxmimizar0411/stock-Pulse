"""
Regime-Conditional Model Router

Routes predictions to specialist models based on current market regime:
- Bull: XGBoost/LightGBM ensemble (momentum-following)
- Bear: GARCH-heavy + defensive ensemble  
- Sideways: Balanced ensemble (mean-reversion bias)

This is MODEL selection routing. Signal weight adjustments are handled
separately in signal_fusion.py _get_regime_adjusted_weights().
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from brain.models.events import MarketRegime

logger = logging.getLogger(__name__)


class RegimeRouter:
    """
    Routes model predictions based on current market regime.
    
    Implements regime-conditional specialist model strategy where different
    models are emphasized based on market conditions.
    """
    
    def __init__(self, model_manager=None):
        """
        Args:
            model_manager: Brain ModelManager instance with trained models
        """
        self.model_manager = model_manager
        
        # Regime-specific model priorities (model_name: weight)
        self.regime_model_weights = {
            MarketRegime.BULL: {
                "xgboost_direction": 0.50,   # High weight on gradient boosting
                "lightgbm_direction": 0.35,
                "garch_volatility": 0.15,    # Low weight on volatility model
            },
            MarketRegime.BEAR: {
                "xgboost_direction": 0.25,   # Reduce trend-following
                "lightgbm_direction": 0.20,
                "garch_volatility": 0.55,    # Emphasize volatility/risk
            },
            MarketRegime.SIDEWAYS: {
                "xgboost_direction": 0.35,   # Balanced
                "lightgbm_direction": 0.35,
                "garch_volatility": 0.30,
            },
        }
        
        self._stats = {
            "routing_calls": 0,
            "bull_routes": 0,
            "bear_routes": 0,
            "sideways_routes": 0,
        }
    
    async def route_prediction(
        self,
        features: np.ndarray,
        regime: MarketRegime,
        return_individual: bool = False,
    ) -> Dict[str, Any]:
        """
        Route prediction to regime-appropriate models.
        
        Args:
            features: Input feature array (n_samples, n_features)
            regime: Current market regime
            return_individual: Include individual model predictions
            
        Returns:
            Dict containing:
            - regime_prediction: Weighted prediction for the regime
            - regime_direction: "BUY" (2), "HOLD" (1), or "SELL" (0)
            - confidence: Model agreement score
            - weights_used: Model weights for this regime
            - models_used: List of models invoked
            - individual_predictions: (optional) Per-model outputs
        """
        if not self.model_manager:
            return {"error": "Model manager not available"}
        
        # Get regime-specific weights
        weights = self.regime_model_weights.get(regime, self.regime_model_weights[MarketRegime.SIDEWAYS])
        
        # Collect predictions from each model
        predictions = {}
        individual_outputs = {}
        
        for model_name, weight in weights.items():
            if weight == 0:
                continue
            
            try:
                pred_result = await self.model_manager.predict(model_name, features)
                
                if pred_result and "predictions" in pred_result:
                    predictions[model_name] = pred_result["predictions"]
                    individual_outputs[model_name] = pred_result
                else:
                    logger.warning(f"Model {model_name} returned no predictions")
            except Exception as e:
                logger.warning(f"Model {model_name} prediction failed: {e}")
        
        if not predictions:
            return {"error": "No model predictions available"}
        
        # Compute weighted regime prediction
        regime_pred = self._blend_predictions(predictions, weights)
        
        # Convert to direction
        regime_direction = self._prediction_to_direction(regime_pred)
        
        # Compute confidence (based on model agreement)
        confidence = self._compute_confidence(predictions, regime_direction)
        
        # Update stats
        self._stats["routing_calls"] += 1
        self._stats[f"{regime.value}_routes"] = self._stats.get(f"{regime.value}_routes", 0) + 1
        
        result = {
            "regime_prediction": float(regime_pred[0]) if isinstance(regime_pred, np.ndarray) else float(regime_pred),
            "regime_direction": regime_direction,
            "confidence": round(confidence, 2),
            "weights_used": weights,
            "regime": regime.value,
            "models_used": list(predictions.keys()),
        }
        
        if return_individual:
            result["individual_predictions"] = {
                name: {
                    "prediction": pred.tolist() if isinstance(pred, np.ndarray) else pred,
                    "direction": self._prediction_to_direction(pred),
                }
                for name, pred in predictions.items()
            }
        
        return result
    
    def _blend_predictions(self, predictions: Dict[str, Any], weights: Dict[str, float]) -> float:
        """Blend predictions using weighted average."""
        weighted_sum = 0.0
        total_weight = 0.0
        
        for model_name, pred in predictions.items():
            weight = weights.get(model_name, 0.0)
            if weight == 0:
                continue
            
            # Extract prediction value
            if isinstance(pred, (list, np.ndarray)):
                pred_value = float(pred[0]) if len(pred) > 0 else 1.0
            else:
                pred_value = float(pred)
            
            weighted_sum += pred_value * weight
            total_weight += weight
        
        if total_weight == 0:
            return 1.0  # HOLD
        
        return weighted_sum / total_weight
    
    def _prediction_to_direction(self, prediction: Any) -> str:
        """Convert numerical prediction to trading direction."""
        if isinstance(prediction, (list, np.ndarray)):
            pred_value = float(prediction[0]) if len(prediction) > 0 else 1.0
        else:
            pred_value = float(prediction)
        
        # Threshold-based direction
        if pred_value >= 1.5:
            return "BUY"
        elif pred_value <= 0.5:
            return "SELL"
        else:
            return "HOLD"
    
    def _compute_confidence(self, predictions: Dict[str, Any], regime_direction: str) -> float:
        """Compute confidence based on model agreement."""
        if not predictions:
            return 0.0
        
        # Count models agreeing with regime direction
        agreements = 0
        for pred in predictions.values():
            model_direction = self._prediction_to_direction(pred)
            if model_direction == regime_direction:
                agreements += 1
        
        # Agreement percentage
        agreement_rate = agreements / len(predictions)
        
        # Base confidence from agreement
        base_confidence = agreement_rate * 80
        
        # Bonus for strong consensus
        if agreement_rate >= 0.9:
            base_confidence += 15
        elif agreement_rate >= 0.75:
            base_confidence += 10
        
        return min(base_confidence, 100.0)
    
    def get_regime_weights(self, regime: MarketRegime) -> Dict[str, float]:
        """Get model weights for a specific regime."""
        return self.regime_model_weights.get(regime, {})
    
    def update_regime_weights(self, regime: MarketRegime, new_weights: Dict[str, float]):
        """
        Update model weights for a specific regime.
        
        Args:
            regime: Target regime
            new_weights: New weight dict (should sum to ~1.0)
        """
        total = sum(new_weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Regime weights sum to {total}, normalizing to 1.0")
            new_weights = {k: v / total for k, v in new_weights.items()}
        
        self.regime_model_weights[regime] = new_weights
        logger.info(f"Updated {regime.value} regime weights: {new_weights}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get routing statistics."""
        return {
            **self._stats,
            "regime_strategies": {
                regime.value: weights
                for regime, weights in self.regime_model_weights.items()
            }
        }
