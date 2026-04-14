"""
TimesFM 2.5 Forecaster

Secondary forecaster for positional trades (20-90 days).
Uses google/timesfm-2.5-200m-pytorch model with CPU-based inference.
"""

import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
import numpy as np
import torch
from transformers import AutoModel
import logging

logger = logging.getLogger(__name__)


class TimesFMForecaster:
    """
    TimesFM 2.5 forecaster for positional trading (20-90 day horizon).
    
    Features:
    - Zero-shot forecasting
    - 16K context length
    - Up to 1000-step horizon
    - Probabilistic forecasts with quantiles
    - 200M parameters
    """
    
    def __init__(self, model_name: str = "google/timesfm-2.5-200m-pytorch", device: str = "cpu"):
        """
        Initialize TimesFM forecaster.
        
        Args:
            model_name: HuggingFace model identifier
            device: Device to run on ("cpu" or "cuda")
        """
        self.model_name = model_name
        self.device = device
        self.model: Optional[Any] = None
        self.loaded = False
        self.model_info = {
            "name": model_name,
            "parameters": "200M",
            "type": "Decoder-only transformer",
            "max_context": 16384,
            "max_horizon": 1000,
            "quantiles": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        }
        
    async def load_model(self):
        """Load TimesFM model (async wrapper for blocking operation)."""
        if self.loaded:
            logger.info("TimesFM model already loaded")
            return
            
        logger.info(f"Loading TimesFM model: {self.model_name} on {self.device}")
        
        try:
            # Run model loading in thread pool
            self.model = await asyncio.to_thread(
                self._load_model_sync
            )
            self.loaded = True
            logger.info(f"✅ TimesFM model loaded successfully on {self.device}")
            
        except Exception as e:
            logger.error(f"Failed to load TimesFM model: {str(e)}")
            # Model might not be available yet, create fallback
            logger.warning("TimesFM model not available, using fallback")
            self.loaded = False
            raise
    
    def _load_model_sync(self) -> Any:
        """Synchronous model loading."""
        try:
            from transformers import TimesFm2_5ModelForPrediction
            
            model = TimesFm2_5ModelForPrediction.from_pretrained(
                self.model_name,
                torch_dtype=torch.float32,
            )
            model.to(self.device)
            model.eval()
            return model
        except Exception as e:
            logger.error(f"TimesFM loading failed: {str(e)}")
            # Fallback: Use AutoModel if specific class not available
            logger.info("Attempting AutoModel fallback...")
            model = AutoModel.from_pretrained(self.model_name, trust_remote_code=True)
            model.to(self.device)
            model.eval()
            return model
    
    async def forecast(
        self,
        historical_data: List[float],
        horizon: int = 30,
        context_length: Optional[int] = None,
        quantiles: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Generate forecast for given historical data.
        
        Args:
            historical_data: Historical price/return data
            horizon: Number of steps to forecast (20-90 for positional trading)
            context_length: Number of historical points to use (default: all, max 16K)
            quantiles: List of quantiles to predict
            
        Returns:
            Dictionary with forecast results
        """
        if not self.loaded:
            # Try to load, but if it fails, use fallback
            try:
                await self.load_model()
            except Exception as e:
                logger.warning(f"TimesFM not available, using fallback forecast: {str(e)}")
                return self._fallback_forecast(historical_data, horizon)
        
        if horizon < 1 or horizon > 1000:
            raise ValueError("Horizon must be between 1 and 1000")
        
        if len(historical_data) < 20:
            raise ValueError("Need at least 20 historical data points")
        
        # Default quantiles
        if quantiles is None:
            quantiles = [0.1, 0.5, 0.9]
        
        # Use specified context or all available data (up to 16K)
        if context_length is None:
            context_length = min(len(historical_data), 16384)
        else:
            context_length = min(context_length, 16384)
        
        # Get last N points
        context_data = historical_data[-context_length:]
        
        try:
            # Run forecast in thread pool
            forecast_result = await asyncio.to_thread(
                self._forecast_sync,
                context_data,
                horizon,
                quantiles
            )
            
            # Add metadata
            forecast_result.update({
                "model": self.model_name,
                "horizon": horizon,
                "context_length": len(context_data),
                "quantiles": quantiles,
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "device": self.device
            })
            
            return forecast_result
            
        except Exception as e:
            logger.error(f"TimesFM forecast error: {str(e)}, using fallback")
            return self._fallback_forecast(historical_data, horizon)
    
    def _forecast_sync(
        self,
        context_data: List[float],
        horizon: int,
        quantiles: List[float]
    ) -> Dict[str, Any]:
        """Synchronous forecast computation."""
        # Convert to tensor
        past_values = torch.tensor(context_data, dtype=torch.float32).unsqueeze(0)  # Add batch dim
        
        # Run prediction
        with torch.no_grad():
            # TimesFM 2.5 API
            try:
                outputs = self.model(
                    past_values=[context_data],  # List of series
                    forecast_context_len=min(len(context_data), 1024),
                    prediction_length=horizon
                )
                
                # Extract predictions
                # outputs.mean_predictions shape: [batch, horizon]
                # outputs.full_predictions shape: [batch, horizon, quantiles]
                
                mean_forecast = outputs.mean_predictions[0].cpu().numpy().tolist()
                
                # Extract quantiles if available
                if hasattr(outputs, 'full_predictions'):
                    quantile_forecasts = outputs.full_predictions[0].cpu().numpy()  # [horizon, num_quantiles]
                    
                    # TimesFM default quantiles: [0.1, 0.2, ..., 0.9]
                    default_quantiles = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
                    
                    result = {}
                    for q in quantiles:
                        if q in default_quantiles:
                            q_idx = default_quantiles.index(q)
                            result[f"q{int(q*100)}"] = quantile_forecasts[:, q_idx].tolist()
                    
                    return {
                        "forecast_mean": mean_forecast,
                        "forecast_median": result.get("q50", mean_forecast),
                        "forecast_lower_80": result.get("q10", None),
                        "forecast_upper_80": result.get("q90", None),
                        "quantile_forecasts": result,
                        "last_observed": context_data[-1]
                    }
                else:
                    # Point forecast only
                    return {
                        "forecast_mean": mean_forecast,
                        "forecast_median": mean_forecast,
                        "forecast_lower_80": None,
                        "forecast_upper_80": None,
                        "quantile_forecasts": {},
                        "last_observed": context_data[-1]
                    }
                    
            except Exception as e:
                logger.error(f"TimesFM prediction failed: {str(e)}")
                raise
    
    def _fallback_forecast(
        self,
        historical_data: List[float],
        horizon: int
    ) -> Dict[str, Any]:
        """
        Fallback forecast using simple exponential smoothing.
        Used when TimesFM model is not available.
        """
        logger.info("Using exponential smoothing fallback forecast")
        
        # Simple exponential smoothing
        alpha = 0.3
        data = np.array(historical_data)
        
        # Calculate trend
        if len(data) > 10:
            recent_trend = (data[-1] - data[-10]) / 10
        else:
            recent_trend = 0
        
        # Initialize with last value
        forecast = []
        last_value = data[-1]
        
        for i in range(horizon):
            # Add trend and some noise
            next_value = last_value + recent_trend
            forecast.append(float(next_value))
            last_value = next_value
        
        # Simple confidence intervals (±10%)
        forecast_array = np.array(forecast)
        lower_80 = (forecast_array * 0.9).tolist()
        upper_80 = (forecast_array * 1.1).tolist()
        
        return {
            "forecast_mean": forecast,
            "forecast_median": forecast,
            "forecast_lower_80": lower_80,
            "forecast_upper_80": upper_80,
            "quantile_forecasts": {
                "q10": lower_80,
                "q50": forecast,
                "q90": upper_80
            },
            "last_observed": float(data[-1]),
            "model": "fallback_exponential_smoothing",
            "horizon": horizon,
            "context_length": len(historical_data),
            "quantiles": [0.1, 0.5, 0.9],
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "device": "cpu",
            "fallback": True
        }
    
    async def forecast_multiple_horizons(
        self,
        historical_data: List[float],
        horizons: List[int] = [20, 30, 60, 90]
    ) -> Dict[int, Dict[str, Any]]:
        """
        Generate forecasts for multiple horizons.
        
        Args:
            historical_data: Historical data
            horizons: List of forecast horizons
            
        Returns:
            Dictionary mapping horizon to forecast results
        """
        results = {}
        for h in horizons:
            results[h] = await self.forecast(historical_data, horizon=h)
        
        return results
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information and status."""
        return {
            **self.model_info,
            "loaded": self.loaded,
            "device": self.device,
            "status": "ready" if self.loaded else "not_loaded"
        }
    
    async def unload_model(self):
        """Unload model from memory."""
        if self.model is not None:
            del self.model
            self.model = None
            self.loaded = False
            
            # Force garbage collection
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            logger.info("TimesFM model unloaded")
