"""
Brain Signal Models

Pydantic models for API serialization of Brain signals and related data.
These complement the event dataclasses (events.py) for REST/WebSocket output.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ContributingFactorModel(BaseModel):
    name: str
    score: float = Field(ge=-1.0, le=1.0, description="Signal score [-1, +1]")
    weight: float = Field(ge=0.0, le=1.0, description="Weight in fusion [0, 1]")
    description: str = ""


class BrainSignal(BaseModel):
    """Full signal output matching the Brain spec."""
    signal_id: str
    timestamp: datetime
    symbol: str
    company: str = ""
    sector: str = ""
    direction: str = Field(description="BUY, SELL, or HOLD")
    confidence: float = Field(ge=0.0, le=100.0, description="Confidence 0-100%")
    timeframe: str = Field(description="intraday, swing, positional, investment")
    entry_price: float = 0.0
    target_price: float = 0.0
    stop_loss: float = 0.0
    risk_reward_ratio: float = 0.0
    risk_level: str = "MEDIUM"
    contributing_factors: List[ContributingFactorModel] = []
    explanation: str = ""
    shap_features: Dict[str, float] = {}
    regime: Optional[str] = None
    model_version: str = ""

    # Swing-specific fields (Phase 2)
    expected_hold_days: Optional[int] = Field(None, description="Expected hold period in days")
    swing_phase: Optional[str] = Field(None, description="breakout, pullback, trend, consolidation")
    signal_tier: Optional[str] = Field(None, description="<40% suppressed, 40-60% watchlist, 60-80% actionable, >80% conviction")


class RegimeStatus(BaseModel):
    """Current market regime status."""
    current_regime: str
    bull_probability: float
    bear_probability: float
    sideways_probability: float
    regime_duration_days: int = 0
    last_change: Optional[datetime] = None
    updated_at: datetime


class FeatureVector(BaseModel):
    """Feature vector for a symbol."""
    symbol: str
    date: str
    features: Dict[str, float]
    feature_count: int
    computed_at: datetime
    categories: Dict[str, List[str]] = {}


class SentimentSummary(BaseModel):
    """Sentiment summary for a symbol or market."""
    symbol: str = ""
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    label: str = "NEUTRAL"
    positive_prob: float = 0.0
    negative_prob: float = 0.0
    neutral_prob: float = 0.0
    article_count: int = 0
    sources: Dict[str, float] = {}
    updated_at: datetime


class ModelPrediction(BaseModel):
    """ML model prediction output."""
    symbol: str
    model_name: str
    model_version: str
    direction: str
    probability: float
    predicted_return_pct: float = 0.0
    horizon_days: int = 5
    shap_top_features: Dict[str, float] = {}
    predicted_at: datetime


class BrainStatus(BaseModel):
    """Overall Brain system status."""
    version: str
    status: str = "operational"
    modules: Dict[str, bool] = {}
    current_regime: Optional[str] = None
    active_signals_count: int = 0
    models_loaded: List[str] = []
    last_feature_computation: Optional[datetime] = None
    last_model_prediction: Optional[datetime] = None
    uptime_seconds: float = 0.0


class RiskMetrics(BaseModel):
    """Portfolio risk metrics."""
    var_95: float = 0.0
    var_99: float = 0.0
    cvar_95: float = 0.0
    max_drawdown_pct: float = 0.0
    current_drawdown_pct: float = 0.0
    daily_pnl_pct: float = 0.0
    position_count: int = 0
    largest_position_pct: float = 0.0
    sector_concentration: Dict[str, float] = {}
    risk_level: str = "MEDIUM"
    capital_protection_status: str = "NORMAL"
    computed_at: datetime


class ExplainabilityReport(BaseModel):
    """SHAP-based explanation for a prediction."""
    symbol: str
    prediction_direction: str
    prediction_confidence: float
    shap_values: Dict[str, float]
    top_bullish_factors: List[Dict[str, Any]] = []
    top_bearish_factors: List[Dict[str, Any]] = []
    natural_language_explanation: str = ""
    model_name: str = ""
    generated_at: datetime
