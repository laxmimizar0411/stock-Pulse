#!/usr/bin/env python3
"""
StockPulse Database Setup Script

Creates and verifies all three database layers + filesystem directories:
  1. PostgreSQL  – 14 time-series tables with 40+ indexes
     (prices_daily, derived_metrics_daily, technical_indicators,
      ml_features_daily, risk_metrics, valuation_daily,
      fundamentals_quarterly, shareholding_quarterly,
      corporate_actions, macro_indicators, derivatives_daily,
      intraday_metrics, weekly_metrics, schema_migrations)
  2. MongoDB     – 10 collections with indexes + schema validation
  3. Redis       – Connectivity verification
  4. Filesystem  – Required local directories

Usage:
    python setup_databases.py              # Setup ALL databases + filesystem
    python setup_databases.py --postgres   # PostgreSQL only
    python setup_databases.py --mongo      # MongoDB only
    python setup_databases.py --redis      # Redis check only
    python setup_databases.py --check      # Verify all connections (read-only)
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the same directory as this script
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("setup_databases")


# ================================================================
#  PostgreSQL Schema (raw SQL executed as a single batch)
# ================================================================

POSTGRESQL_SCHEMA = """
-- ==============================================
-- StockPulse Time-Series Schema  (PostgreSQL 14+)
-- Complete schema covering all 270+ data fields
-- ==============================================

-- 1. Prices Daily: OHLCV + delivery data (Fields #15-27)
CREATE TABLE IF NOT EXISTS prices_daily (
    symbol          VARCHAR(20)     NOT NULL,
    date            DATE            NOT NULL,
    open            NUMERIC(12,2),
    high            NUMERIC(12,2),
    low             NUMERIC(12,2),
    close           NUMERIC(12,2),
    adjusted_close  NUMERIC(12,2),
    last            NUMERIC(12,2),
    prev_close      NUMERIC(12,2),
    volume          BIGINT,
    turnover        NUMERIC(18,2),
    total_trades    INTEGER,
    delivery_qty    BIGINT,
    delivery_pct    NUMERIC(6,2),
    vwap            NUMERIC(12,2),
    isin            VARCHAR(12),
    series          VARCHAR(5)      DEFAULT 'EQ',
    created_at      TIMESTAMPTZ     DEFAULT now(),
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_prices_date ON prices_daily (date DESC);
CREATE INDEX IF NOT EXISTS idx_prices_symbol_date ON prices_daily (symbol, date DESC);

-- 2. Derived Price Metrics (computed daily, Fields #28-38)
CREATE TABLE IF NOT EXISTS derived_metrics_daily (
    symbol                  VARCHAR(20)     NOT NULL,
    date                    DATE            NOT NULL,
    daily_return_pct        NUMERIC(10,4),
    return_5d_pct           NUMERIC(10,4),
    return_20d_pct          NUMERIC(10,4),
    return_60d_pct          NUMERIC(10,4),
    day_range_pct           NUMERIC(10,4),
    gap_percentage          NUMERIC(10,4),
    week_52_high            NUMERIC(12,2),
    week_52_low             NUMERIC(12,2),
    distance_from_52w_high  NUMERIC(10,4),
    volume_ratio            NUMERIC(10,4),
    avg_volume_20d          BIGINT,
    created_at              TIMESTAMPTZ     DEFAULT now(),
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_derived_date ON derived_metrics_daily (date DESC);
CREATE INDEX IF NOT EXISTS idx_derived_symbol_date ON derived_metrics_daily (symbol, date DESC);

-- 3. Technical Indicators (computed daily from OHLCV, Fields #138-152, #227-229)
CREATE TABLE IF NOT EXISTS technical_indicators (
    symbol           VARCHAR(20)     NOT NULL,
    date             DATE            NOT NULL,
    sma_20           NUMERIC(12,2),
    sma_50           NUMERIC(12,2),
    sma_200          NUMERIC(12,2),
    ema_12           NUMERIC(12,2),
    ema_26           NUMERIC(12,2),
    rsi_14           NUMERIC(6,2),
    macd             NUMERIC(12,4),
    macd_signal      NUMERIC(12,4),
    macd_histogram   NUMERIC(12,4),
    bollinger_upper  NUMERIC(12,2),
    bollinger_lower  NUMERIC(12,2),
    atr_14           NUMERIC(12,4),
    adx_14           NUMERIC(6,2),
    obv              BIGINT,
    support_level    NUMERIC(12,2),
    resistance_level NUMERIC(12,2),
    ichimoku_tenkan  NUMERIC(12,2),
    ichimoku_kijun   NUMERIC(12,2),
    ichimoku_senkou_a NUMERIC(12,2),
    ichimoku_senkou_b NUMERIC(12,2),
    stoch_k          NUMERIC(6,2),
    stoch_d          NUMERIC(6,2),
    cci_20           NUMERIC(10,2),
    williams_r       NUMERIC(6,2),
    cmf              NUMERIC(10,4),
    created_at       TIMESTAMPTZ     DEFAULT now(),
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_tech_date ON technical_indicators (date DESC);
CREATE INDEX IF NOT EXISTS idx_tech_symbol_date ON technical_indicators (symbol, date DESC);

-- 4. Extended ML/Strategy Features (daily, Fields #165-186, #230-233)
CREATE TABLE IF NOT EXISTS ml_features_daily (
    symbol                   VARCHAR(20)     NOT NULL,
    date                     DATE            NOT NULL,
    realized_volatility_10d  NUMERIC(10,4),
    realized_volatility_20d  NUMERIC(10,4),
    return_1d_pct            NUMERIC(10,4),
    return_3d_pct            NUMERIC(10,4),
    return_10d_pct           NUMERIC(10,4),
    momentum_rank_sector     NUMERIC(6,2),
    price_vs_sma20_pct       NUMERIC(10,4),
    price_vs_sma50_pct       NUMERIC(10,4),
    volume_zscore            NUMERIC(10,4),
    volatility_percentile_1y NUMERIC(6,2),
    turnover_20d_avg         NUMERIC(18,2),
    free_float_market_cap    NUMERIC(18,2),
    days_since_earnings      INTEGER,
    days_to_earnings         INTEGER,
    trading_day_of_week      SMALLINT,
    nifty_50_return_1m       NUMERIC(10,4),
    fii_net_activity_daily   NUMERIC(18,2),
    dii_net_activity_daily   NUMERIC(18,2),
    sp500_return_1d          NUMERIC(10,4),
    nasdaq_return_1d         NUMERIC(10,4),
    created_at               TIMESTAMPTZ     DEFAULT now(),
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_ml_date ON ml_features_daily (date DESC);
CREATE INDEX IF NOT EXISTS idx_ml_symbol_date ON ml_features_daily (symbol, date DESC);

-- 5. Risk & Performance Metrics (rolling, Fields #249-256)
CREATE TABLE IF NOT EXISTS risk_metrics (
    symbol                   VARCHAR(20)     NOT NULL,
    date                     DATE            NOT NULL,
    beta_1y                  NUMERIC(10,4),
    beta_3y                  NUMERIC(10,4),
    max_drawdown_1y          NUMERIC(10,4),
    sharpe_ratio_1y          NUMERIC(10,4),
    sortino_ratio_1y         NUMERIC(10,4),
    information_ratio_1y     NUMERIC(10,4),
    rolling_volatility_30d   NUMERIC(10,4),
    downside_deviation_1y    NUMERIC(10,4),
    created_at               TIMESTAMPTZ     DEFAULT now(),
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_risk_date ON risk_metrics (date DESC);
CREATE INDEX IF NOT EXISTS idx_risk_symbol_date ON risk_metrics (symbol, date DESC);

-- 6. Valuation Metrics (daily/weekly, Fields #93-109)
CREATE TABLE IF NOT EXISTS valuation_daily (
    symbol                  VARCHAR(20)     NOT NULL,
    date                    DATE            NOT NULL,
    market_cap              NUMERIC(18,2),
    enterprise_value        NUMERIC(18,2),
    pe_ratio                NUMERIC(10,2),
    pe_ratio_forward        NUMERIC(10,2),
    peg_ratio               NUMERIC(10,4),
    pb_ratio                NUMERIC(10,2),
    ps_ratio                NUMERIC(10,2),
    ev_to_ebitda            NUMERIC(10,2),
    ev_to_sales             NUMERIC(10,2),
    dividend_yield          NUMERIC(8,4),
    fcf_yield               NUMERIC(8,4),
    earnings_yield          NUMERIC(8,4),
    sector_avg_pe           NUMERIC(10,2),
    sector_avg_roe          NUMERIC(8,4),
    industry_avg_pe         NUMERIC(10,2),
    historical_pe_median    NUMERIC(10,2),
    sector_performance      NUMERIC(10,4),
    created_at              TIMESTAMPTZ     DEFAULT now(),
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_val_date ON valuation_daily (date DESC);
CREATE INDEX IF NOT EXISTS idx_val_symbol_date ON valuation_daily (symbol, date DESC);

-- 7. Fundamentals Quarterly (income / balance-sheet / cash-flow, Fields #39-92)
CREATE TABLE IF NOT EXISTS fundamentals_quarterly (
    symbol              VARCHAR(20)     NOT NULL,
    period_end          DATE            NOT NULL,
    period_type         VARCHAR(10)     NOT NULL DEFAULT 'quarterly',
    -- Income Statement (Fields #39-56)
    revenue             NUMERIC(18,2),
    revenue_growth_yoy  NUMERIC(8,4),
    revenue_growth_qoq  NUMERIC(8,4),
    operating_profit    NUMERIC(18,2),
    operating_margin    NUMERIC(8,4),
    gross_profit        NUMERIC(18,2),
    gross_margin        NUMERIC(8,4),
    net_profit          NUMERIC(18,2),
    net_profit_margin   NUMERIC(8,4),
    eps                 NUMERIC(10,2),
    eps_growth_yoy      NUMERIC(8,4),
    interest_expense    NUMERIC(18,2),
    depreciation        NUMERIC(18,2),
    ebitda              NUMERIC(18,2),
    ebit                NUMERIC(18,2),
    other_income        NUMERIC(18,2),
    tax_expense         NUMERIC(18,2),
    effective_tax_rate  NUMERIC(8,4),
    -- Balance Sheet (Fields #57-73)
    total_assets        NUMERIC(18,2),
    total_equity        NUMERIC(18,2),
    total_debt          NUMERIC(18,2),
    long_term_debt      NUMERIC(18,2),
    short_term_debt     NUMERIC(18,2),
    cash_and_equiv      NUMERIC(18,2),
    net_debt            NUMERIC(18,2),
    current_assets      NUMERIC(18,2),
    current_liabilities NUMERIC(18,2),
    inventory           NUMERIC(18,2),
    receivables         NUMERIC(18,2),
    payables            NUMERIC(18,2),
    fixed_assets        NUMERIC(18,2),
    intangible_assets   NUMERIC(18,2),
    reserves_and_surplus NUMERIC(18,2),
    book_value_per_share NUMERIC(12,2),
    contingent_liabilities NUMERIC(18,2),
    -- Cash Flow (Fields #74-81)
    operating_cash_flow NUMERIC(18,2),
    investing_cash_flow NUMERIC(18,2),
    financing_cash_flow NUMERIC(18,2),
    capital_expenditure NUMERIC(18,2),
    free_cash_flow      NUMERIC(18,2),
    dividends_paid      NUMERIC(18,2),
    debt_repayment      NUMERIC(18,2),
    equity_raised       NUMERIC(18,2),
    -- Financial Ratios (Fields #82-92)
    roe                 NUMERIC(8,4),
    roa                 NUMERIC(8,4),
    roic                NUMERIC(8,4),
    debt_to_equity      NUMERIC(8,4),
    interest_coverage   NUMERIC(8,2),
    current_ratio       NUMERIC(8,4),
    quick_ratio         NUMERIC(8,4),
    asset_turnover      NUMERIC(8,4),
    inventory_turnover  NUMERIC(8,4),
    receivables_turnover NUMERIC(8,4),
    dividend_payout_ratio NUMERIC(8,4),
    -- Extended Quarterly (Fields #187-190)
    earnings_surprise_pct    NUMERIC(8,4),
    analyst_rating_consensus NUMERIC(6,2),
    target_price_consensus   NUMERIC(12,2),
    num_analysts             INTEGER,
    -- Extended Annual (Fields #191-194)
    revenue_5y_cagr     NUMERIC(8,4),
    eps_5y_cagr         NUMERIC(8,4),
    roe_5y_avg          NUMERIC(8,4),
    fcf_3y_avg          NUMERIC(18,2),
    created_at          TIMESTAMPTZ     DEFAULT now(),
    PRIMARY KEY (symbol, period_end, period_type)
);

CREATE INDEX IF NOT EXISTS idx_fund_date ON fundamentals_quarterly (period_end DESC);
CREATE INDEX IF NOT EXISTS idx_fund_symbol ON fundamentals_quarterly (symbol, period_end DESC);
CREATE INDEX IF NOT EXISTS idx_fund_period_type ON fundamentals_quarterly (period_type, period_end DESC);

-- 8. Shareholding Quarterly (Fields #110-119)
CREATE TABLE IF NOT EXISTS shareholding_quarterly (
    symbol                  VARCHAR(20)     NOT NULL,
    quarter_end             DATE            NOT NULL,
    promoter_holding        NUMERIC(6,2),
    promoter_pledging       NUMERIC(6,2),
    fii_holding             NUMERIC(6,2),
    dii_holding             NUMERIC(6,2),
    public_holding          NUMERIC(6,2),
    promoter_holding_change NUMERIC(6,2),
    fii_holding_change      NUMERIC(6,2),
    num_shareholders        INTEGER,
    mf_holding              NUMERIC(6,2),
    insurance_holding       NUMERIC(6,2),
    created_at              TIMESTAMPTZ     DEFAULT now(),
    PRIMARY KEY (symbol, quarter_end)
);

CREATE INDEX IF NOT EXISTS idx_share_date ON shareholding_quarterly (quarter_end DESC);
CREATE INDEX IF NOT EXISTS idx_share_symbol ON shareholding_quarterly (symbol, quarter_end DESC);

-- 9. Corporate Actions & Events (Fields #120-129)
CREATE TABLE IF NOT EXISTS corporate_actions (
    id                  SERIAL          PRIMARY KEY,
    symbol              VARCHAR(20)     NOT NULL,
    action_type         VARCHAR(30)     NOT NULL,
    action_date         DATE,
    ex_date             DATE,
    record_date         DATE,
    dividend_per_share  NUMERIC(10,2),
    stock_split_ratio   VARCHAR(20),
    bonus_ratio         VARCHAR(20),
    rights_issue_ratio  VARCHAR(20),
    buyback_details     TEXT,
    next_earnings_date  DATE,
    pending_events      TEXT,
    stock_status        VARCHAR(30)     DEFAULT 'active',
    sebi_investigation  BOOLEAN         DEFAULT FALSE,
    created_at          TIMESTAMPTZ     DEFAULT now(),
    UNIQUE (symbol, action_type, action_date)
);

CREATE INDEX IF NOT EXISTS idx_corp_symbol ON corporate_actions (symbol);
CREATE INDEX IF NOT EXISTS idx_corp_date ON corporate_actions (action_date DESC);
CREATE INDEX IF NOT EXISTS idx_corp_type ON corporate_actions (action_type);
CREATE INDEX IF NOT EXISTS idx_corp_symbol_date ON corporate_actions (symbol, action_date DESC);

-- 10. Macro Indicators Monthly (Fields #238-245)
CREATE TABLE IF NOT EXISTS macro_indicators (
    date                DATE            NOT NULL PRIMARY KEY,
    cpi_inflation       NUMERIC(8,4),
    iip_growth          NUMERIC(8,4),
    rbi_repo_rate       NUMERIC(6,4),
    usdinr_rate         NUMERIC(10,4),
    crude_brent_price   NUMERIC(12,2),
    gold_price          NUMERIC(12,2),
    steel_price         NUMERIC(12,2),
    copper_price        NUMERIC(12,2),
    created_at          TIMESTAMPTZ     DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_macro_date ON macro_indicators (date DESC);

-- 11. Derivatives / F&O Data (Fields #257-270)
CREATE TABLE IF NOT EXISTS derivatives_daily (
    symbol                      VARCHAR(20)     NOT NULL,
    date                        DATE            NOT NULL,
    futures_oi                  BIGINT,
    futures_oi_change_pct       NUMERIC(10,4),
    futures_price_near          NUMERIC(12,2),
    futures_basis_pct           NUMERIC(10,4),
    fii_index_futures_long_oi   BIGINT,
    fii_index_futures_short_oi  BIGINT,
    options_call_oi_total       BIGINT,
    options_put_oi_total        BIGINT,
    put_call_ratio_oi           NUMERIC(8,4),
    put_call_ratio_volume       NUMERIC(8,4),
    options_max_pain_strike     NUMERIC(12,2),
    iv_atm_pct                  NUMERIC(8,4),
    iv_percentile_1y            NUMERIC(6,2),
    pcr_index_level             NUMERIC(8,4),
    created_at                  TIMESTAMPTZ     DEFAULT now(),
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_deriv_date ON derivatives_daily (date DESC);
CREATE INDEX IF NOT EXISTS idx_deriv_symbol_date ON derivatives_daily (symbol, date DESC);

-- 12. Intraday / Hourly Metrics (Fields #221-226)
CREATE TABLE IF NOT EXISTS intraday_metrics (
    symbol                  VARCHAR(20)     NOT NULL,
    timestamp               TIMESTAMPTZ     NOT NULL,
    rsi_hourly              NUMERIC(6,2),
    macd_crossover_hourly   NUMERIC(12,4),
    vwap_intraday           NUMERIC(12,2),
    advance_decline_ratio   NUMERIC(8,4),
    sectoral_heatmap        JSONB,
    india_vix               NUMERIC(8,2),
    created_at              TIMESTAMPTZ     DEFAULT now(),
    PRIMARY KEY (symbol, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_intra_symbol_ts ON intraday_metrics (symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_intra_ts ON intraday_metrics (timestamp DESC);

-- 13. Weekly Aggregates (Fields #234-237)
CREATE TABLE IF NOT EXISTS weekly_metrics (
    symbol                      VARCHAR(20)     NOT NULL,
    week_start                  DATE            NOT NULL,
    sma_weekly_crossover        BOOLEAN,
    support_resistance_weekly   JSONB,
    google_trends_score         NUMERIC(6,2),
    job_postings_growth         NUMERIC(8,4),
    created_at                  TIMESTAMPTZ     DEFAULT now(),
    PRIMARY KEY (symbol, week_start)
);

CREATE INDEX IF NOT EXISTS idx_weekly_date ON weekly_metrics (week_start DESC);
CREATE INDEX IF NOT EXISTS idx_weekly_symbol ON weekly_metrics (symbol, week_start DESC);

-- 14. Database Migrations Tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    id              SERIAL          PRIMARY KEY,
    version         VARCHAR(50)     NOT NULL UNIQUE,
    description     TEXT,
    applied_at      TIMESTAMPTZ     DEFAULT now(),
    checksum        VARCHAR(64)
);

-- Insert initial migration record
INSERT INTO schema_migrations (version, description)
VALUES ('v1.0.0', 'Initial schema with all 14 tables')
ON CONFLICT (version) DO NOTHING;
"""


# ================================================================
#  MongoDB Collection + Index Definitions
# ================================================================

MONGO_COLLECTIONS = {
    "watchlist": {
        "indexes": [
            {"keys": [("symbol", 1)], "unique": True},
        ],
    },
    "portfolio": {
        "indexes": [
            {"keys": [("symbol", 1)], "unique": True},
        ],
    },
    "alerts": {
        "indexes": [
            {"keys": [("id", 1)], "unique": True},
            {"keys": [("symbol", 1)]},
            {"keys": [("status", 1)]},
            {"keys": [("status", 1), ("symbol", 1)]},
        ],
    },
    "stock_data": {
        "indexes": [
            {"keys": [("symbol", 1)], "unique": True},
            {"keys": [("last_updated", -1)]},
            {"keys": [("stock_master.sector", 1)]},
            {"keys": [("stock_master.market_cap_category", 1)]},
        ],
    },
    "price_history": {
        "indexes": [
            {"keys": [("symbol", 1), ("date", -1)], "unique": True},
        ],
    },
    "extraction_log": {
        "indexes": [
            {"keys": [("symbol", 1), ("source", 1), ("started_at", -1)]},
            {"keys": [("status", 1)]},
            {"keys": [("started_at", 1)], "expireAfterSeconds": 7776000},  # 90 days TTL
        ],
    },
    "quality_reports": {
        "indexes": [
            {"keys": [("symbol", 1), ("generated_at", -1)]},
            {"keys": [("generated_at", 1)], "expireAfterSeconds": 7776000},  # 90 days TTL
        ],
    },
    "pipeline_jobs": {
        "indexes": [
            {"keys": [("job_id", 1)], "unique": True},
            {"keys": [("created_at", -1)]},
            {"keys": [("status", 1)]},
            {"keys": [("created_at", 1)], "expireAfterSeconds": 7776000},  # 90 days TTL
        ],
    },
    "news_articles": {
        "indexes": [
            {"keys": [("id", 1)], "unique": True, "sparse": True},
            {"keys": [("published_date", -1)]},
            {"keys": [("related_stocks", 1)]},
            {"keys": [("sentiment", 1)]},
            {"keys": [("source", 1), ("published_date", -1)]},
            {"keys": [("stored_at", 1)]},
        ],
    },
    "backtest_results": {
        "indexes": [
            {"keys": [("id", 1)], "unique": True, "sparse": True},
            {"keys": [("symbol", 1), ("strategy", 1), ("created_at", -1)]},
            {"keys": [("created_at", -1)]},
        ],
    },
}


# ================================================================
#  MongoDB Schema Validation Rules
# ================================================================

MONGO_SCHEMA_VALIDATORS = {
    "watchlist": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["symbol", "name"],
            "properties": {
                "symbol": {
                    "bsonType": "string",
                    "pattern": "^[A-Z0-9&_.-]{1,20}$",
                    "description": "Stock ticker symbol (uppercase, max 20 chars)",
                },
                "name": {
                    "bsonType": "string",
                    "maxLength": 200,
                    "description": "Company name",
                },
                "target_price": {
                    "bsonType": ["double", "int", "null"],
                    "minimum": 0,
                    "description": "Target price must be non-negative",
                },
                "stop_loss": {
                    "bsonType": ["double", "int", "null"],
                    "minimum": 0,
                    "description": "Stop-loss must be non-negative",
                },
                "notes": {
                    "bsonType": ["string", "null"],
                    "maxLength": 2000,
                    "description": "User notes (max 2000 chars)",
                },
                "alerts_enabled": {
                    "bsonType": "bool",
                },
            },
        }
    },
    "portfolio": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["symbol", "name", "quantity", "avg_buy_price"],
            "properties": {
                "symbol": {
                    "bsonType": "string",
                    "pattern": "^[A-Z0-9&_.-]{1,20}$",
                    "description": "Stock ticker symbol",
                },
                "name": {
                    "bsonType": "string",
                    "maxLength": 200,
                },
                "quantity": {
                    "bsonType": ["int", "double"],
                    "minimum": 0,
                    "description": "Number of shares must be non-negative",
                },
                "avg_buy_price": {
                    "bsonType": ["double", "int"],
                    "minimum": 0,
                    "description": "Average buy price must be non-negative",
                },
                "buy_date": {
                    "bsonType": "string",
                },
            },
        }
    },
    "alerts": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["id", "symbol", "condition", "target_value", "status"],
            "properties": {
                "id": {
                    "bsonType": "string",
                    "pattern": "^alert_[a-f0-9]{12}$",
                    "description": "Alert ID format: alert_<12 hex chars>",
                },
                "symbol": {
                    "bsonType": "string",
                    "pattern": "^[A-Z0-9&_.-]{1,20}$",
                },
                "condition": {
                    "bsonType": "string",
                    "enum": ["price_above", "price_below", "price_crosses", "percent_change", "volume_spike"],
                },
                "target_value": {
                    "bsonType": ["double", "int"],
                    "minimum": 0,
                },
                "priority": {
                    "bsonType": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
                "status": {
                    "bsonType": "string",
                    "enum": ["active", "triggered", "expired", "disabled"],
                },
                "trigger_count": {
                    "bsonType": "int",
                    "minimum": 0,
                },
            },
        }
    },
    "stock_data": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["symbol"],
            "properties": {
                "symbol": {
                    "bsonType": "string",
                    "pattern": "^[A-Z0-9&_.-]{1,20}$",
                },
                "company_name": {
                    "bsonType": ["string", "null"],
                    "maxLength": 300,
                },
                "last_updated": {
                    "bsonType": "string",
                },
            },
        }
    },
}


# ================================================================
#  PostgreSQL Setup
# ================================================================

async def setup_postgresql(check_only: bool = False) -> bool:
    """Create PostgreSQL tables and indexes, or just verify they exist."""
    dsn = os.environ.get("TIMESERIES_DSN", "postgresql://localhost:5432/stockpulse_ts")

    try:
        import asyncpg
    except ImportError:
        logger.error("asyncpg not installed. Run: pip install asyncpg")
        return False

    try:
        # Try to connect; auto-create the database if it doesn't exist
        try:
            conn = await asyncpg.connect(dsn)
        except asyncpg.InvalidCatalogNameError:
            db_name = dsn.rsplit("/", 1)[-1].split("?")[0]
            base_dsn = dsn.rsplit("/", 1)[0] + "/postgres"
            logger.info(f"Database '{db_name}' doesn't exist - creating it...")
            sys_conn = await asyncpg.connect(base_dsn)
            await sys_conn.execute(f"CREATE DATABASE {db_name}")
            await sys_conn.close()
            logger.info(f"Created database '{db_name}'")
            conn = await asyncpg.connect(dsn)

        logger.info(f"Connected to PostgreSQL: {dsn}")

        if check_only:
            tables = await conn.fetch(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            table_names = [t["table_name"] for t in tables]
            expected = [
                "prices_daily", "derived_metrics_daily", "technical_indicators",
                "ml_features_daily", "risk_metrics", "valuation_daily",
                "fundamentals_quarterly", "shareholding_quarterly",
                "corporate_actions", "macro_indicators", "derivatives_daily",
                "intraday_metrics", "weekly_metrics", "schema_migrations",
            ]
            logger.info("PostgreSQL tables:")
            for name in expected:
                if name in table_names:
                    rows = await conn.fetchval(f"SELECT COUNT(*) FROM {name}")
                    size = await conn.fetchval(f"SELECT pg_size_pretty(pg_total_relation_size('{name}'))")
                    logger.info(f"  [OK] {name}: {rows} rows, {size}")
                else:
                    logger.warning(f"  [MISSING] {name}")
            await conn.close()
            return True

        # Execute the full schema (idempotent via IF NOT EXISTS)
        await conn.execute(POSTGRESQL_SCHEMA)

        # Verify tables
        tables = await conn.fetch(
            """SELECT table_name,
                      (SELECT COUNT(*) FROM information_schema.columns c
                       WHERE c.table_name = t.table_name AND c.table_schema = 'public') as col_count
               FROM information_schema.tables t
               WHERE table_schema = 'public'
               ORDER BY table_name"""
        )
        logger.info("PostgreSQL tables created/verified:")
        for t in tables:
            rows = await conn.fetchval(f"SELECT COUNT(*) FROM {t['table_name']}")
            size = await conn.fetchval(f"SELECT pg_size_pretty(pg_total_relation_size('{t['table_name']}'))")
            logger.info(f"  [OK] {t['table_name']}: {t['col_count']} columns, {rows} rows, {size}")

        indexes = await conn.fetch(
            """SELECT indexname, tablename FROM pg_indexes
               WHERE schemaname = 'public' ORDER BY tablename, indexname"""
        )
        logger.info(f"Indexes: {len(indexes)} total")
        for idx in indexes:
            logger.info(f"  {idx['tablename']}.{idx['indexname']}")

        # Check for TimescaleDB and apply optimizations if available
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
            logger.info("TimescaleDB extension detected and enabled")

            hypertable_check = await conn.fetchval(
                "SELECT count(*) FROM _timescaledb_catalog.hypertable WHERE table_name = 'prices_daily';"
            )
            if hypertable_check == 0:
                logger.info("  -> Converting prices_daily to hypertable")
                await conn.execute(
                    "SELECT create_hypertable('prices_daily', by_range('date', INTERVAL '1 month'), if_not_exists => TRUE);"
                )
                logger.info("  -> Converting technical_indicators to hypertable")
                await conn.execute(
                    "SELECT create_hypertable('technical_indicators', by_range('date', INTERVAL '1 month'), if_not_exists => TRUE);"
                )

                logger.info("  -> Setting up compression policies")
                await conn.execute("""
                    ALTER TABLE prices_daily SET (
                        timescaledb.compress,
                        timescaledb.compress_segmentby = 'symbol',
                        timescaledb.compress_orderby = 'date DESC'
                    );
                """)
                await conn.execute("""
                    ALTER TABLE technical_indicators SET (
                        timescaledb.compress,
                        timescaledb.compress_segmentby = 'symbol',
                        timescaledb.compress_orderby = 'date DESC'
                    );
                """)
                try:
                    await conn.execute("SELECT add_compression_policy('prices_daily', INTERVAL '6 months');")
                    await conn.execute("SELECT add_compression_policy('technical_indicators', INTERVAL '6 months');")
                except Exception as e:
                    if "already exists" not in str(e):
                        raise

        except Exception as e:
            if "timescaledb" in str(e).lower() or "extension" in str(e).lower():
                logger.info("TimescaleDB not available. Proceeding with standard PostgreSQL.")
            else:
                logger.warning(f"TimescaleDB setup note: {e}")

        await conn.close()
        logger.info("PostgreSQL setup complete")
        return True

    except Exception as e:
        logger.error(f"PostgreSQL setup failed: {e}")
        return False


# ================================================================
#  MongoDB Setup
# ================================================================

async def setup_mongodb(check_only: bool = False) -> bool:
    """Create MongoDB collections, indexes, and schema validation."""
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB_NAME", os.environ.get("DB_NAME", "stockpulse"))

    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError:
        logger.error("motor not installed. Run: pip install motor")
        return False

    try:
        client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
        await client.admin.command("ping")
        logger.info(f"Connected to MongoDB: {mongo_url}/{db_name}")

        db = client[db_name]

        if check_only:
            existing = await db.list_collection_names()
            logger.info("MongoDB collections:")
            for name in MONGO_COLLECTIONS:
                if name in existing:
                    count = await db[name].count_documents({})
                    indexes = await db[name].index_information()
                    logger.info(f"  [OK] {name}: {count} documents, {len(indexes)} indexes")
                else:
                    logger.warning(f"  [MISSING] {name}")
            client.close()
            return True

        existing = await db.list_collection_names()

        for coll_name, coll_config in MONGO_COLLECTIONS.items():
            # Create collection if it doesn't exist
            if coll_name not in existing:
                # Apply schema validation if defined
                if coll_name in MONGO_SCHEMA_VALIDATORS:
                    await db.create_collection(
                        coll_name,
                        validator=MONGO_SCHEMA_VALIDATORS[coll_name],
                        validationLevel="moderate",
                        validationAction="warn",
                    )
                    logger.info(f"  Created collection with schema validation: {coll_name}")
                else:
                    await db.create_collection(coll_name)
                    logger.info(f"  Created collection: {coll_name}")
            else:
                # Apply/update schema validation on existing collections
                if coll_name in MONGO_SCHEMA_VALIDATORS:
                    try:
                        await db.command(
                            "collMod",
                            coll_name,
                            validator=MONGO_SCHEMA_VALIDATORS[coll_name],
                            validationLevel="moderate",
                            validationAction="warn",
                        )
                        logger.info(f"  Updated schema validation: {coll_name}")
                    except Exception as e:
                        logger.warning(f"  Schema validation update for {coll_name}: {e}")
                else:
                    logger.info(f"  Collection exists: {coll_name}")

            # Create indexes
            collection = db[coll_name]
            indexes = coll_config.get("indexes", [])
            for idx_conf in indexes:
                try:
                    kwargs = {}
                    if idx_conf.get("unique"):
                        kwargs["unique"] = True
                    if idx_conf.get("sparse"):
                        kwargs["sparse"] = True
                    if idx_conf.get("expireAfterSeconds") is not None:
                        kwargs["expireAfterSeconds"] = idx_conf["expireAfterSeconds"]
                    await collection.create_index(idx_conf["keys"], **kwargs)
                except Exception as e:
                    logger.warning(f"  Index note for {coll_name}: {e}")

            logger.info(f"    {len(indexes)} index(es) ensured")

        # Final verification
        collections = await db.list_collection_names()
        logger.info(f"MongoDB setup complete. Collections: {sorted(collections)}")
        client.close()
        return True

    except Exception as e:
        logger.error(f"MongoDB setup failed: {e}")
        return False


# ================================================================
#  Redis Check
# ================================================================

def check_redis() -> bool:
    """Verify Redis connectivity and report basic info."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

    try:
        import redis
    except ImportError:
        logger.error("redis not installed. Run: pip install redis")
        return False

    try:
        r = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=3)
        r.ping()

        info = r.info("memory")
        logger.info(f"Redis connected: {redis_url}")
        logger.info(f"  Version : {info.get('redis_version', 'N/A')}")
        logger.info(f"  Memory  : {info.get('used_memory_human', 'N/A')}")
        logger.info(f"  Keys    : {r.dbsize()}")

        r.close()
        return True

    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        logger.info("  (Redis is optional - the app falls back to in-memory cache.)")
        return False


# ================================================================
#  Filesystem Setup
# ================================================================

def setup_filesystem() -> bool:
    """Create required local directories for binary artifacts."""
    dirs = [
        ROOT_DIR / os.environ.get("REPORTS_DIR", "./reports"),
        ROOT_DIR / os.environ.get("BHAVCOPY_DIR", "./data/bhavcopy"),
        ROOT_DIR / os.environ.get("MODELS_DIR", "./models"),
        ROOT_DIR / os.environ.get("BACKUPS_DIR", "./backups"),
        ROOT_DIR / "cache" / "html",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        # Add .gitkeep so Git tracks empty directories
        gitkeep = d / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
        logger.info(f"  Directory ready: {d.relative_to(ROOT_DIR)}/")

    logger.info("Filesystem directories created")
    return True


# ================================================================
#  Main
# ================================================================

async def main() -> int:
    parser = argparse.ArgumentParser(description="StockPulse Database Setup")
    parser.add_argument("--postgres", action="store_true", help="Setup PostgreSQL only")
    parser.add_argument("--mongo", action="store_true", help="Setup MongoDB only")
    parser.add_argument("--redis", action="store_true", help="Check Redis only")
    parser.add_argument("--check", action="store_true", help="Verify all connections (read-only)")
    args = parser.parse_args()

    # If no specific flag is passed, do everything
    do_all = not (args.postgres or args.mongo or args.redis)

    logger.info("=" * 60)
    logger.info("StockPulse Database Setup")
    logger.info("=" * 60)

    results = {}

    # --- PostgreSQL ---
    if do_all or args.postgres:
        logger.info("\n--- PostgreSQL Time-Series Store ---")
        results["postgresql"] = await setup_postgresql(check_only=args.check)

    # --- MongoDB ---
    if do_all or args.mongo:
        logger.info("\n--- MongoDB Entity Store ---")
        results["mongodb"] = await setup_mongodb(check_only=args.check)

    # --- Redis ---
    if do_all or args.redis:
        logger.info("\n--- Redis Cache Layer ---")
        results["redis"] = check_redis()

    # --- Filesystem ---
    if do_all:
        logger.info("\n--- Filesystem Directories ---")
        results["filesystem"] = setup_filesystem()

    # --- Summary ---
    logger.info("\n" + "=" * 60)
    logger.info("Setup Summary")
    logger.info("=" * 60)

    all_ok = True
    for name, ok in results.items():
        status = "OK" if ok else "FAIL"
        logger.info(f"  [{status}] {name}")
        # Redis is optional; only count required databases as failures
        if not ok and name != "redis":
            all_ok = False

    if all_ok:
        logger.info("\nAll databases ready! Start the server with:")
        logger.info("  cd backend && uvicorn server:app --reload")
    else:
        logger.warning("\nSome databases failed. Check the errors above.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
