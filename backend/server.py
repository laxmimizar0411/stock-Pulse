from fastapi import FastAPI, APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import WriteConcern
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import asyncio
from services.mongo_utils import (
    sanitize_symbol, validate_update_fields,
    WATCHLIST_UPDATE_FIELDS, PORTFOLIO_UPDATE_FIELDS,
)
from services.db_dashboard_service import DatabaseDashboardService
from routes.db_dashboard import router as db_dashboard_router, init_dashboard_router
from services.pg_control_service import PgControlService
from routes.pg_control import router as pg_control_router, init_pg_control_router

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from models.stock_models import (
    Stock, WatchlistItem, PortfolioHolding, Portfolio,
    NewsItem, ScreenerRequest, ScreenerFilter, LLMInsightRequest
)
from services.mock_data import (
    get_all_stocks, generate_news_items, generate_market_overview as mock_market_overview, INDIAN_STOCKS
)
from services.scoring_engine import generate_analysis, generate_ml_prediction
from services.llm_service import generate_stock_insight, summarize_news
from services.cache_service import init_cache_service, get_cache_service, CacheService
from services.timeseries_store import init_timeseries_store, get_timeseries_store, TimeSeriesStore

# Import real market data service
try:
    from services.market_data_service import (
        get_stock_quote, get_historical_data, get_market_indices,
        get_bulk_quotes, get_stock_fundamentals, is_real_data_available,
        get_available_symbols, STOCK_SYMBOL_MAP
    )
    REAL_DATA_AVAILABLE = is_real_data_available()
except ImportError:
    REAL_DATA_AVAILABLE = False

# Import WebSocket manager
try:
    from services.websocket_manager import (
        connection_manager, price_broadcaster, handle_websocket_message
    )
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection with production-grade settings
_env = os.environ.get('ENVIRONMENT', 'development').lower()
_default_mongo = 'mongodb://localhost:27017'
mongo_url = os.environ.get('MONGO_URL', _default_mongo)
if _env == 'production':
    if not mongo_url or mongo_url.strip() == '':
        logger.critical("MONGO_URL must be set in production")
        raise SystemExit(1)
    if 'localhost' in mongo_url or '127.0.0.1' in mongo_url:
        logger.critical("MONGO_URL must not point at localhost in production")
        raise SystemExit(1)
db_name = os.environ.get('MONGO_DB_NAME', os.environ.get('DB_NAME', 'stockpulse'))
client = AsyncIOMotorClient(
    mongo_url,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=10000,
    socketTimeoutMS=30000,
    maxPoolSize=20,
    minPoolSize=1,
    retryWrites=True,
    retryReads=True,
)
db = client[db_name]

# Critical collections: majority write concern for durability on replica set (99.9% SLA)
# Writes are acknowledged only after replicated to a majority; journaled for crash safety.
_CRITICAL_WC = WriteConcern(w="majority", j=True)
db.watchlist = db.get_collection("watchlist", write_concern=_CRITICAL_WC)
db.portfolio = db.get_collection("portfolio", write_concern=_CRITICAL_WC)
db.news_articles = db.get_collection("news_articles", write_concern=_CRITICAL_WC)
db.backtest_results = db.get_collection("backtest_results", write_concern=_CRITICAL_WC)
db.alerts = db.get_collection("alerts", write_concern=_CRITICAL_WC)
db.pipeline_jobs = db.get_collection("pipeline_jobs", write_concern=_CRITICAL_WC)
db.stock_data = db.get_collection("stock_data", write_concern=_CRITICAL_WC)

# Redis connection
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
cache = init_cache_service(redis_url)

# PostgreSQL time-series DSN
timeseries_dsn = os.environ.get('TIMESERIES_DSN', 'postgresql://localhost:5432/stockpulse_ts')
_ts_store = None  # initialized async in startup

# Initialize Alerts Service
try:
    from services.alerts_service import init_alerts_service, get_alerts_service
    from models.alert_models import AlertCreate, AlertUpdate, AlertCondition, AlertStatus
    alerts_service = init_alerts_service(db)
    ALERTS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Alerts service not available: {e}")
    ALERTS_AVAILABLE = False
    alerts_service = None

# Import Data Extraction Pipeline
try:
    from data_extraction.pipeline.orchestrator import PipelineOrchestrator
    from data_extraction.models.extraction_models import ExtractionStatus
    EXTRACTION_PIPELINE_AVAILABLE = True
    _pipeline_orchestrator = None  # Lazy initialization
except ImportError as e:
    logger.warning(f"Data extraction pipeline not available: {e}")
    EXTRACTION_PIPELINE_AVAILABLE = False
    _pipeline_orchestrator = None

# Import Data Pipeline Service (Groww API)
try:
    from services.pipeline_service import init_pipeline_service, get_pipeline_service, DataPipelineService
    from models.pipeline_models import (
        RunExtractionRequest, RunExtractionResponse, StartSchedulerRequest,
        LogsResponse, DataSummaryResponse, APITestRequest, APITestResponse,
        PipelineStatusResponse, JobResponse
    )
    GROW_TOTP_TOKEN = os.environ.get('GROW_TOTP_TOKEN', '')
    GROW_SECRET_KEY = os.environ.get('GROW_SECRET_KEY', '')
    PIPELINE_SERVICE_AVAILABLE = bool(GROW_TOTP_TOKEN and GROW_SECRET_KEY)
    _data_pipeline_service = None
except ImportError as e:
    logger.warning(f"Data pipeline service not available: {e}")
    PIPELINE_SERVICE_AVAILABLE = False
    _data_pipeline_service = None
    GROW_TOTP_TOKEN = ''
    GROW_SECRET_KEY = ''

# Import NSE Bhavcopy Extractor
try:
    from data_extraction.extractors.nse_bhavcopy_extractor import NSEBhavcopyExtractor, get_bhavcopy_extractor
    NSE_BHAVCOPY_AVAILABLE = True
    _bhavcopy_extractor = None
except ImportError as e:
    logger.warning(f"NSE Bhavcopy extractor not available: {e}")
    NSE_BHAVCOPY_AVAILABLE = False
    _bhavcopy_extractor = None

# Import Screener.in Extractor
try:
    from data_extraction.extractors.screener_extractor import ScreenerExtractor, get_screener_extractor
    SCREENER_AVAILABLE = True
    _screener_extractor = None
except ImportError as e:
    logger.warning(f"Screener.in extractor not available: {e}")
    SCREENER_AVAILABLE = False
    _screener_extractor = None
    PIPELINE_SERVICE_AVAILABLE = False
    _data_pipeline_service = None
    GROW_TOTP_TOKEN = ''
    GROW_SECRET_KEY = ''

# Configuration
USE_REAL_DATA = os.environ.get('USE_REAL_DATA', 'true').lower() == 'true'

# Create the main app
app = FastAPI(title="Stock Analysis Platform API", version="1.0.0")

# Create router with /api prefix
api_router = APIRouter(prefix="/api")

# Log data source status
logger.info(f"Real data available: {REAL_DATA_AVAILABLE}")
logger.info(f"Use real data: {USE_REAL_DATA}")
logger.info(f"Data source: {'Real (Yahoo Finance)' if REAL_DATA_AVAILABLE and USE_REAL_DATA else 'Mock Data'}")

# Cache TTL constants (used with Redis cache service)
CACHE_TTL = 300  # 5 minutes for mock data
REAL_CACHE_TTL = 60  # 1 minute for real data


def _get_cap_category(market_cap: float) -> str:
    """Determine market cap category based on Indian market standards"""
    if market_cap >= 200000000000:  # 20,000 Cr+
        return "Large"
    elif market_cap >= 50000000000:  # 5,000 Cr+
        return "Mid"
    else:
        return "Small"


def _calculate_technicals(history: list, quote: dict) -> dict:
    """Calculate technical indicators from historical price data"""
    if not history or len(history) < 20:
        return {
            "sma_50": quote.get("current_price", 0),
            "sma_200": quote.get("current_price", 0),
            "rsi_14": 50,
            "high_52_week": quote.get("fifty_two_week_high", 0),
            "low_52_week": quote.get("fifty_two_week_low", 0),
            "volume_avg_20": quote.get("avg_volume", 0),
        }
    
    closes = [h["close"] for h in history]
    
    # Calculate SMAs
    sma_50 = sum(closes[-50:]) / min(50, len(closes)) if len(closes) >= 20 else closes[-1]
    sma_200 = sum(closes[-200:]) / min(200, len(closes)) if len(closes) >= 50 else closes[-1]
    
    # Calculate RSI (simplified)
    gains = []
    losses = []
    for i in range(1, min(15, len(closes))):
        diff = closes[-i] - closes[-i-1]
        if diff > 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))
    
    avg_gain = sum(gains) / 14 if gains else 0
    avg_loss = sum(losses) / 14 if losses else 0.001
    rs = avg_gain / avg_loss if avg_loss > 0 else 100
    rsi = 100 - (100 / (1 + rs))
    
    return {
        "sma_50": round(sma_50, 2),
        "sma_200": round(sma_200, 2),
        "rsi_14": round(rsi, 2),
        "high_52_week": quote.get("fifty_two_week_high", max(closes) if closes else 0),
        "low_52_week": quote.get("fifty_two_week_low", min(closes) if closes else 0),
        "volume_avg_20": quote.get("avg_volume", 0),
        "support_level": round(min(closes[-20:]) * 0.98, 2) if len(closes) >= 20 else 0,
        "resistance_level": round(max(closes[-20:]) * 1.02, 2) if len(closes) >= 20 else 0,
    }

# Helper functions
def get_cached_stocks():
    """Get stock data with Redis caching (fallback to in-memory)."""
    cached = cache.get_stock_list() if cache else None
    if cached is not None:
        return cached
    
    stocks = get_all_stocks()
    stock_map = {s["symbol"]: s for s in stocks}
    if cache:
        cache.set_stock_list(stock_map)
    return stock_map


# ==================== HEALTH CHECK ====================
@api_router.get("/")
async def root():
    return {"message": "Stock Analysis Platform API", "status": "healthy"}


@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@api_router.get("/database/health")
async def database_health_check():
    """Comprehensive health check for all database layers.

    Returns connectivity status, row counts, and diagnostics for
    PostgreSQL, MongoDB, Redis, and filesystem directories.
    """
    health = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "postgresql": {"status": "not_initialized"},
        "mongodb": {"status": "unknown"},
        "redis": {"status": "unknown"},
        "filesystem": {"status": "unknown"},
    }

    # --- PostgreSQL ---
    if _ts_store and _ts_store._is_initialized:
        try:
            stats = await _ts_store.get_stats()
            health["postgresql"] = {
                "status": "connected",
                "tables": stats,
            }
        except Exception as e:
            health["postgresql"] = {"status": "error", "error": str(e)}
    else:
        health["postgresql"]["message"] = (
            "Time-series store not initialized. "
            "Ensure PostgreSQL is running and TIMESERIES_DSN is set."
        )

    # --- MongoDB ---
    try:
        await db.command("ping")
        collections = await db.list_collection_names()
        coll_stats = {}
        for coll_name in sorted(collections):
            count = await db[coll_name].count_documents({})
            coll_stats[coll_name] = {"documents": count}
        mongo_health = {
            "status": "connected",
            "database": db_name,
            "collections_count": len(collections),
            "collections": coll_stats,
        }
        # Replica set status (only when connected to a replica set)
        try:
            rs_status = await client.admin.command("replSetGetStatus")
            members = []
            for m in rs_status.get("members", []):
                optime = m.get("optimeDate")
                members.append({
                    "name": m.get("name"),
                    "stateStr": m.get("stateStr"),
                    "health": m.get("health"),
                    "optimeDate": getattr(optime, "isoformat", lambda: str(optime))() if optime else None,
                })
            mongo_health["replica_set"] = {
                "set": rs_status.get("set"),
                "myState": rs_status.get("myState"),
                "members": members,
            }
        except Exception:
            pass  # Standalone or not a replica set
        health["mongodb"] = mongo_health
    except Exception as e:
        health["mongodb"] = {"status": "error", "error": str(e)}

    # --- Redis ---
    if cache and cache.is_redis_available:
        health["redis"] = {
            "status": "connected",
            **cache.get_stats(),
        }
    else:
        health["redis"] = {
            "status": "fallback",
            "message": "Using in-memory cache (Redis not available)",
            **(cache.get_stats() if cache else {}),
        }

    # --- Filesystem ---
    base = Path(__file__).parent
    dirs_to_check = ["reports", "data/bhavcopy", "models", "cache/html", "backups"]
    dir_status = {}
    for d in dirs_to_check:
        full = base / d
        dir_status[d] = {
            "exists": full.exists(),
            "writable": os.access(full, os.W_OK) if full.exists() else False,
        }
    health["filesystem"] = {"status": "ok", "directories": dir_status}

    # --- Overall ---
    pg_ok = health["postgresql"]["status"] == "connected"
    mongo_ok = health["mongodb"]["status"] == "connected"
    redis_ok = health["redis"]["status"] in ("connected", "fallback")
    health["overall"] = "healthy" if (pg_ok and mongo_ok and redis_ok) else "degraded"

    return health


@api_router.get("/cache/stats")
async def get_cache_stats():
    """Get Redis cache statistics"""
    if not cache:
        return {"status": "unavailable", "message": "Cache service not initialized"}
    return {
        "status": "active",
        **cache.get_stats()
    }


@api_router.delete("/cache/flush")
async def flush_cache():
    """Flush all cache entries (admin operation)"""
    if cache:
        cache.invalidate_all()
        return {"message": "Cache flushed successfully"}
    return {"message": "Cache not available"}


@api_router.get("/timeseries/stats")
async def get_timeseries_stats():
    """Get PostgreSQL time-series database statistics"""
    if not _ts_store:
        return {"status": "unavailable", "message": "Time-series store not initialized"}
    try:
        stats = await _ts_store.get_stats()
        return {"status": "active", **stats}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@api_router.get("/timeseries/prices/{symbol}")
async def get_timeseries_prices(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(default=500, le=5000)
):
    """Get historical OHLCV data from PostgreSQL time-series store"""
    if not _ts_store:
        raise HTTPException(status_code=503, detail="Time-series store not available")
    
    prices = await _ts_store.get_prices(
        symbol.upper(), start_date=start_date, end_date=end_date, limit=limit
    )
    return {
        "symbol": symbol.upper(),
        "count": len(prices),
        "data": prices
    }


@api_router.get("/timeseries/derived-metrics/{symbol}")
async def get_timeseries_derived_metrics(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(default=500, le=5000),
):
    """Get derived price metrics from PostgreSQL"""
    if not _ts_store:
        raise HTTPException(status_code=503, detail="Time-series store not available")
    data = await _ts_store.get_derived_metrics(symbol.upper(), start_date=start_date, end_date=end_date, limit=limit)
    return {"symbol": symbol.upper(), "count": len(data), "data": data}


@api_router.get("/timeseries/valuation/{symbol}")
async def get_timeseries_valuation(
    symbol: str,
    limit: int = Query(default=500, le=5000),
):
    """Get valuation metrics from PostgreSQL"""
    if not _ts_store:
        raise HTTPException(status_code=503, detail="Time-series store not available")
    data = await _ts_store.get_valuation(symbol.upper(), limit=limit)
    return {"symbol": symbol.upper(), "count": len(data), "data": data}


@api_router.get("/timeseries/ml-features/{symbol}")
async def get_timeseries_ml_features(
    symbol: str,
    limit: int = Query(default=500, le=5000),
):
    """Get ML/strategy features from PostgreSQL"""
    if not _ts_store:
        raise HTTPException(status_code=503, detail="Time-series store not available")
    data = await _ts_store.get_ml_features(symbol.upper(), limit=limit)
    return {"symbol": symbol.upper(), "count": len(data), "data": data}


@api_router.get("/timeseries/risk-metrics/{symbol}")
async def get_timeseries_risk_metrics(
    symbol: str,
    limit: int = Query(default=500, le=5000),
):
    """Get risk & performance metrics from PostgreSQL"""
    if not _ts_store:
        raise HTTPException(status_code=503, detail="Time-series store not available")
    data = await _ts_store.get_risk_metrics(symbol.upper(), limit=limit)
    return {"symbol": symbol.upper(), "count": len(data), "data": data}


@api_router.get("/timeseries/corporate-actions/{symbol}")
async def get_timeseries_corporate_actions(
    symbol: str,
    limit: int = Query(default=50, le=500),
):
    """Get corporate actions from PostgreSQL"""
    if not _ts_store:
        raise HTTPException(status_code=503, detail="Time-series store not available")
    data = await _ts_store.get_corporate_actions(symbol.upper(), limit=limit)
    return {"symbol": symbol.upper(), "count": len(data), "data": data}


@api_router.get("/timeseries/macro-indicators")
async def get_timeseries_macro_indicators(
    limit: int = Query(default=60, le=500),
):
    """Get macro indicators from PostgreSQL (no symbol required)"""
    if not _ts_store:
        raise HTTPException(status_code=503, detail="Time-series store not available")
    data = await _ts_store.get_macro_indicators(limit=limit)
    return {"count": len(data), "data": data}


@api_router.get("/timeseries/derivatives/{symbol}")
async def get_timeseries_derivatives(
    symbol: str,
    limit: int = Query(default=500, le=5000),
):
    """Get F&O / derivatives data from PostgreSQL"""
    if not _ts_store:
        raise HTTPException(status_code=503, detail="Time-series store not available")
    data = await _ts_store.get_derivatives(symbol.upper(), limit=limit)
    return {"symbol": symbol.upper(), "count": len(data), "data": data}


@api_router.get("/timeseries/intraday/{symbol}")
async def get_timeseries_intraday(
    symbol: str,
    start_ts: Optional[str] = None,
    end_ts: Optional[str] = None,
    limit: int = Query(default=500, le=5000),
):
    """Get intraday/hourly metrics from PostgreSQL"""
    if not _ts_store:
        raise HTTPException(status_code=503, detail="Time-series store not available")
    data = await _ts_store.get_intraday_metrics(symbol.upper(), start_ts=start_ts, end_ts=end_ts, limit=limit)
    return {"symbol": symbol.upper(), "count": len(data), "data": data}


@api_router.get("/timeseries/weekly-metrics/{symbol}")
async def get_timeseries_weekly_metrics(
    symbol: str,
    limit: int = Query(default=104, le=1000),
):
    """Get weekly metrics from PostgreSQL"""
    if not _ts_store:
        raise HTTPException(status_code=503, detail="Time-series store not available")
    data = await _ts_store.get_weekly_metrics(symbol.upper(), limit=limit)
    return {"symbol": symbol.upper(), "count": len(data), "data": data}


@api_router.get("/timeseries/technicals/{symbol}")
async def get_timeseries_technicals(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(default=500, le=5000),
):
    """Get technical indicators from PostgreSQL"""
    if not _ts_store:
        raise HTTPException(status_code=503, detail="Time-series store not available")
    data = await _ts_store.get_technicals(symbol.upper(), start_date=start_date, end_date=end_date, limit=limit)
    return {"symbol": symbol.upper(), "count": len(data), "data": data}


@api_router.get("/timeseries/fundamentals/{symbol}")
async def get_timeseries_fundamentals(
    symbol: str,
    period_type: str = "quarterly",
    limit: int = Query(default=40, le=200),
):
    """Get quarterly/annual fundamentals from PostgreSQL"""
    if not _ts_store:
        raise HTTPException(status_code=503, detail="Time-series store not available")
    data = await _ts_store.get_fundamentals(symbol.upper(), period_type=period_type, limit=limit)
    return {"symbol": symbol.upper(), "count": len(data), "data": data}


@api_router.get("/timeseries/shareholding/{symbol}")
async def get_timeseries_shareholding(
    symbol: str,
    limit: int = Query(default=28, le=200),
):
    """Get quarterly shareholding from PostgreSQL"""
    if not _ts_store:
        raise HTTPException(status_code=503, detail="Time-series store not available")
    data = await _ts_store.get_shareholding(symbol.upper(), limit=limit)
    return {"symbol": symbol.upper(), "count": len(data), "data": data}


# ==================== MARKET OVERVIEW ====================
@api_router.get("/market/overview")
async def get_market_overview():
    """Get market overview including indices, breadth, and sector performance"""
    # Check Redis cache first (60s TTL)
    if cache:
        cached = cache.get("market:overview")
        if cached is not None:
            return cached
    
    # Try real data first
    overview = None
    if REAL_DATA_AVAILABLE and USE_REAL_DATA:
        try:
            indices = await get_market_indices()
            if indices:
                overview = mock_market_overview()
                overview.update(indices)
        except Exception as e:
            logger.error(f"Real data failed, falling back to mock: {e}")
    
    if overview is None:
        overview = mock_market_overview()
    
    # Cache in Redis
    if cache:
        cache.set("market:overview", overview, 60)
    
    return overview


# ==================== STOCKS ====================
@api_router.get("/stocks", response_model=List[Dict[str, Any]])
async def get_stocks(
    sector: Optional[str] = None,
    cap: Optional[str] = None,
    limit: int = Query(default=50, le=100)
):
    """Get list of stocks with optional filtering"""
    stocks = list(get_cached_stocks().values())
    
    if sector:
        stocks = [s for s in stocks if s["sector"].lower() == sector.lower()]
    if cap:
        stocks = [s for s in stocks if s["market_cap_category"].lower() == cap.lower()]
    
    # Sort by market cap
    stocks.sort(key=lambda x: x["valuation"]["market_cap"], reverse=True)
    
    return stocks[:limit]


@api_router.get("/stocks/{symbol}")
async def get_stock(symbol: str):
    """Get detailed stock data including analysis"""
    symbol = symbol.upper()
    
    # Try real data first
    if REAL_DATA_AVAILABLE and USE_REAL_DATA:
        try:
            quote = await get_stock_quote(symbol)
            history = await get_historical_data(symbol, period="3mo", interval="1d")
            fundamentals = await get_stock_fundamentals(symbol)
            
            if quote:
                # Build stock data from real quote
                stock_data = {
                    "symbol": symbol,
                    "name": quote.get("name", symbol),
                    "sector": quote.get("sector", "Unknown"),
                    "industry": quote.get("industry", "Unknown"),
                    "market_cap_category": _get_cap_category(quote.get("market_cap", 0)),
                    "current_price": quote.get("current_price", 0),
                    "price_change": quote.get("price_change", 0),
                    "price_change_percent": quote.get("price_change_percent", 0),
                    "fundamentals": fundamentals or {},
                    "valuation": {
                        "pe_ratio": quote.get("pe_ratio", 0),
                        "pb_ratio": quote.get("pb_ratio", 0),
                        "dividend_yield": quote.get("dividend_yield", 0),
                        "market_cap": quote.get("market_cap", 0),
                    },
                    "technicals": _calculate_technicals(history, quote),
                    "shareholding": {},  # Not available from Yahoo Finance
                    "price_history": history[-90:] if history else [],
                }
                
                # Generate analysis
                stock_data["analysis"] = generate_analysis(stock_data)
                stock_data["ml_prediction"] = generate_ml_prediction(stock_data)
                
                return stock_data
        except Exception as e:
            logger.error(f"Real data failed for {symbol}, falling back to mock: {e}")
    
    # Fallback to mock data
    stocks = get_cached_stocks()
    
    if symbol not in stocks:
        raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")
    
    stock_data = stocks[symbol].copy()
    stock_data["analysis"] = generate_analysis(stock_data)
    stock_data["ml_prediction"] = generate_ml_prediction(stock_data)
    
    return stock_data


@api_router.get("/stocks/{symbol}/analysis")
async def get_stock_analysis(symbol: str):
    """Get detailed analysis for a stock (with Redis caching)"""
    symbol = symbol.upper()
    
    # Check cache first
    if cache:
        cached_result = cache.get_analysis(symbol)
        if cached_result is not None:
            return cached_result
    
    stocks = get_cached_stocks()
    
    if symbol not in stocks:
        raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")
    
    stock_data = stocks[symbol]
    analysis = generate_analysis(stock_data)
    ml_prediction = generate_ml_prediction(stock_data)
    
    result = {
        "symbol": symbol,
        "name": stock_data["name"],
        "current_price": stock_data["current_price"],
        "analysis": analysis,
        "ml_prediction": ml_prediction
    }
    
    # Cache the result
    if cache:
        cache.set_analysis(symbol, result)
    
    return result


@api_router.post("/stocks/{symbol}/llm-insight")
async def get_llm_insight(symbol: str, request: LLMInsightRequest):
    """Get AI-powered insight for a stock"""
    stocks = get_cached_stocks()
    symbol = symbol.upper()
    
    if symbol not in stocks:
        raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")
    
    stock_data = stocks[symbol].copy()
    stock_data["analysis"] = generate_analysis(stock_data)
    
    insight = await generate_stock_insight(stock_data, request.analysis_type)
    
    return {
        "symbol": symbol,
        "analysis_type": request.analysis_type,
        "insight": insight
    }


# ==================== SCREENER ====================
@api_router.post("/screener")
async def screen_stocks(request: ScreenerRequest):
    """Screen stocks based on multiple criteria.

    Uses PostgreSQL cross-table JOINs when available (prices + technicals +
    fundamentals + shareholding). Falls back to in-memory filtering over
    cached mock data when PostgreSQL is not connected.
    """
    # --- Try PostgreSQL path first (fast, supports cross-table filters) ---
    if _ts_store:
        try:
            # Check if screener results are cached in Redis
            import hashlib, json as _json
            filter_hash = hashlib.md5(
                _json.dumps([f.model_dump() for f in request.filters], sort_keys=True, default=str).encode()
            ).hexdigest()[:12]
            cache_key = f"screener:{filter_hash}"

            cached = cache.get(cache_key) if cache else None
            if cached is not None:
                return cached

            filters_for_pg = [
                {"metric": f.metric, "operator": f.operator, "value": f.value, "value2": f.value2}
                for f in request.filters
            ]
            pg_results = await _ts_store.get_screener_data(
                filters=filters_for_pg,
                sort_by=request.sort_by,
                sort_order=request.sort_order,
                limit=request.limit,
            )

            if pg_results:
                response = {"count": len(pg_results), "stocks": pg_results, "source": "postgresql"}
                if cache:
                    cache.set(cache_key, response, 120)  # 2 min cache
                return response
        except Exception as e:
            logger.debug(f"PostgreSQL screener fallback: {e}")

    # --- Fallback: in-memory filtering over mock/cached data ---
    stocks = list(get_cached_stocks().values())
    results = []

    for stock in stocks:
        passes_all = True
        fund = stock.get("fundamentals", {})
        val = stock.get("valuation", {})
        tech = stock.get("technicals", {})
        share = stock.get("shareholding", {})

        all_metrics = {
            **fund, **val, **tech, **share,
            "current_price": stock.get("current_price", 0),
            "price_change_percent": stock.get("price_change_percent", 0),
            "market_cap": val.get("market_cap", 0),
        }

        for f in request.filters:
            value = all_metrics.get(f.metric, 0)

            if f.operator == "gt" and not (value > f.value):
                passes_all = False
            elif f.operator == "lt" and not (value < f.value):
                passes_all = False
            elif f.operator == "gte" and not (value >= f.value):
                passes_all = False
            elif f.operator == "lte" and not (value <= f.value):
                passes_all = False
            elif f.operator == "eq" and not (value == f.value):
                passes_all = False
            elif f.operator == "between" and f.value2 is not None:
                if not (f.value <= value <= f.value2):
                    passes_all = False

            if not passes_all:
                break

        if passes_all:
            analysis = generate_analysis(stock)
            results.append({
                **stock,
                "analysis": analysis
            })

    # Sort results
    sort_key = request.sort_by
    reverse = request.sort_order == "desc"

    def get_sort_value(s):
        if sort_key == "market_cap":
            return s.get("valuation", {}).get("market_cap", 0)
        elif sort_key == "score":
            return s.get("analysis", {}).get("long_term_score", 0)
        elif sort_key in s.get("fundamentals", {}):
            return s["fundamentals"].get(sort_key, 0)
        elif sort_key in s.get("valuation", {}):
            return s["valuation"].get(sort_key, 0)
        return s.get(sort_key, 0)

    results.sort(key=get_sort_value, reverse=reverse)

    return {
        "count": len(results),
        "stocks": results[:request.limit],
        "source": "in_memory"
    }


@api_router.get("/screener/presets")
async def get_screener_presets():
    """Get pre-built screener filters"""
    return [
        {
            "id": "quality_value",
            "name": "Quality + Value",
            "description": "High ROE, low debt, reasonable valuation",
            "filters": [
                {"metric": "roe", "operator": "gt", "value": 15},
                {"metric": "debt_to_equity", "operator": "lt", "value": 1},
                {"metric": "pe_ratio", "operator": "lt", "value": 30},
            ]
        },
        {
            "id": "high_growth",
            "name": "High Growth Momentum",
            "description": "Strong revenue growth with technical strength",
            "filters": [
                {"metric": "revenue_growth_yoy", "operator": "gt", "value": 15},
                {"metric": "rsi_14", "operator": "between", "value": 40, "value2": 70},
            ]
        },
        {
            "id": "dividend_champions",
            "name": "Dividend Champions",
            "description": "High dividend yield with sustainable payout",
            "filters": [
                {"metric": "dividend_yield", "operator": "gt", "value": 2},
                {"metric": "debt_to_equity", "operator": "lt", "value": 1.5},
            ]
        },
        {
            "id": "oversold_quality",
            "name": "Oversold Quality",
            "description": "Technically oversold but fundamentally strong",
            "filters": [
                {"metric": "rsi_14", "operator": "lt", "value": 40},
                {"metric": "roe", "operator": "gt", "value": 12},
            ]
        },
        {
            "id": "low_debt_leaders",
            "name": "Low Debt Leaders",
            "description": "Virtually debt-free companies",
            "filters": [
                {"metric": "debt_to_equity", "operator": "lt", "value": 0.3},
                {"metric": "interest_coverage", "operator": "gt", "value": 10},
            ]
        },
    ]


# ==================== WATCHLIST ====================
@api_router.get("/watchlist")
async def get_watchlist():
    """Get user's watchlist"""
    watchlist = await db.watchlist.find({}, {"_id": 0}).to_list(100)
    
    # Enrich with current data
    stocks = get_cached_stocks()
    enriched = []
    
    for item in watchlist:
        symbol = item.get("symbol", "")
        if symbol in stocks:
            stock = stocks[symbol]
            analysis = generate_analysis(stock)
            enriched.append({
                **item,
                "current_price": stock["current_price"],
                "price_change": stock["price_change"],
                "price_change_percent": stock["price_change_percent"],
                "score": analysis["long_term_score"],
                "verdict": analysis["verdict"],
            })
        else:
            enriched.append(item)
    
    return enriched


@api_router.post("/watchlist")
async def add_to_watchlist(item: WatchlistItem):
    """Add stock to watchlist"""
    # Check if already exists
    existing = await db.watchlist.find_one({"symbol": item.symbol})
    if existing:
        raise HTTPException(status_code=400, detail="Stock already in watchlist")
    
    doc = item.model_dump()
    doc["added_date"] = doc["added_date"].isoformat()
    
    # Create a copy for insertion (MongoDB modifies the original dict)
    insert_doc = {**doc}
    await db.watchlist.insert_one(insert_doc)
    
    # Return the original doc without _id
    return {"message": "Added to watchlist", "item": doc}


@api_router.delete("/watchlist/{symbol}")
async def remove_from_watchlist(symbol: str):
    """Remove stock from watchlist"""
    try:
        clean_symbol = sanitize_symbol(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = await db.watchlist.delete_one({"symbol": clean_symbol})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Stock not in watchlist")
    return {"message": "Removed from watchlist"}


@api_router.put("/watchlist/{symbol}")
async def update_watchlist_item(symbol: str, updates: Dict[str, Any]):
    """Update watchlist item (target price, stop loss, notes)"""
    try:
        clean_symbol = sanitize_symbol(symbol)
        safe_updates = validate_update_fields(updates, WATCHLIST_UPDATE_FIELDS)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not safe_updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    result = await db.watchlist.update_one(
        {"symbol": clean_symbol},
        {"$set": safe_updates}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Stock not in watchlist")
    return {"message": "Updated successfully"}


# ==================== PORTFOLIO ====================
@api_router.get("/portfolio")
async def get_portfolio():
    """Get user's portfolio"""
    holdings = await db.portfolio.find({}, {"_id": 0}).to_list(100)
    
    if not holdings:
        return {
            "holdings": [],
            "total_invested": 0,
            "current_value": 0,
            "total_profit_loss": 0,
            "total_profit_loss_percent": 0,
            "xirr": 0,
            "sector_allocation": [],
        }
    
    stocks = get_cached_stocks()
    enriched_holdings = []
    total_invested = 0
    current_value = 0
    sector_allocation = {}
    
    for holding in holdings:
        symbol = holding.get("symbol", "")
        qty = holding.get("quantity", 0)
        avg_price = holding.get("avg_buy_price", 0)
        invested = qty * avg_price
        total_invested += invested
        
        if symbol in stocks:
            stock = stocks[symbol]
            curr_price = stock["current_price"]
            curr_val = qty * curr_price
            current_value += curr_val
            pl = curr_val - invested
            pl_pct = (pl / invested) * 100 if invested > 0 else 0
            
            sector = stock.get("sector", "Other")
            sector_allocation[sector] = sector_allocation.get(sector, 0) + curr_val
            
            enriched_holdings.append({
                **holding,
                "current_price": curr_price,
                "current_value": round(curr_val, 2),
                "profit_loss": round(pl, 2),
                "profit_loss_percent": round(pl_pct, 2),
                "sector": sector,
            })
        else:
            enriched_holdings.append(holding)
    
    total_pl = current_value - total_invested
    total_pl_pct = (total_pl / total_invested) * 100 if total_invested > 0 else 0
    
    # Convert sector allocation to list
    sector_list = [
        {"sector": k, "value": round(v, 2), "percent": round((v / current_value) * 100, 2) if current_value > 0 else 0}
        for k, v in sorted(sector_allocation.items(), key=lambda x: x[1], reverse=True)
    ]
    
    return {
        "holdings": enriched_holdings,
        "total_invested": round(total_invested, 2),
        "current_value": round(current_value, 2),
        "total_profit_loss": round(total_pl, 2),
        "total_profit_loss_percent": round(total_pl_pct, 2),
        "xirr": round(total_pl_pct * 1.2, 2),  # Simplified XIRR approximation
        "sector_allocation": sector_list,
    }


@api_router.post("/portfolio")
async def add_to_portfolio(holding: PortfolioHolding):
    """Add holding to portfolio"""
    doc = holding.model_dump()
    
    # Check if stock already exists, update quantity if so
    existing = await db.portfolio.find_one({"symbol": holding.symbol})
    if existing:
        # Average out the buy price
        total_qty = existing.get("quantity", 0) + holding.quantity
        total_value = (existing.get("quantity", 0) * existing.get("avg_buy_price", 0)) + (holding.quantity * holding.avg_buy_price)
        new_avg = total_value / total_qty if total_qty > 0 else 0
        
        await db.portfolio.update_one(
            {"symbol": holding.symbol},
            {"$set": {"quantity": total_qty, "avg_buy_price": round(new_avg, 2)}}
        )
        return {"message": "Updated existing holding"}
    
    # Create a copy for insertion (MongoDB modifies the original dict)
    insert_doc = {**doc}
    await db.portfolio.insert_one(insert_doc)
    
    # Return the original doc without _id
    return {"message": "Added to portfolio", "holding": doc}


@api_router.delete("/portfolio/{symbol}")
async def remove_from_portfolio(symbol: str):
    """Remove holding from portfolio"""
    try:
        clean_symbol = sanitize_symbol(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = await db.portfolio.delete_one({"symbol": clean_symbol})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Holding not found")
    return {"message": "Removed from portfolio"}


@api_router.put("/portfolio/{symbol}")
async def update_portfolio_holding(symbol: str, updates: Dict[str, Any]):
    """Update portfolio holding"""
    try:
        clean_symbol = sanitize_symbol(symbol)
        safe_updates = validate_update_fields(updates, PORTFOLIO_UPDATE_FIELDS)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not safe_updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    result = await db.portfolio.update_one(
        {"symbol": clean_symbol},
        {"$set": safe_updates}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Holding not found")
    return {"message": "Updated successfully"}


# ==================== NEWS ====================
@api_router.get("/news")
async def get_news(
    symbol: Optional[str] = None,
    sentiment: Optional[str] = None,
    limit: int = Query(default=20, le=50)
):
    """Get market news with sentiment (persisted to MongoDB)"""
    # Check if we have recent news in MongoDB (< 3 minutes old)
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    
    mongo_news = []
    try:
        query = {"stored_at": {"$gte": cutoff}}
        if symbol:
            query["related_stocks"] = symbol.upper()
        if sentiment:
            query["sentiment"] = sentiment.upper()

        cursor = db.news_articles.find(query, {"_id": 0}).sort("published_date", -1).limit(limit)
        mongo_news = await cursor.to_list(length=limit)
    except Exception as e:
        logger.warning(f"Failed to fetch news from MongoDB: {e}")
    
    if mongo_news:
        return mongo_news
    
    # Generate fresh news and persist
    news = generate_news_items()
    
    # Persist to MongoDB
    try:
        now = datetime.now(timezone.utc).isoformat()
        for article in news:
            article["stored_at"] = now
            await db.news_articles.update_one(
                {"title": article.get("title")},
                {"$set": article},
                upsert=True
            )
    except Exception as e:
        logger.warning(f"Failed to persist news: {e}")
    
    if symbol:
        news = [n for n in news if symbol.upper() in n.get("related_stocks", [])]
    if sentiment:
        news = [n for n in news if n.get("sentiment", "").upper() == sentiment.upper()]
    
    return news[:limit]


@api_router.get("/news/summary")
async def get_news_summary():
    """Get AI-generated news summary"""
    news = generate_news_items()
    summary = await summarize_news(news[:10])

    return {
        "summary": summary,
        "news_count": len(news),
        "positive_count": len([n for n in news if n["sentiment"] == "POSITIVE"]),
        "negative_count": len([n for n in news if n["sentiment"] == "NEGATIVE"]),
        "neutral_count": len([n for n in news if n["sentiment"] == "NEUTRAL"]),
    }


# ==================== NEWS ARTICLES PERSISTENCE ====================

class NewsArticleCreate(BaseModel):
    title: str
    summary: str = ""
    source: str = ""
    url: str = ""
    published_date: Optional[str] = None
    sentiment: str = "NEUTRAL"
    sentiment_score: float = 0.0
    related_stocks: List[str] = []
    tags: List[str] = []


@api_router.get("/news/articles")
async def get_persisted_news(
    symbol: Optional[str] = None,
    sentiment: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(default=50, le=200)
):
    """Get persisted news articles from MongoDB"""
    query = {}
    if symbol:
        query["related_stocks"] = symbol.upper()
    if sentiment:
        query["sentiment"] = sentiment.upper()
    if source:
        query["source"] = source

    cursor = (
        db.news_articles
        .find(query, {"_id": 0})
        .sort("published_date", -1)
        .limit(limit)
    )
    articles = await cursor.to_list(length=limit)
    return {"count": len(articles), "articles": articles}


@api_router.post("/news/articles")
async def create_news_article(article: NewsArticleCreate):
    """Persist a news article to MongoDB"""
    doc = article.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    if not doc.get("published_date"):
        doc["published_date"] = doc["created_at"]
    doc["related_stocks"] = [s.upper() for s in doc.get("related_stocks", [])]

    insert_doc = {**doc}
    await db.news_articles.insert_one(insert_doc)
    return {"message": "Article saved", "id": doc["id"], "article": doc}


@api_router.post("/news/articles/bulk")
async def bulk_create_news_articles(articles: List[NewsArticleCreate]):
    """Persist multiple news articles at once"""
    docs = []
    for article in articles:
        doc = article.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        if not doc.get("published_date"):
            doc["published_date"] = doc["created_at"]
        doc["related_stocks"] = [s.upper() for s in doc.get("related_stocks", [])]
        docs.append(doc)

    if docs:
        await db.news_articles.insert_many(docs)

    return {"message": f"Saved {len(docs)} articles", "count": len(docs)}


@api_router.get("/news/articles/{article_id}")
async def get_news_article(article_id: str):
    """Get a specific news article by ID"""
    article = await db.news_articles.find_one({"id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@api_router.delete("/news/articles/{article_id}")
async def delete_news_article(article_id: str):
    """Delete a news article"""
    result = await db.news_articles.delete_one({"id": article_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"message": "Article deleted"}


@api_router.get("/news/articles/stats/summary")
async def get_news_stats():
    """Get news article statistics"""
    total = await db.news_articles.count_documents({})
    positive = await db.news_articles.count_documents({"sentiment": "POSITIVE"})
    negative = await db.news_articles.count_documents({"sentiment": "NEGATIVE"})
    neutral = await db.news_articles.count_documents({"sentiment": "NEUTRAL"})

    # Get unique sources
    pipeline = [
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    sources = await db.news_articles.aggregate(pipeline).to_list(50)

    return {
        "total_articles": total,
        "by_sentiment": {
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
        },
        "by_source": [{"source": s["_id"], "count": s["count"]} for s in sources if s["_id"]],
    }


# ==================== REPORTS ====================
class ReportRequest(BaseModel):
    report_type: str  # single_stock, comparison, portfolio_health
    symbols: List[str] = []


@api_router.post("/reports/generate")
async def generate_report(request: ReportRequest):
    """Generate analysis report"""
    stocks = get_cached_stocks()
    
    if request.report_type == "single_stock":
        if not request.symbols:
            raise HTTPException(status_code=400, detail="Symbol required")
        
        symbol = request.symbols[0].upper()
        if symbol not in stocks:
            raise HTTPException(status_code=404, detail="Stock not found")
        
        stock = stocks[symbol].copy()
        stock["analysis"] = generate_analysis(stock)
        stock["ml_prediction"] = generate_ml_prediction(stock)
        stock["llm_insight"] = await generate_stock_insight(stock, "full")
        
        return {
            "report_type": "single_stock",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data": stock
        }
    
    elif request.report_type == "comparison":
        if len(request.symbols) < 2:
            raise HTTPException(status_code=400, detail="At least 2 symbols required for comparison")
        
        comparison_data = []
        for sym in request.symbols[:5]:  # Max 5 stocks
            sym = sym.upper()
            if sym in stocks:
                stock = stocks[sym].copy()
                stock["analysis"] = generate_analysis(stock)
                comparison_data.append(stock)
        
        return {
            "report_type": "comparison",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data": comparison_data
        }
    
    elif request.report_type == "portfolio_health":
        portfolio = await get_portfolio()
        
        health_data = {
            "portfolio": portfolio,
            "diversification_score": len(set(h.get("sector", "") for h in portfolio.get("holdings", []))) * 10,
            "risk_assessment": "MODERATE" if portfolio.get("total_profit_loss_percent", 0) > 0 else "HIGH",
            "recommendations": [
                "Consider diversifying across more sectors",
                "Review holdings with negative returns",
                "Set stop-loss levels for high-risk positions"
            ]
        }
        
        return {
            "report_type": "portfolio_health",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data": health_data
        }
    
    raise HTTPException(status_code=400, detail="Invalid report type")


# PDF Export endpoint
try:
    from services.pdf_service import (
        generate_single_stock_pdf, generate_comparison_pdf, 
        generate_portfolio_health_pdf, is_pdf_available
    )
    from fastapi.responses import Response
    PDF_EXPORT_AVAILABLE = is_pdf_available()
except ImportError:
    PDF_EXPORT_AVAILABLE = False


@api_router.post("/reports/generate-pdf")
async def generate_pdf_report(request: ReportRequest):
    """Generate PDF report for download"""
    if not PDF_EXPORT_AVAILABLE:
        raise HTTPException(status_code=503, detail="PDF generation not available. Install reportlab.")
    
    stocks = get_cached_stocks()
    
    try:
        if request.report_type == "single_stock":
            if not request.symbols:
                raise HTTPException(status_code=400, detail="Symbol required")
            
            symbol = request.symbols[0].upper()
            if symbol not in stocks:
                raise HTTPException(status_code=404, detail="Stock not found")
            
            stock = stocks[symbol].copy()
            stock["analysis"] = generate_analysis(stock)
            stock["ml_prediction"] = generate_ml_prediction(stock)
            stock["llm_insight"] = await generate_stock_insight(stock, "full")
            
            pdf_bytes = generate_single_stock_pdf(stock)
            filename = f"{symbol}_report_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        elif request.report_type == "comparison":
            if len(request.symbols) < 2:
                raise HTTPException(status_code=400, detail="At least 2 symbols required")
            
            comparison_data = []
            for sym in request.symbols[:5]:
                sym = sym.upper()
                if sym in stocks:
                    stock = stocks[sym].copy()
                    stock["analysis"] = generate_analysis(stock)
                    comparison_data.append(stock)
            
            pdf_bytes = generate_comparison_pdf(comparison_data)
            filename = f"comparison_{'_'.join(request.symbols[:3])}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        elif request.report_type == "portfolio_health":
            portfolio = await get_portfolio()
            health_data = {
                "portfolio": portfolio,
                "diversification_score": len(set(h.get("sector", "") for h in portfolio.get("holdings", []))) * 10,
                "risk_assessment": "MODERATE" if portfolio.get("total_profit_loss_percent", 0) > 0 else "HIGH",
                "recommendations": [
                    "Consider diversifying across more sectors",
                    "Review holdings with negative returns",
                    "Set stop-loss levels for high-risk positions"
                ]
            }
            
            pdf_bytes = generate_portfolio_health_pdf(health_data)
            filename = f"portfolio_health_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        else:
            raise HTTPException(status_code=400, detail="Invalid report type")
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")


# ==================== SECTORS ====================
@api_router.get("/sectors")
async def get_sectors():
    """Get list of sectors with stock counts"""
    stocks = list(get_cached_stocks().values())
    sectors = {}
    
    for stock in stocks:
        sector = stock.get("sector", "Other")
        if sector not in sectors:
            sectors[sector] = {"name": sector, "count": 0, "stocks": []}
        sectors[sector]["count"] += 1
        sectors[sector]["stocks"].append(stock["symbol"])
    
    return list(sectors.values())


# ==================== SEARCH ====================
@api_router.get("/search")
async def search_stocks(q: str = Query(..., min_length=1)):
    """Search stocks by symbol or name"""
    stocks = list(get_cached_stocks().values())
    q = q.upper()
    
    results = [
        {"symbol": s["symbol"], "name": s["name"], "sector": s["sector"]}
        for s in stocks
        if q in s["symbol"].upper() or q in s["name"].upper()
    ]
    
    return results[:10]


# ==================== BACKTESTING ====================
try:
    from services.backtesting_service import (
        run_backtest, get_available_strategies, get_strategy_info
    )
    from models.backtest_models import BacktestConfig, StrategyType
    BACKTEST_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Backtesting service not available: {e}")
    BACKTEST_AVAILABLE = False


@api_router.get("/backtest/strategies")
async def list_strategies():
    """Get list of available backtesting strategies"""
    if not BACKTEST_AVAILABLE:
        raise HTTPException(status_code=503, detail="Backtesting service not available")
    
    strategies = get_available_strategies()
    return [s.model_dump() for s in strategies]


@api_router.get("/backtest/strategies/{strategy_id}")
async def get_strategy(strategy_id: str):
    """Get details for a specific strategy"""
    if not BACKTEST_AVAILABLE:
        raise HTTPException(status_code=503, detail="Backtesting service not available")
    
    try:
        strategy_type = StrategyType(strategy_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    strategy = get_strategy_info(strategy_type)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    return strategy.model_dump()


@api_router.post("/backtest/run")
async def run_backtest_endpoint(config: BacktestConfig):
    """Run a backtest with the specified configuration"""
    if not BACKTEST_AVAILABLE:
        raise HTTPException(status_code=503, detail="Backtesting service not available")
    
    symbol = config.symbol.upper()
    stocks = get_cached_stocks()
    
    if symbol not in stocks:
        raise HTTPException(status_code=404, detail="Stock not found")
    
    # Get price history
    try:
        if REAL_DATA_AVAILABLE and USE_REAL_DATA:
            from services.market_data_service import get_historical_data
            history = await get_historical_data(symbol, period="2y")
            if history:
                price_history = [
                    {
                        "date": h["date"].strftime("%Y-%m-%d") if hasattr(h["date"], "strftime") else h["date"],
                        "open": h.get("open", h.get("close", 0)),
                        "high": h.get("high", h.get("close", 0)),
                        "low": h.get("low", h.get("close", 0)),
                        "close": h.get("close", 0),
                        "volume": h.get("volume", 0)
                    }
                    for h in history
                ]
            else:
                price_history = None
        else:
            price_history = None
        
        # Fallback to mock data if needed
        if not price_history:
            from services.mock_data import generate_price_history
            price_history = generate_price_history(symbol, days=500)
        
        # Run the backtest
        result = await run_backtest(config, price_history)

        # Persist backtest result to MongoDB (single save with all metadata)
        try:
            result_dict = result.model_dump()
            result_dict["id"] = str(uuid.uuid4())
            result_dict["symbol"] = symbol
            result_dict["strategy"] = config.strategy.value if hasattr(config.strategy, 'value') else str(config.strategy)
            result_dict["created_at"] = datetime.now(timezone.utc).isoformat()
            result_dict["config"] = {
                "initial_capital": config.initial_capital,
                "start_date": config.start_date,
                "end_date": config.end_date,
            }
            insert_doc = {**result_dict}
            await db.backtest_results.insert_one(insert_doc)
            logger.info(f"Backtest result saved for {symbol}")
        except Exception as save_err:
            logger.warning(f"Failed to save backtest result: {save_err}")
        
        return result.model_dump()

    except Exception as e:
        logger.error(f"Backtest error: {e}")
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@api_router.get("/backtest/history")
async def get_backtest_history(
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = Query(default=20, le=100)
):
    """Get saved backtest results history"""
    """Get saved backtest results from MongoDB"""
    query = {}
    if symbol:
        query["symbol"] = symbol.upper()
    if strategy:
        query["strategy"] = strategy

    cursor = (
        db.backtest_results
        .find(query, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    results = await cursor.to_list(length=limit)
    return {"count": len(results), "results": results}


@api_router.get("/backtest/history/{result_id}")
async def get_backtest_result(result_id: str):
    """Get a specific backtest result by ID"""
    result = await db.backtest_results.find_one({"id": result_id}, {"_id": 0})
    if not result:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return result


@api_router.delete("/backtest/history/{result_id}")
async def delete_backtest_result(result_id: str):
    """Delete a specific backtest result"""
    result = await db.backtest_results.delete_one({"id": result_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return {"message": "Backtest result deleted"}


# ==================== ALERTS ====================
@api_router.get("/alerts")
async def get_alerts(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = Query(default=50, le=100)
):
    """Get all price alerts"""
    if not ALERTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Alerts service not available")
    
    status_enum = None
    if status:
        try:
            status_enum = AlertStatus(status)
        except ValueError:
            pass
    
    alerts = await alerts_service.get_all_alerts(status=status_enum, symbol=symbol, limit=limit)
    
    return {
        "alerts": [a.model_dump() for a in alerts],
        "total": len(alerts),
        "active": len([a for a in alerts if a.status == AlertStatus.ACTIVE]),
        "triggered": len([a for a in alerts if a.status == AlertStatus.TRIGGERED]),
    }


@api_router.post("/alerts")
async def create_alert(alert_data: AlertCreate):
    """Create a new price alert"""
    if not ALERTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Alerts service not available")
    
    # Get stock name if available
    stocks = get_cached_stocks()
    stock = stocks.get(alert_data.symbol.upper())
    stock_name = stock.get("name") if stock else None
    
    alert = await alerts_service.create_alert(alert_data, stock_name)
    
    return {"message": "Alert created", "alert": alert.model_dump()}


@api_router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str):
    """Get a specific alert"""
    if not ALERTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Alerts service not available")
    
    alert = await alerts_service.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return alert.model_dump()


@api_router.put("/alerts/{alert_id}")
async def update_alert(alert_id: str, updates: AlertUpdate):
    """Update an existing alert"""
    if not ALERTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Alerts service not available")
    
    alert = await alerts_service.update_alert(alert_id, updates)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {"message": "Alert updated", "alert": alert.model_dump()}


@api_router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str):
    """Delete an alert"""
    if not ALERTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Alerts service not available")
    
    success = await alerts_service.delete_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {"message": "Alert deleted"}


@api_router.get("/alerts/summary/stats")
async def get_alerts_summary():
    """Get alerts summary statistics"""
    if not ALERTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Alerts service not available")
    
    summary = await alerts_service.get_summary()
    return summary.model_dump()


@api_router.get("/alerts/notifications/recent")
async def get_recent_notifications(limit: int = Query(default=20, le=50)):
    """Get recent alert notifications"""
    if not ALERTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Alerts service not available")
    
    notifications = alerts_service.get_recent_notifications(limit)
    return [n.model_dump() for n in notifications]


@api_router.post("/alerts/check")
async def manually_check_alerts():
    """Manually trigger alert condition check (for testing)"""
    if not ALERTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Alerts service not available")
    
    # Get active alert symbols
    active_alerts = await alerts_service.get_all_alerts(status=AlertStatus.ACTIVE)
    symbols = list(set(a.symbol for a in active_alerts))
    
    if not symbols:
        return {"message": "No active alerts", "notifications": []}
    
    # Fetch current prices
    prices = {}
    if REAL_DATA_AVAILABLE and USE_REAL_DATA:
        try:
            quotes = await get_bulk_quotes(symbols)
            for symbol, quote in quotes.items():
                if quote:
                    prices[symbol] = {
                        "price": quote.get("current_price", 0),
                        "change_percent": quote.get("price_change_percent", 0),
                    }
        except Exception as e:
            logger.error(f"Error fetching prices for alert check: {e}")
    
    if not prices:
        # Fallback to cached stock data
        stocks = get_cached_stocks()
        for symbol in symbols:
            if symbol in stocks:
                prices[symbol] = {
                    "price": stocks[symbol].get("current_price", 0),
                    "change_percent": stocks[symbol].get("price_change_percent", 0),
                }
    
    notifications = await alerts_service.check_alert_conditions(prices)
    
    return {
        "message": f"Checked {len(active_alerts)} alerts",
        "triggered": len(notifications),
        "notifications": [n.model_dump() for n in notifications]
    }


# ==================== DATA EXTRACTION PIPELINE ====================

class ExtractionRequest(BaseModel):
    """Request model for data extraction"""
    symbols: List[str] = Field(..., description="List of stock symbols to extract")
    sources: Optional[List[str]] = Field(None, description="Data sources to use (default: all)")


class ExtractionResponse(BaseModel):
    """Response model for data extraction"""
    job_id: str
    status: str
    total_symbols: int
    processed_symbols: int
    failed_symbols: int
    progress_percent: float
    errors: List[str]
    duration_seconds: Optional[float]


@api_router.get("/extraction/status")
async def get_extraction_status():
    """Get status of data extraction pipeline and available features"""
    return {
        "pipeline_available": EXTRACTION_PIPELINE_AVAILABLE,
        "real_data_available": REAL_DATA_AVAILABLE,
        "use_real_data": USE_REAL_DATA,
        "current_data_source": "Real (Yahoo Finance)" if REAL_DATA_AVAILABLE and USE_REAL_DATA else "Mock Data",
        "available_extractors": ["yfinance", "nse_bhavcopy"] if EXTRACTION_PIPELINE_AVAILABLE else [],
        "features": {
            "field_definitions": 160,
            "deal_breakers": 10,
            "risk_penalties": 10,
            "quality_boosters": 9,
        }
    }


@api_router.post("/extraction/run", response_model=ExtractionResponse)
async def run_extraction(request: ExtractionRequest):
    """
    Run the data extraction pipeline for specified symbols.
    
    This endpoint triggers the full extraction pipeline:
    1. Raw data extraction from multiple sources
    2. Data cleaning and normalization
    3. Calculation of derived fields
    4. Technical indicator computation
    5. Validation against scoring rules
    6. Quality assessment
    """
    global _pipeline_orchestrator
    
    if not EXTRACTION_PIPELINE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Data extraction pipeline not available"
        )
    
    try:
        # Initialize orchestrator if needed
        if _pipeline_orchestrator is None:
            _pipeline_orchestrator = PipelineOrchestrator(db=db)
        
        # Run the pipeline
        job = await _pipeline_orchestrator.run(
            symbols=request.symbols,
            sources=request.sources
        )
        
        # Return results
        duration = None
        if job.completed_at and job.started_at:
            duration = (job.completed_at - job.started_at).total_seconds()
        
        return ExtractionResponse(
            job_id=job.job_id,
            status=job.status.value,
            total_symbols=job.total_symbols,
            processed_symbols=job.processed_symbols,
            failed_symbols=job.failed_symbols,
            progress_percent=job.progress_pct,
            errors=job.errors[:10],  # Limit errors
            duration_seconds=duration
        )
        
    except Exception as e:
        logger.error(f"Extraction pipeline error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {str(e)}"
        )


@api_router.get("/extraction/fields")
async def get_field_definitions():
    """Get all 160 field definitions with their metadata"""
    try:
        from data_extraction.config.field_definitions import FIELD_DEFINITIONS, FIELDS_BY_CATEGORY
        
        # Convert dataclass objects to dicts
        fields_by_cat = {}
        for cat, fields in FIELDS_BY_CATEGORY.items():
            fields_by_cat[cat] = [
                {
                    "name": f.name,
                    "field_id": f.field_id,
                    "data_type": f.data_type.value if hasattr(f.data_type, 'value') else str(f.data_type),
                    "unit": f.unit,
                    "priority": f.priority.value if hasattr(f.priority, 'value') else str(f.priority),
                    "update_frequency": f.update_frequency.value if hasattr(f.update_frequency, 'value') else str(f.update_frequency),
                    "source": f.source.value if hasattr(f.source, 'value') else str(f.source),
                    "used_for": f.used_for,
                }
                for f in fields
            ]
        
        return {
            "total_fields": len(FIELD_DEFINITIONS),
            "categories": list(FIELDS_BY_CATEGORY.keys()),
            "fields_by_category": fields_by_cat
        }
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Field definitions not available: {str(e)}"
        )


# ==================== DATA PIPELINE API (Groww Integration) ====================

@api_router.get("/pipeline/status")
async def get_pipeline_status():
    """Get current data pipeline status and metrics"""
    global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Data pipeline service not configured. GROW_TOTP_TOKEN/GROW_SECRET_KEY not set.",
            "is_running": False,
            "metrics": None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    if _data_pipeline_service is None:
        _data_pipeline_service = init_pipeline_service(db=db, totp_token=GROW_TOTP_TOKEN, secret_key=GROW_SECRET_KEY)
        await _data_pipeline_service.initialize()
    
    return _data_pipeline_service.get_status()


@api_router.post("/pipeline/run")
async def run_pipeline_extraction(request: RunExtractionRequest = None):
    """
    Manually trigger a data extraction job.
    
    Extracts stock market data from Groww API for specified symbols.
    If no symbols provided, uses default set of top Indian stocks.
    """
    global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Data pipeline service not configured. GROW_TOTP_TOKEN/GROW_SECRET_KEY not set."
        )
    
    if _data_pipeline_service is None:
        _data_pipeline_service = init_pipeline_service(db=db, totp_token=GROW_TOTP_TOKEN, secret_key=GROW_SECRET_KEY)
        await _data_pipeline_service.initialize()
    
    symbols = request.symbols if request and request.symbols else None
    extraction_type = request.extraction_type.value if request and request.extraction_type else "quotes"
    
    job = await _data_pipeline_service.run_extraction(
        symbols=symbols,
        extraction_type=extraction_type
    )
    
    return {
        "message": "Extraction job started",
        "job": job.to_dict()
    }


@api_router.post("/pipeline/scheduler/start")
async def start_pipeline_scheduler(request: StartSchedulerRequest = None):
    """Start the automatic data extraction scheduler"""
    global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Data pipeline service not configured. GROW_TOTP_TOKEN/GROW_SECRET_KEY not set."
        )
    
    if _data_pipeline_service is None:
        _data_pipeline_service = init_pipeline_service(db=db, totp_token=GROW_TOTP_TOKEN, secret_key=GROW_SECRET_KEY)
        await _data_pipeline_service.initialize()
    
    interval = request.interval_minutes if request else 30
    await _data_pipeline_service.start_scheduler(interval_minutes=interval)
    
    return {
        "message": f"Scheduler started with {interval} minute interval",
        "status": _data_pipeline_service.get_status()
    }


@api_router.post("/pipeline/scheduler/stop")
async def stop_pipeline_scheduler():
    """Stop the automatic data extraction scheduler"""
    # global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Data pipeline service not configured. GROW_TOTP_TOKEN/GROW_SECRET_KEY not set."
        )
    
    if _data_pipeline_service is None:
        return {"message": "Scheduler not running"}
    
    await _data_pipeline_service.stop_scheduler()
    
    return {
        "message": "Scheduler stopped",
        "status": _data_pipeline_service.get_status()
    }


@api_router.get("/pipeline/jobs")
async def get_pipeline_jobs(limit: int = Query(default=20, le=100)):
    """Get list of recent extraction jobs"""
    # global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE or _data_pipeline_service is None:
        return {"jobs": [], "total": 0}
    
    jobs = _data_pipeline_service.get_jobs(limit=limit)
    return {"jobs": jobs, "total": len(jobs)}


@api_router.get("/pipeline/jobs/{job_id}")
async def get_pipeline_job(job_id: str):
    """Get details of a specific extraction job"""
    # global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE or _data_pipeline_service is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = _data_pipeline_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return job


@api_router.get("/pipeline/history")
async def get_pipeline_history(limit: int = Query(default=50, le=100)):
    """Get extraction job history"""
    # global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE or _data_pipeline_service is None:
        return {"history": [], "total": 0}
    
    history = _data_pipeline_service.get_job_history(limit=limit)
    return {"history": history, "total": len(history)}


@api_router.get("/pipeline/logs")
async def get_pipeline_logs(
    limit: int = Query(default=100, le=500),
    event_type: Optional[str] = None
):
    """Get pipeline event logs"""
    # global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE or _data_pipeline_service is None:
        return {"logs": [], "total": 0}
    
    logs = _data_pipeline_service.get_logs(limit=limit, event_type=event_type)
    return {"logs": logs, "total": len(logs)}


@api_router.get("/pipeline/metrics")
async def get_pipeline_metrics():
    """Get detailed pipeline and API metrics"""
    global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE:
        return {
            "pipeline_available": False,
            "message": "Pipeline not configured",
            "pipeline_metrics": None,
            "api_metrics": None
        }
    
    if _data_pipeline_service is None:
        _data_pipeline_service = init_pipeline_service(db=db, totp_token=GROW_TOTP_TOKEN, secret_key=GROW_SECRET_KEY)
        await _data_pipeline_service.initialize()
    
    status = _data_pipeline_service.get_status()
    
    return {
        "pipeline_available": True,
        "pipeline_metrics": status.get("metrics"),
        "api_metrics": status.get("extractor_metrics"),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@api_router.get("/pipeline/data-summary")
async def get_pipeline_data_summary():
    """Get summary of extracted data"""
    # global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE or _data_pipeline_service is None:
        return {
            "unique_symbols_extracted": 0,
            "data_by_symbol": {},
            "last_extraction_time": None
        }
    
    return _data_pipeline_service.get_data_summary()


@api_router.post("/pipeline/test-api")
async def test_grow_api(request: APITestRequest = None):
    """
    Test the Groww API connection and fetch a sample quote.
    Use this to validate API connectivity and response structure.
    """
    global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Data pipeline service not configured. GROW_TOTP_TOKEN/GROW_SECRET_KEY not set."
        )
    
    if _data_pipeline_service is None:
        _data_pipeline_service = init_pipeline_service(db=db, totp_token=GROW_TOTP_TOKEN, secret_key=GROW_SECRET_KEY)
        await _data_pipeline_service.initialize()
    
    symbol = request.symbol if request else "RELIANCE"
    
    if not _data_pipeline_service.grow_extractor:
        raise HTTPException(status_code=503, detail="Groww extractor not initialized")
    
    result = await _data_pipeline_service.grow_extractor.get_stock_quote(symbol)
    
    return {
        "success": result.status.value == "success",
        "message": f"API test {'successful' if result.status.value == 'success' else 'failed'} for {symbol}",
        "latency_ms": result.latency_ms,
        "data": result.data if result.status.value == "success" else None,
        "error": result.error,
        "retries": result.retries
    }


@api_router.get("/pipeline/default-symbols")
async def get_default_symbols():
    """Get the default list of symbols used for extraction"""
    # global _data_pipeline_service
    
    if _data_pipeline_service:
        return _data_pipeline_service.get_symbol_categories()
    
    from services.pipeline_service import DataPipelineService
    return {
        "symbols": DataPipelineService.DEFAULT_SYMBOLS,
        "count": len(DataPipelineService.DEFAULT_SYMBOLS)
    }


@api_router.post("/pipeline/symbols/add")
async def add_pipeline_symbols(symbols: List[str]):
    """Add new symbols to the tracking list"""
    # global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE or _data_pipeline_service is None:
        raise HTTPException(status_code=503, detail="Pipeline service not available")
    
    result = _data_pipeline_service.add_symbols(symbols)
    return {
        "message": f"Added {len(result['added'])} symbols",
        **result
    }


@api_router.post("/pipeline/symbols/remove")
async def remove_pipeline_symbols(symbols: List[str]):
    """Remove symbols from the tracking list"""
    # global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE or _data_pipeline_service is None:
        raise HTTPException(status_code=503, detail="Pipeline service not available")
    
    result = _data_pipeline_service.remove_symbols(symbols)
    return {
        "message": f"Removed {len(result['removed'])} symbols",
        **result
    }


@api_router.put("/pipeline/scheduler/config")
async def update_scheduler_config(
    interval_minutes: Optional[int] = Query(None, ge=5, le=1440),
    auto_start: Optional[bool] = None
):
    """Update scheduler configuration"""
    # global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE or _data_pipeline_service is None:
        raise HTTPException(status_code=503, detail="Pipeline service not available")
    
    result = _data_pipeline_service.update_scheduler_config(
        interval_minutes=interval_minutes,
        auto_start=auto_start
    )
    return {
        "message": "Scheduler configuration updated",
        **result
    }


@api_router.get("/pipeline/symbol-categories")
async def get_symbol_categories():
    """Get symbols organized by category (NIFTY 50, NIFTY Next 50, Mid/Small caps)"""
    # global _data_pipeline_service
    
    if not PIPELINE_SERVICE_AVAILABLE or _data_pipeline_service is None:
        raise HTTPException(status_code=503, detail="Pipeline service not available")
    
    return _data_pipeline_service.get_symbol_categories()


# ==================== NSE BHAVCOPY API ====================

@api_router.get("/bhavcopy/status")
async def get_bhavcopy_status():
    """Get NSE Bhavcopy extractor status and metrics"""
    global _bhavcopy_extractor
    
    if not NSE_BHAVCOPY_AVAILABLE:
        return {
            "available": False,
            "message": "NSE Bhavcopy extractor not available"
        }
    
    if _bhavcopy_extractor is None:
        _bhavcopy_extractor = get_bhavcopy_extractor()
    
    return {
        "available": True,
        "metrics": _bhavcopy_extractor.get_metrics(),
        "cached_dates": _bhavcopy_extractor.get_cached_dates(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@api_router.get("/bhavcopy/download/{date}")
async def download_bhavcopy(date: str):
    """
    Download NSE Bhavcopy for a specific date.
    
    Date format: YYYY-MM-DD (e.g., 2025-02-17)
    Returns delivery data, VWAP, and trade counts for all stocks.
    """
    global _bhavcopy_extractor
    
    if not NSE_BHAVCOPY_AVAILABLE:
        raise HTTPException(status_code=503, detail="NSE Bhavcopy extractor not available")
    
    if _bhavcopy_extractor is None:
        _bhavcopy_extractor = get_bhavcopy_extractor()
        await _bhavcopy_extractor.initialize()
    
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    data = await _bhavcopy_extractor.download_bhavcopy(target_date)
    
    if data is None:
        raise HTTPException(
            status_code=404, 
            detail=f"Bhavcopy not available for {date}. Market may be closed or data not yet published."
        )
    
    # Write OHLCV data to PostgreSQL time-series store
    pg_count = 0
    if _ts_store:
        try:
            records = [d.to_dict() for d in data]
            pg_count = await _ts_store.upsert_prices(records)
            logger.info(f"Bhavcopy → PostgreSQL: upserted {pg_count} price records for {date}")
        except Exception as e:
            logger.warning(f"Failed to write bhavcopy to PostgreSQL: {e}")
    
    return {
        "date": date,
        "records_count": len(data),
        "postgresql_upserted": pg_count,
        "data": [d.to_dict() for d in data[:100]],  # Limit to 100 records for response
        "message": f"Downloaded {len(data)} records. {pg_count} stored in PostgreSQL. Showing first 100."
    }


@api_router.get("/bhavcopy/symbol/{symbol}")
async def get_bhavcopy_symbol(symbol: str, date: Optional[str] = None):
    """
    Get Bhavcopy data for a specific symbol.
    
    Returns delivery volume, delivery percentage, VWAP, and trade counts.
    If date not provided, uses the last trading day.
    """
    global _bhavcopy_extractor
    
    if not NSE_BHAVCOPY_AVAILABLE:
        raise HTTPException(status_code=503, detail="NSE Bhavcopy extractor not available")
    
    if _bhavcopy_extractor is None:
        _bhavcopy_extractor = get_bhavcopy_extractor()
        await _bhavcopy_extractor.initialize()
    
    target_date = None
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    data = await _bhavcopy_extractor.get_symbol_data(symbol.upper(), target_date)
    
    if data is None:
        raise HTTPException(
            status_code=404, 
            detail=f"Data not found for {symbol}. Check if the symbol is correct and market was open."
        )
    
    return {
        "symbol": symbol.upper(),
        "data": data.to_dict()
    }


@api_router.post("/bhavcopy/symbols")
async def get_bhavcopy_multiple_symbols(symbols: List[str], date: Optional[str] = None):
    """
    Get Bhavcopy data for multiple symbols.
    
    Returns delivery data, VWAP, and trade counts for each symbol.
    """
    global _bhavcopy_extractor
    
    if not NSE_BHAVCOPY_AVAILABLE:
        raise HTTPException(status_code=503, detail="NSE Bhavcopy extractor not available")
    
    if _bhavcopy_extractor is None:
        _bhavcopy_extractor = get_bhavcopy_extractor()
        await _bhavcopy_extractor.initialize()
    
    target_date = None
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    symbols_upper = [s.upper() for s in symbols]
    data = await _bhavcopy_extractor.get_multiple_symbols(symbols_upper, target_date)
    
    return {
        "requested": len(symbols),
        "found": len(data),
        "data": {k: v.to_dict() for k, v in data.items()},
        "missing": [s for s in symbols_upper if s not in data]
    }


@api_router.get("/bhavcopy/metrics")
async def get_bhavcopy_metrics():
    """Get NSE Bhavcopy extraction metrics"""
    global _bhavcopy_extractor
    
    if not NSE_BHAVCOPY_AVAILABLE:
        return {"available": False}
    
    if _bhavcopy_extractor is None:
        _bhavcopy_extractor = get_bhavcopy_extractor()
    
    return {
        "available": True,
        "metrics": _bhavcopy_extractor.get_metrics()
    }


# ==================== SCREENER.IN API ====================

@api_router.get("/screener/status")
async def get_screener_status():
    """Get Screener.in extractor status and metrics"""
    global _screener_extractor
    
    if not SCREENER_AVAILABLE:
        return {
            "available": False,
            "message": "Screener.in extractor not available"
        }
    
    if _screener_extractor is None:
        _screener_extractor = get_screener_extractor()
    
    return {
        "available": True,
        "metrics": _screener_extractor.get_metrics(),
        "cached_symbols": _screener_extractor.get_cached_symbols(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@api_router.get("/screener/company/{symbol}")
async def get_screener_company(symbol: str, consolidated: bool = Query(default=True)):
    """
    Get comprehensive financial data for a company from Screener.in.
    
    Returns:
    - Income Statement (Revenue, Profit, EPS, Margins)
    - Balance Sheet (Assets, Debt, Equity)
    - Cash Flow (OCF, FCF)
    - Financial Ratios (ROE, ROCE, D/E)
    - Shareholding (Promoter, FII, DII)
    """
    global _screener_extractor
    
    if not SCREENER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Screener.in extractor not available")
    
    if _screener_extractor is None:
        _screener_extractor = get_screener_extractor()
        await _screener_extractor.initialize()
    
    data = await _screener_extractor.get_financial_data(symbol.upper(), consolidated)
    
    if data is None:
        raise HTTPException(
            status_code=404, 
            detail=f"Company not found: {symbol}. Check if the symbol is correct."
        )
    
    return {
        "symbol": symbol.upper(),
        "data": data.to_dict()
    }


@api_router.post("/screener/companies")
async def get_screener_multiple_companies(symbols: List[str], consolidated: bool = Query(default=True)):
    """
    Get financial data for multiple companies from Screener.in.
    
    Note: This may take time due to rate limiting (2 seconds between requests).
    """
    global _screener_extractor
    
    if not SCREENER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Screener.in extractor not available")
    
    if _screener_extractor is None:
        _screener_extractor = get_screener_extractor()
        await _screener_extractor.initialize()
    
    if len(symbols) > 10:
        raise HTTPException(
            status_code=400, 
            detail="Maximum 10 symbols allowed per request due to rate limiting"
        )
    
    symbols_upper = [s.upper() for s in symbols]
    data = await _screener_extractor.get_multiple_companies(symbols_upper, consolidated)
    
    return {
        "requested": len(symbols),
        "found": len(data),
        "data": {k: v.to_dict() for k, v in data.items()},
        "missing": [s for s in symbols_upper if s not in data]
    }


@api_router.get("/screener/metrics")
async def get_screener_metrics():
    """Get Screener.in extraction metrics"""
    global _screener_extractor
    
    if not SCREENER_AVAILABLE:
        return {"available": False}
    
    if _screener_extractor is None:
        _screener_extractor = get_screener_extractor()
    
    return {
        "available": True,
        "metrics": _screener_extractor.get_metrics()
    }


# Include routers
app.include_router(api_router)
api_router.include_router(db_dashboard_router)
api_router.include_router(pg_control_router)

# CORS middleware - default to localhost only, never open wildcard
_cors_origins_env = os.environ.get('CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000')
_cors_origins = [origin.strip() for origin in _cors_origins_env.split(',') if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ==================== WEBSOCKET ====================
@app.websocket("/ws/prices")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time price updates"""
    if not WEBSOCKET_AVAILABLE:
        await websocket.close(code=1003, reason="WebSocket not available")
        return
    
    # Generate unique client ID
    client_id = f"client_{uuid.uuid4().hex[:8]}"
    
    await connection_manager.connect(websocket, client_id)
    
    try:
        while True:
            # Wait for messages from client
            data = await websocket.receive_text()
            await handle_websocket_message(websocket, client_id, data)
    except WebSocketDisconnect:
        connection_manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        connection_manager.disconnect(client_id)


@app.websocket("/ws/prices/{client_id}")
async def websocket_with_id(websocket: WebSocket, client_id: str):
    """WebSocket endpoint with custom client ID"""
    if not WEBSOCKET_AVAILABLE:
        await websocket.close(code=1003, reason="WebSocket not available")
        return
    
    await connection_manager.connect(websocket, client_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            await handle_websocket_message(websocket, client_id, data)
    except WebSocketDisconnect:
        connection_manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        connection_manager.disconnect(client_id)


# ==================== DASHBOARD WEBSOCKET ====================

# Simple in-memory set of dashboard WS clients
_dashboard_ws_clients: set = set()


@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """WebSocket for real-time dashboard events (activity, errors, thresholds)."""
    import asyncio as _asyncio

    await websocket.accept()
    _dashboard_ws_clients.add(websocket)
    logger.info(f"Dashboard WS client connected. Total: {len(_dashboard_ws_clients)}")

    try:
        # Push events every 10 seconds
        while True:
            try:
                overview_data = {}
                if _dashboard_svc:
                    # Lightweight pulse: doc counts + error count + thresholds
                    mongo_colls = await db.list_collection_names()
                    total_docs = 0
                    for c in mongo_colls:
                        total_docs += await db[c].count_documents({})

                    threshold_alerts = await _dashboard_svc.check_thresholds()

                    # Recent errors in last 5 min
                    five_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
                    recent_error_count = await db.pipeline_jobs.count_documents(
                        {"status": {"$in": ["failed", "error"]}, "created_at": {"$gte": five_min_ago}}
                    )
                    recent_error_count += await db.extraction_log.count_documents(
                        {"status": {"$in": ["failed", "error"]}, "started_at": {"$gte": five_min_ago}}
                    )

                    overview_data = {
                        "type": "dashboard_pulse",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "mongo_total_docs": total_docs,
                        "mongo_collections": len(mongo_colls),
                        "recent_errors_5m": recent_error_count,
                        "threshold_alerts": len(threshold_alerts),
                        "alerts": [a["message"] for a in threshold_alerts[:3]],
                    }

                    # Add Redis info
                    if cache and cache.is_redis_available:
                        stats = cache.get_stats()
                        overview_data["redis_keys"] = stats.get("key_count", 0)

                    # Add PG info
                    if _ts_store and _ts_store._is_initialized:
                        try:
                            pg_stats = await _ts_store.get_stats()
                            overview_data["pg_total_rows"] = sum(
                                t.get("rows", 0) for t in pg_stats.values()
                                if isinstance(t, dict) and "rows" in t
                            )
                        except Exception:
                            pass

                await websocket.send_json(overview_data)
            except Exception as e:
                logger.debug(f"Dashboard WS send error: {e}")
                break

            await _asyncio.sleep(10)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _dashboard_ws_clients.discard(websocket)
        logger.info(f"Dashboard WS client disconnected. Total: {len(_dashboard_ws_clients)}")


# ==================== DATABASE INDEX SETUP ====================
async def _ensure_mongodb_indexes(database):
    """Create MongoDB indexes at startup for all collections.

    Indexes are idempotent - calling create_index on an existing index is a no-op.
    This ensures performance regardless of whether setup_databases.py was run first.
    """
    try:
        # Watchlist
        await database.watchlist.create_index("symbol", unique=True)

        # Portfolio
        await database.portfolio.create_index("symbol", unique=True)

        # Alerts (includes compound index for filtered queries)
        await database.alerts.create_index("id", unique=True)
        await database.alerts.create_index("symbol")
        await database.alerts.create_index("status")
        await database.alerts.create_index([("status", 1), ("symbol", 1)])

        # Stock data (from extraction pipeline)
        await database.stock_data.create_index("symbol", unique=True)
        await database.stock_data.create_index("last_updated")
        await database.stock_data.create_index("stock_master.sector")
        await database.stock_data.create_index("stock_master.market_cap_category")

        # Price history (MongoDB-side, complements PostgreSQL)
        await database.price_history.create_index(
            [("symbol", 1), ("date", -1)], unique=True
        )

        # Extraction log (with TTL for auto-cleanup after 90 days)
        await database.extraction_log.create_index(
            [("symbol", 1), ("source", 1), ("started_at", -1)]
        )
        await database.extraction_log.create_index("status")
        await database.extraction_log.create_index(
            [("started_at", 1)], expireAfterSeconds=7776000
        )

        # Quality reports (with TTL for auto-cleanup after 90 days)
        await database.quality_reports.create_index(
            [("symbol", 1), ("generated_at", -1)]
        )
        await database.quality_reports.create_index(
            [("generated_at", 1)], expireAfterSeconds=7776000
        )

        # Pipeline jobs (with TTL for auto-cleanup after 90 days)
        await database.pipeline_jobs.create_index("job_id", unique=True)
        await database.pipeline_jobs.create_index([("created_at", -1)])
        await database.pipeline_jobs.create_index("status")
        await database.pipeline_jobs.create_index(
            [("created_at", 1)], expireAfterSeconds=7776000
        )

        # News articles (includes id index and stored_at for cache queries)
        await database.news_articles.create_index("id", unique=True, sparse=True)
        await database.news_articles.create_index([("published_date", -1)])
        await database.news_articles.create_index("related_stocks")
        await database.news_articles.create_index("sentiment")
        await database.news_articles.create_index([("source", 1), ("published_date", -1)])
        await database.news_articles.create_index("stored_at")

        # Backtest results (includes id index for single-result lookups)
        await database.backtest_results.create_index("id", unique=True, sparse=True)
        await database.backtest_results.create_index(
            [("symbol", 1), ("strategy", 1), ("created_at", -1)]
        )
        await database.backtest_results.create_index([("created_at", -1)])

        logger.info("MongoDB indexes created/verified for all collections")
    except Exception as e:
        logger.warning(f"MongoDB index creation issue: {e}")


# ==================== LIFECYCLE EVENTS ====================
@app.on_event("startup")
async def startup_event():
    """Start background services on app startup"""
    global _data_pipeline_service, _ts_store
    
    logger.info("Starting StockPulse API...")

    # Log cache status
    if cache and cache.is_redis_available:
        logger.info("Redis cache is active")
    else:
        logger.warning("Redis not available, using in-memory cache fallback")

    # Initialize PostgreSQL time-series store
    try:
        _ts_store = await init_timeseries_store(timeseries_dsn)
        logger.info("PostgreSQL time-series store initialized")
    except Exception as e:
        logger.warning(f"Time-series store not available: {e}")

    # Verify MongoDB connectivity before proceeding
    try:
        await client.admin.command("ping")
        server_info = await client.server_info()
        logger.info(f"MongoDB connected: version {server_info.get('version', 'unknown')}")
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        if os.environ.get("ENVIRONMENT", "development").lower() == "production":
            logger.critical("Production: exiting because MongoDB is unreachable (fail-fast).")
            raise SystemExit(1)
        logger.error("Server will start but database operations will fail!")

    # Initialize PostgreSQL Control & Monitoring service
    try:
        _pg_control_svc = PgControlService(dsn=timeseries_dsn)
        if _ts_store and _ts_store._pool:
            _pg_control_svc.set_pool(_ts_store._pool)
        init_pg_control_router(_pg_control_svc)
        logger.info("PostgreSQL control service initialized")
    except Exception as e:
        logger.warning(f"PostgreSQL control service init warning: {e}")

    # Initialize Database Dashboard service
    try:
        _dashboard_svc = DatabaseDashboardService(
            mongo_db=db, ts_store=_ts_store, cache=cache
        )
        init_dashboard_router(_dashboard_svc)
        logger.info("Database Dashboard service initialized")
        # Record initial size snapshot
        try:
            await _dashboard_svc.record_size_snapshot()
            logger.info("Database size snapshot recorded")
        except Exception as snap_err:
            logger.debug(f"Size snapshot on startup: {snap_err}")
    except Exception as e:
        logger.warning(f"Database Dashboard service init warning: {e}")

    # Ensure MongoDB indexes exist (idempotent - safe to call on every startup)
    try:
        await _ensure_mongodb_indexes(db)
        logger.info("MongoDB indexes verified")
    except Exception as e:
        logger.warning(f"MongoDB index creation warning: {e}")
    
    if WEBSOCKET_AVAILABLE:
        await price_broadcaster.start()
        logger.info("Price broadcaster started")
    
    # Initialize Data Pipeline Service (with PostgreSQL bridge)
    if PIPELINE_SERVICE_AVAILABLE:
        try:
            _data_pipeline_service = init_pipeline_service(
                db=db,
                totp_token=GROW_TOTP_TOKEN,
                secret_key=GROW_SECRET_KEY,
                ts_store=_ts_store,
            )
            await _data_pipeline_service.initialize()
            logger.info("Data pipeline service initialized with Groww API + PostgreSQL bridge")
        except Exception as e:
            logger.error(f"Failed to initialize data pipeline service: {e}")
    else:
        logger.warning("Data pipeline service not available (GROW_TOTP_TOKEN/GROW_SECRET_KEY not set)")
    
    logger.info("StockPulse API ready!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on app shutdown"""
    # global _data_pipeline_service
    
    logger.info("Shutting down StockPulse API...")
    
    if WEBSOCKET_AVAILABLE:
        await price_broadcaster.stop()
        logger.info("Price broadcaster stopped")
    
    # Cleanup Data Pipeline Service
    if _data_pipeline_service:
        try:
            await _data_pipeline_service.stop_scheduler()
            if _data_pipeline_service.grow_extractor:
                await _data_pipeline_service.grow_extractor.close()
            logger.info("Data pipeline service stopped")
        except Exception as e:
            logger.error(f"Error stopping pipeline service: {e}")
    
    # Close Redis connection
    if cache:
        cache.close()
        logger.info("Redis cache connection closed")
    
    # Close PostgreSQL time-series store
    if _ts_store:
        await _ts_store.close()
        logger.info("PostgreSQL time-series store closed")
    
    client.close()
    logger.info("Database connection closed")
