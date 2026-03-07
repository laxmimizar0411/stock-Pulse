# Task List: Complete PostgreSQL DB and Make It Fully Operational

**Goal:** Finish all incomplete Postgres work so the 14-table schema is writable, readable via API, used by the screener where relevant, and covered by tests. Target: **local Postgres only**, single-user.

**Hand this document to an AI (or follow it yourself) and implement each task in order.**

---

## A. Relevant Files (Do Not Miss)

| File | Role |
|------|------|
| `backend/setup_databases.py` | Postgres schema (14 tables), DB creation, indexes; run with `--postgres` |
| `backend/services/timeseries_store.py` | All upsert/get methods for Postgres tables; screener JOIN and COLUMN_MAP |
| `backend/services/pipeline_service.py` | `_persist_to_timeseries()` — maps Groww results to Postgres; currently only 4 tables |
| `backend/server.py` | Startup init of `_ts_store`, routes that use it (health, timeseries, screener, bhavcopy) |
| `backend/routes/pg_control.py` | PG Control API (status, toggle, resources) |
| `backend/services/pg_control_service.py` | Start/stop Postgres, CPU/RAM/storage/connection monitoring |
| `backend/services/db_dashboard_service.py` | Metadata and sort order for all 14 tables (introspection) |
| `backend/test_pipeline.py` | `--db-only` expects a list of Postgres tables; currently 4 |
| `backend/.env.example` | `TIMESERIES_DSN` for Postgres |
| `frontend/src/pages/PostgresControl.jsx` | PG Control UI (toggle, resources, connections, schema) |
| `frontend/src/App.js` | Route for `/pg-control` |
| `frontend/src/lib/api.js` | Any API client helpers for timeseries/Postgres |
| `Documentation/PROMPT_PostgreSQL_Complete_Local_Setup.md` | Earlier prompt; update if schema/flow changes |
| `Documentation/V2-Complete-Data-requirement-Claude-Offline_Loader.md` | Field reference for 270+ fields and table mapping |

---

## B. Task List (Implement in Order)

### Task 1: TimeSeriesStore — Add CRUD for `intraday_metrics` and `weekly_metrics`

**File:** `backend/services/timeseries_store.py`

- **1.1** Add `async def upsert_intraday_metrics(self, records: List[Dict[str, Any]]) -> int`.  
  Table `intraday_metrics` has columns: `symbol`, `timestamp` (TIMESTAMPTZ), `rsi_hourly`, `macd_crossover_hourly`, `vwap_intraday`, `advance_decline_ratio`, `sectoral_heatmap` (JSONB), `india_vix`. Use `ON CONFLICT (symbol, timestamp) DO UPDATE` and the same pattern as other upserts in this file.
- **1.2** Add `async def get_intraday_metrics(self, symbol: str, start_ts: Optional[str] = None, end_ts: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]` (filter by symbol and optional timestamp range, order by timestamp DESC, limit).
- **1.3** Add `async def upsert_weekly_metrics(self, records: List[Dict[str, Any]]) -> int`.  
  Table `weekly_metrics` has: `symbol`, `week_start` (DATE), `sma_weekly_crossover`, `support_resistance_weekly` (JSONB), `google_trends_score`, `job_postings_growth`. Use `ON CONFLICT (symbol, week_start) DO UPDATE`.
- **1.4** Add `async def get_weekly_metrics(self, symbol: str, limit: int = 104) -> List[Dict[str, Any]]` (order by week_start DESC).

---

### Task 2: Pipeline — Persist to All Tables That Have Data or Can Be Derived

**File:** `backend/services/pipeline_service.py`

- **2.1** In `_persist_to_timeseries()`, after building `price_records`, `technical_records`, `fundamental_records`, `shareholding_records`, add logic to build (when possible from `results` or from already-fetched data):
  - **derived_metrics_daily:** e.g. daily returns, 52-week high/low, volume ratio (derive from `prices_daily` or from `data` if available). If Groww does not send these, add a **derivation step**: after `upsert_prices`, optionally query latest `prices_daily` for each symbol and compute derived fields, then call `self.ts_store.upsert_derived_metrics(derived_records)`.
  - **valuation_daily:** P/E, P/B, yields, etc. If present in `data`, build records and call `self.ts_store.upsert_valuation(valuation_records)`.
  - **ml_features_daily:** volatility, momentum, etc. If present in `data` or computable from prices/technicals, build and call `self.ts_store.upsert_ml_features(ml_records)`.
  - **risk_metrics:** beta, Sharpe, drawdown, etc. If present or computable, build and call `self.ts_store.upsert_risk_metrics(risk_records)`.
- **2.2** For **corporate_actions**, **macro_indicators**, **derivatives_daily**: if the Groww (or any) extractor does not currently provide these, add a comment in code: "Corporate actions / macro / derivatives to be filled by separate job or extractor." Do **not** leave unconditional empty writes; only call the corresponding upsert when you have at least one record built from `results` or from an external source.
- **2.3** For **intraday_metrics** and **weekly_metrics**: same as above — call `upsert_intraday_metrics` / `upsert_weekly_metrics` only when you have records (e.g. from future intraday source or weekly aggregation). Optionally add a **weekly aggregation job** that reads from `prices_daily` and writes into `weekly_metrics` (e.g. sma_weekly_crossover) if that fits the schema.
- **2.4** Ensure every new `ts_store` call is inside the same `try` block as the existing upserts; on exception log and call `_log_event("pg_persist_error", ...)`.

---

### Task 3: Screener — Extend JOIN and COLUMN_MAP to New Tables

**File:** `backend/services/timeseries_store.py`

- **3.1** In `get_screener_data()`, extend the main query’s CTEs and JOINs to include (with LEFT JOIN so missing data does not drop symbols):
  - Latest row per symbol from `derived_metrics_daily` (e.g. alias `d`).
  - Latest from `valuation_daily` (e.g. alias `v`).
  - Latest from `risk_metrics` (alias `r`).
  - Optionally `ml_features_daily`, `derivatives_daily` if you want to filter by them.
- **3.2** Extend `COLUMN_MAP` with metrics from these tables (e.g. from `derived_metrics_daily`: 52w high/low, return columns; from `valuation_daily`: pe_ratio, pb_ratio, dividend_yield, etc.; from `risk_metrics`: beta, sharpe_ratio, max_drawdown, etc.). Use the exact column names from `setup_databases.py` schema.
- **3.3** Add the new aliases to the SELECT list and to the ORDER BY so sort_by can use the new columns. Keep the query valid when some tables are empty (LEFT JOINs and NULLS LAST).

---

### Task 4: REST API — Expose Read Endpoints for All Time-Series Tables

**File:** `backend/server.py`

- **4.1** Add GET endpoints (under `/api/timeseries/` or `/api/data/`) that call the existing TimeSeriesStore getters and return JSON. Use the same pattern as existing `GET /api/timeseries/prices/{symbol}` (query params: limit, start_date/end_date or start_ts/end_ts where applicable). Add:
  - `GET /api/timeseries/derived-metrics/{symbol}` → `_ts_store.get_derived_metrics(symbol, ...)`
  - `GET /api/timeseries/valuation/{symbol}` → `_ts_store.get_valuation(symbol, ...)`
  - `GET /api/timeseries/ml-features/{symbol}` → `_ts_store.get_ml_features(symbol, ...)`
  - `GET /api/timeseries/risk-metrics/{symbol}` → `_ts_store.get_risk_metrics(symbol, ...)`
  - `GET /api/timeseries/corporate-actions/{symbol}` → `_ts_store.get_corporate_actions(symbol, ...)`
  - `GET /api/timeseries/macro-indicators` (no symbol) → `_ts_store.get_macro_indicators(limit=...)`
  - `GET /api/timeseries/derivatives/{symbol}` → `_ts_store.get_derivatives(symbol, ...)`
  - `GET /api/timeseries/intraday/{symbol}` → `_ts_store.get_intraday_metrics(symbol, ...)` (query params: start_ts, end_ts, limit)
  - `GET /api/timeseries/weekly-metrics/{symbol}` → `_ts_store.get_weekly_metrics(symbol, limit=...)`
- **4.2** For each endpoint: if `_ts_store` is None or not initialized, return 503 with a clear message. Use existing `get_prices` and `get_technicals` patterns (e.g. optional date range, limit) for consistency.

---

### Task 5: Tests and Setup Script Text

- **5.1** **File:** `backend/test_pipeline.py`  
  In the `--db-only` Postgres check, replace the `expected` list of 4 tables with the full 14:  
  `["prices_daily", "derived_metrics_daily", "technical_indicators", "ml_features_daily", "risk_metrics", "valuation_daily", "fundamentals_quarterly", "shareholding_quarterly", "corporate_actions", "macro_indicators", "derivatives_daily", "intraday_metrics", "weekly_metrics", "schema_migrations"]`.  
  Ensure the loop still prints each table’s row count and reports MISSING for any that do not exist.

- **5.2** **File:** `backend/setup_databases.py`  
  Update the top-level docstring (and any comment that says "4 time-series tables") to state that Postgres has **14 tables** (and 40+ indexes). Do not change the schema SQL unless you are fixing a bug.

---

### Task 6: Optional — Derived Data Job (Recommended for “Operational”)

- **6.1** Add a small module or function (e.g. in `backend/services/` or `backend/jobs/`) that:  
  (a) Reads from `prices_daily` (and optionally `technical_indicators`, `fundamentals_quarterly`) for symbols that have data.  
  (b) Computes derived_metrics_daily (e.g. daily return, 52-week high/low from rolling window, volume ratio) and calls `ts_store.upsert_derived_metrics(...)`.  
  (c) Can be run on a schedule (e.g. after pipeline run) or via a one-off script.  
  This ensures `derived_metrics_daily` gets populated even if the Groww API does not send these fields.

- **6.2** If you add a weekly aggregation: from `prices_daily`, compute per-symbol weekly OHLCV and any weekly metrics (e.g. sma_weekly_crossover) and call `ts_store.upsert_weekly_metrics(...)`. Run this job weekly or after daily pipeline.

---

### Task 7: Documentation and Runbook

- **7.1** Update `Documentation/PROMPT_PostgreSQL_Complete_Local_Setup.md` (or a short runbook section) so that it reflects the **14-table** schema and mentions:  
  - Running `python setup_databases.py --postgres` to create all 14 tables.  
  - The new REST endpoints for derived, valuation, risk, corporate, macro, derivatives, intraday, weekly.  
  - That the pipeline now persists to all tables for which data is available (and that derived/weekly can be filled by the optional derivation job).

- **7.2** Optionally add one paragraph to `Documentation/DEVELOPMENT_HISTORY.md` under “Current Status Summary” or a new Phase 10: “PostgreSQL 14-table schema fully wired: pipeline persistence to all applicable tables, screener extended, REST APIs for all time-series tables, tests and runbook updated.”

---

## C. Definition of Done

- All 14 tables have corresponding upsert and get methods in `timeseries_store.py` (intraday and weekly added; others already exist).
- Pipeline `_persist_to_timeseries()` builds and writes records for every table for which data exists in the pipeline or can be derived from existing Postgres data; no silent skips for tables that have a store method.
- Screener `get_screener_data()` includes the new tables in the JOIN and COLUMN_MAP so filters/sort can use derived, valuation, risk, etc.
- REST API exposes read access for all time-series tables (including intraday and weekly).
- `test_pipeline.py --db-only` expects 14 tables; `setup_databases.py` docstring says 14 tables.
- Optional: derivation job fills `derived_metrics_daily` (and optionally `weekly_metrics`) from `prices_daily`.
- Docs/runbook updated so a developer can run Postgres locally, run setup, start the app, and use all endpoints and the screener with the 14-table schema.

---

## D. Out of Scope for This Task List

- Cloud or hosted Postgres (Supabase, Aiven, etc.); only local.
- Changing the 14-table schema (no new tables or column renames unless required by a bug).
- Frontend UI changes beyond what is already in PostgresControl and Database Dashboard.
- New data sources (e.g. NSE F&O, RBI macro) — only wire existing or derivable data into the existing tables.

---

## E. Additional Notes and Conventions (Read Before Implementing)

- **Schema as source of truth:** All column names for every table must match `backend/setup_databases.py` exactly. When building pipeline records or extending `COLUMN_MAP` in `get_screener_data()`, copy names from the `CREATE TABLE` statements (e.g. `derived_metrics_daily`: daily_return_pct, return_5d_pct, week_52_high, week_52_low, volume_ratio, etc.; `valuation_daily`: pe_ratio, pb_ratio, dividend_yield, market_cap, etc.; `risk_metrics`: beta_1y, sharpe_ratio_1y, max_drawdown_1y, etc.). Do not invent column names.

- **schema_migrations table:** Do **not** add any app-level write or upsert for `schema_migrations`. It is maintained only by `setup_databases.py` (initial INSERT). The app only reads it if needed; `get_stats()` may include it in the table list for row count/size.

- **Bhavcopy → Postgres:** The flow `GET /api/bhavcopy/download/{date}` → Bhavcopy extractor → `[d.to_dict() for d in data]` → `_ts_store.upsert_prices(records)` must keep working. `timeseries_store.upsert_prices` already uses `record.get(key, default)` for optional fields (last, turnover, delivery_qty, etc.). Ensure any change to `upsert_prices` or to the Bhavcopy record shape does not break this; if the extractor’s `to_dict()` matches the expected keys (symbol, date, open, high, low, close, last, prev_close, volume, turnover, total_trades, delivery_qty, delivery_pct, vwap, isin, series), no change is needed.

- **Response shape for new GET endpoints:** Use the same pattern as existing `GET /api/timeseries/prices/{symbol}`: return `{ "symbol": "<symbol>", "count": N, "data": [ ... ] }` for symbol-scoped endpoints. For `GET /api/timeseries/macro-indicators` (no symbol), return `{ "count": N, "data": [ ... ] }`. Use 503 when `_ts_store` is None or not initialized.

- **Timezone for intraday:** In `upsert_intraday_metrics`, the `timestamp` column is TIMESTAMPTZ. Pass timezone-aware datetimes (e.g. from ISO string with timezone or `datetime(..., tzinfo=timezone.utc)`). In `get_intraday_metrics`, accept optional `start_ts` / `end_ts` as ISO strings and parse to timezone-aware for the query.

- **TimeSeriesStore vs schema:** If any existing upsert method (e.g. `upsert_technicals`) has fewer columns in its INSERT than the table definition in `setup_databases.py`, extend the method to include all columns from the schema (e.g. `technical_indicators` has ichimoku_tenkan, ichimoku_kijun, stoch_k, stoch_d, cci_20, williams_r, cmf, macd_histogram). Match the schema 1:1 so no column is missing.

- **get_stats() table list:** Ensure `get_stats()` in `timeseries_store.py` iterates over all 14 tables (including `schema_migrations`) so `/api/database/health` and `/api/timeseries/stats` (and PG Control/dashboard) show correct row counts and sizes for every table.

- **Frontend API client (optional):** If any UI will call the new timeseries endpoints, add corresponding functions in `frontend/src/lib/api.js` (e.g. `getTimeseriesValuation(symbol)`, `getTimeseriesRiskMetrics(symbol)`). If the new endpoints are only for internal or future use, backend-only is sufficient.

- **Corporate actions:** TimeSeriesStore has `insert_corporate_action(record)` (single record), not a batch upsert. For pipeline Task 2, either loop over records calling `insert_corporate_action` or add `upsert_corporate_actions(records)` that uses `ON CONFLICT` if the table has a unique constraint (check `setup_databases.py` for primary/unique key on `corporate_actions`).

- **Regression check:** After implementing, verify: (1) `python setup_databases.py --postgres` runs without error; (2) `python test_pipeline.py --db-only` passes and reports all 14 tables; (3) Bhavcopy download still writes to `prices_daily`; (4) Screener still returns results when Postgres is up; (5) Existing `/api/timeseries/prices/{symbol}` and `/api/timeseries/stats` still work.
