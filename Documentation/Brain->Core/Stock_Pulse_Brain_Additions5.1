# Stock Pulse Brain — Additions & Supplementary Architecture

> **This document covers areas NOT addressed in the main architecture document. Read alongside the primary "Stock Pulse Brain: Complete Intelligence System Architecture" for the full picture.**

---

## A. Options & Derivatives Intelligence Module

India's F&O market is one of the largest globally by contract volume — NIFTY and BANKNIFTY options alone generate billions in daily turnover. Ignoring derivatives means ignoring half the market's intelligence.

### Options Analytics Engine

The system must compute and serve **real-time Greeks** (Delta, Gamma, Theta, Vega, Rho) for all active NSE F&O contracts (~200+ stocks + index options). The Black-Scholes model serves as the baseline, but Indian options require the **Black-76 model** for European-style index options (NIFTY, BANKNIFTY, FINNIFTY) and adjustments for dividend expectations on stock options. Implied Volatility (IV) is extracted via Newton-Raphson iteration from live option prices and organized into a **volatility surface** (strike × expiry grid) updated every tick.

### Options-Specific Signals

**Put-Call Ratio (PCR)** at both aggregate and strike-level granularity — PCR > 1.2 is generally bullish (put writers confident), PCR < 0.7 is bearish. **Max Pain** computation identifies the strike where option writers lose the least, serving as an expiry-day price magnet. **Open Interest (OI) analysis** tracks OI buildup and unwinding at key strikes — significant OI at a strike acts as support/resistance. **IV Rank and IV Percentile** contextualize current IV against its historical range (52-week) to identify cheap/expensive options for strategy selection. **Unusual Options Activity (UOA)** detection flags contracts with volume > 3× average OI — often signals informed institutional positioning ahead of events.

### Options Strategy Recommendation Engine

Based on market regime (HMM output), IV environment, and directional view, the system recommends optimal strategies:

| Regime | IV Level | View | Recommended Strategies |
|--------|----------|------|----------------------|
| Bull | Low IV | Bullish | Long calls, bull call spreads, cash-secured puts |
| Bull | High IV | Bullish | Bull put spreads, covered calls |
| Bear | Low IV | Bearish | Long puts, bear put spreads |
| Bear | High IV | Bearish | Bear call spreads, iron condors |
| Sideways | High IV | Neutral | Short strangles, iron butterflies, jade lizards |
| Sideways | Low IV | Neutral | Calendar spreads, long straddles (pre-event) |

Each recommendation includes a P&L payoff diagram, breakeven points, max profit/loss, probability of profit (via Monte Carlo simulation of underlying price paths), and margin requirement estimate per SEBI's SPAN + exposure margin rules.

### Expiry Day Intelligence

Weekly expiry trading (every Thursday for NIFTY/BANKNIFTY) is a massive volume event in India. The system provides: Gamma Exposure (GEX) analysis identifying dealer hedging flows that pin/magnify price moves, expiry-day-specific models trained on Thursday price action patterns, and time-decay-aware position management that accelerates exit signals as Theta crush intensifies in the final 2 hours.

---

## B. Alternative Data Sources

Traditional market and fundamental data is necessary but not sufficient for edge. Alternative data provides information asymmetry.

### Data Sources and Integration

**Google Trends India** — search interest for company/brand names, sector keywords ("home loan rates," "car sales"), and macro terms ("recession India," "gold price") provides leading indicators of consumer demand. Accessible via `pytrends` library with daily granularity for India (`geo='IN'`). Spike in "Reliance Jio" searches before quarterly results correlates with subscriber growth surprises.

**Satellite & Geospatial Data** — parking lot occupancy at malls (proxy for retail sector health), nighttime light intensity (economic activity), port traffic (trade volumes), agricultural crop health via NDVI (monsoon impact). Sources: Sentinel-2 (free, ESA), Planet Labs (commercial). Most relevant for long-term fundamental analysis of infrastructure, retail, and agriculture stocks.

**Web Scraping Intelligence** — e-commerce pricing and inventory on Amazon.in/Flipkart (competitive intelligence for consumer companies), job posting volumes on Naukri.com/LinkedIn (growth proxy — hiring surge = expansion), app download rankings from Sensor Tower (digital business traction), and government tender data from GeM portal (order book proxy for infra/defense companies).

**Credit Card / UPI Transaction Data** — anonymized, aggregated transaction volumes by merchant category. UPI transaction data is published monthly by NPCI and serves as a proxy for digital payment adoption (bullish for payment processors like Paytm, PhonePe parent companies). India processes 14+ billion UPI transactions monthly — growth trends directly impact fintech stock valuations.

**Social Media Sentiment (India-Specific)** — beyond Twitter/X, monitor **r/IndianStreetBets** (Reddit, 800K+ members), **TradingView India ideas**, **Moneycontrol forums**, **StockEdge community**, and financial YouTube/Instagram influencer sentiment. Hindi-language sentiment requires IndicNLP/AI4Bharat processing before FinBERT scoring.

**Regulatory Filings** — SEBI SAST (Substantial Acquisition of Shares and Takeovers) filings signal promoter/institutional accumulation, bulk deal data (>0.5% of equity in a single trade) published daily by NSE, block deal data (>5 lakh shares at ≥₹10 crore), and insider trading disclosures under SEBI PIT regulations.

### Alternative Data Pipeline

All alternative data feeds are assigned a **signal decay half-life** (Google Trends: ~7 days, satellite: ~30 days, web scraping: ~3 days, social sentiment: ~24 hours) which determines refresh frequency and feature weight decay in models. Data is stored in MongoDB (flexible schema for heterogeneous sources) and feature-engineered into standardized signals before joining the main feature store.

---

## C. Security, Secrets Management & Data Privacy

### API Key and Credential Management

Broker API keys (Zerodha, Angel One, DhanHQ), LLM API keys (OpenAI, Anthropic), and database credentials are managed via **HashiCorp Vault** (self-hosted) or **AWS Secrets Manager** with automatic rotation policies:

- Broker API tokens: rotated daily (most Indian broker APIs issue session tokens valid for 1 trading day)
- LLM API keys: rotated monthly, per-service isolation (separate keys for sentiment vs. report generation)
- Database credentials: rotated quarterly via Vault's dynamic secrets
- Never stored in code, environment variables, or configuration files — injected at runtime via sidecar or init container

### Encryption Strategy

**Data at rest**: AES-256 encryption on all database volumes (QuestDB, PostgreSQL, MongoDB, Redis persistence). MinIO S3 buckets use server-side encryption with customer-managed keys (SSE-C). **Data in transit**: TLS 1.3 for all inter-service communication, mTLS between microservices via Istio service mesh, and TLS for all broker API connections. **Sensitive PII**: if the platform stores user data (names, PAN numbers, demat details), encrypt these fields at the application layer using envelope encryption before database storage.

### Network Security

- All broker API connections originate from **static elastic IPs** (SEBI requirement effective April 2026)
- WAF (AWS WAF or Cloudflare) protects public-facing APIs
- VPC with private subnets for all backend services — only the API gateway and WebSocket endpoint are internet-facing
- Network policies in Kubernetes restrict pod-to-pod communication to explicit allowlists
- DDoS protection via AWS Shield Standard (free) with option to upgrade to Shield Advanced

### Audit Logging

Every order, signal, model prediction, and agent decision is logged to an immutable audit trail (Kafka + S3 archival) with:
- Timestamp (nanosecond precision, IST)
- Actor (which service/model/agent initiated)
- Action (signal generated, order placed, risk check failed)
- Payload hash (SHA-256 for tamper detection)
- SEBI requires 5-year retention of all trading records

---

## D. Disaster Recovery & Business Continuity

### Failure Scenarios During Market Hours

Market hours (9:15 AM – 3:30 PM IST) are critical — system downtime during live trading can mean missed exits and unchecked losses. The system implements:

**Broker API failure**: automatic failover to secondary broker (e.g., Angel One → DhanHQ). All supported brokers implement the same adapter interface, enabling hot-swap within 5 seconds. Positions are reconciled post-failover via portfolio sync APIs.

**Kafka cluster failure**: multi-AZ deployment with ISR (In-Sync Replicas) ≥ 2 ensures no single-AZ failure causes data loss. If the entire Kafka cluster is unreachable (extremely rare), the system enters **safe mode**: all open positions trigger pre-calculated stop-loss orders via direct broker API calls, bypassing the event pipeline entirely.

**Database failure**: QuestDB runs with WAL (Write-Ahead Logging) and periodic snapshots to S3. PostgreSQL uses streaming replication with automatic failover via Patroni. Redis Sentinel provides automatic master failover with sub-second detection.

**Cloud region failure**: critical stop-loss and position management logic runs as a lightweight **"guardian process"** on a separate cloud provider (e.g., DigitalOcean Bangalore) that monitors positions and executes emergency exits if the primary AWS Mumbai region is unreachable.

### Recovery Time and Point Objectives

| Component | RTO (Recovery Time) | RPO (Recovery Point) |
|-----------|--------------------|--------------------|
| Order execution | <10 seconds (broker failover) | Zero (pre-computed stop-losses) |
| Kafka event stream | <30 seconds (AZ failover) | <1 second |
| Feature computation | <2 minutes (Flink checkpoint restore) | <30 seconds |
| ML model serving | <1 minute (rolling pod restart) | N/A (stateless) |
| Database (QuestDB) | <5 minutes (replica promotion) | <10 seconds |
| Full system | <5 minutes | <30 seconds |

### Chaos Engineering

Monthly chaos tests using **Litmus Chaos** or **Chaos Mesh** simulate: random pod kills during market hours, network partition between services, broker API latency injection (500ms → 5s), and Kafka broker failure. Each test validates that stop-losses execute and no unprotected positions remain.

---

## E. Indian Tax Optimization Module

### Capital Gains Tax Rules (FY 2025–26)

The system must be tax-aware in its holding period recommendations:

- **STCG (Short-Term Capital Gains)**: holdings sold within 12 months — taxed at **20%** (increased from 15% in Budget 2024)
- **LTCG (Long-Term Capital Gains)**: holdings sold after 12 months — taxed at **12.5%** (increased from 10% in Budget 2024) on gains exceeding ₹1.25 lakh per year (increased from ₹1 lakh)
- **Intraday profits**: treated as business income, taxed at slab rate
- **F&O profits**: speculative business income, taxed at slab rate
- **Securities Transaction Tax (STT)**: already modeled in backtesting; not separately deductible from business income but deductible from speculative income

### Tax-Loss Harvesting Engine

The system implements automated tax-loss harvesting:

1. **Identify** positions with unrealized losses approaching the 12-month LTCG cutoff
2. **Calculate** tax benefit of realizing the loss now (at 20% STCG rate) versus waiting
3. **Execute** sell + immediate rebuy of a correlated substitute (to maintain market exposure while booking the loss — note: India has no wash-sale rule unlike the US)
4. **Track** harvested losses against gains for net tax liability minimization
5. **Year-end optimization**: in March (FY end), run a portfolio-wide optimization that identifies the optimal set of positions to realize for maximum tax efficiency

### Holding Period Intelligence

When generating SELL signals, the system checks the holding period and appends tax-adjusted returns:

- If a position is 10–11 months old with moderate profit, the system may recommend "HOLD to LTCG" (saving 7.5% tax differential) unless the signal strength exceeds a configurable threshold
- Signal output includes: `pre_tax_return`, `post_tax_return`, `tax_rate_applied`, `days_to_ltcg_eligibility`, and `tax_saving_if_held`

---

## F. IPO Analysis Module

India has one of the world's most active IPO markets (100+ mainboard IPOs annually). Early identification of quality IPOs and post-listing behavior prediction is high-value intelligence.

### Pre-IPO Analysis

The LLM agent team analyzes DRHP (Draft Red Herring Prospectus) and RHP documents:

- **Financial health scoring**: revenue growth trajectory, profitability margins, debt levels, cash flow quality
- **Peer comparison**: automatic identification of listed peers and relative valuation (P/E, EV/EBITDA, P/S)
- **Promoter background check**: prior ventures, regulatory actions, litigation history (extracted from RHP risk factors)
- **GMP (Grey Market Premium) tracking**: scrape aggregator sites for unofficial pre-listing premium as a sentiment gauge
- **Subscription data analysis**: real-time tracking of QIB, NII, and Retail subscription multiples during the bidding period — historically, QIB oversubscription > 10x correlates with strong listing gains
- **Anchor investor analysis**: identify anchor allottees and their historical IPO performance

### Post-IPO Intelligence

- **Listing day prediction model**: trained on historical IPO data (subscription ratios, GMP, market conditions, sector sentiment) to predict listing premium/discount
- **Lock-in expiry tracking**: promoter lock-in (18 months for 20% stake) and anchor investor lock-in (30/90 days) — potential selling pressure alerts
- **Post-listing momentum**: track price action relative to issue price with alerts at key levels (issue price support, 52-week high)

---

## G. Corporate Governance & Promoter Risk Scoring

Indian markets have unique governance risks that Western-focused platforms often miss.

### Promoter Risk Indicators

- **Promoter pledging percentage**: high pledge (>50% of holdings) signals financial stress and creates forced-selling risk during market downturns — this was a major factor in the Zee Entertainment and DHFL crises
- **Promoter holding changes**: quarterly tracking of promoter stake increases/decreases (from BSE/NSE shareholding pattern filings)
- **Related party transactions (RPT)**: LLM extraction from annual report notes — excessive RPTs flag potential value siphoning
- **Auditor changes**: unexpected auditor resignation or qualification in audit reports is a red flag
- **Board independence**: ratio of independent directors, frequency of board meetings, attendance records
- **SEBI/exchange actions**: track any show-cause notices, fines, or trading suspensions against the company or promoters

### Governance Score

A composite **Governance Score (0–100)** is computed using weighted factors: promoter pledging (25%), related party transactions relative to revenue (20%), auditor quality and tenure (15%), board independence and meeting frequency (15%), regulatory action history (15%), and disclosure timeliness (10%). Stocks with Governance Score < 40 receive automatic position size limits or exclusion from the investable universe.

---

## H. Global Market Correlation & Pre-Market Intelligence

### Overnight Global Signal Processing

Indian markets are significantly influenced by overnight global movements. The pre-market intelligence engine (running 7:00–9:15 AM IST) processes:

- **US market close** (S&P 500, NASDAQ, Dow Jones) — correlation with NIFTY next-day open is historically 0.5–0.7 during risk-off periods
- **SGX NIFTY / GIFT NIFTY futures** — the most direct indicator of Indian market opening direction, trading 16 hours/day on Singapore/GIFT City exchanges
- **Asian market openings** — Nikkei 225, Hang Seng, Shanghai Composite — sequential opening pattern provides regional sentiment
- **US futures** (S&P 500 E-mini) — live during Indian pre-market, signals intraday global risk appetite
- **Crude oil** (Brent) overnight movement — direct impact on OMCs, airlines, paints, and overall market sentiment
- **US Dollar Index (DXY)** and INR/USD NDF (Non-Deliverable Forward) rate — signals expected INR movement at market open
- **US Treasury yields** (10Y) — rising yields reduce FII appetite for Indian equities
- **VIX (CBOE)** — global risk appetite gauge; spike above 20 typically triggers FII selling in EMs

### Pre-Market Signal Generation

By 8:30 AM IST, the system produces a "Market Opening Prediction" signal based on GIFT NIFTY movement, overnight global factors, and any India-specific overnight news (corporate actions, government announcements, RBI after-hours communications). This signal feeds the Morning Brief report and adjusts opening-hour strategy parameters (wider stops if gap-up/gap-down expected, reduced position sizes if high uncertainty).

---

## I. Communication & Delivery Channels (India-Specific)

### Telegram Bot Integration

Telegram is the dominant platform for Indian retail trading communities. The system deploys a Telegram bot (`python-telegram-bot` library) with:

- Real-time signal delivery with formatted messages: `🟢 BUY RELIANCE @ ₹2,850 | Target: ₹3,050 | SL: ₹2,780 | Confidence: 78%`
- Interactive commands: `/portfolio` (current positions), `/signals` (today's signals), `/risk` (portfolio risk summary), `/market` (market overview)
- Alert subscriptions: users subscribe to specific stocks, sectors, or signal types
- Group channel for broadcast signals + private bot for portfolio-specific alerts

### WhatsApp Business API

For users who prefer WhatsApp (dominant messaging app in India), a WhatsApp Business API integration delivers:
- Morning brief summary
- High-priority P1 alerts
- End-of-day P&L summary
- Reply-based interaction for quick portfolio queries

### Mobile Push Notification Strategy

Using Firebase Cloud Messaging with priority tiers:
- **Critical (P1)**: delivered as high-priority notification that bypasses Do Not Disturb — stop-loss triggers, portfolio circuit breaker activation, high-confidence signals >85%
- **Important (P2)**: standard push notification — new signals, earnings alerts, price target hits
- **Digest (P3)**: batched into a daily summary notification at 4:30 PM IST

---

## J. Paper Trading & Simulation Environment

### Virtual Trading Engine

Before any strategy goes live, it must survive a minimum 3-month paper trading period. The simulation engine:

- Mirrors the full production pipeline (data ingestion → features → models → signals → risk checks → virtual execution) but writes to a **shadow order book** instead of broker APIs
- Simulates realistic execution: slippage modeled as `0.05% + f(volume, spread)`, partial fills for large orders, rejection probability for illiquid stocks, and realistic latency injection
- Tracks identical metrics as live trading: Sharpe, Sortino, max drawdown, win rate, average R-multiple, profit factor
- **A/B comparison dashboard** shows paper strategy performance side-by-side with: (a) what the live system would have done, (b) benchmark buy-and-hold, (c) NIFTY 50 index

### Promotion Criteria (Paper → Live)

A strategy is promoted from paper to live trading only when:
1. Minimum 3 months of paper trading completed
2. Sharpe ratio > 1.5 (annualized)
3. Maximum drawdown < 15%
4. Win rate > 55% for directional strategies
5. Profit factor > 1.5
6. Performance consistency across at least 2 different market regimes (verified by HMM)
7. No single day with loss > 3% of virtual capital
8. Manual review and sign-off

Promoted strategies start at **10% capital allocation** and scale up in 10% increments every 2 weeks if live performance tracks within 1 standard deviation of paper performance.

---

## K. Commodity & Currency Correlation Analytics

### Cross-Asset Correlation Matrix

Indian equities have strong, well-documented correlations with commodities and currencies that the main architecture should explicitly model:

| Asset | Correlated Indian Sectors | Relationship |
|-------|--------------------------|--------------|
| Crude Oil (Brent) | OMCs (HPCL, BPCL, IOC) — inverse; Airlines (IndiGo) — inverse; Paints (Asian Paints) — inverse (crude is raw material); ONGC, Oil India — positive | ₹5/barrel move ≈ 1–3% sector move |
| Gold | Titan, Kalyan Jewellers — positive (revenue driver); Banking — inverse (gold is competing safe haven) | Safe-haven correlation spikes during market stress |
| Copper | Metal stocks (Hindalco, Tata Steel) — positive; Real estate, infra — leading indicator | Copper as "Dr. Copper" — economic health barometer |
| INR/USD | IT (TCS, Infosys, Wipro) — inverse (rupee depreciation = higher export revenue); Importers (oil, electronics) — positive (weaker rupee = higher costs) | 1% INR depreciation ≈ 1.5–2% IT sector EPS boost |
| US 10Y Yield | FII flows — inverse (rising yields pull FII money to US); Rate-sensitive sectors — inverse | Yield spike → FII selling → broad market pressure |

### Dynamic Correlation Monitoring

Correlations are not static — they regime-shift (correlations spike toward 1.0 during crises). The system computes:
- Rolling 30/60/90-day correlation matrices across all asset pairs
- **DCC-GARCH** (Dynamic Conditional Correlation) for time-varying correlation estimation
- Correlation breakout alerts when a historically stable relationship diverges by > 2 standard deviations — potential dislocation trade opportunity or risk signal

---

## L. Performance Benchmarking & Reporting Standards

### Strategy Performance Metrics (Full Suite)

Beyond the basics mentioned in the main document, the system tracks:

- **CAGR** (Compound Annual Growth Rate) — absolute return metric
- **Sharpe Ratio** — risk-adjusted return (target: >1.5)
- **Sortino Ratio** — penalizes only downside deviation (more relevant than Sharpe for asymmetric strategies)
- **Calmar Ratio** — CAGR / Max Drawdown (target: >1.0)
- **Omega Ratio** — probability-weighted ratio of gains vs losses at a threshold return
- **Information Ratio** — active return vs tracking error against NIFTY 50
- **Profit Factor** — gross profits / gross losses (target: >1.5)
- **Average R-Multiple** — average return per unit of risk (R = initial risk amount)
- **Expectancy** — (win% × avg win) - (loss% × avg loss) — expected value per trade
- **Maximum Drawdown Duration** — longest time from peak to recovery (not just depth)
- **Ulcer Index** — measures depth and duration of drawdowns combined

### Benchmark Comparison

Every strategy and the overall portfolio are benchmarked against:
1. **NIFTY 50 Total Return Index** (includes dividends) — primary benchmark
2. **NIFTY 500** — broader market benchmark
3. **Sector-specific indices** — for sector-focused strategies
4. **Fixed deposit rate** (SBI 1-year FD, ~7%) — the risk-free alternative
5. **PPF rate** (7.1%) — the retail investor's opportunity cost

Monthly and quarterly reports show alpha generation over each benchmark with statistical significance testing (t-test, bootstrap confidence intervals).

---

## M. Load Testing & Capacity Planning

### Performance Benchmarks

Before go-live, the system must pass these load tests:

| Scenario | Target | Test Tool |
|----------|--------|-----------|
| Tick ingestion throughput | >50,000 ticks/second | Custom Rust load generator |
| Kafka produce/consume | >100,000 msgs/second per partition | kafka-producer-perf-test |
| Feature computation (Flink) | <30ms P99 for 2,000 symbols | Flink metrics + Prometheus |
| ML inference latency | <20ms P99 (ONNX Runtime) | Locust / custom benchmark |
| Redis read latency | <1ms P99 | redis-benchmark |
| API gateway throughput | >10,000 requests/second | k6 or Locust |
| WebSocket concurrent connections | >10,000 simultaneous | Artillery |
| End-to-end signal generation | <100ms P95 | Jaeger distributed trace analysis |

### Market Open Stress Test

The 9:15 AM IST market open is the highest-load moment — all 2,000+ stocks start trading simultaneously, generating a tick storm. The system must handle:
- 10x normal tick rate in the first 5 minutes
- All feature computations completing within latency SLA despite burst load
- No message backlog in Kafka exceeding 5 seconds

Capacity planning uses the formula: `Required_Capacity = Peak_Load × 1.5 (headroom) × 1.2 (growth factor)`. Auto-scaling via Kubernetes HPA is configured with custom metrics (Kafka consumer lag, Flink backpressure) rather than just CPU/memory.

---

## N. Data Quality & Reconciliation Framework

### Multi-Source Data Reconciliation

Since the system ingests data from multiple sources (Zerodha, Angel One, yfinance, NSE bhavcopy), discrepancies are inevitable. The reconciliation framework:

1. **Primary source hierarchy**: NSE bhavcopy (ground truth for EOD) > broker real-time feed > yfinance
2. **Real-time cross-validation**: if two broker feeds disagree on LTP by > 0.5%, flag and use the source closer to NSE's last traded price
3. **EOD reconciliation job** (4:30 PM daily): compare all day's OHLCV data against bhavcopy, flag and correct discrepancies, log all corrections for audit
4. **Corporate action adjustment**: automatically adjust historical prices for splits, bonuses, and rights issues using NSE's corporate action data — failure to adjust causes false signals from technical indicators

### Data Quality Monitoring Dashboard

A dedicated Grafana dashboard tracks: data freshness (time since last update per symbol), missing data rate (symbols with no updates in 5+ minutes during market hours), OHLC integrity violations, cross-source deviation alerts, and bhavcopy reconciliation match rate (target: >99.5%).

---

## O. Mutual Fund & ETF Intelligence

### Why Include MFs/ETFs

Many Indian retail investors hold mutual funds alongside direct equities. Stock Pulse can differentiate by providing:

- **ETF arbitrage signals**: when ETF price deviates from NAV by > 0.5% (common in illiquid ETFs like Bharat 22, CPSE ETF)
- **Sectoral ETF timing**: use the same sector rotation intelligence to recommend entry/exit on sector ETFs (NIFTY IT ETF, Bank ETF, etc.)
- **Mutual fund portfolio overlap analysis**: identify which MF schemes hold the same stocks as the user's direct equity portfolio — avoid unintended concentration
- **MF flow analysis**: monthly AMFI data on scheme-level inflows/outflows — large inflows into small-cap MFs signal potential frothiness; large outflows signal redemption pressure on underlying stocks
- **SIP timing intelligence**: while SIPs are inherently time-averaged, the system can flag months where additional lump-sum investment is statistically favorable based on market regime

---

*These additions fill critical gaps in the main architecture around derivatives intelligence, alternative data, security, disaster recovery, tax optimization, Indian-specific delivery channels, and operational concerns. Each module integrates with the existing event-driven architecture via Kafka topics and follows the same microservices pattern described in the primary document.*
