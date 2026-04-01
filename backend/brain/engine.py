"""
Brain Engine — Lifecycle management for the Stock Pulse Brain.

Handles startup, shutdown, and provides access to all Brain subsystems.
This is the main entry point for integrating the Brain with the FastAPI app.

Phase 1 subsystems:
    - Kafka Event Bus (stub mode when broker unavailable)
    - Feature Pipeline (technical, fundamental, macro, cross-sectional)
    - Feature Store (MongoDB-backed when Redis/PG unavailable)
    - Batch Scheduler (lightweight Airflow alternative)
    - Storage Layer (MinIO or local filesystem fallback)
    - Data Quality Engine
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from brain.config import BrainConfig, brain_config
from brain.events.kafka_manager import KafkaConfig, KafkaManager

logger = logging.getLogger("brain.engine")

IST = timezone(timedelta(hours=5, minutes=30))


class BrainEngine:
    """
    Central Brain engine — manages all subsystems.

    Usage in FastAPI:
        brain = BrainEngine()

        @app.on_event("startup")
        async def startup():
            await brain.start(db=mongo_db)

        @app.on_event("shutdown")
        async def shutdown():
            await brain.stop()
    """

    def __init__(self, config: Optional[BrainConfig] = None):
        self.config = config or brain_config
        self._started = False
        self._start_time: Optional[float] = None

        # Core subsystems
        self.kafka: Optional[KafkaManager] = None
        self.feature_pipeline = None
        self.feature_store = None
        self.batch_scheduler = None
        self.minio_client = None
        self.data_quality = None

        # Phase 2 subsystems
        self.model_manager = None
        self.signal_generator = None
        self.signal_fusion = None
        self.confidence_scorer = None
        self.backtest_engine = None

        # Database reference
        self._db = None

        # Phase 1+2 statistics
        self._stats = {
            "features_computed": 0,
            "batch_runs": 0,
            "data_quality_checks": 0,
            "models_trained": 0,
            "signals_generated": 0,
            "backtests_run": 0,
        }

    @property
    def db(self):
        return self._db

    async def start(self, db=None):
        """Start all Brain subsystems."""
        if self._started:
            logger.warning("Brain engine already started")
            return

        self._start_time = time.monotonic()
        self._db = db

        logger.info("=" * 60)
        logger.info("Starting Stock Pulse Brain v%s", self.config.version)
        logger.info("=" * 60)

        # 1. Start Kafka event bus
        await self._start_kafka()

        # 2. Initialize Feature Pipeline (Phase 1)
        await self._start_feature_pipeline()

        # 3. Initialize Feature Store (Phase 1)
        await self._start_feature_store()

        # 4. Initialize Batch Scheduler (Phase 1)
        await self._start_batch_scheduler()

        # 5. Initialize Storage Layer (Phase 1)
        await self._start_storage()

        # 6. Initialize Data Quality (Phase 1)
        await self._start_data_quality()

        # 7. Initialize Model Manager (Phase 2)
        await self._start_model_manager()

        # 8. Initialize Signal Pipeline (Phase 2)
        await self._start_signal_pipeline()

        # 9. Initialize Backtest Engine (Phase 2)
        await self._start_backtest_engine()

        self._started = True
        logger.info("=" * 60)
        logger.info("Stock Pulse Brain READY — Phase 1+2 Active")
        logger.info("  Feature Pipeline: %s", "✅" if self.feature_pipeline else "❌")
        logger.info("  Feature Store:    %s", "✅" if self.feature_store else "❌")
        logger.info("  Batch Scheduler:  %s", "✅" if self.batch_scheduler else "❌")
        logger.info("  Storage Layer:    %s", "✅" if self.minio_client else "❌")
        logger.info("  Data Quality:     %s", "✅" if self.data_quality else "❌")
        logger.info("  Kafka:            %s", "✅ CONNECTED" if (self.kafka and self.kafka._connected) else "⚠️ STUB")
        logger.info("  Model Manager:    %s", "✅" if self.model_manager else "❌")
        logger.info("  Signal Pipeline:  %s", "✅" if self.signal_fusion else "❌")
        logger.info("  Backtest Engine:  %s", "✅" if self.backtest_engine else "❌")
        logger.info("=" * 60)

    async def stop(self):
        """Gracefully stop all Brain subsystems."""
        if not self._started:
            return

        logger.info("Shutting down Stock Pulse Brain...")

        # Stop in reverse order of startup
        if self.batch_scheduler:
            await self.batch_scheduler.stop()

        if self.kafka:
            await self.kafka.stop()

        self._started = False
        logger.info("Stock Pulse Brain stopped")

    # -----------------------------------------------------------------------
    # Phase 1: Feature Pipeline
    # -----------------------------------------------------------------------

    async def _start_feature_pipeline(self):
        """Initialize the feature pipeline with data fetchers."""
        try:
            from brain.features.feature_pipeline import FeaturePipeline
            from brain.features.data_fetchers import (
                MongoDataFetchers,
                fetch_price_data_yfinance,
                fetch_fundamental_data_yfinance,
                fetch_macro_data_yfinance,
                fetch_market_data_yfinance,
            )
            from brain.event_bus import get_event_bus

            # Use MongoDB-backed fetchers if db is available, else YFinance direct
            if self._db is not None:
                fetchers = MongoDataFetchers(self._db)
                self.feature_pipeline = FeaturePipeline(
                    config=self.config,
                    event_bus=get_event_bus() if get_event_bus().is_running else None,
                    price_fetcher=fetchers.fetch_price_data,
                    fundamental_fetcher=fetchers.fetch_fundamental_data,
                    macro_fetcher=fetchers.fetch_macro_data,
                    market_fetcher=fetchers.fetch_market_data,
                )
            else:
                self.feature_pipeline = FeaturePipeline(
                    config=self.config,
                    price_fetcher=fetch_price_data_yfinance,
                    fundamental_fetcher=fetch_fundamental_data_yfinance,
                    macro_fetcher=fetch_macro_data_yfinance,
                    market_fetcher=fetch_market_data_yfinance,
                )

            await self.feature_pipeline.initialize()
            logger.info("✅ Feature Pipeline: READY (%d features registered)",
                        self.feature_pipeline.registry.feature_count)

        except Exception:
            logger.exception("⚠️ Feature Pipeline: FAILED to initialize")
            self.feature_pipeline = None

    # -----------------------------------------------------------------------
    # Phase 1: Feature Store
    # -----------------------------------------------------------------------

    async def _start_feature_store(self):
        """Initialize the feature store (MongoDB-backed fallback)."""
        try:
            from brain.features.feature_store import FeatureStore

            # Use MongoDB as the online store fallback
            self.feature_store = FeatureStore(
                redis_client=None,  # No Redis available
                pg_pool=None,       # No PostgreSQL available
            )
            # Inject MongoDB reference for fallback storage
            self.feature_store._mongo_db = self._db
            logger.info("✅ Feature Store: READY (MongoDB fallback mode)")

        except Exception:
            logger.exception("⚠️ Feature Store: FAILED to initialize")
            self.feature_store = None

    # -----------------------------------------------------------------------
    # Phase 1: Batch Scheduler
    # -----------------------------------------------------------------------

    async def _start_batch_scheduler(self):
        """Initialize the batch scheduler with all DAGs."""
        try:
            from brain.batch.scheduler import BatchScheduler
            from brain.batch.dag_daily_bhavcopy import dag_daily_bhavcopy
            from brain.batch.dag_fii_dii import dag_fii_dii
            from brain.batch.dag_fundamentals import dag_fundamentals
            from brain.batch.dag_corporate_actions import dag_corporate_actions
            from brain.batch.dag_macro_data import dag_macro_data

            self.batch_scheduler = BatchScheduler()

            # Set shared context
            if self._db is not None:
                self.batch_scheduler.set_context(db=self._db)

            # Register all DAGs
            self.batch_scheduler.register_dag(
                "daily_bhavcopy",
                dag_daily_bhavcopy,
                schedule_time="16:30",
                description="Download and process NSE Bhavcopy after market close",
            )
            self.batch_scheduler.register_dag(
                "fii_dii_flows",
                dag_fii_dii,
                schedule_time="17:00",
                description="Fetch FII/DII institutional flow data",
            )
            self.batch_scheduler.register_dag(
                "fundamentals",
                dag_fundamentals,
                schedule_time="18:00",
                description="Update fundamental data for tracked stocks",
            )
            self.batch_scheduler.register_dag(
                "corporate_actions",
                dag_corporate_actions,
                schedule_time="17:30",
                description="Track dividends, splits, bonuses, rights issues",
            )
            self.batch_scheduler.register_dag(
                "macro_data",
                dag_macro_data,
                schedule_time="17:30",
                description="Fetch macro-economic indicators (VIX, INR, Crude)",
            )

            await self.batch_scheduler.start()
            logger.info("✅ Batch Scheduler: READY (%d DAGs registered)",
                        len(self.batch_scheduler._dags))

        except Exception:
            logger.exception("⚠️ Batch Scheduler: FAILED to initialize")
            self.batch_scheduler = None

    # -----------------------------------------------------------------------
    # Phase 1: Storage Layer
    # -----------------------------------------------------------------------

    async def _start_storage(self):
        """Initialize MinIO storage (or local filesystem fallback)."""
        try:
            from brain.storage.minio_client import MinIOClient

            self.minio_client = MinIOClient()
            connected = await self.minio_client.initialize()

            if connected:
                logger.info("✅ Storage Layer: MinIO CONNECTED")
            else:
                logger.info("✅ Storage Layer: LOCAL FILESYSTEM fallback")

        except Exception:
            logger.exception("⚠️ Storage Layer: FAILED to initialize")
            self.minio_client = None

    # -----------------------------------------------------------------------
    # Phase 1: Data Quality
    # -----------------------------------------------------------------------

    async def _start_data_quality(self):
        """Initialize the data quality engine."""
        try:
            from brain.ingestion.data_quality import DataQualityEngine

            self.data_quality = DataQualityEngine()
            logger.info("✅ Data Quality: READY")

        except Exception:
            logger.exception("⚠️ Data Quality: FAILED to initialize")
            self.data_quality = None

    # -----------------------------------------------------------------------
    # Phase 2: Model Manager
    # -----------------------------------------------------------------------

    async def _start_model_manager(self):
        """Initialize the ML model manager."""
        try:
            from brain.models_ml.model_manager import ModelManager

            self.model_manager = ModelManager(db=self._db)

            # Try loading any previously trained models from disk
            for model_name in ["xgboost_direction", "lightgbm_direction", "garch_volatility"]:
                self.model_manager._load_model(model_name)

            loaded = self.model_manager.get_loaded_models()
            logger.info("✅ Model Manager: READY (%d models loaded: %s)", len(loaded), loaded or "none")

        except Exception:
            logger.exception("⚠️ Model Manager: FAILED to initialize")
            self.model_manager = None

    # -----------------------------------------------------------------------
    # Phase 2: Signal Pipeline
    # -----------------------------------------------------------------------

    async def _start_signal_pipeline(self):
        """Initialize signal generator, fusion engine, and confidence scorer."""
        try:
            from brain.signals.signal_generator import (
                generate_technical_signal,
                generate_fundamental_signal,
                generate_volume_signal,
                generate_macro_signal,
            )
            from brain.signals.signal_fusion import SignalFusionEngine
            from brain.signals.confidence_scorer import ConfidenceScorer

            self.signal_fusion = SignalFusionEngine(config=self.config)
            self.confidence_scorer = ConfidenceScorer()
            logger.info("✅ Signal Pipeline: READY (fusion + confidence)")

        except Exception:
            logger.exception("⚠️ Signal Pipeline: FAILED to initialize")
            self.signal_fusion = None
            self.confidence_scorer = None

    # -----------------------------------------------------------------------
    # Phase 2: Backtest Engine
    # -----------------------------------------------------------------------

    async def _start_backtest_engine(self):
        """Initialize the backtesting engine."""
        try:
            from brain.backtesting.vectorbt_engine import BacktestEngine

            self.backtest_engine = BacktestEngine(
                initial_capital=1_000_000,
                max_position_pct=0.10,
                stop_loss_pct=0.03,
                take_profit_pct=0.06,
                max_hold_days=30,
            )
            logger.info("✅ Backtest Engine: READY (Indian cost model)")

        except Exception:
            logger.exception("⚠️ Backtest Engine: FAILED to initialize")
            self.backtest_engine = None

    # -----------------------------------------------------------------------
    # Kafka (original)
    # -----------------------------------------------------------------------

    async def _start_kafka(self):
        """Start Kafka event bus."""
        if self.config.kafka.enabled:
            kafka_config = KafkaConfig(
                bootstrap_servers=self.config.kafka.bootstrap_servers,
                client_id=self.config.kafka.client_id,
                group_id=self.config.kafka.group_id,
            )
            self.kafka = KafkaManager(kafka_config)
            connected = await self.kafka.start()

            if connected:
                await self.kafka.create_topics()
                logger.info("✅ Kafka event bus: CONNECTED")
            else:
                logger.warning("⚠️  Kafka event bus: STUB MODE (no broker available)")
        else:
            logger.info("⏭️  Kafka event bus: DISABLED by config")
            self.kafka = KafkaManager()  # Stub instance

    # -----------------------------------------------------------------------
    # Public API methods
    # -----------------------------------------------------------------------

    async def compute_features(self, symbol: str) -> Dict[str, Any]:
        """Compute features for a single symbol."""
        if not self.feature_pipeline:
            raise RuntimeError("Feature pipeline not initialized")

        features = await self.feature_pipeline.compute_features(symbol)
        self._stats["features_computed"] += 1

        # Sanitize features: replace NaN/Infinity with None for JSON serialization
        features = _sanitize_features(features)

        # Store in MongoDB if available
        if self._db is not None and features:
            try:
                await self._db["brain_features"].update_one(
                    {"symbol": symbol.upper()},
                    {"$set": {
                        "symbol": symbol.upper(),
                        "features": features,
                        "feature_count": len(features),
                        "computed_at": datetime.now(IST).isoformat(),
                    }},
                    upsert=True,
                )
            except Exception:
                logger.exception("Error storing features for %s in MongoDB", symbol)

        return features

    async def compute_features_batch(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Compute features for multiple symbols."""
        if not self.feature_pipeline:
            raise RuntimeError("Feature pipeline not initialized")

        results = await self.feature_pipeline.run_batch(symbols)
        self._stats["features_computed"] += len(symbols)

        # Sanitize all results
        results = {sym: _sanitize_features(f) if f else {} for sym, f in results.items()}

        # Store all in MongoDB
        if self._db is not None:
            for symbol, features in results.items():
                if features:
                    try:
                        await self._db["brain_features"].update_one(
                            {"symbol": symbol.upper()},
                            {"$set": {
                                "symbol": symbol.upper(),
                                "features": features,
                                "feature_count": len(features),
                                "computed_at": datetime.now(IST).isoformat(),
                            }},
                            upsert=True,
                        )
                    except Exception:
                        pass

        return results

    async def get_stored_features(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get previously computed features from MongoDB."""
        if self._db is None:
            # Try pipeline cache
            if self.feature_pipeline:
                return self.feature_pipeline.get_latest_features(symbol)
            return None

        try:
            doc = await self._db["brain_features"].find_one(
                {"symbol": symbol.upper()},
                {"_id": 0},
            )
            return doc
        except Exception:
            return None

    async def run_data_quality_check(self, symbol: str, price_data=None) -> Dict[str, Any]:
        """Run data quality checks on a symbol's data."""
        if not self.data_quality:
            return {"error": "Data quality engine not initialized"}

        if price_data is None and self.feature_pipeline:
            # Fetch price data
            from brain.features.data_fetchers import fetch_price_data_yfinance
            price_data = await fetch_price_data_yfinance(symbol)

        if price_data is None:
            return {"error": f"No price data available for {symbol}"}

        # Convert DataFrame to OHLCVBar list for quality engine
        try:
            from brain.schemas.market_data import OHLCVBar, Exchange
            import pandas as pd

            bars = []
            for _, row in price_data.iterrows():
                bar = OHLCVBar(
                    symbol=symbol.upper(),
                    exchange=Exchange.NSE,
                    timeframe="1d",
                    open=float(row.get("open", 0)),
                    high=float(row.get("high", 0)),
                    low=float(row.get("low", 0)),
                    close=float(row.get("close", 0)),
                    volume=int(float(row.get("volume", 0))),
                    timestamp=pd.Timestamp(row.get("date", pd.Timestamp.now())),
                    source="yfinance",
                )
                bars.append(bar)

            report = self.data_quality.validate_ohlcv_bars(bars, symbol=symbol, source="yfinance")
            self._stats["data_quality_checks"] += 1

            return {
                "symbol": report.symbol,
                "source": report.source,
                "total_records": report.total_records,
                "is_acceptable": report.is_acceptable,
                "passed_checks": report.passed_count,
                "failed_checks": report.failed_count,
                "checks": [
                    {
                        "name": r.check_name,
                        "passed": r.passed,
                        "severity": r.severity.value if hasattr(r.severity, 'value') else str(r.severity),
                        "message": r.message,
                    }
                    for r in report.results
                ],
            }
        except Exception as e:
            logger.exception("Error in data quality check for %s", symbol)
            return {"error": str(e), "symbol": symbol}

    # -----------------------------------------------------------------------
    # Phase 2: Model Training & Prediction
    # -----------------------------------------------------------------------

    async def train_models(self, symbol: str, horizon: int = 5) -> Dict[str, Any]:
        """
        Train ML models for a symbol using its price data.
        Fetches data, creates features, builds training dataset, trains ensemble.
        """
        if not self.model_manager:
            return {"error": "Model manager not initialized"}

        from brain.features.data_fetchers import MongoDataFetchers, fetch_price_data_yfinance
        from brain.models_ml.feature_engineering import build_training_dataset

        # Fetch price data (use MongoDB first, then YFinance)
        price_df = None
        if self._db is not None:
            fetchers = MongoDataFetchers(self._db)
            price_df = await fetchers.fetch_price_data(symbol, days=730)
        if price_df is None or price_df.empty:
            price_df = await fetch_price_data_yfinance(symbol, days=730)
        if price_df is None or price_df.empty:
            return {"error": f"No price data for {symbol}"}

        # Build training dataset from price features
        X, y, feature_names = build_training_dataset(
            price_df, {}, horizon=horizon,
            up_threshold=0.01, down_threshold=-0.01,
        )

        if len(X) < 100:
            return {"error": f"Insufficient training data for {symbol} ({len(X)} samples)"}

        # Train ensemble
        results = {}
        results["xgboost"] = await self.model_manager.train_xgboost(X, y, feature_names)
        results["lightgbm"] = await self.model_manager.train_lightgbm(X, y, feature_names)

        # Train GARCH on returns
        returns = price_df["close"].pct_change().dropna().values * 100
        if len(returns) > 100:
            results["garch"] = await self.model_manager.train_garch(returns)

        self._stats["models_trained"] += 1
        return {
            "symbol": symbol,
            "samples": len(X),
            "features": len(feature_names),
            "feature_names": feature_names,
            "results": results,
        }

    async def generate_signal(self, symbol: str, current_price: float = 0.0) -> Dict[str, Any]:
        """Generate a trading signal for a symbol using all available data."""
        if not self.signal_fusion:
            return {"error": "Signal pipeline not initialized"}

        from brain.signals.signal_generator import (
            generate_technical_signal,
            generate_fundamental_signal,
            generate_volume_signal,
            generate_macro_signal,
            RawSignal,
        )

        raw_signals = []

        # Get features
        features = await self.get_stored_features(symbol)
        feat_dict = features.get("features", {}) if features else {}

        # Technical signal
        try:
            tech_signal = generate_technical_signal(feat_dict)
            raw_signals.append(tech_signal)
        except Exception:
            pass

        # Fundamental signal
        try:
            fund_signal = generate_fundamental_signal(feat_dict)
            raw_signals.append(fund_signal)
        except Exception:
            pass

        # Volume signal
        try:
            vol_signal = generate_volume_signal(feat_dict)
            raw_signals.append(vol_signal)
        except Exception:
            pass

        # Macro signal
        try:
            macro_signal = generate_macro_signal(feat_dict)
            raw_signals.append(macro_signal)
        except Exception:
            pass

        # ML model signal (if models are trained)
        if self.model_manager and self.model_manager.get_loaded_models():
            try:
                from brain.models_ml.feature_engineering import prepare_features
                X, names = prepare_features(feat_dict)
                pred = await self.model_manager.predict("xgboost_direction", X)
                if pred and "predictions" in pred:
                    direction_idx = pred["predictions"][0] if pred["predictions"] else 1
                    ml_score = {0: -0.8, 1: 0.0, 2: 0.8}.get(direction_idx, 0.0)
                    raw_signals.append(RawSignal(
                        source="ml_model", score=ml_score,
                        confidence=0.7, details={"model": "xgboost_direction", "prediction": pred}
                    ))
            except Exception:
                pass

        if not raw_signals:
            return {"error": "No signals could be generated", "symbol": symbol}

        # Fuse signals
        signal_event = self.signal_fusion.fuse_signals(
            symbol=symbol,
            raw_signals=raw_signals,
            current_price=current_price,
        )

        self._stats["signals_generated"] += 1

        # Convert to serializable dict
        return {
            "signal_id": signal_event.signal_id,
            "symbol": signal_event.symbol,
            "direction": signal_event.direction.value if hasattr(signal_event.direction, 'value') else str(signal_event.direction),
            "confidence": signal_event.confidence,
            "timeframe": signal_event.timeframe.value if hasattr(signal_event.timeframe, 'value') else str(signal_event.timeframe),
            "entry_price": signal_event.entry_price,
            "target_price": signal_event.target_price,
            "stop_loss": signal_event.stop_loss,
            "risk_reward_ratio": signal_event.risk_reward_ratio,
            "risk_level": signal_event.risk_level.value if hasattr(signal_event.risk_level, 'value') else str(signal_event.risk_level),
            "contributing_factors": [
                {"name": f.name, "score": f.score, "weight": f.weight, "description": f.description}
                for f in (signal_event.contributing_factors or [])
            ],
            "explanation": signal_event.explanation,
            "raw_signals_count": len(raw_signals),
        }

    async def run_backtest(self, symbol: str, horizon: int = 5) -> Dict[str, Any]:
        """Run a backtest for a symbol using model predictions."""
        if not self.backtest_engine:
            return {"error": "Backtest engine not initialized"}

        from brain.features.data_fetchers import MongoDataFetchers, fetch_price_data_yfinance
        from brain.models_ml.feature_engineering import build_training_dataset, create_target_labels
        import pandas as pd

        # Fetch price data (MongoDB first, then YFinance)
        price_df = None
        if self._db is not None:
            fetchers = MongoDataFetchers(self._db)
            price_df = await fetchers.fetch_price_data(symbol, days=730)
        if price_df is None or price_df.empty:
            price_df = await fetch_price_data_yfinance(symbol, days=730)
        if price_df is None or price_df.empty:
            return {"error": f"No price data for {symbol}"}

        price_df = price_df.sort_values("date").reset_index(drop=True)

        # Build signals from trained model or from price-based rules
        if self.model_manager and "xgboost_direction" in self.model_manager.get_loaded_models():
            X, y, feature_names = build_training_dataset(price_df, {}, horizon=horizon)
            if len(X) > 0:
                pred = await self.model_manager.predict("xgboost_direction", X)
                if pred and "predictions" in pred:
                    signals = pd.Series(pred["predictions"])
                    # Align with price data (features start at idx ~200)
                    offset = len(price_df) - len(signals)
                    full_signals = pd.Series([1] * offset + signals.tolist())
                else:
                    # Fallback: use target labels as perfect-foresight baseline
                    full_signals = create_target_labels(price_df["close"], horizon)
            else:
                full_signals = create_target_labels(price_df["close"], horizon)
        else:
            # No model trained - use target labels as baseline
            full_signals = create_target_labels(price_df["close"], horizon)

        # Run backtest
        result = self.backtest_engine.run(price_df, full_signals, symbol=symbol)
        self._stats["backtests_run"] += 1

        return result

    # -----------------------------------------------------------------------
    # Health & Status
    # -----------------------------------------------------------------------

    async def health_check(self) -> dict:
        """Return health status of all Brain subsystems."""
        health = {
            "brain_version": self.config.version,
            "started": self._started,
            "uptime_seconds": time.monotonic() - self._start_time if self._start_time else 0,
            "subsystems": {},
            "stats": self._stats,
        }

        # Kafka
        if self.kafka:
            health["subsystems"]["kafka"] = await self.kafka.health_check()

        # Feature Pipeline
        if self.feature_pipeline:
            health["subsystems"]["feature_pipeline"] = {
                "status": "healthy",
                "stats": self.feature_pipeline.get_stats(),
            }
        else:
            health["subsystems"]["feature_pipeline"] = {"status": "not_initialized"}

        # Feature Store
        if self.feature_store:
            health["subsystems"]["feature_store"] = {
                "status": "healthy",
                "mode": "mongodb_fallback",
                "stats": self.feature_store._stats,
            }
        else:
            health["subsystems"]["feature_store"] = {"status": "not_initialized"}

        # Batch Scheduler
        if self.batch_scheduler:
            health["subsystems"]["batch_scheduler"] = await self.batch_scheduler.health_check()
        else:
            health["subsystems"]["batch_scheduler"] = {"status": "not_initialized"}

        # Storage
        if self.minio_client:
            health["subsystems"]["storage"] = {
                "status": "healthy",
                "connected": self.minio_client._connected,
                "mode": "minio" if self.minio_client._connected else "local_fallback",
                "stats": self.minio_client._stats,
            }
        else:
            health["subsystems"]["storage"] = {"status": "not_initialized"}

        # Data Quality
        if self.data_quality:
            health["subsystems"]["data_quality"] = {"status": "healthy"}
        else:
            health["subsystems"]["data_quality"] = {"status": "not_initialized"}

        # Phase 2: Model Manager
        if self.model_manager:
            health["subsystems"]["model_manager"] = {
                "status": "healthy",
                "loaded_models": self.model_manager.get_loaded_models(),
                "stats": self.model_manager.get_stats(),
            }
        else:
            health["subsystems"]["model_manager"] = {"status": "not_initialized"}

        # Phase 2: Signal Pipeline
        if self.signal_fusion:
            health["subsystems"]["signal_pipeline"] = {
                "status": "healthy",
                "active_signals": len(self.signal_fusion._active_signals),
            }
        else:
            health["subsystems"]["signal_pipeline"] = {"status": "not_initialized"}

        # Phase 2: Backtest Engine
        if self.backtest_engine:
            health["subsystems"]["backtest_engine"] = {
                "status": "healthy",
                "initial_capital": self.backtest_engine.initial_capital,
            }
        else:
            health["subsystems"]["backtest_engine"] = {"status": "not_initialized"}

        # Overall status
        initialized_count = sum(
            1 for s in health["subsystems"].values()
            if s.get("status") in ("healthy", "degraded")
        )
        total = len(health["subsystems"])
        health["status"] = (
            "healthy" if initialized_count == total and self._started
            else "degraded" if self._started
            else "stopped"
        )

        return health

    def get_config_summary(self) -> dict:
        """Return a summary of the brain configuration."""
        return self.config.to_dict()


def _sanitize_features(features: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize feature dict: replace NaN/Infinity with None for JSON safety."""
    import math

    sanitized = {}
    for key, value in features.items():
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                sanitized[key] = None
            else:
                sanitized[key] = round(value, 6)  # Limit precision
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_features(value)
        elif isinstance(value, list):
            sanitized[key] = [
                None if isinstance(v, float) and (math.isnan(v) or math.isinf(v))
                else round(v, 6) if isinstance(v, float) else v
                for v in value
            ]
        else:
            sanitized[key] = value
    return sanitized


# Global Brain engine singleton
brain_engine = BrainEngine()
