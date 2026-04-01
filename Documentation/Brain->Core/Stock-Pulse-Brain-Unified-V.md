# Stock Pulse Brain — Unified Execution Guide

> **Single source of truth** for the Stock Pulse Brain system — covering end-to-end data flow, implementation checklists with file paths synced to the actual codebase, infrastructure requirements, and system architecture. Every decision in this document is oriented toward the platform's primary mission: **maximizing profit through swing trading on the Indian stock market.**

---

## Mission: Swing-Trading-First Intelligence

Stock Pulse Brain is an AI-powered intelligence system built for the **Indian equity market** with a clear focus split:

| Focus Area | Allocation | Holding Period | Primary Models |
|-----------|-----------|---------------|----------------|
| **Swing Trading** | ~80% | 2–30 days | XGBoost/LightGBM (direction), TFT (multi-horizon targets), GARCH (volatility timing) |
| **Intraday** | ~10% | Minutes to hours | LSTM-Attention (pattern detection), real-time streaming signals |
| **Positional/Long-term** | ~10% | 1–6 months | N-BEATS/N-HiTS (extended horizon), fundamental scoring |

Every component — from feature engineering to risk management to signal generation — is optimized for identifying **2–30 day swing entry/exit opportunities** with high confidence and disciplined risk control.

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
| Real-time Streaming | ❌ Not implemented | Phase 5 |
| Foundation Models (Kronos/TimesFM) | ❌ Not implemented | Phase 5 |
| Reinforcement Learning (PPO/FinRL) | ❌ Not implemented | Phase 5 |
| Security & Secrets Management | ❌ Not implemented | Phase 6 |
| Watchlist & Multi-Portfolio | ❌ Not implemented | Phase 6 |
| MF/ETF Analysis | ❌ Not implemented | Phase 6 |

---

## Infrastructure Requirements

### Compute Requirements

| Component | Minimum | Recommended | Notes |
|-----------|---------|-------------|-------|
| **CPU** | 8 cores | 16 cores | XGBoost training is CPU-bound |
| **RAM** | 32 GB | 64 GB | FinBERT + Feature Store + Kafka need ~20 GB combined |
| **GPU** | None (CPU fallback) | 1× NVIDIA T4 (16 GB VRAM) | Required for LSTM-Attention, TFT, FinBERT fine-tuning. Inference can run on CPU via ONNX |
| **Disk (SSD)** | 100 GB | 250 GB | TimescaleDB + PostgreSQL + Redis persistence + MinIO |

### Storage Estimates

| Data Type | Estimate | Retention |
|-----------|----------|-----------|
| OHLCV (NIFTY 500, 10 years, daily) | ~2 GB | Permanent |
| OHLCV (NIFTY 500, 10 years, 1-min intraday) | ~150 GB | Rolling 2 years |
| News corpus (3 years) | ~5 GB | Permanent |
| Feature Store (online Redis) | ~2 GB | Hot cache |
| Feature Store (offline PostgreSQL) | ~10 GB | Permanent |
| MinIO Parquet archive | ~50 GB | Permanent |
| MLflow artifacts + model checkpoints | ~20 GB | Rolling |
| **Total estimated** | **~240 GB** | |

### Docker Resource Allocation

| Service | CPU Limit | Memory Limit | Notes |
|---------|-----------|-------------|-------|
| Kafka (KRaft) | 2 cores | 4 GB | Single broker for dev |
| PostgreSQL + TimescaleDB | 2 cores | 4 GB | Shared instance |
| Redis | 1 core | 2 GB | Online feature store + cache |
| MinIO | 1 core | 1 GB | Object storage |
| MLflow | 1 core | 1 GB | Experiment tracking |
| Backend (Brain) | 4 cores | 8 GB | Model inference + API |
| Airflow | 2 cores | 4 GB | Batch orchestration |
| Frontend | 1 core | 1 GB | React dashboard |
| Prometheus + Grafana | 1 core | 1 GB | Monitoring |

> **Cost note:** This entire stack runs comfortably on a single machine (16-core, 64 GB RAM, 250 GB SSD) or a ~$150/month cloud VM. GPU is only needed during model training (can use spot instances or Colab Pro).

---

## Master Pipeline: The 6-Phase Architecture

Data enters at Phase 1 from external sources, gets progressively refined through each phase, and exits Phase 6 as actionable swing trading picks served via API. Trade outcomes feed back for continuous model improvement.

```
[External Data Sources: NSE, BSE, News, Social, RBI/SEBI]
        |
        v
  PHASE 1: Data Foundation
  Sources -> Kafka (KRaft) -> Preprocessing
  -> TimescaleDB | PostgreSQL | Redis | MinIO
  Feast Feature Store <- Airflow batch DAGs
        |
        v  Clean features via Feast (point-in-time, no leakage)
  PHASE 2: AI/ML + Swing Signal Generation
  MODEL TIERS: GARCH | XGBoost | LSTM-Attn | TFT | N-BEATS
  -> ONNX Runtime (5-20ms) -> Signal Fusion
  -> Meta-Labeling -> Confidence Scoring
  Backtesting: VectorBT Pro (Indian cost model)
        |
        v  Signals + confidence + regime
  PHASE 3: Intelligence + LLM + Risk
  HMM Regime | FinBERT NLP | Governance Scoring
  Sector Rotation | Dividend Intel | Regulatory Calendar
  LangGraph Multi-Agent: 4 Analysts + Bull/Bear + Synthesizer
  RAG Knowledge Base (Qdrant)
  Risk: Kelly + ATR Stops + HRP + Regime Throttling
  SHAP/LIME Explainability
        |
        v  Risk-bounded decisions + explanations
  PHASE 4: IPO, Tax & Validation
  IPO Analysis | Tax Optimization (STCG/LTCG)
  Paper Trading Signal Validator
  Telegram Bot + Push Notifications
        |
        v  Validated signals + tax-aware decisions
  PHASE 5: Advanced ML & Real-Time Streaming
  Foundation Models: Kronos + TimesFM -> Regime Ensemble
  RL Portfolio: FinRL PPO -> Black-Litterman
  Global Correlations -> Pre-market signal by 8:30 AM
  Python Streaming (Faust/Bytewax) -> <100ms features
        |
        v  Final portfolio + explanations
  PHASE 6: Production, Security & Dashboard
  Security: Vault + TLS + Audit Logging
  System Health Dashboard + Grafana + Prometheus
  7+ Panel Dashboard | TradingView | Watchlists | Multi-Portfolio
  MF/ETF Overlap | REST API + WebSocket -> Stock Pulse Website
  Agentic Reports: Morning Brief, Market Wrap, Weekly
        |
        v  Trade outcomes
  FEEDBACK LOOP -> Walk-forward retrain Phase 2-3 models
```

---

## Phase 1: Data Foundation & Event Infrastructure

### Data Flow

**IN:** Raw data from 5 source categories — NSE/BSE feeds (broker APIs), historical OHLCV (10+ years), news (ET, Moneycontrol, LiveMint), social media (Twitter, Reddit, Telegram), government (RBI, SEBI, budget/GST)

**INSIDE:**

1. All sources publish to **Kafka (KRaft mode)** topics: `raw-ticks`, `normalized-ohlcv`, `signals`, `orders`, `alerts`, `features`
2. **Pydantic Schema Validation** enforces data governance (via `backend/brain/schemas/market_data.py`)
3. **Dead Letter Queue** catches failed messages
4. **Preprocessing pipeline** cleans, normalizes splits/bonuses, validates OHLC integrity, checks circuit limits, timestamps to IST
5. Routes to: **TimescaleDB** (OHLCV series) | **PostgreSQL** (trades, metadata) | **Redis** (1–5s TTL cache) | **MinIO** (Parquet archive)
6. **Feast Feature Store** (Redis online + PostgreSQL offline) computes swing-critical features: RSI, MACD, BB, VWAP, ATR, OBV + India-specific: delivery %, FII/DII flows, promoter %
7. **Airflow DAGs** run post-market: `dag_daily_bhavcopy`, `dag_fii_dii`, `dag_fundamentals`, `dag_corporate_actions`, `dag_macro_data`

**OUT:** Point-in-time correct features with no data leakage, versioned and ready for swing-trading AI models

### Internal Data Flow Diagram

```
NSE/BSE    Brokers    News    Social    SEBI/RBI    Bhavcopy
  |          |         |        |          |           |
  v          v         v        v          v           v
       Kafka (KRaft, no ZooKeeper)
       Topics: raw-ticks | normalized-ohlcv | signals | alerts
       Pydantic Schema Validation + Dead Letter Queue
                    |
                    v
       Preprocessing Pipeline
       OHLC integrity | volume check | circuit limits | IST normalize
                    |
       +------------+------------+-----------+
       v            v            v           v
  TimescaleDB   PostgreSQL    Redis      MinIO
  (OHLCV)      (trades)    (1-5s TTL)  (Parquet)
       |            |            |
       +------------+------------+
                    v
       Feast Feature Store (online: Redis, offline: PostgreSQL)
       Swing: RSI(14), MACD, BB(20,2), ATR(14), VWAP
       Fund: revenue z-scores, P/E, ROE, dividend yield
       India: delivery%, FII/DII, promoter%, sector flows
                    |
                    v
       Airflow Batch DAGs (post-market)
       bhavcopy | fii_dii | fundamentals | corporate_actions | macro
```

### Implementation Checklist

**1.1 — Kafka Event Bus:**

- [ ] Add Kafka (KRaft) to `docker-compose.yml`
- [ ] `backend/brain/events/kafka_manager.py` *(exists)*
- [ ] `backend/brain/events/topics.py` *(exists)*
- [ ] `backend/brain/schemas/market_data.py` *(exists — Pydantic, not Protobuf)*
- [ ] Implement DLQ + health checks

**1.2 — Enhanced Ingestion:**

- [ ] Upgrade extractors to publish to Kafka
- [ ] Enhance NSE Bhavcopy for CM-UDiFF format
- [ ] `backend/brain/ingestion/normalizer.py` *(exists)* + `data_quality.py` *(exists)*
- [ ] `backend/brain/ingestion/kafka_bridge.py` *(exists)*
- [ ] Circuit breaker detection + exponential backoff reconnection

**1.3 — Feature Store (Feast + Redis):**

- [ ] Configure Feast + `backend/brain/features/feature_store.py` *(exists)*
- [ ] `backend/brain/features/technical_features.py` *(exists)* + `fundamental_features.py` *(exists)*
- [ ] `backend/brain/features/macro_features.py` *(exists)* + `cross_sectional_features.py` *(exists)*
- [ ] `backend/brain/features/feature_registry.py` *(exists)* + `feature_pipeline.py` *(exists)*
- [ ] `backend/brain/features/timeseries_fetchers.py` *(exists)*
- [ ] Point-in-time retrieval + versioning

**1.4 — Storage Enhancement:**

- [ ] MinIO for Parquet archival — `backend/brain/storage/minio_client.py` *(exists)* + `parquet_writer.py` *(exists)*
- [ ] Redis TTL strategy (1–5s during market hours, relaxed post-market)
- [ ] Airflow DAGs in `backend/brain/batch/airflow_dags/`

---

## Phase 2: AI/ML Model Training & Swing Signal Generation

### Data Flow

**IN:** Features from Feast + market regime context

**INSIDE:**

1. **MLflow** tracks experiments; **Optuna** for Bayesian hyperparameter optimization
2. **Walk-forward validation** (never k-fold for financial data); **CPCV** for tuning
3. **Feature pipeline:** log/scaling → correlation filtering → Boruta → LASSO → PCA
4. **Model tiers (swing-trading optimized):**
    - Tier 1 (Volatility): GARCH(1,1) + EGARCH → optimal swing entry timing via volatility regime
    - Tier 2 (Workhorses): XGBoost / LightGBM / CatBoost → **primary swing direction (2–30 day horizon)**
    - Tier 3 (Intraday): LSTM with attention → intraday pattern detection (10% allocation)
    - Primary: TFT → **multi-horizon swing targets (5d/10d/20d quantile forecasts)**
    - Extended: N-BEATS / N-HiTS → positional horizon (1–6 months, 10% allocation)
5. All models exported to **ONNX** (5–20ms inference)
6. **Signal fusion (swing-weighted):** Technical(35%) + Sentiment(20%) + Fundamental(20%) + Volume(15%) + Macro(10%)
7. **Meta-labeling:** direction model + confidence model. <40% suppressed, 40–60% watchlist, 60–80% actionable, >80% high-conviction
8. **Swing-specific signal fields:** `expected_hold_days`, `risk_reward_ratio`, `swing_phase` (breakout/pullback/trend)
9. **VectorBT Pro** backtesting with Indian costs: STT, exchange, GST, stamp duty, SEBI fees, DP charges

**OUT:** Structured swing signal JSON: `{ticker, direction, confidence, target, stop_loss, expected_hold_days, risk_reward_ratio, swing_phase, contributing_factors, explanation}`

### Internal Data Flow Diagram

```
Feast Feature Store
       |
       v
  MLflow + Optuna + Walk-Forward Validation + CPCV
  Feature Pipeline: log/scale -> correlation -> Boruta -> LASSO -> PCA
       |
       v
  MODEL TIERS (Swing-Trading Optimized):
  T1: GARCH+EGARCH -> Volatility regime (swing entry timing)
  T2: XGBoost/LGBM/CatBoost -> Swing direction (2-30 day) [PRIMARY]
  T3: LSTM-Attention -> Intraday patterns (10%)
  Primary: TFT -> Multi-horizon swing targets (5d/10d/20d)
  Extended: N-BEATS/N-HiTS -> Positional (1-6 months, 10%)
       |
       v  ONNX Runtime (5-20ms)
  SWING SIGNAL GENERATION:
  Fusion: Tech(35%) + Sent(20%) + Fund(20%) + Vol(15%) + Macro(10%)
  Thresholds: <40% kill | 40-60% watch | 60-80% act | >80% conviction
  Meta-labeling: direction + confidence models
  Swing fields: expected_hold_days, risk_reward, swing_phase
       |
       v
  {ticker, direction, confidence, target, stop_loss, hold_days, swing_phase}
  Validated via VectorBT Pro (Indian costs: STT, GST, stamp, SEBI, DP)
  QuantStats tearsheets: Sharpe, Sortino, Calmar, monthly heatmaps
```

### Implementation Checklist

**2.1 — ML Infrastructure:**

- [ ] MLflow + `backend/brain/models_ml/base_model.py` *(exists)*
- [ ] `backend/brain/models_ml/validation.py` *(exists — walk-forward + CPCV)*
- [ ] Optuna Bayesian optimization with pruning

**2.2 — Core Models:**

- [ ] `backend/brain/models_ml/statistical/garch_model.py` *(exists)*
- [ ] `backend/brain/models_ml/statistical/arima_model.py` *(exists)*
- [ ] `backend/brain/models_ml/gradient_boosting/xgboost_model.py` *(exists)*
- [ ] `backend/brain/models_ml/gradient_boosting/lightgbm_model.py` *(exists)*
- [ ] `backend/brain/models_ml/gradient_boosting/ensemble.py` *(exists)*
- [ ] `backend/brain/models_ml/deep_learning/` — LSTM-Attention, TFT, N-BEATS *(placeholders exist)*
- [ ] ONNX export + inference engine

**2.3 — Signal Engine:**

- [ ] `backend/brain/signals/signal_generator.py` *(exists)*
- [ ] `backend/brain/signals/signal_fusion.py` *(exists)*
- [ ] `backend/brain/signals/confidence_scorer.py` *(exists)*
- [ ] `backend/brain/models/signals.py` *(exists — Pydantic signal schemas)*
- [ ] Add swing-specific fields: `expected_hold_days`, `risk_reward_ratio`, `swing_phase`

**2.4 — Backtesting:**

- [ ] `backend/brain/backtesting/` *(placeholder exists)*
- [ ] VectorBT Pro integration with Indian cost model
- [ ] `backend/brain/risk/indian_costs.py` *(exists — STT, GST, stamp duty, SEBI, DP)*
- [ ] QuantStats tearsheet generation

---

## Phase 3: Intelligence Layer, LLM Agents & Risk Management

### Data Flow

**IN:** Signals + features + raw text from Phase 2

**INSIDE:**

1. **HMM Regime Detection:** 3-state Gaussian HMM (bull/bear/sideways) on returns, VIX, FII flows, INR/USD. Complementary: K-Means/GMM, CUSUM change-point. Routes to regime-specialist swing models.
2. **FinBERT Sentiment:** Indian variant `kdave/FineTuned_Finbert`. Pipeline: language detect → Hindi→English (IndicTrans2) → NER → sentiment → event extraction. Ensemble: 0.5×FinBERT + 0.2×VADER + 0.3×LLM. Sources: ET, Moneycontrol, LiveMint, Twitter, Reddit.
3. **LangGraph Multi-Agent System:**
    - 2-tier LLM routing: Tier 1 (Claude/GPT-5 for deep analysis), Tier 2 (GPT-4.1-mini for extraction/lightweight)
    - 4 analyst agents: Fundamental, Technical, Sentiment, Macro
    - Dialectical: Bull Researcher ↔ Bear Researcher → Research Synthesizer
    - Trader Agent → Risk Agent (veto power)
    - Reports: Morning Brief 8:30 AM, Market Wrap 4:30 PM, Weekly Analysis
4. **RAG Knowledge Base:** Qdrant vector DB with hybrid search (BM25 + semantic). Index: company filings, SEBI circulars, RBI policies, brokerage research. 512-token chunks with 50-token overlap. Cohere rerank for accuracy.
5. **Sector Rotation Engine:** Track capital flows across IT, Banking, Pharma, Auto, FMCG, Metals, Realty, Energy. Detect rotation signals using relative strength (RS), money flow index (MFI), and FII/DII sector-level data. Auto-adjust swing portfolio sector weights.
6. **Dividend Intelligence:** Track ex-dates, yield, payout ratio, dividend growth rate. Flag stocks approaching ex-date for swing timing. Integrate with tax module for post-2020 dividend taxation impact.
7. **Regulatory Event Calendar:** Auto-track SEBI board meetings, RBI policy dates, Union Budget, quarterly results season, F&O expiry schedule. Pre-event risk parameter tightening. Post-event signal boosting.
8. **Decision Engine:** Hunter-Guard → Hard rules (VIX cap, F&O ban, SEBI margin) → Optuna-tuned ensemble weighting → Meta-Labeling Filter (confidence <40% = killed)
9. **Risk Management:** ATR stops (Entry - ATR14×Mult) | Kelly sizing (Half/Quarter) | Capital escalation (10%DD→halve, 15%→halt, 20%→kill) | VaR/CVaR (Historical+Parametric+Monte Carlo) | Stress tests (2008, 2020, 2016) | SEBI margin checks
10. **HRP Portfolio:** Cluster → quasi-diag → recursive bipartition → inverse-variance. Rebalance weekly or on regime change.
11. **Regime Throttling:** Crisis → suppress longs, tighten stops 50%, cut to 20%, increase cash
12. **Governance Scoring:** 0–100 (pledging 25%, RPT 20%, auditor 15%, board 15%, regulatory 15%, disclosure 10%). Auto-exclude <40.
13. **SHAP/LIME:** Per-trade waterfall charts + natural language explanations

**OUT:** Risk-bounded Buy/Sell/Hold decisions with position sizes, stop levels, confidence scores, sector allocation, expected hold period, and full NL explanations

### Internal Data Flow Diagram

```
Signals + Features + Raw Text
       |
       +---> HMM Regime (3-state: bull/bear/sideways)
       |     + K-Means/GMM, CUSUM change-point
       |     -> Routes to specialist swing models per regime
       |
       +---> FinBERT NLP (Indian variant)
       |     Lang detect -> Hindi->En -> NER -> Sentiment
       |     Ensemble: 0.5*FinBERT + 0.2*VADER + 0.3*LLM
       |
       +---> LangGraph Multi-Agent System (2-tier LLM)
       |     [Fund] [Tech] [Sent] [Macro] analysts
       |     Bull Researcher <-> Bear Researcher -> Synthesizer
       |     Trader Agent -> Risk Agent (veto)
       |     Tier 1: Claude/GPT-5 | Tier 2: GPT-4.1-mini
       |
       +---> RAG Knowledge Base (Qdrant)
       |     Hybrid search: BM25 + semantic + Cohere rerank
       |
       +---> Sector Rotation Engine
       |     IT | Banking | Pharma | Auto | FMCG | Metals
       |     RS + MFI + FII/DII sector flows -> rotation signals
       |
       +---> Dividend Intelligence
       |     Ex-dates | Yield | Growth rate | Tax impact
       |
       +---> Regulatory Event Calendar
       |     SEBI | RBI | Budget | Results | F&O expiry
       |     -> Pre-event risk tightening
       |
       +---> Governance Scoring (auto-exclude <40)
       |
       v
  Hunter-Guard -> Hard Rules (VIX, F&O ban, SEBI)
  -> Optuna Ensemble Weighting -> Meta-Label Filter
       |
       v
  Risk Engine: Kelly + ATR + HRP + Regime Throttle
  Capital Escalation: 10%->halve, 15%->halt, 20%->kill
  VaR/CVaR + Stress Tests (2008, 2020, 2016)
       |
       v
  SHAP/LIME -> NL Explanation per swing trade
```

### Implementation Checklist

**3.1 — HMM Regime:**

- [ ] `backend/brain/regime/hmm_detector.py` *(exists)*
- [ ] `backend/brain/regime/regime_store.py` *(exists)*
- [ ] Add `changepoint_detector.py` + `regime_router.py`

**3.2 — FinBERT Sentiment:**

- [ ] `backend/brain/sentiment/finbert_analyzer.py` *(exists)*
- [ ] `backend/brain/sentiment/entity_extractor.py` *(exists)*
- [ ] `backend/brain/sentiment/news_scraper.py` *(exists)*
- [ ] `backend/brain/sentiment/sentiment_aggregator.py` *(exists)*
- [ ] Add `earnings_analyzer.py`

**3.3 — LLM Multi-Agent (2-Tier):**

- [ ] `backend/brain/agents/orchestrator.py` (LangGraph)
- [ ] `fundamental_analyst.py` + `technical_analyst.py` + `sentiment_analyst.py` + `macro_analyst.py`
- [ ] `bull_researcher.py` + `bear_researcher.py` + `research_synthesizer.py`
- [ ] `trader_agent.py` + `risk_agent.py` + `report_generator.py`
- [ ] `llm_router.py` — 2-tier routing (Tier 1: Claude/GPT-5, Tier 2: GPT-4.1-mini)

**3.4 — RAG Knowledge Base:**

- [ ] `backend/brain/rag/` *(placeholder exists)*
- [ ] Deploy Qdrant vector database
- [ ] `vector_store.py` + `document_processor.py` + `retriever.py` + `reranker.py`
- [ ] Index: company filings, SEBI circulars, RBI policies, brokerage research

**3.5 — Sector Rotation:**

- [ ] `backend/brain/sector/sector_rotation.py` — RS, MFI, sector flow analysis
- [ ] `backend/brain/sector/sector_mapper.py` — stock-to-sector mapping for NIFTY 500
- [ ] Integration with HMM regime for sector-regime conditional weights

**3.6 — Dividend Intelligence:**

- [ ] `backend/brain/dividends/dividend_tracker.py` — ex-date tracking, yield calculation
- [ ] `backend/brain/dividends/dividend_scorer.py` — payout ratio, growth rate, tax impact
- [ ] Integration with swing signal timing (avoid buying just before ex-date for short-term)

**3.7 — Regulatory Event Calendar:**

- [ ] `backend/brain/calendar/regulatory_calendar.py` — SEBI, RBI, Budget, results season
- [ ] `backend/brain/calendar/event_risk_adjuster.py` — pre-event risk tightening
- [ ] Auto-fetch: NSE corporate actions API, RBI announcement calendar

**3.8 — Risk Engine:**

- [ ] `backend/brain/risk/stop_loss_engine.py` *(exists)*
- [ ] `backend/brain/risk/position_sizer.py` *(exists)*
- [ ] `backend/brain/risk/capital_protection.py` *(exists)*
- [ ] `backend/brain/risk/portfolio_risk.py` *(exists)*
- [ ] Add `var_calculator.py` + `stress_testing.py` + `sebi_compliance.py`

**3.9 — Governance:**

- [ ] `backend/brain/governance/governance_scorer.py` + `promoter_tracker.py` + `red_flag_detector.py`

**3.10 — SHAP Explainability:**

- [ ] `backend/brain/explainability/shap_explainer.py` *(exists)*
- [ ] Add `lime_explainer.py` + `nl_explanation.py`

---

## Phase 4: IPO Analysis, Tax Optimization & Signal Validation

### Data Flow

**IN:** Risk-bounded swing decisions from Phase 3 + IPO/tax data

**INSIDE:**

1. **IPO Analysis:**
    - DRHP/RHP document analysis agent (financial health, peer comparison, promoter background)
    - GMP (Grey Market Premium) tracking scraper
    - Subscription data tracking: QIB, NII, Retail multiples
    - Listing day prediction model
    - Lock-in expiry tracking (promoter 18 months, anchor 30/90 days) — swing opportunity on unlock
2. **Indian Tax Optimization:**
    - FY 2025–26 capital gains rules: STCG 20% (< 12 months), LTCG 12.5% (≥ 12 months, > ₹1.25L)
    - Tax-loss harvesting engine (India has no wash-sale rule — significant advantage)
    - Holding period intelligence: `days_to_ltcg`, `tax_saving_if_held` added to SELL signals
    - Year-end (March) portfolio-wide tax optimization
    - Post-2020 dividend taxation: dividends taxed as income — integrated with dividend intelligence
3. **Paper Trading Signal Validator (Lightweight):**
    - Log every swing signal: ticker, direction, entry price, target, stop, confidence
    - Track outcome: hit target / hit stop / timed out
    - Calculate: win rate, avg R-multiple, profit factor, Sharpe
    - Promotion criteria: validated over 2–3 months, Sharpe >1.5, win rate >55%, max DD <15%
    - No complex shadow order book — this is purely signal validation
4. **Communication Channels:**
    - Telegram bot (`python-telegram-bot`): `/portfolio`, `/signals`, `/risk`, `/market`, `/ipo`
    - Firebase push notifications with priority tiers: P1 (critical swing alerts) → P3 (daily digest)

**OUT:** Tax-optimized swing decisions + IPO opportunities + validated signal track record + alert delivery

### Implementation Checklist

**4.1 — IPO Analysis:**

- [ ] `backend/brain/ipo/ipo_analyzer.py` — DRHP/RHP analysis agent
- [ ] `backend/brain/ipo/gmp_tracker.py` — grey market premium scraping
- [ ] `backend/brain/ipo/listing_predictor.py` — listing day model
- [ ] `backend/brain/ipo/lock_in_tracker.py` — lock-in expiry for swing opportunities

**4.2 — Tax Optimization:**

- [ ] `backend/brain/tax/` *(placeholder exists)*
- [ ] `capital_gains.py` — STCG/LTCG calculation engine
- [ ] `tax_loss_harvesting.py` — harvest optimizer (no wash-sale rule in India)
- [ ] `holding_period_optimizer.py` — `days_to_ltcg`, `tax_saving_if_held`

**4.3 — Paper Trading Validator:**

- [ ] `backend/brain/paper_trading/` *(placeholder exists)*
- [ ] `signal_validator.py` — log signal, track outcome, calculate metrics
- [ ] `promotion_tracker.py` — track readiness for live deployment

**4.4 — Communication:**

- [ ] `backend/brain/communication/` *(placeholder exists)*
- [ ] `telegram_bot.py` — signal delivery, portfolio commands
- [ ] `push_notifications.py` — Firebase with priority tiers

---

## Phase 5: Advanced ML & Real-Time Streaming

### Data Flow

**IN:** Historical data + current features + regime state

**INSIDE:**

1. **Foundation Models:** Kronos (fine-tuned on Indian OHLCV) + TimesFM 2.5 + Chronos/Moirai zero-shot baselines. Regime-conditional ensembling via HMM + XGBoost meta-learner.
2. **RL Portfolio:** FinRL + PPO agent in Indian market environment (NIFTY 50, Indian costs, margin rules). Target: Sharpe >2.0. Black-Litterman with AI-generated views for swing portfolio allocation.
3. **Global Correlations:** Overnight processing of S&P 500, NASDAQ, SGX/GIFT NIFTY, Asian markets, crude oil, DXY, US 10Y. Rolling exponential correlation with decay factor. Pre-market swing signal by 8:30 AM IST. Breakout alerts at >2σ divergence.
4. **Real-Time Streaming (Python-Native):** Faust or Bytewax for lightweight streaming. 4 streaming jobs: Feature Computation, CEP Signal Detection, Anomaly Detection, Feature Freshness Monitor. Windowed aggregations: 1min, 5min, 15min, 1hr OHLCV. Chart pattern detection for swing entries: double bottoms, volume breakouts, head-and-shoulders. Target: <100ms end-to-end.
5. **Alternative Data (High-Signal Only):** Google Trends India — brand/sector search interest as leading indicators. SEBI SAST filings, bulk/block deals, insider disclosures. Signal decay half-lives per source.

**OUT:** Enhanced swing predictions + optimized portfolio weights + pre-market signals + real-time pattern alerts

### Implementation Checklist

**5.1 — Foundation Models:**

- [ ] `backend/brain/models_ml/foundation/kronos_model.py`
- [ ] `backend/brain/models_ml/foundation/timesfm_model.py`
- [ ] `backend/brain/models_ml/ensemble/ensemble_manager.py`

**5.2 — RL Portfolio:**

- [ ] `backend/brain/portfolio/rl_optimizer.py` + `finrl_environment.py`
- [ ] `backend/brain/portfolio/black_litterman.py` + `hrp_optimizer.py`

**5.3 — Global Correlations:**

- [ ] `backend/brain/correlation/global_signals.py` + `correlation_matrix.py`
- [ ] `backend/brain/correlation/premarket_engine.py` — pre-market swing signal by 8:30 AM

**5.4 — Real-Time Streaming:**

- [ ] `backend/brain/streaming/feature_computation.py` — windowed aggregation
- [ ] `backend/brain/streaming/cep_signal_detection.py` — complex event processing
- [ ] `backend/brain/streaming/anomaly_detector.py` — price/volume anomalies
- [ ] `backend/brain/streaming/freshness_monitor.py` — feature staleness alerts

**5.5 — Alternative Data:**

- [ ] `backend/brain/alt_data/google_trends.py` — search interest signals
- [ ] `backend/brain/alt_data/regulatory_filings.py` — SAST, bulk/block deals, insider

---

## Phase 6: Production Hardening, Security & Dashboard

### Data Flow

**IN:** Risk-bounded orders + explanations from Phase 3/4/5

**INSIDE:**

1. **Security & Secrets Management:**
    - HashiCorp Vault or Docker Secrets for all credentials
    - AES-256 encryption at rest, TLS 1.3 in transit
    - Audit logging with SHA-256 payload hashes (5-year retention)
    - Static IPs for broker API connections (SEBI requirement for algo trading)
2. **System Health Dashboard:**
    - Kafka: consumer lag, topic throughput, DLQ depth
    - Feature Store: feature freshness (staleness >2h = alert), computation time
    - Models: inference latency (P95), prediction drift score, last retrain date
    - APIs: quota usage per provider, rate limit proximity, error rates
    - Infrastructure: CPU/RAM/disk per container, network I/O
3. **Continuous Learning:** Walk-forward retraining, concept drift detection (Evidently AI — KL-divergence, PSI), Optuna weight recalibration, triple-barrier labeling, online learning for sentiment + regime.
4. **Feedback Loop:** Every swing trade logged (entry, signals, confidence, outcome, P&L attribution). Monthly performance reports.
5. **Monitoring & Observability:** Prometheus + Grafana metrics, Jaeger/OpenTelemetry tracing, retraining triggers on performance degradation.
6. **Agentic Reports:** Analyst → Writer → Editor agents via RAG. Morning Brief 8:30 AM, Market Wrap 4:30 PM, Weekly Analysis.
7. **Dashboard (7+ panels):**
    - Market Overview — NIFTY/SENSEX, sector heatmap, India VIX, FII/DII
    - Swing Signal Board — active signals with confidence, targets, stops, hold period
    - Stock Deep Dive — per-stock analysis with TradingView charts + SHAP waterfall
    - Portfolio Tracker — holdings, P&L, sector allocation, performance vs NIFTY
    - Sentiment Dashboard — aggregate market sentiment, per-stock NLP scores
    - Agent Activity Log — LLM agent reasoning chain, research outputs
    - Report Center — generated reports, PDF download
    - **Watchlist & Multi-Portfolio Management** — custom watchlists (growth, dividend, sector), multiple portfolio profiles (aggressive swing, defensive, sector-focused), portfolio-level analytics
    - **MF/ETF Analysis (Light)** — mutual fund overlap detection with direct equity holdings, basic SIP timing signals, MF vs direct stock alpha comparison
8. **REST API + WebSocket:**
    - `GET /brain/picks` — top swing picks with confidence + targets
    - `GET /brain/market-regime` — current HMM state + sector rotation
    - `GET /brain/stock/{symbol}` — deep analysis with SHAP
    - `GET /brain/portfolio` — allocation + performance
    - `GET /brain/risk-dashboard` — risk metrics + VaR
    - `GET /brain/sectors` — sector rotation signals + flow data
    - `GET /brain/dividends` — upcoming ex-dates + impact analysis
    - `GET /brain/ipo` — active IPOs + analysis
    - `GET /brain/calendar` — regulatory events + risk adjustments
    - `GET /brain/watchlists` — custom watchlists
    - `GET /brain/mf-overlap` — MF/ETF overlap with portfolio
    - `WS /brain/live` — real-time swing signal + price updates
9. **Disaster Recovery:**
    - Broker API failover (primary → secondary within 5s)
    - Kafka ISR ≥ 2 across AZs (production)
    - Guardian process for emergency position exits
    - Database backup: daily automated PostgreSQL + Redis snapshots

**OUT:** Fully operational swing trading platform serving via REST API + WebSocket to Stock Pulse website

### Implementation Checklist

**6.1 — Security:**

- [ ] Secrets management (Vault / Docker Secrets)
- [ ] TLS configuration + encryption at rest
- [ ] Audit logging

**6.2 — System Health Dashboard:**

- [ ] `backend/brain/monitoring/` *(placeholder exists)*
- [ ] `health_dashboard.py` — Kafka lag, feature freshness, model staleness
- [ ] Grafana dashboard templates for system health

**6.3 — Monitoring & Observability:**

- [ ] Prometheus + Grafana setup
- [ ] Jaeger/OpenTelemetry tracing
- [ ] Evidently AI model drift (KL-divergence, PSI)
- [ ] Retraining triggers on degradation

**6.4 — Dashboard:**

- [ ] TradingView Lightweight Charts integration
- [ ] 7+ panels including Watchlist & Multi-Portfolio + MF/ETF
- [ ] SHAP waterfall visualizations
- [ ] Real-time WebSocket updates
- [ ] Automated PDF report generation

**6.5 — Disaster Recovery:**

- [ ] Broker API failover
- [ ] Database backup automation
- [ ] Guardian process for emergency exits

---

## System Reaction Matrix

How each phase reacts to key market events:

| Event | Phase 1 (Data) | Phase 2 (AI/ML) | Phase 3 (Intel) | Phase 4 (IPO/Tax) | Phase 5 (Adv ML) | Phase 6 (Prod) |
| --- | --- | --- | --- | --- | --- | --- |
| **Market crash** | Ingests data | Models predict drop | HMM→Crisis, blocks buys, cuts to 20% | Paper trade validates | Correlation alerts fire | Executes sells, reports |
| **Earnings beat** | Ingests news+data | Score updates, signal fires | NLP bullish, Hunter entry, Kelly sizes | Tax: check hold period | No change | Buys, logs, reports |
| **FII selling** | Ingests FII data | Macro signal negative | Guard exit, tightens stops, sector rotation | No change | Global correlation updates | Exits weak, reports |
| **F&O ban** | Ingests ban list | Flags metadata | Hard rule blocks trade | No change | No change | No execution |
| **Model drift** | No change | Drift detected | Meta-label filters more | Win rate tracked | Ensemble reweights | Triggers retraining |
| **RBI rate hike** | Ingests announcement | Macro updates | Sector rotation (Banking↔IT), calendar adjusts | Tax impact analysis | Correlation shift | Reports updated |
| **IPO listing** | Ingests listing data | No change | Governance score check | IPO analyzer activates, lock-in tracked | No change | Dashboard updated |
| **Dividend ex-date** | Ingests ex-date | Fundamental feature updates | Dividend intel flags swing timing | Tax: dividend income calc | No change | Portfolio adjusted |
| **Sector rotation** | Ingests sector flows | Sector features update | Rotation engine triggers reweight | No change | Global flows confirm | Portfolio rebalanced |
| **Tax year-end (March)** | No change | No change | No change | Tax-loss harvesting activates | No change | Reports, sell suggestions |

---

## Implementation → Phase Mapping

| Phase | Core Deliverable |
| --- | --- |
| Phase 1: Data Foundation | Kafka + DBs + Feast + Airflow running |
| Phase 2: AI/ML + Signals | Models trained, swing signals with confidence |
| Phase 3: Intelligence + LLM + Risk | HMM, NLP, agents, risk, governance, sectors, dividends, calendar, RAG, XAI |
| Phase 4: IPO + Tax + Validation | IPO analysis, tax optimization, paper trade validation, Telegram bot |
| Phase 5: Advanced ML + Streaming | Foundation models, RL, global signals, real-time streaming |
| Phase 6: Production + Security | Dashboard, monitoring, security, DR, watchlists, MF/ETF, API |

---

## Feedback Loop: How the System Self-Improves

```
Phase 6 (Execution) logs every swing trade:
  entry reason | signals | confidence | hold_days | outcome | P&L
       |
       v
  Walk-Forward Validation
  Train on 3 years -> Test on next quarter -> Roll forward
       |
       v
  Concept Drift Detection (Evidently AI)
  Model accuracy drops below threshold -> Trigger retrain
       |
       v
  Optuna Weight Recalibration
  Down-weight decaying models, up-weight improving ones
       |
       v
  Triple-Barrier Labeling (swing-optimized)
  Profit target | Stop-loss | Time limit (adaptive to volatility + swing phase)
       |
       v
  Updated models deployed -> Phase 2-3 swing predictions improve
  Cycle repeats continuously
```

---

## Architecture Diagrams

Architecture diagrams are located in `Documentation/Brain->Core/Architecture Design/`:

- **Image 1** — Master Pipeline: 6-Phase Architecture Overview
- **Image 2** — Phase 1: Data Foundation Internal Wiring
- **Image 3** — Phase 2: AI/ML Model Tiers + Signal Generation
- **Image 4** — Phase 3: Intelligence + LLM Agents + Risk
- **Image 5** — System Reaction Matrix

> **Note:** Diagrams should be updated to reflect: removal of Options/Derivatives from Phase 3, removal of Tier 3 local LLM, addition of Sector Rotation + Dividend Intelligence + Regulatory Calendar + RAG, and the inclusion of Phase 4 (IPO/Tax/Validation) and Phase 5 (Streaming).