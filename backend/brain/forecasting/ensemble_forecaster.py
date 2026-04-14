"""
Ensemble Forecaster

Regime-conditional ensemble meta-learner that combines:
- Chronos-Bolt-Base (swing 5-20d)
- TimesFM 2.5 (positional 20-90d)
- HMM regime state from Phase 3.1

Uses XGBoost to stack forecasts with regime-dependent weights.
"""

import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Literal
import numpy as np
from xgboost import XGBRegressor
import logging

from .chronos_forecaster import ChronosForecaster
from .timesfm_forecaster import TimesFMForecaster

logger = logging.getLogger(__name__)

RegimeType = Literal["bull", "bear", "sideways", "unknown"]


class EnsembleForecaster:
    """
    Regime-conditional ensemble that combines Chronos and TimesFM.
    
    Strategy:
    - Short horizon (5-20d): Weight Chronos higher
    - Long horizon (20-90d): Weight TimesFM higher
    - Bull regime: More aggressive (higher weights on upside forecasts)
    - Bear regime: More conservative (higher weights on downside forecasts)
    - Sideways: Balanced weights
    
    Meta-learner (XGBoost) learns optimal weights from historical accuracy per regime.
    """
    
    def __init__(self, device: str = "cpu"):
        """Initialize ensemble forecaster."""
        self.device = device
        
        # Initialize base models
        self.chronos = ChronosForecaster(device=device)
        self.timesfm = TimesFMForecaster(device=device)
        
        # Meta-learner for ensemble (one per regime)
        self.meta_models: Dict[str, Optional[XGBRegressor]] = {
            "bull": None,
            "bear": None,
            "sideways": None,
            "unknown": None
        }
        
        # Default weights (before training meta-model)
        self.default_weights = {
            "bull": {"chronos": 0.6, "timesfm": 0.4},
            "bear": {"chronos": 0.5, "timesfm": 0.5},
            "sideways": {"chronos": 0.55, "timesfm": 0.45},
            "unknown": {"chronos": 0.5, "timesfm": 0.5}
        }
        
        self.models_loaded = False
        
    async def load_models(self):
        """Load both Chronos and TimesFM models."""
        if self.models_loaded:
            logger.info("Ensemble models already loaded")
            return
        
        logger.info("Loading ensemble forecasting models...")
        
        # Load models in parallel
        await asyncio.gather(
            self.chronos.load_model(),
            # TimesFM might fail, but that's ok - we have fallback
            self._safe_load_timesfm()
        )
        
        self.models_loaded = True
        logger.info("✅ Ensemble forecasting models loaded")
    
    async def _safe_load_timesfm(self):
        """Safely load TimesFM with fallback."""
        try:
            await self.timesfm.load_model()
        except Exception as e:
            logger.warning(f"TimesFM load failed, will use fallback: {str(e)}")
    
    async def forecast(
        self,
        historical_data: List[float],
        horizon: int,
        regime: RegimeType = "unknown",
        use_meta_learner: bool = False
    ) -> Dict[str, Any]:
        """
        Generate ensemble forecast.
        
        Args:
            historical_data: Historical price/return data
            horizon: Forecast horizon (5-90 days)
            regime: Current market regime (bull/bear/sideways/unknown)
            use_meta_learner: Use trained meta-model for weights (if available)
            
        Returns:
            Combined forecast with metadata
        """
        if not self.models_loaded:
            await self.load_models()
        
        if horizon < 5 or horizon > 90:
            logger.warning(f"Horizon {horizon} outside optimal range (5-90). Proceeding anyway.")
        
        # Decide which models to use based on horizon
        use_chronos = horizon <= 30  # Chronos works best for shorter horizons
        use_timesfm = horizon >= 15  # TimesFM better for longer horizons
        
        # Generate forecasts from base models
        forecasts = {}
        
        if use_chronos:
            try:
                chronos_result = await self.chronos.forecast(
                    historical_data,
                    horizon=min(horizon, 20),  # Chronos max optimal horizon
                    context_length=512
                )
                forecasts["chronos"] = chronos_result
            except Exception as e:
                logger.error(f"Chronos forecast failed: {str(e)}")
                forecasts["chronos"] = None
        
        if use_timesfm:
            try:
                timesfm_result = await self.timesfm.forecast(
                    historical_data,
                    horizon=horizon,
                    context_length=1024
                )
                forecasts["timesfm"] = timesfm_result
            except Exception as e:
                logger.error(f"TimesFM forecast failed: {str(e)}")
                forecasts["timesfm"] = None
        
        # If both models failed, return error
        if not forecasts.get("chronos") and not forecasts.get("timesfm"):
            raise RuntimeError("All base models failed to generate forecast")
        
        # Combine forecasts
        combined_result = await self._combine_forecasts(
            forecasts,
            horizon,
            regime,
            use_meta_learner
        )
        
        return combined_result
    
    async def _combine_forecasts(
        self,
        forecasts: Dict[str, Optional[Dict[str, Any]]],
        horizon: int,
        regime: RegimeType,
        use_meta_learner: bool
    ) -> Dict[str, Any]:
        """Combine forecasts from multiple models."""
        
        # Determine weights
        if use_meta_learner and self.meta_models.get(regime) is not None:
            weights = await self._get_meta_weights(forecasts, regime)
        else:
            weights = self._get_default_weights(horizon, regime)
        
        # Extract forecast arrays
        chronos_forecast = forecasts.get("chronos")
        timesfm_forecast = forecasts.get("timesfm")
        
        # Combine mean forecasts
        combined_mean = None
        
        if chronos_forecast and timesfm_forecast:
            # Both available
            c_mean = np.array(chronos_forecast["forecast_mean"][:horizon])
            t_mean = np.array(timesfm_forecast["forecast_mean"][:horizon])
            
            # Ensure same length
            min_len = min(len(c_mean), len(t_mean))
            c_mean = c_mean[:min_len]
            t_mean = t_mean[:min_len]
            
            combined_mean = (
                weights["chronos"] * c_mean +
                weights["timesfm"] * t_mean
            )
            
            # Combine confidence intervals
            c_lower = np.array(chronos_forecast.get("forecast_lower_80", c_mean)[:min_len])
            c_upper = np.array(chronos_forecast.get("forecast_upper_80", c_mean)[:min_len])
            t_lower = np.array(timesfm_forecast.get("forecast_lower_80", t_mean)[:min_len])
            t_upper = np.array(timesfm_forecast.get("forecast_upper_80", t_mean)[:min_len])
            
            combined_lower = (
                weights["chronos"] * c_lower +
                weights["timesfm"] * t_lower
            )
            combined_upper = (
                weights["chronos"] * c_upper +
                weights["timesfm"] * t_upper
            )
            
        elif chronos_forecast:
            # Only Chronos available
            combined_mean = np.array(chronos_forecast["forecast_mean"][:horizon])
            combined_lower = np.array(chronos_forecast.get("forecast_lower_80", combined_mean))
            combined_upper = np.array(chronos_forecast.get("forecast_upper_80", combined_mean))
            weights = {"chronos": 1.0, "timesfm": 0.0}
            
        elif timesfm_forecast:
            # Only TimesFM available
            combined_mean = np.array(timesfm_forecast["forecast_mean"][:horizon])
            combined_lower = np.array(timesfm_forecast.get("forecast_lower_80", combined_mean))
            combined_upper = np.array(timesfm_forecast.get("forecast_upper_80", combined_mean))
            weights = {"chronos": 0.0, "timesfm": 1.0}
        
        else:
            raise RuntimeError("No forecasts available for ensemble")
        
        # Return combined result
        return {
            "forecast_mean": combined_mean.tolist(),
            "forecast_lower_80": combined_lower.tolist(),
            "forecast_upper_80": combined_upper.tolist(),
            "horizon": horizon,
            "regime": regime,
            "weights": weights,
            "models_used": {
                "chronos": chronos_forecast is not None,
                "timesfm": timesfm_forecast is not None
            },
            "base_forecasts": {
                "chronos": chronos_forecast["forecast_mean"][:horizon] if chronos_forecast else None,
                "timesfm": timesfm_forecast["forecast_mean"][:horizon] if timesfm_forecast else None
            },
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "meta_learner_used": use_meta_learner and self.meta_models.get(regime) is not None
        }
    
    def _get_default_weights(self, horizon: int, regime: RegimeType) -> Dict[str, float]:
        """Get default weights based on horizon and regime."""
        base_weights = self.default_weights[regime].copy()
        
        # Adjust based on horizon
        if horizon <= 10:
            # Short horizon: favor Chronos
            base_weights["chronos"] = min(1.0, base_weights["chronos"] + 0.2)
            base_weights["timesfm"] = 1.0 - base_weights["chronos"]
        elif horizon >= 60:
            # Long horizon: favor TimesFM
            base_weights["timesfm"] = min(1.0, base_weights["timesfm"] + 0.2)
            base_weights["chronos"] = 1.0 - base_weights["timesfm"]
        
        return base_weights
    
    async def _get_meta_weights(
        self,
        forecasts: Dict[str, Optional[Dict[str, Any]]],
        regime: RegimeType
    ) -> Dict[str, float]:
        """
        Get weights from trained meta-learner.
        
        In production, this would use features from the forecasts
        and current market conditions to predict optimal weights.
        """
        # TODO: Implement meta-learner inference
        # For now, return default weights
        return self.default_weights[regime]
    
    async def train_meta_learner(
        self,
        historical_data: Dict[str, List[float]],
        regimes: List[RegimeType],
        actuals: List[float]
    ):
        """
        Train meta-learner to optimize ensemble weights.
        
        Args:
            historical_data: Historical forecast data from base models
            regimes: Regime labels for each time step
            actuals: Actual observed values
        """
        # TODO: Implement meta-learner training
        # This would:
        # 1. Generate forecasts from base models on historical data
        # 2. Learn optimal weights per regime using XGBoost
        # 3. Store trained models in self.meta_models
        logger.info("Meta-learner training not yet implemented")
        pass
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get ensemble model information."""
        return {
            "ensemble_type": "regime_conditional",
            "base_models": {
                "chronos": self.chronos.get_model_info(),
                "timesfm": self.timesfm.get_model_info()
            },
            "meta_learner": {
                "type": "XGBoost",
                "regimes": list(self.meta_models.keys()),
                "trained": {
                    regime: model is not None
                    for regime, model in self.meta_models.items()
                }
            },
            "default_weights": self.default_weights,
            "models_loaded": self.models_loaded,
            "status": "ready" if self.models_loaded else "not_loaded"
        }
    
    async def unload_models(self):
        """Unload all models from memory."""
        await asyncio.gather(
            self.chronos.unload_model(),
            self.timesfm.unload_model()
        )
        self.models_loaded = False
        logger.info("Ensemble models unloaded")
