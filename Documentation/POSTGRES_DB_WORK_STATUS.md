# PostgreSQL Database — Current Work Status

> **Generated:** March 9, 2026  
> **Scope:** Backend PostgreSQL time-series store (14 tables), TimeSeriesStore, pipeline, jobs, API, and gaps.

---

## 1. Work completed (done)

### Schema & setup
- **14 tables** defined and created in `backend/setup_databases.py`:
  - `prices_daily`, `derived_metrics_daily`, `technical_indicators`, `ml_features_daily`, `risk_metrics`, `valuation_daily`, `fundamentals_quarterly`, `shareholding_quarterly`, `corporate_actions`, `macro_indicators`, `derivatives_daily`, `intraday_metrics`, `weekly_metrics`, `schema_migrations`
- **40+ indexes** (symbol, date, symbol+date, etc.) for all tables.
- **Auto-create database** if missing (`InvalidCatalogNameError` → create `stockpulse_ts` then connect).
- **Optional TimescaleDB**: when extension is present, `prices_daily` and `technical_indicators` converted to hypertables + compression policies; no continuous aggregates created in setup (see gaps).

### TimeSeriesStore (`backend/services/timeseries_store.py`)
- **Connection pool**: asyncpg, min 2 / max 10, 30s command timeout.
- **12 upsert methods** (ON CONFLICT DO UPDATE where applicable):
  - `upsert_prices`, `upsert_technicals`, `upsert_fundamentals`, `upsert_shareholding`, `upsert_derived_metrics`, `upsert_valuation`, `upsert_ml_features`, `upsert_risk_metrics`, `upsert_macro_indicators`, `upsert_derivatives`, `upsert_intraday_metrics`, `upsert_weekly_metrics`
- **1 insert-only**: `insert_corporate_action` (single record, no upsert).
- **17+ read methods**: `get_prices`, `get_latest_price_date`, `get_price_count`, `get_weekly_prices`, `get_monthly_prices`, `get_technicals`, `get_fundamentals`, `get_shareholding`, `get_derived_metrics`, `get_valuation`, `get_ml_features`, `get_risk_metrics`, `get_corporate_actions`, `get_macro_indicators`, `get_derivatives`, `get_intraday_metrics`, `get_weekly_metrics`, `get_screener_data`, `get_stats`.
- **Screener**: `get_screener_data` does 7-table JOIN (prices, technicals, fundamentals, shareholding, derived, valuation, risk) with ~50 filter/sort keys in `COLUMN_MAP`.

### Data flow into PostgreSQL
- **Bhavcopy** (`server.py`): writes to `prices_daily` via `_ts_store.upsert_prices(records)`.
- **Pipeline** (`pipeline_service._persist_to_timeseries`): builds and writes to 9 categories when fields present:
  - prices, technicals, fundamentals, shareholding, valuation, derived_metrics, ml_features, risk_metrics, corporate_actions (via `insert_corporate_action` per record).
- **Derived metrics job** (`jobs/derive_metrics.py`): reads `prices_daily`, computes derived fields, writes `derived_metrics_daily` and `weekly_metrics` (when `--weekly`).

### API & control
- **14 time-series GET endpoints** under `/api/timeseries/*` (stats, prices, derived-metrics, technicals, fundamentals, shareholding, valuation, ml-features, risk-metrics, corporate-actions, macro-indicators, derivatives, intraday, weekly-metrics).
- **Screener**: `POST /api/screener` uses PostgreSQL 7-table JOIN when `_ts_store` is initialized; fallback to in-memory when not.
- **Health**: `/api/database/health` includes PostgreSQL status (tables, row counts).
- **PG Control**: status, toggle, resources, health endpoints; frontend `PostgresControl.jsx` with toggle and resource cards.

### Documentation
- `Documentation/PROMPT_PostgreSQL_Complete_Local_Setup.md` — setup and architecture.
- `Documentation/DEVELOPMENT_HISTORY.md` — mentions PostgreSQL expansion.

---

## 2. Pending / not wired (work to do)

| Item | Description |
|------|-------------|
| **Macro indicators** | Table and `upsert_macro_indicators` exist; no job or pipeline step fills them. Comment in pipeline: “Macro indicators … filled by separate extractors or derivation jobs when data sources become available (NSE F&O, RBI macro, intraday feed).” |
| **Derivatives** | Table and `upsert_derivatives` exist; no F&O extractor or job populates them. Same comment as above. |
| **Intraday metrics** | Table and `upsert_intraday_metrics` exist; no intraday feed or job populates them. |
| **Weekly aggregation (plain Postgres)** | `get_weekly_prices` / `get_monthly_prices` use TimescaleDB continuous aggregates `prices_weekly` and `prices_monthly`. These are **not** created in `setup_databases.py`. Without TimescaleDB, both methods return `[]` and log a warning. |
| **Scheduled derivation** | `compute_derived_metrics` and `compute_weekly_metrics` are run manually or by test; no scheduler (e.g. cron or in-app) runs them after bhavcopy or pipeline. |

---

## 3. Gaps and missing implementation

### Schema vs code
- **`prices_daily.adjusted_close`**: Column exists in schema; `upsert_prices` does **not** include it. Bhavcopy and pipeline do not set it; yfinance extractor has `adjusted_close` but that path may not write to this table. **Gap:** Add `adjusted_close` to `upsert_prices` and populate from pipeline/bhavcopy if available.

### Weekly/monthly without TimescaleDB
- **`prices_weekly` / `prices_monthly`**: Referenced only in `get_weekly_prices` and `get_monthly_prices`. Setup does not create these (no continuous aggregates in script). **Gap:** Either (a) add TimescaleDB continuous aggregates in setup when extension is present, or (b) implement plain-Postgres weekly/monthly aggregation (e.g. SQL or pandas) and use it when TimescaleDB is absent.

### Corporate actions
- **Upsert semantics**: `insert_corporate_action` is insert-only. Duplicate (symbol, action_type, action_date) can be inserted multiple times. **Gap (optional):** If business rule is one row per event, add unique constraint and use `ON CONFLICT DO UPDATE` or skip duplicates.
- **Doc vs schema**: Doc says PK `(symbol, ex_date, action_type)`; actual table has `id SERIAL PRIMARY KEY`. Update doc to match schema.

### Macro table doc
- Doc says `macro_indicators` PK `(indicator_name, date)`; actual schema is `date DATE NOT NULL PRIMARY KEY` (one row per date). Update doc.

### Data sources
- **macro_indicators**: Needs RBI/macro source and a small job to call `upsert_macro_indicators`.
- **derivatives_daily**: Needs NSE F&O (or similar) source and job to call `upsert_derivatives`.
- **intraday_metrics**: Needs intraday feed and job to call `upsert_intraday_metrics`.

---

## 4. Errors and fixes needed

### 1) `insert_corporate_action` — empty string dates
- **Issue:** For `ex_date`, `record_date`, or `next_earnings_date`, code does `if isinstance(x, str): x = datetime.strptime(x, "%Y-%m-%d").date()`. If value is `""`, `strptime("", "%Y-%m-%d")` raises.
- **Fix:** Only parse when the value is a non-empty string (e.g. `if isinstance(x, str) and x.strip():` then parse; otherwise leave as None for NULL in DB).

### 2) `prices_daily.adjusted_close` not written
- **Issue:** Schema has `adjusted_close`; `upsert_prices` does not insert/update it.
- **Fix:** Add `adjusted_close` to the INSERT and ON CONFLICT DO UPDATE in `upsert_prices`, and pass it from records (e.g. from pipeline/bhavcopy or default None).

### 3) Optional: corporate action date parsing robustness
- **Issue:** If `action_date` is empty string, same `strptime` issue as above.
- **Fix:** Use the same “non-empty string only” parsing for `action_date` (and consistently for all date fields in this method).

---

## 5. Required work summary

| Priority | Task | Type |
|----------|------|------|
| High | Fix `insert_corporate_action` to handle empty-string dates (and optionally `action_date`) | Bug fix |
| High | Add `adjusted_close` to `upsert_prices` and ensure callers pass it when available | Gap |
| Medium | Provide weekly/monthly aggregation without TimescaleDB (or add continuous aggregates in setup) | Gap |
| Medium | Document actual PKs for `corporate_actions` and `macro_indicators` | Doc |
| Low | Schedule derived metrics (and optionally weekly) job after bhavcopy/pipeline | Feature |
| Low | Implement macro/derivatives/intraday data sources and jobs | Feature |
| Low | Optional: corporate_actions upsert or unique constraint to avoid duplicates | Enhancement |

---

## 6. Quick reference

| Layer | File(s) | Status |
|-------|---------|--------|
| Schema | `setup_databases.py` (POSTGRESQL_SCHEMA) | Done (14 tables, 40+ indexes) |
| Store | `timeseries_store.py` | Done (12 upsert + 1 insert + 17+ get); 2 bugs/gaps above |
| Pipeline | `pipeline_service.py` (_persist_to_timeseries) | Done for 9 categories; macro/derivatives/intraday noted as future |
| Derivation | `jobs/derive_metrics.py` | Done; not scheduled |
| API | `server.py` (timeseries + health + screener) | Done |
| PG Control | `pg_control_service.py`, `routes/pg_control.py`, PostgresControl.jsx | Done |
| Tests | `test_pipeline.py` (--db-only) | Referenced in docs |

---

**Conclusion:** Core PostgreSQL work is in place (schema, store, pipeline persistence for 9 tables, derivation job, API, screener, PG Control). Remaining work: fix corporate action date parsing and `adjusted_close` in `upsert_prices`, then optional improvements (weekly/monthly without TimescaleDB, scheduling, macro/derivatives/intraday sources, and doc corrections).
