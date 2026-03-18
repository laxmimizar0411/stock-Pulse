# Stock Pulse — Phase 1: Data Infrastructure Hardening
## Complete Build Map with File-Level Route Mapping

**Priority**: CRITICAL — Every subsequent phase depends on reliable data
**Brain→Core References**: Doc 1 Sec 18-19 (Data Architecture, Indian Market Sources), Doc 3 Sec H (Indian Data Vendors), Architecture Roadmap Sec 2 (Data Acquisition), V2 Data Requirements (160 fields), Missing Components Addendum 4 (Failure Modes)

---

## CURRENT STATE AUDIT (Verified Against Codebase)

### What's Working
| Component | File | Status | Details |
|-----------|------|--------|---------|
| NSE Bhavcopy Extractor | `backend/data_extraction/extractors/nse_bhavcopy_extractor.py` | FUNCTIONAL | Downloads new UDiFF + legacy format, rate-limited, caching |
| yfinance Extractor | `backend/data_extraction/extractors/yfinance_extractor.py` | FUNCTIONAL | 2yr history, OHLCV, fundamentals, 20 fields, .NS/.BO suffix mapping |
| Screener.in Extractor | `backend/data_extraction/extractors/screener_extractor.py` | PARTIAL | HTML scraping fragile, fallback regex works, income/BS/CF/shareholding |
| Groww API Extractor | `backend/data_extraction/extractors/grow_extractor.py` | FUNCTIONAL | TOTP auth, retry/backoff, latency tracking — but NOT wired into orchestrator |
| Pipeline Orchestrator | `backend/data_extraction/pipeline/orchestrator.py` | FUNCTIONAL | 6-stage async pipeline — only uses NSE Bhavcopy + yfinance (not Screener/Groww) |
| Data Cleaner | `backend/data_extraction/processors/cleaner.py` | FUNCTIONAL | Numeric coercion, string normalization, invalid value removal |
| Calculation Engine | `backend/data_extraction/processors/calculation_engine.py` | FUNCTIONAL | Derived metrics from shareholding_history and price series |
| Technical Calculator | `backend/data_extraction/processors/technical_calculator.py` | PARTIAL | 9 of 15 indicators computed; 6 are schema-only stubs (see below) |
| Validation Engine | `backend/data_extraction/processors/validation_engine.py` | FUNCTIONAL | 30 rules (D1-D10, R1-R10, Q1-Q10) all operational |
| Confidence Scorer | `backend/data_extraction/quality/confidence_scorer.py` | FUNCTIONAL | 4-component weighted model (completeness 40%, freshness 30%, agreement 15%, validation 15%) |
| Field Definitions | `backend/data_extraction/config/field_definitions.py` | DEFINED | 160 fields across 13 categories |
| MongoDB Store | `backend/data_extraction/storage/mongodb_store.py` | FUNCTIONAL | stock_data, price_history, extraction_log, quality_reports, pipeline_jobs |
| Scheduler | `backend/server.py` routes | FUNCTIONAL | POST /pipeline/scheduler/start|stop — custom async, configurable interval |
| Market Indices | `backend/services/market_data_service.py` | PARTIAL | 4 indices only: NIFTY_50, SENSEX, NIFTY_BANK, INDIA_VIX — no sectoral |
| PostgreSQL Schema | `backend/setup_databases.py` | FUNCTIONAL | 14 tables, 40+ indexes, corporate_actions with SEBI fields |
| All 7 Jobs | `backend/jobs/*.py` | FUNCTIONAL | derive_metrics, derivatives, intraday, macro, ml_features, valuation, shareholding |

### What's Broken / Missing
| Gap | Impact | Where It's Expected |
|-----|--------|-------------------|
| 6 technical indicators NOT computed | Stochastic, CCI, Williams %R, CMF, Ichimoku columns are always NULL | `technical_calculator.py` |
| Split/bonus price adjustment NOT implemented | Historical prices not adjusted for corporate actions | `validation_engine.py` / new job |
| Groww extractor NOT in orchestrator | Premium data source unused in pipeline | `orchestrator.py` |
| Screener extractor NOT in orchestrator | Fundamental data not flowing through main pipeline | `orchestrator.py` |
| Only 2 of 160 fields have backup_source | Single point of failure for most data | `field_definitions.py` |
| No sectoral index data | Missing NIFTY IT, NIFTY PHARMA, NIFTY AUTO etc. | `market_data_service.py` |
| No FII/DII daily flow data | Critical Indian market signal not extracted | No extractor exists |
| No bulk/block deal data | Missing institutional activity signals | No extractor exists |
| No earnings calendar / event dates | next_earnings_date always NULL | No reliable source wired |
| Macro indicators limited | Only 4 yfinance tickers; RBI data via env vars only | `macro_indicators_job.py` |
| ml_features_job leaves 11 fields NULL | momentum_rank_sector, fii/dii_net_activity, etc. | `ml_features_job.py` |
| No data freshness alerting | Stale data goes unnoticed | Nothing exists |
| DataPipeline.jsx shows limited real status | Frontend exists but pipeline visibility incomplete | `frontend/src/pages/DataPipeline.jsx` |
| No TimescaleDB hypertables | Plain PostgreSQL — no continuous aggregates or compression | `setup_databases.py` |
| No cross-source data reconciliation | Price discrepancies between sources go undetected | Nothing exists |

---

## PHASE 1 BUILD MAP — 8 Steps

### Dependency Graph
```
Step 1 (Fix Orchestrator) ──────────────────────────────────────────►
    │
    ├──► Step 2 (Complete Technical Indicators) ────────────────────►
    │
    ├──► Step 3 (Add Missing Extractors) ──────────────────────────►
    │        │
    │        └──► Step 4 (Corporate Action Adjustment) ────────────►
    │
    ├──► Step 5 (Fill NULL Fields in Jobs) ─────────────────────────►
    │
    ├──► Step 6 (Data Quality & Reconciliation) ───────────────────►
    │
    ├──► Step 7 (Scheduler & EOD Pipeline) ────────────────────────►
    │
    └──► Step 8 (Frontend Pipeline Visibility) ────────────────────►
```

Steps 2-6 can be done in parallel after Step 1. Steps 7-8 depend on 1-6 being stable.

---

### STEP 1: Wire All Extractors Into Orchestrator
**Why**: Groww and Screener extractors exist but aren't used. The pipeline only uses NSE Bhavcopy + yfinance, which means fundamental data, detailed shareholding, and premium Groww quotes never flow through.

**Files to modify:**
| File | Change |
|------|--------|
| `backend/data_extraction/pipeline/orchestrator.py` | Add ScreenerExtractor and GrowwAPIExtractor to extractor list; add fallback logic if Groww TOTP not configured |
| `backend/data_extraction/config/field_definitions.py` | Add `backup_source` for fields where multiple extractors can provide the same data (currently only 2 of 160 have it) |

**Specific tasks:**
- [ ] **1.1** In `orchestrator.py`, import `ScreenerExtractor` and `GrowwAPIExtractor`
- [ ] **1.2** In `orchestrator.py.__init__()`, initialize both extractors with try/except (Groww needs TOTP env vars — graceful skip if missing)
- [ ] **1.3** In `orchestrator._process_symbol()`, call Screener extractor after yfinance to fill fundamental fields (income statement, balance sheet, cash flow, shareholding history)
- [ ] **1.4** In `orchestrator._process_symbol()`, call Groww extractor as optional enrichment for real-time quotes and premium data
- [ ] **1.5** Add merge logic: when multiple sources provide the same field, prefer by source priority:
  - Price/OHLCV: NSE Bhavcopy > Groww > yfinance (official exchange data wins per Architecture Roadmap Sec 2.4)
  - Fundamentals: Screener.in > yfinance (closest to raw filings)
  - Real-time quotes: Groww > yfinance (lower latency)
- [ ] **1.6** In `field_definitions.py`, populate `backup_source` for all fields where a second extractor can provide the same data. Currently ~30+ fields have dual coverage (yfinance + screener for PE, PB, market_cap; yfinance + bhavcopy for OHLCV; etc.)
- [ ] **1.7** Log source conflicts to `extraction_log` MongoDB collection for review (per Architecture Roadmap Sec 2.4: "Log all conflicts for periodic review")

**Brain→Core mapping**: Doc 1 Sec 18.2 (Pipeline Architecture: "Ingestion → Processing → Storage"), Architecture Roadmap Sec 2.4 (Conflicting Data Resolution)

**Route affected**: `POST /api/extraction/run` → `orchestrator.run()` → now uses all 4 extractors

---

### STEP 2: Complete Technical Indicator Library
**Why**: 6 indicators exist in the PostgreSQL `technical_indicators` table schema but `technical_calculator.py` doesn't compute them. Those columns are always NULL, breaking any downstream scoring or ML feature that depends on them.

**Files to modify:**
| File | Change |
|------|--------|
| `backend/data_extraction/processors/technical_calculator.py` | Add 6 missing indicator computations |

**Currently computed (9):** SMA(20,50,200), EMA(12,26), RSI(14), MACD+Signal, Bollinger(20,2), ATR(14), ADX(14), OBV, Support/Resistance

**Must add (6 — already in DB schema from `setup_databases.py`):**
- [ ] **2.1** Stochastic %K and %D (14,3) — `stoch_k`, `stoch_d` columns exist
  ```
  %K = 100 × (Close - Lowest Low(14)) / (Highest High(14) - Lowest Low(14))
  %D = SMA(%K, 3)
  ```
- [ ] **2.2** CCI(20) — `cci_20` column exists
  ```
  CCI = (Typical Price - SMA(TP, 20)) / (0.015 × Mean Deviation)
  Typical Price = (High + Low + Close) / 3
  ```
- [ ] **2.3** Williams %R(14) — `williams_r` column exists
  ```
  %R = (Highest High(14) - Close) / (Highest High(14) - Lowest Low(14)) × -100
  ```
- [ ] **2.4** Chaikin Money Flow(20) — `cmf` column exists
  ```
  MFM = ((Close - Low) - (High - Close)) / (High - Low)
  MFV = MFM × Volume
  CMF = SUM(MFV, 20) / SUM(Volume, 20)
  ```
- [ ] **2.5** Ichimoku Cloud — `ichimoku_tenkan`, `ichimoku_kijun`, `ichimoku_senkou_a`, `ichimoku_senkou_b` columns exist
  ```
  Tenkan-sen = (Highest High(9) + Lowest Low(9)) / 2
  Kijun-sen = (Highest High(26) + Lowest Low(26)) / 2
  Senkou A = (Tenkan + Kijun) / 2, shifted 26 periods forward
  Senkou B = (Highest High(52) + Lowest Low(52)) / 2, shifted 26 periods forward
  ```
- [ ] **2.6** Update `calculate_all()` method to include new indicators in the output dict with matching column names from `setup_databases.py`

**Additional indicators to add (NOT in current schema — requires schema migration):**
These are referenced in Brain→Core Doc 1 Sec 20, Doc 3 Sec F, and Architecture Roadmap Sec 3.1C as essential:
- [ ] **2.7** VWAP (Volume Weighted Average Price) — needed by Doc 3 Sec F.1 for execution benchmarking
- [ ] **2.8** MFI (Money Flow Index, 14) — momentum indicator from Doc 1 Sec 20
- [ ] **2.9** Parabolic SAR — trend indicator from Doc 1 Sec 20
- [ ] **2.10** Supertrend — popular Indian market indicator

For 2.7-2.10: Add columns to `technical_indicators` table via new Alembic migration in `backend/alembic/versions/`.

**Brain→Core mapping**: Doc 1 Sec 20 (Technical Indicators — lists 36+ indicators), Doc 3 Sec F.2 (Indian Market Momentum requires stochastic + OBV), V2 Data Requirements Category 12

**Route affected**: Pipeline orchestrator step 4 (TechnicalCalculator.calculate_all) → `timeseries_store.upsert_technical_indicators()` → fills previously-NULL columns

---

### STEP 3: Add Missing Data Extractors
**Why**: Several critical Indian market data types have no extraction source at all. FII/DII flows are the single most important India-specific signal (Doc 1 Sec 19, Doc 4 Sec C.1 MMI component #1). Sectoral indices are needed for relative scoring.

**Files to create / modify:**
| File | Change |
|------|--------|
| NEW: `backend/data_extraction/extractors/nse_index_extractor.py` | Fetch index data from NSE/yfinance |
| NEW: `backend/data_extraction/extractors/nse_fii_dii_extractor.py` | Fetch FII/DII daily activity |
| `backend/services/market_data_service.py` | Add sectoral indices to INDIAN_INDICES dict |
| `backend/jobs/macro_indicators_job.py` | Wire FII/DII data into macro_indicators table |
| `backend/data_extraction/pipeline/orchestrator.py` | Add new extractors to pipeline |
| `backend/setup_databases.py` | Add Alembic migration if new columns needed |

**Specific tasks:**

#### 3A: Sectoral Index Data
- [ ] **3.1** In `market_data_service.py`, add sectoral indices to INDIAN_INDICES:
  ```python
  "NIFTY_IT": "^CNXIT",
  "NIFTY_PHARMA": "^CNXPHARMA",
  "NIFTY_AUTO": "^CNXAUTO",
  "NIFTY_BANK": "^NSEBANK",        # already exists
  "NIFTY_FMCG": "^CNXFMCG",
  "NIFTY_METAL": "^CNXMETAL",
  "NIFTY_REALTY": "^CNXREALTY",
  "NIFTY_ENERGY": "^CNXENERGY",
  "NIFTY_INFRA": "^CNXINFRA",
  "NIFTY_PSE": "^CNXPSE",
  "NIFTY_500": "^CRSLDX",
  "NIFTY_MIDCAP_100": "^NSEMDCP100",
  "NIFTY_SMALLCAP_100": "^NSESMLCP100",
  ```
- [ ] **3.2** Create `nse_index_extractor.py` extending `base_extractor.py` — fetch daily OHLCV for all indices via yfinance, store in a new `index_daily` PostgreSQL table or use existing macro_indicators with `indicator_name` as index symbol
- [ ] **3.3** Wire index extractor into `macro_indicators_job.py` to run as part of daily macro update

#### 3B: FII/DII Daily Activity
- [ ] **3.4** Create `nse_fii_dii_extractor.py` — scrape NSE's FII/DII daily activity page (https://www.nseindia.com/reports/fii-dii) or use the NSE API endpoint for institutional activity
  - Data fields: fii_buy_value, fii_sell_value, fii_net_value, dii_buy_value, dii_sell_value, dii_net_value, date
  - Rate-limited with NSE session cookie handling (NSE blocks without proper headers)
- [ ] **3.5** Store FII/DII data: either add columns to `macro_indicators` table or create a new `institutional_activity_daily` table via Alembic migration
- [ ] **3.6** In `ml_features_job.py`, use FII/DII data to fill the currently-NULL `fii_net_activity_daily` and `dii_net_activity_daily` columns in `ml_features_daily`

#### 3C: Bulk/Block Deals (Lower priority — nice to have)
- [ ] **3.7** Create extractor for NSE bulk/block deal data (optional, available from NSE reports page)
- [ ] **3.8** Store in `corporate_actions` table with `action_type = 'BULK_DEAL'` or `'BLOCK_DEAL'`

**Brain→Core mapping**: Doc 1 Sec 19 (Indian Market specifics — "FII/DII flow data: Critical signal unique to Indian markets"), Doc 4 Sec C.2 MMI (7 components: #1 is FII Activity), Doc 2 Sec O (Multi-Horizon Alpha — "Cross-Asset Lead-Lag"), Architecture Roadmap Sec 2.2 (Data Source Tiers)

**Routes affected**:
- `GET /api/market/overview` → now returns sectoral indices
- `POST /api/jobs/run/macro-indicators` → now includes FII/DII and index data
- `GET /api/timeseries/macro-indicators` → returns richer dataset

---

### STEP 4: Corporate Action Price Adjustment
**Why**: The `corporate_actions` table stores split ratios and bonus ratios, but historical prices are NEVER adjusted. A 1:10 stock split makes the stock appear to have crashed 90%. This corrupts every derived metric, technical indicator, and ML feature.

**Files to modify / create:**
| File | Change |
|------|--------|
| NEW: `backend/jobs/corporate_action_adjustment_job.py` | New job to adjust historical prices |
| `backend/services/timeseries_store.py` | Add `get_corporate_actions()` and `bulk_update_prices()` methods |
| `backend/data_extraction/processors/validation_engine.py` | Add split/bonus detection heuristic |
| `backend/server.py` | Add trigger route `POST /api/jobs/run/adjust-prices` |

**Specific tasks:**
- [ ] **4.1** Create `corporate_action_adjustment_job.py`:
  - Query `corporate_actions` table for all STOCK_SPLIT, BONUS events
  - For each event: fetch all `prices_daily` rows for that symbol BEFORE the ex_date
  - Apply adjustment factor:
    - Stock split "1:5" → multiply all pre-split close/open/high/low by 1/5, multiply volume by 5
    - Bonus "1:1" → multiply all pre-bonus prices by 1/2, multiply volume by 2
  - Add `adjusted` boolean column to `prices_daily` via migration to prevent re-adjustment
  - Log all adjustments
- [ ] **4.2** In `validation_engine.py`, add heuristic detection: if day-over-day price change > 40% AND a corporate action exists near that date, flag for adjustment review
- [ ] **4.3** In `timeseries_store.py`, add `bulk_update_prices(symbol, adjustments: list[dict])` for batch-updating historical prices
- [ ] **4.4** Add route in `server.py`: `POST /api/jobs/run/adjust-prices` → triggers the adjustment job
- [ ] **4.5** Run adjustment job after every pipeline extraction (or on-demand)

**Brain→Core mapping**: Doc 1 Sec 18.2 ("Processing: Cleaning, split/bonus adjustment"), Architecture Roadmap Sec 2.4 (Data Validation — "split/bonus adjustment"), V2 Data Requirements Category 10 (Corporate Actions)

**Route affected**: New `POST /api/jobs/run/adjust-prices`, and all price-dependent routes become accurate post-adjustment

---

### STEP 5: Fill NULL Fields in Existing Jobs
**Why**: Several jobs leave important columns as NULL because the data sources aren't connected yet. Steps 1 and 3 provide the data; this step wires it into the jobs.

**Files to modify:**
| File | NULL Fields to Fill | Data Source |
|------|-------------------|-------------|
| `backend/jobs/ml_features_job.py` | `fii_net_activity_daily`, `dii_net_activity_daily` | FII/DII extractor from Step 3B |
| `backend/jobs/ml_features_job.py` | `nifty_50_return_1m` | `macro_indicators` or index data from Step 3A |
| `backend/jobs/ml_features_job.py` | `turnover_20d_avg` | `prices_daily.turnover` (already in DB) |
| `backend/jobs/ml_features_job.py` | `volatility_percentile_1y` | Compute from `realized_volatility_20d` over 252 days |
| `backend/jobs/ml_features_job.py` | `momentum_rank_sector` | Requires sector mapping + ranking within sector |
| `backend/jobs/ml_features_job.py` | `free_float_market_cap` | `shareholding_quarterly.public_holding` × market_cap |
| `backend/jobs/ml_features_job.py` | `days_since_earnings`, `days_to_earnings` | `corporate_actions.next_earnings_date` (if available) |
| `backend/jobs/macro_indicators_job.py` | `repo_rate`, `reverse_repo_rate`, `cpi_inflation`, `iip_growth` | Currently env-var fallback only; add RBI data scraping |

**Specific tasks:**
- [ ] **5.1** In `ml_features_job.py`, after computing basic features, query `macro_indicators` for latest FII/DII net values and populate `fii_net_activity_daily`, `dii_net_activity_daily`
- [ ] **5.2** In `ml_features_job.py`, compute `nifty_50_return_1m` from `macro_indicators` or index prices (fetch Nifty 50 close 21 trading days ago, compute return)
- [ ] **5.3** In `ml_features_job.py`, compute `turnover_20d_avg` from `prices_daily.turnover` using 20-day rolling mean (data already exists in DB)
- [ ] **5.4** In `ml_features_job.py`, compute `volatility_percentile_1y` — rank current `realized_volatility_20d` against its own 252-day history, express as percentile
- [ ] **5.5** In `ml_features_job.py`, compute `momentum_rank_sector`:
  - Requires a sector lookup (yfinance provides sector in fundamentals, or use static mapping in `market_data_service.py`)
  - For each stock, compute 3-month return, rank within its sector, normalize to 0-100
- [ ] **5.6** In `ml_features_job.py`, compute `free_float_market_cap` = latest `shareholding_quarterly.public_holding` × latest market_cap from `valuation_daily`
- [ ] **5.7** In `macro_indicators_job.py`, add RBI data sources for `repo_rate`, `cpi_inflation` — either scrape RBI website or use a static update mechanism (these change infrequently: repo rate changes ~4x/year, CPI monthly)
- [ ] **5.8** `days_since_earnings` and `days_to_earnings` — mark as DEFERRED unless reliable earnings calendar source found. Leave as NULL with a comment explaining why.

**Brain→Core mapping**: Doc 1 Sec 18.1 (Data Categories — Feature Store must have complete features), Doc 1 Sec 20 (Feature Engineering — "Indian market features: FII/DII flow momentum"), V2 Data Requirements Categories 3, 11

**Routes affected**: `GET /api/timeseries/ml-features/{symbol}` returns fuller data; `GET /api/timeseries/macro-indicators` returns RBI rates

---

### STEP 6: Data Quality, Reconciliation & Freshness Monitoring
**Why**: With 4 extractors feeding data, price discrepancies between sources will occur. The Missing Components doc (Addendum 4) mandates explicit failure mode handling. Architecture Roadmap Sec 2.4 requires conflict logging and resolution.

**Files to modify / create:**
| File | Change |
|------|--------|
| `backend/data_extraction/quality/confidence_scorer.py` | Enhance source_agreement scoring to actually cross-check |
| NEW: `backend/services/data_freshness_service.py` | Monitor data staleness, generate alerts |
| `backend/data_extraction/pipeline/orchestrator.py` | Add reconciliation step after extraction |
| `backend/services/alerts_service.py` | Add system-level data freshness alerts |
| `backend/server.py` | Add `GET /api/data-quality/status` route |

**Specific tasks:**
- [ ] **6.1** Create `data_freshness_service.py`:
  - Query each PostgreSQL table's MAX(date) or MAX(created_at)
  - Compare against expected freshness thresholds (from `field_definitions.py` update_frequency):
    - `prices_daily`: should be updated by 16:00 IST on trading days
    - `fundamentals_quarterly`: should be < 120 days old
    - `macro_indicators`: should be < 2 days old for daily items
    - `shareholding_quarterly`: should be < 120 days old
  - Return stale tables with severity (WARNING: 1 day late, CRITICAL: 3+ days late)
- [ ] **6.2** In `orchestrator.py`, after all extractors run for a symbol, add a reconciliation step:
  - Compare OHLCV from NSE Bhavcopy vs yfinance vs Groww
  - If close prices differ by > 1%, log to `extraction_log` with severity WARNING
  - Use NSE Bhavcopy as authoritative source (official exchange data)
- [ ] **6.3** In `confidence_scorer.py`, enhance `_calculate_source_agreement()`:
  - Currently scores agreement but doesn't actually compare multiple source values
  - Add actual cross-source comparison using extraction records from MongoDB
- [ ] **6.4** Add `GET /api/data-quality/status` route in `server.py`:
  - Returns per-table freshness, row counts, last update timestamps
  - Returns any active reconciliation warnings
  - Returns overall data health score
- [ ] **6.5** In `alerts_service.py`, add system alert type `DATA_STALE`:
  - Auto-generate alerts when data freshness thresholds breached
  - Show in frontend Alerts page alongside user price alerts
- [ ] **6.6** Implement graceful degradation per Missing Components Addendum 4:
  - If a critical data source fails, continue with cached data + staleness flag
  - If minimum required fields unavailable (per `field_definitions.py` CRITICAL priority), block analysis and return clear error
  - Define the critical fields list: close_price, volume, pe_ratio, roe, debt_to_equity, promoter_holding (minimum viable analysis)

**Brain→Core mapping**: Architecture Roadmap Sec 2.4 (Missing Data Strategy, Conflicting Data Resolution), Missing Components Addendum 2 (Confidence Output), Addendum 4 (Failure Modes, Graceful Degradation Levels), Doc 1 Sec 18.2 ("quality monitoring")

**Route added**: `GET /api/data-quality/status` (new)
**Routes affected**: All analysis routes now respect data freshness; `GET /api/alerts` includes system data alerts

---

### STEP 7: Scheduler & EOD Pipeline Orchestration
**Why**: The scheduler exists (`POST /pipeline/scheduler/start`) but it only triggers pipeline extraction. A proper EOD pipeline must chain: extract → clean → compute indicators → derive metrics → update scores → check alerts. Currently these are all separate manual triggers.

**Files to modify:**
| File | Change |
|------|--------|
| `backend/services/pipeline_service.py` | Add `run_eod_pipeline()` that chains all steps |
| `backend/server.py` | Add `POST /api/pipeline/run-eod` route |
| `backend/server.py` | Enhance scheduler to run full EOD chain |

**Specific tasks:**
- [ ] **7.1** In `pipeline_service.py`, create `run_eod_pipeline(symbols=None)`:
  ```
  Step 1: Run orchestrator.run(symbols) — extraction + clean + calculate + validate
  Step 2: Run derive_metrics.compute_derived_metrics(ts_store, symbols)
  Step 3: Run derive_metrics.compute_weekly_metrics(ts_store, symbols)
  Step 4: Run ml_features_job (for the symbols)
  Step 5: Run valuation_job (for the symbols)
  Step 6: Run corporate_action_adjustment_job (if new actions detected)
  Step 7: Check all active alerts against new data
  Step 8: Update data freshness status
  Step 9: Log pipeline run to MongoDB pipeline_jobs collection
  ```
  Each step logs success/failure. Pipeline continues even if non-critical steps fail (graceful degradation).
- [ ] **7.2** Add `POST /api/pipeline/run-eod` route in `server.py` — triggers full EOD pipeline
- [ ] **7.3** Create market-hours-aware scheduling:
  ```
  Pre-market (09:00 IST): Fetch overnight news, macro data, global index moves
  Post-market (15:45 IST): Full EOD pipeline — bhavcopy + indicators + scores + alerts
  Weekly (Saturday): Fundamental data refresh (screener), shareholding update
  Monthly (1st): Macro indicators refresh, data quality audit
  ```
  Implement in `pipeline_service.py` scheduler with IST timezone awareness
- [ ] **7.4** Add pipeline run history tracking:
  - Store in MongoDB `pipeline_jobs` collection (already exists)
  - Fields: start_time, end_time, status, symbols_processed, errors, step_timings
- [ ] **7.5** Make scheduler respect Indian market calendar (skip weekends, NSE holidays)

**Brain→Core mapping**: Doc 1 Sec 18.2 ("Batch: Scheduled jobs for fundamentals, macro, alternative data"), Doc 1 Sec 19 ("Market hours: 09:15-15:30 IST"), Architecture Roadmap Sec 5.1 (Complete Analysis Pipeline — 6 phases)

**Routes added**: `POST /api/pipeline/run-eod`
**Routes affected**: `POST /pipeline/scheduler/start` now runs full chain, not just extraction

---

### STEP 8: Frontend Pipeline Visibility
**Why**: `DataPipeline.jsx` (32KB) exists and has a UI, but it needs to display real pipeline status from the new EOD pipeline, data freshness, and reconciliation warnings.

**Files to modify:**
| File | Change |
|------|--------|
| `frontend/src/pages/DataPipeline.jsx` | Add data freshness panel, EOD pipeline status, reconciliation warnings |
| `backend/server.py` | Ensure all new routes are CORS-enabled and return consistent JSON |

**Specific tasks:**
- [ ] **8.1** Add "Data Freshness" panel to DataPipeline.jsx:
  - Call `GET /api/data-quality/status`
  - Show per-table last-update timestamps with color coding (green=fresh, yellow=warning, red=stale)
  - Show overall data health score
- [ ] **8.2** Add "EOD Pipeline" panel:
  - Call `GET /api/pipeline/history` (already exists)
  - Show last pipeline run with per-step status (Step 1: Extract ✓, Step 2: Derive ✓, etc.)
  - Show time taken for each step
  - Button to trigger `POST /api/pipeline/run-eod`
- [ ] **8.3** Add "Data Quality Warnings" panel:
  - Show active reconciliation warnings (source price mismatches)
  - Show fields with low confidence scores
  - Show symbols where analysis is blocked due to insufficient data
- [ ] **8.4** Add "Scheduler Status" indicator:
  - Show if scheduler is running, next scheduled run time
  - Controls to start/stop/reconfigure scheduler

**Brain→Core mapping**: Architecture Roadmap Sec 4.4 (Data Freshness Indicators — "Every data point displayed includes a freshness indicator"), Missing Components Addendum 2.1 (Confidence Output — "Missing: Promoter pledging, Contingent liab." style display)

---

## PHASE 1 COMPLETION CHECKLIST

When all 8 steps are done, verify:

| Checkpoint | How to Verify |
|-----------|---------------|
| All 4 extractors run in pipeline | `POST /api/extraction/run` with a symbol → check MongoDB extraction_log shows records from bhavcopy, yfinance, screener, groww |
| All 15 technical indicators populated | `GET /api/timeseries/technicals/{symbol}` → no NULL columns for stoch_k, cci_20, williams_r, cmf, ichimoku_* |
| Corporate action adjustment works | Find a stock with a known split (e.g., RELIANCE 1:10 in Sept 2020) → verify pre-split prices are adjusted |
| FII/DII data flowing | `GET /api/timeseries/macro-indicators` → fii_net_flow and dii_net_flow have recent values |
| Sectoral indices available | `GET /api/market/overview` → returns NIFTY_IT, NIFTY_PHARMA, etc. |
| ML features mostly filled | `GET /api/timeseries/ml-features/{symbol}` → fii_net_activity, nifty_50_return_1m, turnover_20d_avg, volatility_percentile populated |
| Data freshness monitored | `GET /api/data-quality/status` → returns per-table freshness with severity levels |
| Cross-source reconciliation | Check MongoDB extraction_log for reconciliation warnings when prices disagree |
| EOD pipeline runs end-to-end | `POST /api/pipeline/run-eod` → completes all 9 steps, logged in pipeline_jobs |
| Scheduler is market-aware | Scheduler skips weekends and NSE holidays |
| Frontend shows pipeline health | DataPipeline.jsx shows freshness, pipeline history, quality warnings |
| Graceful degradation works | Kill Redis → system falls back to in-memory cache. Block screener.in → pipeline continues with other sources. |

---

## ITEMS REMOVED FROM ORIGINAL PHASE 1

| Original Item | Reason Removed | Where It Goes |
|---------------|---------------|---------------|
| "TimescaleDB optimization: hypertables, continuous aggregates" | Plain PostgreSQL 16 works fine at current scale. TimescaleDB adds operational complexity. Only needed if table sizes exceed ~100M rows. | Phase 9 (Production Hardening) — add only when performance profiling shows need |
| "Redis feature store setup" | Redis is already used for caching. A formal feature store (Feast/Redis) is needed when ML models are in production. No models exist yet. | Phase 5 (ML Models) — build alongside first real model |
| "Multi-timeframe aggregates (1min, 5min, 15min)" | No intraday data source exists yet. Bhavcopy is EOD only. Groww provides daily candles. Sub-daily data requires broker WebSocket (Zerodha/Angel One). | Phase 9 (Real-Time Infrastructure) |
| "MongoDB schema finalization" | MongoDB schema is already functional with 10 collections + indexes. No finalization needed — it adapts as extractors add data. | N/A — already done |

---

## ITEMS ADDED (Not in Original Phase 1)

| New Item | Why It's Phase 1 | Brain→Core Reference |
|----------|-----------------|---------------------|
| Wire Groww + Screener into orchestrator | Extractors exist but aren't used — wasted code | Architecture Roadmap Sec 2.2 (Multi-tier sources) |
| Complete 6 missing technical indicators | DB schema expects them, everything downstream gets NULLs | Doc 1 Sec 20, V2 Data Requirements Cat 12 |
| Corporate action price adjustment | Without this, all historical analysis is corrupted by splits/bonuses | Doc 1 Sec 18.2, Architecture Roadmap Sec 2.4 |
| Fill NULL fields in ml_features_job | 11 of 21 ML feature columns are always NULL | V2 Data Requirements Cat 3 |
| Data freshness monitoring | No alerting when data goes stale — silent failures | Missing Components Addendum 4, Architecture Roadmap Sec 4.4 |
| Cross-source reconciliation | 4 sources with no conflict detection | Architecture Roadmap Sec 2.4 |
| EOD pipeline chaining | Individual jobs exist but aren't orchestrated end-to-end | Doc 1 Sec 18.2, Architecture Roadmap Sec 5.1 |
| Market-hours-aware scheduler | Current scheduler is interval-based, not market-aware | Doc 1 Sec 19 (Market hours 09:15-15:30 IST) |

---

## ESTIMATED FILE CHANGES SUMMARY

| Files Modified | Files Created |
|---------------|--------------|
| `backend/data_extraction/pipeline/orchestrator.py` | `backend/data_extraction/extractors/nse_fii_dii_extractor.py` |
| `backend/data_extraction/processors/technical_calculator.py` | `backend/data_extraction/extractors/nse_index_extractor.py` |
| `backend/data_extraction/config/field_definitions.py` | `backend/jobs/corporate_action_adjustment_job.py` |
| `backend/data_extraction/quality/confidence_scorer.py` | `backend/services/data_freshness_service.py` |
| `backend/jobs/ml_features_job.py` | `backend/alembic/versions/v1_1_0_phase1_additions.py` (migration) |
| `backend/jobs/macro_indicators_job.py` | |
| `backend/services/market_data_service.py` | |
| `backend/services/pipeline_service.py` | |
| `backend/services/timeseries_store.py` | |
| `backend/services/alerts_service.py` | |
| `backend/data_extraction/processors/validation_engine.py` | |
| `backend/server.py` | |
| `frontend/src/pages/DataPipeline.jsx` | |
| **13 files modified** | **5 files created** |
