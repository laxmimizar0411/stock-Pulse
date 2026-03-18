# Stock Pulse — Master Build Guide
## From Brain→Core Documents to Fully Integrated Website

**Generated from**: Brain→Core Documents 1-4 (KB v2.0, Supplements v2.1, v2.2, v2.3)
**Current State**: React frontend (15 pages) + FastAPI backend + MongoDB + PostgreSQL + Redis
**Target**: Full-featured Indian stock market intelligence platform (NSE/BSE)

---

## Current Website Inventory

### Frontend (React + Radix UI + Tailwind + Recharts)
| Page | Status | Purpose |
|------|--------|---------|
| Dashboard.jsx | Exists | Main overview |
| StockAnalyzer.jsx | Exists | Individual stock analysis |
| Screener.jsx | Exists | Stock screening/filtering |
| Portfolio.jsx | Exists | Portfolio management |
| Watchlist.jsx | Exists | Watchlist tracking |
| NewsHub.jsx | Exists | News aggregation |
| Alerts.jsx | Exists | Price/event alerts |
| Backtest.jsx | Exists | Strategy backtesting |
| Derivatives.jsx | Exists | F&O data |
| IntradayMetrics.jsx | Exists | Intraday analytics |
| MacroIndicators.jsx | Exists | Macro economic data |
| Reports.jsx | Exists | PDF report generation |
| DataPipeline.jsx | Exists | Pipeline monitoring |
| DatabaseDashboard.jsx | Exists | DB health monitoring |
| PostgresControl.jsx | Exists | PostgreSQL admin |

### Backend (FastAPI + Motor/MongoDB + PostgreSQL + Redis)
| Service | Status | Purpose |
|---------|--------|---------|
| server.py | Exists | Main FastAPI app |
| scoring_engine.py | Exists | Stock scoring (deal-breakers, risk penalties) |
| market_data_service.py | Exists | Market data fetching |
| llm_service.py | Exists | AI-powered insights (generate_stock_insight, summarize_news) |
| backtesting_service.py | Exists | Strategy backtesting |
| alerts_service.py | Exists | Alert management |
| cache_service.py | Exists | Redis caching |
| pipeline_service.py | Exists | Data pipeline orchestration |
| timeseries_store.py | Exists | TimescaleDB/time-series storage |
| websocket_manager.py | Exists | Real-time WebSocket |
| pdf_service.py | Exists | PDF report generation |
| mock_data.py | Exists | Mock/sample data |

### Data Extraction Pipeline
| Extractor | Status | Source |
|-----------|--------|--------|
| yfinance_extractor.py | Exists | Yahoo Finance (OHLCV, basics) |
| screener_extractor.py | Exists | Screener.in (fundamentals) |
| grow_extractor.py | Exists | Groww (market data) |
| nse_bhavcopy_extractor.py | Exists | NSE Bhavcopy (EOD data) |
| base_extractor.py | Exists | Base class for all extractors |

### Processing Pipeline
| Component | Status | Purpose |
|-----------|--------|---------|
| calculation_engine.py | Exists | Derived metric calculations |
| technical_calculator.py | Exists | Technical indicator computation |
| cleaner.py | Exists | Data cleaning/normalization |
| validation_engine.py | Exists | Data quality validation |
| confidence_scorer.py | Exists | Data confidence scoring |
| orchestrator.py | Exists | Pipeline orchestration |

### Jobs (Scheduled Tasks)
| Job | Status | Purpose |
|-----|--------|---------|
| derive_metrics.py | Exists | Compute derived metrics |
| intraday_metrics_job.py | Exists | Intraday computations |
| valuation_job.py | Exists | Valuation calculations |
| shareholding_job.py | Exists | Shareholding pattern tracking |
| derivatives_job.py | Exists | F&O data processing |
| macro_indicators_job.py | Exists | Macro indicator updates |
| ml_features_job.py | Exists | ML feature preparation |

---

## MASTER BUILD PLAN — 10 Phases

---

### PHASE 1: Data Infrastructure Hardening
**Priority**: CRITICAL — Everything else depends on this
**Brain Doc Reference**: Sections 18, 19 (Data Architecture, Indian Market Sources)

#### 1.1 Complete Data Extraction Coverage
- [ ] **Enhance yfinance_extractor**: Add options chain data, institutional holdings, dividend history
- [ ] **Enhance screener_extractor**: Add quarterly results, cash flow statements, balance sheet trends, peer comparison data
- [ ] **Add NSE Official Data extractor**: FII/DII daily activity, bulk/block deals, delivery percentage data
- [ ] **Add BSE extractor**: Corporate announcements, board meeting outcomes, AGM results
- [ ] **Add corporate events extractor**: Earnings dates, dividends, splits, bonus, rights issues, M&A
- [ ] **Add promoter holdings extractor**: SAST data from NSE/BSE, pledging data (critical for Doc 4 red flags)
- [ ] **Add index data extractor**: Nifty 50, Nifty 500, sectoral indices, India VIX

#### 1.2 Data Quality & Storage
- [ ] **Enhance validation_engine.py**: Add split/bonus adjustment logic, corporate action handling
- [ ] **Add data reconciliation**: Cross-validate prices across yfinance vs NSE Bhavcopy vs Groww
- [ ] **TimescaleDB optimization**: Implement hypertables for OHLCV, continuous aggregates for multi-timeframe (1min, 5min, 15min, daily, weekly, monthly)
- [ ] **MongoDB schema finalization**: Collections for fundamentals, corporate events, news, sentiment scores
- [ ] **Redis feature store setup**: Pre-computed features for real-time serving (Doc 1, Sec 18: Feature Store)
- [ ] **Add data freshness monitoring**: Alert when any data source is stale beyond threshold

#### 1.3 Scheduled Pipeline
- [ ] **Market hours scheduler**: Pre-market (9:00-9:15), market (9:15-15:30), post-market jobs
- [ ] **EOD pipeline**: Bhavcopy → clean → compute indicators → update scores → generate alerts
- [ ] **Weekly/Monthly batch**: Fundamental data refresh, shareholding patterns, macro indicators
- [ ] **Integrate with DataPipeline.jsx**: Show real pipeline status, logs, success/failure rates

**Deliverables**: All Indian market data flowing reliably into the platform with quality checks.

---

### PHASE 2: Technical Indicator Engine & Feature Engineering
**Priority**: HIGH — Foundation for all ML models
**Brain Doc Reference**: Section 20 (Technical Indicators), Section 18 (Feature Engineering)

#### 2.1 Complete Technical Indicator Library (36+ indicators)
- [ ] **Trend**: SMA(20,50,200), EMA(12,26,50), MACD(12,26,9), ADX(14), Parabolic SAR, Supertrend
- [ ] **Momentum**: RSI(14), Stochastic(14,3), Williams %R, ROC, CCI(20), MFI(14)
- [ ] **Volatility**: Bollinger Bands(20,2), ATR(14), Keltner Channels, Historical Volatility, Donchian Channels
- [ ] **Volume**: OBV, VWAP, A/D Line, Chaikin Money Flow, Volume SMA(20)
- [ ] **Multi-timeframe**: Compute each indicator across daily, weekly, monthly windows
- [ ] **Use Pandas-TA library** (130+ indicators) as base — Doc 4 recommendation

#### 2.2 Advanced Feature Engineering
- [ ] **Relative features**: Express indicators relative to sector average and Nifty 50
- [ ] **Interaction features**: RSI × Volume change, MACD × Volatility, Price × Delivery%
- [ ] **Rolling statistics**: Mean, std, skew, kurtosis of returns over 5/20/60/200 windows
- [ ] **Sector-specific features**: Banking (NPA, CASA), IT (USD sensitivity), Pharma (FDA pipeline)
- [ ] **Indian market features**: FII/DII flow momentum, promoter holding changes, delivery % trends

#### 2.3 Feature Store Integration
- [ ] **Redis-based feature store**: Pre-computed features for online serving
- [ ] **Feature versioning**: Track feature computation logic changes
- [ ] **Feature importance tracking**: Log which features drive predictions

**Deliverables**: 50+ features per stock, updated in real-time, accessible via feature store.

---

### PHASE 3: Scoring Engine & Forensic Models (Stocks to Buy/Avoid)
**Priority**: HIGH — Direct user-facing value
**Brain Doc Reference**: Sections 13 (Risk), Doc 4 (Forensic Models, DVM, MMI)

#### 3.1 Enhance Existing Scoring Engine
The current `scoring_engine.py` already has deal-breakers (D1-D10) and risk penalties (R1-R10). Enhance with:
- [ ] **Altman Z-Score**: Implement with Indian thresholds (Z>2.99 safe, Z<1.81 distress)
- [ ] **Beneish M-Score**: Earnings manipulation detection (M>-2.22 = likely manipulation)
- [ ] **Piotroski F-Score**: 9-point financial health (7-9 = strong buy, 0-3 = avoid)
- [ ] **Promoter Pledging Alerts**: Flag >30% as caution, >80% as deal-breaker (already D7)
- [ ] **200-Day SMA Filter**: Auto-flag stocks below 200-DMA as "Avoid"

#### 3.2 DVM Scoring Framework (Doc 4)
Build the Trendlyne-style DVM scoring (0-100 per pillar):
- [ ] **Durability Score**: Revenue/profit growth consistency, cash flow stability, low debt, high ROE
- [ ] **Valuation Score**: Undervalued relative to peers AND own historical range (P/E, P/B, EV/EBITDA, PEG)
- [ ] **Momentum Score**: 30+ technical indicators combined — price strength, volume trends, MA crossovers
- [ ] **Composite Rule**: Stocks in top 20% across ALL THREE pillars = high conviction buys

#### 3.3 Market Mood Index (MMI)
Build proprietary MMI from 7 components (Doc 4):
- [ ] **FII Activity**: Net OI of FIIs in index futures
- [ ] **India VIX**: 30-day anticipated volatility
- [ ] **Market Breadth**: Advancing vs declining stocks on Nifty 50
- [ ] **Price Momentum**: 30-day EMA minus 90-day EMA of Nifty 50
- [ ] **Price Strength**: % stocks at 52-week high vs low
- [ ] **Gold Demand**: Gold vs Nifty 50 relative returns
- [ ] **Skew**: OTM put IV minus OTM call IV
- [ ] **Action zones**: <30 = BUY, 31-49 = cautious buy, ~50 = hold, 51-70 = tighten stops, >70 = SELL

#### 3.4 Composite Risk Score (0-100 per stock) — Doc 1 Sec 13.2
- [ ] **Volatility Risk**: Historical + implied vol relative to sector/market
- [ ] **Liquidity Risk**: Volume, Amihud ratio, market cap tier
- [ ] **Fundamental Risk**: D/E, interest coverage, cash flow stability
- [ ] **Technical Risk**: Distance from support, trend strength, overbought/oversold
- [ ] **Sentiment Risk**: Negative news trends, insider selling
- [ ] **Correlation Risk**: Market beta (diversification value)

#### 3.5 Frontend Integration
- [ ] **StockAnalyzer.jsx**: Add DVM scores, Z-Score, M-Score, F-Score, risk score gauges
- [ ] **Dashboard.jsx**: Add MMI indicator (fear/greed gauge), market health overview
- [ ] **Screener.jsx**: Filter by DVM scores, forensic flags, risk scores

**Deliverables**: Every stock has a comprehensive score card; market mood displayed on dashboard.

---

### PHASE 4: Sentiment Analysis & News Intelligence
**Priority**: HIGH — Layer 3 of the 6-layer signal pipeline
**Brain Doc Reference**: Sections 4 (LLMs), 17 (Sentiment & Alt Data)

#### 4.1 Sentiment Pipeline
- [ ] **FinBERT integration**: Fine-tune on Indian financial news for sentiment classification
- [ ] **News scraping**: MoneyControl, Economic Times, LiveMint, Business Standard RSS/API
- [ ] **Corporate filing sentiment**: BSE/NSE announcement tone analysis
- [ ] **Social media signals**: Twitter/X financial accounts, Reddit (r/IndianStreetBets)
- [ ] **Emotion analysis** (Doc 2): Beyond positive/negative — detect fear, greed, uncertainty
- [ ] **Source weighting**: Institutional analyst reports weighted higher than retail social media

#### 4.2 LLM-Powered Analysis (Enhance existing llm_service.py)
- [ ] **RAG pipeline**: Connect LLM to real-time financial data for up-to-date analysis
- [ ] **Earnings call analysis**: Quarterly transcript tone analysis, forward guidance extraction
- [ ] **Event impact assessment**: BSTS causal impact after RBI policy, budget, earnings (Doc 2)
- [ ] **Auto-generated reports**: LLM writes stock analysis reports from data

#### 4.3 Frontend Integration
- [ ] **NewsHub.jsx**: Add sentiment scores per article, trending sentiment by stock/sector
- [ ] **StockAnalyzer.jsx**: Sentiment tab showing news timeline with sentiment overlay
- [ ] **Alerts.jsx**: Sentiment-based alerts (e.g., "Sudden negative sentiment spike for RELIANCE")

**Deliverables**: Real-time sentiment scoring on all major news, integrated into stock analysis.

---

### PHASE 5: ML/DL Prediction Models
**Priority**: HIGH — Core intelligence engine
**Brain Doc Reference**: Sections 2, 3, 5 (ML/DL, Transformers, Foundation Models)

#### 5.1 Baseline Models
- [ ] **ARIMA/SARIMA**: Statistical baseline for price forecasting (seasonal patterns: budget, Diwali)
- [ ] **XGBoost/LightGBM**: Cross-sectional return prediction using 50+ features
- [ ] **Random Forest**: Direction prediction (up/down/sideways) — good interpretability baseline
- [ ] **Logistic Regression/ElasticNet**: Factor models for interpretable scoring

#### 5.2 Deep Learning Models
- [ ] **LSTM**: Multi-layer for price prediction; the most validated model for stock forecasting
- [ ] **BiLSTM**: Forward + backward passes for richer temporal context
- [ ] **LSTM-CNN Hybrid**: CNN extracts spatial features from price windows, LSTM learns temporal
- [ ] **GRU**: Faster training alternative to LSTM for smaller datasets/quick retraining

#### 5.3 Transformer Models
- [ ] **TFT (Temporal Fusion Transformer)**: Multi-horizon forecasting with interpretable attention
  - Variable Selection Networks for dynamic feature importance
  - Quantile outputs (10th, 50th, 90th percentile predictions)
- [ ] **PatchTST**: Subseries-level tokenization for improved performance
- [ ] **Informer**: Long-sequence forecasting with efficient attention

#### 5.4 Foundation Models (Zero-Shot)
- [ ] **Chronos integration**: Pre-trained probabilistic forecasting, zero-shot on unseen stocks
- [ ] **TS-RAG** (Doc 4, NeurIPS 2025): Build pattern database from 10+ years Nifty 500, retrieve similar historical patterns for each prediction

#### 5.5 Ensemble & Model Management
- [ ] **Ensemble combiner**: Weighted combination of all models via meta-learning
- [ ] **MLflow integration**: Experiment tracking, model versioning, A/B testing
- [ ] **Walk-forward validation**: Proper temporal split, purged cross-validation
- [ ] **Model monitoring**: Track prediction accuracy, detect model drift

#### 5.6 Frontend Integration
- [ ] **StockAnalyzer.jsx**: Add prediction tab showing model forecasts with confidence intervals
- [ ] **Dashboard.jsx**: Top predictions summary, model accuracy metrics
- [ ] **New page — Model Performance**: Show model comparison, backtested accuracy, live accuracy

**Deliverables**: Multiple models producing daily predictions with confidence intervals.

---

### PHASE 6: Risk Management & Regime Detection
**Priority**: MEDIUM-HIGH — Critical for production
**Brain Doc Reference**: Sections 13, 14 (Risk Management, Bleeding-Edge Quant)

#### 6.1 Volatility & Risk Models
- [ ] **GARCH/EGARCH/GJR-GARCH**: Time-varying volatility forecasting per stock
- [ ] **VaR computation**: Historical, parametric, and Monte Carlo VaR at 95%/99%
- [ ] **CVaR (Expected Shortfall)**: Average loss in worst-case scenarios
- [ ] **Maximum Drawdown tracking**: Real-time MDD monitoring per position and portfolio

#### 6.2 Regime Detection
- [ ] **Hidden Markov Models (HMM)**: Detect bull/bear/sideways regime changes
- [ ] **Gaussian Mixture Models (GMM)**: Alternative regime classification (Doc 2)
- [ ] **India VIX regime mapping**: Map VIX levels to risk regimes
- [ ] **Regime-adaptive scaling**: Auto-adjust strategy weights based on detected regime

#### 6.3 Anomaly Detection
- [ ] **Isolation Forest**: Detect unusual price/volume patterns
- [ ] **Autoencoder-based**: Learn "normal" market behavior, flag deviations
- [ ] **Circuit breaker prediction**: Model stock-level and market-wide circuit breaker triggers

#### 6.4 Stop-Loss & Exit Logic
- [ ] **ATR-based trailing stops**: Dynamic stops that adjust with volatility
- [ ] **Volatility-scaled position sizing**: Inverse proportion to ATR
- [ ] **Time-based exits**: Max holding period enforcement
- [ ] **Valuation-based sells** (Doc 4): P/E Z-score > +2 triggers profit booking

#### 6.5 Frontend Integration
- [ ] **Portfolio.jsx**: Add risk metrics (VaR, CVaR, beta, Sharpe) per holding and portfolio-level
- [ ] **Dashboard.jsx**: Market regime indicator (bull/bear/volatile), portfolio heat map
- [ ] **Alerts.jsx**: Risk-based alerts (VaR breach, regime change, anomaly detected)
- [ ] **New page — Risk Dashboard**: Comprehensive risk overview with stress test results

**Deliverables**: Automated risk monitoring, regime detection, and dynamic stop-loss management.

---

### PHASE 7: Portfolio Intelligence & Optimization
**Priority**: MEDIUM — After predictions and risk are working
**Brain Doc Reference**: Sections 15, 10 (Portfolio Optimization, Trading Strategies)

#### 7.1 Portfolio Optimization Methods
- [ ] **Markowitz Mean-Variance**: With Ledoit-Wolf shrinkage for stable covariance
- [ ] **Black-Litterman**: Incorporate ML predictions as "views" for more stable portfolios
- [ ] **Hierarchical Risk Parity (HRP)**: Hierarchical clustering, robust to estimation errors
- [ ] **Mean-CVaR**: Optimize while controlling tail risk
- [ ] **Kelly Criterion**: Optimal position sizing (use Half/Quarter Kelly in practice)

#### 7.2 Portfolio Rules (Doc 3, Sec J)
- [ ] **Max portfolio heat**: 6-8% total risk at any time
- [ ] **Sector exposure cap**: 20-25% per sector
- [ ] **Single stock limit**: Never >5% risk per position
- [ ] **Drawdown rule**: Auto-reduce size after 10% drawdown
- [ ] **Correlation limits**: Avoid highly correlated positions

#### 7.3 Strategy Engine
- [ ] **Momentum strategy**: 12-month lookback, skip most recent month, top 20% quintile
- [ ] **Mean reversion**: Bollinger/RSI extreme signals with quality filters
- [ ] **Sector rotation**: RRG-style relative rotation based on momentum + breadth
- [ ] **Event-driven**: Post-earnings drift, post-announcement strategies
- [ ] **Multi-indicator fusion**: Combine 4+ indicators (profit factor 1.882 per Doc 1)

#### 7.4 Frontend Integration
- [ ] **Portfolio.jsx**: Add optimization suggestions, rebalancing recommendations
- [ ] **Backtest.jsx**: Connect to real backtesting engine with walk-forward validation
- [ ] **New page — Strategy Builder**: Visual strategy construction with indicator selection
- [ ] **Portfolio analytics**: QuantStats-style tear sheets in the Reports section

**Deliverables**: Automated portfolio optimization with multiple strategies and proper backtesting.

---

### PHASE 8: Signal Generation & Ranking Engine
**Priority**: MEDIUM — Ties everything together
**Brain Doc Reference**: Section 10 (6-Layer Signal Pipeline), Section 12 (Advanced Alpha)

#### 8.1 6-Layer Signal Fusion Pipeline
- [ ] **Layer 1 — Technical**: Automated pattern recognition + indicator signals
- [ ] **Layer 2 — Fundamental**: Valuation metrics, earnings surprise, DVM scores
- [ ] **Layer 3 — Sentiment**: LLM-derived sentiment from news, social, filings
- [ ] **Layer 4 — Alternative Data**: Options flow, insider activity, delivery % (start with accessible data)
- [ ] **Layer 5 — ML/DL Prediction**: Model outputs from LSTM, TFT, XGBoost ensemble
- [ ] **Layer 6 — Meta-Fusion**: Weighted combination of all layers via attention-based aggregation

#### 8.2 Stock Ranking Engine
- [ ] **Conviction tiers**: Strong Buy / Buy / Hold / Sell / Strong Sell
- [ ] **Sector-relative ranking**: Rank within sector, not just absolute
- [ ] **High-conviction filtering**: Only top 5-10% treated as high-conviction (Doc 1, Sec 12.6)
- [ ] **Event-sensitive timing**: Rebuild scores after earnings/filings, not just calendar dates

#### 8.3 Alpha Signals (Differentiation Layer)
- [ ] **Microstructure alpha** (non-HFT): Order-book imbalance, volume-spread dynamics
- [ ] **Cross-impact**: FII/DII flows leading stock moves, sector ETF lead-lag
- [ ] **Options-implied signals**: Put/call ratio, unusual options activity, IV skew
- [ ] **Alpha decay management**: Assign half-lives to signals, auto-reduce aging signals

#### 8.4 Frontend Integration
- [ ] **Screener.jsx**: Show signal-fused rankings with conviction tiers
- [ ] **Dashboard.jsx**: "Top Picks" section with highest-conviction signals
- [ ] **StockAnalyzer.jsx**: Signal breakdown showing each layer's contribution
- [ ] **New page — Signal Dashboard**: Real-time signal generation monitor

**Deliverables**: Unified ranking system producing daily stock picks with transparent reasoning.

---

### PHASE 9: Real-Time Infrastructure & Production Hardening
**Priority**: MEDIUM — For production readiness
**Brain Doc Reference**: Section 22 (System Architecture), Doc 3 (SEBI Compliance)

#### 9.1 Real-Time Data Pipeline
- [ ] **WebSocket live prices**: Real-time price feeds via broker APIs (Zerodha/Angel One)
- [ ] **Event-driven architecture**: Kafka/RabbitMQ for event bus (NewBar, SignalGenerated, RiskAlert)
- [ ] **Stream processing**: Apache Flink for real-time indicator computation as ticks arrive
- [ ] **WebSocket push to frontend**: Real-time updates via existing websocket_manager.py

#### 9.2 Production Infrastructure
- [ ] **Docker Compose**: Full stack containerization (already have Dockerfile)
- [ ] **API rate limiting**: Enhance existing rate_limiter.py for production
- [ ] **Error handling**: Graceful degradation when data sources fail
- [ ] **Monitoring**: Prometheus + Grafana for system health, latency, error rates
- [ ] **Logging**: Structured logging for audit trail
- [ ] **Backup strategy**: Automated database backups

#### 9.3 SEBI Compliance (Doc 3, Sec G)
- [ ] **Audit trail**: Full log of all algorithmic decisions
- [ ] **Kill switch**: Emergency shutdown capability
- [ ] **Order rate monitoring**: Track if approaching 10 orders/sec threshold
- [ ] **Algo identification**: Tag system for all orders
- [ ] **Infrastructure hosting**: Note SEBI 2025 requirement for broker-hosted infrastructure

#### 9.4 Frontend Integration
- [ ] **DataPipeline.jsx**: Real pipeline monitoring with live status
- [ ] **DatabaseDashboard.jsx**: Real database health metrics
- [ ] **System status bar**: Show connection status, data freshness across all pages

**Deliverables**: Production-ready infrastructure with SEBI compliance awareness.

---

### PHASE 10: Advanced & Differentiation Features
**Priority**: LOW-MEDIUM — Long-term competitive advantage
**Brain Doc Reference**: Sections 6, 7, 8, 14 (Emerging Architectures, Bleeding-Edge)

#### 10.1 Advanced Models (Future)
- [ ] **DRL Portfolio Agent**: PPO/TD3 for reinforcement learning-based portfolio management
- [ ] **GNN (Graph Neural Network)**: Model inter-stock relationships, supply chain dependencies
- [ ] **Foundation model fine-tuning**: Chronos/TimeGPT fine-tuned on Indian market data
- [ ] **Diffusion models**: Probabilistic future scenario generation for risk assessment

#### 10.2 Alternative Data (Start Simple)
- [ ] **Web traffic tracking**: App/website traffic for consumer tech/SaaS companies
- [ ] **Job posting trends**: Leading indicator of business momentum (IT/Tech sector)
- [ ] **Insider transaction scoring**: Promoter buying/selling as signal
- [ ] **FII/DII flow momentum**: Track institutional money flows as alpha signal

#### 10.3 Explainability (XAI)
- [ ] **SHAP integration**: Feature importance for every prediction
- [ ] **LIME**: Local explanations for individual stock predictions
- [ ] **Attention visualization**: TFT attention weights showing what drove the forecast
- [ ] **Natural language explanations**: LLM translates model output to plain English

#### 10.4 Knowledge Graph (Doc 2)
- [ ] **Indian market KG**: Company-supplier-customer-sector-macro relationships
- [ ] **Cascading impact prediction**: If TCS reports bad results → predict impact on IT sector
- [ ] **Supply chain mapping**: Track upstream/downstream dependencies

#### 10.5 Frontend Integration
- [ ] **StockAnalyzer.jsx**: XAI tab showing "Why this prediction?"
- [ ] **New page — Knowledge Graph**: Visual interactive graph of stock relationships
- [ ] **New page — Scenario Analysis**: What-if scenarios using diffusion models

**Deliverables**: Cutting-edge features for competitive differentiation.

---

## Recommended Build Order (Critical Path)

```
Phase 1 (Data) ──────────────────────────────────────────────────────────►
    │
    ├──► Phase 2 (Indicators & Features) ─────────────────────────────────►
    │        │
    │        ├──► Phase 3 (Scoring & Forensics) ──────────────────────────►
    │        │        │
    │        │        ├──► Phase 4 (Sentiment) ───────────────────────────►
    │        │        │        │
    │        │        │        ├──► Phase 5 (ML Models) ──────────────────►
    │        │        │        │        │
    │        │        │        │        ├──► Phase 6 (Risk) ──────────────►
    │        │        │        │        │        │
    │        │        │        │        │        ├──► Phase 7 (Portfolio) ─►
    │        │        │        │        │        │        │
    │        │        │        │        │        │        └──► Phase 8 ────►
    │        │        │        │        │        │                 │
    │        │        │        │        │        │                 └─► P9/10
    │        │        │        │        │        │
Phase 9 (Infrastructure) can start in parallel ──────────────────────────►
```

## Success Metrics (Doc 3, Sec J.3)

| Metric | Target |
|--------|--------|
| Prediction accuracy (directional) | >70% |
| Sharpe ratio (deployed strategies) | >1.5 |
| Maximum drawdown (annual) | <20% |
| System uptime (market hours) | >99.9% |
| Order latency (end-to-end) | <100ms |
| Walk-Forward Efficiency (WFE) | >50% |

---

## Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Frontend | React, Radix UI, Tailwind CSS, Recharts, shadcn/ui |
| Backend | FastAPI (Python), WebSocket |
| Databases | PostgreSQL/TimescaleDB, MongoDB (Motor), Redis |
| ML/DL | PyTorch, scikit-learn, XGBoost/LightGBM, Hugging Face |
| Data | pandas, NumPy, Pandas-TA, yfinance |
| LLM | FinBERT, Llama3 (via API), RAG pipeline |
| Infrastructure | Docker, Prometheus + Grafana, MLflow |
| Streaming | Kafka/RabbitMQ (future), Apache Flink (future) |
| Backtesting | VectorBT, custom engine |
