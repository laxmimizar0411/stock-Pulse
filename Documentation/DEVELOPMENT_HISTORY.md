# StockPulse - Complete Development History

> **Document Version**: 5.0
> **Last Updated**: March 7, 2026
> **Platform**: Indian Stock Market Analysis Platform (NSE/BSE)
> **Repository**: [github.com/ShraddheyWamanSatpute/Stock-Pulse](https://github.com/ShraddheyWamanSatpute/Stock-Pulse)
> **Active PR**: [#1 - Hybrid Database Architecture + Pipeline Fixes](https://github.com/ShraddheyWamanSatpute/Stock-Pulse/pull/1)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Overview](#2-architecture-overview)
3. [Complete Development Timeline](#3-complete-development-timeline)
4. [Session-by-Session Changelog](#4-session-by-session-changelog)
5. [Current File Structure](#5-current-file-structure)
6. [API Endpoints Reference](#6-api-endpoints-reference)
7. [Database Architecture](#7-database-architecture)
8. [Scoring System](#8-scoring-system)
9. [Data Extraction Pipeline](#9-data-extraction-pipeline)
10. [Testing & Quality Assurance](#10-testing--quality-assurance)
11. [Known Issues & Next Steps](#11-known-issues--next-steps)
12. [Related Documentation](#12-related-documentation)
13. [Current Status Summary](#13-current-status-summary)

---

## 1. Project Overview

### What is StockPulse?

StockPulse is a comprehensive personal stock analysis platform designed for Indian markets (NSE/BSE). It combines rule-based scoring, machine learning predictions, and LLM-powered insights to help users make informed investment decisions.

### Key Capabilities

| Feature | Description |
|---------|-------------|
| 160 Data Fields | Comprehensive data across 13 categories |
| Hybrid 4-Layer Database | Redis + MongoDB + PostgreSQL + Filesystem |
| 10 Deal-Breakers | D1-D10 automatic stock rejection rules |
| 10 Risk Penalties | R1-R10 score deduction rules |
| 9 Quality Boosters | Q1-Q9 score enhancement rules |
| Investment Checklists | 10 short-term + 13 long-term criteria |
| Live Data Pipeline | Groww Trading API with TOTP authentication |
| 143 Tracked Symbols | NIFTY 50 + NIFTY Next 50 + Mid/Small Caps |

---

## 2. Architecture Overview

### Technology Stack (Current - v3.0)

```
+-------------------------------------------------------------+
|                        FRONTEND                              |
|  React 18 + Tailwind CSS + shadcn/ui + Recharts             |
|  Port: 3000                                                  |
+-------------------------------------------------------------+
|                        BACKEND                               |
|  FastAPI + Python 3.11 + async (Motor, asyncpg, redis-py)   |
|  Port: 8001                                                  |
+-------------------------------------------------------------+
|                   DATABASE LAYER (4-Layer Hybrid)             |
|  Redis ........... Real-time cache, pub/sub, sorted sets     |
|  MongoDB ......... Entity/document store (Motor async)       |
|  PostgreSQL ...... Time-series & analytics (asyncpg)         |
|  Filesystem ...... Binary artifacts, reports, exports        |
+-------------------------------------------------------------+
|                    INTEGRATIONS                              |
|  Groww Trading API ... Live Indian market data (TOTP auth)   |
|  OpenAI GPT-4o ...... AI insights (via Emergent LLM key)    |
|  Yahoo Finance ...... Historical/backup prices (yfinance)    |
|  NSE Bhavcopy ....... Official EOD OHLCV data               |
+-------------------------------------------------------------+
```

---

## 3. Complete Development Timeline

### Phase 1: Foundation (v1.0) - Initial Build
- Setup FastAPI backend with MongoDB
- Create React frontend with Tailwind CSS + shadcn/ui
- Implement 7 core modules (Dashboard, Analyzer, Screener, Watchlist, Portfolio, NewsHub, Reports)
- Add mock data for 40 Indian stocks
- Integrate GPT-4o for AI insights via Emergent LLM key
- Basic scoring system skeleton

### Phase 2: Scoring System & Data Framework (v2.0)
- Design 160 data fields across 13 categories
- Build extraction framework with yfinance and NSE bhavcopy parser
- Implement all 10 Deal-Breakers (D1-D10)
- Implement all 10 Risk Penalties (R1-R10)
- Implement all 9 Quality Boosters (Q1-Q9)
- Add Confidence Score formula
- Add Investment Checklists (10 short-term + 13 long-term)
- Add Data Extraction Pipeline API endpoints
- Enhanced frontend Checklist tab UI

### Phase 3: Live Data Pipeline (v2.1)
- Groww Trading API integration with JWT authentication
- Expanded stock tracking from 30 to 143 symbols
- Automated data collection scheduler (15-min intervals)
- Data Pipeline monitoring dashboard (frontend page)
- 12 new pipeline API endpoints
- Redis cache integration for live market data piping

### Phase 4: Database Architecture Design (v2.2)
- Created comprehensive Database Architecture Plan documentation
- Designed 4-layer hybrid database system (Redis, MongoDB, PostgreSQL, Filesystem)
- Defined 10 MongoDB collections with index configurations
- Defined 4 PostgreSQL tables with optimized schemas
- Defined Redis cache patterns (HASH, SORTED SET, PUB/SUB)
- Created PR #1 on GitHub

### Phase 5: Database Implementation (v2.3)
- Built `setup_databases.py` - automated database setup script
- Built `timeseries_store.py` - PostgreSQL bridge with asyncpg (646 lines)
- Built `cache_service.py` - Redis cache service with pub/sub (396 lines)
- Built `mongodb_store.py` - MongoDB storage layer (294 lines)
- Enhanced `server.py` with MongoDB indexes, news/backtest endpoints, screener optimization
- Connected pipeline service to PostgreSQL bridge for data persistence

### Phase 6: Database Fixes & Pipeline Repair (v2.4)
- Rewrote corrupted `setup_databases.py` (two versions had been concatenated)
- Fixed server.py duplicate MongoDB index creation
- Fixed server.py duplicate screener code with wrong API
- Added `/api/database/health` endpoint
- Fixed Groww pipeline token refresh race condition
- Fixed Groww pipeline field naming mismatch between extractor and persistence layer
- Fixed Groww pipeline `_test_api_connection` endpoint inconsistency
- Improved Groww pipeline response parsing and reduced bulk concurrency
- Enhanced `test_pipeline.py` with --db-only, --api-only, --all modes

### Phase 7: Data Sources Documentation (v3.0) - Current
- Created comprehensive Data Sources & Extraction Guide (1,663 lines)
- Mapped all 160 fields to their extraction sources, methods, and Python code
- Documented anti-bot handling for NSE, BSE, Screener.in, Trendlyne
- Identified free broker APIs (Dhan, Angel One, Fyers, Breeze) for real-time data
- Provided cost analysis showing Rs 0/month is achievable for full pipeline

### Phase 8: MongoDB Operations & Database Dashboard (v3.1)
- Implemented MongoDB production-hardening patterns in code (timeouts, pooling, health checks, indexes at startup)
- Introduced environment-aware MongoDB connection policy:
  - In **development/local**: `MONGO_URL` defaults to `mongodb://localhost:27017` for single-user local use
  - In **production**: `MONGO_URL` is required and must not point to localhost; app fails fast if Mongo is unreachable
- Configured **majority write concern** (`w="majority", j=true`) for critical MongoDB collections (`watchlist`, `portfolio`, `news_articles`, `backtest_results`, `alerts`, `pipeline_jobs`, `stock_data`) and wired `MongoDBStore` to reuse these app-level collections
- Extended `/api/database/health` to optionally include MongoDB **replica set status** (set name, member states, optime) when connected to a replica set (future production use)
- Added MongoDB backup script with rotation and JSON fallback (`backend/scripts/backup_mongodb.py`)
- Introduced Database Dashboard backend (`DatabaseDashboardService` + `/database` router) for collections/tables overview, activity, errors, settings, and size history
- Added query playground (MongoDB & PostgreSQL read-only queries), export endpoints, and audit logging
- Added WebSocket-powered dashboard pulse (`/ws/dashboard`) that streams live DB metrics (Mongo, Redis, PostgreSQL)
- Documented MongoDB production checklist and runbooks for future hosted/replica-set deployment (not required for current local-only use)

---

## 4. Session-by-Session Changelog

### Session 1 - Foundation (v1.0)

**What was built:**
- Complete FastAPI backend with all core endpoints
- React 18 frontend with 7 pages
- MongoDB integration via Motor (async driver)
- Mock data service generating realistic data for 40 Indian stocks
- GPT-4o LLM integration for AI-powered stock insights
- Basic scoring engine skeleton

**Files created:**
- `backend/server.py` - Main API server
- `backend/services/scoring_engine.py` - Scoring system
- `backend/services/mock_data.py` - Mock data generation
- `backend/services/llm_service.py` - GPT-4o integration
- `backend/models/stock_models.py` - Pydantic data models
- `frontend/src/pages/Dashboard.jsx` - Market overview
- `frontend/src/pages/StockAnalyzer.jsx` - Stock analysis
- `frontend/src/pages/Screener.jsx` - Stock screening
- `frontend/src/pages/Watchlist.jsx` - Watchlist management
- `frontend/src/pages/Portfolio.jsx` - Portfolio tracking
- `frontend/src/pages/NewsHub.jsx` - News aggregation
- `frontend/src/pages/Reports.jsx` - Report generation

---

### Session 2 - Scoring System & Data Framework (v2.0)

**What was built:**
- Complete 4-tier scoring system with 29 rules
- 160 data field definitions across 13 categories
- Data extraction framework (yfinance + NSE bhavcopy)
- Investment checklists (short-term + long-term)

**Scoring Rules Implemented:**

Deal-Breakers (D1-D10) - Any one triggers automatic rejection (score capped at 35):

| Code | Rule | Threshold |
|------|------|-----------|
| D1 | Interest Coverage | < 2.0x |
| D2 | SEBI Investigation | = true |
| D3 | Revenue Declining | 3+ years |
| D4 | Negative OCF | 2+ years |
| D5 | Negative FCF | 3+ years |
| D6 | Stock Status | Not ACTIVE |
| D7 | Promoter Pledging | > 80% |
| D8 | Debt-to-Equity | > 5.0 |
| D9 | Credit Rating | D/Withdrawn |
| D10 | Avg Volume | < 50,000 |

Risk Penalties (R1-R10) - Cumulative score deductions:

| Code | Rule | Threshold | LT Penalty | ST Penalty |
|------|------|-----------|------------|------------|
| R1 | D/E Moderate | 2.0-5.0 | -15 | -10 |
| R2 | Interest Coverage | 2.0-3.0x | -10 | -5 |
| R3 | ROE Weak | < 10% | -12 | -5 |
| R4 | Promoter Decreased | > 5% drop | -8 | -12 |
| R5 | Promoter Pledging | 30-80% | -10 | -15 |
| R6 | Price Below 52W High | > 30% | -5 | -15 |
| R7 | Operating Margin | Declining 2+ yrs | -10 | -5 |
| R8 | P/E Expensive | > 2x sector | -10 | -5 |
| R9 | Delivery % Low | < 30% | -5 | -10 |
| R10 | Contingent Liabilities | > 10% | -8 | -3 |

Quality Boosters (Q1-Q9) - Capped at +30 total:

| Code | Rule | Threshold | LT Boost | ST Boost |
|------|------|-----------|----------|----------|
| Q1 | ROE Excellent | > 20% | +15 | +5 |
| Q2 | Revenue Growth | > 15% CAGR | +12 | +5 |
| Q3 | Zero Debt | D/E < 0.1 | +10 | +5 |
| Q4 | Dividend History | 10+ years | +8 | +3 |
| Q5 | Operating Margin | > 25% | +10 | +5 |
| Q6 | Promoter Holding | > 50% | +8 | +10 |
| Q7 | FII Interest | > 20% | +5 | +8 |
| Q8 | 52W Breakout | With 2x volume | +3 | +12 |
| Q9 | FCF Yield | > 5% | +8 | +4 |

Confidence Score Formula:
```
Confidence = DataCompleteness(40%) + DataFreshness(30%) + SourceAgreement(15%) + MLConfidence(15%)
```

**Files modified:**
- `backend/services/scoring_engine.py` - Full scoring implementation
- `frontend/src/pages/StockAnalyzer.jsx` - Checklist tab UI
- `backend/server.py` - Extraction API endpoints

**Files created:**
- `backend/data_extraction/config/field_definitions.py` - 160 field definitions
- `backend/data_extraction/extractors/yfinance_extractor.py` - Yahoo Finance extractor
- `backend/data_extraction/extractors/nse_extractor.py` - NSE bhavcopy parser
- `backend/data_extraction/pipeline/orchestrator.py` - Pipeline coordination
- `backend/data_extraction/processors/data_cleaner.py` - Data cleaning
- `backend/data_extraction/quality/validator.py` - Data quality checks

---

### Session 3 - Live Data Pipeline (v2.1)

**What was built:**
- Groww Trading API integration with TOTP-based authentication (pyotp)
- JWT token management with automatic refresh
- Rate limiting (10 req/sec, 300 req/min) with retry logic (5 retries, exponential backoff)
- Expanded symbol tracking from 30 to 143 stocks across 3 categories
- Automated scheduler with configurable intervals
- Data pipeline monitoring dashboard (new frontend page)
- Redis cache integration for piping live market data

**Symbol Categories (143 Total):**

| Category | Count | Examples |
|----------|-------|----------|
| NIFTY 50 | 50 | RELIANCE, TCS, HDFCBANK, INFY |
| NIFTY Next 50 | 50 | ADANIGREEN, AMBUJACEM, DMART |
| Mid & Small Caps | 43 | AUROPHARMA, PERSISTENT, MRF |

**Files created:**
- `backend/data_extraction/extractors/grow_extractor.py` - Groww API extractor (~820 lines)
- `backend/services/pipeline_service.py` - Pipeline management service (721 lines)
- `backend/models/pipeline_models.py` - Pydantic models for pipeline
- `frontend/src/pages/DataPipeline.jsx` - Monitoring dashboard

**Files modified:**
- `backend/server.py` - Added 12 new pipeline API endpoints
- `frontend/src/lib/api.js` - Added pipeline API client functions

---

### Session 4 - Database Architecture Design (v2.2)

**What was built:**
- Comprehensive Database Architecture Plan document
- 4-layer hybrid database design:
  - **Redis**: Real-time cache (HASH, SORTED SET, PUB/SUB patterns)
  - **MongoDB**: Entity/document store (10 collections)
  - **PostgreSQL**: Time-series analytics (4 tables)
  - **Filesystem**: Binary artifacts (reports, exports)

**PR #1 created:** `claude/agitated-edison` branch pushed to GitHub

**Files created:**
- `Documentation/Database_Architecture_Plan.md`

---

### Session 5 - Database Implementation (v2.3)

**Commit:** `de20dd7` - "feat: Complete hybrid database implementation (Phases 1-4)"

**What was built:**

PostgreSQL Time-Series Store (`backend/services/timeseries_store.py` - 646 lines):
- `TimeSeriesStore` class with asyncpg connection pool
- Upsert methods for all 4 tables (prices_daily, technical_indicators, fundamentals_quarterly, shareholding_quarterly)
- `get_screener_data()` with 4-table JOIN and comprehensive COLUMN_MAP
- Automatic table creation on first connect

Redis Cache Service (`backend/services/cache_service.py` - 396 lines):
- `CacheService` with HASH operations (`set_stock_hash`, `get_stock_field`)
- SORTED SET operations (`update_top_movers`, `get_top_gainers/losers`)
- PUB/SUB operations (`publish_price`, `publish_alert`, `subscribe_prices`)
- TTL-based caching: 60s prices, 300s analysis, 30s pipeline, 180s news

MongoDB Store (`backend/data_extraction/storage/mongodb_store.py` - 294 lines):
- `MongoDBStore` class for extraction data persistence

MongoDB Collections (10):
1. `watchlist` - User watchlists (unique by symbol)
2. `portfolio` - User portfolio entries (unique by symbol)
3. `alerts` - Price/condition alerts
4. `stock_data` - Enriched stock snapshots
5. `price_history` - Price history cache
6. `extraction_log` - Data extraction audit trail
7. `quality_reports` - Data quality validation reports
8. `pipeline_jobs` - Pipeline execution jobs
9. `news_articles` - News with sentiment (TTL: 30 days)
10. `backtest_results` - Strategy backtesting results

PostgreSQL Tables (14):
1. `prices_daily` - Daily OHLCV (symbol + date unique)
2. `derived_metrics_daily` - Returns, 52-week high/low, volume ratios
3. `technical_indicators` - SMA, RSI, MACD, Ichimoku, Stochastic, CCI, etc. (27 cols)
4. `ml_features_daily` - ML predicted scores, anomaly flags
5. `risk_metrics` - VaR, beta, Sharpe, volatility, max drawdown
6. `valuation_daily` - P/E, P/B, EV/EBITDA, dividend yield, PEG
7. `fundamentals_quarterly` - Revenue, profit, ratios (55+ cols)
8. `shareholding_quarterly` - Promoter, FII, DII holdings
9. `corporate_actions` - Dividends, splits, bonuses
10. `macro_indicators` - Repo rate, GDP, CPI, USD/INR
11. `derivatives_daily` - Futures OI, options, put-call ratio, IV
12. `intraday_metrics` - VWAP, tick count, bid/ask snapshots (JSONB)
13. `weekly_metrics` - SMA crossover, sectoral heatmap (JSONB)
14. `schema_migrations` - Version tracking

Database Setup Script (`backend/setup_databases.py`):
- Automated setup for all 4 database layers
- PostgreSQL schema creation with indexes
- MongoDB collection creation with index configurations
- Redis connectivity check
- Filesystem directory setup

**Server enhancements:**
- MongoDB index creation at startup
- News article endpoints (`/api/news`)
- Backtest result endpoints (`/api/backtest`)
- PostgreSQL-powered screener optimization
- Pipeline service connected to TimeSeriesStore for persistence

**Files created:**
- `backend/services/timeseries_store.py`
- `backend/services/cache_service.py`
- `backend/data_extraction/storage/mongodb_store.py`
- `backend/setup_databases.py`

**Files modified:**
- `backend/server.py` - Startup hooks, new endpoints, screener optimization
- `backend/services/pipeline_service.py` - PostgreSQL bridge integration
- `backend/.env.example` - Database connection strings
- `backend/requirements.txt` - Added asyncpg, redis, pyotp

---

### Session 6 - Database Fixes & Pipeline Repair (v2.4)

**Commit:** `0a4f70b` - "fix: Database setup rewrite, server cleanup, and Groww pipeline fixes"

**Problems found and fixed:**

1. **`setup_databases.py` was corrupted** - Two complete versions of the file had been concatenated (duplicate imports, duplicate functions, code after `if __name__`). Complete rewrite with clean single implementation using argparse (`--postgres`, `--mongo`, `--redis`, `--check` flags).

2. **server.py duplicate MongoDB index creation** - `_ensure_mongodb_indexes(db)` was called correctly, but an identical inline block also created the same indexes. Removed the duplicate.

3. **server.py duplicate screener code** - Old PostgreSQL screener code with wrong API (`min_rsi=min_rsi, max_rsi=max_rsi`) was left alongside the correct version (`filters=filters_for_pg`). Removed the old block.

4. **Added `/api/database/health` endpoint** - Comprehensive health check for PostgreSQL (tables, row counts, sizes), MongoDB (collections, document counts), Redis (stats), filesystem (directories), and overall status.

5. **Groww pipeline token refresh race condition** - Multiple concurrent 401 responses could trigger parallel refresh attempts causing session corruption. Fixed by adding `_token_refresh_lock` (asyncio.Lock) with 5-second dedup check.

6. **Groww pipeline field naming mismatch** - `_transform_quote_data()` returned `last_price`, `day_change_percent` but `_persist_to_timeseries()` expected `current_price`, `ltp`, `price_change_percent`. Updated transform to output all canonical field aliases.

7. **Groww pipeline `_test_api_connection` inconsistency** - Used `/live-data/ltp` with `exchange_symbols=NSE_RELIANCE` while actual extraction used `/live-data/quote` with `trading_symbol=RELIANCE`. Fixed to use consistent endpoint/params.

8. **Groww pipeline response parsing fragility** - `get_stock_quote()` only handled one response format. Enhanced to handle status/payload wrapper, direct data, and nested data key formats.

9. **Groww pipeline bulk concurrency too high** - Semaphore was set to 10 concurrent requests which could trigger rate limits. Reduced to 5.

10. **`test_pipeline.py` enhanced** - Added 3 test modes: `--db-only` (test all DB connections), `--api-only` (test Groww API auth + quotes), `--all` (full pipeline with PG bridge).

**Files modified:**
- `backend/setup_databases.py` - Complete rewrite
- `backend/server.py` - Removed duplicates, added health endpoint
- `backend/data_extraction/extractors/grow_extractor.py` - 6 bug fixes
- `backend/test_pipeline.py` - Enhanced integration tests

---

### Session 7 - Data Sources Documentation (v3.0)

**Commit:** `d9b9b30` - "docs: Add comprehensive data sources & extraction guide for all 160 fields"

**What was built:**
- `Documentation/Data_Sources_and_Extraction_Guide.md` (1,663 lines)
- Maps every one of the 160 data fields to its source, extraction method, and Python code
- Covers 9 data sources with working code examples:
  1. NSE Bhavcopy via `jugaad-data` library
  2. Screener.in web scraping (BeautifulSoup)
  3. BSE India API for shareholding and corporate actions
  4. yfinance for adjusted close and backup prices
  5. Free broker APIs (Dhan, Angel One, Fyers, Breeze)
  6. Trendlyne for institutional flow data
  7. RSS feeds (Moneycontrol, Economic Times, Business Standard)
  8. Credit rating agencies (CRISIL, ICRA, CARE)
  9. pandas-ta for all 15 technical indicators
- Anti-bot handling guide for each source
- Cost analysis: full pipeline achievable for Rs 0/month
- Phase-wise extraction priority plan

**Files created:**
- `Documentation/Data_Sources_and_Extraction_Guide.md`

---

### Session 8 - MongoDB Ops & Database Dashboard (v3.1)

**Key commits:**
- `0ead30c` - "feat: MongoDB production-ready hardening - security, validation, backups"
- `69fbf00` - "feat: add comprehensive Database Dashboard for monitoring & management"
- `9fc8cd5` - "feat: complete Database Dashboard gap fixes - CRUD, charts, filters, docs"
- `82867c9` - "feat: add Query Playground, Tools, Help Panel, Export, WebSocket, and theme toggle"
- `342aa25` - "Merge pull request #9 from ShraddheyWamanSatpute/claude/mongodb-production-ready-0AkeH"

**What was built:**
- MongoDB hardening in the backend:
  - Timeouts, connection pooling, `serverSelectionTimeoutMS` and `socketTimeoutMS` tuned
  - Centralized index creation at startup for all 10 MongoDB collections
  - Environment-aware connection policy: production requires non-localhost `MONGO_URL` and fails fast if Mongo is down; development keeps using local Mongo with graceful logging
  - Majority write concern configured for high-value collections, ensuring durable writes once a replica set is used
  - Health checks (`/api/database/health`) now enumerate collections, document counts, and (when available) replica set status (set name, member states, optime)
  - Backup script `backend/scripts/backup_mongodb.py` with mongodump + JSON fallback and rotation
- Database Dashboard (backend):
  - `/database/overview` - aggregated view of MongoDB, PostgreSQL, and Redis usage
  - `/database/collections`, `/database/tables`, `/database/redis/keys` - introspection endpoints
  - `/database/activity`, `/database/errors`, `/database/errors/trend` - activity and error feeds
  - `/database/settings` - dashboard configuration (safe mode, thresholds, refresh interval)
  - `/database/audit-log` - structured audit trail for admin operations
  - `/database/backup` - API trigger for MongoDB backup script
  - `/database/query/mongodb` and `/database/query/postgresql` - **read-only** query playground
- Database Dashboard (frontend, `DatabaseDashboard.jsx`):
  - Live overview cards for MongoDB/Redis/PostgreSQL status and sizes
  - Collections/tables browser with sampling and inferred schema view
  - Activity & error timeline, error trend charts
  - Safe-mode bulk delete, export (JSON/CSV), and audit-log viewer
  - Tools/help panel explaining how the dashboard maps to the hybrid database architecture
- Observability:
  - WebSocket endpoint `/ws/dashboard` streams periodic DB metrics (collection counts, error counts, Redis keys, PG rows)
  - Health endpoint extended to include MongoDB replica-set info when connected to a replica set (future production)

**Notes for current phase:**
- All MongoDB production/replica-set features are implemented in a way that **default to local single-node usage** (your current setup).
- Additional MongoDB documents (`MongoDB_Production_Checklist.md`, `MongoDB_Runbooks.md`) capture future hosted/99.9% SLA guidance without changing current local flow.

### Phase 9: PostgreSQL Full Expansion (v4.0)
- Expanded PostgreSQL schema from 4 tables to 14 tables with 40+ indexes covering 270+ fields from V2 data spec
- New tables: derived_metrics_daily, ml_features_daily, risk_metrics, valuation_daily, corporate_actions, macro_indicators, derivatives_daily, intraday_metrics, weekly_metrics, schema_migrations
- Extended `timeseries_store.py` with 12 upsert methods and 17+ query methods covering all 14 tables
- Extended screener from 4-table JOIN to 7-table JOIN (added derived, valuation, risk CTEs) with ~50 filter/sort keys
- Fixed `upsert_technicals` to include all 27 schema columns (added Ichimoku, Stochastic, CCI, Williams %R, CMF, MACD histogram)
- Fixed `upsert_fundamentals` to dynamically include all 55+ columns via FUND_COLS list
- Rewrote `_persist_to_timeseries()` in pipeline_service.py from 4-table writes to 9 table categories
- Added 12 new REST endpoints under `/api/timeseries/` for all table types
- Created PostgreSQL Control service (`pg_control_service.py`) with start/stop/resource monitoring
- Created PG Control REST routes (`routes/pg_control.py`) — 4 endpoints
- Created PG Control frontend UI (`PostgresControl.jsx`) with power toggle, resource cards, per-table storage, connection stats, pool stats, auto-refresh
- Created derived data computation job (`jobs/derive_metrics.py`) computing daily returns, 52-week metrics, volume ratios, and weekly SMA crossovers
- Updated `test_pipeline.py` expected tables from 4 to 14
- Updated `setup_databases.py` docstring and check-only mode for 14 tables
- Updated `db_dashboard_service.py` metadata for all 14 tables
- Updated `PROMPT_PostgreSQL_Complete_Local_Setup.md` to reflect full 14-table architecture

---

## 5. Current File Structure

```
Stock-Pulse/
├── backend/
│   ├── server.py                    # Main FastAPI server (~2430 lines)
│   │                                #   - All REST endpoints
│   │                                #   - WebSocket support
│   │                                #   - Startup hooks (DB init, pipeline)
│   │                                #   - /api/database/health endpoint
│   │
│   ├── setup_databases.py           # Database setup & migration script
│   │                                #   --postgres, --mongo, --redis, --check
│   │
│   ├── test_pipeline.py             # Integration test suite
│   │                                #   --db-only, --api-only, --all
│   │
│   ├── models/
│   │   ├── stock_models.py          # Stock, Portfolio, Alert, ScreenerFilter models
│   │   └── pipeline_models.py       # Pipeline job, config, metrics models
│   │
│   ├── jobs/
│   │   ├── __init__.py              # Jobs package init
│   │   └── derive_metrics.py        # Derived metrics computation job
│   │
│   ├── routes/
│   │   └── pg_control.py            # PostgreSQL control REST routes
│   │
│   ├── services/
│   │   ├── scoring_engine.py        # 4-tier scoring (D1-D10, R1-R10, Q1-Q9, ML)
│   │   ├── mock_data.py             # Mock data for 40 stocks
│   │   ├── llm_service.py           # GPT-4o integration
│   │   ├── alerts_service.py        # Price alert service (379 lines)
│   │   ├── pipeline_service.py      # Groww pipeline orchestration (9-table persistence)
│   │   ├── cache_service.py         # Redis cache with pub/sub (396 lines)
│   │   ├── timeseries_store.py      # PostgreSQL time-series bridge (14 tables, 12 upsert + 17 query methods)
│   │   ├── pg_control_service.py    # PostgreSQL start/stop/resource monitoring
│   │   └── db_dashboard_service.py  # Database dashboard metadata (14 tables)
│   │
│   ├── data_extraction/
│   │   ├── config/
│   │   │   └── field_definitions.py # 160 field definitions with metadata
│   │   ├── extractors/
│   │   │   ├── yfinance_extractor.py    # Yahoo Finance data
│   │   │   ├── nse_extractor.py         # NSE bhavcopy parser
│   │   │   └── grow_extractor.py        # Groww API extractor (~820 lines)
│   │   ├── storage/
│   │   │   └── mongodb_store.py     # MongoDB persistence (294 lines)
│   │   ├── pipeline/
│   │   │   └── orchestrator.py      # Pipeline coordination
│   │   ├── processors/
│   │   │   └── data_cleaner.py      # Data normalization
│   │   └── quality/
│   │       └── validator.py         # Data quality checks
│   │
│   ├── .env.example                 # Environment variable template
│   └── requirements.txt             # Python dependencies (140 packages)
│
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.jsx        # Market overview, indices
│       │   ├── StockAnalyzer.jsx    # Analysis with 5 tabs
│       │   ├── Screener.jsx         # Custom stock screening
│       │   ├── Watchlist.jsx        # Watchlist management
│       │   ├── Portfolio.jsx        # Portfolio with P&L
│       │   ├── NewsHub.jsx          # News aggregation
│       │   ├── Reports.jsx          # Report generation
│       │   ├── DataPipeline.jsx     # Pipeline monitoring dashboard
│       │   └── PostgresControl.jsx  # PG control UI (start/stop, resources)
│       ├── components/
│       │   ├── Charts.jsx           # Price/volume charts
│       │   └── ScoreCard.jsx        # Score visualization
│       └── lib/
│           └── api.js               # API client with pipeline functions
│
├── Documentation/
│   ├── DEVELOPMENT_HISTORY.md                    # This document
│   ├── Database_Architecture_Plan.md             # 4-layer DB design
│   ├── Data_Sources_and_Extraction_Guide.md      # 160-field source mapping
│   ├── Technical-architecture-LLD-HLD.md         # System architecture
│   ├── StockPulse_Data_Extraction_System_Blueprint.md  # Extraction blueprint
│   ├── V2-Complete-Data-requirement-Claude-Offline_Loader.md  # 160 field spec
│   ├── MD folder/
│   │   ├── Stock_Analysis_Framework.md           # Scoring rules detail
│   │   ├── Stock_Analysis_Platform_Architecture.md
│   │   ├── Stock_Platform_Tech_Stack.md
│   │   └── missing components.md
│   └── *.docx                       # Word versions of above docs
│
└── memory/
    └── PRD.md                       # Product Requirements Document
```

---

## 6. API Endpoints Reference

### Stock Analysis
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/stocks` | GET | List all stocks with filters |
| `/api/stocks/{symbol}` | GET | Full stock analysis with scoring |
| `/api/stocks/{symbol}/llm-insight` | POST | AI-powered insights via GPT-4o |

### Market Data
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/market/overview` | GET | Indices, breadth, FII/DII |

### User Features
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/watchlist` | GET/POST/DELETE | Watchlist CRUD |
| `/api/portfolio` | GET/POST/PUT/DELETE | Portfolio CRUD |
| `/api/screener` | POST | Custom screening (PostgreSQL-optimized) |
| `/api/alerts` | GET/POST/DELETE | Price alerts CRUD |

### Data Extraction
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/extraction/status` | GET | Pipeline availability |
| `/api/extraction/fields` | GET | 160 field definitions |
| `/api/extraction/run` | POST | Trigger extraction |

### Data Pipeline (Groww API)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pipeline/status` | GET | Pipeline status & metrics |
| `/api/pipeline/test-api` | POST | Test Groww API connection |
| `/api/pipeline/run` | POST | Trigger extraction job |
| `/api/pipeline/scheduler/start` | POST | Start auto-scheduler |
| `/api/pipeline/scheduler/stop` | POST | Stop scheduler |
| `/api/pipeline/scheduler/config` | PUT | Update scheduler settings |
| `/api/pipeline/jobs` | GET | List extraction jobs |
| `/api/pipeline/jobs/{job_id}` | GET | Get job details |
| `/api/pipeline/history` | GET | Job history |
| `/api/pipeline/logs` | GET | Pipeline event logs |
| `/api/pipeline/metrics` | GET | Detailed API metrics |
| `/api/pipeline/data-summary` | GET | Extracted data summary |
| `/api/pipeline/default-symbols` | GET | Tracked symbols |
| `/api/pipeline/symbol-categories` | GET | Symbols by category |
| `/api/pipeline/symbols/add` | POST | Add new symbols |
| `/api/pipeline/symbols/remove` | POST | Remove symbols |

### Time-Series Data (14 endpoints)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/timeseries/stats` | GET | Row counts and pool stats for all 14 tables |
| `/api/timeseries/prices/{symbol}` | GET | Daily OHLCV |
| `/api/timeseries/derived-metrics/{symbol}` | GET | Derived daily metrics |
| `/api/timeseries/technicals/{symbol}` | GET | Technical indicators |
| `/api/timeseries/fundamentals/{symbol}` | GET | Quarterly fundamentals |
| `/api/timeseries/shareholding/{symbol}` | GET | Shareholding data |
| `/api/timeseries/valuation/{symbol}` | GET | Valuation ratios |
| `/api/timeseries/ml-features/{symbol}` | GET | ML features |
| `/api/timeseries/risk-metrics/{symbol}` | GET | Risk metrics |
| `/api/timeseries/corporate-actions/{symbol}` | GET | Corporate actions |
| `/api/timeseries/macro-indicators` | GET | Macro indicators |
| `/api/timeseries/derivatives/{symbol}` | GET | Derivatives data |
| `/api/timeseries/intraday/{symbol}` | GET | Intraday metrics |
| `/api/timeseries/weekly-metrics/{symbol}` | GET | Weekly metrics |

### PostgreSQL Control
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/database/postgres-control/status` | GET | PG running state, version, uptime |
| `/api/database/postgres-control/toggle` | POST | Start/stop Postgres |
| `/api/database/postgres-control/resources` | GET | CPU, RAM, storage, connections, pool |
| `/api/database/postgres-control/health` | GET | Quick health check |

### Database & Health
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Basic server health check |
| `/api/database/health` | GET | Comprehensive DB health (PG, Mongo, Redis, FS) |

### News & Backtest
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/news` | GET/POST | News articles CRUD |
| `/api/backtest` | GET/POST | Backtest results CRUD |

---

## 7. Database Architecture

### 4-Layer Hybrid Design

#### Layer 1: Redis (Hot Cache)
- **Purpose**: Real-time data, pub/sub for WebSocket, sorted sets for rankings
- **TTLs**: 60s prices, 300s analysis, 30s pipeline, 180s news
- **Patterns**: HASH (per-field reads), SORTED SET (top movers), PUB/SUB (price broadcasts)
- **Fallback**: Graceful degradation to MongoDB if Redis is unavailable

#### Layer 2: MongoDB (Entity Store)
- **Purpose**: Document storage for user data, extraction logs, news articles
- **Collections**: 10 collections with compound indexes
- **Driver**: Motor (async)
- **Key indexes**: symbol (unique on watchlist/portfolio), timestamp + symbol on logs

#### Layer 3: PostgreSQL (Time-Series Analytics)
- **Purpose**: OHLCV storage, technical indicators, fundamentals, derived metrics, valuation, risk, and more
- **Tables**: 14 tables with UNIQUE constraints on (symbol, date/quarter) and 40+ indexes
- **Driver**: asyncpg (async)
- **Key feature**: 7-table JOIN screener with ~50 filter/sort keys via COLUMN_MAP

#### Layer 4: Filesystem (Binary Artifacts)
- **Purpose**: Reports (PDF/Excel), data exports, ML model files
- **Directories**: `data/reports/`, `data/exports/`, `data/models/`, `data/cache/`

### Redis Cache Patterns

```
stock:{SYMBOL}          -> HASH   (current_price, volume, change, etc.)
top:gainers             -> ZSET   (symbol -> change_pct)
top:losers              -> ZSET   (symbol -> change_pct)
prices:{SYMBOL}         -> PUB/SUB channel
alerts:{SYMBOL}         -> PUB/SUB channel
analysis:{SYMBOL}       -> STRING (JSON, TTL 300s)
pipeline:status         -> STRING (JSON, TTL 30s)
news:latest             -> STRING (JSON, TTL 180s)
```

---

## 8. Scoring System

### 4-Tier Rule Hierarchy

```
+-------------------------------------------------------------+
| TIER 1: DEAL-BREAKERS (D1-D10)                              |
| If ANY triggered -> Score capped at 35, verdict = AVOID      |
+-------------------------------------------------------------+
| TIER 2: RISK PENALTIES (R1-R10)                              |
| Cumulative deductions from base score                        |
+-------------------------------------------------------------+
| TIER 3: QUALITY BOOSTERS (Q1-Q9)                             |
| Cumulative additions, capped at +30 total                    |
+-------------------------------------------------------------+
| TIER 4: ML ADJUSTMENT                                        |
| +/- 10 points based on ML model confidence                  |
+-------------------------------------------------------------+
```

### Score Interpretation

| Score Range | Verdict | Interpretation |
|-------------|---------|----------------|
| 80-100 | STRONG BUY | Excellent opportunity |
| 65-79 | BUY | Good candidate |
| 50-64 | HOLD | Neutral, wait for clarity |
| 35-49 | AVOID | Below average, risks exist |
| 0-34 | STRONG AVOID | Poor quality or deal-breaker |

### Investment Checklists

**Short-Term (10 items):** Price above 50-day SMA, RSI 30-70, volume confirms trend, no earnings in 2 weeks, sector strength, no negative catalysts, stock not halted (deal-breaker), volume > 100k (deal-breaker), clear support level, risk/reward >= 2:1

**Long-Term (13 items):** Revenue grown 3+ years, profitable, ROE > 15%, FCF positive & growing, D/E < 1.5, competitive moat, good management, industry tailwinds, PEG < 2, no fraud history (deal-breaker), no disruption threat (deal-breaker), interest coverage > 3x (deal-breaker), business understandable

---

## 9. Data Extraction Pipeline

### Groww API Pipeline Architecture

```
+-------------------------------------------------------------+
| GrowwAPIExtractor (grow_extractor.py)                        |
|   - TOTP auth via pyotp -> JWT access token                  |
|   - Token refresh with asyncio.Lock (race condition safe)    |
|   - Rate limiting: 10/sec, 300/min                           |
|   - Retry: 5 attempts with exponential backoff               |
|   - Bulk extraction: semaphore(5) for concurrency control    |
|   - Canonical field output matching persistence layer        |
+-------------------------------------------------------------+
| DataPipelineService (pipeline_service.py)                    |
|   - Scheduler: auto-start, configurable interval (15 min)   |
|   - Job management: create, track, history                   |
|   - 143 symbols across 3 categories                          |
|   - Persistence to PostgreSQL via TimeSeriesStore            |
|   - Logging & audit trail to MongoDB                         |
+-------------------------------------------------------------+
| TimeSeriesStore (timeseries_store.py)                         |
|   - 12 upsert methods for all 14 tables                      |
|   - 17+ query methods with filtering and pagination           |
|   - 7-table JOIN screener for /api/screener (~50 sort/filter)|
+-------------------------------------------------------------+
```

### Data Flow

```
Groww API -> GrowwAPIExtractor -> _transform_quote_data()
    -> DataPipelineService._persist_to_timeseries()
        -> TimeSeriesStore.upsert_price() [PostgreSQL]
    -> CacheService.set_stock_hash() [Redis]
    -> MongoDBStore.save_extraction_log() [MongoDB]
```

### 160 Data Fields by Category

| Category | Field Count | Primary Source |
|----------|-------------|----------------|
| Stock Master | 14 | NSE/BSE, Screener.in |
| Price & Volume | 13 | NSE Bhavcopy |
| Derived Metrics | 11 | Calculated from prices |
| Income Statement | 18 | Screener.in |
| Balance Sheet | 17 | Screener.in |
| Cash Flow | 8 | Screener.in |
| Financial Ratios | 11 | Calculated from financials |
| Valuation | 17 | Calculated (price + financials) |
| Shareholding | 10 | BSE Filings |
| Corporate Actions | 10 | BSE/NSE announcements |
| News & Sentiment | 8 | RSS Feeds + NLP |
| Technical Indicators | 15 | pandas-ta |
| Qualitative & Metadata | 8 | Manual/System |
| **Total** | **160** | |

---

## 10. Testing & Quality Assurance

### test_pipeline.py Modes

| Mode | Flag | What It Tests |
|------|------|---------------|
| DB Only | `--db-only` | MongoDB ping, Redis ping, PostgreSQL connect + table verification |
| API Only | `--api-only` | Groww TOTP auth, single quote, bulk quotes (5 symbols) |
| Full | `--all` | Complete pipeline: auth + extraction + PostgreSQL persistence |

### Test Results Summary

| Component | Tests | Passed | Status |
|-----------|-------|--------|--------|
| Deal-Breakers D1-D10 | 10 | 10 | Passed |
| Risk Penalties R1-R10 | 10 | 10 | Passed |
| Quality Boosters Q1-Q9 | 9 | 9 | Passed |
| Confidence Scoring | 4 | 4 | Passed |
| Investment Checklists | 23 | 23 | Passed |
| Extraction Pipeline | 3 | 3 | Passed |
| Python Syntax (all 9 backend files) | 9 | 9 | Passed |

---

## 11. Known Issues & Next Steps

### Immediate Next Steps (User Action Required)

| Step | Command | Purpose |
|------|---------|---------|
| 1. Install databases | `brew install postgresql mongodb-community redis` | Install DB software |
| 2. Start databases | `brew services start postgresql mongodb-community redis` | Start DB services |
| 3. Create `.env` file | Copy from `.env.example`, fill in credentials | Configure connections |
| 4. Run DB setup | `python setup_databases.py` | Create tables & collections |
| 5. Run tests | `python test_pipeline.py --db-only` | Verify DB connectivity |
| 6. Test Groww API | `python test_pipeline.py --api-only` | Verify API authentication |
| 7. Full test | `python test_pipeline.py --all` | End-to-end pipeline test |

### Future Development Phases

| Phase | Description | Status |
|-------|-------------|--------|
| Screener.in Extractor | Build scraper for 60+ fundamental fields | Planned |
| NSE Bhavcopy Automation | Daily OHLCV download via jugaad-data | Planned |
| BSE Shareholding Scraper | Quarterly shareholding pattern extraction | Planned |
| RSS News Aggregator | Moneycontrol, ET, BS feed integration | Planned |
| Sentiment Analysis | VADER/FinBERT for news sentiment scoring | Planned |
| pandas-ta Integration | Calculate 15 technical indicators from OHLCV | Planned |
| Frontend Integration | Connect frontend to live DB data (remove mock) | Planned |
| TimescaleDB Migration | Convert PostgreSQL to TimescaleDB for hypertables | Planned |
| ML Model Training | Train price prediction models on historical data | Planned |

---

## 12. Related Documentation

| Document | Location | Description |
|----------|----------|-------------|
| Database Architecture Plan | `Documentation/Database_Architecture_Plan.md` | 4-layer DB design details |
| Data Sources & Extraction Guide | `Documentation/Data_Sources_and_Extraction_Guide.md` | 160-field source mapping with code |
| V2 Data Requirements | `Documentation/V2-Complete-Data-requirement-Claude-Offline_Loader.md` | Complete 160-field specification |
| Technical Architecture (LLD/HLD) | `Documentation/Technical-architecture-LLD-HLD.md` | System design documents |
| Extraction Blueprint | `Documentation/StockPulse_Data_Extraction_System_Blueprint.md` | Extraction pipeline design |
| Scoring Framework | `Documentation/MD folder/Stock_Analysis_Framework.md` | Detailed scoring rules |
| Platform Architecture | `Documentation/MD folder/Stock_Analysis_Platform_Architecture.md` | Architecture overview |
| Tech Stack | `Documentation/MD folder/Stock_Platform_Tech_Stack.md` | Technology choices |
| PRD | `memory/PRD.md` | Product Requirements Document |

---

## Git History (Key Commits)

| Commit | Message | Session |
|--------|---------|---------|
| Initial commits | Core platform build (v1.0 + v2.0) | Sessions 1-2 |
| `1b239bf` | fix: Pipe extracted Groww live data into Redis cache | Session 3 |
| `d0a6830` | chore: add missing Redis cache to market overview & fix frontend linting | Session 3 |
| `de20dd7` | feat: Complete hybrid database implementation (Phases 1-4) | Session 5 |
| `f65cf5a` | Merge branch 'main' into claude/agitated-edison | Merge |
| `0a4f70b` | fix: Database setup rewrite, server cleanup, and Groww pipeline fixes | Session 6 |
| `d9b9b30` | docs: Add comprehensive data sources & extraction guide for all 160 fields | Session 7 |
| `0ead30c` | feat: MongoDB production-ready hardening - security, validation, backups | Session 8 |
| `69fbf00` | feat: add comprehensive Database Dashboard for monitoring & management | Session 8 |
| `9fc8cd5` | feat: complete Database Dashboard gap fixes - CRUD, charts, filters, docs | Session 8 |
| `82867c9` | feat: add Query Playground, Tools, Help Panel, Export, WebSocket, and theme toggle | Session 8 |
| `342aa25` | Merge pull request #9 from ShraddheyWamanSatpute/claude/mongodb-production-ready-0AkeH | Merge |

---

*Document maintained as part of StockPulse development history. Last updated: March 7, 2026.*

---

## 13. Current Status Summary

As of **March 2026**, the StockPulse system is in a strong **advanced-prototype** state, optimized for **local single-user use** with a clear path to future production deployment:

- **Frontend**
  - React SPA with 8 main pages: Dashboard, Stock Analyzer, Screener, Watchlist, Portfolio, News Hub, Reports, and Data Pipeline.
  - UI built with Tailwind + shadcn/ui; charts and scorecards wired to backend APIs (mock data by default, live data when pipeline + DBs are configured).
  - Database Dashboard UI (admin view) is available for future use once the backend dashboard API is enabled in your environment.

- **Backend & APIs**
  - FastAPI server exposes full feature set:
    - Stock analysis, screening, watchlist, portfolio, alerts, backtesting, PDF reports, and AI insights.
    - Extraction & Groww pipeline APIs, including scheduler and metrics.
    - Comprehensive `/api/database/health` and `/database/*` endpoints for database monitoring and admin.
  - For your current workflow, the system works fully with:
    - **Local MongoDB** (single node, localhost)
    - **Optional local Redis** (for caching) and **optional local PostgreSQL** (for time-series + screener). If they are not running, the app degrades gracefully to mock data and Mongo-only flows.

- **Databases**
  - **MongoDB**: Primary store for user data (watchlist, portfolio, alerts), pipeline jobs, extraction logs, quality reports, news, and backtest results. Indexes, backup script, and safety utilities are implemented and used.
  - **Redis**: Integrated cache layer for prices, analysis, pipeline status, and screener results; falls back to in-memory cache if Redis is not available.
  - **PostgreSQL**: Time-series + analytics layer fully expanded to 14 tables with 40+ indexes covering 270+ fields. 12 upsert methods, 17+ query methods, 7-table JOIN screener with ~50 filter/sort keys. Pipeline persists to 9 table categories. Derived metrics job computes daily returns, 52-week metrics, and weekly crossovers. PG Control UI provides start/stop toggle and resource monitoring. Fully operational when Postgres runs locally.
  - MongoDB configuration is **environment-aware**:
    - In your current **development/local** setup, `ENVIRONMENT` defaults to `development` and `MONGO_URL` safely defaults to `mongodb://localhost:27017`
    - In a future **production** setup, `MONGO_URL` will be required, must not use localhost, and the app will fail fast if Mongo is unreachable
  - Critical MongoDB collections are already configured with **majority write concern** (`w="majority", j=true`) and replica set health reporting is wired into `/api/database/health`, ready to be used when you move to a replica set.
  - All **production/replica-set guidance for MongoDB** is documented (checklist + runbooks) but **not required** in your current local-only setup.

- **Operations & Docs**
  - Detailed technical/functional documentation exists for architecture, databases, scoring, extraction, and data sources.
  - MongoDB production checklist and runbooks are ready for a future phase when you decide to host the system for other users or on cloud, without impacting the current local workflow.
