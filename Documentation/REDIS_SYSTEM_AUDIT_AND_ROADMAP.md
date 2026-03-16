# Redis System Audit & Implementation Roadmap — Stock-Pulse

> **Purpose:** Make Redis fully operational and production-ready for the Stock-Pulse platform.  
> **Scope:** Backend architecture, cache service, WebSocket broadcaster, pipeline integration, dashboard, and deployment.  
> **Last updated:** March 2026.

### Implementation Status

| Phase | Status | Notes |
|-------|--------|--------|
| **Phase 1** | ✅ **Complete** | SCAN, retry, LRU fallback, connection pool, alert queue cap + consumer, flush guard, env docs, REDIS_SETUP.md, runbook, 28 tests |
| **Phase 2** | 🔶 **Partial** | Connection pool, dashboard helpers (get_redis_info, scan_keys, get_stock_hash), market_data_service Redis, API caching for dashboard endpoints — done; namespace prefix and full Phase 2 checklist optional |
| **Phase 3** | ⬜ Pending | Rate limiting, multi-instance WebSocket subscriber, optional job queue/session store |

See **§8.3** for Phase 1 completion checklist (all items done). Implemented files: `cache_service.py`, `db_dashboard_service.py`, `market_data_service.py`, `alert_consumer.py`, `server.py`, `test_redis_cache.py`, `REDIS_SETUP.md`, `.env.example`, `Data_Storage_and_Growth_Guide.md`.

---

## 1. Redis System Audit Report

### 1.1 Backend Architecture (Relevant to Redis)

- **FastAPI** app (`server.py`) initializes a **global CacheService** at startup using `REDIS_URL` and passes it to the database dashboard service.
- **Pipeline** (`pipeline_service.py`) uses `get_cache_service()` to write live prices, stock hashes, pub/sub updates, and top movers after fetching from Groww.
- **WebSocket** (`websocket_manager.py`) uses a **separate Redis connection** in `PriceBroadcaster` for pub/sub and `ws:price:*` cache (no shared connection pool).
- **Market data service** (`market_data_service.py`) uses **Redis** (via CacheService) for quotes, history, indices, and fundamentals (`mkt:*` keys with TTL); cache is shared across restarts/workers.
- **Database dashboard** (`db_dashboard_service.py`) uses the global cache via **CacheService methods only** (get_redis_info, scan_keys, get_key_info, get_key_value_preview, get_stock_hash); no direct `cache._redis` access.

### 1.2 Current Redis Configuration

| Item | Location | Current state |
|------|----------|----------------|
| **URL** | `REDIS_URL` env, default `redis://localhost:6379` | Used in `server.py` and `websocket_manager.py` |
| **Auth** | Optional (password in URL, e.g. `redis://:pass@host:6379`) | No explicit auth in code; URL only |
| **DB index** | `CacheService(db=0)` | Fixed DB 0 |
| **Timeouts** | `REDIS_CONNECT_TIMEOUT`, `REDIS_SOCKET_TIMEOUT` (default 5s each) | Configurable via env |
| **Connection pooling** | `ConnectionPool` with `REDIS_MAX_CONNECTIONS` (default 10) | Used by CacheService |
| **Eviction / maxmemory** | Documented in REDIS_SETUP.md and Data_Storage_and_Growth_Guide.md | Set in Redis server config |

### 1.3 Existing Redis Usage

| Component | Implemented | Partially implemented | Missing |
|-----------|-------------|------------------------|--------|
| **CacheService** (strings, TTL) | ✅ get/set/delete/delete_pattern, domain helpers (price, analysis, stock_list, market, pipeline, news) | — | — |
| **CacheService** (HASH) | ✅ set_stock_hash, get_stock_field(s) | — | get_stock_hash (full HASH) not exposed |
| **CacheService** (SORTED SET) | ✅ top_gainers, top_losers with TTL | — | — |
| **CacheService** (PUB/SUB) | ✅ publish_price | — | No subscribe in backend (see 1.4) |
| **CacheService** (LIST) | ✅ publish_alert → RPUSH + LTRIM (cap 1000); **alert_consumer.py** BLPOP consumer | — | — |
| **PriceBroadcaster** | ✅ Own Redis client; publish to channel:prices; setex ws:price:* | — | No subscription to channel:prices for multi-instance |
| **Pipeline → Redis** | ✅ set_price, set_stock_hash, publish_price, update_top_movers | — | — |
| **Server API** | ✅ Market overview, analysis, screener cache; get_cached_stocks; /cache/stats, /cache/flush | — | — |
| **Market data service** | ✅ Uses CacheService for quotes, history, indices, fundamentals (`mkt:*` keys) | — | — |
| **Session store** | — | — | ❌ Not implemented (stateless/JWT may be OK) |
| **Job queue (Celery/RQ)** | — | — | ❌ Not implemented |
| **Rate limiting** | — | — | ❌ Not implemented |

### 1.4 Data Flow (Redis)

- **Write:** Pipeline (Groww) → CacheService (price:*, stock:*, channel:prices, top_gainers, top_losers). PriceBroadcaster → ws:price:* + channel:prices. API → market:overview, analysis:*, screener:{hash}.
- **Read:** API (market overview, analysis, screener, stock list) → CacheService get. Dashboard → cache.get_stats(), cache._redis for keys/memory.
- **Alert queue:** RPUSH + LTRIM (cap 1000); **alert_consumer.py** runs BLPOP and processes alerts (started with server lifecycle).

### 1.5 Where Redis Is Implemented vs Missing

- **Implemented:** Central cache (strings, HASH, ZSET, publish), **SCAN** (no KEYS), **connection pool**, **connection retry + auto-reconnect**, **bounded LRU fallback** (10k keys), **alert_queue** cap (LTRIM) + **alert_consumer** (BLPOP), **market_data_service** Redis (`mkt:*`), dashboard via **CacheService methods** (get_redis_info, scan_keys, get_stock_hash, etc.), **/cache/flush** guarded in production (ALLOW_CACHE_FLUSH), configurable timeouts and max_connections, REDIS_SETUP.md + runbook, **28 tests** (test_redis_cache.py).
- **Partially implemented:** PUB/SUB (publish only; no subscriber in app for multi-instance WebSocket).
- **Missing (Phase 2/3):** Key namespace prefix (optional); rate limiting; job queue; session store (if needed); multi-instance WebSocket subscriber.

### 1.6 Website / Frontend–Backend Flow (Redis Impact)

- **Frontend** calls backend APIs (see `frontend/src/lib/api.js`). Responses that are **currently cached in Redis** and improve **website responsiveness**:
  - `GET /market/overview` → cache key `market:overview` (60s)
  - `GET /stocks/:symbol/analysis` → cache key `analysis:{symbol}` (300s)
  - `POST /screener` → cache key `screener:{filter_hash}` (120s)
  - Stock list used by multiple endpoints → `stock_list` (300s)
- **Not cached (potential for UX):** `GET /timeseries/stats`, `GET /database/health`, `GET /database/overview`, `GET /pipeline/status`, `GET /stocks` (list), `GET /sectors`, heavy GETs used by Dashboard and Database Dashboard. Adding short TTL cache for these would reduce latency and improve responsiveness.
- **Deployment:** Redis is configured via `REDIS_URL` only. No Docker Compose Redis service definition in repo; no explicit production deployment steps (install Redis, set maxmemory, run `setup_databases.py --redis`) in this roadmap — added below in §2.1 and §8.

---

## 2. Complete Redis Task List

### 2.1 Pending Tasks

| # | Task | Priority | Owner/phase |
|---|------|----------|-------------|
| 1 | Implement alert_queue consumer (BLPOP or background task) or remove RPUSH if alerts are not used | Medium | Phase 1 |
| 2 | Use SCAN instead of KEYS in delete_pattern and key listing to avoid blocking | High | Phase 1 |
| 3 | Add Redis connection retry on startup; optionally add periodic health check (e.g. ping every 60s) and reconnect if connection lost | Medium | Phase 1 (retry); Phase 2 (periodic check) |
| 4 | Document and enforce maxmemory + eviction policy (e.g. allkeys-lru) in Redis server / docs | High | Phase 1 |
| 5 | Introduce key namespace prefix (e.g. `stockpulse:`) and use it consistently | Low | Phase 2 |
| 6 | Unify Redis client usage: consider single connection pool or shared client for CacheService and PriceBroadcaster | Medium | Phase 2 |
| 7 | Add optional Redis-backed cache in market_data_service for quotes/history/indices (with TTL) to share across restarts/workers | Medium | Phase 2 |
| 8 | Add production Redis settings to .env.example (REDIS_URL with password, REDIS_SSL, optional REDIS_MAX_CONNECTIONS) | Low | Phase 1 |
| 9 | **Redis setup and integration (operational):** Document or add: (a) Install/start Redis (e.g. brew/docker); (b) Configure maxmemory and maxmemory-policy in redis.conf; (c) Set REDIS_URL in .env; (d) Run `python setup_databases.py --redis` to verify; (e) Verify `/api/cache/stats` and `/api/database/health` show Redis connected | High | Phase 1 |
| 10 | Add query result caching for expensive GETs used by UI: e.g. `/timeseries/stats`, `/database/health`, `/database/overview` with short TTL (30–60s) to improve dashboard responsiveness | Medium | Phase 2 |
| 11 | Cap or add TTL/expiration for `alert_queue` LIST (e.g. LTRIM to max length or TTL per item) to avoid unbounded growth if consumer is not implemented | Low | Phase 1 |
| 12 | Restrict or protect `/cache/flush` (FLUSHDB) in production — admin-only or remove from public API | Medium | Phase 1 |
| 13 | Make Redis socket/connect timeouts configurable via env (e.g. REDIS_SOCKET_TIMEOUT, REDIS_CONNECT_TIMEOUT) and increase default socket timeout to 5s to reduce false failures under load | Low | Phase 1 |
| 14 | Add Redis runbook section (e.g. in MongoDB_Runbooks.md or new Redis_Runbook.md): what to do when Redis is down, how to verify connectivity, how to safely flush or clear cache, when to restart app | Medium | Phase 1 |
| 15 | Add or extend automated tests for Redis: connectivity (setup_databases.py --redis), cache get/set and fallback when Redis unavailable, and after Phase 1 SCAN-based key listing (no KEYS) | Medium | Phase 1 |
| 16 | Document Redis deployment: add dedicated Redis setup section to Data_Storage_and_Growth_Guide.md or create REDIS_SETUP.md with install/start (brew, docker run, or Compose if added later), maxmemory config, and verification steps | Low | Phase 1 |
| 17 | Add CacheService methods get_redis_info() and scan_keys(prefix, cursor, count) and refactor db_dashboard_service to use them instead of direct cache._redis access | Low | Phase 2 |
| 18 | Optional: Expose get_stock_hash(symbol) in CacheService for full HASH read when needed (currently only get_stock_field(s)) | Low | Phase 2 |

### 2.2 Incomplete Implementations

| Feature | Current state | To complete |
|---------|----------------|-------------|
| **Caching layer** | CacheService + in-memory fallback; market_data_service not using Redis | Use CacheService (or a thin wrapper) in market_data_service for quote/history/indices with TTL; keep fallback |
| **Queue systems** | Only alert_queue (LIST) — write-only, no consumer | Add BLPOP consumer or remove; no job queue (Celery/RQ) yet |
| **Session management** | Not implemented (stateless/JWT) | If server-side sessions needed later, implement Redis session store with TTL |
| **Pub/Sub** | Publish only (channel:prices); PriceBroadcaster broadcasts in-process | For multi-instance: add a subscriber task that listens on channel:prices and pushes to local WebSocket manager |
| **Background workers** | No Redis-backed workers; pipeline/jobs triggered via API | Optional: Celery or RQ with Redis broker for async jobs and task scheduling |
| **Rate limiting** | Not implemented | Redis INCR + EXPIRE (or similar) per IP/client for selected API routes |
| **Alert queue (LIST)** | publish_alert does RPUSH to alert_queue | Either: (a) add a small worker that BLPOPs and processes (e.g. trigger notifications), or (b) remove publish_alert / alert_queue if unused |
| **Key listing** | get_redis_keys uses KEYS pattern | Switch to SCAN and optional cursor-based pagination for dashboard |
| **Eviction** | Not configured in app | Document in setup/runbooks: set maxmemory and maxmemory-policy (e.g. allkeys-lru) on Redis server |
| **Task scheduling** | Jobs (derive_metrics, macro, derivatives, intraday) run via API or CLI | Optional: use Redis as Celery Beat backend or similar for cron-like scheduling |

### 2.3 Architecture Gaps (Redis Should Be Used But Isn’t)

| Gap | Recommendation |
|-----|----------------|
| **Market data cache not shared** | Cache get_stock_quote, get_historical_data, get_market_indices, get_stock_fundamentals in Redis (with TTL) so multiple workers or restarts share the same cache. |
| **No rate limiting** | Use Redis INCR + EXPIRE (or Redis 7+ rate limit helpers) for API rate limiting per IP or per user. |
| **No job queue** | If async jobs (e.g. bhavcopy, macro job) should be queued: use Redis as broker (e.g. Celery or RQ) and document in roadmap; otherwise keep current “trigger via API” approach. |
| **No cache invalidation on DB write** | When pipeline or bhavcopy updates a symbol, optionally invalidate only that symbol’s cache (e.g. price:SYMBOL, analysis:SYMBOL); currently pipeline overwrites price/stock which is acceptable. |
| **No session store** | If moving to multi-user with server-side sessions, store session in Redis with TTL; if staying stateless/JWT, no change. |
| **Frequently accessed API responses not cached** | Cache GETs used by frontend for dashboard UX: e.g. `/timeseries/stats`, `/database/health`, `/database/overview`, `/pipeline/status` with 30–60s TTL. |
| **Query result caching** | Heavy query results (screener already cached; optionally timeseries stats, database overview) benefit from short TTL to reduce backend load and improve response time. |
| **No task scheduling backend** | Redis can back Celery Beat or similar for cron-like runs; currently jobs are manual/API-triggered. |
| **Deployment configuration** | Document Redis in deployment: Docker image (or docker run), REDIS_URL for production, optional TLS, health check in orchestrator. |
| **Testing** | Only connectivity in test_pipeline.py; no tests for cache get/set, fallback, or SCAN. Add or extend tests (see §2.1 task 15). |
| **Runbook** | No dedicated Redis runbook; only brief mention in MongoDB_Runbooks. Add Redis section: when down, verify, safe flush, restart (see §2.1 task 14). |

---

## 3. Errors, Bugs & Issues (With Fixes)

| # | Issue | Severity | Fix |
|---|--------|----------|-----|
| 1 | **KEYS pattern in production** — `delete_pattern` and dashboard key listing use `redis.keys(pattern)`, which blocks Redis for large key sets | High | Use `SCAN` with a cursor (e.g. `SCAN 0 MATCH pattern COUNT 100`) and iterate; expose paginated or cursor-based listing in dashboard. |
| 2 | **Two separate Redis connections** — CacheService and PriceBroadcaster each create their own connection; no pooling | Medium | Use a single connection pool (e.g. `redis.ConnectionPool`) shared by CacheService and, if possible, by PriceBroadcaster (or document that two connections are acceptable for single-instance). |
| 3 | **alert_queue never consumed** — publish_alert pushes to LIST but nothing BLPOPs | Medium | Either implement a small loop/task that BLPOPs `alert_queue` and processes (e.g. send notification), or stop writing to it and remove/repurpose. |
| 4 | **In-memory fallback unbounded** — `_fallback_cache` dict has no max size; long-running process could grow memory | Medium | Add a max size (e.g. 10_000 keys) and evict oldest or LRU when full (e.g. use OrderedDict or cachetools.TTLCache with maxsize). |
| 5 | **Socket timeouts very short** — socket_timeout=1 can cause false failures under load | Low | Increase to 5–10s or make configurable via env; keep connect_timeout ~2–5s. |
| 6 | **No reconnect on failure** — If Redis goes down after startup, cache stays in fallback until restart | Medium | On get/set failure, try reconnecting once and retry; or run a periodic health check and reconnect if needed. |
| 7 | **Dashboard couples to cache._redis** — db_dashboard_service uses `cache._redis` directly | Low | Prefer CacheService methods (e.g. `get_redis_info()`, `scan_keys(prefix, cursor, count)`) so dashboard doesn’t depend on private attribute. |
| 8 | **market_data_service cache is process-local** — Quotes/history/indices not in Redis | Medium | Have market_data_service use CacheService (or a shared Redis cache) with same TTLs so all workers see the same data. |
| 9 | **Redis configuration: no connection pool** — Single connection per client; under async/concurrent requests can cause contention or blocking | Medium | Use redis.ConnectionPool(max_connections=10) and pass to Redis client so multiple operations share connections. |
| 10 | **Missing expiration on alert_queue** — LIST has no TTL or max length; can grow unbounded if no consumer | Low | Add LTRIM to cap length (e.g. keep last 1000) when RPUSH, or document and add TTL if Redis supports (or process/expire in consumer). |
| 11 | **Inefficient caching pattern: duplicate in-memory cache** — market_data_service maintains its own _price_cache instead of using Redis, so cache is not shared and is lost on restart | Medium | Use CacheService for quote/history/indices so one source of truth and shared across workers. |
| 12 | **Latency bottleneck: KEYS blocks** — Using KEYS for key listing blocks Redis for large key sets; can cause latency spikes | High | Use SCAN (see issue #1). |
| 13 | **Concurrency** — CacheService uses synchronous redis-py; in async FastAPI, blocking calls can stall event loop (typically short duration) | Low | For high throughput, consider redis.asyncio or run cache ops in run_in_executor; document for scale. |
| 14 | **Scalability risk: no failover** — If Redis goes down, app uses in-memory fallback; no automatic reconnect to replica or failover | Low | Document: single Redis instance; for HA, deploy Redis Sentinel or managed Redis with replica and update REDIS_URL/docs. |

---

## 4. Redis Data Architecture

### 4.1 Key Naming Conventions (Current)

| Prefix / key | Type | Used by | TTL (s) |
|--------------|------|---------|---------|
| `price:{SYMBOL}` | String (JSON) | CacheService, pipeline | 60 |
| `analysis:{SYMBOL}` | String (JSON) | Server (analysis API) | 300 |
| `stock:{SYMBOL}` | HASH | Pipeline (set_stock_hash) | 60 |
| `stock_list` | String (JSON) | get_cached_stocks | 300 |
| `market:overview` | String (JSON) | Market overview API | 60 |
| `pipeline:*` | String | Pipeline status | 30 |
| `news:*` | String | News cache | 180 |
| `screener:{filter_hash}` | String (JSON) | Screener API | 120 |
| `top_gainers` | SORTED SET | Pipeline | 60 |
| `top_losers` | SORTED SET | Pipeline | 60 |
| `channel:prices` | Pub/Sub channel | CacheService, PriceBroadcaster | N/A |
| `ws:price:{SYMBOL}` | String (JSON) | PriceBroadcaster | 10 |
| `alert_queue` | LIST | publish_alert (no consumer) | None |

Recommendation: introduce a namespace prefix (e.g. `stockpulse:`) for all keys so multiple apps or environments can share the same Redis without collision (e.g. `stockpulse:price:RELIANCE`). Optional in Phase 2.

### 4.2 Data Structures Summary

| Structure | Use case | Keys / channels |
|-----------|----------|------------------|
| String | JSON blob cache (price, analysis, market, screener, stock_list, ws:price) | All prefixed keys above except HASH/ZSET/LIST |
| HASH | Per-field stock data (partial read) | stock:{SYMBOL} |
| SORTED SET | Top gainers/losers by change % | top_gainers, top_losers |
| LIST | Alert queue (unconsumed) | alert_queue |
| Pub/Sub | Real-time price broadcast | channel:prices |
| **Set** | Not currently used | Potential: unique symbol sets, rate-limit buckets |
| **Stream** | Not currently used | Optional: event streaming/audit; Pub/Sub sufficient for now |

### 4.3 Namespace Structure (Proposed for Phase 2)

Use a single key prefix to avoid collision and support multiple environments. Example: `stockpulse:cache:price:RELIANCE`, `stockpulse:cache:market:overview`, `stockpulse:queue:alerts`. Configurable via `REDIS_KEY_PREFIX` (e.g. `stockpulse:` or empty for backward compatibility).

### 4.4 TTL Strategy

- **Short (10–60s):** Live prices, ws:price, market overview, stock HASH — avoid stale data.
- **Medium (120–300s):** Analysis, stock list, screener, news — balance freshness vs load.
- **Pipeline (30s):** Status — frequently updated.
- **No TTL:** alert_queue (if consumed, consider TTL or LTRIM to cap length; see §3 issue #10).

### 4.5 Cache Invalidation Rules

- **Per-symbol:** invalidate_stock(symbol) removes price:*, analysis:*, stock:* for that symbol. Pipeline overwrites price and stock on update (no explicit invalidation needed).
- **Full flush:** invalidate_all() → FLUSHDB (use with care; document as admin-only; restrict in production — see §2.1 task 12).
- **Screener:** Key is filter hash; natural expiry 120s.
- **Market overview:** 60s TTL; no explicit invalidation.

---

## 5. Redis Optimization Recommendations

### 5.1 API Response Caching (Current vs Recommended)

| Endpoint / data | Cached in Redis? | TTL | Improves (UX / backend) |
|-----------------|-------------------|-----|-------------------------|
| GET /market/overview | Yes | 60s | Dashboard load, responsiveness |
| GET /stocks/:symbol/analysis | Yes | 300s | Analyzer tab, backend compute |
| POST /screener | Yes (by filter hash) | 120s | Screener results, DB load |
| Stock list (internal) | Yes (stock_list) | 300s | Multiple endpoints |
| GET /timeseries/stats | No | — | Add 30–60s for dashboard |
| GET /database/health | No | — | Add 30–60s for dashboard |
| GET /database/overview | No | — | Add 30–60s for dashboard |
| GET /pipeline/status | No | — | Add 30s for pipeline page |

### 5.2 Website Responsiveness and User Experience

- Redis directly improves **responsiveness** by caching market overview, analysis, and screener so the UI gets fast responses without recomputing or re-querying on every request.
- **Backend processing** is reduced for cached analysis and screener (heavy scoring and PostgreSQL JOINs).
- **Recommendation:** Extend caching to GET endpoints that the frontend uses for Dashboard and Database Dashboard (timeseries stats, database health/overview, pipeline status) with short TTL (30–60s) to improve perceived performance and reduce backend load.

### 5.3 Other Optimizations

| Area | Recommendation |
|------|----------------|
| **Stock data caching** | Extend to market_data_service (quotes, history, indices) in Redis so all processes share cache. |
| **Pipelining** | For bulk writes (e.g. pipeline writing 50 symbols), use redis.pipeline() and setex/set in one round-trip (PriceBroadcaster already does this for ws:price:*). Add similar batching in CacheService if we do bulk set_price. |
| **Batching** | get_stock_fields already uses HMGET; ensure any new “get many” APIs use MGET or pipeline where appropriate. |
| **SCAN instead of KEYS** | Required for key listing and delete_pattern to avoid blocking (see §3). |
| **Connection pool** | Use redis.ConnectionPool(max_connections=10) and pass to Redis(connection_pool=pool) so multiple threads/tasks share connections. |
| **Lua scripts** | Optional: use a small script for “get-or-set” (e.g. get market overview, set if missing with TTL) to reduce round-trips. Not critical for current scale. |
| **Streams** | Not required for current design; Pub/Sub is enough for price broadcast. Streams can be considered later for audit or event replay. |
| **Distributed locks** | Only needed if multiple workers run the same job (e.g. pipeline). Use Redis SET NX EX for simple locking; or stick to “single runner” and document. |

---

## 6. Performance & Scalability

- **Single-instance:** Current design is sufficient (one FastAPI process, one Redis). Fix KEYS, add eviction docs, optional pool.
- **Multi-instance:** (a) Share cache via Redis (already the case). (b) WebSocket: add a subscriber to `channel:prices` in each instance that forwards to its local ConnectionManager so all instances get the same feed. (c) Use a single PriceBroadcaster instance or a dedicated “price” service that publishes to Redis; others only subscribe.
- **High-traffic:** Add connection pooling; use pipeline for bulk writes; keep TTLs short for hot keys; set maxmemory and allkeys-lru on Redis.
- **Financial data workload:** Burst traffic around market open/close is common; ensure Redis has enough memory (maxmemory) and connection pool size; avoid KEYS (use SCAN) so listing does not block during peak.

---

## 7. Security & Production Readiness Checklist

| Item | Status | Action |
|------|--------|--------|
| **Authentication** | Optional | Use REDIS_URL with password for production (`redis://:password@host:6379`). Document in .env.example. |
| **TLS** | Optional | For managed Redis (e.g. Redis Cloud), use rediss:// and set SSL verify. Add REDIS_SSL=true and use in from_url if needed. |
| **Environment variables** | Done | REDIS_URL from env. Add REDIS_SSL, optional REDIS_MAX_CONNECTIONS. |
| **Memory management** | Server-side | Document: set maxmemory (e.g. 256–512MB) and maxmemory-policy allkeys-lru in redis.conf or via CONFIG SET. |
| **Eviction policy** | Server-side | allkeys-lru recommended for cache-only usage. |
| **Monitoring** | Partial | /api/cache/stats and dashboard show hits, misses, keys, memory. Add optional periodic log or metric export (e.g. hit rate). |
| **Logging** | Partial | Cache errors at debug; connection success/failure at info. Add reconnect and health-check logs. |
| **Backup** | Optional | Redis is cache; persistence optional (RDB/AOF). Document backup if storing critical state; for cache-only, document “no backup required” or snapshot for disaster recovery. |
| **No FLUSHDB in API** | Risk | /cache/flush calls invalidate_all() → FLUSHDB. Restrict to admin or remove in production (see §2.1 task 12). |
| **Failover handling** | Partial | When Redis is down, in-memory fallback; no replica. For HA document Redis Sentinel or managed Redis. |

---

## 8. Redis Feature Implementation Roadmap

### Phase 1 — Must-have (production-ready)

1. **Replace KEYS with SCAN** in `cache_service.delete_pattern` and in dashboard `get_redis_keys` (with cursor/pagination).
2. **Document maxmemory and eviction** in `Documentation/Data_Storage_and_Growth_Guide.md` (or runbooks) and in setup instructions.
3. **Add connection retry** in CacheService.initialize (retry 2–3 times with backoff) and optionally on first failure in get/set.
4. **Cap in-memory fallback** size (e.g. 10_000 keys, TTLCache or OrderedDict eviction).
5. **Alert queue:** Either implement BLPOP consumer (e.g. background task that pushes to notification path) or remove/deprecate publish_alert and alert_queue.
6. **.env.example:** Add comment for REDIS_URL with password; optional REDIS_SSL, REDIS_MAX_CONNECTIONS.
7. **Redis setup and integration:** Document operational steps: (a) Install/start Redis (e.g. brew, docker); (b) Set maxmemory and maxmemory-policy in redis.conf; (c) Set REDIS_URL in .env; (d) Run `python setup_databases.py --redis`; (e) Verify `/api/cache/stats` and `/api/database/health` show Redis connected.
8. **Cap alert_queue** or add expiration strategy (LTRIM on RPUSH or consumer-side) to prevent unbounded growth.
9. **Protect /cache/flush:** Restrict to admin (e.g. auth middleware) or remove from public API in production.
10. **Configurable timeouts:** Make Redis socket_timeout and connect_timeout configurable via env; increase default socket timeout to 5s (see §2.1 task 13).
11. **Redis runbook:** Add runbook section for Redis: when Redis is down, how to verify, safe flush, restart app if needed (see §2.1 task 14).
12. **Testing:** Add or extend tests for Redis connectivity, cache get/set, in-memory fallback when Redis unavailable, and SCAN-based key listing once implemented (see §2.1 task 15).
13. **Redis setup documentation:** Add Redis setup section to Data_Storage_and_Growth_Guide.md or create REDIS_SETUP.md with install/start, maxmemory, verification (see §2.1 task 16).

### Phase 2 — Should-have (robustness and consistency)

1. **Single connection pool** for CacheService (and optionally PriceBroadcaster) with configurable max_connections.
2. **Namespace prefix** (e.g. `stockpulse:`) for all keys; configurable via REDIS_KEY_PREFIX.
3. **market_data_service** use CacheService for quote/history/indices/fundamentals (with existing TTLs) so cache is shared across restarts/workers.
4. **Dashboard:** Use CacheService methods for Redis info and key listing instead of `cache._redis` (add get_redis_info(), scan_keys).
5. **Query result / API response caching:** Add short TTL cache (30–60s) for GET /timeseries/stats, /database/health, /database/overview, /pipeline/status to improve dashboard responsiveness and reduce backend load.
6. **CacheService API for dashboard:** Add get_redis_info() and scan_keys(prefix, cursor, count); refactor db_dashboard_service to use these instead of cache._redis (see §2.1 task 17).
7. **Optional:** get_stock_hash(symbol) in CacheService for full HASH read (see §2.1 task 18).
8. **Optional:** Periodic Redis health check (e.g. background task ping every 60s) and reconnect if connection lost (see §2.1 task 3).

### Phase 3 — Nice-to-have (scale and features)

1. **Rate limiting:** Redis-backed rate limiter (e.g. INCR + EXPIRE per client/IP) for selected API routes.
2. **Multi-instance WebSocket:** Subscriber task that listens on `channel:prices` and forwards to local WebSocket manager.
3. **Optional job queue:** If moving pipeline/jobs to a queue, use Redis as Celery or RQ broker and document.
4. **Optional session store:** If adding server-side sessions, store in Redis with TTL.

### 8.1 Redis Feature Implementation Plan (by Use Case)

| Use case | Current | Phase 1 | Phase 2 | Phase 3 |
|----------|---------|---------|---------|---------|
| **Performance: API response caching** | market/overview, analysis, screener | — | Add timeseries/database/pipeline GET cache | — |
| **Performance: Stock data caching** | Pipeline writes price/stock to Redis | — | market_data_service uses Redis | — |
| **Performance: Query result caching** | Screener cached | — | timeseries stats, DB health/overview | — |
| **System: Job queues** | None | — | — | Optional Celery/RQ with Redis broker |
| **System: Background workers** | None | — | — | Optional |
| **System: Task scheduling** | API/CLI triggered | — | — | Optional Redis-backed (e.g. Celery Beat) |
| **System: Rate limiting** | None | — | — | Redis INCR + EXPIRE |
| **System: Session management** | None | — | — | Optional if server-side sessions needed |
| **Real-time: Pub/Sub** | Publish only | — | — | Subscriber for multi-instance WS |
| **Real-time: Live stock updates** | channel:prices + ws:price:* | — | — | — |
| **Real-time: WebSocket support** | PriceBroadcaster uses Redis | — | — | Multi-instance via subscriber |
| **Reliability: Retry** | None | Connection retry on init/failure | — | — |
| **Reliability: Periodic health check** | None | — | Optional ping + reconnect | — |
| **Reliability: Failover** | In-memory fallback | Document | — | Document HA options |
| **Reliability: Expiration policies** | TTL on all cache keys | alert_queue cap/LTRIM | — | — |
| **Reliability: Cache invalidation** | Per-symbol, full flush | Protect flush | — | — |

### 8.2 Phase 1 Recommended Implementation Order

1. **SCAN instead of KEYS** (cache_service + dashboard) — unblocks production safety.
2. **Connection retry** on init and optional on first get/set failure — improves resilience.
3. **Cap in-memory fallback** — prevents unbounded memory growth.
4. **Document maxmemory and eviction** — operational requirement.
5. **Redis setup documentation** — runbook and setup steps (tasks 9, 14, 16).
6. **Alert queue:** consumer or cap (LTRIM) or remove — prevents unbounded LIST.
7. **.env.example** production Redis options and **configurable timeouts**.
8. **Protect /cache/flush** — restrict or remove in production.
9. **Tests** for Redis and fallback; **runbook** section for Redis.

### 8.3 Phase 1 Completion Criteria (Definition of Done)

- [x] No KEYS used; key listing and delete_pattern use SCAN.
- [x] CacheService retries connection on startup (2–3 with backoff) and optionally on first failure.
- [x] In-memory fallback is capped (e.g. 10k keys) with eviction (_LRUFallbackCache).
- [x] maxmemory and maxmemory-policy documented and set on Redis server for production (REDIS_SETUP.md, Data_Storage_and_Growth_Guide.md).
- [x] alert_queue has a consumer (alert_consumer.py BLPOP) and is capped (LTRIM 1000).
- [x] /cache/flush is restricted in production unless ALLOW_CACHE_FLUSH=true.
- [x] REDIS_URL (and optional REDIS_SSL, REDIS_MAX_CONNECTIONS, REDIS_CONNECT_TIMEOUT, REDIS_SOCKET_TIMEOUT) documented in .env.example.
- [x] Redis setup and runbook steps documented (REDIS_SETUP.md); `setup_databases.py --redis` and /api/cache/stats used for verification.
- [x] Tests cover Redis connectivity and fallback when Redis is unavailable (test_redis_cache.py — 28 tests).

---

## 9. Deliverables Summary

| # | Deliverable | Location in this doc |
|---|-------------|----------------------|
| 1 | Redis system audit report | §1 |
| 2 | Complete Redis task list (pending, incomplete, gaps) | §2 |
| 3 | Bug & issue list with fixes | §3 |
| 4 | Missing architecture components | §2.3, §1.5 |
| 5 | Redis optimization recommendations | §5, §6 |
| 6 | Production-readiness checklist | §7 |
| 7 | Redis feature implementation roadmap | §8 |
| — | Key naming, structures, TTL, invalidation, namespace | §4 |
| — | API response caching table; website UX; feature plan by use case | §5.1, §5.2, §8.1 |
| — | Phase 1 recommended order; Phase 1 completion criteria (definition of done) | §8.2, §8.3 |

---

## 10. Final Objective Checklist

- **High performance:** SCAN instead of KEYS; connection pool; pipeline for bulk writes; TTLs in place.  
- **Efficient caching:** Domain helpers and TTLs documented; optional namespace; market_data_service uses Redis (mkt:* keys).  
- **Scalable real-time:** Pub/Sub in place; multi-instance subscriber in Phase 3.  
- **Reliable background:** Alert queue has BLPOP consumer (alert_consumer.py) and LTRIM cap; optional job queue in Phase 3.  
- **Optimized DB interactions:** Cache used for read-heavy APIs; invalidation rules documented.  
- **Production-grade:** Auth/TLS via URL and env; maxmemory/eviction documented; monitoring and logging; no unsafe FLUSHDB exposure without guard.

**Phase 1 is complete.** Redis is production-ready for the current Stock-Pulse single-instance deployment. Phase 2 (partial) added connection pool, dashboard helpers, market_data Redis, and API caching. Phase 3 (rate limiting, multi-instance WebSocket) remains optional. Use **§8.2** for implementation order and **§8.3** for Phase 1 completion checklist.

### Related Files

| File | Role |
|------|------|
| `backend/services/cache_service.py` | Central Redis cache: SCAN, pool, retry, LRU fallback, LTRIM alert_queue, get_redis_info, scan_keys, get_stock_hash |
| `backend/services/alert_consumer.py` | BLPOP consumer for alert_queue; started with server lifecycle |
| `backend/services/websocket_manager.py` | PriceBroadcaster — separate Redis client for channel:prices and ws:price:* |
| `backend/server.py` | init_cache_service, cache usage in APIs, flush guard (ALLOW_CACHE_FLUSH), alert consumer lifecycle, dashboard endpoint caching |
| `backend/services/pipeline_service.py` | Writes to Redis after Groww fetch (price, stock hash, publish, top movers) |
| `backend/services/db_dashboard_service.py` | Uses CacheService methods only (no cache._redis); Redis stats, scan_keys, key info |
| `backend/services/market_data_service.py` | Redis-backed cache for quotes, history, indices, fundamentals (mkt:* keys) |
| `backend/setup_databases.py` | `python setup_databases.py --redis` — connectivity check only |
| `backend/test_redis_cache.py` | 28 tests: LRU fallback, CacheService fallback, Redis integration, connection retry |
| `backend/.env.example` | REDIS_URL, REDIS_SSL, REDIS_MAX_CONNECTIONS, REDIS_CONNECT_TIMEOUT, REDIS_SOCKET_TIMEOUT, ALLOW_CACHE_FLUSH |
| `Documentation/REDIS_SETUP.md` | Install, config, verification, key naming, eviction, runbook, production checklist |
| `Documentation/Data_Storage_and_Growth_Guide.md` | Redis maxmemory, eviction, backup notes |
