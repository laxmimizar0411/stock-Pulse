# Database Dashboard

Complete database visibility, monitoring, and management for StockPulse.

## Overview

The Database Dashboard provides a unified interface to inspect, monitor, and manage all three database layers (MongoDB, PostgreSQL, Redis) used by StockPulse. It is designed for single-user operation and includes safety features like Safe Mode, audit logging, and input validation.

## Architecture

```
Frontend (React)               Backend (FastAPI)              Databases
DatabaseDashboard.jsx  --->  /api/database/* routes  --->  MongoDB (Motor)
                             db_dashboard.py                PostgreSQL (asyncpg)
                             db_dashboard_service.py        Redis (redis-py)
```

**Key files:**
- `frontend/src/pages/DatabaseDashboard.jsx` — UI (all tabs and components)
- `backend/routes/db_dashboard.py` — API router (17 endpoints)
- `backend/services/db_dashboard_service.py` — Service layer (no direct DB access from frontend)
- `frontend/src/lib/api.js` — API client functions

## Tabs

### 1. Overview
- Health cards for all three databases (status, counts, sizes)
- Storage usage bar chart (MongoDB collections + PostgreSQL tables)
- Data flow pipeline visualization (5-stage diagram)
- Connection & system info panel

### 2. Data Management (CRUD)
Full create/read/update/delete for user data:
- **Watchlist** — Add/edit/remove stocks with target price, stop loss, notes
- **Portfolio** — Manage holdings with quantity, buy price, sector
- **Alerts** — Create/edit/delete price alerts with type, condition, threshold

Features:
- Inline editing (click edit icon → modify cells → save)
- Search/filter within each section
- Safe Mode confirmation for deletes
- Uses existing API endpoints (no new backend routes needed)

### 3. MongoDB
- Browse all collections with document counts and metadata
- View paginated sample documents (JSON view)
- Schema inference from samples + JSON Schema validator display
- Index information
- Delete documents (with Safe Mode confirmation)
- ID field auto-detection for delete operations

### 4. PostgreSQL
- Browse all tables with row counts and sizes
- Paginated tabular data view (ordered by date/primary key)
- Schema view: columns, types, nullable, defaults, indexes, foreign keys
- Read-only (no delete/edit for time-series data)

### 5. Redis
- Key browser grouped by prefix
- Cache stats (hit rate, memory, key count)
- Value preview for safe prefixes only (sensitive keys hidden)
- Cache flush option
- Prefix-based search/filter

### 6. Activity
Three sub-tabs:

**Activity Feed:**
- Pipeline jobs, extraction logs, audit entries
- Filter by collection (pipeline_jobs, extraction_log, audit_log)
- Filter by status (success, failed, running)
- Text search

**Errors:**
- Failed pipeline jobs and extractions
- Error trend chart (last 7 days, bar chart)
- Detail expansion with error messages

**Audit Log:**
- All dashboard operations logged with timestamp, action, store, record ID
- Filter by action (create/update/delete)
- Filter by store (mongodb/postgresql/redis)
- Filter by collection/table name
- Paginated

### 7. Settings
- **Safe Mode** — Require confirmation for destructive actions (default: ON)
- **Auto-Refresh Interval** — 15–300 seconds (default: 30)
- **Default Page Size** — 10–100 (default: 25)
- **Alert Thresholds** (all actively evaluated):
  - MongoDB data size (GB)
  - PostgreSQL data size (GB) — via `pg_database_size()`
  - Redis memory (MB)
  - Connection pool usage (%)
  - Error rate per hour — counts failed jobs/extractions in the last hour

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/database/overview` | Aggregated overview of all databases |
| GET | `/api/database/data-flow` | Data flow pipeline description |
| GET | `/api/database/threshold-alerts` | Check state against thresholds |
| GET | `/api/database/collections` | List MongoDB collections |
| GET | `/api/database/collections/{name}/sample` | Paginated documents |
| GET | `/api/database/collections/{name}/schema` | Inferred schema + validator |
| DELETE | `/api/database/collections/{name}/documents` | Delete single document |
| GET | `/api/database/tables` | List PostgreSQL tables |
| GET | `/api/database/tables/{name}/sample` | Paginated rows |
| GET | `/api/database/tables/{name}/schema` | Column/index/FK info |
| GET | `/api/database/redis/keys` | List Redis keys by prefix |
| GET | `/api/database/activity` | Recent activity feed (supports `since`, `until`, `collection` params) |
| GET | `/api/database/errors` | Recent errors (supports `since`, `until` params) |
| GET | `/api/database/errors/trend` | Error counts by day |
| GET | `/api/database/settings` | Dashboard settings |
| PATCH | `/api/database/settings` | Update settings |
| POST | `/api/database/audit-log` | Write audit log entry |
| GET | `/api/database/audit-log` | Paginated audit log (supports `action`, `store`, `collection_or_table` filters) |

## Security

- **No direct DB access** from frontend — all queries go through the service layer
- **Collection name validation** — regex `^[a-z_]{1,50}$` for MongoDB
- **Table name whitelisting** — only known PG tables allowed
- **SQL injection prevention** — parameterized queries for PostgreSQL
- **NoSQL injection prevention** — field whitelists, input sanitization via `mongo_utils.py`
- **Redis safe prefix policy** — only whitelisted key prefixes show values
- **Audit logging** — all destructive operations logged
- **Safe Mode** — confirmation required for deletes (togglable)
- **Value truncation** — large values truncated to prevent memory issues

## Settings Storage

Settings are stored in MongoDB collection `db_settings` with key `dashboard`. Default values are used when the collection doesn't exist yet. Allowed fields are validated server-side.

## Deletable Collections

Only these MongoDB collections allow document deletion from the dashboard:
- `watchlist`, `portfolio`, `alerts`
- `news_articles`, `backtest_results`
- `extraction_log`, `pipeline_jobs`, `quality_reports`

Stock data and price history are protected from accidental deletion.
