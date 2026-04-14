"""
Chronos-Bolt-Base Forecaster

Primary forecaster for swing trades (5-20 days).
Uses amazon/chronos-bolt-base model with CPU-based inference.
"""

import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
import numpy as np
import torch
from chronos import BaseChronosPipeline
import logging

logger = logging.getLogger(__name__)


class ChronosForecaster:
    """
    Chronos-Bolt-Base forecaster for swing trading (5-20 day horizon).
    
    Features:
    - Zero-shot forecasting
    - Quantile predictions (10th, 50th, 90th)
    - CPU-optimized (250x faster than original Chronos)
    - Context length: up to 2048 points
    - Horizon: up to 64 steps
    """
    
    def __init__(self, model_name: str = "amazon/chronos-bolt-base", device: str = "cpu"):
        """
        Initialize Chronos forecaster.
        
        Args:
            model_name: HuggingFace model identifier
            device: Device to run on ("cpu" or "cuda")
        """
        self.model_name = model_name
        self.device = device
        self.pipeline: Optional[BaseChronosPipeline] = None
        self.loaded = False
        self.model_info = {
            "name": model_name,
            "parameters": "205M",
            "type": "T5 encoder-decoder",
            "max_context": 2048,
            "max_horizon": 64,
            "quantiles": [0.1, 0.5, 0.9]
        }
        
    async def load_model(self):
        """Load Chronos model (async wrapper for blocking operation)."""
        if self.loaded:
            logger.info("Chronos model already loaded")
            return
            
        logger.info(f"Loading Chronos model: {self.model_name} on {self.device}")
        
        try:
            # Run model loading in thread pool to avoid blocking event loop
            self.pipeline = await asyncio.to_thread(
                self._load_model_sync
            )
            self.loaded = True
            logger.info(f"✅ Chronos model loaded successfully on {self.device}")
            
        except Exception as e:
            logger.error(f"Failed to load Chronos model: {str(e)}")
            raise
    
    def _load_model_sync(self) -> BaseChronosPipeline:
        """Synchronous model loading."""
        return BaseChronosPipeline.from_pretrained(
            self.model_name,
            device_map=self.device,
            torch_dtype=torch.bfloat16 if self.device == "cpu" else torch.float32,
        )
    
    async def forecast(
        self,
        historical_data: List[float],
        horizon: int = 5,
        context_length: Optional[int] = None,
        quantiles: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Generate forecast for given historical data.
        
        Args:
            historical_data: Historical price/return data (list of floats)
            horizon: Number of steps to forecast (5-20 for swing trading)
            context_length: Number of historical points to use (default: all, max 2048)
            quantiles: List of quantiles to predict (default: [0.1, 0.5, 0.9])
            
        Returns:
            Dictionary with forecast results including quantiles, mean, and metadata
        """
        if not self.loaded:
            await self.load_model()
        
        if horizon < 1 or horizon > 64:
            raise ValueError("Horizon must be between 1 and 64")
        
        if len(historical_data) < 10:
            raise ValueError("Need at least 10 historical data points")
        
        # Default quantiles
        if quantiles is None:
            quantiles = [0.1, 0.5, 0.9]
        
        # Use specified context or all available data (up to 2048)
        if context_length is None:
            context_length = min(len(historical_data), 2048)
        else:
            context_length = min(context_length, 2048)
        
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
            logger.error(f"Forecast error: {str(e)}")
            raise
    
    def _forecast_sync(
        self,
        context_data: List[float],
        horizon: int,
        quantiles: List[float]
    ) -> Dict[str, Any]:
        """Synchronous forecast computation."""
        # Convert to tensor
        context_tensor = torch.tensor(context_data, dtype=torch.float32)
        
        # Run prediction
        with torch.no_grad():
            forecast_output = self.pipeline.predict(
                context=context_tensor,
                prediction_length=horizon,
                # Chronos returns quantile forecasts by default
            )
        
        # forecast_output shape: [num_samples, num_quantiles, horizon]
        # Default quantiles in Chronos are typically [0.1, 0.2, ..., 0.9]
        # We'll extract the specific quantiles we need
        
        # For simplicity, extract from the first batch (single series)
        forecast_array = forecast_output[0].numpy()  # Shape: [num_quantiles, horizon]
        
        # Chronos default quantiles: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        # Map to our desired quantiles
        default_quantiles = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        
        result = {}
        for q in quantiles:
            if q in default_quantiles:
                q_idx = default_quantiles.index(q)
                result[f"q{int(q*100)}"] = forecast_array[q_idx].tolist()
        
        # Calculate mean (median as proxy)
        median_idx = default_quantiles.index(0.5)
        mean_forecast = forecast_array[median_idx].tolist()
        
        # Calculate prediction intervals
        lower_idx = default_quantiles.index(0.1) if 0.1 in quantiles else 0
        upper_idx = default_quantiles.index(0.9) if 0.9 in quantiles else -1
        
        return {
            "forecast_mean": mean_forecast,
            "forecast_median": mean_forecast,  # Same for Chronos
            "forecast_lower_80": forecast_array[lower_idx].tolist(),
            "forecast_upper_80": forecast_array[upper_idx].tolist(),
            "quantile_forecasts": result,
            "last_observed": context_data[-1]
        }
    
    async def forecast_multiple_horizons(
        self,
        historical_data: List[float],
        horizons: List[int] = [5, 10, 15, 20]
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
        if self.pipeline is not None:
            del self.pipeline
            self.pipeline = None
            self.loaded = False
            
            # Force garbage collection
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            logger.info("Chronos model unloaded")
