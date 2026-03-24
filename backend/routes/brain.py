"""
Brain API Routes

Endpoints for the Stock Pulse Brain intelligence system.
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brain", tags=["brain"])

# Will be injected during server startup
_brain_registry = None


def init_brain_router(registry):
    """Initialize the brain router with the registry instance."""
    global _brain_registry
    _brain_registry = registry


@router.get("/status")
async def brain_status():
    """Get overall Brain system status."""
    if _brain_registry is None:
        return {
            "version": "0.1.0",
            "status": "not_initialized",
            "modules": {},
            "message": "Brain system not yet initialized",
        }
    status = _brain_registry.get_status()
    return status.model_dump()


@router.get("/event-bus/stats")
async def event_bus_stats():
    """Get event bus statistics."""
    if _brain_registry is None or not _brain_registry.is_started:
        raise HTTPException(status_code=503, detail="Brain not initialized")
    return _brain_registry.event_bus.get_stats()


@router.get("/config")
async def brain_config():
    """Get current Brain configuration (non-sensitive values)."""
    if _brain_registry is None:
        raise HTTPException(status_code=503, detail="Brain not initialized")
    config = _brain_registry.config
    return {
        "fusion_weights": {
            "technical": config.fusion_weights.technical,
            "sentiment": config.fusion_weights.sentiment,
            "fundamental": config.fusion_weights.fundamental,
            "volume": config.fusion_weights.volume,
            "macro": config.fusion_weights.macro,
        },
        "confidence_thresholds": {
            "suppress": config.confidence_thresholds.suppress,
            "watchlist": config.confidence_thresholds.watchlist,
            "actionable": config.confidence_thresholds.actionable,
            "high_conviction": config.confidence_thresholds.high_conviction,
        },
        "risk": {
            "max_single_position_pct": config.risk.max_single_position_pct,
            "max_sector_concentration_pct": config.risk.max_sector_concentration_pct,
            "daily_loss_cap_pct": config.risk.daily_loss_cap_pct,
            "kelly_fraction": config.risk.kelly_fraction,
        },
        "modules": {
            "features_enabled": config.modules.features_enabled,
            "regime_enabled": config.modules.regime_enabled,
            "ml_models_enabled": config.modules.ml_models_enabled,
            "signal_fusion_enabled": config.modules.signal_fusion_enabled,
            "sentiment_enabled": config.modules.sentiment_enabled,
            "agents_enabled": config.modules.agents_enabled,
            "risk_engine_enabled": config.modules.risk_engine_enabled,
            "options_enabled": config.modules.options_enabled,
            "tax_enabled": config.modules.tax_enabled,
        },
    }


# ==================== PHASE 1: Features ====================

@router.get("/features/{symbol}")
async def get_features(symbol: str):
    """Get the computed feature vector for a symbol."""
    if _brain_registry is None or not _brain_registry.is_started:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    feature_engine = _brain_registry.get_module("feature_engine")
    if feature_engine is None:
        raise HTTPException(status_code=501, detail="Feature engine not yet implemented")

    features = await feature_engine.get_features(symbol.upper())
    if features is None:
        raise HTTPException(status_code=404, detail=f"No features for {symbol}")
    return features


# ==================== PHASE 2: Regime ====================

@router.get("/regime")
async def get_regime():
    """Get current market regime detection."""
    if _brain_registry is None or not _brain_registry.is_started:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    regime_detector = _brain_registry.get_module("regime_detector")
    if regime_detector is None:
        raise HTTPException(status_code=501, detail="Regime detector not yet implemented")

    return await regime_detector.get_current_regime()


@router.get("/regime/history")
async def get_regime_history(days: int = Query(default=90, ge=1, le=365)):
    """Get regime detection history."""
    if _brain_registry is None or not _brain_registry.is_started:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    regime_detector = _brain_registry.get_module("regime_detector")
    if regime_detector is None:
        raise HTTPException(status_code=501, detail="Regime detector not yet implemented")

    return await regime_detector.get_history(days)


# ==================== PHASE 3: Signals ====================

@router.get("/signals")
async def get_signals(
    sector: Optional[str] = None,
    confidence_min: float = Query(default=40.0, ge=0, le=100),
    direction: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Get active Brain signals with optional filters."""
    if _brain_registry is None or not _brain_registry.is_started:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    signal_engine = _brain_registry.get_module("signal_fusion")
    if signal_engine is None:
        raise HTTPException(status_code=501, detail="Signal fusion not yet implemented")

    return await signal_engine.get_signals(
        sector=sector,
        confidence_min=confidence_min,
        direction=direction,
        limit=limit,
    )


@router.get("/signals/{symbol}")
async def get_signal_for_symbol(symbol: str):
    """Get the latest Brain signal for a specific symbol."""
    if _brain_registry is None or not _brain_registry.is_started:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    signal_engine = _brain_registry.get_module("signal_fusion")
    if signal_engine is None:
        raise HTTPException(status_code=501, detail="Signal fusion not yet implemented")

    signal = await signal_engine.get_signal(symbol.upper())
    if signal is None:
        raise HTTPException(status_code=404, detail=f"No signal for {symbol}")
    return signal


@router.get("/explain/{symbol}")
async def explain_prediction(symbol: str):
    """Get SHAP-based explanation for a symbol's prediction."""
    if _brain_registry is None or not _brain_registry.is_started:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    explainer = _brain_registry.get_module("explainability")
    if explainer is None:
        raise HTTPException(status_code=501, detail="Explainability not yet implemented")

    explanation = await explainer.explain(symbol.upper())
    if explanation is None:
        raise HTTPException(status_code=404, detail=f"No explanation for {symbol}")
    return explanation


# ==================== PHASE 4: Sentiment ====================

@router.get("/sentiment/{symbol}")
async def get_sentiment(symbol: str):
    """Get sentiment analysis for a symbol."""
    if _brain_registry is None or not _brain_registry.is_started:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    sentiment = _brain_registry.get_module("sentiment")
    if sentiment is None:
        raise HTTPException(status_code=501, detail="Sentiment pipeline not yet implemented")

    result = await sentiment.get_sentiment(symbol.upper())
    if result is None:
        raise HTTPException(status_code=404, detail=f"No sentiment data for {symbol}")
    return result


@router.get("/sentiment/market")
async def get_market_sentiment():
    """Get overall market sentiment."""
    if _brain_registry is None or not _brain_registry.is_started:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    sentiment = _brain_registry.get_module("sentiment")
    if sentiment is None:
        raise HTTPException(status_code=501, detail="Sentiment pipeline not yet implemented")

    return await sentiment.get_market_sentiment()


# ==================== PHASE 5: Research ====================

@router.get("/research/{symbol}")
async def get_research(symbol: str):
    """Get multi-agent research analysis for a symbol."""
    if _brain_registry is None or not _brain_registry.is_started:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    agents = _brain_registry.get_module("agents")
    if agents is None:
        raise HTTPException(status_code=501, detail="Agent system not yet implemented")

    return await agents.research(symbol.upper())


# ==================== PHASE 6: Risk ====================

@router.get("/risk/portfolio")
async def get_portfolio_risk():
    """Get portfolio risk metrics (VaR, CVaR, drawdown)."""
    if _brain_registry is None or not _brain_registry.is_started:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    risk = _brain_registry.get_module("risk_engine")
    if risk is None:
        raise HTTPException(status_code=501, detail="Risk engine not yet implemented")

    return await risk.get_portfolio_risk()


@router.get("/risk/stress-test")
async def stress_test():
    """Run stress test scenarios on the portfolio."""
    if _brain_registry is None or not _brain_registry.is_started:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    risk = _brain_registry.get_module("risk_engine")
    if risk is None:
        raise HTTPException(status_code=501, detail="Risk engine not yet implemented")

    return await risk.run_stress_test()
