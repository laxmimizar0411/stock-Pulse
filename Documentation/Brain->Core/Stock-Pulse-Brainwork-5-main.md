# Stock Pulse Brain: complete intelligence system architecture

**Stock Pulse Brain is the central nervous system of an AI-powered Indian stock market platform that fuses machine learning, quantitative finance, LLM reasoning, and real-time streaming to generate actionable trading intelligence across NSE and BSE.** This document specifies every module, data flow, model, and technology choice required to build a production-grade system capable of continuous learning, risk-aware decision-making, and scalable signal delivery. The architecture follows a polyglot microservices design with Rust on the hot path, Python for ML/research, Apache Kafka as the event backbone, and Kubernetes on AWS Mumbai for deployment — targeting **50–100ms end-to-end latency** from market tick to execution signal.

---

## 1. System architecture: event-driven microservices for quantitative intelligence

Stock Pulse Brain adopts an **event-driven, polyglot microservices architecture** inspired by NautilusTrader (Rust core + Python API) and QuantConnect LEAN (modular event-driven design). Every state change flows as an immutable event through Apache Kafka, enabling full audit trails, replay capability, and decoupled scaling of individual services.

### Core modules and responsibilities

The system comprises seven primary services, each owning a single domain:

**Data Ingestion Service (Rust + Go)** connects to NSE/BSE via broker WebSocket APIs (Zerodha Kite, Angel One SmartAPI, DhanHQ), normalizes tick data into a canonical Protobuf schema, handles reconnections with exponential backoff, and publishes to Kafka topics (`raw-ticks`, `normalized-ohlcv`, `order-book-updates`). Rust's `tokio` async runtime delivers **<5ms ingestion latency** with zero garbage collection pauses.

**Feature Engine (Apache Flink + Feast)** consumes raw ticks and computes real-time features — VWAP, RSI, MACD, Bollinger Bands, rolling volatility — using Flink's stateful stream processing with exactly-once semantics. Computed features are written to **Redis** (online store, sub-millisecond serving) and **PostgreSQL** (offline store for training) via Feast's feature registry. Features are versioned and point-in-time correct to prevent data leakage.

**Signal Generation Engine (Flink CEP + Python)** uses Apache Flink's Complex Event Processing library to detect trading patterns — double bottoms, volume breakouts, support/resistance breaks — via `MATCH_RECOGNIZE` SQL patterns. It merges rule-based signals with ML model outputs into unified Buy/Sell/Hold signals with confidence scores.

**Model Serving Service (Python + ONNX Runtime)** serves ML models for price prediction, volatility forecasting, and alpha factor generation. Models trained in PyTorch are exported to ONNX format for production inference. MLflow manages model versioning and experiment tracking. Non-latency-critical models use Python-native serving; latency-sensitive inference uses ONNX Runtime achieving **5–20ms per prediction**.

**Risk Management Service (Rust)** sits on the critical path — every order passes through pre-trade risk checks completing in **<1ms**: position limits, daily P&L caps, margin verification, circuit breaker awareness, sector exposure limits, and VaR/drawdown monitoring. SEBI margin requirements and circuit breaker rules are encoded as configurable policies.

**Execution Engine (Rust + Go)** routes validated orders to broker REST APIs, manages the full order lifecycle (placed → confirmed → partial fill → filled/rejected), implements smart order routing, and handles slippage management. Broker connections are abstracted behind an adapter pattern so Zerodha, Angel One, or DhanHQ can be swapped without changing core logic.

**Monitoring & Observability Layer** uses Prometheus + Grafana for metrics, Loki for centralized logging, Jaeger/OpenTelemetry for distributed tracing, and custom dashboards for P&L tracking, model drift detection, and system health alerting.

### Technology stack and integration points

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Hot-path execution | **Rust** (tokio, axum) | ~120ns order execution, no GC pauses, memory safety |
| Infrastructure services | **Go** | Goroutine concurrency, fast compilation, API adapters |
| ML/Research | **Python 3.12+** | Unmatched ML ecosystem (PyTorch, pandas, scikit-learn) |
| Event backbone | **Apache Kafka** (KRaft mode, no ZooKeeper) | De facto financial streaming standard, millisecond latency |
| Stream processing | **Apache Flink 1.19+** | CEP library, exactly-once semantics, SQL + DataStream API |
| Feature store | **Feast + Redis 7.x** | Open-source, sub-ms online serving, pluggable backends |
| Inter-service sync calls | **gRPC** with Protobuf | Binary efficiency, type safety, streaming support |
| API gateway | **Kong** or **Envoy Proxy** | Rate limiting, authentication, routing |
| Container orchestration | **Kubernetes** (EKS on AWS ap-south-1 Mumbai) | Proximity to NSE/BSE data centers, managed scaling |
| CI/CD | **GitHub Actions + ArgoCD** | GitOps deployment with canary/blue-green strategies |

### Data flow: market hours vs post-market

During **live trading (9:15 AM – 3:30 PM IST)**, tick data flows through the full streaming pipeline: WebSocket → Rust handler → Kafka → Flink (parallel feature computation + CEP signal detection) → Model Serving → Signal Aggregator → Risk Manager → Execution Engine. Target end-to-end latency: **50–100ms**.

During **post-market (3:30 PM onwards)**, Apache Airflow orchestrates batch pipelines: EOD bhavcopy download → TimescaleDB/QuestDB, batch feature computation → Feast offline store, model retraining → MLflow, backtesting → VectorBT, and report generation. A **pre-market warm-up phase (7:00–9:15 AM)** loads latest sentiment, verifies broker API connectivity, warms Redis caches, and runs model inference for the day's universe.

---

## 2. Intelligence layer: multi-signal fusion with AI-driven reasoning

The intelligence layer is the decision-making brain that synthesizes technical, fundamental, sentiment, and macroeconomic signals into unified trading intelligence. It follows a **multi-signal fusion architecture** where each signal source produces a normalized score [-1, +1] with an associated confidence [0, 1], and a stacked ensemble meta-model combines them.

### Prediction engine architecture

The prediction engine operates as a pipeline: individual signal generators (technical, fundamental, sentiment, macro) emit scored signals → a feature vector is constructed → an ensemble ML model (XGBoost meta-learner over LSTM, TFT, and gradient boosting base models) produces a unified prediction with direction, magnitude, and confidence. **Dynamic weighting** adjusts signal importance contextually: during earnings season, sentiment weight increases; during RBI policy announcements, macro weight increases; during trending markets detected by the HMM regime filter, technical weight dominates.

### Signal generation and confidence scoring

Every signal passes through a confidence scoring formula that integrates **technical alignment** (30% weight — do RSI, MACD, moving averages agree?), **sentiment strength** (25% — FinBERT score consistency across sources), **fundamental support** (20% — valuation relative to sector), **volume confirmation** (15% — above-average volume confirming the move), and **macro headwinds** (10% — opposing macro factors as a penalty). The output is sigmoid-transformed to a 0–100% confidence score. Signals below **40% are suppressed**, 40–60% go to watchlist, 60–80% are actionable with moderate position sizing, and **above 80% trigger high-conviction allocations**.

### Macro and micro economic analysis for Indian markets

India-specific macro factors are modeled as regime inputs: **RBI repo rate** changes directly impact banking and rate-sensitive sectors; **crude oil prices** affect OMCs, airlines, and paints (India imports ~85% of crude); **INR/USD movements** benefit IT exporters on depreciation but hurt importers; **FII/DII flows** are the single most important liquidity driver (FIIs can move markets 1–3% on heavy flow days); **monsoon forecasts** from IMD impact agriculture, FMCG, and rural economy stocks; **election cycles** drive infrastructure and defense spending narratives. Each macro factor is mapped to specific sector impact coefficients, updated monthly.

### Sector rotation and earnings surprise detection

The system tracks relative strength of all NIFTY sector indices (IT, Banking, Pharma, FMCG, Auto, Metal, Realty, Energy) and identifies money flow rotation using FII/DII sector-wise data. Seasonal patterns are encoded: IT sector strength in Q1 (US fiscal year-end deals), banking strength during credit growth cycles, FMCG uplift during festive seasons. Earnings surprise detection compares management guidance language (analyzed by the LLM agent) against consensus estimates, with post-earnings drift prediction based on surprise magnitude and management tone divergence between prepared remarks and Q&A sections.

---

## 3. Data layer: Indian market data infrastructure and storage architecture

### Indian market data providers

The Indian market data ecosystem offers a surprisingly rich set of API-accessible data sources, many of them free:

**Angel One SmartAPI** is the recommended primary free data source — it provides real-time OHLCV, market depth (top 5 orders), open interest, historical candles across NSE/BSE/MCX/CDS segments, supports **20 orders/second** and up to 1,000 WebSocket token subscriptions per session, all at zero cost. **Zerodha Kite Connect** at ₹2,000/month is the production-grade choice with the largest user base (16M+ clients), offering up to **10 years of intraday historical data**, full WebSocket tick streaming in three modes (LTP, Quote, Full with market depth), and mature Python SDK (`pykiteconnect`). **Upstox, Dhan, and FYERS APIs** are free alternatives with varying feature completeness. For exchange-licensed institutional-grade data, **TrueData** and **Global Datafeeds** provide authorized NSE/MCX/BSE real-time feeds with option Greeks, FIX Protocol support, and 60,000+ symbols.

For fundamental data, **Screener.in** (₹4,999/year) provides 10-year financial statements with custom query capabilities; **Trendlyne** (₹5,900/year) offers DVM scores, 1,400+ screener parameters, FII/DII tracking, and insider activity; **yfinance** (free) supplements with `RELIANCE.NS` / `RELIANCE.BO` ticker format access to OHLCV, fundamentals, and financials. The unofficial Python library **jugaad_data** pulls directly from NSE website APIs for more accurate Indian stock data than yfinance.

NSE's official **CM-UDiFF bhavcopy** (new format since July 2024) provides daily EOD data including OHLC, volume, delivered quantity, and 52-week highs/lows in CSV/ZIP format. FII/DII daily institutional investment data is published on the NSE website and accessible via `nsetools` and `jugaad_data` Python libraries.

### Storage architecture

| Database | Use Case | Technology Choice | Rationale |
|----------|----------|-------------------|-----------|
| Time-series (ticks, OHLCV) | All market data | **QuestDB** | 6–13x faster ingestion than TimescaleDB, native ASOF JOIN support (critical for point-in-time financial lookups), SQL-compatible |
| Relational (fundamentals, metadata) | Company data, orders, positions | **PostgreSQL 16+** | JSONB support, rich ecosystem, excellent for complex joins |
| Cache (hot data) | Real-time LTP, feature serving | **Redis 7.x** | Sub-millisecond latency, TTL-based expiry (1–5s during market hours) |
| Document store (unstructured) | News articles, sentiment results, raw API responses | **MongoDB** | Flexible schema for varied data sources |
| Data lake (raw archival) | Bhavcopy CSVs, historical archives | **MinIO** (S3-compatible) | Self-hosted, cost-effective, Apache Parquet format for analytics |
| Analytics (backtesting) | Cross-sectional analysis, large historical queries | **ClickHouse** or **DuckDB + Parquet** | Columnar OLAP for analytical workloads |

### Data pipeline design

The system implements a **Lambda architecture** with parallel batch and speed layers:

The **real-time pipeline** runs during market hours: broker WebSocket feeds → Apache Kafka (topics partitioned by symbol for ordering) → Flink streaming jobs (feature computation, CEP signal detection, anomaly detection) → QuestDB persistence + Redis hot cache. Kafka is configured with **replication factor 3** across availability zones, lz4 compression for latency/throughput balance, and `acks=all` for order topics (durability) vs `acks=1` for tick data (speed).

The **batch pipeline** runs post-market via Apache Airflow DAGs: `dag_daily_bhavcopy` downloads CM and F&O bhavcopy at 4:00 PM; `dag_fii_dii` scrapes institutional flow data; `dag_fundamentals` refreshes quarterly results from Screener.in/Trendlyne during earnings season; `dag_corporate_actions` tracks dividends, splits, and bonuses; `dag_macro_data` pulls RBI rates, CPI, and GDP from data.gov.in; and `dag_data_quality` validates everything with Great Expectations rules.

### Indian market data considerations

Critical nuances the data layer must handle: **circuit breakers** (2%, 5%, 10%, 20% bands for individual stocks; stocks with F&O derivatives have no individual circuits); **T+1 settlement** since January 2023 requiring same-day holdings reconciliation; **pre-open session** (9:00–9:08 AM order collection, 9:08–9:15 AM matching) with equilibrium price capture; **bhavcopy format migration** to CM-UDiFF (code must handle both old and new formats for historical data); **SEBI's mandatory static IP requirement** for API-based algo trading effective April 2026; and approximately **14–15 market holidays per year** plus the special Diwali Muhurat trading session (1 hour). Data quality checks enforce OHLC relationship integrity (Low ≤ Open, Close ≤ High), volume > 0 for non-circuit stocks, price within circuit limits, and cross-source reconciliation between yfinance and NSE bhavcopy with flagging on >0.5% deviation.

---

## 4. AI/ML model ecosystem: from classical statistics to foundation models

### Model taxonomy by prediction task

The model ecosystem spans five tiers of increasing complexity, each serving distinct prediction horizons and tasks:

**Tier 1 — Statistical baselines** include ARIMA/SARIMA for stationary series benchmarking and the GARCH family (GARCH, EGARCH, GJR-GARCH) as the gold standard for volatility forecasting and options pricing. These are computationally cheap, interpretable, and essential for comparison against more complex models.

**Tier 2 — Gradient boosting machines** (XGBoost, LightGBM, CatBoost) are the workhorses for tabular feature-based directional prediction. They excel at ingesting engineered feature sets (technical indicators, fundamental ratios, macro variables) and producing directional classifications with built-in feature importance. Multiple Indian market studies confirm their strong performance on NSE/BSE stocks.

**Tier 3 — Deep learning architectures** serve medium-term forecasting. **Temporal Fusion Transformers (TFT)** are the recommended primary model — they handle multi-horizon forecasting with static and time-varying covariates, provide built-in interpretability through attention mechanisms, and produce probabilistic quantile forecasts. Research reports **MAPE of 1–1.3%** on daily/weekly stock forecasts. **N-BEATS** offers pure deep learning with interpretable trend/seasonality decomposition (validated by Diebold-Mariano tests against ARIMA, LSTM, GRU on S&P 500). **N-HiTS** extends this with hierarchical interpolation optimized for long-horizon forecasts. LSTM with attention mechanisms remains strong for Indian market prediction, with studies showing high R² on NIFTY 50 daily close predictions.

**Tier 4 — Reinforcement learning** uses **PPO (Proximal Policy Optimization)** as the primary algorithm for portfolio management, achieving **Sharpe ratio of 2.06** versus 0.92 for mean-variance optimization in comparative studies including Indian Sensex. The **FinRL** open-source framework provides pre-built environments for PPO, A2C, SAC, and TD3 with data preprocessing pipelines. A2C serves as a lighter alternative; TD3 handles high-dimensional portfolios.

**Tier 5 — Foundation models** represent the 2024–2026 frontier. **Kronos** (Tsinghua University) is the most relevant finance-specific foundation model, pretrained on **12 billion K-line records from 45 global exchanges** with custom OHLCV tokenization — it achieves zero-shot performance competitive with domain-specific models and improves further with fine-tuning. **Google TimesFM 2.5** (200M params, decoder-only, 100B time points pretraining) has been fine-tuned for stock prices with demonstrated Sharpe ratio improvements. **Amazon Chronos** (T5-based, tokenized time series) and **Salesforce Moirai** (multi-variate capable) provide additional zero-shot baselines.

### Recommended model allocation by horizon

| Prediction Horizon | Primary Model | Supporting Models |
|-------------------|---------------|-------------------|
| Intraday (minutes–hours) | LSTM/GRU with attention + HMM regime filter | XGBoost for feature signals |
| Short-term (1–5 days) | **TFT** with technical indicators | N-BEATS univariate baseline, XGBoost direction |
| Medium-term (1–4 weeks) | TFT-GNN hybrid, fine-tuned Kronos/TimesFM | GARCH volatility overlay, HMM regime detection |
| Long-term (1–12 months) | N-HiTS, foundation models zero-shot | Random Forest factor selection, macro indicators |
| Portfolio optimization | **PPO via FinRL** | TD3 for high-dimensional, Mean-CVaR optimization |

### Feature engineering pipeline

Features are organized in five categories: **technical indicators** (RSI, MACD, Bollinger Bands, ATR, OBV, VWAP, Ichimoku, plus fractional differentiation per López de Prado to preserve memory while achieving stationarity); **fundamental features** (P/E, P/B, ROE, ROCE, debt-to-equity, earnings growth, plus India-specific promoter holding % and FII/DII holding changes); **macroeconomic features** (RBI repo rate, INR/USD, crude oil, India VIX, FPI net flows, GDP, CPI, IIP); **market microstructure features** (delivery volume % — a uniquely Indian indicator of genuine buying versus speculation, advance-decline ratio, market breadth); and **cross-sectional features** (sector momentum, relative strength versus NIFTY 50, rolling beta, correlation regime).

Feature selection follows a rigorous pipeline: raw features → log/scaling transforms → correlation filtering (drop |r| > 0.95) → Boruta algorithm for relevant feature identification → LASSO for sparse selection → PCA for dimensionality reduction → final feature set. **Single Feature Importance (SFI)** per López de Prado computes out-of-sample importance to avoid overfitting.

### Validation, training, and deployment

**Walk-forward validation** is the gold standard: train on a rolling/expanding window (e.g., 5 years), test on the subsequent out-of-sample period (e.g., 1 year), roll forward, repeat. This simulates real-world deployment and produces multiple OOS performance estimates. **Combinatorial Purged Cross-Validation (CPCV)** is used for hyperparameter tuning — it generates C(N,k) train/test combinations with purging to prevent data leakage from autocorrelation and embargo periods to exclude observations after test sets. Standard k-fold must never be used for financial data.

The training pipeline runs: Data Ingestion → Feature Engineering → Feature Selection → Walk-Forward Split → Model Training (PyTorch 2.2+) → Hyperparameter Optimization (Optuna 3.x with Bayesian search + pruning) → Ensemble Construction → Backtesting → Deployment via **BentoML** (lightweight Python-native serving) or **Triton Inference Server** (multi-framework, dynamic batching for GPU inference). **MLflow 2.x** manages experiment tracking, model versioning, and the model registry. **Evidently AI** monitors data drift (KL-divergence, PSI) and concept drift in production, with retraining triggers on performance degradation, regime changes detected by HMM, or scheduled cycles (weekly for short-term models, monthly for TFT/N-HiTS, quarterly for foundation model fine-tuning).

---

## 5. Trading intelligence: hybrid strategy engine with rigorous backtesting

### Strategy engine design

The strategy engine uses a **three-layer hybrid architecture**. Layer 1 (rule-based) generates signals from classical technical indicators and fundamental filters. Layer 2 (AI/ML) produces probability-scored signals from deep learning models consuming multi-timeframe features. Layer 3 (signal aggregation) combines all signals through a meta-model or weighted voting system into a unified output: `{ticker, direction, confidence%, target_price, stop_loss, position_size_recommendation, timeframe}`.

Supported strategy types include **momentum** (trend-following via ROC, RSI, MA slopes — best in trending regimes), **mean-reversion** (RSI extremes, Bollinger Band bounces, z-score — best in sideways markets), **pairs trading** (cointegrated pairs via Engle-Granger/Johansen tests — market neutral), **factor-based** (value, momentum, quality, low-volatility factors — long-term systematic), and **statistical arbitrage** (multi-factor PCA residual alpha — diversified). Multi-timeframe analysis uses at least three timeframes: daily for trend direction, 4-hour for entry timing, 1-hour for precise execution. Disagreement across timeframes proportionally reduces the confidence score.

### Backtesting framework

**VectorBT Pro** is the primary backtesting engine — it processes **1 million simulated orders in ~70–100ms** using vectorized NumPy operations and Numba JIT compilation, enabling parameter optimization across thousands of combinations in minutes rather than hours. It can backtest 1,000 stocks × 10 years in under one minute. **Backtrader** serves as the secondary validation engine for execution realism and Indian broker integration (adapters exist for Zerodha Kite Connect and Finvasia APIs). **QuantStats** generates comprehensive tearsheets with Sharpe, Sortino, Calmar, Information ratio, Omega ratio, monthly returns heatmaps, and drawdown analysis.

Walk-forward optimization divides historical data into sequential in-sample (12-month) and out-of-sample (3-month) windows, rolling forward to ensure parameter robustness across market regimes. **Transaction costs are modeled precisely for Indian markets** — STT (0.1% delivery, 0.025% intraday sell), exchange transaction charges (NSE 0.00307%), GST (18% on brokerage + charges), stamp duty (0.015% buy delivery), SEBI fees (₹10/crore), and DP charges (₹15.34/scrip sell delivery).

---

## 6. Risk management: practical mechanisms approaching zero loss

Achieving "zero loss" is aspirational, but the system implements multiple overlapping defense layers that **practically minimize drawdowns and protect capital** through algorithmic discipline that removes emotional decision-making.

### Stop-loss and capital protection

The recommended approach is a **hybrid ATR-volatility stop** — `Stop = Entry - (ATR(14) × Multiplier)` where the multiplier is 1.5–2x for day trading, 2–3x for swing, and 3–4x for positional. Research shows **2x ATR stops reduce maximum drawdown by 32%** versus fixed percentage stops. ATR naturally widens during volatile periods and tightens during calm periods, adapting to market conditions. A fixed maximum floor (e.g., 5% loss) provides an absolute backstop. Trailing stops lock profits by moving the stop in the favorable direction only, using the Chandelier Exit variant (`Highest_High_Since_Entry - ATR × Multiplier`).

**Capital protection escalation**: if portfolio drawdown exceeds **10%, position sizes are halved**; at **15%, all new entries are halted**; at **20%, all positions are closed** (the "kill switch"). Daily loss is capped at 2–3% of capital. Single-position exposure is capped at 10–15% of portfolio, and sector concentration is limited to 30%.

### Position sizing with fractional Kelly

The Kelly Criterion (`K% = W - (1-W)/R` where W is win probability and R is reward/risk ratio) maximizes long-term growth but is dangerously aggressive in practice — full Kelly can produce **50–70% drawdowns**. Stock Pulse Brain defaults to **Half Kelly (f/2)**, which captures approximately 75% of optimal growth with dramatically reduced drawdown. During high-volatility regimes detected by the HMM, the system automatically switches to **Quarter Kelly (f/4)** for enhanced safety. Position size is further constrained by volatility: `shares = risk_amount / (ATR × multiplier)`, ensuring each position risks at most 1–2% of total capital.

### Portfolio-level risk metrics

**Value at Risk (VaR)** is computed via historical simulation, parametric (variance-covariance), and Monte Carlo methods — "with 95% confidence, the 1-day maximum portfolio loss will not exceed X." **Conditional VaR (CVaR / Expected Shortfall)** averages losses beyond the VaR threshold, capturing tail risk that VaR misses. Monte Carlo simulation generates 10,000+ portfolio paths using bootstrapped returns to assess the probability of drawdown exceeding thresholds and validate strategy robustness.

**Stress testing** runs the portfolio through historical crisis scenarios — the 2008 GFC, COVID March 2020 crash, 2016 demonetization, 2015 China devaluation — and hypothetical scenarios: 20% market drop in 5 days, 50% volatility spike, sudden FII withdrawal of ₹50,000 crore, and interest rate shocks. Indian market-specific risks are explicitly modeled: circuit breaker lockouts (inability to exit illiquid positions), SEBI peak margin requirements, and FII flow reversals.

---

## 7. Prediction and forecasting: regime-aware multi-horizon intelligence

### Market regime detection

A **3-state Gaussian Hidden Markov Model** classifies market conditions into bull, bear, and sideways regimes. The HMM is trained on a multi-feature input vector: daily returns, rolling annualized volatility, India VIX, FII/FPI net flow momentum, and INR/USD rate of change. The model outputs posterior probabilities for each regime plus a state transition matrix that informs regime persistence expectations.

Regime detection serves three critical functions: **(1) trading filter** — disallowing aggressive entries during high-volatility bear regimes; **(2) model selector** — routing predictions to specialist models trained on regime-specific data; **(3) feature input** — feeding regime probabilities as features to downstream ensemble models. Complementary approaches include K-Means/GMM clustering for simpler regime identification, Regime-Switching GARCH (MS-GARCH) for volatility-specific regime detection, and CUSUM/PELT change-point detection for structural breaks.

### Multi-horizon forecasting strategy

Short-term predictions (1–5 days) emphasize technical signals processed by the Temporal Fusion Transformer, which achieves **<1% MAPE on daily forecasts** with built-in interpretability through temporal attention weights. Medium-term forecasts (1–4 weeks) incorporate fundamental data and cross-sectional features through the TFT-GNN hybrid that models inter-stock relationships — particularly valuable for NIFTY 50 constituents where sector correlations drive returns. Long-term predictions (1–12 months) rely on N-HiTS's hierarchical interpolation with heavy weighting of fundamental analysis features and macroeconomic indicators (RBI rates, crude oil, GDP trajectory).

**Volatility forecasting** uses a GARCH(1,1) model enhanced by **NBEATSx** (N-BEATS with exogenous variables like India VIX), which has been shown to produce statistically more precise volatility forecasts than standard GARCH, LSTM, and TCN models. Volatility forecasts directly feed the ATR-based stop-loss system and options pricing modules.

### Ensemble and meta-labeling

The final prediction combines multiple model outputs through **regime-conditional ensembling**: specialist models trained per regime are selected based on the current HMM-detected state, then blended via a stacked XGBoost meta-learner. **Meta-labeling** (per López de Prado) adds a critical second layer: the primary model predicts direction (side), while a secondary model predicts the probability that the primary model is correct (size/confidence), significantly improving F1 scores and reducing false positive trades.

---

## 8. LLM and AI agents: reasoning, sentiment, and automated research

### LLM model selection strategy

A **tiered routing architecture** optimizes cost and capability: **Tier 1 (deep reasoning)** uses GPT-5/Claude Opus for complex investment analysis and report generation — Claude Opus achieves **87.82% on financial reasoning benchmarks** with 5x lower token consumption than GPT-5, making it the best accuracy-per-token model. **Tier 2 (quick-thinking)** uses GPT-4.1 mini/nano and Gemini Flash for data extraction, summarization, and classification at low cost. **Tier 3 (local/open-source)** runs FinGPT (fine-tuned Llama, achieving **F1 up to 87.62% on sentiment, 95.50% on headline classification**), FinBERT, and Mistral 7B locally on GPU servers for privacy-sensitive operations and cost optimization. A fine-tuned Indian market FinBERT variant (`kdave/FineTuned_Finbert` on HuggingFace) exists specifically for Indian financial news.

Semantic caching stores LLM responses for repeated queries (e.g., same company analysis within a day), and batch processing aggregates non-urgent analyses for off-peak inference. Estimated monthly LLM cost: **$2,000–5,000** for a hybrid local+API setup serving ~1,500 NSE/BSE stocks.

### Multi-agent system architecture

Inspired by the **TradingAgents framework** (UCLA/MIT, 2024–2025) which demonstrated **26.62% cumulative returns versus -5.23% buy-and-hold**, the system deploys specialized AI agents orchestrated by **LangGraph** (production-grade graph-based state machine, used at LinkedIn and Uber) with **CrewAI** for simpler declarative workflows.

The agent team comprises four analyst agents running concurrently — Fundamental Analyst (P/E analysis, revenue growth, ROCE), Technical Analyst (pattern detection, support/resistance, indicator scoring), Sentiment Analyst (FinBERT pipeline over Economic Times, Moneycontrol, LiveMint, Twitter/X, r/IndianStreetBets), and Macro Analyst (RBI policy tracking, FII/DII flows, crude oil, monsoon forecasts). Their outputs feed into a **dialectical research phase** where Bull and Bear researcher agents argue opposing positions before a Research Synthesizer produces a consensus view with confidence intervals. Finally, a Trader Agent synthesizes all research into actionable signals, subject to veto or modification by a Risk Management Agent. Support agents handle report generation (daily morning brief at 8:30 AM, market wrap at 4:30 PM), real-time alerting, and RAG-based knowledge retrieval.

### Financial NLP pipeline

The NLP pipeline processes text through: language detection → Hindi-to-English translation (IndicTrans2/AI4Bharat) → text cleaning → sentence segmentation → financial NER (SpaCy with custom entity types: COMPANY, TICKER, SECTOR, FINANCIAL_METRIC, REGULATORY_BODY) → **multi-model sentiment ensemble** (0.5×FinBERT + 0.2×VADER + 0.3×LLM) → event extraction → entity-sentiment mapping → signal generation. Research confirms FinBERT consistently outperforms VADER for financial text, as VADER misinterprets terms like "depreciation" and "shortfall."

Earnings call analysis separates management discussion from Q&A sections (which show divergent sentiment patterns), applies FinBERT scoring per section, and uses LLM summarization for key insight extraction. Management tone divergence between prepared remarks and unscripted Q&A is a strong signal for earnings quality assessment.

### Explainability with SHAP and natural language

**SHAP (SHapley Additive exPlanations)** provides game-theory-based feature attribution for every prediction — quantifying exactly how much each feature (RSI, FinBERT sentiment, P/E ratio) contributed to the signal. SHAP values are generated for all XGBoost/ensemble predictions and visualized as waterfall charts in the dashboard. **LIME** supplements with lightweight local surrogate explanations for on-demand queries. The agent architecture adds a unique explainability layer: every decision includes the full reasoning chain from each agent, plus the bull/bear debate transcript, producing natural language explanations like: "BUY signal driven by FinBERT sentiment +0.72 from 15 articles, RSI at 35 (oversold), FII net buying ₹500Cr in sector, P/E below 5-year median."

### RAG knowledge base

A **Qdrant** vector database stores chunked financial knowledge (512-token chunks, 50-token overlap) from company filings, SEBI circulars, RBI policies, brokerage research, and historical prediction outcomes. Hybrid search combines BM25 full-text retrieval with semantic vector search using OpenAI text-embedding-3-small, with **Cohere rerank** improving RAG correctness from 33.5% to 49.0% in financial Q&A benchmarks. Agentic RAG enables iterative retrieval for complex multi-hop questions about company fundamentals, regulatory changes, and historical market events.

---

## 9. Real-time decision engine: sub-second market response

### Event-driven streaming architecture

The real-time engine follows **event sourcing** (every state change is an immutable Kafka event), **CQRS** (separate read/write paths for different latency requirements), and **schema governance** (Confluent Schema Registry with Avro/Protobuf schemas for evolution without breaking consumers).

**Kafka configuration** targets the Indian market's ~2,000 actively traded NSE symbols: 5+ brokers in KRaft mode (no ZooKeeper), replication factor 3 across availability zones, topics partitioned by stock symbol for per-symbol ordering, lz4 compression, 1–5ms `linger.ms` for latency/throughput balance. Retention: 7 days for raw ticks (then archive to S3/Parquet), 30 days for signals, indefinite for orders (SEBI compliance). Idempotency keys handle at-least-once delivery without duplicates.

### Flink streaming jobs

Four parallel Flink jobs power the real-time intelligence: **Feature Computation** consumes raw ticks and computes windowed aggregations (1min, 5min, 15min, 1hr OHLCV) plus streaming technical indicators, publishing to Redis and Kafka; **CEP Signal Detection** uses Flink's Pattern API and `MATCH_RECOGNIZE` SQL to detect chart patterns (double bottoms, volume breakouts, head-and-shoulders) in real-time; **Anomaly Detection** monitors order flow, volume, and price movements for unusual activity; and **Feature Freshness Monitor** tracks computation latency and alerts on staleness (target: <30 seconds for 5-minute features).

### Latency budget

| Stage | Target Latency | Technology |
|-------|---------------|------------|
| WebSocket ingestion → Kafka | <5ms | Rust + tokio |
| Kafka produce + consume | 5–15ms | Kafka KRaft, lz4, acks=1 |
| Feature computation | 10–30ms | Flink stateful processing |
| Feature serving from Redis | <1ms | Redis 7.x in-memory |
| ML model inference | 5–20ms | ONNX Runtime / TorchServe |
| Signal aggregation + risk checks | 2–5ms | Rust pre-trade engine |
| Order submission to broker | 10–30ms | REST API to Kite/SmartAPI |
| **Total end-to-end** | **~50–100ms** | — |

This latency is more than sufficient for Indian retail algorithmic trading. For further optimization, the system can employ binary serialization (Protobuf/Flatbuffers instead of JSON internally), CPU pinning for latency-critical threads, pre-allocated memory pools on the hot path, and connection pooling for broker API calls.

### Trading-hours lifecycle management

The system auto-scales with market hours via Kubernetes CronHPA: scale up at 9:00 AM IST for pre-market warm-up, full capacity during 9:15 AM–3:30 PM continuous trading, scale down at 4:00 PM. The pre-open session (9:00–9:08 AM) is handled specially — the system captures equilibrium price data and adjusts opening signals accordingly. The post-close session (3:40–4:00 PM) captures final settlement prices. Overnight, health checks, infrastructure maintenance, and next-day preparation run on minimal resources.

---

## 10. Output layer: signals, alerts, and actionable dashboards

### Signal output specification

Every signal is emitted as a structured JSON payload containing: `signal_id`, `timestamp` (IST), `ticker`, `company`, `sector`, `direction` (BUY/SELL/HOLD), `confidence` (0–100%), `timeframe` (intraday/swing/positional/investment), `entry_price`, `target_price`, `stop_loss`, `risk_reward_ratio`, `risk_level` (LOW/MEDIUM/HIGH), `contributing_factors` (technical score + weight, fundamental score + weight, sentiment score + weight, macro score + weight, volume score + weight), `natural_language_explanation`, and `shap_features` (top feature attributions with SHAP values). Signals are delivered via REST API (`GET /api/v1/signals?sector=banking&confidence_min=70`), WebSocket stream (`WS /api/v1/stream/signals`), and push notifications.

### Alert and notification system

Alerts are tiered by priority: **P1 (critical)** — high-confidence signals >80%, earnings surprises >5%, portfolio VaR breach, stop-loss triggered — delivered via push notification + SMS + email within **<10 seconds**; **P2 (important)** — price breakouts, sentiment shifts >30 points in 4 hours, macro events — delivered via push notification + dashboard; **P3 (informational)** — watchlist movements, sector rotation signals — dashboard only. Delivery infrastructure: Firebase Cloud Messaging (mobile push), AWS SNS (SMS), SendGrid (email), WebSocket (real-time dashboard).

### Dashboard architecture

The frontend uses **React/Next.js + TradingView Lightweight Charts + D3.js** with Tailwind CSS. Seven primary panels provide comprehensive market intelligence: a Market Overview panel (NIFTY/SENSEX with sentiment overlay, sector heatmap, FII/DII flows, India VIX gauge), a Signal Board (active signals sorted by confidence with traffic-light color coding), Stock Deep Dive pages (per-stock technical chart, sentiment timeline, fundamental metrics, SHAP waterfall chart), Portfolio Tracker (positions, P&L, risk metrics, stop-loss proximity), Sentiment Dashboard (market-wide sentiment gauge, sector breakdown, social media buzz, trending tickers), Agent Activity Log (real-time feed of agent analyses and debate summaries), and Report Center (auto-generated daily/weekly PDFs plus interactive reports).

### Automated report generation

The Report Generation Agent produces four recurring reports: a **Morning Brief** (8:30 AM IST) with market outlook, key signals, macro summary, and earnings calendar; a **Market Wrap** (4:30 PM IST) with day's performance, signal accuracy review, and after-hours developments; a **Weekly Analysis** with sector rotation summary, top performers, and portfolio recommendations; and **Quarterly Earnings Reports** with company-specific deep dives during earnings season. All reports are generated by Claude/GPT with RAG context and delivered as both PDF and interactive web format.

---

## Connecting it all: implementation roadmap and production considerations

### SEBI regulatory compliance

As of October 2025, SEBI requires: **static IP** for all API-based algo trading (configure elastic IP on cloud infrastructure); **algo registration** with exchanges as "White Box" (logic disclosed) or "Black Box" (performance-audited); strategies under **10 orders per second** classified as "Client Direct API" with simplified registration; complete **order audit trails** with timestamps (Kafka's immutable log satisfies this natively); and if offering the platform as a service, registration as an Algo Provider with exchanges.

### Cost structure

The system operates at three budget tiers: **Minimum viable** (₹0/month data + open-source infrastructure) using Angel One SmartAPI + yfinance + self-hosted stack; **Professional** (~₹5,000–10,000/month) using Kite Connect + TrueData + cloud infrastructure; **Enterprise** (~₹2–5 lakh/month) including multiple broker feeds, institutional data, multi-GPU inference, and full cloud infrastructure with LLM API costs of $2,000–5,000/month.

### Phased implementation

**Phase 1 (Months 1–3)**: Data layer + Indian market data ingestion + basic feature engineering + PostgreSQL/QuestDB/Redis storage + Kafka event bus + ATR-based stop-loss + HRP portfolio optimization using PyPortfolioOpt.

**Phase 2 (Months 4–6)**: AI/ML model training (TFT, XGBoost, LSTM) + walk-forward validation + VectorBT backtesting engine + signal generation with confidence scoring + MLflow experiment tracking + basic dashboard.

**Phase 3 (Months 7–9)**: LLM agent system (LangGraph) + FinBERT sentiment pipeline + multi-agent research team + Black-Litterman optimization with AI views + HMM regime detection + SHAP explainability + comprehensive alerting.

**Phase 4 (Months 10–12)**: Foundation model fine-tuning (Kronos/TimesFM) + RL portfolio optimization (PPO via FinRL) + Monte Carlo stress testing + full dashboard with TradingView charts + live trading integration + SEBI compliance + continuous learning pipelines.

### Continuous improvement loop

The system improves through a closed feedback loop: every signal's predicted outcome is compared against actual results, producing a **hit rate** and **information coefficient** that are tracked on rolling windows. Model drift is monitored via Evidently AI, triggering retraining when performance degrades below thresholds. The HMM regime detector adapts strategy selection to current market conditions. Agent reasoning chains are logged and periodically reviewed for quality improvement. A/B testing of new models runs in shadow mode (paper trading) for minimum 3 months before capital allocation, with gradual rollout from 10% to full allocation based on rolling Sharpe ratio comparison.

This architecture delivers a system that is modular (every component is independently deployable and replaceable), scalable (Kafka + Kubernetes handle growth from hundreds to thousands of stocks), resilient (multi-layer risk management from position level to portfolio level), explainable (SHAP + agent reasoning chains), and continuously improving — converging toward the aspiration of maximum profitability with minimal risk through algorithmic discipline, adaptive intelligence, and relentless data-driven learning.