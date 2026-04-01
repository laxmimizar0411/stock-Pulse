# Stock Pulse Brain — Step-by-Step Implementation Plan

The Stock Pulse Brain is the central intelligence system for Stock Pulse — an AI-powered Indian stock market analysis and prediction platform. This plan bridges the gap between the **existing codebase** (FastAPI backend, React frontend, basic data extraction, scoring engine, Redis/MongoDB/PostgreSQL) and the **target architecture** described in the two Brain documents.

The plan is organized into **6 Phases over ~12 months**, each building on the previous, with clear milestones and deliverables.

---

## Current State Analysis

### What Already Exists

| Component | Status | Location |
|-----------|--------|----------|
| FastAPI Backend | ✅ Running | [backend/server.py](file:///Users/shraddheysatpute/Downloads/Stock-Monitering-App/Stock-Pulse-5/backend/server.py) |
| Data Extractors | ✅ YFinance, Dhan, Groww, Screener, NSE Bhavcopy | `backend/data_extraction/extractors/` |
| Pipeline Orchestrator | ✅ Basic | `backend/data_extraction/pipeline/orchestrator.py` |
| Scoring Engine | ✅ Basic | `backend/services/scoring_engine.py` |
| Backtesting Service | ✅ Basic | `backend/services/backtesting_service.py` |
| LLM Service | ✅ Basic (Google Gemini) | `backend/services/llm_service.py` |
| Alert System | ✅ Basic | `backend/services/alerts_service.py` |
| Redis Cache | ✅ Running | `backend/services/cache_service.py` |
| TimeSeries Store | ✅ PostgreSQL | `backend/services/timeseries_store.py` |
| WebSocket Manager | ✅ Basic | `backend/services/websocket_manager.py` |
| MongoDB | ✅ Document store | `docker-compose.yml` |
| React Frontend | ✅ Basic dashboard | `frontend/src/` |
| Derived Metrics Jobs | ✅ Derivatives, macro, ML features, valuations | `backend/jobs/` |
| Docker Compose | ✅ Redis + MongoDB + PostgreSQL + Backend + Frontend | `docker-compose.yml` |

### What the Brain Requires (Gap Analysis)

| Brain Module | Gap | Priority |
|-------------|-----|----------|
| Event backbone (Kafka) | ❌ Not implemented | Phase 1 |
| Feature Store (Feast + Redis) | ❌ Only basic Redis cache exists | Phase 1 |
| Real-time streaming (Flink) | ❌ Not implemented | Phase 2 |
| AI/ML Models (TFT, LSTM, XGBoost, GARCH) | ❌ No models trained | Phase 2 |
| Signal Generation Engine | ⚠️ Basic scoring exists, needs multi-signal fusion | Phase 2 |
| HMM Regime Detection | ❌ Not implemented | Phase 3 |
| LLM Multi-Agent System (LangGraph) | ❌ Only basic LLM service exists | Phase 3 |
| FinBERT Sentiment Pipeline | ❌ Not implemented | Phase 3 |
| Risk Management Engine | ❌ No systematic risk management | Phase 3 |
| Options/Derivatives Intelligence | ❌ Not implemented | Phase 4 |
| Reinforcement Learning (PPO/FinRL) | ❌ Not implemented | Phase 5 |
| Foundation Models (Kronos/TimesFM) | ❌ Not implemented | Phase 5 |
| RAG Knowledge Base (Qdrant) | ❌ Not implemented | Phase 3 |
| Paper Trading Simulation | ❌ Not implemented | Phase 4 |
| Tax Optimization Module | ❌ Not implemented | Phase 4 |
| Corporate Governance Scoring | ❌ Not implemented | Phase 3 |

---

## Phase 1 — Data Foundation & Event Infrastructure (Months 1–2)

> **Goal**: Build the data backbone — robust data ingestion, event streaming with Kafka, feature store, and enhanced storage layer.

### Step 1.1 — Apache Kafka Event Bus Setup

- [ ] Add Kafka (KRaft mode, no ZooKeeper) to `docker-compose.yml`
- [ ] Create Kafka producer/consumer wrapper module (`backend/brain/events/kafka_manager.py`)
- [ ] Define core Kafka topics: `raw-ticks`, `normalized-ohlcv`, `signals`, `orders`, `alerts`, `features`
- [ ] Create Protobuf schemas for market data messages (`backend/brain/schemas/`)
- [ ] Implement dead-letter queue (DLQ) for failed message processing
- [ ] Add Kafka health checks and monitoring

**Files**:
- [NEW] `backend/brain/__init__.py`
- [NEW] `backend/brain/events/__init__.py`
- [NEW] `backend/brain/events/kafka_manager.py`
- [NEW] `backend/brain/events/topics.py`
- [NEW] `backend/brain/schemas/market_data.proto`
- [MODIFY] `docker-compose.yml` — add Kafka service

### Step 1.2 — Enhanced Data Ingestion Pipeline

- [ ] Upgrade existing extractors to publish data to Kafka topics
- [ ] Add Angel One SmartAPI extractor (primary free data source per Brain doc)
- [ ] Enhance NSE Bhavcopy extractor for CM-UDiFF new format
- [ ] Implement data normalization layer (canonical Protobuf schema)
- [ ] Add circuit breaker detection and handling
- [ ] Implement reconnection with exponential backoff for WebSocket feeds
- [ ] Add data quality checks: OHLC integrity, volume validation, price within circuit limits

**Files**:
- [NEW] `backend/brain/ingestion/__init__.py`
- [NEW] `backend/brain/ingestion/angel_one_extractor.py`
- [NEW] `backend/brain/ingestion/normalizer.py`
- [NEW] `backend/brain/ingestion/data_quality.py`
- [MODIFY] `backend/data_extraction/extractors/yfinance_comprehensive_extractor.py` — add Kafka publishing
- [MODIFY] `backend/data_extraction/extractors/nse_bhavcopy_extractor.py` — CM-UDiFF support

### Step 1.3 — Feature Store Setup (Feast + Redis)

- [ ] Install and configure Feast with Redis online store and PostgreSQL offline store
- [ ] Define feature views: technical indicators, fundamental ratios, macro variables
- [ ] Implement point-in-time correct feature retrieval (prevent data leakage)
- [ ] Set up feature versioning and registry
- [ ] Create feature computation module for: RSI, MACD, Bollinger Bands, VWAP, ATR, OBV
- [ ] Implement India-specific features: delivery volume %, FII/DII flows, promoter holding %

**Files**:
- [NEW] `backend/brain/features/__init__.py`
- [NEW] `backend/brain/features/feature_store.py`
- [NEW] `backend/brain/features/technical_indicators.py`
- [NEW] `backend/brain/features/fundamental_features.py`
- [NEW] `backend/brain/features/india_specific_features.py`
- [NEW] `backend/brain/features/feature_registry.py`
- [NEW] `feature_store/feature_repo/` — Feast feature repository config

### Step 1.4 — Storage Layer Enhancement

- [ ] Evaluate and optionally add QuestDB for time-series (6–13x faster than TimescaleDB)
- [ ] Set up MinIO (S3-compatible) for data lake / raw archival (Parquet format)
- [ ] Implement Redis TTL strategy: 1–5s during market hours, relaxed post-market
- [ ] Set up Apache Airflow for batch pipeline orchestration
- [ ] Create batch DAGs: `dag_daily_bhavcopy`, `dag_fii_dii`, `dag_fundamentals`, `dag_corporate_actions`, `dag_macro_data`

**Files**:
- [NEW] `backend/brain/storage/__init__.py`
- [NEW] `backend/brain/storage/questdb_client.py`
- [NEW] `backend/brain/storage/minio_client.py`
- [NEW] `backend/brain/batch/__init__.py`
- [NEW] `backend/brain/batch/airflow_dags/dag_daily_bhavcopy.py`
- [NEW] `backend/brain/batch/airflow_dags/dag_fii_dii.py`
- [NEW] `backend/brain/batch/airflow_dags/dag_fundamentals.py`
- [MODIFY] `docker-compose.yml` — add QuestDB, MinIO, Airflow services

### Phase 1 Milestone
> ✅ Market data flows through Kafka, features are computed and stored in Feast, batch pipelines run post-market via Airflow. All existing functionality continues to work.

---

## Phase 2 — AI/ML Model Training & Signal Generation (Months 3–5)

> **Goal**: Train core prediction models, build the signal generation engine with multi-signal fusion and confidence scoring.

### Step 2.1 — ML Training Infrastructure

- [ ] Set up MLflow for experiment tracking, model versioning, and model registry
- [ ] Implement walk-forward validation framework (never use k-fold for financial data)
- [ ] Implement Combinatorial Purged Cross-Validation (CPCV) for hyperparameter tuning
- [ ] Create feature engineering pipeline: log/scaling → correlation filtering → Boruta → LASSO → PCA
- [ ] Set up Optuna for Bayesian hyperparameter optimization with pruning

**Files**:
- [NEW] `backend/brain/ml/__init__.py`
- [NEW] `backend/brain/ml/training/__init__.py`
- [NEW] `backend/brain/ml/training/walk_forward.py`
- [NEW] `backend/brain/ml/training/cpcv.py`
- [NEW] `backend/brain/ml/training/feature_selection.py`
- [NEW] `backend/brain/ml/training/experiment_tracker.py`
- [MODIFY] `docker-compose.yml` — add MLflow service

### Step 2.2 — Core Prediction Models

- [ ] Train **GARCH(1,1)** + EGARCH for volatility forecasting (Tier 1 baseline)
- [ ] Train **XGBoost / LightGBM / CatBoost** for directional prediction (Tier 2 workhorses)
- [ ] Train **LSTM with attention** for intraday & short-term forecasting (Tier 3)
- [ ] Train **Temporal Fusion Transformer (TFT)** for multi-horizon forecasting (primary model)
- [ ] Train **N-BEATS** and **N-HiTS** for long-horizon forecasting
- [ ] Export models to ONNX format for production inference (5–20ms target)
- [ ] Implement model serving via BentoML or ONNX Runtime

**Files**:
- [NEW] `backend/brain/ml/models/__init__.py`
- [NEW] `backend/brain/ml/models/garch_model.py`
- [NEW] `backend/brain/ml/models/gradient_boosting.py`
- [NEW] `backend/brain/ml/models/lstm_attention.py`
- [NEW] `backend/brain/ml/models/tft_model.py`
- [NEW] `backend/brain/ml/models/nbeats_model.py`
- [NEW] `backend/brain/ml/models/nhits_model.py`
- [NEW] `backend/brain/ml/serving/__init__.py`
- [NEW] `backend/brain/ml/serving/model_server.py`
- [NEW] `backend/brain/ml/serving/onnx_inference.py`

### Step 2.3 — Signal Generation Engine

- [ ] Build multi-signal fusion architecture: Technical + Fundamental + Sentiment + Macro + Volume
- [ ] Implement confidence scoring formula: technical alignment (30%) + sentiment strength (25%) + fundamental support (20%) + volume confirmation (15%) + macro headwinds (10%)
- [ ] Implement signal thresholds: <40% suppressed, 40–60% watchlist, 60–80% actionable, >80% high-conviction
- [ ] Build stacked ensemble meta-model (XGBoost meta-learner)
- [ ] Implement meta-labeling (direction model + confidence model)
- [ ] Implement dynamic signal weighting based on context (earnings season, RBI policy, trending markets)
- [ ] Create structured signal output JSON: `{ticker, direction, confidence, target, stop_loss, contributing_factors, explanation}`

**Files**:
- [NEW] `backend/brain/signals/__init__.py`
- [NEW] `backend/brain/signals/signal_generator.py`
- [NEW] `backend/brain/signals/confidence_scorer.py`
- [NEW] `backend/brain/signals/signal_fusion.py`
- [NEW] `backend/brain/signals/meta_labeling.py`
- [NEW] `backend/brain/signals/signal_models.py` — Pydantic models for signal schema

### Step 2.4 — Backtesting Engine Enhancement

- [ ] Integrate **VectorBT Pro** as primary backtesting engine (1M orders in ~70–100ms)
- [ ] Model Indian transaction costs precisely: STT, exchange charges, GST, stamp duty, SEBI fees, DP charges
- [ ] Implement walk-forward optimization with rolling in-sample/out-of-sample windows
- [ ] Add **QuantStats** tearsheet generation (Sharpe, Sortino, Calmar, monthly heatmaps, drawdown analysis)
- [ ] Full performance metrics suite: CAGR, Sharpe, Sortino, Calmar, Omega, Information Ratio, Profit Factor, R-Multiple, Expectancy, Max DD Duration, Ulcer Index

**Files**:
- [MODIFY] `backend/services/backtesting_service.py` — upgrade with VectorBT, Indian cost model
- [NEW] `backend/brain/backtesting/__init__.py`
- [NEW] `backend/brain/backtesting/vectorbt_engine.py`
- [NEW] `backend/brain/backtesting/indian_costs.py`
- [NEW] `backend/brain/backtesting/performance_metrics.py`
- [NEW] `backend/brain/backtesting/quantstats_reports.py`

### Phase 2 Milestone
> ✅ ML models trained and serving predictions via ONNX Runtime. Signal generation produces unified Buy/Sell/Hold signals with confidence scores. Backtesting validates strategies against historical data with realistic Indian market costs.

---

## Phase 3 — Intelligence Layer & LLM Agents (Months 5–7)

> **Goal**: Build the LLM multi-agent system, sentiment pipeline, HMM regime detection, risk management, governance scoring, and RAG knowledge base.

### Step 3.1 — HMM Market Regime Detection

- [ ] Train 3-state Gaussian HMM (bull, bear, sideways) on: daily returns, rolling volatility, India VIX, FII/FPI flows, INR/USD
- [ ] Implement regime-conditional model routing (specialist models per regime)
- [ ] Implement regime-aware strategy selection and position sizing
- [ ] Add complementary regime detection: K-Means/GMM, CUSUM change-point detection

**Files**:
- [NEW] `backend/brain/regime/__init__.py`
- [NEW] `backend/brain/regime/hmm_detector.py`
- [NEW] `backend/brain/regime/regime_router.py`
- [NEW] `backend/brain/regime/changepoint_detector.py`

### Step 3.2 — FinBERT Sentiment Pipeline

- [ ] Deploy FinBERT model (+ Indian variant `kdave/FineTuned_Finbert`)
- [ ] Build NLP pipeline: language detect → Hindi→English translation (IndicTrans2) → cleaning → NER → sentiment → event extraction
- [ ] Implement multi-model sentiment ensemble: 0.5×FinBERT + 0.2×VADER + 0.3×LLM
- [ ] Build news scrapers: Economic Times, Moneycontrol, LiveMint
- [ ] Implement social sentiment: Twitter/X, r/IndianStreetBets, TradingView India
- [ ] Build earnings call analyzer: management discussion vs Q&A section separation, tone divergence detection

**Files**:
- [NEW] `backend/brain/sentiment/__init__.py`
- [NEW] `backend/brain/sentiment/finbert_model.py`
- [NEW] `backend/brain/sentiment/nlp_pipeline.py`
- [NEW] `backend/brain/sentiment/news_scrapers.py`
- [NEW] `backend/brain/sentiment/social_scraper.py`
- [NEW] `backend/brain/sentiment/earnings_analyzer.py`
- [NEW] `backend/brain/sentiment/sentiment_ensemble.py`

### Step 3.3 — LLM Multi-Agent System

- [ ] Set up **LangGraph** for agent orchestration (graph-based state machine)
- [ ] Implement tiered LLM routing: Tier 1 (Claude/GPT-5 for deep analysis), Tier 2 (GPT-4.1 mini for extraction), Tier 3 (local FinGPT/Mistral)
- [ ] Build 4 analyst agents: Fundamental, Technical, Sentiment, Macro
- [ ] Build dialectical research agents: Bull Researcher + Bear Researcher → Research Synthesizer
- [ ] Build Trader Agent (synthesis to actionable signals) + Risk Management Agent (veto power)
- [ ] Implement Report Generation Agent: Morning Brief (8:30 AM), Market Wrap (4:30 PM), Weekly Analysis
- [ ] Add semantic caching for repeated LLM queries

**Files**:
- [NEW] `backend/brain/agents/__init__.py`
- [NEW] `backend/brain/agents/orchestrator.py` — LangGraph graph definition
- [NEW] `backend/brain/agents/fundamental_analyst.py`
- [NEW] `backend/brain/agents/technical_analyst.py`
- [NEW] `backend/brain/agents/sentiment_analyst.py`
- [NEW] `backend/brain/agents/macro_analyst.py`
- [NEW] `backend/brain/agents/bull_researcher.py`
- [NEW] `backend/brain/agents/bear_researcher.py`
- [NEW] `backend/brain/agents/research_synthesizer.py`
- [NEW] `backend/brain/agents/trader_agent.py`
- [NEW] `backend/brain/agents/risk_agent.py`
- [NEW] `backend/brain/agents/report_generator.py`
- [NEW] `backend/brain/agents/llm_router.py`
- [MODIFY] `backend/services/llm_service.py` — upgrade to tiered routing

### Step 3.4 — Risk Management Engine

- [ ] Implement hybrid ATR-volatility stop-loss: `Entry - (ATR(14) × Multiplier)`
- [ ] Implement capital protection escalation: 10% DD → halve positions, 15% → halt new entries, 20% → kill switch
- [ ] Implement fractional Kelly position sizing (Half Kelly default, Quarter Kelly in high-vol regimes)
- [ ] Implement VaR (Historical Simulation + Parametric + Monte Carlo)
- [ ] Implement CVaR / Expected Shortfall
- [ ] Add stress testing scenarios: 2008 GFC, COVID March 2020, Demonetization 2016
- [ ] Implement SEBI margin requirement checks

**Files**:
- [NEW] `backend/brain/risk/__init__.py`
- [NEW] `backend/brain/risk/stop_loss.py`
- [NEW] `backend/brain/risk/position_sizing.py`
- [NEW] `backend/brain/risk/var_calculator.py`
- [NEW] `backend/brain/risk/stress_testing.py`
- [NEW] `backend/brain/risk/capital_protection.py`
- [NEW] `backend/brain/risk/sebi_compliance.py`

### Step 3.5 — RAG Knowledge Base

- [ ] Deploy **Qdrant** vector database
- [ ] Implement document chunking (512-token chunks, 50-token overlap)
- [ ] Set up hybrid search: BM25 + semantic vector search (text-embedding-3-small)
- [ ] Add **Cohere rerank** for improved retrieval accuracy
- [ ] Index: company filings, SEBI circulars, RBI policies, brokerage research
- [ ] Implement agentic RAG for multi-hop financial queries

**Files**:
- [NEW] `backend/brain/rag/__init__.py`
- [NEW] `backend/brain/rag/vector_store.py`
- [NEW] `backend/brain/rag/document_processor.py`
- [NEW] `backend/brain/rag/retriever.py`
- [NEW] `backend/brain/rag/reranker.py`
- [MODIFY] `docker-compose.yml` — add Qdrant service

### Step 3.6 — Corporate Governance & Promoter Risk Scoring

- [ ] Implement Governance Score (0-100): promoter pledging (25%), RPTs (20%), auditor quality (15%), board independence (15%), regulatory history (15%), disclosure timeliness (10%)
- [ ] Track promoter holding changes from BSE/NSE quarterly filings
- [ ] Detect red flags: auditor resignation, excessive RPTs, SEBI show-cause notices
- [ ] Auto-exclude stocks with Governance Score < 40 from investable universe

**Files**:
- [NEW] `backend/brain/governance/__init__.py`
- [NEW] `backend/brain/governance/governance_scorer.py`
- [NEW] `backend/brain/governance/promoter_tracker.py`
- [NEW] `backend/brain/governance/red_flag_detector.py`

### Step 3.7 — SHAP Explainability

- [ ] Generate SHAP values for all XGBoost/ensemble predictions
- [ ] Create waterfall chart visualizations for the dashboard
- [ ] Add LIME for lightweight on-demand explanations
- [ ] Generate natural language explanations from SHAP values + agent reasoning

**Files**:
- [NEW] `backend/brain/explainability/__init__.py`
- [NEW] `backend/brain/explainability/shap_explainer.py`
- [NEW] `backend/brain/explainability/lime_explainer.py`
- [NEW] `backend/brain/explainability/nl_explanation.py`

### Phase 3 Milestone
> ✅ Multi-agent LLM research team produces daily research/signals. FinBERT processes Indian financial news. HMM routes predictions to regime-specific models. Risk management protects capital with ATR stops, Kelly sizing, and VaR monitoring. RAG knowledge base answers financial queries.

---

## Phase 4 — Options Intelligence, Paper Trading & Tax Optimization (Months 7–9)

> **Goal**: Add options/derivatives intelligence, paper trading simulation, tax optimization, IPO analysis, and enhanced delivery channels.

### Step 4.1 — Options & Derivatives Intelligence

- [ ] Implement real-time Greeks computation (Delta, Gamma, Theta, Vega, Rho)
- [ ] Build Black-Scholes + Black-76 pricing engines
- [ ] Build Implied Volatility surface (strike × expiry grid)
- [ ] Implement PCR, Max Pain, OI analysis, IV Rank/Percentile, Unusual Options Activity (UOA) detection
- [ ] Build options strategy recommendation engine (regime × IV × view → strategy)
- [ ] Add expiry day intelligence: GEX analysis, Thursday-specific models, Theta crush management

**Files**:
- [NEW] `backend/brain/options/__init__.py`
- [NEW] `backend/brain/options/greeks_engine.py`
- [NEW] `backend/brain/options/pricing_models.py`
- [NEW] `backend/brain/options/volatility_surface.py`
- [NEW] `backend/brain/options/options_signals.py`
- [NEW] `backend/brain/options/strategy_recommender.py`
- [NEW] `backend/brain/options/expiry_intelligence.py`

### Step 4.2 — Paper Trading & Simulation Engine

- [ ] Build virtual trading engine mirroring full production pipeline
- [ ] Implement shadow order book with realistic slippage model: `0.05% + f(volume, spread)`
- [ ] Track full metrics: Sharpe, Sortino, max drawdown, win rate, R-multiple, profit factor
- [ ] Build A/B comparison dashboard: paper vs live vs buy-and-hold vs NIFTY 50
- [ ] Implement promotion criteria: 3 months paper, Sharpe >1.5, max DD <15%, win rate >55%
- [ ] Implement gradual capital allocation scaling (10% → 100%)

**Files**:
- [NEW] `backend/brain/paper_trading/__init__.py`
- [NEW] `backend/brain/paper_trading/virtual_engine.py`
- [NEW] `backend/brain/paper_trading/shadow_orderbook.py`
- [NEW] `backend/brain/paper_trading/promotion_criteria.py`
- [NEW] `backend/brain/paper_trading/performance_tracker.py`

### Step 4.3 — Indian Tax Optimization

- [ ] Implement FY 2025–26 capital gains tax rules (STCG 20%, LTCG 12.5%)
- [ ] Build tax-loss harvesting engine (India has no wash-sale rule)
- [ ] Add holding period intelligence to SELL signals (`days_to_ltcg`, `tax_saving_if_held`)
- [ ] Implement year-end (March) portfolio-wide tax optimization
- [ ] Add tax-adjusted returns to all signal outputs

**Files**:
- [NEW] `backend/brain/tax/__init__.py`
- [NEW] `backend/brain/tax/capital_gains.py`
- [NEW] `backend/brain/tax/tax_loss_harvesting.py`
- [NEW] `backend/brain/tax/holding_period_optimizer.py`

### Step 4.4 — IPO Analysis Module

- [ ] Build DRHP/RHP analysis agent (financial health, peer comparison, promoter background)
- [ ] Implement GMP tracking scraper
- [ ] Track subscription data: QIB, NII, Retail multiples
- [ ] Build listing day prediction model
- [ ] Add lock-in expiry tracking (promoter 18 months, anchor 30/90 days)

**Files**:
- [NEW] `backend/brain/ipo/__init__.py`
- [NEW] `backend/brain/ipo/ipo_analyzer.py`
- [NEW] `backend/brain/ipo/gmp_tracker.py`
- [NEW] `backend/brain/ipo/listing_predictor.py`

### Step 4.5 — Communication Channels

- [ ] Build Telegram bot (`python-telegram-bot`): signal delivery, `/portfolio`, `/signals`, `/risk`, `/market`
- [ ] Implement WhatsApp Business API integration for morning briefs and P1 alerts
- [ ] Configure Firebase Cloud Messaging with priority tiers (P1 critical → P3 digest)

**Files**:
- [NEW] `backend/brain/delivery/__init__.py`
- [NEW] `backend/brain/delivery/telegram_bot.py`
- [NEW] `backend/brain/delivery/whatsapp_service.py`
- [NEW] `backend/brain/delivery/push_notifications.py`

### Phase 4 Milestone
> ✅ Options intelligence provides Greeks, strategy recommendations, and expiry day analysis. Paper trading validates strategies for 3+ months before live deployment. Tax module optimizes after-tax returns. IPO analyzer identifies pre-listing opportunities.

---

## Phase 5 — Advanced ML & Real-Time Engine (Months 9–11)

> **Goal**: Deploy foundation models, reinforcement learning for portfolio optimization, real-time Flink streaming, and global correlation analytics.

### Step 5.1 — Foundation Model Integration

- [ ] Fine-tune **Kronos** (12B K-line records, OHLCV tokenization) on Indian market data
- [ ] Fine-tune **Google TimesFM 2.5** for stock price prediction
- [ ] Evaluate **Chronos** and **Moirai** as zero-shot baselines
- [ ] Implement regime-conditional ensembling: specialist models selected by HMM state + stacked XGBoost meta-learner

**Files**:
- [NEW] `backend/brain/ml/models/kronos_model.py`
- [NEW] `backend/brain/ml/models/timesfm_model.py`
- [NEW] `backend/brain/ml/models/ensemble_manager.py`

### Step 5.2 — Reinforcement Learning Portfolio Optimization

- [ ] Set up **FinRL** framework with PPO as primary agent
- [ ] Implement environment for Indian market: NIFTY 50 universe, Indian cost model, margin rules
- [ ] Train PPO agent on historical data with walk-forward validation
- [ ] Benchmark against mean-variance optimization (target: Sharpe >2.0)
- [ ] Implement Black-Litterman optimization with AI-generated market views

**Files**:
- [NEW] `backend/brain/portfolio/__init__.py`
- [NEW] `backend/brain/portfolio/rl_optimizer.py`
- [NEW] `backend/brain/portfolio/finrl_environment.py`
- [NEW] `backend/brain/portfolio/black_litterman.py`
- [NEW] `backend/brain/portfolio/hrp_optimizer.py`

### Step 5.3 — Real-Time Flink Streaming (or Python-Native Alternative)

- [ ] Evaluate Apache Flink vs Python-native streaming (Faust/Bytewax) for current scale
- [ ] Implement 4 parallel streaming jobs: Feature Computation, CEP Signal Detection, Anomaly Detection, Feature Freshness Monitor
- [ ] Implement windowed aggregations: 1min, 5min, 15min, 1hr OHLCV
- [ ] Implement chart pattern detection: double bottoms, volume breakouts, head-and-shoulders
- [ ] Target latency: <100ms end-to-end

**Files**:
- [NEW] `backend/brain/streaming/__init__.py`
- [NEW] `backend/brain/streaming/feature_computation.py`
- [NEW] `backend/brain/streaming/cep_signal_detection.py`
- [NEW] `backend/brain/streaming/anomaly_detector.py`
- [NEW] `backend/brain/streaming/freshness_monitor.py`

### Step 5.4 — Global Market Correlation & Pre-Market Intelligence

- [ ] Implement overnight global signal processing: S&P 500, NASDAQ, SGX/GIFT NIFTY, Asian markets, crude oil, DXY, US 10Y
- [ ] Implement cross-asset correlation matrix with India-specific mappings
- [ ] Implement DCC-GARCH for time-varying correlation
- [ ] Build pre-market prediction engine (produces opening signal by 8:30 AM IST)
- [ ] Implement correlation breakout alerts (>2σ divergence)

**Files**:
- [NEW] `backend/brain/correlation/__init__.py`
- [NEW] `backend/brain/correlation/global_signals.py`
- [NEW] `backend/brain/correlation/correlation_matrix.py`
- [NEW] `backend/brain/correlation/premarket_engine.py`

### Step 5.5 — Alternative Data Integration

- [ ] Google Trends India (`pytrends`) — brand/sector search interest as leading indicators
- [ ] Web scraping: e-commerce pricing, Naukri.com job postings, app download rankings
- [ ] UPI transaction data from NPCI (monthly, fintech impact)
- [ ] Regulatory filings: SEBI SAST, bulk/block deals, insider trading disclosures
- [ ] Assign signal decay half-lives per data source

**Files**:
- [NEW] `backend/brain/alt_data/__init__.py`
- [NEW] `backend/brain/alt_data/google_trends.py`
- [NEW] `backend/brain/alt_data/web_scraper.py`
- [NEW] `backend/brain/alt_data/regulatory_filings.py`
- [NEW] `backend/brain/alt_data/upi_data.py`

### Phase 5 Milestone
> ✅ Foundation models provide zero-shot and fine-tuned predictions. RL agent optimizes portfolio allocation. Real-time streaming computes features and detects patterns in <100ms. Global correlations inform pre-market signals. Alternative data provides information edge.

---

## Phase 6 — Production Hardening & Dashboard (Months 11–12)

> **Goal**: Security, disaster recovery, monitoring, SEBI compliance, load testing, and full dashboard build.

### Step 6.1 — Security & Secrets Management

- [ ] Deploy HashiCorp Vault or AWS Secrets Manager for all credentials
- [ ] Implement AES-256 encryption at rest, TLS 1.3 in transit, mTLS between services
- [ ] Configure static elastic IPs for broker API connections (SEBI requirement)
- [ ] Implement audit logging with SHA-256 payload hashes (5-year retention)

### Step 6.2 — Disaster Recovery

- [ ] Implement broker API failover (primary → secondary within 5s)
- [ ] Configure Kafka ISR ≥ 2 across AZs
- [ ] Build "guardian process" for emergency position exits
- [ ] Set up chaos engineering tests (Litmus Chaos) for monthly validation

### Step 6.3 — Monitoring & Observability

- [ ] Deploy Prometheus + Grafana for metrics
- [ ] Set up Jaeger/OpenTelemetry for distributed tracing
- [ ] Monitor model drift via Evidently AI (KL-divergence, PSI)
- [ ] Build data quality monitoring dashboard in Grafana
- [ ] Implement retraining triggers on performance degradation

### Step 6.4 — Frontend Dashboard Enhancement

- [ ] Integrate **TradingView Lightweight Charts** for interactive stock charts
- [ ] Build 7 primary panels: Market Overview, Signal Board, Stock Deep Dive, Portfolio Tracker, Sentiment Dashboard, Agent Activity Log, Report Center
- [ ] Add SHAP waterfall chart visualizations per stock
- [ ] Implement real-time WebSocket updates for signals and prices
- [ ] Build automated PDF report generation and delivery

### Step 6.5 — Load Testing & SEBI Compliance

- [ ] Run load tests: 50K ticks/sec ingestion, <100ms P95 E2E, 10K concurrent WebSocket connections
- [ ] Validate market open stress test (10x burst at 9:15 AM)
- [ ] Implement SEBI algo registration requirements (static IP, order audit trail, <10 orders/sec classification)
- [ ] Configure Kubernetes CronHPA for market-hours autoscaling

### Phase 6 Milestone
> ✅ Production-grade system with security, DR, monitoring, compliance, and a stunning dashboard. Ready for live trading with paper-validated strategies.

---

## Verification Plan

### Automated Tests

Each phase will include unit tests and integration tests. Testing approach:

1. **Phase 1**: Test Kafka producer/consumer roundtrip, feature computation accuracy against known values, data quality validation rules
   - Run: `cd backend && python -m pytest tests/brain/test_events.py tests/brain/test_features.py -v`

2. **Phase 2**: Test model inference latency (<20ms), signal confidence scoring calculations, backtesting cost model against manual calculations
   - Run: `cd backend && python -m pytest tests/brain/test_models.py tests/brain/test_signals.py tests/brain/test_backtesting.py -v`

3. **Phase 3**: Test HMM regime transitions, sentiment scoring pipeline, agent response quality, risk calculations (VaR, position sizing), SHAP value generation
   - Run: `cd backend && python -m pytest tests/brain/test_regime.py tests/brain/test_sentiment.py tests/brain/test_risk.py -v`

4. **Phase 4**: Test Greeks calculations against Black-Scholes analytical solutions, paper trading order execution, tax calculations
   - Run: `cd backend && python -m pytest tests/brain/test_options.py tests/brain/test_paper_trading.py tests/brain/test_tax.py -v`

### Manual Verification

> [!IMPORTANT]
> Each phase should be manually validated by the developer (you) by running the system locally with Docker Compose and verifying the dashboard shows expected data and signals.

**Phase 1 manual check**: Start all services with `docker compose up`, verify Kafka topics exist via Kafka UI, check feature store serves features via API.

**Phase 2 manual check**: Trigger model training, verify MLflow UI shows experiments, check signal API returns structured JSON with confidence scores.

**Phase 3 manual check**: Run agent research workflow for a specific stock (e.g., RELIANCE), verify it produces bull/bear arguments and final synthesis with SHAP explanations.

**Phase 4 manual check**: View options chain for NIFTY, verify Greeks are computed, check paper trading creates virtual orders.

---

## Recommended Starting Point

> [!TIP]
> **Start with Phase 1, Step 1.1 (Kafka setup)** — this is the backbone. Everything else depends on having the event-driven infrastructure in place. However, we can parallelize by also starting Step 1.3 (Feature Store) since features can initially be computed in batch without Kafka.

The entire `backend/brain/` directory is the new code home for the Brain system, keeping it cleanly separated from the existing `backend/services/` and `backend/data_extraction/` code.
