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

Phase 2 subsystems:
    - Model Manager (XGBoost, LightGBM, GARCH)
    - Signal Pipeline (fusion + confidence scoring)
    - Backtest Engine (vectorized with Indian cost model)

Phase 3 subsystems:
    - HMM Regime Detection (3-state: bull/bear/sideways)
    - Complementary Detectors (K-Means, GMM, CUSUM)
    - Regime Router (regime-conditional model weighting)
    - Position Sizer (Kelly Criterion + drawdown escalation)
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
        self.normalizer = None
        self.kafka_bridge = None

        # Phase 2 subsystems
        self.model_manager = None
        self.signal_generator = None
        self.signal_fusion = None
        self.confidence_scorer = None
        self.backtest_engine = None

        # Phase 3.2 subsystems — Sentiment Pipeline
        self.sentiment_aggregator = None
        self.social_scraper = None
        self.earnings_analyzer = None

        # Phase 3.3 subsystems — LLM Multi-Agent System
        self.agent_orchestrator = None

        # Phase 3.4 subsystems — Risk Management Engine
        self.var_calculator = None
        self.stress_test_engine = None
        self.sebi_compliance = None
        self.hrp_optimizer = None

        # Phase 3.5-3.10 subsystems
        self.rag_knowledge_base = None
        self.governance_scorer = None
        self.sector_rotation = None
        self.dividend_intelligence = None
        self.regulatory_calendar = None
        self.explainability_engine = None

        # Phase 3 subsystems
        self.hmm_detector = None
        self.kmeans_detector = None
        self.gmm_detector = None
        self.cusum_detector = None
        self.regime_router = None
        self.position_sizer = None
        self.regime_store = None
        self._current_regime = None
        self._regime_probabilities = {}
        self._regime_last_trained = None

        # Database reference
        self._db = None

        # Phase 1+2+3 statistics
        self._stats = {
            "features_computed": 0,
            "batch_runs": 0,
            "data_quality_checks": 0,
            "models_trained": 0,
            "signals_generated": 0,
            "backtests_run": 0,
            "regime_detections": 0,
            "regime_retrains": 0,
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

        # 2. Initialize Ingestion Pipeline (Normalizer + Kafka Bridge)
        await self._start_ingestion_pipeline()

        # 3. Initialize Feature Pipeline (Phase 1)
        await self._start_feature_pipeline()

        # 4. Initialize Feature Store (Phase 1)
        await self._start_feature_store()

        # 5. Initialize Batch Scheduler (Phase 1)
        await self._start_batch_scheduler()

        # 6. Initialize Storage Layer (Phase 1)
        await self._start_storage()

        # 7. Initialize Data Quality (Phase 1)
        await self._start_data_quality()

        # 8. Initialize Model Manager (Phase 2)
        await self._start_model_manager()

        # 9. Initialize Signal Pipeline (Phase 2)
        await self._start_signal_pipeline()

        # 10. Initialize Backtest Engine (Phase 2)
        await self._start_backtest_engine()

        # 11. Initialize Regime Detection (Phase 3.1)
        await self._start_regime_detection()

        # 12. Initialize Sentiment Pipeline (Phase 3.2)
        await self._start_sentiment_pipeline()

        # 13. Initialize LLM Multi-Agent System (Phase 3.3)
        await self._start_agent_system()

        # 14. Initialize Risk Management Engine (Phase 3.4)
        await self._start_risk_engine()

        # 15. Initialize remaining Phase 3 subsystems (3.5-3.10)
        await self._start_phase3_remaining()

        self._started = True
        logger.info("=" * 60)
        logger.info("Stock Pulse Brain READY — Phase 1+2+3 Active")
        logger.info("  Ingestion Pipeline: %s", "✅" if self.kafka_bridge else "❌")
        logger.info("  Feature Pipeline: %s", "✅" if self.feature_pipeline else "❌")
        logger.info("  Feature Store:    %s", "✅" if self.feature_store else "❌")
        logger.info("  Batch Scheduler:  %s", "✅" if self.batch_scheduler else "❌")
        logger.info("  Storage Layer:    %s", "✅" if self.minio_client else "❌")
        logger.info("  Data Quality:     %s", "✅" if self.data_quality else "❌")
        logger.info("  Kafka:            %s", "✅ CONNECTED" if (self.kafka and self.kafka._connected) else "⚠️ STUB")
        logger.info("  Model Manager:    %s", "✅" if self.model_manager else "❌")
        logger.info("  Signal Pipeline:  %s", "✅" if self.signal_fusion else "❌")
        logger.info("  Backtest Engine:  %s", "✅" if self.backtest_engine else "❌")
        logger.info("  Regime Detection: %s", "✅" if self.hmm_detector else "❌")
        logger.info("  Regime Router:    %s", "✅" if self.regime_router else "❌")
        logger.info("  Position Sizer:   %s", "✅" if self.position_sizer else "❌")
        logger.info("  Sentiment Pipeline: %s", "✅" if self.sentiment_aggregator else "❌")
        logger.info("  Social Scraper:   %s", "✅" if self.social_scraper else "❌")
        logger.info("  Earnings Analyzer:%s", "✅" if self.earnings_analyzer else "❌")
        logger.info("  Agent Orchestrator: %s", "✅" if self.agent_orchestrator else "❌")
        logger.info("  VaR Calculator:   %s", "✅" if self.var_calculator else "❌")
        logger.info("  Stress Testing:   %s", "✅" if self.stress_test_engine else "❌")
        logger.info("  SEBI Compliance:  %s", "✅" if self.sebi_compliance else "❌")
        logger.info("  HRP Optimizer:    %s", "✅" if self.hrp_optimizer else "❌")
        logger.info("  RAG Knowledge:    %s", "✅" if (self.rag_knowledge_base and self.rag_knowledge_base.is_available) else "❌")
        logger.info("  Governance Score: %s", "✅" if self.governance_scorer else "❌")
        logger.info("  Sector Rotation:  %s", "✅" if self.sector_rotation else "❌")
        logger.info("  Dividend Intel:   %s", "✅" if self.dividend_intelligence else "❌")
        logger.info("  Reg. Calendar:    %s", "✅" if self.regulatory_calendar else "❌")
        logger.info("  Explainability:   %s", "✅" if self.explainability_engine else "❌")
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
    # Phase 1: Ingestion Pipeline (Normalizer + Kafka Bridge)
    # -----------------------------------------------------------------------

    async def _start_ingestion_pipeline(self):
        """Initialize the data ingestion pipeline with Normalizer and KafkaBridge."""
        try:
            from brain.ingestion.normalizer import DataNormalizer
            from brain.ingestion.kafka_bridge import KafkaBridge

            # Initialize Normalizer
            self.normalizer = DataNormalizer()
            logger.info("✅ Normalizer: READY")

            # Initialize Kafka Bridge
            # Pass KafkaManager if available, else standalone mode
            self.kafka_bridge = KafkaBridge(kafka_manager=self.kafka)
            
            if self.kafka and self.kafka._connected:
                logger.info("✅ Kafka Bridge: READY (connected to Kafka)")
            else:
                logger.info("✅ Kafka Bridge: READY (standalone mode, no Kafka)")

        except Exception:
            logger.exception("⚠️ Ingestion Pipeline: FAILED to initialize")
            self.normalizer = None
            self.kafka_bridge = None

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
                eb = get_event_bus()
                self.feature_pipeline = FeaturePipeline(
                    config=self.config,
                    event_bus=eb if eb and eb.is_running else None,
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
                mongo_db=self._db,  # Set MongoDB instance once
            )
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
    # Phase 3: Regime Detection
    # -----------------------------------------------------------------------

    async def _start_regime_detection(self):
        """Initialize HMM regime detection, complementary detectors, router, and position sizer."""
        try:
            from brain.regime import (
                HMMRegimeDetector,
                KMeansRegimeDetector,
                GMMRegimeDetector,
                CUSUMDetector,
                RegimeRouter,
                PositionSizer,
                RegimeStore,
            )
            from brain.models.events import MarketRegime

            # Initialize all detectors
            self.hmm_detector = HMMRegimeDetector(config=self.config.regime)
            self.kmeans_detector = KMeansRegimeDetector(n_clusters=3)
            self.gmm_detector = GMMRegimeDetector(n_components=3)
            self.cusum_detector = CUSUMDetector(
                window_size=50, threshold_multiplier=4.0, drift=0.5
            )

            # Initialize regime router (with model_manager if available)
            self.regime_router = RegimeRouter(model_manager=self.model_manager)

            # Initialize position sizer
            self.position_sizer = PositionSizer(risk_config=self.config.risk)

            # Initialize regime store (Redis if available, otherwise in-memory)
            self.regime_store = RegimeStore(cache_service=None, ts_store=None)

            # Default regime
            self._current_regime = MarketRegime.SIDEWAYS
            self._regime_probabilities = {
                "bull_prob": 0.33, "bear_prob": 0.33, "sideways_prob": 0.34
            }

            # Try loading previously saved HMM model from disk
            try:
                import os
                model_path = self._get_hmm_model_path()
                if os.path.exists(model_path):
                    self.hmm_detector.load(model_path)
                    logger.info("HMM model loaded from disk: %s", model_path)
            except Exception:
                logger.debug("No saved HMM model found, will train from scratch")

            # Attempt auto-training from historical data
            await self._auto_train_regime_detectors()

            logger.info("Phase 3 Regime Detection: READY")

        except Exception:
            logger.exception("Phase 3 Regime Detection: FAILED to initialize")
            self.hmm_detector = None
            self.kmeans_detector = None
            self.gmm_detector = None
            self.cusum_detector = None
            self.regime_router = None
            self.position_sizer = None
            self.regime_store = None

    def _get_hmm_model_path(self) -> str:
        """Get filesystem path for persisted HMM model."""
        import os
        model_dir = os.path.join(os.path.dirname(__file__), "..", "data", "models", "regime")
        os.makedirs(model_dir, exist_ok=True)
        return os.path.join(model_dir, "hmm_detector.pkl")

    async def _auto_train_regime_detectors(self):
        """Auto-train regime detectors on startup if historical data is available."""
        try:
            features = await self._build_regime_features()
            if features is None or len(features) < 100:
                logger.info("Insufficient data for regime training (%d rows), using rule-based fallback",
                            len(features) if features is not None else 0)
                return

            # Train HMM
            self.hmm_detector.train(features)
            logger.info("HMM detector trained on %d observations", len(features))

            # Persist HMM model to disk
            try:
                self.hmm_detector.save(self._get_hmm_model_path())
            except Exception:
                logger.debug("Could not persist HMM model to disk")

            # Train K-Means and GMM
            if self.kmeans_detector and self.kmeans_detector.is_available:
                self.kmeans_detector.train(features)
                logger.info("K-Means detector trained")

            if self.gmm_detector and self.gmm_detector.is_available:
                self.gmm_detector.train(features)
                logger.info("GMM detector trained")

            # Run initial prediction
            regime, probs = self.hmm_detector.predict_regime(features)
            self._current_regime = regime
            self._regime_probabilities = probs
            self._regime_last_trained = datetime.now(IST)
            self._stats["regime_retrains"] += 1

            # Set CUSUM baseline regime
            self.cusum_detector.set_current_regime(regime)

            logger.info("Initial regime detected: %s (probs: %s)", regime.value, probs)

            # Publish regime event
            await self._publish_regime_event(regime, probs)

        except Exception:
            logger.exception("Auto-train regime detectors failed, using rule-based fallback")

    async def _build_regime_features(self):
        """Build feature matrix for regime detection from historical data."""
        import numpy as np

        try:
            from brain.features.data_fetchers import fetch_price_data_yfinance

            # Use NIFTY 50 as the market proxy
            lookback_days = self.config.regime.lookback_years * 365
            price_df = await fetch_price_data_yfinance("^NSEI", days=lookback_days)

            if price_df is None or price_df.empty or len(price_df) < 100:
                logger.warning("Insufficient NIFTY 50 price data for regime training")
                return None

            # Compute features
            close = price_df["close"].values.astype(float)
            n_prices = len(close)

            # 1. Daily returns
            daily_returns = np.diff(close) / close[:-1]
            n = len(daily_returns)

            # 2. Rolling 20-day volatility
            rolling_vol = np.array([
                np.std(daily_returns[max(0, i - 19):i + 1])
                for i in range(n)
            ])

            # 3. Fetch India VIX historical time-series
            vix_df = await fetch_price_data_yfinance("^INDIAVIX", days=lookback_days)
            if vix_df is not None and not vix_df.empty and len(vix_df) > 10:
                vix_close = vix_df["close"].values.astype(float)
                # Align VIX to daily_returns length (VIX may have different trading days)
                if len(vix_close) >= n:
                    vix_col = vix_close[-n:]
                else:
                    # Pad front with the earliest available value
                    pad = np.full(n - len(vix_close), vix_close[0])
                    vix_col = np.concatenate([pad, vix_close])
            else:
                logger.debug("India VIX historical data unavailable, using rolling vol proxy")
                # Proxy: annualized rolling vol * 100 approximates VIX
                vix_col = rolling_vol * np.sqrt(252) * 100

            # 4. Fetch INR/USD historical time-series
            inr_usd_df = await fetch_price_data_yfinance("USDINR=X", days=lookback_days)
            if inr_usd_df is not None and not inr_usd_df.empty and len(inr_usd_df) > 10:
                # Invert USDINR to get INR/USD (1 INR = X USD)
                usdinr_close = inr_usd_df["close"].values.astype(float)
                inr_usd_raw = 1.0 / np.where(usdinr_close > 0, usdinr_close, 83.0)
                if len(inr_usd_raw) >= n:
                    inr_usd_col = inr_usd_raw[-n:]
                else:
                    pad = np.full(n - len(inr_usd_raw), inr_usd_raw[0])
                    inr_usd_col = np.concatenate([pad, inr_usd_raw])
            else:
                logger.debug("INR/USD historical data unavailable, using constant 0.012")
                inr_usd_col = np.full(n, 0.012)

            # 4. FII/DII flow momentum (from MongoDB if available, else zeros)
            fii_dii_col = np.zeros(n)
            if self._db is not None:
                try:
                    fii_dii_collection = self._db.get_collection("fii_dii_flows")
                    cursor = fii_dii_collection.find().sort("date", -1).limit(n)
                    flows = []
                    async for doc in cursor:
                        net_flow = doc.get("fii_net", 0.0) + doc.get("dii_net", 0.0)
                        flows.append(net_flow)
                    if flows:
                        flows = list(reversed(flows))
                        # Pad or truncate to match
                        pad_len = n - len(flows)
                        if pad_len > 0:
                            flows = [0.0] * pad_len + flows
                        fii_dii_col = np.array(flows[:n])
                except Exception:
                    logger.debug("FII/DII data not available from MongoDB, using zeros")

            # Stack features: (n_samples, 5)
            features = np.column_stack([
                daily_returns,
                rolling_vol,
                vix_col,
                fii_dii_col,
                inr_usd_col,
            ])

            # Remove any rows with NaN/Inf
            valid_mask = np.all(np.isfinite(features), axis=1)
            features = features[valid_mask]

            logger.info("Built regime feature matrix: shape=%s", features.shape)
            return features

        except Exception:
            logger.exception("Failed to build regime features")
            return None

    async def _publish_regime_event(self, regime, probabilities):
        """Publish a regime change event to the event bus."""
        try:
            from brain.event_bus import get_event_bus
            from brain.models.events import BrainEvent, EventType

            eb = get_event_bus()
            if eb and eb.is_running:
                event = BrainEvent(
                    event_type=EventType.REGIME_CHANGED,
                    source="regime.hmm_detector",
                    payload={
                        "regime": regime.value,
                        "probabilities": probabilities,
                    },
                )
                await eb.publish("regime.changed", event)
        except Exception:
            logger.debug("Could not publish regime event (event bus not available)")

    async def detect_regime(self, force_retrain: bool = False) -> Dict[str, Any]:
        """
        Run regime detection. Retrains if stale or forced.

        Returns dict with current regime, probabilities, and detector consensus.
        """
        if not self.hmm_detector:
            return {"error": "Regime detection not initialized"}

        from brain.models.events import MarketRegime

        # Check if retrain needed
        needs_retrain = force_retrain
        if self._regime_last_trained:
            days_since = (datetime.now(IST) - self._regime_last_trained).days
            if days_since >= self.config.regime.retrain_frequency_days:
                needs_retrain = True
                logger.info("Regime model stale (%d days), retraining", days_since)

        if needs_retrain:
            await self._auto_train_regime_detectors()

        # Build current features for prediction
        features = await self._build_regime_features()
        if features is None or len(features) < 10:
            return {
                "regime": self._current_regime.value if self._current_regime else "sideways",
                "probabilities": self._regime_probabilities,
                "source": "cached",
                "message": "Using cached regime (insufficient data for fresh detection)",
            }

        # Get predictions from all detectors
        hmm_regime, hmm_probs = self.hmm_detector.predict_regime(features)

        kmeans_regime = MarketRegime.SIDEWAYS
        gmm_regime = MarketRegime.SIDEWAYS
        gmm_probs = {}

        if self.kmeans_detector and self.kmeans_detector.is_trained:
            kmeans_regime, _ = self.kmeans_detector.predict_regime(features)

        if self.gmm_detector and self.gmm_detector.is_trained:
            gmm_regime, gmm_probs = self.gmm_detector.predict_regime(features)

        # CUSUM: update with latest data point
        cusum_change = False
        cusum_type = None
        if self.cusum_detector and len(features) > 0:
            last_return = float(features[-1, 0])
            last_vol = float(features[-1, 1])
            cusum_change, cusum_type = self.cusum_detector.update(last_return, last_vol)
            if cusum_change:
                cusum_suggested = self.cusum_detector.suggest_regime(cusum_type)
                logger.info("CUSUM detected change: %s -> suggested %s", cusum_type, cusum_suggested.value)

        # Ensemble consensus: majority vote
        votes = [hmm_regime, kmeans_regime, gmm_regime]
        regime_counts = {}
        for v in votes:
            regime_counts[v] = regime_counts.get(v, 0) + 1
        consensus_regime = max(regime_counts, key=regime_counts.get)
        consensus_strength = regime_counts[consensus_regime] / len(votes)

        # Update current regime if consensus is strong or HMM agrees
        previous_regime = self._current_regime
        if consensus_strength >= 0.67 or consensus_regime == hmm_regime:
            self._current_regime = consensus_regime
            self._regime_probabilities = hmm_probs

        # Update CUSUM tracker
        if self.cusum_detector:
            self.cusum_detector.set_current_regime(self._current_regime)

        self._stats["regime_detections"] += 1

        # Persist to regime store for history
        if self.regime_store:
            from datetime import date as _date
            try:
                await self.regime_store.save_regime(
                    regime=self._current_regime,
                    probabilities=hmm_probs,
                    regime_date=_date.today(),
                )
            except Exception:
                logger.debug("Could not persist regime to store")

        # Publish event if regime changed
        if self._current_regime != previous_regime:
            logger.info("Regime change: %s -> %s", previous_regime.value, self._current_regime.value)
            await self._publish_regime_event(self._current_regime, hmm_probs)

        # Get transition matrix
        transition_matrix = None
        try:
            tm = self.hmm_detector.get_transition_matrix()
            transition_matrix = tm.tolist()
        except Exception:
            pass

        return {
            "regime": self._current_regime.value,
            "probabilities": hmm_probs,
            "consensus": {
                "regime": consensus_regime.value,
                "strength": round(consensus_strength, 2),
                "votes": {r.value: c for r, c in regime_counts.items()},
            },
            "detectors": {
                "hmm": {"regime": hmm_regime.value, "probabilities": hmm_probs},
                "kmeans": {"regime": kmeans_regime.value},
                "gmm": {"regime": gmm_regime.value, "probabilities": gmm_probs},
                "cusum": {
                    "change_detected": cusum_change,
                    "change_type": cusum_type,
                    "statistics": self.cusum_detector.get_statistics() if self.cusum_detector else {},
                },
            },
            "transition_matrix": transition_matrix,
            "last_trained": self._regime_last_trained.isoformat() if self._regime_last_trained else None,
            "source": "live",
        }

    async def get_regime_status(self) -> Dict[str, Any]:
        """Get current regime status without recomputing."""
        return {
            "regime": self._current_regime.value if self._current_regime else "unknown",
            "probabilities": self._regime_probabilities,
            "last_trained": self._regime_last_trained.isoformat() if self._regime_last_trained else None,
            "position_sizer": self.position_sizer.get_current_state() if self.position_sizer else None,
            "cusum": self.cusum_detector.get_statistics() if self.cusum_detector else None,
            "stats": {
                "regime_detections": self._stats.get("regime_detections", 0),
                "regime_retrains": self._stats.get("regime_retrains", 0),
            },
        }

    async def calculate_position_size(
        self,
        signal_confidence: float,
        win_rate: float,
        risk_reward_ratio: float,
        entry_price: float,
        stop_loss: float,
        timeframe: str = "swing",
    ) -> Dict[str, Any]:
        """Calculate position size using Kelly Criterion with regime awareness."""
        if not self.position_sizer:
            return {"error": "Position sizer not initialized"}

        from brain.models.events import MarketRegime, SignalTimeframe

        # Map timeframe string to enum
        tf_map = {
            "intraday": SignalTimeframe.INTRADAY,
            "swing": SignalTimeframe.SWING,
            "positional": SignalTimeframe.POSITIONAL,
        }
        tf = tf_map.get(timeframe, SignalTimeframe.SWING)

        return self.position_sizer.calculate_position_size(
            signal_confidence=signal_confidence,
            win_rate=win_rate,
            risk_reward_ratio=risk_reward_ratio,
            entry_price=entry_price,
            stop_loss=stop_loss,
            regime=self._current_regime,
            timeframe=tf,
        )

    # -----------------------------------------------------------------------
    # Phase 3.2: Sentiment Pipeline
    # -----------------------------------------------------------------------

    async def _start_sentiment_pipeline(self):
        """Initialize the full sentiment pipeline: FinBERT + VADER + LLM + social."""
        try:
            from brain.sentiment.finbert_analyzer import FinBERTAnalyzer
            from brain.sentiment.news_scraper import NewsScraper
            from brain.sentiment.entity_extractor import EntityExtractor
            from brain.sentiment.sentiment_aggregator import SentimentAggregator
            from brain.sentiment.social_scraper import SocialScraper
            from brain.sentiment.earnings_analyzer import EarningsCallAnalyzer
            from brain.sentiment.llm_sentiment import analyze_sentiment_llm

            # Initialize components
            analyzer = FinBERTAnalyzer(
                use_finbert=self.config.sentiment.finbert_enabled,
                use_indian_variant=True,
                use_vader=self.config.sentiment.vader_enabled,
            )
            scraper = NewsScraper(
                max_age_hours=self.config.sentiment.max_article_age_hours,
                max_articles_per_source=self.config.sentiment.max_articles_per_source,
            )
            extractor = EntityExtractor()

            # Load stock universe for entity extraction
            universe = self._get_stock_universe()
            if universe:
                extractor.load_universe(universe)

            # LLM sentiment function (uses Gemini Tier 2)
            llm_fn = None
            if self.config.sentiment.llm_enabled:
                llm_fn = analyze_sentiment_llm

            # Event bus
            event_bus = None
            try:
                from brain.event_bus import get_event_bus
                eb = get_event_bus()
                if eb and eb.is_running:
                    event_bus = eb
            except Exception:
                pass

            # Create aggregator
            self.sentiment_aggregator = SentimentAggregator(
                scraper=scraper,
                analyzer=analyzer,
                extractor=extractor,
                event_bus=event_bus,
                llm_sentiment_fn=llm_fn,
                half_life_hours=self.config.sentiment.half_life_hours,
            )

            # Initialize aggregator (loads stock universe, pre-loads models in background)
            self.sentiment_aggregator.initialize(stock_universe=universe)

            # Social scraper
            self.social_scraper = SocialScraper()

            # Earnings call analyzer
            self.earnings_analyzer = EarningsCallAnalyzer(
                finbert_analyzer=analyzer,
                llm_fn=None,  # Will be connected when LLM agents are ready
            )

            logger.info("✅ Sentiment Pipeline: READY (FinBERT=%s, VADER=%s, LLM=%s, Social=%s)",
                        self.config.sentiment.finbert_enabled,
                        self.config.sentiment.vader_enabled,
                        self.config.sentiment.llm_enabled,
                        "✅")

        except Exception:
            logger.exception("⚠️ Sentiment Pipeline: FAILED to initialize")
            self.sentiment_aggregator = None
            self.social_scraper = None
            self.earnings_analyzer = None

    def _get_stock_universe(self) -> Dict[str, str]:
        """Get stock universe for entity extraction from known NIFTY stocks."""
        return {
            "RELIANCE": "Reliance Industries Ltd",
            "TCS": "Tata Consultancy Services Ltd",
            "HDFCBANK": "HDFC Bank Ltd",
            "INFY": "Infosys Ltd",
            "ICICIBANK": "ICICI Bank Ltd",
            "HINDUNILVR": "Hindustan Unilever Ltd",
            "SBIN": "State Bank of India",
            "BHARTIARTL": "Bharti Airtel Ltd",
            "ITC": "ITC Ltd",
            "KOTAKBANK": "Kotak Mahindra Bank Ltd",
            "LT": "Larsen & Toubro Ltd",
            "AXISBANK": "Axis Bank Ltd",
            "WIPRO": "Wipro Ltd",
            "HCLTECH": "HCL Technologies Ltd",
            "ASIANPAINT": "Asian Paints Ltd",
            "MARUTI": "Maruti Suzuki India Ltd",
            "TITAN": "Titan Company Ltd",
            "SUNPHARMA": "Sun Pharmaceutical Industries Ltd",
            "BAJFINANCE": "Bajaj Finance Ltd",
            "TATAMOTORS": "Tata Motors Ltd",
            "TATASTEEL": "Tata Steel Ltd",
            "NTPC": "NTPC Ltd",
            "POWERGRID": "Power Grid Corporation of India Ltd",
            "ONGC": "Oil & Natural Gas Corporation Ltd",
            "TECHM": "Tech Mahindra Ltd",
            "ULTRACEMCO": "UltraTech Cement Ltd",
            "NESTLEIND": "Nestle India Ltd",
            "DRREDDY": "Dr. Reddy's Laboratories Ltd",
            "ADANIENT": "Adani Enterprises Ltd",
            "ADANIPORTS": "Adani Ports & Special Economic Zone Ltd",
            "BAJAJFINSV": "Bajaj Finserv Ltd",
            "COALINDIA": "Coal India Ltd",
            "BRITANNIA": "Britannia Industries Ltd",
            "CIPLA": "Cipla Ltd",
            "GRASIM": "Grasim Industries Ltd",
            "DIVISLAB": "Divi's Laboratories Ltd",
            "INDUSINDBK": "IndusInd Bank Ltd",
            "EICHERMOT": "Eicher Motors Ltd",
            "HEROMOTOCO": "Hero MotoCorp Ltd",
            "JSWSTEEL": "JSW Steel Ltd",
            "HINDALCO": "Hindalco Industries Ltd",
            "BAJAJ-AUTO": "Bajaj Auto Ltd",
            "VEDL": "Vedanta Ltd",
            "ZOMATO": "Zomato Ltd",
            "TATAPOWER": "Tata Power Company Ltd",
            "IRCTC": "Indian Railway Catering and Tourism Corporation Ltd",
            "ADANIGREEN": "Adani Green Energy Ltd",
            "M&M": "Mahindra & Mahindra Ltd",
            "PAYTM": "One 97 Communications Ltd",
        }

    # -----------------------------------------------------------------------
    # Phase 3.2: Sentiment API helpers
    # -----------------------------------------------------------------------

    async def get_sentiment(self, symbol: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get sentiment for a symbol via the aggregator."""
        if not self.sentiment_aggregator:
            return {"error": "Sentiment pipeline not initialized"}
        
        try:
            result = await self.sentiment_aggregator.compute_sentiment(symbol, force_refresh=force_refresh)
            return result.to_dict()
        except Exception as e:
            logger.exception("Error computing sentiment for %s", symbol)
            return {"error": str(e)}

    async def get_market_sentiment(self) -> Dict[str, Any]:
        """Get market-wide sentiment."""
        if not self.sentiment_aggregator:
            return {"error": "Sentiment pipeline not initialized"}
        
        try:
            result = await self.sentiment_aggregator.compute_market_sentiment()
            return result.to_dict()
        except Exception as e:
            logger.exception("Error computing market sentiment")
            return {"error": str(e)}

    async def get_social_sentiment(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get social media sentiment."""
        if not self.social_scraper:
            return {"error": "Social scraper not initialized"}
        
        try:
            if symbol:
                posts = await self.social_scraper.fetch_for_symbol(symbol)
            else:
                posts = await self.social_scraper.fetch_all()
            
            # Analyze sentiment of social posts
            if posts and self.sentiment_aggregator:
                texts = [p.raw_text for p in posts if p.raw_text]
                if texts:
                    from brain.sentiment.finbert_analyzer import _vader_analyze
                    vader_results = _vader_analyze(texts[:30])
                    
                    avg_score = sum(r.score for r in vader_results) / len(vader_results) if vader_results else 0.0
                    
                    return {
                        "symbol": symbol or "ALL",
                        "post_count": len(posts),
                        "sentiment_score": round(avg_score, 4),
                        "label": "positive" if avg_score > 0.1 else "negative" if avg_score < -0.1 else "neutral",
                        "top_posts": [
                            {
                                "title": p.title[:100],
                                "source": f"{p.source}/{p.subreddit}" if p.subreddit else p.source,
                                "score": p.score,
                                "url": p.url,
                                "symbols": p.symbols[:5],
                            }
                            for p in posts[:10]
                        ],
                        "sources": self.social_scraper.get_stats().get("sources", {}),
                    }
            
            return {
                "symbol": symbol or "ALL",
                "post_count": len(posts),
                "sentiment_score": 0.0,
                "label": "neutral",
                "top_posts": [
                    {"title": p.title[:100], "source": p.source, "score": p.score}
                    for p in posts[:10]
                ],
            }
        except Exception as e:
            logger.exception("Error computing social sentiment")
            return {"error": str(e)}

    async def analyze_earnings_call(
        self, symbol: str, transcript: str, quarter: str = ""
    ) -> Dict[str, Any]:
        """Analyze an earnings call transcript."""
        if not self.earnings_analyzer:
            return {"error": "Earnings analyzer not initialized"}
        
        try:
            result = self.earnings_analyzer.analyze_transcript(
                symbol=symbol, transcript=transcript, quarter=quarter
            )
            return result.to_dict()
        except Exception as e:
            logger.exception("Error analyzing earnings call for %s", symbol)
            return {"error": str(e)}

    # -----------------------------------------------------------------------
    # Phase 3.3: LLM Multi-Agent System
    # -----------------------------------------------------------------------

    async def _start_agent_system(self):
        """Initialize the LLM multi-agent orchestration system."""
        try:
            from brain.agents.orchestrator import AgentOrchestrator

            self.agent_orchestrator = AgentOrchestrator()

            if self.agent_orchestrator.is_available:
                logger.info("✅ LLM Multi-Agent System: READY (10 agents, Gemini 2-tier)")
            else:
                logger.warning("⚠️ LLM Multi-Agent System: NO API KEY (agents initialized but LLM unavailable)")

        except Exception:
            logger.exception("⚠️ LLM Multi-Agent System: FAILED to initialize")
            self.agent_orchestrator = None

    async def run_agent_analysis(self, symbol: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run the full multi-agent analysis pipeline for a symbol."""
        if not self.agent_orchestrator:
            return {"error": "Agent orchestrator not initialized"}

        try:
            ctx = context or {}
            if self._current_regime:
                ctx["regime"] = self._current_regime.value
            if self.sentiment_aggregator and symbol != "MARKET":
                try:
                    sent = self.sentiment_aggregator._cache.get(symbol)
                    if sent:
                        ctx["sentiment"] = sent.to_dict()
                        ctx["sentiment_score"] = sent.score
                except Exception:
                    pass

            result = await self.agent_orchestrator.analyze_symbol(symbol, ctx)
            return result.to_dict()

        except Exception as e:
            logger.exception(f"Agent analysis failed for {symbol}")
            return {"error": str(e)}

    # -----------------------------------------------------------------------
    # Phase 3.4: Risk Management Engine
    # -----------------------------------------------------------------------

    async def _start_risk_engine(self):
        """Initialize the risk management engine."""
        try:
            from brain.risk.var_calculator import VaRCalculator
            from brain.risk.stress_testing import StressTestEngine
            from brain.risk.sebi_compliance import SEBIComplianceEngine
            from brain.risk.hrp_portfolio import HRPOptimizer

            self.var_calculator = VaRCalculator(confidence=0.95, mc_simulations=10000)
            self.stress_test_engine = StressTestEngine()
            self.sebi_compliance = SEBIComplianceEngine()
            self.hrp_optimizer = HRPOptimizer()

            logger.info("✅ Risk Management Engine: READY (VaR + Stress + SEBI + HRP)")

        except Exception:
            logger.exception("⚠️ Risk Management Engine: FAILED to initialize")
            self.var_calculator = None
            self.stress_test_engine = None
            self.sebi_compliance = None
            self.hrp_optimizer = None

    async def calculate_var(self, symbol: str, returns_list: List[float], portfolio_value: float = 1000000.0) -> Dict[str, Any]:
        """Calculate VaR using all methods."""
        if not self.var_calculator:
            return {"error": "VaR calculator not initialized"}
        import numpy as np
        returns = np.array(returns_list)
        results = self.var_calculator.calculate(symbol, returns, portfolio_value)
        return {method: r.to_dict() for method, r in results.items()}

    async def run_stress_test(self, symbol: str, portfolio_value: float = 1000000.0, sector: str = "general") -> Dict[str, Any]:
        """Run stress test scenarios."""
        if not self.stress_test_engine:
            return {"error": "Stress test engine not initialized"}
        results = self.stress_test_engine.run_stress_test(symbol, portfolio_value, sector)
        return {name: r.to_dict() for name, r in results.items()}

    async def check_sebi_margin(self, symbol: str, trade_value: float, **kwargs) -> Dict[str, Any]:
        """Check SEBI margin requirements."""
        if not self.sebi_compliance:
            return {"error": "SEBI compliance engine not initialized"}
        result = self.sebi_compliance.calculate_margin(symbol, trade_value, **kwargs)
        return result.to_dict()

    # -----------------------------------------------------------------------
    # Phase 3.5-3.10: Remaining subsystems
    # -----------------------------------------------------------------------

    async def _start_phase3_remaining(self):
        """Initialize Phase 3.5 through 3.10 subsystems."""
        # Phase 3.5: RAG Knowledge Base
        try:
            from brain.rag.knowledge_base import RAGKnowledgeBase
            self.rag_knowledge_base = RAGKnowledgeBase()
            self.rag_knowledge_base.initialize()
            if self.rag_knowledge_base.is_available:
                logger.info("✅ RAG Knowledge Base: READY")
            else:
                logger.warning("⚠️ RAG Knowledge Base: Embedder not available")
        except Exception:
            logger.exception("⚠️ RAG Knowledge Base: FAILED")
            self.rag_knowledge_base = None

        # Phase 3.6: Governance Scorer
        try:
            from brain.governance.governance_scorer import GovernanceScorer
            self.governance_scorer = GovernanceScorer()
            logger.info("✅ Corporate Governance Scorer: READY")
        except Exception:
            logger.exception("⚠️ Corporate Governance Scorer: FAILED")
            self.governance_scorer = None

        # Phase 3.7: Sector Rotation
        try:
            from brain.sector.sector_rotation import SectorRotationEngine
            self.sector_rotation = SectorRotationEngine()
            logger.info("✅ Sector Rotation Engine: READY")
        except Exception:
            logger.exception("⚠️ Sector Rotation Engine: FAILED")
            self.sector_rotation = None

        # Phase 3.8: Dividend Intelligence
        try:
            from brain.dividends.dividend_intelligence import DividendIntelligence
            self.dividend_intelligence = DividendIntelligence()
            logger.info("✅ Dividend Intelligence: READY")
        except Exception:
            logger.exception("⚠️ Dividend Intelligence: FAILED")
            self.dividend_intelligence = None

        # Phase 3.9: Regulatory Calendar
        try:
            from brain.calendar.regulatory_calendar import RegulatoryCalendar
            self.regulatory_calendar = RegulatoryCalendar()
            self.regulatory_calendar.initialize()
            logger.info("✅ Regulatory Calendar: READY (%d events)", len(self.regulatory_calendar._events))
        except Exception:
            logger.exception("⚠️ Regulatory Calendar: FAILED")
            self.regulatory_calendar = None

        # Phase 3.10: Explainability Engine
        try:
            from brain.explainability.explainability_engine import ExplainabilityEngine
            from brain.sentiment.llm_sentiment import analyze_deep_llm
            self.explainability_engine = ExplainabilityEngine(llm_fn=analyze_deep_llm)
            logger.info("✅ SHAP Explainability Engine: READY")
        except Exception:
            logger.exception("⚠️ SHAP Explainability Engine: FAILED")
            self.explainability_engine = None

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

        # Store in MongoDB via FeatureStore abstraction
        if self.feature_store and self._db is not None and features:
            await self.feature_store.store_features(symbol, features)

        return features

    async def compute_features_batch(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Compute features for multiple symbols."""
        if not self.feature_pipeline:
            raise RuntimeError("Feature pipeline not initialized")

        results = await self.feature_pipeline.run_batch(symbols)
        self._stats["features_computed"] += len(symbols)

        # Sanitize all results
        results = {sym: _sanitize_features(f) if f else {} for sym, f in results.items()}

        # Store all in MongoDB via FeatureStore abstraction
        if self.feature_store and self._db is not None:
            for symbol, features in results.items():
                if features:
                    await self.feature_store.store_features(symbol, features)

        return results

    async def get_stored_features(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get previously computed features from MongoDB."""
        # Try FeatureStore abstraction first
        if self.feature_store and self._db is not None:
            return await self.feature_store.get_features(symbol)
        
        # Fallback to pipeline cache if no DB
        if self.feature_pipeline:
            return self.feature_pipeline.get_latest_features(symbol)
        
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

        # ML model signal — use regime router if available, else direct prediction
        regime_routing_result = None
        if self.model_manager and self.model_manager.get_loaded_models():
            try:
                from brain.models_ml.feature_engineering import prepare_features
                X, names = prepare_features(feat_dict)

                if self.regime_router and self._current_regime:
                    # Regime-routed prediction (weighted ensemble per regime)
                    regime_routing_result = await self.regime_router.route_prediction(
                        features=X, regime=self._current_regime, return_individual=True,
                    )
                    if regime_routing_result and "error" not in regime_routing_result:
                        direction_str = regime_routing_result.get("regime_direction", "HOLD")
                        ml_score = {"BUY": 0.8, "HOLD": 0.0, "SELL": -0.8}.get(direction_str, 0.0)
                        confidence = regime_routing_result.get("confidence", 50) / 100.0
                        raw_signals.append(RawSignal(
                            source="ml_regime_routed", score=ml_score,
                            confidence=max(0.5, confidence),
                            details={
                                "regime": self._current_regime.value,
                                "direction": direction_str,
                                "models_used": regime_routing_result.get("models_used", []),
                            }
                        ))
                    else:
                        regime_routing_result = None  # fallback below

                if regime_routing_result is None:
                    # Direct prediction fallback (no regime routing)
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
        result = {
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
            "expected_hold_days": signal_event.expected_hold_days,
            "swing_phase": signal_event.swing_phase,
            "contributing_factors": [
                {"name": f.name, "score": f.score, "weight": f.weight, "description": f.description}
                for f in (signal_event.contributing_factors or [])
            ],
            "explanation": signal_event.explanation,
            "raw_signals_count": len(raw_signals),
        }

        # Enrich with regime context
        if self._current_regime:
            result["market_regime"] = self._current_regime.value
            result["regime_probabilities"] = self._regime_probabilities
        if regime_routing_result and "error" not in regime_routing_result:
            result["regime_routing"] = {
                "direction": regime_routing_result.get("regime_direction"),
                "confidence": regime_routing_result.get("confidence"),
                "weights_used": regime_routing_result.get("weights_used"),
                "models_used": regime_routing_result.get("models_used"),
            }

        return result

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

        # Phase 3: Regime Detection
        if self.hmm_detector:
            health["subsystems"]["regime_detection"] = {
                "status": "healthy",
                "current_regime": self._current_regime.value if self._current_regime else "unknown",
                "last_trained": self._regime_last_trained.isoformat() if self._regime_last_trained else None,
                "detectors": ["hmm", "kmeans", "gmm", "cusum"],
            }
        else:
            health["subsystems"]["regime_detection"] = {"status": "not_initialized"}

        # Phase 3: Position Sizer
        if self.position_sizer:
            health["subsystems"]["position_sizer"] = {
                "status": "healthy",
                "state": self.position_sizer.get_current_state(),
            }
        else:
            health["subsystems"]["position_sizer"] = {"status": "not_initialized"}

        # Phase 3.2: Sentiment Pipeline
        if self.sentiment_aggregator:
            health["subsystems"]["sentiment_pipeline"] = {
                "status": "healthy",
                "stats": self.sentiment_aggregator.get_stats(),
            }
        else:
            health["subsystems"]["sentiment_pipeline_phase3"] = {"status": "not_initialized"}

        if self.social_scraper:
            health["subsystems"]["social_scraper"] = {
                "status": "healthy",
                "stats": self.social_scraper.get_stats(),
            }
        else:
            health["subsystems"]["social_scraper"] = {"status": "not_initialized"}

        if self.earnings_analyzer:
            health["subsystems"]["earnings_analyzer"] = {
                "status": "healthy",
                "stats": self.earnings_analyzer.get_stats(),
            }
        else:
            health["subsystems"]["earnings_analyzer"] = {"status": "not_initialized"}

        # Phase 3.3: Agent System
        if self.agent_orchestrator:
            health["subsystems"]["agent_orchestrator"] = {
                "status": "healthy" if self.agent_orchestrator.is_available else "no_api_key",
                "stats": self.agent_orchestrator.get_stats(),
            }
        else:
            health["subsystems"]["agent_orchestrator"] = {"status": "not_initialized"}

        # Phase 3.5: RAG Knowledge Base
        if self.rag_knowledge_base and self.rag_knowledge_base.is_available:
            health["subsystems"]["rag_knowledge_base"] = {
                "status": "healthy",
                "stats": self.rag_knowledge_base.get_stats(),
            }
        else:
            health["subsystems"]["rag_knowledge_base"] = {"status": "not_initialized"}

        # Phase 3.6: Governance Scorer
        if self.governance_scorer:
            health["subsystems"]["governance_scorer"] = {
                "status": "healthy",
                "stats": self.governance_scorer.get_stats(),
            }
        else:
            health["subsystems"]["governance_scorer"] = {"status": "not_initialized"}

        # Phase 3.7: Sector Rotation
        if self.sector_rotation:
            health["subsystems"]["sector_rotation"] = {
                "status": "healthy",
                "stats": self.sector_rotation.get_stats(),
            }
        else:
            health["subsystems"]["sector_rotation"] = {"status": "not_initialized"}

        # Phase 3.8: Dividend Intelligence
        if self.dividend_intelligence:
            health["subsystems"]["dividend_intelligence"] = {
                "status": "healthy",
                "stats": self.dividend_intelligence.get_stats(),
            }
        else:
            health["subsystems"]["dividend_intelligence"] = {"status": "not_initialized"}

        # Phase 3.9: Regulatory Calendar
        if self.regulatory_calendar:
            health["subsystems"]["regulatory_calendar"] = {
                "status": "healthy",
                "stats": self.regulatory_calendar.get_stats(),
            }
        else:
            health["subsystems"]["regulatory_calendar"] = {"status": "not_initialized"}

        # Phase 3.10: Explainability Engine
        if self.explainability_engine:
            health["subsystems"]["explainability_engine"] = {
                "status": "healthy",
                "stats": self.explainability_engine.get_stats(),
            }
        else:
            health["subsystems"]["explainability_engine"] = {"status": "not_initialized"}

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
