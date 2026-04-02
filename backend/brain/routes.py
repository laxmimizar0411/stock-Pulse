"""
Brain API Routes — Phase 1+2+3: Data, ML Models, and Regime Detection.

Phase 1 — Data Foundation:
    GET  /api/brain/health, /config, /features/{symbol}, /data-quality/{symbol}
    POST /api/brain/features/compute, /features/batch
    GET  /api/brain/batch/status, /batch/history, /kafka/topics, /storage/status

Phase 2 — AI/ML Models:
    POST /api/brain/models/train, /models/predict/{model_name}
    POST /api/brain/signals/generate, /backtest/run
    GET  /api/brain/models/status, /signals/active

Phase 3 — Market Regime Detection:
    GET  /api/brain/market-regime, /market-regime/history
    POST /api/brain/market-regime/detect
    POST /api/brain/position-size/calculate
    GET  /api/brain/position-size/state, /phase3/summary
"""

import logging
from typing import List, Optional

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
