# Stock Pulse Brain — Step-by-Step Implementation Guide

The Stock Pulse Brain is the central intelligence system for Stock Pulse — an AI-powered Indian stock market analysis and prediction platform. Its **primary mission is maximizing profit through swing trading** (~80% focus on 2–30 day swing trades, ~10% intraday, ~10% positional/long-term).

This plan bridges the gap between the **existing codebase** (FastAPI backend, React frontend, basic data extraction, scoring engine, Redis/MongoDB/PostgreSQL) and the **target architecture** described in the unified Brain document (`Stock-Pulse-Brain-Unified-V.md`).

The plan is organized into **6 Phases**, each building on the previous, with clear milestones and deliverables.

> **Note:** This document and the unified guide (`Stock-Pulse-Brain-Unified-V.md`) are kept in sync. The unified guide is the authoritative reference for architecture and design; this document is the step-by-step implementation roadmap with file paths.

---

## Current State Analysis

### What Already Exists

| Component | Status | Location |
|-----------|--------|----------|
| FastAPI Backend | ✅ Running | `backend/server.py` |
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

| Brain Module | Gap | Phase |
|-------------|-----|-------|
| Event backbone (Kafka) | ❌ Not implemented | Phase 1 |
| Feature Store (Feast + Redis) | ❌ Only basic Redis cache exists | Phase 1 |
| AI/ML Models (TFT, LSTM, XGBoost, GARCH) | ❌ No models trained | Phase 2 |
| Signal Generation Engine | ⚠️ Basic scoring exists, needs multi-signal fusion | Phase 2 |
| HMM Regime Detection | ❌ Not implemented | Phase 3 |
| LLM Multi-Agent System (LangGraph) | ❌ Only basic LLM service exists | Phase 3 |
| FinBERT Sentiment Pipeline | ❌ Not implemented | Phase 3 |
| Risk Management Engine | ❌ No systematic risk management | Phase 3 |
| Sector Rotation Strategy | ❌ Not implemented | Phase 3 |
| Dividend Intelligence | ❌ Not implemented | Phase 3 |
| Regulatory Event Calendar | ❌ Not implemented | Phase 3 |
| Corporate Governance Scoring | ❌ Not implemented | Phase 3 |
| RAG Knowledge Base (Qdrant) | ❌ Not implemented | Phase 3 |
| IPO Analysis Module | ❌ Not implemented | Phase 4 |
| Indian Tax Optimization | ❌ Not implemented | Phase 4 |
| Paper Trading Validation | ❌ Not implemented | Phase 4 |
| Real-time Streaming (Faust/Bytewax) | ❌ Not implemented | Phase 5 |
| Reinforcement Learning (PPO/FinRL) | ❌ Not implemented | Phase 5 |
| Foundation Models (Kronos/TimesFM) | ❌ Not implemented | Phase 5 |
| Security & Secrets Management | ❌ Not implemented | Phase 6 |
| System Health Dashboard | ❌ Not implemented | Phase 6 |
| Watchlist & Multi-Portfolio | ❌ Not implemented | Phase 6 |
| MF/ETF Analysis | ❌ Not implemented | Phase 6 |

---

## Phase 1 — Data Foundation & Event Infrastructure

> **Goal**: Build the data backbone — robust data ingestion, event streaming with Kafka, feature store, and enhanced storage layer.

### Step 1.1 — Apache Kafka Event Bus Setup

- [ ] Add Kafka (KRaft mode, no ZooKeeper) to `docker-compose.yml`
- [ ] Create Kafka producer/consumer wrapper module
- [ ] Define core Kafka topics: `raw-ticks`, `normalized-ohlcv`, `signals`, `orders`, `alerts`, `features`
- [ ] Create Pydantic schemas for market data messages
- [ ] Implement dead-letter queue (DLQ) for failed message processing
- [ ] Add Kafka health checks and monitoring

**Files**:
- `backend/brain/__init__.py` *(exists)*
- `backend/brain/events/__init__.py` *(exists)*
- `backend/brain/events/kafka_manager.py` *(exists)*
- `backend/brain/events/topics.py` *(exists)*
- `backend/brain/schemas/market_data.py` *(exists — Pydantic, not Protobuf)*
- [MODIFY] `docker-compose.yml` — add Kafka service

### Step 1.2 — Enhanced Data Ingestion Pipeline

- [ ] Upgrade existing extractors to publish data to Kafka topics
- [ ] Enhance NSE Bhavcopy extractor for CM-UDiFF new format
- [ ] Implement data normalization layer (canonical Pydantic schema)
- [ ] Add circuit breaker detection and handling
- [ ] Implement reconnection with exponential backoff for WebSocket feeds
- [ ] Add data quality checks: OHLC integrity, volume validation, price within circuit limits

**Files**:
- `backend/brain/ingestion/__init__.py` *(exists)*
- `backend/brain/ingestion/normalizer.py` *(exists)*
- `backend/brain/ingestion/data_quality.py` *(exists)*
- `backend/brain/ingestion/kafka_bridge.py` *(exists)*
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
- `backend/brain/features/__init__.py` *(exists)*
- `backend/brain/features/feature_store.py` *(exists)*
- `backend/brain/features/technical_features.py` *(exists)*
- `backend/brain/features/fundamental_features.py` *(exists)*
- `backend/brain/features/cross_sectional_features.py` *(exists)*
- `backend/brain/features/macro_features.py` *(exists)*
- `backend/brain/features/feature_registry.py` *(exists)*
- `backend/brain/features/feature_pipeline.py` *(exists)*
- `backend/brain/features/timeseries_fetchers.py` *(exists)*
- [NEW] `feature_store/feature_repo/` — Feast feature repository config

### Step 1.4 — Storage Layer Enhancement

- [ ] Set up MinIO (S3-compatible) for data lake / raw archival (Parquet format)
- [ ] Implement Redis TTL strategy: 1–5s during market hours, relaxed post-market
- [ ] Set up Apache Airflow for batch pipeline orchestration
- [ ] Create batch DAGs: `dag_daily_bhavcopy`, `dag_fii_dii`, `dag_fundamentals`, `dag_corporate_actions`, `dag_macro_data`

**Files**:
- `backend/brain/storage/__init__.py` *(exists)*
- `backend/brain/storage/minio_client.py` *(exists)*
- `backend/brain/storage/parquet_writer.py` *(exists)*
- [NEW] `backend/brain/batch/__init__.py`
- [NEW] `backend/brain/batch/airflow_dags/dag_daily_bhavcopy.py`
- [NEW] `backend/brain/batch/airflow_dags/dag_fii_dii.py`
- [NEW] `backend/brain/batch/airflow_dags/dag_fundamentals.py`
- [MODIFY] `docker-compose.yml` — add MinIO, Airflow services

### Phase 1 Milestone
> ✅ Market data flows through Kafka, features are computed and stored in Feast, batch pipelines run post-market via Airflow. All existing functionality continues to work.

---

## Phase 2 — AI/ML Model Training & Swing Signal Generation

> **Goal**: Train core prediction models optimized for **swing trading (2–30 day holds)**, build the signal generation engine with multi-signal fusion and confidence scoring.

### Step 2.1 — ML Training Infrastructure

- [ ] Set up MLflow for experiment tracking, model versioning, and model registry
- [ ] Implement walk-forward validation framework (never use k-fold for financial data)
- [ ] Implement Combinatorial Purged Cross-Validation (CPCV) for hyperparameter tuning
- [ ] Create feature engineering pipeline: log/scaling → correlation filtering → Boruta → LASSO → PCA
- [ ] Set up Optuna for Bayesian hyperparameter optimization with pruning

**Files**:
- `backend/brain/models_ml/__init__.py` *(exists)*
- `backend/brain/models_ml/base_model.py` *(exists)*
- `backend/brain/models_ml/validation.py` *(exists — walk-forward + CPCV)*
- [MODIFY] `docker-compose.yml` — add MLflow service

### Step 2.2 — Core Prediction Models (Swing-Trading Optimized)

- [ ] Train **GARCH(1,1)** + EGARCH for volatility forecasting → optimal swing entry timing via volatility regime (Tier 1)
- [ ] Train **XGBoost / LightGBM / CatBoost** for **primary swing direction (2–30 day horizon)** (Tier 2 — Primary ★)
- [ ] Train **LSTM with attention** for intraday pattern detection (Tier 3 — 10% allocation)
- [ ] Train **Temporal Fusion Transformer (TFT)** for **multi-horizon swing targets (5d/10d/20d quantile forecasts)** (Primary ★)
- [ ] Train **N-BEATS** and **N-HiTS** for positional horizon (1–6 months, 10% allocation)
- [ ] Export models to ONNX format for production inference (5–20ms target)
- [ ] Implement model serving via ONNX Runtime

**Files**:
- `backend/brain/models_ml/statistical/garch_model.py` *(exists)*
- `backend/brain/models_ml/statistical/arima_model.py` *(exists)*
- `backend/brain/models_ml/gradient_boosting/xgboost_model.py` *(exists)*
- `backend/brain/models_ml/gradient_boosting/lightgbm_model.py` *(exists)*
- `backend/brain/models_ml/gradient_boosting/ensemble.py` *(exists)*
- `backend/brain/models_ml/deep_learning/` *(placeholder exists — LSTM-Attention, TFT, N-BEATS)*

### Step 2.3 — Swing Signal Generation Engine

- [ ] Build multi-signal fusion architecture: Technical + Fundamental + Sentiment + Macro + Volume
- [ ] Implement **swing-weighted** confidence scoring: Technical(35%) + Sentiment(20%) + Fundamental(20%) + Volume(15%) + Macro(10%)
- [ ] Implement signal thresholds: <40% suppressed, 40–60% watchlist, 60–80% actionable, >80% high-conviction
- [ ] Implement meta-labeling (direction model + confidence model)
- [ ] Add **swing-specific signal fields**: `expected_hold_days`, `risk_reward_ratio`, `swing_phase` (breakout/pullback/trend)
- [ ] Create structured signal output JSON: `{ticker, direction, confidence, target, stop_loss, expected_hold_days, risk_reward_ratio, swing_phase, contributing_factors, explanation}`

**Files**:
- `backend/brain/signals/__init__.py` *(exists)*
- `backend/brain/signals/signal_generator.py` *(exists)*
- `backend/brain/signals/confidence_scorer.py` *(exists)*
- `backend/brain/signals/signal_fusion.py` *(exists)*
- `backend/brain/models/signals.py` *(exists — Pydantic signal schemas)*

### Step 2.4 — Backtesting Engine Enhancement

- [ ] Integrate **VectorBT Pro** as primary backtesting engine (1M orders in ~70–100ms)
- [ ] Model Indian transaction costs precisely: STT, exchange charges, GST, stamp duty, SEBI fees, DP charges
- [ ] Implement walk-forward optimization with rolling in-sample/out-of-sample windows
- [ ] Add **QuantStats** tearsheet generation (Sharpe, Sortino, Calmar, monthly heatmaps, drawdown analysis)
- [ ] Full performance metrics suite: CAGR, Sharpe, Sortino, Calmar, Omega, Information Ratio, Profit Factor, R-Multiple, Expectancy, Max DD Duration, Ulcer Index

**Files**:
- [MODIFY] `backend/services/backtesting_service.py` — upgrade with VectorBT, Indian cost model
- `backend/brain/backtesting/__init__.py` *(exists)*
- `backend/brain/risk/indian_costs.py` *(exists — STT, GST, stamp duty, SEBI, DP)*
- [NEW] `backend/brain/backtesting/vectorbt_engine.py`
- [NEW] `backend/brain/backtesting/performance_metrics.py`
- [NEW] `backend/brain/backtesting/quantstats_reports.py`

### Phase 2 Milestone
> ✅ ML models trained and serving predictions via ONNX Runtime, optimized for swing trading horizons. Signal generation produces unified Buy/Sell/Hold signals with confidence scores and swing-specific fields (hold_days, risk_reward, swing_phase). Backtesting validates strategies against historical data with realistic Indian market costs.

---

## Phase 3 — Intelligence Layer, LLM Agents & Risk Management

> **Goal**: Build the LLM multi-agent system (2-tier), sentiment pipeline, HMM regime detection, risk management, governance scoring, RAG knowledge base, sector rotation, dividend intelligence, and regulatory event calendar.

### Step 3.1 — HMM Market Regime Detection

- [ ] Train 3-state Gaussian HMM (bull, bear, sideways) on: daily returns, rolling volatility, India VIX, FII/FPI flows, INR/USD
- [ ] Implement regime-conditional model routing (specialist swing models per regime)
- [ ] Implement regime-aware strategy selection and position sizing
- [ ] Add complementary regime detection: K-Means/GMM, CUSUM change-point detection

**Files**:
- `backend/brain/regime/__init__.py` *(exists)*
- `backend/brain/regime/hmm_detector.py` *(exists)*
- `backend/brain/regime/regime_store.py` *(exists)*
- [NEW] `backend/brain/regime/changepoint_detector.py`
- [NEW] `backend/brain/regime/regime_router.py`

### Step 3.2 — FinBERT Sentiment Pipeline

- [ ] Deploy FinBERT model (+ Indian variant `kdave/FineTuned_Finbert`)
- [ ] Build NLP pipeline: language detect → Hindi→English translation (IndicTrans2) → cleaning → NER → sentiment → event extraction
- [ ] Implement multi-model sentiment ensemble: 0.5×FinBERT + 0.2×VADER + 0.3×LLM
- [ ] Build news scrapers: Economic Times, Moneycontrol, LiveMint
- [ ] Implement social sentiment: Twitter/X, r/IndianStreetBets, TradingView India
- [ ] Build earnings call analyzer: management discussion vs Q&A section separation, tone divergence detection

**Files**:
- `backend/brain/sentiment/__init__.py` *(exists)*
- `backend/brain/sentiment/finbert_analyzer.py` *(exists)*
- `backend/brain/sentiment/entity_extractor.py` *(exists)*
- `backend/brain/sentiment/news_scraper.py` *(exists)*
- `backend/brain/sentiment/sentiment_aggregator.py` *(exists)*
- [NEW] `backend/brain/sentiment/social_scraper.py`
- [NEW] `backend/brain/sentiment/earnings_analyzer.py`

### Step 3.3 — LLM Multi-Agent System (2-Tier)

- [ ] Set up **LangGraph** for agent orchestration (graph-based state machine)
- [ ] Implement 2-tier LLM routing: **Tier 1** (Claude/GPT-5 for deep analysis), **Tier 2** (GPT-4.1-mini for extraction/lightweight tasks)
- [ ] Build 4 analyst agents: Fundamental, Technical, Sentiment, Macro
- [ ] Build dialectical research agents: Bull Researcher + Bear Researcher → Research Synthesizer
- [ ] Build Trader Agent (synthesis to actionable signals) + Risk Management Agent (veto power)
- [ ] Implement Report Generation Agent: Morning Brief (8:30 AM), Market Wrap (4:30 PM), Weekly Analysis
- [ ] Add semantic caching for repeated LLM queries

**Files**:
- `backend/brain/agents/__init__.py` *(exists)*
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
- `backend/brain/risk/__init__.py` *(exists)*
- `backend/brain/risk/stop_loss_engine.py` *(exists)*
- `backend/brain/risk/position_sizer.py` *(exists)*
- `backend/brain/risk/capital_protection.py` *(exists)*
- `backend/brain/risk/portfolio_risk.py` *(exists)*
- `backend/brain/risk/indian_costs.py` *(exists)*
- [NEW] `backend/brain/risk/var_calculator.py`
- [NEW] `backend/brain/risk/stress_testing.py`
- [NEW] `backend/brain/risk/sebi_compliance.py`

### Step 3.5 — RAG Knowledge Base

- [ ] Deploy **Qdrant** vector database
- [ ] Implement document chunking (512-token chunks, 50-token overlap)
- [ ] Set up hybrid search: BM25 + semantic vector search (text-embedding-3-small)
- [ ] Add **Cohere rerank** for improved retrieval accuracy
- [ ] Index: company filings, SEBI circulars, RBI policies, brokerage research
- [ ] Implement agentic RAG for multi-hop financial queries

**Files**:
- `backend/brain/rag/__init__.py` *(placeholder exists)*
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

### Step 3.7 — Sector Rotation Engine

- [ ] Track capital flows across IT, Banking, Pharma, Auto, FMCG, Metals, Realty, Energy sectors
- [ ] Detect rotation signals using relative strength (RS), money flow index (MFI), and FII/DII sector-level data
- [ ] Auto-adjust swing portfolio sector weights based on rotation signals
- [ ] Integration with HMM regime for sector-regime conditional weights

**Files**:
- [NEW] `backend/brain/sector/__init__.py`
- [NEW] `backend/brain/sector/sector_rotation.py`
- [NEW] `backend/brain/sector/sector_mapper.py` — stock-to-sector mapping for NIFTY 500

### Step 3.8 — Dividend Intelligence

- [ ] Track ex-dates, yield, payout ratio, dividend growth rate
- [ ] Flag stocks approaching ex-date for swing timing (avoid buying just before ex-date for short-term)
- [ ] Integrate with tax module for post-2020 dividend taxation impact
- [ ] Dividend scoring for fundamental analysis overlay

**Files**:
- [NEW] `backend/brain/dividends/__init__.py`
- [NEW] `backend/brain/dividends/dividend_tracker.py`
- [NEW] `backend/brain/dividends/dividend_scorer.py`

### Step 3.9 — Regulatory Event Calendar

- [ ] Auto-track SEBI board meetings, RBI policy dates, Union Budget, quarterly results season, F&O expiry schedule
- [ ] Pre-event risk parameter tightening
- [ ] Post-event signal boosting
- [ ] Auto-fetch: NSE corporate actions API, RBI announcement calendar

**Files**:
- [NEW] `backend/brain/calendar/__init__.py`
- [NEW] `backend/brain/calendar/regulatory_calendar.py`
- [NEW] `backend/brain/calendar/event_risk_adjuster.py`

### Step 3.10 — SHAP Explainability

- [ ] Generate SHAP values for all XGBoost/ensemble predictions
- [ ] Create waterfall chart visualizations for the dashboard
- [ ] Add LIME for lightweight on-demand explanations
- [ ] Generate natural language explanations from SHAP values + agent reasoning

**Files**:
- `backend/brain/explainability/__init__.py` *(exists)*
- `backend/brain/explainability/shap_explainer.py` *(exists)*
- [NEW] `backend/brain/explainability/lime_explainer.py`
- [NEW] `backend/brain/explainability/nl_explanation.py`

### Phase 3 Milestone
> ✅ Multi-agent LLM research team (2-tier) produces daily research/signals. FinBERT processes Indian financial news. HMM routes predictions to regime-specific models. Sector rotation engine tracks capital flows. Dividend intelligence flags swing timing. Regulatory calendar auto-adjusts risk. Risk management protects capital with ATR stops, Kelly sizing, and VaR monitoring. RAG knowledge base answers financial queries.

---

## Phase 4 — IPO Analysis, Tax Optimization & Signal Validation

> **Goal**: Add IPO analysis, tax optimization, lightweight paper trading signal validation, and communication channels.

### Step 4.1 — IPO Analysis Module

- [ ] Build DRHP/RHP analysis agent (financial health, peer comparison, promoter background)
- [ ] Implement GMP tracking scraper
- [ ] Track subscription data: QIB, NII, Retail multiples
- [ ] Build listing day prediction model
- [ ] Add lock-in expiry tracking (promoter 18 months, anchor 30/90 days) — swing opportunity on unlock

**Files**:
- [NEW] `backend/brain/ipo/__init__.py`
- [NEW] `backend/brain/ipo/ipo_analyzer.py`
- [NEW] `backend/brain/ipo/gmp_tracker.py`
- [NEW] `backend/brain/ipo/listing_predictor.py`
- [NEW] `backend/brain/ipo/lock_in_tracker.py`

### Step 4.2 — Indian Tax Optimization

- [ ] Implement FY 2025–26 capital gains tax rules (STCG 20% < 12 months, LTCG 12.5% ≥ 12 months > ₹1.25L)
- [ ] Build tax-loss harvesting engine (India has no wash-sale rule — significant advantage)
- [ ] Add holding period intelligence to SELL signals (`days_to_ltcg`, `tax_saving_if_held`)
- [ ] Implement year-end (March) portfolio-wide tax optimization
- [ ] Integrate post-2020 dividend taxation (dividends taxed as income)

**Files**:
- `backend/brain/tax/__init__.py` *(exists)*
- [NEW] `backend/brain/tax/capital_gains.py`
- [NEW] `backend/brain/tax/tax_loss_harvesting.py`
- [NEW] `backend/brain/tax/holding_period_optimizer.py`

### Step 4.3 — Paper Trading Signal Validator (Lightweight)

- [ ] Log every swing signal: ticker, direction, entry price, target, stop, confidence
- [ ] Track outcome: hit target / hit stop / timed out
- [ ] Calculate: win rate, avg R-multiple, profit factor, Sharpe
- [ ] Implement promotion criteria: validated over 2–3 months, Sharpe >1.5, win rate >55%, max DD <15%

> **Note:** This is a lightweight signal validation tracker, not a complex shadow order book. The goal is to validate Brain signals before trusting them with real capital.

**Files**:
- `backend/brain/paper_trading/__init__.py` *(exists)*
- [NEW] `backend/brain/paper_trading/signal_validator.py`
- [NEW] `backend/brain/paper_trading/promotion_tracker.py`

### Step 4.4 — Communication Channels

- [ ] Build Telegram bot (`python-telegram-bot`): signal delivery, `/portfolio`, `/signals`, `/risk`, `/market`, `/ipo`
- [ ] Configure Firebase Cloud Messaging with priority tiers (P1 critical → P3 digest)

**Files**:
- `backend/brain/communication/__init__.py` *(exists)*
- [NEW] `backend/brain/communication/telegram_bot.py`
- [NEW] `backend/brain/communication/push_notifications.py`

### Phase 4 Milestone
> ✅ IPO analyzer identifies pre-listing and lock-in expiry swing opportunities. Tax module optimizes after-tax returns. Paper trading validates swing signals for 2–3 months before live deployment. Telegram bot delivers P1 alerts and portfolio commands.

---

## Phase 5 — Advanced ML & Real-Time Streaming

> **Goal**: Deploy foundation models, reinforcement learning for portfolio optimization, Python-native real-time streaming, and global correlation analytics.

### Step 5.1 — Foundation Model Integration

- [ ] Fine-tune **Kronos** (12B K-line records, OHLCV tokenization) on Indian market data
- [ ] Fine-tune **Google TimesFM 2.5** for stock price prediction
- [ ] Evaluate **Chronos** and **Moirai** as zero-shot baselines
- [ ] Implement regime-conditional ensembling: specialist models selected by HMM state + stacked XGBoost meta-learner

**Files**:
- [NEW] `backend/brain/models_ml/foundation/kronos_model.py`
- [NEW] `backend/brain/models_ml/foundation/timesfm_model.py`
- [NEW] `backend/brain/models_ml/ensemble/ensemble_manager.py`

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

### Step 5.3 — Real-Time Python Streaming (Faust/Bytewax)

- [ ] Deploy **Faust** or **Bytewax** for lightweight Python-native streaming (chosen over Flink for cost and simplicity)
- [ ] Implement 4 parallel streaming jobs: Feature Computation, CEP Signal Detection, Anomaly Detection, Feature Freshness Monitor
- [ ] Implement windowed aggregations: 1min, 5min, 15min, 1hr OHLCV
- [ ] Implement chart pattern detection for swing entries: double bottoms, volume breakouts, head-and-shoulders
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
- [ ] Use rolling exponential correlation with decay factor (cost-effective alternative to DCC-GARCH)
- [ ] Build pre-market swing signal engine (produces opening signal by 8:30 AM IST)
- [ ] Implement correlation breakout alerts (>2σ divergence)

**Files**:
- [NEW] `backend/brain/correlation/__init__.py`
- [NEW] `backend/brain/correlation/global_signals.py`
- [NEW] `backend/brain/correlation/correlation_matrix.py`
- [NEW] `backend/brain/correlation/premarket_engine.py`

### Step 5.5 — Alternative Data Integration (High-Signal Only)

- [ ] Google Trends India (`pytrends`) — brand/sector search interest as leading indicators
- [ ] Regulatory filings: SEBI SAST, bulk/block deals, insider trading disclosures
- [ ] Assign signal decay half-lives per data source

**Files**:
- [NEW] `backend/brain/alt_data/__init__.py`
- [NEW] `backend/brain/alt_data/google_trends.py`
- [NEW] `backend/brain/alt_data/regulatory_filings.py`

### Phase 5 Milestone
> ✅ Foundation models provide zero-shot and fine-tuned predictions. RL agent optimizes portfolio allocation. Real-time Python streaming computes features and detects swing patterns in <100ms. Global correlations inform pre-market signals. Alternative data (Google Trends, regulatory filings) provides information edge.

---

## Phase 6 — Production Hardening, Security & Dashboard

> **Goal**: Security, disaster recovery, system health dashboard, monitoring, SEBI compliance, watchlists, MF/ETF analysis, and full dashboard build.

### Step 6.1 — Security & Secrets Management

- [ ] Deploy HashiCorp Vault or Docker Secrets for all credentials
- [ ] Implement AES-256 encryption at rest, TLS 1.3 in transit
- [ ] Configure static IPs for broker API connections (SEBI requirement for algo trading)
- [ ] Implement audit logging with SHA-256 payload hashes (5-year retention)

### Step 6.2 — System Health Dashboard

- [ ] Kafka: consumer lag, topic throughput, DLQ depth
- [ ] Feature Store: feature freshness (staleness >2h = alert), computation time
- [ ] Models: inference latency (P95), prediction drift score, last retrain date
- [ ] APIs: quota usage per provider, rate limit proximity, error rates
- [ ] Infrastructure: CPU/RAM/disk per container, network I/O

**Files**:
- `backend/brain/monitoring/__init__.py` *(exists)*
- [NEW] `backend/brain/monitoring/health_dashboard.py`
- [NEW] Grafana dashboard templates

### Step 6.3 — Disaster Recovery

- [ ] Implement broker API failover (primary → secondary within 5s)
- [ ] Configure Kafka ISR ≥ 2 across AZs (production)
- [ ] Build "guardian process" for emergency position exits
- [ ] Database backup: daily automated PostgreSQL + Redis snapshots

### Step 6.4 — Monitoring & Observability

- [ ] Deploy Prometheus + Grafana for metrics
- [ ] Set up Jaeger/OpenTelemetry for distributed tracing
- [ ] Monitor model drift via Evidently AI (KL-divergence, PSI)
- [ ] Implement retraining triggers on performance degradation

### Step 6.5 — Frontend Dashboard Enhancement

- [ ] Integrate **TradingView Lightweight Charts** for interactive stock charts
- [ ] Build 7+ primary panels: Market Overview, Signal Board, Stock Deep Dive, Portfolio Tracker, Sentiment Dashboard, Agent Activity Log, Report Center
- [ ] Add **Watchlist & Multi-Portfolio Management**: custom watchlists (growth, dividend, sector), multiple portfolio profiles (aggressive swing, defensive, sector-focused), portfolio-level analytics
- [ ] Add **MF/ETF Analysis (Light)**: mutual fund overlap detection with direct equity holdings, basic SIP timing signals, MF vs direct stock alpha comparison
- [ ] Add SHAP waterfall chart visualizations per stock
- [ ] Implement real-time WebSocket updates for signals and prices
- [ ] Build automated PDF report generation and delivery

### Step 6.6 — REST API & WebSocket

- [ ] `GET /brain/picks` — top swing picks with confidence + targets
- [ ] `GET /brain/market-regime` — current HMM state + sector rotation
- [ ] `GET /brain/stock/{symbol}` — deep analysis with SHAP
- [ ] `GET /brain/portfolio` — allocation + performance
- [ ] `GET /brain/risk-dashboard` — risk metrics + VaR
- [ ] `GET /brain/sectors` — sector rotation signals + flow data
- [ ] `GET /brain/dividends` — upcoming ex-dates + impact analysis
- [ ] `GET /brain/ipo` — active IPOs + analysis
- [ ] `GET /brain/calendar` — regulatory events + risk adjustments
- [ ] `GET /brain/watchlists` — custom watchlists
- [ ] `GET /brain/mf-overlap` — MF/ETF overlap with portfolio
- [ ] `WS /brain/live` — real-time swing signal + price updates

### Phase 6 Milestone
> ✅ Production-grade system with security, DR, system health monitoring, compliance, and a stunning dashboard with watchlists, multi-portfolio, and MF/ETF analysis. Ready for live trading with paper-validated strategies.

---

## Verification Plan

### Automated Tests

Each phase will include unit tests and integration tests. Testing approach:

1. **Phase 1**: Test Kafka producer/consumer roundtrip, feature computation accuracy against known values, data quality validation rules
   - Run: `cd backend && python -m pytest tests/brain/test_events.py tests/brain/test_features.py -v`

2. **Phase 2**: Test model inference latency (<20ms), signal confidence scoring calculations, backtesting cost model against manual calculations
   - Run: `cd backend && python -m pytest tests/brain/test_models.py tests/brain/test_signals.py tests/brain/test_backtesting.py -v`

3. **Phase 3**: Test HMM regime transitions, sentiment scoring pipeline, agent response quality, risk calculations (VaR, position sizing), SHAP value generation, sector rotation signals
   - Run: `cd backend && python -m pytest tests/brain/test_regime.py tests/brain/test_sentiment.py tests/brain/test_risk.py tests/brain/test_sectors.py -v`

4. **Phase 4**: Test paper trading signal validation, tax calculations, IPO listing predictions
   - Run: `cd backend && python -m pytest tests/brain/test_paper_trading.py tests/brain/test_tax.py tests/brain/test_ipo.py -v`

### Manual Verification

> [!IMPORTANT]
> Each phase should be manually validated by the developer (you) by running the system locally with Docker Compose and verifying the dashboard shows expected data and signals.

**Phase 1 manual check**: Start all services with `docker compose up`, verify Kafka topics exist via Kafka UI, check feature store serves features via API.

**Phase 2 manual check**: Trigger model training, verify MLflow UI shows experiments, check signal API returns structured JSON with confidence scores and swing-specific fields.

**Phase 3 manual check**: Run agent research workflow for a specific stock (e.g., RELIANCE), verify it produces bull/bear arguments and final synthesis with SHAP explanations. Check sector rotation signals.

**Phase 4 manual check**: Run paper trade validator, check IPO analysis for a recent IPO, verify tax calculations for STCG/LTCG.

---

## Recommended Starting Point

> [!TIP]
> **Start with Phase 1, Step 1.1 (Kafka setup)** — this is the backbone. Everything else depends on having the event-driven infrastructure in place. However, we can parallelize by also starting Step 1.3 (Feature Store) since features can initially be computed in batch without Kafka.

The entire `backend/brain/` directory is the new code home for the Brain system, keeping it cleanly separated from the existing `backend/services/` and `backend/data_extraction/` code.
