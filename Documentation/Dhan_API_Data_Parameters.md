# Dhan API Data Parameters Reference

## Overview

StockPulse uses the **DhanHQ v2 REST API** as its primary data extraction source for Indian stock market data. This document lists all data fields received from Dhan API endpoints and how they map to the internal schema.

- **API Base URL**: `https://api.dhan.co`
- **Documentation**: https://dhanhq.co/docs/v2/
- **Python SDK**: https://github.com/dhan-oss/DhanHQ-py

## Authentication

| Header | Description |
|--------|-------------|
| `access-token` | JWT access token (valid ~24h, generated from web.dhan.co) |
| `client-id` | Dhan client ID (numeric string extracted from JWT payload) |
| `Content-Type` | `application/json` |
| `Accept` | `application/json` |

## Endpoints Used

### 1. Market Quote — Full Quote

**Endpoint**: `POST /v2/marketfeed/quote`

Retrieves full market data including OHLC, volume, OI, and market depth for up to 1000 instruments per request.

**Request Body**:
```json
{
  "NSE_EQ": ["2885", "11536", "1333"]
}
```
Keys are exchange segments, values are arrays of security IDs.

**Response Fields** (per instrument):

| Field | Type | Description | Internal Mapping |
|-------|------|-------------|------------------|
| `last_price` | float | Last traded price | `current_price`, `ltp` |
| `ohlc.open` | float | Day open price | `open` |
| `ohlc.high` | float | Day high price | `high` |
| `ohlc.low` | float | Day low price | `low` |
| `ohlc.close` | float | Previous close price | `close`, `prev_close` |
| `volume` | int | Total traded volume | `volume` |
| `average_price` | float | Average traded price | `average_price` |
| `last_quantity` | int | Last traded quantity | `last_quantity` |
| `buy_quantity` | int | Total buy quantity | `buy_quantity` |
| `sell_quantity` | int | Total sell quantity | `sell_quantity` |
| `oi` | int | Open interest (derivatives) | `open_interest` |
| `oi_day_high` | int | OI day high | `oi_day_high` |
| `oi_day_low` | int | OI day low | `oi_day_low` |
| `net_change` | float | Net price change | `net_change`, `price_change` |
| `upper_circuit_limit` | float | Upper circuit price | `upper_circuit_limit` |
| `lower_circuit_limit` | float | Lower circuit price | `lower_circuit_limit` |
| `last_trade_time` | string | Timestamp of last trade | `last_trade_time` |
| `depth.buy[]` | array | Best 5 buy levels | `depth.buy` |
| `depth.buy[].price` | float | Bid price at level | `bid_price` (level 0) |
| `depth.buy[].quantity` | int | Bid quantity at level | `bid_quantity` (level 0) |
| `depth.buy[].orders` | int | Number of orders at level | — |
| `depth.sell[]` | array | Best 5 sell levels | `depth.sell` |
| `depth.sell[].price` | float | Ask price at level | `ask_price` (level 0) |
| `depth.sell[].quantity` | int | Ask quantity at level | `ask_quantity` (level 0) |
| `depth.sell[].orders` | int | Number of orders at level | — |

### 2. Market Quote — LTP

**Endpoint**: `POST /v2/marketfeed/ltp`

Lightweight endpoint returning only the last traded price.

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `last_price` | float | Last traded price |

### 3. Market Quote — OHLC

**Endpoint**: `POST /v2/marketfeed/ohlc`

Returns OHLC data with LTP.

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `last_price` | float | Last traded price |
| `ohlc.open` | float | Day open |
| `ohlc.high` | float | Day high |
| `ohlc.low` | float | Day low |
| `ohlc.close` | float | Previous close |

### 4. Historical Daily Data

**Endpoint**: `POST /v2/charts/historical`

Returns daily OHLCV candle data for a specified date range.

**Request Body**:
```json
{
  "securityId": "2885",
  "exchangeSegment": "NSE_EQ",
  "instrument": "EQUITY",
  "expiryCode": 0,
  "oi": false,
  "fromDate": "2024-01-01",
  "toDate": "2024-12-31"
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp[]` | array[int] | Epoch timestamps |
| `open[]` | array[float] | Open prices |
| `high[]` | array[float] | High prices |
| `low[]` | array[float] | Low prices |
| `close[]` | array[float] | Close prices |
| `volume[]` | array[int] | Traded volumes |

### 5. Intraday Minute Data

**Endpoint**: `POST /v2/charts/intraday`

Returns minute-level OHLCV candle data for a specified date range.

**Request Body**:
```json
{
  "securityId": "2885",
  "exchangeSegment": "NSE_EQ",
  "instrument": "EQUITY",
  "fromDate": "2024-12-01",
  "toDate": "2024-12-01"
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp[]` | array[int] | Epoch timestamps (minute-level) |
| `open[]` | array[float] | Open prices |
| `high[]` | array[float] | High prices |
| `low[]` | array[float] | Low prices |
| `close[]` | array[float] | Close prices |
| `volume[]` | array[int] | Traded volumes |

### 6. Instrument List

**Endpoint**: `GET /v2/instrument/{exchangeSegment}`

Returns CSV with all security IDs and metadata for a given exchange segment. The extractor can refresh its symbol mapping at runtime via `refresh_instrument_map()`.

## Derived/Computed Fields

The following fields are computed internally from Dhan API data:

| Field | Computation |
|-------|-------------|
| `price_change` | `last_price - prev_close` |
| `price_change_percent` | `(price_change / prev_close) * 100` |
| `date` | Current UTC date |
| `timestamp` | Current UTC ISO timestamp |
| `source` | Always `"dhan"` |

## Exchange Segments

| Segment | Description |
|---------|-------------|
| `NSE_EQ` | NSE Equity |
| `BSE_EQ` | BSE Equity |
| `NSE_FNO` | NSE Futures & Options |
| `BSE_FNO` | BSE Futures & Options |

## Security ID Mapping

Dhan uses numeric security IDs instead of trading symbols. The extractor maintains a built-in mapping of 160+ NSE stocks covering:

- **NIFTY 50** (50 stocks)
- **NIFTY Next 50** (50 stocks)
- **Popular Mid/Small-caps** (60+ stocks)

Example mappings:

| Symbol | Security ID |
|--------|-------------|
| RELIANCE | 2885 |
| TCS | 11536 |
| HDFCBANK | 1333 |
| INFY | 1594 |
| ICICIBANK | 4963 |

The full mapping is in `backend/data_extraction/extractors/dhan_extractor.py`.

## Rate Limits

| Limit | Value |
|-------|-------|
| Requests per second | 20 (conservative) |
| Requests per minute | 250 |
| Instruments per quote request | 1000 max |
| Batch size (used) | 100 per request |

## Data Flow

```
Dhan API (/v2/marketfeed/quote)
    → DhanAPIExtractor.extract_bulk_quotes()
        → DataPipelineService.run_extraction()
            → Redis cache (live prices, top movers)
            → PostgreSQL (prices_daily, technicals, etc.)
            → MongoDB (pipeline_jobs, job history)
```

## PostgreSQL Tables Populated

| Table | Source Fields |
|-------|-------------|
| `prices_daily` | open, high, low, close, volume, prev_close |
| `technical_indicators` | Computed from price data |
| `derived_metrics_daily` | Computed from price history |
| `valuation_daily` | pe_ratio, pb_ratio, market_cap (when available) |
| `fundamentals_quarterly` | From supplementary data sources |
| `intraday_metrics` | average_price, volume, buy/sell quantity |
