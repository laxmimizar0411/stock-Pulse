# PostgreSQL for StockPulse — Complete Local Setup Reference

> **Last Updated:** March 7, 2026
> **Status:** Fully implemented — 14 tables, 40+ indexes, 14 REST endpoints, extended pipeline, derived metrics job, PG Control UI

---

## 1. Context

- **Project:** StockPulse — Indian stock analysis platform (NSE/BSE). Backend: FastAPI (Python). Frontend: React 19. Other stores: MongoDB (entity/document), Redis (cache).
- **PostgreSQL role:** Time-series and analytics layer. It stores 270+ fields across 14 tables covering:
  - Daily OHLCV prices (+ delivery, VWAP)
  - Derived metrics (returns, 52-week high/low, volume ratios)
  - Technical indicators (SMA, RSI, MACD, Ichimoku, Stochastic, CCI, etc.)
  - ML features (predicted scores, anomaly flags)
  - Risk metrics (VaR, beta, Sharpe, max drawdown)
  - Valuation (P/E, P/B, EV/EBITDA, dividend yield, PEG)
  - Quarterly fundamentals (55+ columns: revenue, profit, balance sheet, cash flow, ratios)
  - Quarterly shareholding (promoter, FII, DII, MF, insurance)
  - Corporate actions (dividends, splits, bonuses, rights)
  - Macro indicators (repo rate, GDP, CPI, USD/INR)
  - Derivatives (futures OI, options chain, put-call ratio, IV)
  - Intraday metrics (VWAP, tick count, JSONB bid/ask snapshots)
  - Weekly metrics (SMA crossover, JSONB support/resistance, sectoral heatmap)
  - Schema migrations (version tracking)
- **Goal:** Local Postgres instance; all 14 tables created; app connects at startup; data flows in from Bhavcopy, Groww pipeline, and derivation jobs; screener uses 7-table JOIN; 14 REST endpoints serve all tables; PG Control UI provides ON/OFF toggle and resource monitoring.

---

## 2. Architecture

### 14 PostgreSQL Tables

| # | Table | PK | Key Columns | Source |
|---|-------|----|-------------|--------|
| 1 | `prices_daily` | (symbol, date) | OHLCV, delivery, VWAP, 17 cols | Bhavcopy, Groww |
| 2 | `derived_metrics_daily` | (symbol, date) | daily_return, 5/20/60d returns, 52w high/low, volume_ratio | Derivation job |
| 3 | `technical_indicators` | (symbol, date) | SMA, EMA, RSI, MACD, Bollinger, ATR, ADX, OBV, Ichimoku, Stochastic, CCI, Williams %R, CMF — 27 cols | Pipeline, pandas-ta |
| 4 | `ml_features_daily` | (symbol, date) | predicted_score, anomaly flags, feature vectors | ML jobs |
| 5 | `risk_metrics` | (symbol, date) | var_95, beta, alpha, sharpe, sortino, max_drawdown, volatility | Risk job |
| 6 | `valuation_daily` | (symbol, date) | pe, pb, ps, ev_ebitda, dividend_yield, peg, mcap, enterprise_value | Pipeline |
| 7 | `fundamentals_quarterly` | (symbol, period_end, period_type) | 55+ cols: revenue, profit, margins, EPS, balance sheet, cash flow, ratios | Pipeline |
| 8 | `shareholding_quarterly` | (symbol, quarter_end) | promoter, FII, DII, public, pledging, MF, insurance — 11 cols | Pipeline |
| 9 | `corporate_actions` | (symbol, ex_date, action_type) | dividend_amount, split ratio, bonus ratio, record_date | Pipeline |
| 10 | `macro_indicators` | (indicator_name, date) | value, previous_value, unit, source | Macro job |
| 11 | `derivatives_daily` | (symbol, date) | futures_oi, options_oi, pcr, iv, max_pain, rollover_pct | Derivatives job |
| 12 | `intraday_metrics` | (symbol, timestamp) | vwap_intraday, tick_count, JSONB bid_ask_snapshot | Intraday job |
| 13 | `weekly_metrics` | (symbol, week_start) | sma_weekly_crossover, JSONB support_resistance/sectoral_heatmap | Derivation job |
| 14 | `schema_migrations` | (version) | applied_at, description | Setup script |

### Schema Source of Truth

`backend/setup_databases.py` — constant `POSTGRESQL_SCHEMA` defines all 14 tables with 40+ indexes. Run:
```bash
cd backend
python setup_databases.py --postgres        # Create tables and indexes
python setup_databases.py --check           # Verify-only (expects 14 tables)
```

---

## 3. Data Access Layer — TimeSeriesStore

**File:** `backend/services/timeseries_store.py`

Async class using `asyncpg` with connection pooling (min_size=2, max_size=10).

### Upsert Methods (12)
All use `ON CONFLICT DO UPDATE` pattern:

| Method | Target Table |
|--------|-------------|
| `upsert_prices(records)` | prices_daily |
| `upsert_technicals(records)` | technical_indicators (all 27 cols) |
| `upsert_fundamentals(records)` | fundamentals_quarterly (dynamic 55+ cols via FUND_COLS) |
| `upsert_shareholding(records)` | shareholding_quarterly |
| `upsert_derived_metrics(records)` | derived_metrics_daily |
| `upsert_valuation(records)` | valuation_daily |
| `upsert_ml_features(records)` | ml_features_daily |
| `upsert_risk_metrics(records)` | risk_metrics |
| `upsert_macro_indicators(records)` | macro_indicators |
| `upsert_derivatives(records)` | derivatives_daily |
| `upsert_intraday_metrics(records)` | intraday_metrics (TIMESTAMPTZ, JSONB) |
| `upsert_weekly_metrics(records)` | weekly_metrics (JSONB support) |

### Query Methods (17+)
| Method | Description |
|--------|-------------|
| `get_prices(symbol, limit)` | Daily OHLCV |
| `get_latest_price_date(symbol)` | Most recent date |
| `get_price_count(symbol)` | Row count |
| `get_weekly_prices(symbol, limit)` | Aggregated from prices_daily |
| `get_monthly_prices(symbol, limit)` | Aggregated from prices_daily |
| `get_technicals(symbol, limit)` | Technical indicators |
| `get_fundamentals(symbol, period_type)` | Quarterly fundamentals |
| `get_shareholding(symbol, limit)` | Shareholding data |
| `get_derived_metrics(symbol, limit)` | Derived daily metrics |
| `get_valuation(symbol, limit)` | Valuation ratios |
| `get_ml_features(symbol, limit)` | ML feature vectors |
| `get_risk_metrics(symbol, limit)` | Risk/volatility metrics |
| `get_corporate_actions(symbol)` | Corporate actions |
| `get_macro_indicators(name)` | Macro economic data |
| `get_derivatives(symbol, limit)` | Derivatives data |
| `get_intraday_metrics(symbol, start_ts, end_ts)` | Intraday with TIMESTAMPTZ |
| `get_weekly_metrics(symbol, limit)` | Weekly aggregates |
| `get_screener_data(filters, sort, limit)` | 7-table JOIN with COLUMN_MAP |
| `get_stats()` | Row counts for all 14 tables |

### Screener — 7-Table JOIN
The screener CTE now joins:
1. `latest_prices` — DISTINCT ON (symbol) from prices_daily
2. `latest_tech` — from technical_indicators
3. `latest_fund` — from fundamentals_quarterly
4. `latest_share` — from shareholding_quarterly
5. `latest_derived` — from derived_metrics_daily
6. `latest_val` — from valuation_daily
7. `latest_risk` — from risk_metrics

`COLUMN_MAP` maps ~50+ filter/sort keys to qualified SQL columns across all 7 tables.

---

## 4. Pipeline Persistence

**File:** `backend/services/pipeline_service.py`

`_persist_to_timeseries(results)` builds records for 9 table categories from Groww pipeline output:

1. **prices** — OHLCV + delivery + VWAP fields
2. **technicals** — All 25+ indicator fields (SMA, RSI, MACD, Ichimoku, Stochastic, CCI, etc.)
3. **fundamentals** — All 60+ cols (revenue, profit, margins, EPS, balance sheet, cash flow, ratios)
4. **shareholding** — Promoter, FII, DII, pledging
5. **valuation** — P/E, P/B, EV/EBITDA, dividend yield, PEG, market cap
6. **derived_metrics** — Daily returns, 52-week high/low (when present in data)
7. **ml_features** — ML scores and anomaly flags (when present)
8. **risk_metrics** — VaR, beta, Sharpe, volatility (when present)
9. **corporate_actions** — Dividends, splits, bonuses (when present)

Each category only writes when its detection fields are found in the pipeline data. Macro indicators, derivatives, intraday, and weekly metrics are filled by separate jobs.

---

## 5. Derived Data Computation Job

**File:** `backend/jobs/derive_metrics.py`

Standalone job that reads `prices_daily` and computes derived fields:

### `compute_derived_metrics(ts_store, symbols, lookback_days=260)`
Computes for each symbol:
- `daily_return_pct` — (close - prev_close) / prev_close × 100
- `return_5d_pct`, `return_20d_pct`, `return_60d_pct` — rolling N-day returns
- `day_range_pct` — (high - low) / low × 100
- `gap_percentage` — (open - prev_close) / prev_close × 100
- `week_52_high`, `week_52_low` — rolling 252-day max/min
- `distance_from_52w_high` — percentage from 52-week high
- `avg_volume_20d`, `volume_ratio` — 20-day average volume and ratio

### `compute_weekly_metrics(ts_store, symbols, weeks=104)`
- Groups prices by ISO week
- `sma_weekly_crossover` — whether SMA50 > SMA200 at end of week

### CLI Usage
```bash
cd backend
python -m jobs.derive_metrics                    # All symbols
python -m jobs.derive_metrics --symbols TCS,INFY # Specific symbols
python -m jobs.derive_metrics --weekly           # Also compute weekly metrics
```

Can also be called programmatically:
```python
from jobs.derive_metrics import compute_derived_metrics
await compute_derived_metrics(ts_store)
```

---

## 6. REST API Endpoints

### Time-Series Data (14 endpoints)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/timeseries/stats` | GET | Row counts and pool stats for all 14 tables |
| `/api/timeseries/prices/{symbol}` | GET | Daily OHLCV (params: start_date, end_date, limit) |
| `/api/timeseries/derived-metrics/{symbol}` | GET | Derived daily metrics (params: limit) |
| `/api/timeseries/technicals/{symbol}` | GET | Technical indicators (params: limit) |
| `/api/timeseries/fundamentals/{symbol}` | GET | Quarterly fundamentals (params: period_type) |
| `/api/timeseries/shareholding/{symbol}` | GET | Shareholding data (params: limit) |
| `/api/timeseries/valuation/{symbol}` | GET | Valuation ratios (params: limit) |
| `/api/timeseries/ml-features/{symbol}` | GET | ML features (params: limit) |
| `/api/timeseries/risk-metrics/{symbol}` | GET | Risk metrics (params: limit) |
| `/api/timeseries/corporate-actions/{symbol}` | GET | Corporate actions |
| `/api/timeseries/macro-indicators` | GET | Macro indicators (params: indicator_name) |
| `/api/timeseries/derivatives/{symbol}` | GET | Derivatives data (params: limit) |
| `/api/timeseries/intraday/{symbol}` | GET | Intraday metrics (params: start_ts, end_ts) |
| `/api/timeseries/weekly-metrics/{symbol}` | GET | Weekly metrics (params: limit) |

All return: `{"symbol": "...", "count": N, "data": [...]}` or HTTP 503 if `_ts_store` is None.

### PostgreSQL Control (4 endpoints)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/database/postgres-control/status` | GET | Running state, version, uptime |
| `/api/database/postgres-control/toggle` | POST | Start/stop Postgres (body: `{action: "start"\|"stop"}`) |
| `/api/database/postgres-control/resources` | GET | CPU, RAM, storage (per-table), connections, pool stats |
| `/api/database/postgres-control/health` | GET | Quick health check |

### Screener
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/screener` | POST | 7-table JOIN screener with ~50 filter/sort keys |

---

## 7. Frontend — PG Control UI

**File:** `frontend/src/pages/PostgresControl.jsx`
**Route:** `/pg-control`

Features:
- Power toggle with confirmation dialog for stop
- Resource overview cards: CPU, RAM, Storage, Active Connections (with progress bars)
- **Storage tab:** Per-table breakdown (row count, data size, index size, usage %)
- **Connections tab:** By-state and by-database breakdown
- **Pool tab:** asyncpg connection pool stats
- Schema info card listing all 14 tables
- Auto-refresh every 10 seconds with toggle

**Supporting files:**
- `frontend/src/components/Layout.jsx` — Nav item with HardDrive icon
- `frontend/src/App.js` — Route `/pg-control`
- `frontend/src/lib/api.js` — `getPostgresStatus()`, `togglePostgres()`, `getPostgresResources()`, `getPostgresHealth()`

---

## 8. Quick Start (Local Setup)

```bash
# 1. Install PostgreSQL (14+)
# macOS: brew install postgresql && brew services start postgresql
# Ubuntu: sudo apt install postgresql && sudo systemctl start postgresql

# 2. Create the database
createdb stockpulse_ts

# 3. Set DSN in backend/.env
echo 'TIMESERIES_DSN=postgresql://localhost:5432/stockpulse_ts' >> backend/.env

# 4. Create all 14 tables and 40+ indexes
cd backend
python setup_databases.py --postgres

# 5. Verify
python setup_databases.py --check
python test_pipeline.py --db-only

# 6. Start the backend
uvicorn server:app --port 8001

# 7. Verify via API
curl http://localhost:8001/api/database/health
curl http://localhost:8001/api/timeseries/stats
curl http://localhost:8001/api/database/postgres-control/status

# 8. (Optional) Run derived metrics after loading price data
python -m jobs.derive_metrics
python -m jobs.derive_metrics --weekly
```

---

## 9. Files Reference

| File | Purpose |
|------|---------|
| `backend/setup_databases.py` | Schema definition (14 tables, 40+ indexes) and setup script |
| `backend/services/timeseries_store.py` | Async data access layer (12 upsert, 17+ query methods) |
| `backend/services/pipeline_service.py` | Pipeline persistence to 9 table categories |
| `backend/services/pg_control_service.py` | PG start/stop/resource monitoring service |
| `backend/services/db_dashboard_service.py` | Dashboard metadata for all 14 tables |
| `backend/routes/pg_control.py` | REST routes for PG control |
| `backend/jobs/__init__.py` | Jobs package init |
| `backend/jobs/derive_metrics.py` | Derived metrics computation job |
| `backend/server.py` | FastAPI app with all endpoints |
| `backend/test_pipeline.py` | Integration tests (expects 14 tables) |
| `frontend/src/pages/PostgresControl.jsx` | PG Control UI |
| `frontend/src/lib/api.js` | API client (PG control functions) |

---

## 10. Definition of "100% Complete and Operational"

- Postgres running locally; database `stockpulse_ts` exists; `TIMESERIES_DSN` set in `backend/.env`
- `python setup_databases.py --postgres` creates all 14 tables and 40+ indexes without errors
- Backend starts; `_ts_store` initialized; health endpoint shows `postgresql.status: "connected"` with 14 tables
- Bhavcopy writes to `prices_daily`; Groww pipeline persists to 9 table categories
- Screener uses 7-table JOIN with ~50 filter/sort keys; falls back to in-memory when PG unavailable
- 14 REST endpoints serve all time-series tables
- PG Control UI provides start/stop toggle and resource monitoring
- Derivation job computes daily returns, 52-week metrics, volume ratios, and weekly SMA crossovers
- `test_pipeline.py --db-only` passes with all 14 tables verified
