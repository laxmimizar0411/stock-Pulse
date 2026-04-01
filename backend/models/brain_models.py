from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BrainFeatureSnapshot(BaseModel):
    symbol: str
    as_of_date: str
    technical: Dict[str, Any] = Field(default_factory=dict)
    fundamentals: Dict[str, Any] = Field(default_factory=dict)
    valuation: Dict[str, Any] = Field(default_factory=dict)
    derivatives: Dict[str, Any] = Field(default_factory=dict)
    risk: Dict[str, Any] = Field(default_factory=dict)
    ml_features: Dict[str, Any] = Field(default_factory=dict)
    brain_pipeline_features: Dict[str, Any] = Field(
        default_factory=dict,
        description="Latest brain_features.features JSON (Phase 1 pipeline).",
    )
    brain_pipeline_meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="as_of_date, feature_count, computed_at for brain_pipeline row.",
    )
    freshness: Dict[str, Any] = Field(default_factory=dict)
    quality_flags: List[str] = Field(default_factory=list)


class BrainFeatureResponse(BaseModel):
    symbol: str
    snapshot: Optional[BrainFeatureSnapshot] = None
    available: bool = False


class TrainModelRequest(BaseModel):
    model_name: str = "baseline_gbm"
    lookback_days: int = 365
    horizon_days: int = 5
    symbols: Optional[List[str]] = None


class TrainModelResponse(BaseModel):
    model_name: str
    model_version: str
    trained_at: datetime
    metrics: Dict[str, float] = Field(default_factory=dict)


class OrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: int
    order_type: str = "MARKET"
    price: Optional[float] = None
    strategy_id: Optional[str] = None


class OrderResponse(BaseModel):
    order_id: str
    status: str
    message: str
    risk_checks: Dict[str, Any] = Field(default_factory=dict)
