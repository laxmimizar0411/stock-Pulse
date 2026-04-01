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

        # Database reference
        self._db = None

        # Phase 1 statistics
        self._stats = {
            "features_computed": 0,
            "batch_runs": 0,
            "data_quality_checks": 0,
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

        self._started = True
        logger.info("=" * 60)
        logger.info("Stock Pulse Brain READY — Phase 1 Active")
        logger.info("  Feature Pipeline: %s", "✅" if self.feature_pipeline else "❌")
        logger.info("  Feature Store:    %s", "✅" if self.feature_store else "❌")
        logger.info("  Batch Scheduler:  %s", "✅" if self.batch_scheduler else "❌")
        logger.info("  Storage Layer:    %s", "✅" if self.minio_client else "❌")
        logger.info("  Data Quality:     %s", "✅" if self.data_quality else "❌")
        logger.info("  Kafka:            %s", "✅ CONNECTED" if (self.kafka and self.kafka._connected) else "⚠️ STUB")
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
