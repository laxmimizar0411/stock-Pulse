"""
Ensemble Manager — Model blending for Stock Pulse Brain.

Combines predictions from multiple models with regime-aware weight adjustments:
- XGBoost: 40% (default)
- LightGBM: 30% (default)
- GARCH: 30% (default)

Weights are dynamically adjusted based on MarketRegime:
- Bull: Boost XGBoost/LightGBM (momentum-focused)
- Bear: Boost GARCH (volatility-focused)
- Sideways: Balanced ensemble

Usage:
    manager = EnsembleManager(model_manager)
    prediction = await manager.predict_ensemble(features, regime="bull")
"""

import logging
import numpy as np
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger("brain.models_ml.ensemble")


class MarketRegime(str, Enum):
    """Market regime enumeration."""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"


class EnsembleManager:
    """
    Ensemble manager for blending predictions from multiple models.
    
    Features:
    - Weighted prediction blending
    - Market regime-aware weight adjustments
    - Confidence scoring based on model agreement
    - Individual model contribution tracking
    """
    
    def __init__(self, model_manager=None):
        """
        Initialize ensemble manager.
        
        Args:
            model_manager: Brain ModelManager instance containing trained models
        """
        self.model_manager = model_manager
        
        # Default base weights (must sum to 1.0)
        self.base_weights = {
            "xgboost_direction": 0.40,
            "lightgbm_direction": 0.30,
            "garch_volatility": 0.30,
        }
        
        # Regime-specific weight multipliers
        self.regime_multipliers = {
            MarketRegime.BULL: {
                "xgboost_direction": 1.2,   # Boost gradient boosting (trend following)
                "lightgbm_direction": 1.2,
                "garch_volatility": 0.6,    # Reduce volatility model
            },
            MarketRegime.BEAR: {
                "xgboost_direction": 0.8,   # Reduce trend models
                "lightgbm_direction": 0.8,
                "garch_volatility": 1.4,    # Boost volatility model (risk-off)
            },
            MarketRegime.SIDEWAYS: {
                "xgboost_direction": 1.0,   # Balanced
                "lightgbm_direction": 1.0,
                "garch_volatility": 1.0,
            },
        }
        
        self._stats = {
            "predictions_made": 0,
            "bull_predictions": 0,
            "bear_predictions": 0,
            "sideways_predictions": 0,
        }
    
    def _get_regime_adjusted_weights(self, regime: Optional[str] = None) -> Dict[str, float]:
        """
        Get model weights adjusted for market regime.
        
        Args:
            regime: Market regime ("bull", "bear", "sideways", or None)
            
        Returns:
            Normalized weight dict
        """
        # Start with base weights
        weights = self.base_weights.copy()
        
        # Apply regime multipliers if regime is specified
        if regime:
            try:
                regime_enum = MarketRegime(regime.lower())
                multipliers = self.regime_multipliers.get(regime_enum, {})
                
                for model_name, base_weight in weights.items():
                    multiplier = multipliers.get(model_name, 1.0)
                    weights[model_name] = base_weight * multiplier
            except (ValueError, AttributeError):
                logger.warning(f"Invalid regime '{regime}', using base weights")
        
        # Normalize to sum to 1.0
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        
        return weights
    
    async def predict_ensemble(
        self,
        features: np.ndarray,
        regime: Optional[str] = None,
        return_individual: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate ensemble prediction from all available models.
        
        Args:
            features: Input feature array (n_samples, n_features)
            regime: Market regime for weight adjustment
            return_individual: Include individual model predictions
            
        Returns:
            Dict containing:
            - ensemble_prediction: Weighted prediction
            - ensemble_direction: "BUY" (2), "HOLD" (1), or "SELL" (0)
            - confidence: Agreement-based confidence score
            - weights_used: Dict of model weights
            - individual_predictions: (optional) Dict of per-model predictions
        """
        if not self.model_manager:
            return {"error": "Model manager not available"}
        
        # Get regime-adjusted weights
        weights = self._get_regime_adjusted_weights(regime)
        
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
        
        # Compute weighted ensemble
        ensemble_pred = self._blend_predictions(predictions, weights)
        
        # Convert to direction
        ensemble_direction = self._prediction_to_direction(ensemble_pred)
        
        # Compute confidence (based on model agreement)
        confidence = self._compute_confidence(predictions, ensemble_direction)
        
        # Update stats
        self._stats["predictions_made"] += 1
        if regime:
            self._stats[f"{regime.lower()}_predictions"] = self._stats.get(f"{regime.lower()}_predictions", 0) + 1
        
        result = {
            "ensemble_prediction": float(ensemble_pred[0]) if isinstance(ensemble_pred, np.ndarray) else float(ensemble_pred),
            "ensemble_direction": ensemble_direction,
            "confidence": round(confidence, 2),
            "weights_used": weights,
            "regime": regime,
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
        """
        Blend predictions using weighted average.
        
        Args:
            predictions: Dict of model_name -> prediction array
            weights: Dict of model_name -> weight
            
        Returns:
            Weighted ensemble prediction
        """
        weighted_sum = 0.0
        total_weight = 0.0
        
        for model_name, pred in predictions.items():
            weight = weights.get(model_name, 0.0)
            if weight == 0:
                continue
            
            # Extract prediction value (handle arrays/lists)
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
        """
        Convert numerical prediction to trading direction.
        
        Args:
            prediction: Model prediction (0=SELL, 1=HOLD, 2=BUY for classification)
            
        Returns:
            "BUY", "HOLD", or "SELL"
        """
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
    
    def _compute_confidence(self, predictions: Dict[str, Any], ensemble_direction: str) -> float:
        """
        Compute confidence based on model agreement.
        
        High confidence when models agree on direction.
        Low confidence when models disagree.
        
        Args:
            predictions: Dict of model predictions
            ensemble_direction: Final ensemble direction
            
        Returns:
            Confidence score (0-100)
        """
        if not predictions:
            return 0.0
        
        # Count models agreeing with ensemble direction
        agreements = 0
        for pred in predictions.values():
            model_direction = self._prediction_to_direction(pred)
            if model_direction == ensemble_direction:
                agreements += 1
        
        # Agreement percentage
        agreement_rate = agreements / len(predictions)
        
        # Base confidence from agreement
        base_confidence = agreement_rate * 80  # Max 80% from agreement
        
        # Bonus for strong consensus
        if agreement_rate >= 0.9:
            base_confidence += 15
        elif agreement_rate >= 0.75:
            base_confidence += 10
        
        return min(base_confidence, 100.0)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get ensemble manager statistics."""
        return {
            **self._stats,
            "base_weights": self.base_weights,
            "available_models": list(self.base_weights.keys()),
        }
    
    def update_base_weights(self, new_weights: Dict[str, float]):
        """
        Update base ensemble weights.
        
        Args:
            new_weights: Dict of model_name -> weight (must sum to ~1.0)
        """
        total = sum(new_weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Weights sum to {total}, normalizing to 1.0")
            new_weights = {k: v / total for k, v in new_weights.items()}
        
        self.base_weights = new_weights
        logger.info(f"Updated ensemble base weights: {new_weights}")
