# Stock-Pulse Database Architecture Documentation

> **Project:** Stock-Pulse — AI/ML-powered Indian Stock Market Prediction & Analysis Platform
> **Generated:** 2026-03-16
> **Codebase Size:** ~24,500 lines of Python (backend)

---

## Table of Contents

1. [Database Architecture Overview](#1-database-architecture-overview)
2. [Completed Work](#2-completed-work)
3. [Pending / Incomplete Work](#3-pending--incomplete-work)
4. [Bugs / Risks / Gaps](#4-bugs--risks--gaps)
5. [Recommended Improvements](#5-recommended-improvements)
6. [Production Readiness Assessment](#6-production-readiness-assessment)
7. [Actionable Task List](#7-actionable-task-list)

---

## 1. Database Architecture Overview

Stock-Pulse employs a **polyglot persistence architecture** with three database systems, each serving a distinct role:

### 1.1 PostgreSQL (TimescaleDB-compatible) — Time-Series Analytics Engine

| Attribute | Value |
|-----------|-------|
| **Image** | `postgres:16-alpine` |
| **Port** | 5432 |
| **Database** | `stockpulse_ts` |
| **Driver** | `asyncpg` (async) |
| **Pool** | min=2, max=10, command_timeout=30s |
| **DSN** | `TIMESERIES_DSN=postgresql://localhost:5432/stockpulse_ts` |

**Role:** Stores all time-series financial data — daily prices, technical indicators, derived metrics, fundamentals, risk metrics, valuations, derivatives, macro indicators, and intraday/weekly metrics. Optimized for analytical queries with 40+ indexes and optional TimescaleDB hypertable compression.

**Key Service:** `backend/services/timeseries_store.py` (1,394 lines)

### 1.2 MongoDB — Document Store & Entity Database

| Attribute | Value |
|-----------|-------|
| **Image** | `mongo:7` |
| **Port** | 27017 |
| **Database** | `stockpulse` |
| **Driver** | `motor` (async) / `pymongo` (sync for backups) |
| **Pool** | maxPoolSize=20, minPoolSize=1 |
| **URL** | `MONGO_URL=mongodb://localhost:27017` |

**Role:** Stores user-facing data (watchlists, portfolios, alerts), comprehensive stock entity documents (160+ fields per stock), extraction pipeline logs, data quality reports, news articles with sentiment, and backtest results. Uses schema validation and write concerns for data integrity.

**Key Service:** `backend/data_extraction/storage/mongodb_store.py` (295 lines)

### 1.3 Redis — Hot Cache & Real-Time Messaging

| Attribute | Value |
|-----------|-------|
| **Image** | `redis:7-alpine` |
| **Port** | 6379 |
| **Driver** | `redis[hiredis]` |
| **Pool** | max_connections=10 |
| **Memory** | 256MB (dev), allkeys-lru eviction |
| **URL** | `REDIS_URL=redis://localhost:6379` |

**Role:** Provides sub-second caching for stock prices (60s TTL), analysis results (300s TTL), and market data. Supports PUB/SUB for real-time price broadcasting, SORTED SETs for top gainers/losers, LIST-based alert queuing (max 1,000), and HASH structures for per-stock field retrieval. Includes bounded in-memory LRU fallback (10,000 keys) when Redis is unavailable.

**Key Service:** `backend/services/cache_service.py` (707 lines)

### 1.4 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                         │
└─────────────────────────────┬───────────────────────────────────┘
                              │ HTTP / WebSocket
┌─────────────────────────────▼───────────────────────────────────┐
│                     FastAPI Backend (server.py)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │   Routes     │  │  Services    │  │  Background Jobs       │ │
│  │  /api/*      │  │  scoring     │  │  derive_metrics        │ │
│  │  /database/* │  │  alerts      │  │  derivatives_job       │ │
│  │  /backtest/* │  │  market_data │  │  intraday_metrics_job  │ │
│  │  /pipeline/* │  │  pdf_service │  │  macro_indicators_job  │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬─────────────┘ │
│         │                 │                      │               │
│  ┌──────▼─────────────────▼──────────────────────▼─────────────┐ │
│  │              Database Access Layer                           │ │
│  │  ┌─────────────────┐ ┌──────────────┐ ┌──────────────────┐ │ │
│  │  │ TimeSeriesStore  │ │ MongoDBStore  │ │  CacheService    │ │ │
│  │  │ (asyncpg)        │ │ (motor)       │ │  (redis+LRU)    │ │ │
│  │  └────────┬─────────┘ └──────┬────────┘ └───────┬─────────┘ │ │
│  └───────────┼──────────────────┼───────────────────┼──────────┘ │
└──────────────┼──────────────────┼───────────────────┼────────────┘
               │                  │                   │
    ┌──────────▼──────┐  ┌───────▼────────┐  ┌───────▼────────┐
    │  PostgreSQL 16   │  │  MongoDB 7     │  │  Redis 7       │
    │  (TimescaleDB)   │  │                │  │                │
    │  14 tables       │  │  10 collections│  │  Hot cache     │
    │  270+ fields     │  │  Schema valid. │  │  PUB/SUB       │
    │  40+ indexes     │  │  Write concern │  │  Sorted sets   │
    └─────────────────┘  └────────────────┘  └────────────────┘
```

### 1.5 Data Flow

```
External Sources (NSE, Yahoo Finance, Screener.in, Groww)
    │
    ▼
Data Extraction Pipeline (orchestrator.py)
    │
    ├──► MongoDB: stock_data (160+ fields), price_history, extraction_log
    │
    ▼
Background Jobs (derive_metrics, derivatives, intraday, macro)
    │
    ├──► PostgreSQL: derived_metrics_daily, technical_indicators, risk_metrics, etc.
    │
    ▼
Cache Layer (cache_service.py)
    │
    ├──► Redis: price caches, analysis results, market overview
    │
    ▼
API Endpoints → Frontend
```

---

## 2. Completed Work

### 2.1 PostgreSQL — 14 Time-Series Tables

All tables are defined in `backend/setup_databases.py` with `CREATE TABLE IF NOT EXISTS`.

| # | Table | Fields | Purpose | Primary Key |
|---|-------|--------|---------|-------------|
| 1 | `prices_daily` | 17 | OHLCV + delivery data | (symbol, date) |
| 2 | `derived_metrics_daily` | 13 | Daily returns, 52-week metrics, volume ratio | (symbol, date) |
| 3 | `technical_indicators` | 25 | SMA, EMA, RSI, MACD, Bollinger, Ichimoku, Stochastic, ATR, ADX, OBV, CCI, Williams %R, CMF | (symbol, date) |
| 4 | `ml_features_daily` | 20 | Volatility, momentum, macro context, sentiment | (symbol, date) |
| 5 | `risk_metrics` | 8 | Beta, Sharpe ratio, drawdown, volatility | (symbol, date) |
| 6 | `valuation_daily` | 18 | P/E, P/B, EV/EBITDA, dividend yield, FCF yield | (symbol, date) |
| 7 | `fundamentals_quarterly` | 51 | Income statement, balance sheet, cash flow, ratios, analyst ratings | (symbol, period_end, period_type) |
| 8 | `shareholding_quarterly` | 11 | Promoter, FII, DII, public holdings | (symbol, quarter_end) |
| 9 | `corporate_actions` | 10 | Dividends, splits, bonuses, buybacks | (id) SERIAL |
| 10 | `macro_indicators` | 8 | CPI, IIP, RBI repo rate, FX, commodity prices | (date) |
| 11 | `derivatives_daily` | 15 | F&O OI, futures, options, PCR, IV, max pain | (symbol, date) |
| 12 | `intraday_metrics` | 7 | Hourly RSI, MACD, VWAP, sectoral heatmap, VIX | (symbol, timestamp) |
| 13 | `weekly_metrics` | 4 | Weekly SMA crossover, support/resistance, Google trends | (symbol, week_start) |
| 14 | `schema_migrations` | 4 | Migration tracking and versioning | (id) SERIAL |

**Indexing:** 40+ indexes across all tables for symbol, date, period_type, and composite filtering.

**TimescaleDB Optimization (if extension available):**
- `prices_daily` and `technical_indicators` converted to hypertables (1-month chunks)
- Compression enabled with segmentation by symbol, ordered by date DESC
- Compression policy: data older than 6 months is compressed

### 2.2 MongoDB — 10 Collections with Schema Validation

All collections are defined in `backend/setup_databases.py` with indexes and schema validation.

| # | Collection | Purpose | Key Indexes | TTL |
|---|-----------|---------|-------------|-----|
| 1 | `watchlist` | User stock watchlist | symbol (unique) | — |
| 2 | `portfolio` | Holdings & transactions | symbol (unique) | — |
| 3 | `alerts` | Price alert rules | id (unique), status, symbol | — |
| 4 | `stock_data` | Comprehensive stock entities (160+ fields) | symbol (unique), last_updated, sector, market_cap | — |
| 5 | `price_history` | OHLCV time-series | (symbol, date) compound unique | — |
| 6 | `extraction_log` | Pipeline run audit trail | (symbol, source, started_at), status | 90 days |
| 7 | `quality_reports` | Data quality assessments | (symbol, generated_at) | 90 days |
| 8 | `pipeline_jobs` | Job execution records | job_id (unique), created_at, status | 90 days |
| 9 | `news_articles` | News + sentiment analysis | id (unique, sparse), published_date, related_stocks | — |
| 10 | `backtest_results` | Strategy backtest outputs | id (unique, sparse), (symbol, strategy, created_at) | — |

**Schema Validation Examples:**
- `watchlist`: symbol (1-20 chars, uppercase/digits/&_.-), name, target_price, stop_loss
- `alerts`: id format `alert_<12-hex-chars>`, conditions enum, priority enum, status enum
- `portfolio`: symbol, name, quantity, avg_buy_price (all required)

**Write Concerns:** `majority` + journaled for critical collections (watchlist, portfolio, alerts, pipeline_jobs, news_articles, backtest_results).

### 2.3 Redis — Cache Layer with Fallback

**File:** `backend/services/cache_service.py` (707 lines)

| Feature | Implementation |
|---------|---------------|
| Connection Pool | redis-py with configurable timeouts |
| In-Memory Fallback | LRU cache (10,000 keys) when Redis unavailable |
| TTL Management | Per-domain TTLs (60s–300s) |
| Data Structures | STRINGs, HASHes, SORTED SETs, LISTs, PUB/SUB |
| Health Monitoring | Periodic ping every 60s with reconnection retry |
| Stats Tracking | Hits, misses, errors, hit rate percentage |
| Pattern Deletion | SCAN-based non-blocking key removal |
| TLS Support | Auto-detection via `rediss://` scheme |

**Cache Key Scheme:**
```
stockpulse:price:<SYMBOL>       → Live quotes (60s TTL)
stockpulse:analysis:<SYMBOL>    → Analysis results (300s TTL)
stockpulse:stock:<SYMBOL>       → Stock data HASH
stockpulse:stock_list            → All stocks list (300s TTL)
stockpulse:pipeline:*            → Pipeline status (30s TTL)
stockpulse:news:*                → News items (180s TTL)
stockpulse:market:overview       → Market overview
stockpulse:top_gainers           → SORTED SET by %
stockpulse:top_losers            → SORTED SET by %
```

### 2.4 Data Ingestion Pipelines

**Orchestrator:** `backend/data_extraction/pipeline/orchestrator.py`

| Extractor | Source | Data |
|-----------|--------|------|
| `NSEBhavcopyExtractor` | NSE India | Daily bhavcopy OHLCV files |
| `YFinanceExtractor` | Yahoo Finance | Quotes & historical data |
| `ScreenerExtractor` | Screener.in | Fundamentals & financials |
| `GrowExtractor` | Groww API | Market data (TOTP-based auth) |

**Pipeline Flow:**
1. Extract from source → 2. Validate data → 3. Calculate metrics → 4. Compute technicals → 5. Assess quality → 6. Store to MongoDB

**Storage Layer:** `backend/data_extraction/storage/mongodb_store.py`
- `upsert_stock_data()` — Full stock record (160+ fields)
- `upsert_price_history()` — Batch price records (bulk_write, 500-record chunks)
- `log_extraction()` — Pipeline audit trail
- `upsert_quality_report()` — Data quality metrics

### 2.5 Background Jobs (PostgreSQL Writers)

| Job | File | Frequency | Target Table |
|-----|------|-----------|-------------|
| Derived Metrics | `backend/jobs/derive_metrics.py` | Daily/on-demand | `derived_metrics_daily` |
| Derivatives | `backend/jobs/derivatives_job.py` | Daily | `derivatives_daily` |
| Intraday Metrics | `backend/jobs/intraday_metrics_job.py` | Hourly | `intraday_metrics` |
| Macro Indicators | `backend/jobs/macro_indicators_job.py` | Daily | `macro_indicators` |

### 2.6 Database Monitoring & Administration

| File | Purpose |
|------|---------|
| `backend/services/db_dashboard_service.py` (1,463 lines) | Database introspection, stats, monitoring |
| `backend/services/pg_control_service.py` | PostgreSQL start/stop/resource monitoring |
| `backend/routes/db_dashboard.py` (592 lines) | REST API for database dashboard |
| `backend/routes/pg_control.py` | PostgreSQL control API |
| `backend/scripts/backup_mongodb.py` | Automated MongoDB backup with rotation |

**Dashboard Endpoints:**
- `GET /database/overview` — MongoDB collections, PostgreSQL tables, Redis stats
- `GET /database/data-flow` — Data pipeline visualization
- `GET /database/collections` — MongoDB introspection
- `GET /database/tables` — PostgreSQL table introspection

### 2.7 Security Utilities

**File:** `backend/services/mongo_utils.py` — MongoDB injection prevention and input sanitization.

### 2.8 Database Setup & Initialization

**File:** `backend/setup_databases.py`

```bash
python setup_databases.py              # All databases
python setup_databases.py --postgres   # PostgreSQL only
python setup_databases.py --mongo      # MongoDB only
python setup_databases.py --redis      # Redis check only
python setup_databases.py --check      # Read-only verification
```

### 2.9 Docker Compose Services

**File:** `docker-compose.yml`

```yaml
services:
  redis:    redis:7-alpine    → port 6379 (redis-data volume, health check)
  mongo:    mongo:7           → port 27017 (mongo-data volume, health check)
  postgres: postgres:16-alpine → port 5432 (pg-data volume, health check)
  backend:  depends_on all three (healthy)
```

### 2.10 Database Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `asyncpg` | 0.31.0 | PostgreSQL async driver |
| `motor` | 3.3.1 | MongoDB async driver |
| `pymongo` | 4.5.0 | MongoDB sync (backups) |
| `redis[hiredis]` | 7.2.0 | Redis with C parser |
| `fakeredis` | 2.21.0 | Redis testing/fallback |

---

## 3. Pending / Incomplete Work

### 3.1 Placeholder Derivatives Data — Addressed (status indicator)

**File:** `backend/jobs/derivatives_job.py` (line 194)

When NSE F&O bhavcopy data is unavailable, the job creates **placeholder rows** with NULL fields in the `derivatives_daily` table. A **status indicator** is now implemented:

- **`derivatives_daily.data_source`** column: `'nse_bhavcopy'` = real F&O from NSE bhavcopy; `'placeholder'` = fallback row (no F&O data). Consumers can filter by `data_source` or use the API query `real_data_only=true` to exclude placeholders.
- **Migration:** `setup_databases.py` adds the column on existing DBs and backfills `nse_bhavcopy` where any F&O field is non-null.

**Remaining:** Reliable NSE F&O data source (archives.nseindia.com) remains the primary source; no alternative provider added yet.

### 3.2 Mock Disruption Risk in Scoring Engine

**File:** `backend/services/scoring_engine.py` (line 1445)

```python
# Mock - assume most companies pass
disruption_risk = stock_data.get("disruption_risk", "Low")
```

The disruption risk assessment defaults to "Low" for all companies — no actual disruption analysis is implemented.

**What's Missing:** Real disruption risk model based on industry trends, competition, technology shifts.

### 3.3 PDF Service — Optional Dependency (Addressed)

**File:** `backend/services/pdf_service.py` (lines 29-42)

PDF report generation uses ReportLab when installed and exposes `is_pdf_available()`; if ReportLab is missing, stub classes are used and the `/reports/generate-pdf` endpoint returns 503 with a clear message.

- **Dependency:** `reportlab` is now explicitly present in `backend/requirements.txt` under `# PDF Generation`. In production, installing these requirements makes the feature fully functional; in dev it degrades gracefully.
- **Behavior:** Clients can detect availability via the 503 error or by calling internal helpers.

### 3.4 Backtesting Service — Optional Dependency (Feature flag added)

**File:** `backend/server.py` (lines 1621-1672)

Backtesting imports `services/backtesting_service` and `models/backtest_models` and exposes three endpoints. A clear **feature flag** has been added:

- **Env flag:** `BACKTESTING_ENABLED` (default: `true`). If set to `false`/`0`/`no`, `BACKTEST_AVAILABLE` is forced to `False` even when imports succeed.
- **Behavior when disabled or missing deps:** All backtest endpoints return HTTP 503 with guidance: *"Ensure BACKTESTING_ENABLED is true and dependencies are installed."*

This makes backtesting clearly controllable per environment while remaining optional in deployments that don't need it.

### 3.5 Schema Migrations — Lightweight Framework + Alembic Baseline

**Files:** `backend/setup_databases.py`, `alembic.ini`, `backend/alembic/*`

The project now has two complementary layers for schema migrations:

- **Lightweight in-app framework (existing):**
  - `POSTGRESQL_SCHEMA` still creates all tables using `CREATE TABLE IF NOT EXISTS`, including `schema_migrations` and an initial version row `v1.0.0`.
  - A `MIGRATIONS` list defines ordered migrations as `(version, description, sql)` tuples (e.g. `v1.1.0_derivatives_data_source` for `derivatives_daily.data_source`).
  - `setup_postgresql()` applies each migration transactionally if its `version` is not yet present in `schema_migrations`.

- **Alembic baseline (for future evolution):**
  - `alembic.ini` + `backend/alembic/env.py` configure Alembic to use `TIMESERIES_DSN` for the PostgreSQL URL.
  - `backend/alembic/versions/v1_0_0_baseline.py` is a no-op baseline revision that treats the current schema as Alembic version `v1_0_0_baseline`.
  - Future schema changes should be added as new Alembic revisions under `backend/alembic/versions/`, enabling version-controlled, reversible migrations (and offline SQL generation when needed).

In practice, `setup_databases.py` remains the primary initializer for dev/test environments, while Alembic provides a production-ready path for ongoing schema evolution.

### 3.6 PostgreSQL Backup Strategy — Implemented

- **Backup Script:** `backend/scripts/backup_postgres.py`
  - Uses `pg_dump` against `TIMESERIES_DSN` to create timestamped logical backups (custom format), with optional gzip compression and automatic rotation (keep last N files, default 7).
  - Usage examples:
    - `python scripts/backup_postgres.py` — default backup to `./backups/postgres`, keep 7 copies.
    - `python scripts/backup_postgres.py --keep 14` — keep 14 copies.
    - `python scripts/backup_postgres.py --output /mnt/backups/pg` — custom directory.
    - `python scripts/backup_postgres.py --check` — verify `pg_dump` and paths only.

- **WAL / PITR (operational note):**
  - For full point-in-time recovery, production operators should also enable PostgreSQL WAL archiving (e.g. `archive_mode=on`, `archive_command` to ship WAL to durable storage) and schedule this script via cron or a job runner.
  - This repo does not hard-code `postgresql.conf`, but the backup script and env-based DSN are designed to integrate with such a WAL/PITR setup.

### 3.7 ML Features Pipeline — Implemented (Baseline Job)

The `ml_features_daily` table (20+ fields for volatility, momentum, macro context, sentiment) now has a **baseline background job**:

- **Job:** `backend/jobs/ml_features_job.py`
  - Reads `prices_daily` for the last N days (default 60) and derives:
    - `realized_volatility_10d`, `realized_volatility_20d` (std-dev of daily returns)
    - `return_1d_pct`, `return_3d_pct`, `return_10d_pct`
    - `price_vs_sma20_pct`, `price_vs_sma50_pct`
    - `volume_zscore` (20-day window)
    - `trading_day_of_week`
  - Leaves more advanced context fields (`momentum_rank_sector`, macro/sentiment fields) as NULL for now, to be enriched by upstream ETL when available.
  - Uses `TimeSeriesStore.upsert_ml_features()` for persistence.

- **API Trigger:** `POST /jobs/run/ml-features?days=60`
  - Runs the job for the last `days` calendar days (max 365) and returns `{ job: "ml_features_daily", records_upserted: N }`.

This provides a consistent, automated minimum ML feature set directly from raw price history, closing the previously identified gap in the pipeline.

### 3.8 Valuation Pipeline — Implemented (Baseline Job)

The `valuation_daily` table now has a **baseline valuation job** that recomputes metrics from fundamentals and daily data:

- **Job:** `backend/jobs/valuation_job.py`
  - For a target date or last N trading days, it:
    - Reads latest `fundamentals_quarterly` per symbol (EPS, book value, FCF, net_profit, total_equity).
    - Reads `derived_metrics_daily` snapshot for the same date(s) (price, market_cap, P/E, P/B, PS, dividend_yield, sector averages, etc.).
    - Computes or backfills:
      - `pe_ratio` (price/EPS when missing) and `earnings_yield` (1/PE),
      - `pb_ratio` (price/book when missing),
      - `fcf_yield` (FCF / market_cap when available),
      - and uses existing EV/EBITDA / EV/Sales fields from daily metrics when present.
  - Persists via `TimeSeriesStore.upsert_valuation()`.

- **API Trigger:** `POST /jobs/run/valuation`
  - Query params:
    - `date` (optional, `YYYY-MM-DD`) — recompute for a single trading date.
    - `days` (optional) — recompute for last N trading days (based on `prices_daily`).
  - Response: `{ job: "valuation_daily", records_upserted: N }`.

This closes the gap by providing an automated, recomputable valuation layer that can be run periodically or on demand, independent of upstream extractors.

### 3.9 Shareholding Pipeline — Implemented (MongoDB → PostgreSQL Sync)

The `shareholding_quarterly` table (11 fields) is now populated via a dedicated job that syncs from the existing shareholding extraction:

- **Extractor:** `backend/data_extraction/extractors/screener_extractor.py`
  - Parses the Screener.in `#shareholding` section into `FinancialData.shareholding_history` (a list of period rows with Promoters/FIIs/DIIs/Public columns).
  - This is already stored in MongoDB `stock_data.shareholding_history` by the extraction pipeline.

- **Job:** `backend/jobs/shareholding_job.py`
  - Reads `stock_data` documents from MongoDB with non-empty `shareholding_history` (optionally filtered by `--symbol`).
  - Normalizes each history entry into `shareholding_quarterly` schema:
    - Parses period labels like `Mar 2024` into `quarter_end` dates.
    - Maps Promoters/FIIs/DIIs/Public percentages plus derived fields like `promoter_holding_change`, `fii_holding_change`, `num_shareholders`, `mf_holding`, `insurance_holding` when available.
  - Upserts into PostgreSQL via `TimeSeriesStore.upsert_shareholding()`, keeping the latest ~8 quarters per symbol.

- **API Trigger:** `POST /jobs/run/shareholding`
  - Optional `symbol` query parameter restricts sync to a single stock.
  - Response: `{ job: "shareholding_quarterly", records_upserted: N }`.

Together with the existing Screener extractor, this provides a complete, automated shareholding pipeline from source HTML → MongoDB → PostgreSQL.

### 3.10 Corporate Actions Pipeline — Implemented via Main Extraction Pipeline

The `corporate_actions` table is now fed by the existing extraction + pipeline flow:

- **Data model:** `backend/data_extraction/models/extraction_models.py`
  - `StockDataRecord.corporate_actions` holds extracted corporate action fields (dividends, splits, bonuses, rights, buybacks, next_earnings_date, etc.).
  - Cleaner/validation passes handle this category alongside others.

- **Pipeline writer:** `backend/services/pipeline_service.py`
  - When an extracted record contains corporate action fields (`dividend_per_share`, `stock_split_ratio`, `bonus_ratio`, `action_type`, etc.), the pipeline builds `corporate_records` and calls:
    - `TimeSeriesStore.upsert_corporate_action(rec)` for each record.
  - Logs `"pg_corporate_actions_upserted"` with the count written.

- **Store + API:** `backend/services/timeseries_store.py` and `backend/server.py`
  - `upsert_corporate_action()` persists into `corporate_actions` with appropriate conflict handling.
  - `GET /timeseries/corporate-actions/{symbol}` exposes corporate actions from PostgreSQL.

Corporate actions are therefore ingested automatically whenever the main extraction pipeline runs and emits those fields, so a separate dedicated job is not required.

---

## 4. Bugs / Risks / Gaps

### 4.1 CRITICAL — SQL Injection via String Formatting

**Files:**
- `backend/services/timeseries_store.py` — Lines 618, 1069, 1364, 1366
- `backend/services/db_dashboard_service.py` — Lines 517, 519

**Issue:** Several queries use f-string formatting instead of parameterized queries:

```python
# timeseries_store.py:618 — VULNERABLE
query = f"SELECT * FROM derived_metrics_daily WHERE {where} ORDER BY date DESC LIMIT {limit}"

# timeseries_store.py:1364 — VULNERABLE
row_count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")

# db_dashboard_service.py:519 — ORDER BY injection risk
rows = await conn.fetch(f"SELECT * FROM {name} ORDER BY {order_by} LIMIT $1 OFFSET $2", ...)
```

**Impact:** Potential SQL injection if table names or query fragments are derived from user input without proper whitelisting.

**Fix:** Use parameterized queries exclusively. Whitelist valid table names. Use `sql.Identifier()` for dynamic identifiers.

### 4.2 CRITICAL — Unsafe User SQL Execution in Query Playground

**File:** `backend/services/db_dashboard_service.py` — Line 1328

```python
rows = await conn.fetch(f"{sql} LIMIT {limit}")
```

The query playground allows user-submitted SQL with only simplistic keyword blocking (line 1319-1322). Keyword blocking can be bypassed with comments, whitespace, or encoding tricks.

**Impact:** Potential data exfiltration or denial of service via crafted queries.

**Fix:** Implement proper SQL parsing, statement-level ACL, per-query timeout (`SET statement_timeout`), and consider removing this feature from production.

### 4.3 HIGH — Race Condition in Derived Metrics Computation

**File:** `backend/jobs/derive_metrics.py` — Lines 78-149

No locking mechanism prevents concurrent job execution for the same symbols. Two simultaneous runs will both fetch prices and upsert metrics, potentially causing conflicting data.

**Impact:** Data inconsistency during concurrent job execution.

**Fix:** Implement advisory locks (`pg_advisory_lock`) or a job queue (e.g., Celery, ARQ) with single-worker guarantee per symbol.

### 4.4 HIGH — N+1 Query Pattern in Dashboard

**File:** `backend/services/db_dashboard_service.py` — Lines 1372-1375

```python
"total_docs": sum([await self.db[c].count_documents({}) for c in await self.db.list_collection_names()])
```

Sequentially counts documents across all collections. With 10+ collections, this creates unnecessary latency.

**Impact:** Slow dashboard loading under load.

**Fix:** Use `asyncio.gather()` for parallel counts, or cache the aggregate count.

### 4.5 MEDIUM — Silent Exception Swallowing

**Files:** Multiple (20+ locations)

Bare `except Exception: pass` blocks in:
- `backend/services/db_dashboard_service.py` — Lines 313, 431, 860, 874, 1033, 1052, 1073, 1093, 1117, 1378, 1395, 1407
- `backend/services/cache_service.py` — Lines 376, 388, 705
- `backend/server.py` — Lines 344, 384
- `backend/services/pg_control_service.py` — Lines 72, 100

**Impact:** Database errors silently swallowed; debugging production issues becomes extremely difficult.

**Fix:** Log at WARNING/ERROR level with `exc_info=True` instead of using `pass`. Reserve `pass` only for truly expected exceptions (e.g., `CancelledError`).

### 4.6 MEDIUM — Missing Transaction Coordination in Batch Writes

**File:** `backend/data_extraction/storage/mongodb_store.py` — Lines 143-165

`bulk_write` processes in 500-record chunks without transaction coordination across batches. A failure between chunks leaves partially written data.

**Impact:** Inconsistent price history state after partial failures.

**Fix:** Use MongoDB transactions (requires replica set) or implement idempotent retry logic with batch tracking.

### 4.7 MEDIUM — No Retry Logic for Transient Database Failures

**Files:** All job files (`derive_metrics.py`, `derivatives_job.py`, `intraday_metrics_job.py`, `macro_indicators_job.py`)

When a database operation fails, the job logs a warning and moves to the next symbol. No retry with exponential backoff.

**Impact:** Transient network issues cause silent data gaps.

**Fix:** Implement retry decorator with exponential backoff (e.g., `tenacity` library) for all database writes.

### 4.8 MEDIUM — No Query Timeout in Dashboard SQL

**File:** `backend/services/db_dashboard_service.py` — Lines 1306-1349

User-submitted queries have no per-statement timeout. A crafted query (e.g., cross-join) could exhaust all connections.

**Impact:** Connection pool exhaustion, denial of service.

**Fix:** Set `statement_timeout` before executing user queries: `await conn.execute("SET statement_timeout = '5s'")`.

### 4.9 MEDIUM — Unbounded Symbol List Query

**File:** `backend/data_extraction/storage/mongodb_store.py` — Lines 101-103

```python
docs = await cursor.to_list(length=5000)
```

Hard-coded limit of 5,000 with no pagination. If symbols exceed 5,000, data is silently truncated.

**Impact:** Missing symbols in large-scale deployments.

**Fix:** Implement proper pagination or increase limit with warning logs.

### 4.10 LOW — Missing Input Validation Before PostgreSQL Writes

**File:** `backend/services/timeseries_store.py` — Lines 97-100

Symbol and date values are not validated for format or range before insertion. Malformed data could be written.

**Impact:** Downstream analysis failures from bad data.

**Fix:** Add input validation (symbol format, date range checks) before upserts.

### 4.11 LOW — Redis Connection Not Always Closed on Shutdown

**File:** `backend/services/cache_service.py` — Lines 382-388

The `close()` method exists but may not be called in all shutdown paths. No explicit flush of the in-memory fallback cache.

**Impact:** Minimal — connections are cleaned up by the OS, but graceful shutdown is preferred.

---

## 5. Recommended Improvements

### 5.1 Implement Alembic for Schema Migrations (High Priority)

The current `CREATE TABLE IF NOT EXISTS` approach cannot handle schema evolution (adding columns, changing types, renaming). Adopt [Alembic](https://alembic.sqlalchemy.org/) with asyncpg support for version-controlled, reversible migrations.

### 5.2 Add PostgreSQL Backup Automation (High Priority)

Create a `backup_postgresql.py` script mirroring the existing MongoDB backup system:
- Use `pg_dump` for logical backups
- Implement backup rotation (keep last N)
- Add WAL archiving for point-in-time recovery in production

### 5.3 Implement Connection Pool Monitoring with Alerts (Medium Priority)

The pool stats are collected but not acted upon. Add threshold-based alerting:
- Alert when free connections < 20% of max
- Alert when avg query time exceeds 5s
- Expose metrics via Prometheus endpoint for Grafana dashboards

### 5.4 Add Read Replicas for Analytics Queries (Low Priority)

The dashboard and analytics queries run on the same PostgreSQL instance as writes. For production scale, configure read replicas to offload analytical queries and prevent write contention.

---

## 6. Production Readiness Assessment

### Overall Status: **Partially Ready**

| Category | Status | Notes |
|----------|--------|-------|
| Schema Design | **Ready** | 14 PostgreSQL tables, 10 MongoDB collections, comprehensive field coverage |
| Indexing | **Mostly Ready** | 40+ PostgreSQL indexes, MongoDB indexes with TTL; could add more for specific query patterns |
| Connection Pooling | **Ready** | asyncpg, motor, redis-py all properly pooled |
| Caching | **Ready** | Redis + in-memory LRU fallback, per-domain TTLs |
| Data Ingestion | **Partially Ready** | 4 extractors working; 4 tables lack pipelines (ml_features, valuation, shareholding, corporate_actions) |
| Error Handling | **Partially Ready** | Graceful degradation exists but too many silent exception handlers |
| Security | **Not Ready** | SQL injection risks in f-string queries and query playground |
| Migrations | **Not Ready** | No formal migration system; schema evolution impossible |
| Backups | **Partially Ready** | MongoDB backup exists; PostgreSQL backup missing |
| Monitoring | **Partially Ready** | Dashboard exists but lacks alerting and Prometheus integration |
| Transaction Safety | **Partially Ready** | Some transactions used; batch writes lack cross-batch coordination |
| Retry Logic | **Not Ready** | No retry mechanism for transient failures in jobs |

### What Must Be Completed Before Production

1. **Fix SQL injection vulnerabilities** — Use parameterized queries everywhere
2. **Secure or remove the query playground** — It's a significant attack surface
3. **Implement migration system** — Cannot evolve schema without Alembic or equivalent
4. **Add PostgreSQL backup automation** — Data loss risk without backups
5. **Implement retry logic in jobs** — Transient failures cause silent data gaps
6. **Add per-query timeouts** — Prevent connection pool exhaustion
7. **Replace silent exception handlers** — Critical for production debugging

---

## 7. Actionable Task List

### High Priority — Critical for Production

| # | Task | Files Affected | Effort |
|---|------|---------------|--------|
| H1 | Fix SQL injection: replace all f-string queries with parameterized queries | `timeseries_store.py`, `db_dashboard_service.py` | Medium |
| H2 | Secure query playground: add `statement_timeout`, proper SQL parsing, or remove from production | `db_dashboard_service.py` | Medium |
| H3 | Implement Alembic migration system with initial migration from current schema | New: `alembic/`, `alembic.ini` | Medium |
| H4 | Create PostgreSQL backup script with rotation | New: `scripts/backup_postgresql.py` | Low |
| H5 | Add retry logic with exponential backoff to all background jobs | `derive_metrics.py`, `derivatives_job.py`, `intraday_metrics_job.py`, `macro_indicators_job.py` | Medium |
| H6 | Add advisory locks to prevent concurrent job execution per symbol | `derive_metrics.py` | Low |
| H7 | Replace silent `except: pass` blocks with proper error logging | Multiple service files | Low |

### Medium Priority — Stability & Performance

| # | Task | Files Affected | Effort |
|---|------|---------------|--------|
| M1 | Implement `ml_features_daily` computation job | New: `jobs/ml_features_job.py` | High |
| M2 | Implement `valuation_daily` computation job | New: `jobs/valuation_job.py` | Medium |
| M3 | Add per-query timeout enforcement in dashboard queries | `db_dashboard_service.py` | Low |
| M4 | Fix N+1 pattern: parallelize collection counts with `asyncio.gather()` | `db_dashboard_service.py` | Low |
| M5 | Add MongoDB transaction support for batch price writes | `mongodb_store.py` | Medium |
| M6 | Add connection pool exhaustion alerts | `timeseries_store.py`, `cache_service.py` | Medium |
| M7 | Implement data validation layer before all database writes | `timeseries_store.py`, `mongodb_store.py` | Medium |

### Low Priority — Enhancements

| # | Task | Files Affected | Effort |
|---|------|---------------|--------|
| L1 | Implement `shareholding_quarterly` data pipeline | New: extractor + job | High |
| L2 | Implement `corporate_actions` data pipeline | New: extractor + job | High |
| L3 | Add Prometheus metrics endpoint for database monitoring | New: `routes/metrics.py` | Medium |
| L4 | Implement real disruption risk model to replace mock | `scoring_engine.py` | High |
| L5 | Add pagination support to `get_all_symbols()` | `mongodb_store.py` | Low |
| L6 | Configure read replicas for analytics query offloading | Infrastructure | High |
| L7 | Add derivatives data status indicator to distinguish placeholder vs. real records | `derivatives_job.py` | Low |

---

*This document should be updated as database changes are implemented. Last reviewed: 2026-03-16.*
