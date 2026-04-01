# Stock Pulse Brain — Flow of Execution Across Phases (Unified)

> **Unified document** combining end-to-end data flow (IN/INSIDE/OUT per phase), implementation checklists (A–E with file paths), and system architecture diagrams. This is the single source of truth for how the Brain is built and how data moves through it.
> 

---

## Master Pipeline: The 6-Layer Architecture

Data enters at Phase 1 from external sources, gets progressively refined through each phase, and exits Phase 6 as actionable stock picks served via API. Trade outcomes feed back for continuous model improvement.

```
[External Data Sources: NSE, BSE, News, Social, RBI/SEBI]
        |
        v
  PHASE 1 / Section A: Data Foundation
  Sources -> Kafka (KRaft) -> Preprocessing
  -> TimescaleDB | PostgreSQL | Redis | MinIO
  Feast Feature Store <- Airflow batch DAGs
        |
        v  Clean features via Feast (point-in-time, no leakage)
  PHASE 2-3 / Section B: AI/ML + Signal Generation
  MODEL TIERS: GARCH | XGBoost | LSTM-Attn | TFT | N-BEATS
  -> ONNX Runtime (5-20ms) -> Signal Fusion
  -> Meta-Labeling -> Confidence Scoring
  Backtesting: VectorBT Pro (Indian cost model)
        |
        v  Signals + confidence + regime
  PHASE 3-4-5 / Section C: Intelligence + LLM + Risk
  HMM Regime | FinBERT NLP | Governance Scoring
  LangGraph Multi-Agent: 4 Analysts + Bull/Bear + Synthesizer
  Hunter-Guard -> PSO Ensemble -> Meta-Label Filter
  Risk: Kelly + ATR Stops + HRP + Regime Throttling
  SHAP/LIME Explainability
        |
        v  Risk-bounded decisions + explanations
  PHASE 3+ / Section D: Advanced ML
  Foundation Models: Kronos + TimesFM -> Regime Ensemble
  RL Portfolio: FinRL PPO -> Black-Litterman
  Global Correlations -> Pre-market signal by 8:30 AM
  Alt Data: Google Trends, UPI, SAST filings
        |
        v  Final portfolio + explanations
  PHASE 6 / Section E: Production & Dashboard
  Grafana+Prometheus | 7-panel Dashboard | TradingView
  REST API + WebSocket -> Stock Pulse Website
  Agentic Reports: Morning Brief, Market Wrap, Weekly
        |
        v  Trade outcomes
  FEEDBACK LOOP -> Walk-forward retrain Phase 2-3 models
```

---

## Phase 1 / Section A: Data Foundation & Event Infrastructure

### Data Flow

**IN:** Raw data from 5 source categories — NSE/BSE feeds (Zerodha, Angel One, TrueData), historical OHLCV (10+ years), news (ET, Moneycontrol, LiveMint), social media (Twitter, Reddit, Telegram), government (RBI, SEBI, budget/GST)

**INSIDE:**

1. All sources publish to **Kafka (KRaft mode)** topics: `raw-ticks`, `normalized-ohlcv`, `signals`, `orders`, `alerts`, `features`
2. **Protobuf Schema Registry** enforces data governance
3. **Dead Letter Queue** catches failed messages
4. **Preprocessing pipeline** cleans, normalizes splits/bonuses, validates OHLC integrity, checks circuit limits, timestamps to IST
5. Routes to: **TimescaleDB** (OHLCV series) | **PostgreSQL** (trades, metadata) | **Redis** (1–5s TTL cache) | **MinIO** (Parquet archive)
6. **Feast Feature Store** (Redis online + PostgreSQL offline) computes: RSI, MACD, BB, VWAP, ATR, OBV + India-specific: delivery %, FII/DII flows, promoter %
7. **Airflow DAGs** run post-market: `dag_daily_bhavcopy`, `dag_fii_dii`, `dag_fundamentals`, `dag_corporate_actions`, `dag_macro_data`

**OUT:** Point-in-time correct features with no data leakage, versioned and ready for AI models

### Internal Data Flow Diagram

```
NSE/BSE    Brokers    News    Social    SEBI/RBI    Bhavcopy
  |          |         |        |          |           |
  v          v         v        v          v           v
       Kafka (KRaft, no ZooKeeper)
       Topics: raw-ticks | normalized-ohlcv | signals | alerts
       Schema Registry (Protobuf) + Dead Letter Queue
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
       Tech: RSI, MACD, BB, ATR, OBV
       Fund: revenue z-scores, P/E, ROE
       India: delivery%, FII/DII, promoter%
                    |
                    v
       Airflow Batch DAGs (post-market)
       bhavcopy | fii_dii | fundamentals | corporate_actions | macro
```

### Implementation Checklist

**A.1 — Kafka Event Bus:**

- [ ]  Add Kafka (KRaft) to `docker-compose.yml`
- [ ]  Create `backend/brain/events/kafka_manager.py`
- [ ]  Define topics + `backend/brain/events/topics.py`
- [ ]  Create `backend/brain/schemas/market_data.proto`
- [ ]  Implement DLQ + health checks

**A.2 — Enhanced Ingestion:**

- [ ]  Upgrade extractors to publish to Kafka
- [ ]  Enhance NSE Bhavcopy for CM-UDiFF format
- [ ]  `backend/brain/ingestion/normalizer.py` + `data_quality.py`
- [ ]  Circuit breaker detection + exponential backoff reconnection

**A.3 — Feature Store (Feast + Redis):**

- [ ]  Configure Feast + `backend/brain/features/feature_store.py`
- [ ]  `technical_indicators.py` + `fundamental_features.py` + `india_specific_features.py`
- [ ]  Point-in-time retrieval + versioning

**A.4 — Storage Enhancement:**

- [ ]  Evaluate QuestDB (6–13x faster than TimescaleDB)
- [ ]  MinIO for Parquet archival
- [ ]  Redis TTL strategy
- [ ]  Airflow DAGs in `backend/brain/batch/airflow_dags/`

---

## Phase 2–3 / Section B: AI/ML Model Training & Signal Generation

### Data Flow

**IN:** Features from Feast + market regime context

**INSIDE:**

1. **MLflow** tracks experiments; **Optuna** for Bayesian hyperparameter optimization
2. **Walk-forward validation** (never k-fold); **CPCV** for tuning
3. **Feature pipeline:** log/scaling → correlation filtering → Boruta → LASSO → PCA
4. **Model tiers:**
    - Tier 1 (Baseline): GARCH(1,1) + EGARCH → volatility
    - Tier 2 (Workhorses): XGBoost / LightGBM / CatBoost → direction
    - Tier 3 (Deep): LSTM with attention → intraday
    - Primary: TFT → multi-horizon quantile forecasts (10th/50th/90th)
    - Long: N-BEATS / N-HiTS → extended horizon
5. All models exported to **ONNX** (5–20ms inference)
6. **Signal fusion:** Tech(30%) + Sentiment(25%) + Fundamental(20%) + Volume(15%) + Macro(10%)
7. **Meta-labeling:** direction model + confidence model. <40% suppressed, 40–60% watchlist, 60–80% actionable, >80% high-conviction
8. **VectorBT Pro** backtesting with Indian costs: STT, exchange, GST, stamp duty, SEBI fees, DP charges

**OUT:** Structured signal JSON: `{ticker, direction, confidence, target, stop_loss, contributing_factors, explanation}`

### Internal Data Flow Diagram

```
Feast Feature Store
       |
       v
  MLflow + Optuna + Walk-Forward Validation + CPCV
  Feature Pipeline: log/scale -> correlation -> Boruta -> LASSO -> PCA
       |
       v
  MODEL TIERS:
  T1: GARCH+EGARCH -> Volatility
  T2: XGBoost/LGBM/CatBoost -> Direction
  T3: LSTM-Attention -> Intraday
  Primary: TFT -> Multi-horizon quantiles
  Long: N-BEATS/N-HiTS -> Extended
       |
       v  ONNX Runtime (5-20ms)
  SIGNAL GENERATION:
  Fusion: Tech(30%) + Sent(25%) + Fund(20%) + Vol(15%) + Macro(10%)
  Thresholds: <40% kill | 40-60% watch | 60-80% act | >80% conviction
  Meta-labeling: direction + confidence models
  Dynamic weighting: earnings season, RBI policy, trending
       |
       v
  {ticker, direction, confidence, target, stop_loss, factors}
  Validated via VectorBT Pro (Indian costs: STT, GST, stamp)
  QuantStats tearsheets: Sharpe, Sortino, Calmar, heatmaps
```

### Implementation Checklist

**B.1 — ML Infrastructure:**

- [ ]  MLflow + `backend/brain/ml/training/experiment_tracker.py`
- [ ]  `walk_forward.py` + `cpcv.py` + `feature_selection.py`
- [ ]  Optuna Bayesian optimization with pruning

**B.2 — Core Models:**

- [ ]  `backend/brain/ml/models/garch_model.py`
- [ ]  `gradient_boosting.py` + `lstm_attention.py` + `tft_model.py` + `nbeats_model.py`
- [ ]  ONNX export + `backend/brain/ml/serving/onnx_inference.py`

**B.3 — Signal Engine:**

- [ ]  `backend/brain/signals/signal_generator.py` + `signal_fusion.py`
- [ ]  `confidence_scorer.py` + `meta_labeling.py`
- [ ]  `signal_models.py` (Pydantic schemas)

**B.4 — Backtesting:**

- [ ]  `backend/brain/backtesting/vectorbt_engine.py`
- [ ]  `indian_costs.py` (STT, GST, stamp duty, SEBI, DP)
- [ ]  `quantstats_reports.py` + `performance_metrics.py`

---

## Phase 3–4–5 / Section C: Intelligence Layer & LLM Agents

### Data Flow

**IN:** Signals + features + raw text from B + NSE options chain data

**INSIDE:**

1. **HMM Regime Detection:** 3-state Gaussian HMM (bull/bear/sideways) on returns, VIX, FII flows, INR/USD. Complementary: K-Means/GMM, CUSUM change-point. Routes to specialist models.
2. **FinBERT Sentiment:** Indian variant `kdave/FineTuned_Finbert`. Pipeline: language detect → Hindi→English (IndicTrans2) → NER → sentiment → event extraction. Ensemble: 0.5×FinBERT + 0.2×VADER + 0.3×LLM. Sources: ET, Moneycontrol, LiveMint, Twitter, Reddit.
3. **LangGraph Multi-Agent System:**
    - Tiered LLM routing: Tier 1 (Claude/GPT-5), Tier 2 (GPT-4.1 mini), Tier 3 (local FinGPT/Mistral)
    - 4 analyst agents: Fundamental, Technical, Sentiment, Macro
    - Dialectical: Bull Researcher ↔ Bear Researcher → Research Synthesizer
    - Trader Agent → Risk Agent (veto power)
    - Reports: Morning Brief 8:30 AM, Market Wrap 4:30 PM, Weekly Analysis
4. **Decision Engine:** Hunter-Guard → Options flow (PCR, Max Pain, IV skew) → Hard rules (VIX cap, F&O ban, SEBI margin) → PSO Ensemble → Meta-Labeling Filter (confidence <40% = killed)
5. **Risk Management:** ATR stops (Entry - ATR14×Mult) | Kelly sizing (Half/Quarter) | Capital escalation (10%DD→halve, 15%→halt, 20%→kill) | VaR/CVaR (Historical+Parametric+Monte Carlo) | Stress tests (2008, 2020, 2016) | SEBI margin checks
6. **HRP Portfolio:** Cluster → quasi-diag → recursive bipartition → inverse-variance. Rebalance weekly or on regime change.
7. **Regime Throttling:** Crisis → suppress longs, tighten stops 50%, cut to 20%, increase cash
8. **Tail-Risk Hedging:** 1–3% to NIFTY OTM puts, VIX calls, Gold ETF, USD/INR long
9. **Governance Scoring:** 0–100 (pledging 25%, RPT 20%, auditor 15%, board 15%, regulatory 15%, disclosure 10%). Auto-exclude <40.
10. **SHAP/LIME:** Per-trade waterfall charts + natural language explanations

**OUT:** Risk-bounded Buy/Sell/Hold decisions with position sizes, stop levels, hedge allocations, confidence scores, and full NL explanations

### Internal Data Flow Diagram

```
Signals + Features + Raw Text + Options Chain
       |
       +---> HMM Regime (3-state: bull/bear/sideways)
       |     + K-Means/GMM, CUSUM change-point
       |     -> Routes to specialist models per regime
       |
       +---> FinBERT NLP (Indian variant)
       |     Lang detect -> Hindi->En -> NER -> Sentiment
       |     Ensemble: 0.5*FinBERT + 0.2*VADER + 0.3*LLM
       |
       +---> LangGraph Multi-Agent System
       |     [Fund] [Tech] [Sent] [Macro] analysts
       |     Bull Researcher <-> Bear Researcher -> Synthesizer
       |     Trader Agent -> Risk Agent (veto)
       |     Tiered LLM: Claude > GPT-4.1m > Local
       |
       +---> Governance Scoring (auto-exclude <40)
       |
       v
  Hunter-Guard -> Options Flow -> Hard Rules
  -> PSO Ensemble -> Meta-Label Filter
       |
       v
  Risk Engine: Kelly + ATR + HRP + Regime Throttle
  Capital Escalation: 10%->halve, 15%->halt, 20%->kill
  VaR/CVaR + Stress Tests + Tail Hedging
       |
       v
  SHAP/LIME -> NL Explanation per trade
```

### Implementation Checklist

**C.1 — HMM Regime:**

- [ ]  `backend/brain/regime/hmm_detector.py` + `regime_router.py` + `changepoint_detector.py`

**C.2 — FinBERT Sentiment:**

- [ ]  `backend/brain/sentiment/finbert_model.py` + `nlp_pipeline.py`
- [ ]  `news_scrapers.py` + `social_scraper.py` + `earnings_analyzer.py` + `sentiment_ensemble.py`

**C.3 — LLM Multi-Agent:**

- [ ]  `backend/brain/agents/orchestrator.py` (LangGraph)
- [ ]  `fundamental_analyst.py` + `technical_analyst.py` + `sentiment_analyst.py` + `macro_analyst.py`
- [ ]  `bull_researcher.py` + `bear_researcher.py` + `research_synthesizer.py`
- [ ]  `trader_agent.py` + `risk_agent.py` + `report_generator.py` + `llm_router.py`

**C.4 — Risk Engine:**

- [ ]  `backend/brain/risk/stop_loss.py` + `position_sizing.py`
- [ ]  `var_calculator.py` + `stress_testing.py` + `capital_protection.py` + `sebi_compliance.py`

**C.5 — Governance:**

- [ ]  `backend/brain/governance/governance_scorer.py` + `promoter_tracker.py` + `red_flag_detector.py`

**C.6 — SHAP Explainability:**

- [ ]  `backend/brain/explainability/shap_explainer.py` + `lime_explainer.py` + `nl_explanation.py`

---

## Phase 3+ / Section D: Advanced ML & Real-Time Engine

### Data Flow

**IN:** Historical data + current features + regime state

**INSIDE:**

1. **Foundation Models:** Kronos (fine-tuned on Indian OHLCV) + TimesFM 2.5 + Chronos/Moirai zero-shot baselines. Regime-conditional ensembling via HMM + XGBoost meta-learner.
2. **RL Portfolio:** FinRL + PPO agent in Indian market environment (NIFTY 50, Indian costs, margin rules). Target: Sharpe >2.0. Black-Litterman with AI-generated views.
3. **Global Correlations:** Overnight processing of S&P 500, NASDAQ, SGX/GIFT NIFTY, Asian markets, crude oil, DXY, US 10Y. DCC-GARCH time-varying correlation. Pre-market signal by 8:30 AM IST. Breakout alerts at >2σ divergence.
4. **Alternative Data:** Google Trends India, e-commerce pricing, [Naukri.com](http://Naukri.com) jobs, app rankings, UPI data (NPCI monthly), SEBI SAST, bulk/block deals, insider disclosures. Signal decay half-lives per source.

**OUT:** Enhanced predictions + optimized portfolio weights + pre-market signals + alternative data edge

### Implementation Checklist

**D.1 — Foundation Models:**

- [ ]  `backend/brain/ml/models/kronos_model.py` + `timesfm_model.py` + `ensemble_manager.py`

**D.2 — RL Portfolio:**

- [ ]  `backend/brain/portfolio/rl_optimizer.py` + `finrl_environment.py` + `black_litterman.py` + `hrp_optimizer.py`

**D.3 — Global Correlations:**

- [ ]  `backend/brain/correlation/global_signals.py` + `correlation_matrix.py` + `premarket_engine.py`

**D.4 — Alternative Data:**

- [ ]  `backend/brain/alt_data/google_trends.py` + `web_scraper.py` + `regulatory_filings.py` + `upi_data.py`

---

## Phase 6 / Section E: Production Hardening & Dashboard

### Data Flow

**IN:** Risk-bounded orders + explanations from C/D

**INSIDE:**

1. **Smart Execution:** VWAP/TWAP on NSE/BSE, order splitting, slippage tracking. Future: DRL agent on NSE order book.
2. **Continuous Learning:** Walk-forward retraining, concept drift detection, PSO weight recalibration, triple-barrier labeling, online learning for sentiment + regime.
3. **Feedback Loop:** Every trade logged (entry, signals, confidence, outcome, P&L attribution). Reinforcement learning reward signal. Monthly performance reports.
4. **Agentic Reports:** Analyst → Writer → Editor agents via RAG. Morning Brief 8:30 AM, Market Wrap 4:30 PM, Weekly Analysis.
5. **Monitoring:** Prometheus + Grafana metrics, Jaeger/OpenTelemetry tracing, Evidently AI model drift (KL-divergence, PSI).
6. **Dashboard:** 7 panels (Market Overview, Signal Board, Stock Deep Dive, Portfolio Tracker, Sentiment Dashboard, Agent Activity Log, Report Center) + TradingView Lightweight Charts + SHAP waterfalls + real-time WebSocket.

**OUT:** REST API + WebSocket:

- `GET /brain/picks` — top stock picks
- `GET /brain/market-regime` — current state
- `GET /brain/stock/{symbol}` — detailed analysis
- `GET /brain/portfolio` — allocation
- `GET /brain/risk-dashboard` — risk metrics

**Reports:** Top picks (short+long term), stocks to avoid, entry/exit points, risk level, confidence score, full NL explanation

### Implementation Checklist

**E.1 — Monitoring:**

- [ ]  Prometheus + Grafana + Jaeger/OpenTelemetry
- [ ]  Evidently AI model drift (KL-divergence, PSI)
- [ ]  Retraining triggers on degradation

**E.2 — Dashboard:**

- [ ]  TradingView Lightweight Charts
- [ ]  7 panels + SHAP waterfalls + WebSocket updates
- [ ]  Automated PDF report generation

---

## System Reaction Matrix

How each phase reacts to key market events:

| Event | Phase 1 / A | Phase 2-3 / B | Phase 3-5 / C | Phase 3+ / D | Phase 6 / E |
| --- | --- | --- | --- | --- | --- |
| **Market crash** | Ingests data | Models predict drop | HMM->Crisis, blocks buys, cuts to 20% | Correlation alerts fire | Executes sells, reports |
| **Earnings beat** | Ingests news+data | Score updates, signal fires | NLP bullish, Hunter entry, Kelly sizes | No change | Buys, logs, reports |
| **FII selling** | Ingests FII data | Macro signal negative | Guard exit, tightens stops | Global correlation updates | Exits weak, reports |
| **F&O ban** | Ingests ban list | Flags metadata | Hard rule blocks trade | No change | No execution |
| **Model drift** | No change | Drift detected | Meta-label filters more | Ensemble reweights | Triggers retraining |
| **RBI rate hike** | Ingests announcement | Macro updates | Sector rotation, adjusts weights | Correlation shift | Reports updated |

---

## Implementation → Phase Mapping

| Section | Maps to Phases | Core Deliverable |
| --- | --- | --- |
| A) Data Foundation | Phase 1 | Kafka + DBs + Feast + Airflow running |
| B) AI/ML + Signals | Phase 2 + 3 | Models trained, signals with confidence |
| C) Intelligence + LLM + Risk | Phase 3 + 4 + 5 | HMM, NLP, agents, risk, governance, XAI |
| D) Advanced ML | Phase 3 (advanced) | Foundation models, RL, global signals, alt data |
| E) Production | Phase 6 | Dashboard, monitoring, reports, API |

---

## Feedback Loop: How the System Self-Improves

```
Phase 6 (Execution) logs every trade:
  entry reason | signals | confidence | outcome | P&L
       |
       v
  Walk-Forward Validation
  Train on 3 years -> Test on next quarter -> Roll forward
       |
       v
  Concept Drift Detection
  Model accuracy drops below threshold -> Trigger retrain
       |
       v
  PSO Weight Recalibration
  Down-weight decaying models, up-weight improving ones
       |
       v
  Triple-Barrier Labeling
  Profit target | Stop-loss | Time limit (adaptive to volatility)
       |
       v
  Updated models deployed -> Phase 2-3 predictions improve
  Cycle repeats continuously
```