# StockPulse: Where Data Is Stored & How to Manage Growth

This document answers: **where your data lives** (on your Mac), **how growth can affect the system**, and **what to do now** to avoid slowdowns or failures.

---

## 1. Where is data stored?

The app uses **three databases** plus **files in the project folder**. The databases do **not** store their data inside the Stock-Pulse-2 project; they use system data directories on your Mac.

### Databases (data on your Mac, outside the project)

| Store        | Where data actually lives (typical on macOS) | Controlled by |
|-------------|------------------------------------------------|----------------|
| **MongoDB** | Default: `/usr/local/var/mongodb` (Intel) or `/opt/homebrew/var/mongodb` (Apple Silicon). Check with: `mongosh --eval 'db.serverStatus().storageEngine'` or your `mongod.conf` → `storage.dbPath`. | MongoDB config / how you started `mongod` |
| **Redis**   | Working directory of `redis-server`; persistence file (if enabled) is in the `dir` from config. Find it: `redis-cli config get dir`. Often something like `/usr/local/var/db/redis` or current dir. | Redis config / how you started `redis-server` |
| **PostgreSQL** | Default: `/usr/local/var/postgres` (Intel) or `/opt/homebrew/var/postgres` (Apple Silicon). Check: `psql -c 'SHOW data_directory'` or look inside that path for `postgresql.conf`. | Postgres `PGDATA` / install |

Your app only has **connection strings** in `.env` (e.g. `MONGO_URL`, `REDIS_URL`, `TIMESERIES_DSN`). It does **not** set where Mongo/Redis/Postgres store files; that’s entirely on your Mac.

### Project folder (inside Stock-Pulse-2)

These paths are **inside the repo** (under `backend/` by default, from `setup_databases.py` and `.env`):

| Purpose           | Default path (relative to `backend/`) | Env variable    |
|-------------------|----------------------------------------|-----------------|
| Reports (PDFs)    | `./reports`                            | `REPORTS_DIR`   |
| NSE Bhavcopy CSVs | `./data/bhavcopy`                      | `BHAVCOPY_DIR`  |
| ML models         | `./models`                             | `MODELS_DIR`    |
| Backups (if you add scripts) | `./backups`                    | `BACKUPS_DIR`   |
| Cache (HTML debug)| `./cache/html`                         | —               |

So: **database data = on your Mac in each engine’s data directory**; **reports, bhavcopy, models, backups = inside the project (backend folder)**.

---

## 2. When data grows a lot, how does it affect the system?

| What grows        | Effect | Why |
|-------------------|--------|-----|
| **Disk space**    | **Full disk** → app or OS can crash, backups fail, DBs can’t write. | Mongo, Postgres, Redis, plus bhavcopy CSVs and reports all use disk. On a small Mac SSD this can matter. |
| **MongoDB size**  | **RAM pressure** (WiredTiger cache), **slower queries** if indexes missing, **longer backups**. | Mongo uses RAM for cache; very large collections without indexes cause full scans. |
| **Redis size**    | **RAM usage** (Redis keeps data in memory). If no `maxmemory` → can use a lot of RAM. | Redis is in-memory; without eviction it grows until you run out of RAM or swap. |
| **PostgreSQL size** | **Disk and a bit of RAM**; slow queries if no indexes or no VACUUM. | Table/index files grow; old dead rows can slow things until VACUUM. |
| **Bhavcopy + reports** | **Disk inside project**; many CSV/report files can fill the drive. | These are just files; no automatic cleanup. |

So yes: **if data grows too much, it can make the system slow or unstable** (low disk, heavy RAM use, slow or failing DB operations). For a single-user setup with a few hundred symbols and a few years of data, it’s manageable **if** you take the steps below.

---

## 3. What to do now to avoid negative impact

### 3.1 Know where things are and how big they are

- **Check Mongo data dir size**:  
  `du -sh /usr/local/var/mongodb` (or the path from your `mongod.conf`).
- **Check Redis**:  
  `redis-cli config get dir` then `du -sh <that_dir>`; also `redis-cli info memory`.
- **Check Postgres**:  
  `psql -c 'SHOW data_directory'` then `du -sh <that_path>`.
- **Check project usage**:  
  `du -sh backend/reports backend/data backend/models backend/backups backend/cache`.

Do this every few months so you see growth early.

### 3.2 Cap growth of “unbounded” data

- **MongoDB**
  - **Extraction / pipeline logs**: Add TTL or a cleanup job so old `extraction_log` and `pipeline_jobs` documents are removed or archived (e.g. keep last 90 days). Prevents these collections from growing forever.
  - **Indexes**: Ensure indexes exist for all main queries (symbol, date, status, etc.) so large collections don’t cause full collection scans.
- **Redis**
  - Set **maxmemory** (e.g. 256MB–512MB) and **maxmemory-policy allkeys-lru** so Redis evicts old keys instead of using unlimited RAM. For StockPulse it’s a cache; losing old keys is acceptable.
  - **How to set (pick one):**
    - **redis.conf:** Add `maxmemory 256mb` and `maxmemory-policy allkeys-lru` to your `redis.conf` and restart Redis.
    - **CLI (runtime):** `redis-cli CONFIG SET maxmemory 256mb` and `redis-cli CONFIG SET maxmemory-policy allkeys-lru` (lost on restart unless `CONFIG REWRITE` is used).
    - **Docker:** `docker run ... redis:7-alpine redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru`
  - **Verify:** `redis-cli CONFIG GET maxmemory` and `redis-cli CONFIG GET maxmemory-policy`.
  - See `Documentation/REDIS_SETUP.md` for complete Redis installation, configuration, verification, and runbook.
- **PostgreSQL**
  - Run **VACUUM** periodically (or rely on autovacuum). If you add TimescaleDB later, use compression for old time-series data.
- **Project folder**
  - **Bhavcopy**: Delete or archive CSVs older than X months, or keep only the last N days. Add a small script or cron if you want it automated.
  - **Reports**: Optionally delete or move old PDFs from `reports/` if you don’t need them forever.

These steps **directly avoid** the main ways the database and app can negatively affect the system as data grows.

### 3.3 Backups (so growth doesn’t mean “single point of failure”)

- **MongoDB**: Regular `mongodump` of the `stockpulse` DB to `backend/backups/mongo/` (or another dir). Test restore once.
- **PostgreSQL**: Regular `pg_dump` of `stockpulse_ts` to `backend/backups/postgres/`. Test restore once.
- **Redis**: Optional; if you use it only as cache, backing up is less critical. If you store important state, use RDB/AOF and back up the `dir` from `redis-cli config get dir`.

Keep a few backup generations and make sure `backups/` isn’t committed to git and isn’t served by the web server.

### 3.4 If your Mac disk is small

- Move **Mongo/Postgres data dirs** to an external drive (or a bigger volume) by changing their config and restarting the services. Then point your app’s connection strings to the same host/port (no app change).
- Or move only **project-side** large data: e.g. set `BHAVCOPY_DIR` and `BACKUPS_DIR` to a path on an external drive so `reports/`, `data/bhavcopy/`, `backups/` don’t fill the main SSD.

---

## 4. Short answers to your questions

- **Will all the data be saved locally (on your Mac)?**  
  **Yes.** Mongo, Redis, and Postgres store data in their own directories on your Mac. Only reports, bhavcopy, models, and backups are under the project folder (also on your Mac).

- **Will growth affect the system?**  
  **Yes, if unchecked:** full disk, high RAM (especially Mongo/Redis), and slow queries. With retention (TTL/cleanup), indexes, Redis `maxmemory`, and occasional vacuum/cleanup, you can keep things stable.

- **How to manage it / avoid negative impact?**  
  **Do it now:** (1) Know where each store keeps data and check sizes occasionally. (2) Add retention/TTL/cleanup for logs and jobs in Mongo. (3) Set Redis `maxmemory` and eviction. (4) Clean or archive old bhavcopy and reports. (5) Back up Mongo and Postgres and test restore. That’s enough to prevent the database from negatively affecting the system or making it slow under normal single-user growth.
