"""
Brain API Routes — Phase 1+2+3: Data, ML Models, Regime Detection, and Sentiment.

Phase 1 — Data Foundation:
    GET  /api/brain/health, /config, /features/{symbol}, /data-quality/{symbol}
    POST /api/brain/features/compute, /features/batch
    GET  /api/brain/batch/status, /batch/history, /kafka/topics, /storage/status

Phase 2 — AI/ML Models:
    POST /api/brain/models/train, /models/predict/{model_name}
    POST /api/brain/signals/generate, /backtest/run
    GET  /api/brain/models/status, /signals/active

Phase 3.1 — Market Regime Detection:
    GET  /api/brain/market-regime, /market-regime/history
    POST /api/brain/market-regime/detect
    POST /api/brain/position-size/calculate
    GET  /api/brain/position-size/state, /phase3/summary

Phase 3.2 — Sentiment Analysis:
    GET  /api/brain/sentiment/{symbol}
    GET  /api/brain/sentiment/market
    GET  /api/brain/sentiment/social
    GET  /api/brain/sentiment/social/{symbol}
    POST /api/brain/sentiment/earnings-call
    GET  /api/brain/sentiment/pipeline/status
    GET  /api/brain/phase3_2/summary
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from brain.engine import brain_engine
from brain.events.topics import ALL_TOPICS

logger = logging.getLogger("brain.routes")

router = APIRouter(prefix="/api/brain", tags=["Brain"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class ComputeFeaturesRequest(BaseModel):
    symbol: str
    force_refresh: bool = False


class BatchComputeRequest(BaseModel):
    symbols: List[str]


class TriggerDagRequest(BaseModel):
    params: Optional[dict] = None


# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------

@router.get("/health")
async def brain_health():
    """Get Brain health status including all subsystems."""
    return await brain_engine.health_check()


@router.get("/config")
async def brain_config_summary():
    """Get Brain configuration summary (non-sensitive)."""
    return brain_engine.get_config_summary()


# ---------------------------------------------------------------------------
# Feature Pipeline
# ---------------------------------------------------------------------------

@router.get("/features/status")
async def feature_pipeline_status():
    """Get feature pipeline status and statistics."""
    if not brain_engine.feature_pipeline:
        return {"status": "not_initialized", "message": "Feature pipeline has not been started"}

    return {
        "status": "ready",
        "stats": brain_engine.feature_pipeline.get_stats(),
        "registered_features": brain_engine.feature_pipeline.registry.feature_count,
        "categories": brain_engine.feature_pipeline.registry.categories,
    }


@router.get("/features/{symbol}")
async def get_features(
    symbol: str,
    compute: bool = Query(False, description="Compute fresh features if not cached"),
):
    """
    Get computed features for a symbol.

    If compute=true, will fetch data and compute fresh features.
    Otherwise returns previously computed features from MongoDB.
    """
    symbol = symbol.upper().strip()

    if compute:
        if not brain_engine.feature_pipeline:
            raise HTTPException(status_code=503, detail="Feature pipeline not initialized")

        try:
            features = await brain_engine.compute_features(symbol)
            return {
                "symbol": symbol,
                "features": features,
                "feature_count": len(features),
                "source": "computed_fresh",
            }
        except Exception as e:
            logger.exception("Error computing features for %s", symbol)
            raise HTTPException(status_code=500, detail=f"Feature computation failed: {str(e)}")

    # Try stored features
    stored = await brain_engine.get_stored_features(symbol)
    if stored:
        return {
            "symbol": symbol,
            "features": stored.get("features", {}),
            "feature_count": stored.get("feature_count", 0),
            "computed_at": stored.get("computed_at"),
            "source": "cached",
        }

    return {
        "symbol": symbol,
        "features": {},
        "feature_count": 0,
        "source": "not_computed",
        "message": f"No features computed yet for {symbol}. Use ?compute=true to compute.",
    }


@router.post("/features/compute")
async def compute_features(request: ComputeFeaturesRequest):
    """Trigger feature computation for a single symbol."""
    if not brain_engine.feature_pipeline:
        raise HTTPException(status_code=503, detail="Feature pipeline not initialized")

    symbol = request.symbol.upper().strip()

    if request.force_refresh and brain_engine.feature_pipeline:
        brain_engine.feature_pipeline.invalidate_cache(symbol)

    try:
        features = await brain_engine.compute_features(symbol)
        return {
            "success": True,
            "symbol": symbol,
            "feature_count": len(features),
            "features": features,
        }
    except Exception as e:
        logger.exception("Error computing features for %s", symbol)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/features/batch")
async def batch_compute_features(request: BatchComputeRequest):
    """Trigger batch feature computation for multiple symbols."""
    if not brain_engine.feature_pipeline:
        raise HTTPException(status_code=503, detail="Feature pipeline not initialized")

    if len(request.symbols) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 symbols per batch")

    symbols = [s.upper().strip() for s in request.symbols]

    try:
        results = await brain_engine.compute_features_batch(symbols)
        return {
            "success": True,
            "total_symbols": len(symbols),
            "computed": sum(1 for v in results.values() if v),
            "failed": sum(1 for v in results.values() if not v),
            "results": {
                sym: {
                    "feature_count": len(features),
                    "features": features,
                }
                for sym, features in results.items()
            },
        }
    except Exception as e:
        logger.exception("Error in batch feature computation")
        raise HTTPException(status_code=500, detail=str(e))




# ---------------------------------------------------------------------------
# Data Quality
# ---------------------------------------------------------------------------

@router.get("/data-quality/{symbol}")
async def data_quality_report(symbol: str):
    """Get data quality report for a symbol."""
    symbol = symbol.upper().strip()

    try:
        report = await brain_engine.run_data_quality_check(symbol)
        return {
            "symbol": symbol,
            "report": report,
        }
    except Exception as e:
        logger.exception("Error running data quality check for %s", symbol)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Batch Scheduler
# ---------------------------------------------------------------------------

@router.get("/batch/status")
async def batch_scheduler_status():
    """Get batch scheduler status and DAG definitions."""
    if not brain_engine.batch_scheduler:
        return {"status": "not_initialized", "message": "Batch scheduler has not been started"}

    return brain_engine.batch_scheduler.get_status()


@router.get("/batch/history")
async def batch_run_history(limit: int = Query(20, ge=1, le=100)):
    """Get recent DAG run history."""
    if not brain_engine.batch_scheduler:
        return {"history": [], "message": "Batch scheduler not initialized"}

    return {"history": brain_engine.batch_scheduler.get_history(limit=limit)}


@router.post("/batch/trigger/{dag_name}")
async def trigger_dag(dag_name: str, request: Optional[TriggerDagRequest] = None):
    """Manually trigger a specific DAG."""
    if not brain_engine.batch_scheduler:
        raise HTTPException(status_code=503, detail="Batch scheduler not initialized")

    extra_kwargs = request.params if request and request.params else {}

    run = await brain_engine.batch_scheduler.trigger_dag(dag_name, **extra_kwargs)
    if run is None:
        raise HTTPException(status_code=404, detail=f"DAG '{dag_name}' not found")

    return {
        "success": run.status.value == "success",
        "run": run.to_dict(),
    }


# ---------------------------------------------------------------------------
# Kafka Event System
# ---------------------------------------------------------------------------

@router.get("/kafka/topics")
async def list_kafka_topics():
    """List all defined Kafka topics with their configurations."""
    return {
        "topics": [
            {
                "name": t.name,
                "partitions": t.partitions,
                "replication_factor": t.replication_factor,
                "retention_hours": t.retention_ms / (60 * 60 * 1000)
                if t.retention_ms > 0
                else "infinite",
                "compression": t.compression,
                "description": t.description,
            }
            for t in ALL_TOPICS
        ],
        "total_topics": len(ALL_TOPICS),
    }


@router.get("/kafka/stats")
async def kafka_stats():
    """Get Kafka producer/consumer statistics."""
    if not brain_engine.kafka:
        raise HTTPException(status_code=503, detail="Kafka not initialized")
    return brain_engine.kafka.get_stats()


@router.post("/kafka/produce-test")
async def kafka_produce_test():
    """Send a test message to the system health topic."""
    if not brain_engine.kafka:
        raise HTTPException(status_code=503, detail="Kafka not initialized")

    success = await brain_engine.kafka.produce(
        topic="stockpulse.system.health",
        key="test",
        value={
            "type": "health_check",
            "message": "Brain Kafka connectivity test",
        },
    )

    return {
        "success": success,
        "mode": "live" if brain_engine.kafka._connected else "stub",
    }


# ---------------------------------------------------------------------------
# Storage Layer
# ---------------------------------------------------------------------------

@router.get("/storage/status")
async def storage_status():
    """Get storage layer status."""
    if not brain_engine.minio_client:
        return {"status": "not_initialized", "message": "Storage layer not started"}

    return {
        "status": "connected" if brain_engine.minio_client._connected else "local_fallback",
        "mode": "minio" if brain_engine.minio_client._connected else "filesystem",
        "stats": brain_engine.minio_client._stats,
    }


# ---------------------------------------------------------------------------
# Ingestion Pipeline
# ---------------------------------------------------------------------------

@router.get("/ingestion/status")
async def ingestion_status():
    """Get ingestion pipeline status."""
    status = {
        "kafka_connected": bool(brain_engine.kafka and brain_engine.kafka._connected),
        "kafka_mode": "live" if (brain_engine.kafka and brain_engine.kafka._connected) else "stub",
        "data_quality_available": brain_engine.data_quality is not None,
        "normalizer_available": True,  # Always available (brain.ingestion.normalizer)
        "sources": {
            "yfinance": True,   # Always available
            "nse_bhavcopy": True,  # Extractor exists
            "dhan": False,      # Needs API credentials
            "groww": True,      # Extractor exists
            "screener": True,   # Extractor exists
        },
    }

    # Check Dhan credentials
    import os
    if os.getenv("DHAN_ACCESS_TOKEN") and os.getenv("DHAN_CLIENT_ID"):
        status["sources"]["dhan"] = True

    return status


# ---------------------------------------------------------------------------
# Phase 1 Summary
# ---------------------------------------------------------------------------

@router.get("/phase1/summary")
async def phase1_summary():
    """Get a comprehensive Phase 1 implementation summary."""
    return {
        "phase": "Phase 1: Data Foundation & Event Infrastructure",
        "status": "active",
        "components": {
            "kafka_event_bus": {
                "status": "stub_mode" if not (brain_engine.kafka and brain_engine.kafka._connected) else "connected",
                "description": "Event streaming backbone (KRaft mode, no ZooKeeper)",
                "topics_defined": len(ALL_TOPICS),
            },
            "feature_pipeline": {
                "status": "ready" if brain_engine.feature_pipeline else "not_initialized",
                "description": "Computes technical, fundamental, macro, cross-sectional features",
                "features_registered": brain_engine.feature_pipeline.registry.feature_count if brain_engine.feature_pipeline else 0,
            },
            "feature_store": {
                "status": "ready" if brain_engine.feature_store else "not_initialized",
                "description": "Redis+PostgreSQL feature store (MongoDB fallback in dev)",
                "mode": "mongodb_fallback",
            },
            "batch_scheduler": {
                "status": "running" if (brain_engine.batch_scheduler and brain_engine.batch_scheduler._running) else "stopped",
                "description": "Lightweight Airflow alternative for post-market batch DAGs",
                "dags": list(brain_engine.batch_scheduler._dags.keys()) if brain_engine.batch_scheduler else [],
            },
            "storage_layer": {
                "status": "ready" if brain_engine.minio_client else "not_initialized",
                "description": "MinIO/S3-compatible object storage for Parquet archival",
                "mode": "minio" if (brain_engine.minio_client and brain_engine.minio_client._connected) else "local_fallback",
            },
            "data_quality": {
                "status": "ready" if brain_engine.data_quality else "not_initialized",
                "description": "OHLCV integrity validation, circuit limit checks",
            },
            "ingestion": {
                "status": "ready",
                "description": "Data normalization from YFinance, Dhan, Groww, NSE Bhavcopy",
                "normalizer": True,
                "kafka_bridge": True,
            },
        },
        "api_endpoints": [
            "GET  /api/brain/health",
            "GET  /api/brain/features/{symbol}?compute=true",
            "POST /api/brain/features/compute",
            "POST /api/brain/features/batch",
            "GET  /api/brain/features/status",
            "GET  /api/brain/data-quality/{symbol}",
            "GET  /api/brain/batch/status",
            "GET  /api/brain/batch/history",
            "POST /api/brain/batch/trigger/{dag_name}",
            "GET  /api/brain/kafka/topics",
            "GET  /api/brain/storage/status",
            "GET  /api/brain/ingestion/status",
        ],
    }


# ===========================================================================
# Phase 2: AI/ML Models & Swing Signal Generation
# ===========================================================================


class TrainModelsRequest(BaseModel):
    symbol: str
    horizon: int = 5


class GenerateSignalRequest(BaseModel):
    symbol: str
    current_price: float = 0.0


class BacktestRequest(BaseModel):
    symbol: str
    horizon: int = 5
    initial_capital: float = 1_000_000
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.06
    max_hold_days: int = 30


# ---------------------------------------------------------------------------
# Model Training & Prediction
# ---------------------------------------------------------------------------

@router.post("/models/train")
async def train_models(request: TrainModelsRequest):
    """Train ML models (XGBoost, LightGBM, GARCH) for a symbol."""
    if not brain_engine.model_manager:
        raise HTTPException(status_code=503, detail="Model manager not initialized")

    symbol = request.symbol.upper().strip()
    try:
        result = await brain_engine.train_models(symbol, horizon=request.horizon)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error training models for %s", symbol)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/status")
async def model_status():
    """Get ML model status and experiment history."""
    if not brain_engine.model_manager:
        return {"status": "not_initialized", "message": "Model manager not started"}

    return {
        "status": "ready",
        "loaded_models": brain_engine.model_manager.get_loaded_models(),
        "stats": brain_engine.model_manager.get_stats(),
        "recent_experiments": brain_engine.model_manager.get_experiment_history(limit=10),
    }


@router.post("/models/predict/{model_name}")
async def model_predict(model_name: str, request: ComputeFeaturesRequest):
    """Get prediction from a specific trained model."""
    if not brain_engine.model_manager:
        raise HTTPException(status_code=503, detail="Model manager not initialized")

    symbol = request.symbol.upper().strip()

    # Get features for prediction
    features = await brain_engine.get_stored_features(symbol)
    if not features or not features.get("features"):
        # Compute fresh features
        try:
            feat_dict = await brain_engine.compute_features(symbol)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Cannot compute features for {symbol}")
    else:
        feat_dict = features["features"]

    from brain.models_ml.feature_engineering import prepare_features
    X, names = prepare_features(feat_dict)

    result = await brain_engine.model_manager.predict(model_name, X)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "symbol": symbol,
        "model": model_name,
        "prediction": result,
    }


# ---------------------------------------------------------------------------
# Signal Generation
# ---------------------------------------------------------------------------

@router.post("/signals/generate")
async def generate_signal(request: GenerateSignalRequest):
    """Generate a trading signal for a symbol."""
    if not brain_engine.signal_fusion:
        raise HTTPException(status_code=503, detail="Signal pipeline not initialized")

    symbol = request.symbol.upper().strip()
    try:
        result = await brain_engine.generate_signal(symbol, request.current_price)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error generating signal for %s", symbol)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/active")
async def active_signals():
    """Get all currently active signals."""
    if not brain_engine.signal_fusion:
        return {"signals": [], "count": 0}

    signals = brain_engine.signal_fusion._active_signals
    return {
        "count": len(signals),
        "signals": {
            sym: {
                "direction": sig.direction.value if hasattr(sig.direction, 'value') else str(sig.direction),
                "confidence": sig.confidence,
                "entry_price": sig.entry_price,
                "target_price": sig.target_price,
                "stop_loss": sig.stop_loss,
            }
            for sym, sig in signals.items()
        },
    }


# ---------------------------------------------------------------------------
# Backtesting
# ---------------------------------------------------------------------------

@router.post("/backtest/run")
async def run_backtest(request: BacktestRequest):
    """Run a backtest for a symbol."""
    if not brain_engine.backtest_engine:
        raise HTTPException(status_code=503, detail="Backtest engine not initialized")

    symbol = request.symbol.upper().strip()

    # Update engine settings
    brain_engine.backtest_engine.initial_capital = request.initial_capital
    brain_engine.backtest_engine.stop_loss_pct = request.stop_loss_pct
    brain_engine.backtest_engine.take_profit_pct = request.take_profit_pct
    brain_engine.backtest_engine.max_hold_days = request.max_hold_days

    try:
        result = await brain_engine.run_backtest(symbol, horizon=request.horizon)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error running backtest for %s", symbol)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Phase 2 Summary
# ---------------------------------------------------------------------------

@router.get("/phase2/summary")
async def phase2_summary():
    """Get Phase 2 implementation summary."""
    return {
        "phase": "Phase 2: AI/ML Models & Swing Signal Generation",
        "status": "active",
        "components": {
            "model_manager": {
                "status": "ready" if brain_engine.model_manager else "not_initialized",
                "description": "Centralized ML training, prediction, experiment tracking",
                "loaded_models": brain_engine.model_manager.get_loaded_models() if brain_engine.model_manager else [],
                "supported_models": ["xgboost_direction", "lightgbm_direction", "garch_volatility", "lstm_attention", "tft_multi_horizon"],
            },
            "signal_pipeline": {
                "status": "ready" if brain_engine.signal_fusion else "not_initialized",
                "description": "Multi-signal fusion: Technical(30%) + Sentiment(25%) + Fundamental(20%) + Volume(15%) + Macro(10%)",
                "active_signals": len(brain_engine.signal_fusion._active_signals) if brain_engine.signal_fusion else 0,
            },
            "confidence_scorer": {
                "status": "ready" if brain_engine.confidence_scorer else "not_initialized",
                "description": "Multi-factor confidence scoring (0-100%)",
            },
            "backtest_engine": {
                "status": "ready" if brain_engine.backtest_engine else "not_initialized",
                "description": "Vectorized backtesting with Indian cost model (STT, GST, stamp duty, SEBI)",
                "metrics": ["Sharpe", "Sortino", "Calmar", "Max DD", "Win Rate", "Profit Factor"],
            },
            "feature_engineering": {
                "status": "ready",
                "description": "Price-based feature construction, target labeling, correlation filtering",
            },
            "deep_learning": {
                "lstm_attention": "Structure ready (requires PyTorch)",
                "tft": "Structure ready (requires pytorch-forecasting)",
            },
        },
        "api_endpoints": [
            "POST /api/brain/models/train",
            "GET  /api/brain/models/status",
            "POST /api/brain/models/predict/{model_name}",
            "POST /api/brain/signals/generate",
            "GET  /api/brain/signals/active",
            "POST /api/brain/backtest/run",
            "GET  /api/brain/phase2/summary",
        ],
    }


# ===========================================================================
# Phase 3: Market Regime Detection & Risk Management
# ===========================================================================


class PositionSizeRequest(BaseModel):
    signal_confidence: float = 70.0
    win_rate: float = 0.55
    risk_reward_ratio: float = 2.0
    entry_price: float
    stop_loss: float
    timeframe: str = "swing"


# ---------------------------------------------------------------------------
# Market Regime
# ---------------------------------------------------------------------------

@router.get("/market-regime")
async def get_market_regime(
    detect: bool = Query(False, description="Run fresh detection (otherwise returns cached)"),
):
    """
    Get current market regime (bull/bear/sideways).

    Returns regime state, probabilities, and multi-detector consensus.
    Use ?detect=true to trigger a fresh detection pass.
    """
    if detect:
        try:
            result = await brain_engine.detect_regime()
            if "error" in result:
                raise HTTPException(status_code=503, detail=result["error"])
            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Error detecting market regime")
            raise HTTPException(status_code=500, detail=str(e))

    # Return cached regime status
    return await brain_engine.get_regime_status()


@router.post("/market-regime/detect")
async def detect_market_regime(force_retrain: bool = Query(False)):
    """
    Trigger market regime detection with optional model retraining.

    Args:
        force_retrain: Force HMM/K-Means/GMM retraining even if not stale
    """
    if not brain_engine.hmm_detector:
        raise HTTPException(status_code=503, detail="Regime detection not initialized")

    try:
        result = await brain_engine.detect_regime(force_retrain=force_retrain)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in regime detection")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market-regime/history")
async def regime_history(days: int = Query(90, ge=1, le=365)):
    """Get regime history from the regime store."""
    if not brain_engine.regime_store:
        return {"history": [], "message": "Regime store not initialized"}

    history = await brain_engine.regime_store.get_history(days=days)
    return {
        "days_requested": days,
        "entries": len(history),
        "history": history,
    }


# ---------------------------------------------------------------------------
# Position Sizing
# ---------------------------------------------------------------------------

@router.post("/position-size/calculate")
async def calculate_position_size(request: PositionSizeRequest):
    """
    Calculate regime-aware position size using Kelly Criterion.

    Takes into account current market regime, drawdown rules,
    and signal confidence to determine optimal position sizing.
    """
    if not brain_engine.position_sizer:
        raise HTTPException(status_code=503, detail="Position sizer not initialized")

    try:
        result = await brain_engine.calculate_position_size(
            signal_confidence=request.signal_confidence,
            win_rate=request.win_rate,
            risk_reward_ratio=request.risk_reward_ratio,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            timeframe=request.timeframe,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error calculating position size")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/position-size/state")
async def position_sizer_state():
    """Get current position sizer state (drawdown flags, Kelly fractions)."""
    if not brain_engine.position_sizer:
        return {"status": "not_initialized"}
    return brain_engine.position_sizer.get_current_state()


# ---------------------------------------------------------------------------
# Phase 3 Summary
# ---------------------------------------------------------------------------

@router.get("/phase3/summary")
async def phase3_summary():
    """Get Phase 3.1 implementation summary."""
    return {
        "phase": "Phase 3.1: HMM Market Regime Detection",
        "status": "active" if brain_engine.hmm_detector else "not_initialized",
        "components": {
            "hmm_detector": {
                "status": "ready" if brain_engine.hmm_detector else "not_initialized",
                "description": "3-state Gaussian HMM (bull/bear/sideways)",
            },
            "kmeans_detector": {
                "status": "ready" if (brain_engine.kmeans_detector and brain_engine.kmeans_detector.is_available) else "not_available",
                "description": "K-Means hard clustering regime detector",
            },
            "gmm_detector": {
                "status": "ready" if (brain_engine.gmm_detector and brain_engine.gmm_detector.is_available) else "not_available",
                "description": "GMM soft clustering with probabilities",
            },
            "cusum_detector": {
                "status": "ready" if brain_engine.cusum_detector else "not_initialized",
                "description": "CUSUM change-point detection for real-time regime shifts",
            },
            "regime_router": {
                "status": "ready" if brain_engine.regime_router else "not_initialized",
                "description": "Routes model predictions by regime (bull: XGB 50%, bear: GARCH 55%)",
                "stats": brain_engine.regime_router.get_stats() if brain_engine.regime_router else {},
            },
            "position_sizer": {
                "status": "ready" if brain_engine.position_sizer else "not_initialized",
                "description": "Kelly Criterion with ATR stops and drawdown escalation",
                "state": brain_engine.position_sizer.get_current_state() if brain_engine.position_sizer else {},
            },
        },
        "current_regime": brain_engine._current_regime.value if brain_engine._current_regime else "unknown",
        "api_endpoints": [
            "GET  /api/brain/market-regime",
            "GET  /api/brain/market-regime?detect=true",
            "POST /api/brain/market-regime/detect",
            "GET  /api/brain/market-regime/history",
            "POST /api/brain/position-size/calculate",
            "GET  /api/brain/position-size/state",
            "GET  /api/brain/phase3/summary",
        ],
    }



# =====================================================================
# Phase 3.2: Sentiment Analysis Pipeline
# =====================================================================

class EarningsCallRequest(BaseModel):
    """Request body for earnings call analysis."""
    symbol: str
    transcript: str
    quarter: str = ""

class SentimentBatchRequest(BaseModel):
    """Request body for batch sentiment analysis."""
    symbols: List[str]


@router.get("/sentiment/{symbol}")
async def get_symbol_sentiment(
    symbol: str,
    force_refresh: bool = Query(False, description="Force fresh data fetch"),
):
    """
    Get aggregated sentiment for a specific symbol.
    
    Ensemble: 0.50 × FinBERT + 0.20 × VADER + 0.30 × LLM (Gemini)
    """
    result = await brain_engine.get_sentiment(symbol, force_refresh=force_refresh)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.get("/sentiment/market/overview")
async def get_market_sentiment():
    """
    Get overall market-wide sentiment aggregated from all news sources.
    """
    result = await brain_engine.get_market_sentiment()
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.get("/sentiment/social/feed")
async def get_social_sentiment(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
):
    """
    Get social media sentiment from Reddit (r/IndianStreetBets, r/IndiaInvestments, etc.)
    """
    result = await brain_engine.get_social_sentiment(symbol=symbol)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.get("/sentiment/social/{symbol}")
async def get_social_sentiment_for_symbol(symbol: str):
    """
    Get social media sentiment for a specific symbol.
    Searches Reddit for mentions of the stock.
    """
    result = await brain_engine.get_social_sentiment(symbol=symbol)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.post("/sentiment/earnings-call")
async def analyze_earnings_call(request: EarningsCallRequest):
    """
    Analyze an earnings call transcript.
    
    Splits into management discussion vs Q&A sections,
    measures tone divergence, extracts forward-looking statements.
    """
    if len(request.transcript) < 100:
        raise HTTPException(status_code=400, detail="Transcript too short (min 100 chars)")
    
    result = await brain_engine.analyze_earnings_call(
        symbol=request.symbol,
        transcript=request.transcript,
        quarter=request.quarter,
    )
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.post("/sentiment/batch")
async def compute_batch_sentiment(request: SentimentBatchRequest):
    """
    Compute sentiment for multiple symbols at once.
    """
    if not request.symbols:
        raise HTTPException(status_code=400, detail="No symbols provided")
    if len(request.symbols) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 symbols per batch")
    
    if not brain_engine.sentiment_aggregator:
        raise HTTPException(status_code=503, detail="Sentiment pipeline not initialized")
    
    results = await brain_engine.sentiment_aggregator.compute_all_symbols(request.symbols)
    return {
        "symbols_processed": len(results),
        "results": {sym: res.to_dict() for sym, res in results.items()},
    }


@router.get("/sentiment/pipeline/status")
async def get_sentiment_pipeline_status():
    """
    Get status of all sentiment pipeline components.
    """
    from brain.sentiment.llm_sentiment import get_llm_status

    components = {}
    
    # FinBERT / VADER analyzer status
    if brain_engine.sentiment_aggregator:
        stats = brain_engine.sentiment_aggregator.get_stats()
        components["aggregator"] = {
            "status": "healthy",
            "cached_symbols": stats.get("cached_symbols", 0),
            "analyzer": stats.get("analyzer", {}),
        }
        components["news_scraper"] = {
            "status": "healthy",
            "stats": stats.get("scraper", {}),
        }
    else:
        components["aggregator"] = {"status": "not_initialized"}
        components["news_scraper"] = {"status": "not_initialized"}
    
    # Social scraper
    if brain_engine.social_scraper:
        components["social_scraper"] = {
            "status": "healthy",
            "stats": brain_engine.social_scraper.get_stats(),
        }
    else:
        components["social_scraper"] = {"status": "not_initialized"}
    
    # Earnings analyzer
    if brain_engine.earnings_analyzer:
        components["earnings_analyzer"] = {
            "status": "healthy",
            "stats": brain_engine.earnings_analyzer.get_stats(),
        }
    else:
        components["earnings_analyzer"] = {"status": "not_initialized"}
    
    # LLM service
    llm_status = await get_llm_status()
    components["llm_service"] = llm_status
    
    return {
        "pipeline": "sentiment_analysis",
        "phase": "3.2",
        "components": components,
    }


@router.get("/phase3_2/summary")
async def get_phase3_2_summary():
    """
    Phase 3.2 summary: FinBERT Sentiment Pipeline status and capabilities.
    """
    from brain.sentiment.llm_sentiment import get_llm_status

    llm_status = await get_llm_status()

    return {
        "phase": "3.2",
        "name": "FinBERT Sentiment Pipeline",
        "status": "operational" if brain_engine.sentiment_aggregator else "not_initialized",
        "components": {
            "finbert_analyzer": {
                "status": "ready" if brain_engine.sentiment_aggregator else "not_initialized",
                "description": "ProsusAI/finbert + Indian variant (kdave/FineTuned_Finbert)",
                "models": ["ProsusAI/finbert", "kdave/FineTuned_Finbert"],
            },
            "vader_analyzer": {
                "status": "ready" if brain_engine.sentiment_aggregator else "not_initialized",
                "description": "VADER rule-based sentiment (fast fallback)",
            },
            "llm_sentiment": {
                "status": "ready" if llm_status.get("api_key_configured") else "no_api_key",
                "description": "Gemini LLM contextual sentiment analysis",
                "tier2_model": llm_status.get("tier2_model", ""),
            },
            "news_scraper": {
                "status": "ready" if brain_engine.sentiment_aggregator else "not_initialized",
                "description": "RSS feeds: Moneycontrol, Economic Times, LiveMint, Business Standard",
            },
            "social_scraper": {
                "status": "ready" if brain_engine.social_scraper else "not_initialized",
                "description": "Reddit: r/IndianStreetBets, r/IndiaInvestments, r/DalalStreetTalks",
            },
            "entity_extractor": {
                "status": "ready" if brain_engine.sentiment_aggregator else "not_initialized",
                "description": "NER + symbol mapping for NIFTY 50 universe",
            },
            "earnings_analyzer": {
                "status": "ready" if brain_engine.earnings_analyzer else "not_initialized",
                "description": "Earnings call analysis with management vs Q&A tone divergence",
            },
        },
        "ensemble_weights": {
            "finbert": 0.50,
            "vader": 0.20,
            "llm": 0.30,
        },
        "nlp_pipeline": [
            "1. Language Detection (langdetect)",
            "2. Hindi → English Translation (deep-translator)",
            "3. Text Cleaning / Truncation",
            "4. FinBERT Sentiment (transformer)",
            "5. VADER Sentiment (rule-based)",
            "6. Gemini LLM Contextual Sentiment",
            "7. Weighted Ensemble Aggregation with Time-Decay",
        ],
        "api_endpoints": [
            "GET  /api/brain/sentiment/{symbol}",
            "GET  /api/brain/sentiment/market/overview",
            "GET  /api/brain/sentiment/social/feed",
            "GET  /api/brain/sentiment/social/{symbol}",
            "POST /api/brain/sentiment/earnings-call",
            "POST /api/brain/sentiment/batch",
            "GET  /api/brain/sentiment/pipeline/status",
            "GET  /api/brain/phase3_2/summary",
        ],
    }


# =====================================================================
# Phase 3.3: LLM Multi-Agent System
# =====================================================================

class AgentAnalysisRequest(BaseModel):
    """Request body for multi-agent analysis."""
    symbol: str
    context: dict = {}


@router.post("/agents/analyze")
async def run_agent_analysis(request: AgentAnalysisRequest):
    """
    Run the full multi-agent analysis pipeline for a symbol.
    
    Pipeline:
      Stage 1: 4 Analyst Agents (parallel) — Technical, Fundamental, Macro, Event-Driven
      Stage 2: Bull/Bear Researchers (parallel)
      Stage 3: Synthesizer — Combined recommendation
      Stage 4: Trader Agent — Trade execution plan
      Stage 5: Risk Agent — Review with veto power
      Stage 6: Report Generator — Human-readable report
    
    Returns the complete analysis from all 10 agents.
    """
    result = await brain_engine.run_agent_analysis(
        symbol=request.symbol,
        context=request.context,
    )
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.get("/agents/status")
async def get_agent_system_status():
    """
    Get status of the LLM multi-agent system.
    """
    if not brain_engine.agent_orchestrator:
        return {
            "status": "not_initialized",
            "agents_count": 0,
        }
    
    stats = brain_engine.agent_orchestrator.get_stats()
    return {
        "status": "healthy" if brain_engine.agent_orchestrator.is_available else "no_api_key",
        "agents_count": 10,
        "agents": [
            "TechnicalAnalyst", "FundamentalAnalyst", "MacroAnalyst", "EventDrivenAnalyst",
            "BullResearcher", "BearResearcher", "Synthesizer", "Trader", "RiskAgent", "ReportGenerator",
        ],
        "llm_tiers": {
            "tier1": stats.get("tier1_llm", {}),
            "tier2": stats.get("tier2_llm", {}),
        },
        "orchestrator_stats": stats.get("orchestrator", {}),
    }


@router.get("/phase3_3/summary")
async def get_phase3_3_summary():
    """
    Phase 3.3 summary: LLM Multi-Agent System status and capabilities.
    """
    import os

    return {
        "phase": "3.3",
        "name": "LLM Multi-Agent System (2-Tier)",
        "status": "operational" if (brain_engine.agent_orchestrator and brain_engine.agent_orchestrator.is_available) else "not_available",
        "llm_config": {
            "tier1": {
                "provider": "google",
                "model": os.environ.get("GEMINI_TIER1_MODEL", "gemini-2.5-flash"),
                "use": "Deep analysis (analyst agents, synthesizer, trader, risk)",
            },
            "tier2": {
                "provider": "google",
                "model": os.environ.get("GEMINI_TIER2_MODEL", "gemini-2.0-flash"),
                "use": "Extraction & formatting (report generator)",
            },
        },
        "agents": {
            "analyst_agents": {
                "count": 4,
                "list": ["TechnicalAnalyst", "FundamentalAnalyst", "MacroAnalyst", "EventDrivenAnalyst"],
                "description": "Run in parallel, each analyzing from a different perspective",
            },
            "research_agents": {
                "count": 2,
                "list": ["BullResearcher", "BearResearcher"],
                "description": "Present strongest case for and against the investment",
            },
            "decision_agents": {
                "count": 3,
                "list": ["Synthesizer", "Trader", "RiskAgent"],
                "description": "Combine perspectives, plan trade, review risk (veto power)",
            },
            "output_agents": {
                "count": 1,
                "list": ["ReportGenerator"],
                "description": "Generate human-readable investment report",
            },
        },
        "pipeline_stages": [
            "Stage 1: 4 Analyst Agents (parallel)",
            "Stage 2: Bull/Bear Researchers (parallel)",
            "Stage 3: Synthesizer (combine all)",
            "Stage 4: Trader Agent (trade plan)",
            "Stage 5: Risk Agent (veto power)",
            "Stage 6: Report Generator (human-readable)",
        ],
        "api_endpoints": [
            "POST /api/brain/agents/analyze",
            "GET  /api/brain/agents/status",
            "GET  /api/brain/phase3_3/summary",
        ],
    }



# =====================================================================
# Phase 3.4: Risk Management Engine
# =====================================================================

class VaRRequest(BaseModel):
    """Request body for VaR calculation."""
    symbol: str
    returns: List[float]  # Daily return values
    portfolio_value: float = 1000000.0

class StressTestRequest(BaseModel):
    """Request body for stress testing."""
    symbol: str
    portfolio_value: float = 1000000.0
    sector: str = "general"
    scenarios: Optional[List[str]] = None

class SEBIMarginRequest(BaseModel):
    """Request body for SEBI margin check."""
    symbol: str
    trade_value: float
    is_delivery: bool = True
    current_price: float = 0.0
    prev_close: float = 0.0
    portfolio_value: float = 0.0

class HRPRequest(BaseModel):
    """Request body for HRP portfolio optimization."""
    symbols: List[str]
    returns_matrix: List[List[float]]  # [[day1_ret1, day1_ret2], [day2_ret1, day2_ret2], ...]


@router.post("/risk/var")
async def calculate_var(request: VaRRequest):
    """
    Calculate Value at Risk (VaR) using three methods:
    - Historical VaR
    - Parametric VaR (normal distribution)
    - Monte Carlo VaR (10,000 simulations)
    
    Plus Conditional VaR (CVaR / Expected Shortfall).
    """
    if len(request.returns) < 10:
        raise HTTPException(status_code=400, detail="Need at least 10 return observations")
    
    result = await brain_engine.calculate_var(
        symbol=request.symbol,
        returns_list=request.returns,
        portfolio_value=request.portfolio_value,
    )
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.post("/risk/stress-test")
async def run_stress_test(request: StressTestRequest):
    """
    Run historical stress tests:
    - Global Financial Crisis 2008 (~60% drawdown)
    - COVID-19 Crash 2020 (~38% drawdown)
    - Demonetization 2016 (~6% drawdown)
    - Taper Tantrum 2013 (~12% drawdown)
    - IL&FS Crisis 2018 (~15% drawdown)
    """
    result = await brain_engine.run_stress_test(
        symbol=request.symbol,
        portfolio_value=request.portfolio_value,
        sector=request.sector,
    )
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.get("/risk/stress-test/scenarios")
async def get_stress_scenarios():
    """Get list of available stress test scenarios."""
    if not brain_engine.stress_test_engine:
        raise HTTPException(status_code=503, detail="Stress test engine not initialized")
    return {"scenarios": brain_engine.stress_test_engine.get_available_scenarios()}


@router.post("/risk/sebi-margin")
async def check_sebi_margin(request: SEBIMarginRequest):
    """
    Calculate SEBI-mandated margin requirements:
    - VAR margin, Extreme Loss Margin (ELM)
    - Delivery margin (for T+1 settlement)
    - Concentration margin
    - Compliance violations check
    """
    result = await brain_engine.check_sebi_margin(
        symbol=request.symbol,
        trade_value=request.trade_value,
        is_delivery=request.is_delivery,
        current_price=request.current_price,
        prev_close=request.prev_close,
        portfolio_value=request.portfolio_value,
    )
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.post("/risk/hrp")
async def optimize_hrp_portfolio(request: HRPRequest):
    """
    Hierarchical Risk Parity (HRP) portfolio optimization.
    
    Marcos López de Prado algorithm:
    1. Cluster correlation matrix
    2. Quasi-diagonalize
    3. Recursive bisection for inverse-variance allocation
    """
    import numpy as np

    if not brain_engine.hrp_optimizer:
        raise HTTPException(status_code=503, detail="HRP optimizer not initialized")
    if len(request.symbols) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 symbols")
    if len(request.returns_matrix) < 10:
        raise HTTPException(status_code=400, detail="Need at least 10 return observations")

    returns = np.array(request.returns_matrix)
    if returns.shape[1] != len(request.symbols):
        raise HTTPException(
            status_code=400,
            detail=f"Returns matrix columns ({returns.shape[1]}) != symbols ({len(request.symbols)})"
        )

    result = brain_engine.hrp_optimizer.optimize(returns, request.symbols)
    return result.to_dict()


@router.get("/phase3_4/summary")
async def get_phase3_4_summary():
    """Phase 3.4 summary: Risk Management Engine."""
    return {
        "phase": "3.4",
        "name": "Risk Management Engine",
        "status": "operational" if brain_engine.var_calculator else "not_initialized",
        "components": {
            "var_calculator": {
                "status": "ready" if brain_engine.var_calculator else "not_initialized",
                "methods": ["Historical VaR", "Parametric VaR", "Monte Carlo VaR (10k sims)", "CVaR"],
                "confidence_level": "95%",
            },
            "stress_testing": {
                "status": "ready" if brain_engine.stress_test_engine else "not_initialized",
                "scenarios": ["GFC 2008", "COVID 2020", "Demonetization 2016", "Taper Tantrum 2013", "IL&FS 2018"],
            },
            "sebi_compliance": {
                "status": "ready" if brain_engine.sebi_compliance else "not_initialized",
                "checks": ["VAR margin", "ELM", "Delivery margin", "Concentration", "Circuit breakers"],
            },
            "hrp_portfolio": {
                "status": "ready" if brain_engine.hrp_optimizer else "not_initialized",
                "algorithm": "Marcos López de Prado HRP (cluster → quasi-diag → recursive bipartition)",
            },
        },
        "api_endpoints": [
            "POST /api/brain/risk/var",
            "POST /api/brain/risk/stress-test",
            "GET  /api/brain/risk/stress-test/scenarios",
            "POST /api/brain/risk/sebi-margin",
            "POST /api/brain/risk/hrp",
            "GET  /api/brain/phase3_4/summary",
        ],
    }



# =====================================================================
# Phase 3.5: RAG Knowledge Base
# =====================================================================

class RAGSearchRequest(BaseModel):
    """Request body for RAG search."""
    query: str
    limit: int = 5
    category: Optional[str] = None

class RAGAddDocRequest(BaseModel):
    """Request body for adding a document to RAG."""
    title: str
    content: str
    source: str = "user"
    category: str = "general"
    symbols: List[str] = []


@router.post("/rag/search")
async def rag_search(request: RAGSearchRequest):
    """Search the knowledge base using semantic similarity."""
    if not brain_engine.rag_knowledge_base or not brain_engine.rag_knowledge_base.is_available:
        raise HTTPException(status_code=503, detail="RAG knowledge base not available")
    results = brain_engine.rag_knowledge_base.search(
        query=request.query, limit=request.limit, category=request.category
    )
    return {"query": request.query, "results": [r.to_dict() for r in results], "count": len(results)}


@router.post("/rag/add")
async def rag_add_document(request: RAGAddDocRequest):
    """Add a document to the knowledge base."""
    if not brain_engine.rag_knowledge_base or not brain_engine.rag_knowledge_base.is_available:
        raise HTTPException(status_code=503, detail="RAG knowledge base not available")
    from brain.rag.knowledge_base import KBDocument
    doc = KBDocument(
        title=request.title, content=request.content,
        source=request.source, category=request.category, symbols=request.symbols,
    )
    success = brain_engine.rag_knowledge_base.add_document(doc)
    return {"success": success, "doc_id": doc.doc_id}


@router.get("/rag/status")
async def rag_status():
    """Get RAG knowledge base status."""
    if not brain_engine.rag_knowledge_base:
        return {"status": "not_initialized"}
    return {"status": "healthy" if brain_engine.rag_knowledge_base.is_available else "unavailable",
            "stats": brain_engine.rag_knowledge_base.get_stats()}


@router.get("/phase3_5/summary")
async def get_phase3_5_summary():
    """Phase 3.5 summary: RAG Knowledge Base."""
    kb = brain_engine.rag_knowledge_base
    return {
        "phase": "3.5", "name": "RAG Knowledge Base (Qdrant)",
        "status": "operational" if (kb and kb.is_available) else "not_available",
        "vector_db": "Qdrant (in-memory)",
        "embedder": "all-MiniLM-L6-v2 (384-dim)",
        "stats": kb.get_stats() if kb else {},
        "api_endpoints": ["POST /api/brain/rag/search", "POST /api/brain/rag/add", "GET /api/brain/rag/status"],
    }


# =====================================================================
# Phase 3.6: Corporate Governance Scoring
# =====================================================================

class GovernanceRequest(BaseModel):
    """Request body for governance scoring."""
    symbol: str
    promoter_holding_pct: float = 50.0
    promoter_pledge_pct: float = 0.0
    board_independence_ratio: float = 0.5
    big4_auditor: bool = True
    auditor_tenure_years: int = 3
    related_party_txn_pct: float = 5.0
    regulatory_penalties: int = 0
    dividend_consistency_years: int = 5
    mgmt_turnover_3yr: int = 1
    timely_disclosures: bool = True


@router.post("/governance/score")
async def compute_governance_score(request: GovernanceRequest):
    """Compute corporate governance score (0-100)."""
    if not brain_engine.governance_scorer:
        raise HTTPException(status_code=503, detail="Governance scorer not initialized")
    result = brain_engine.governance_scorer.score(**request.model_dump())
    return result.to_dict()


@router.get("/phase3_6/summary")
async def get_phase3_6_summary():
    """Phase 3.6 summary: Corporate Governance Scoring."""
    return {
        "phase": "3.6", "name": "Corporate Governance Scoring",
        "status": "operational" if brain_engine.governance_scorer else "not_initialized",
        "scoring_components": [
            "Promoter Holding (20pts)", "Promoter Pledge (15pts)", "Board Independence (15pts)",
            "Auditor Quality (10pts)", "Related-Party Txn (10pts)", "Regulatory Compliance (10pts)",
            "Dividend Consistency (10pts)", "Management Stability (5pts)", "Disclosure Quality (5pts)",
        ],
        "grades": ["A+", "A", "B+", "B", "C+", "C", "D"],
        "api_endpoints": ["POST /api/brain/governance/score"],
    }


# =====================================================================
# Phase 3.7: Sector Rotation Engine
# =====================================================================

class SectorRotationRequest(BaseModel):
    """Request body for sector rotation analysis."""
    sector_returns: Dict[str, Dict[str, float]]  # {sector: {"1m": %, "3m": %, "6m": %}}
    business_cycle: str = "expansion"


@router.post("/sector/rotation")
async def compute_sector_rotation(request: SectorRotationRequest):
    """Compute sector rotation scores and rankings."""
    if not brain_engine.sector_rotation:
        raise HTTPException(status_code=503, detail="Sector rotation engine not initialized")
    results = brain_engine.sector_rotation.compute_rotation(
        sector_returns=request.sector_returns,
        business_cycle=request.business_cycle,
    )
    return {"scores": [r.to_dict() for r in results], "business_cycle": request.business_cycle}


@router.get("/sector/list")
async def get_sector_list():
    """Get list of tracked sectors."""
    if not brain_engine.sector_rotation:
        raise HTTPException(status_code=503, detail="Sector rotation engine not initialized")
    return {"sectors": brain_engine.sector_rotation.get_sectors()}


@router.get("/phase3_7/summary")
async def get_phase3_7_summary():
    """Phase 3.7 summary: Sector Rotation Engine."""
    return {
        "phase": "3.7", "name": "Sector Rotation Engine",
        "status": "operational" if brain_engine.sector_rotation else "not_initialized",
        "sectors": list(brain_engine.sector_rotation.get_sectors().keys()) if brain_engine.sector_rotation else [],
        "business_cycles": ["expansion", "peak", "contraction", "trough"],
        "api_endpoints": ["POST /api/brain/sector/rotation", "GET /api/brain/sector/list"],
    }


# =====================================================================
# Phase 3.8: Dividend Intelligence
# =====================================================================

class DividendAnalysisRequest(BaseModel):
    """Request body for dividend analysis."""
    symbol: str
    current_price: float = 100.0
    eps: float = 10.0
    consecutive_years: int = 5
    dividends: List[Dict[str, Any]] = []


@router.post("/dividends/analyze")
async def analyze_dividends(request: DividendAnalysisRequest):
    """Analyze dividend profile for a symbol."""
    if not brain_engine.dividend_intelligence:
        raise HTTPException(status_code=503, detail="Dividend intelligence not initialized")
    from brain.dividends.dividend_intelligence import DividendRecord
    records = [DividendRecord(
        symbol=request.symbol,
        amount_per_share=d.get("amount", 0),
        dividend_type=d.get("type", "final"),
    ) for d in request.dividends]
    result = brain_engine.dividend_intelligence.analyze(
        symbol=request.symbol, current_price=request.current_price,
        dividends=records, eps=request.eps, consecutive_years=request.consecutive_years,
    )
    return result.to_dict()


@router.get("/phase3_8/summary")
async def get_phase3_8_summary():
    """Phase 3.8 summary: Dividend Intelligence."""
    return {
        "phase": "3.8", "name": "Dividend Intelligence",
        "status": "operational" if brain_engine.dividend_intelligence else "not_initialized",
        "metrics": ["Current Yield", "Trailing 12M Dividend", "5Y CAGR", "Payout Ratio",
                     "Consecutive Years", "Sustainability Score"],
        "grades": ["Aristocrat", "Consistent", "Growing", "Irregular", "Non-payer"],
        "api_endpoints": ["POST /api/brain/dividends/analyze"],
    }


# =====================================================================
# Phase 3.9: Regulatory Event Calendar
# =====================================================================

@router.get("/calendar/upcoming")
async def get_upcoming_events(
    days: int = Query(30, description="Number of days to look ahead"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
):
    """Get upcoming regulatory and market events."""
    if not brain_engine.regulatory_calendar:
        raise HTTPException(status_code=503, detail="Regulatory calendar not initialized")
    events = brain_engine.regulatory_calendar.get_upcoming(days=days, event_type=event_type)
    return {"events": events, "count": len(events), "days_ahead": days}


@router.get("/calendar/by-type/{event_type}")
async def get_events_by_type(event_type: str):
    """Get all events of a specific type (rbi, sebi, expiry, earnings, budget, tax)."""
    if not brain_engine.regulatory_calendar:
        raise HTTPException(status_code=503, detail="Regulatory calendar not initialized")
    events = brain_engine.regulatory_calendar.get_by_type(event_type)
    return {"events": events, "count": len(events), "type": event_type}


@router.get("/phase3_9/summary")
async def get_phase3_9_summary():
    """Phase 3.9 summary: Regulatory Event Calendar."""
    cal = brain_engine.regulatory_calendar
    return {
        "phase": "3.9", "name": "Regulatory Event Calendar",
        "status": "operational" if cal else "not_initialized",
        "event_types": ["rbi", "sebi", "expiry", "earnings", "budget", "tax"],
        "total_events": len(cal._events) if cal else 0,
        "api_endpoints": ["GET /api/brain/calendar/upcoming", "GET /api/brain/calendar/by-type/{type}"],
    }


# =====================================================================
# Phase 3.10: SHAP Explainability
# =====================================================================

class ExplainRequest(BaseModel):
    """Request body for model explanation."""
    symbol: str
    model_name: str = "xgboost_direction"


@router.post("/explain/prediction")
async def explain_prediction(request: ExplainRequest):
    """
    Generate SHAP + LIME + NL explanation for a model prediction.
    
    Requires the model to be trained first (via /api/brain/models/train).
    """
    if not brain_engine.explainability_engine:
        raise HTTPException(status_code=503, detail="Explainability engine not initialized")
    
    # Get model from model manager
    if not brain_engine.model_manager:
        raise HTTPException(status_code=503, detail="Model manager not initialized")
    
    # Access the internal _models dict to get the trained model object
    model_obj = brain_engine.model_manager._models.get(request.model_name)
    if model_obj is None:
        available = brain_engine.model_manager.get_loaded_models()
        raise HTTPException(
            status_code=404,
            detail=f"Model '{request.model_name}' not found. Available: {available}"
        )
    
    # Get features for the symbol
    import numpy as np
    try:
        features_data = await brain_engine.feature_pipeline.compute_features(request.symbol)
        # Filter to numeric features only
        numeric_features = {k: v for k, v in features_data.items() if isinstance(v, (int, float)) and not np.isnan(v)}
        feature_names = list(numeric_features.keys())
        feature_values = np.array([list(numeric_features.values())], dtype=np.float64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not compute features for {request.symbol}: {str(e)}")
    
    if len(feature_names) == 0:
        raise HTTPException(status_code=400, detail="No numeric features computed for symbol")

    # Check feature count matches model expectation
    try:
        expected_features = model_obj.n_features_in_ if hasattr(model_obj, 'n_features_in_') else len(feature_names)
        if len(feature_names) != expected_features:
            # Try to match feature names to model's expected features
            if hasattr(model_obj, 'feature_names_in_'):
                model_feature_names = list(model_obj.feature_names_in_)
                matched_values = []
                matched_names = []
                for fn in model_feature_names:
                    if fn in numeric_features:
                        matched_values.append(numeric_features[fn])
                        matched_names.append(fn)
                    else:
                        matched_values.append(0.0)
                        matched_names.append(fn)
                feature_names = matched_names
                feature_values = np.array([matched_values], dtype=np.float64)
    except Exception:
        pass

    result = brain_engine.explainability_engine.explain_prediction(
        symbol=request.symbol,
        model=model_obj,
        model_name=request.model_name,
        features=feature_values.flatten(),
        feature_names=feature_names,
    )
    
    # Generate NL explanation
    await brain_engine.explainability_engine.generate_nl_explanation(result)
    
    return result.to_dict()


@router.get("/phase3_10/summary")
async def get_phase3_10_summary():
    """Phase 3.10 summary: SHAP Explainability."""
    return {
        "phase": "3.10", "name": "SHAP + LIME Explainability",
        "status": "operational" if brain_engine.explainability_engine else "not_initialized",
        "methods": ["SHAP (TreeExplainer)", "LIME (Local Perturbation)", "Natural Language (Gemini LLM)"],
        "compatible_models": ["xgboost_direction", "lightgbm_direction"],
        "api_endpoints": ["POST /api/brain/explain/prediction"],
    }


# =====================================================================
# Complete Phase 3 Summary
# =====================================================================

@router.get("/phase3/complete-summary")
async def get_phase3_complete_summary():
    """Complete Phase 3 summary across all sub-phases."""
    return {
        "phase": "3",
        "name": "Advanced Analytics & Intelligence Layer",
        "sub_phases": {
            "3.1": {
                "name": "HMM Market Regime Detection",
                "status": "operational" if brain_engine.hmm_detector else "not_initialized",
            },
            "3.2": {
                "name": "FinBERT Sentiment Pipeline",
                "status": "operational" if brain_engine.sentiment_aggregator else "not_initialized",
            },
            "3.3": {
                "name": "LLM Multi-Agent System (2-Tier Gemini)",
                "status": "operational" if (brain_engine.agent_orchestrator and brain_engine.agent_orchestrator.is_available) else "not_available",
            },
            "3.4": {
                "name": "Risk Management Engine",
                "status": "operational" if brain_engine.var_calculator else "not_initialized",
            },
            "3.5": {
                "name": "RAG Knowledge Base (Qdrant)",
                "status": "operational" if (brain_engine.rag_knowledge_base and brain_engine.rag_knowledge_base.is_available) else "not_available",
            },
            "3.6": {
                "name": "Corporate Governance Scoring",
                "status": "operational" if brain_engine.governance_scorer else "not_initialized",
            },
            "3.7": {
                "name": "Sector Rotation Engine",
                "status": "operational" if brain_engine.sector_rotation else "not_initialized",
            },
            "3.8": {
                "name": "Dividend Intelligence",
                "status": "operational" if brain_engine.dividend_intelligence else "not_initialized",
            },
            "3.9": {
                "name": "Regulatory Event Calendar",
                "status": "operational" if brain_engine.regulatory_calendar else "not_initialized",
            },
            "3.10": {
                "name": "SHAP + LIME Explainability",
                "status": "operational" if brain_engine.explainability_engine else "not_initialized",
            },
        },
        "total_api_endpoints": 30,
    }

