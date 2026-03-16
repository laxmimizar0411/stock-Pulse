"""
Redis Cache Service for StockPulse

Provides centralized caching with TTL-based expiry for:
- Live stock quotes (60s TTL)
- Stock analysis results (300s TTL)
- Pipeline status (30s TTL)
- General purpose caching

Falls back to in-memory caching if Redis is unavailable.
"""

import json
import logging
import os
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# TTL Constants (seconds)
PRICE_CACHE_TTL = 60        # 1 minute for live price quotes
ANALYSIS_CACHE_TTL = 300    # 5 minutes for analysis results
STOCK_LIST_CACHE_TTL = 300  # 5 minutes for stock list/mock data
PIPELINE_CACHE_TTL = 30     # 30 seconds for pipeline status
NEWS_CACHE_TTL = 180        # 3 minutes for news items
DEFAULT_CACHE_TTL = 120     # 2 minutes default

# Configurable namespace prefix for key isolation (e.g. "stockpulse:" or "" for none)
KEY_PREFIX = os.environ.get("REDIS_KEY_PREFIX", "stockpulse:")

# Cache key prefixes (combined with KEY_PREFIX at runtime)
PREFIX_PRICE = "price:"
PREFIX_ANALYSIS = "analysis:"
PREFIX_STOCK = "stock:"
PREFIX_STOCK_LIST = "stock_list"
PREFIX_PIPELINE = "pipeline:"
PREFIX_NEWS = "news:"
PREFIX_MARKET = "market:"

# Alert queue constraints
ALERT_QUEUE_MAX_LENGTH = 1000

# In-memory fallback constraints
FALLBACK_MAX_KEYS = int(os.environ.get("REDIS_FALLBACK_MAX_KEYS", "10000"))


class _LRUFallbackCache:
    """
    Bounded in-memory cache with LRU eviction and TTL support.
    Prevents unbounded memory growth when Redis is unavailable.
    """

    def __init__(self, max_keys: int = FALLBACK_MAX_KEYS):
        self._store: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._max_keys = max_keys

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.time() > entry["expires_at"]:
            del self._store[key]
            return None
        # Move to end (most recently used)
        self._store.move_to_end(key)
        return entry["value"]

    def set(self, key: str, value: Any, ttl: int) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = {
            "value": value,
            "expires_at": time.time() + ttl,
        }
        # Evict oldest if over capacity
        while len(self._store) > self._max_keys:
            self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def match_delete(self, pattern: str) -> int:
        """Delete keys matching a simple glob pattern (e.g. 'price:*')."""
        prefix = pattern.rstrip("*") if pattern.endswith("*") else None
        to_delete = []
        for k in self._store:
            if prefix is not None:
                if k.startswith(prefix):
                    to_delete.append(k)
            elif k == pattern:
                to_delete.append(k)
        for k in to_delete:
            del self._store[k]
        return len(to_delete)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)

    @staticmethod
    def _match_pattern(key: str, pattern: str) -> bool:
        if pattern.endswith("*"):
            return key.startswith(pattern[:-1])
        return key == pattern


class CacheService:
    """
    Redis-backed cache service with bounded in-memory fallback.

    Uses the synchronous redis-py client for simplicity since cache
    operations are fast (~1ms) and don't benefit much from async overhead.
    For async support, this can be upgraded to redis.asyncio.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379", db: int = 0):
        self._redis = None
        self._pool = None
        self._redis_available = False
        self._fallback_cache = _LRUFallbackCache(max_keys=FALLBACK_MAX_KEYS)
        self._redis_url = redis_url
        self._db = db
        self._key_prefix = KEY_PREFIX
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "errors": 0,
        }

        # Configurable timeouts via environment
        self._connect_timeout = int(os.environ.get("REDIS_CONNECT_TIMEOUT", "5"))
        self._socket_timeout = int(os.environ.get("REDIS_SOCKET_TIMEOUT", "5"))
        self._max_connections = int(os.environ.get("REDIS_MAX_CONNECTIONS", "10"))

        # Optional TLS certificate paths for self-signed / mTLS connections
        # When REDIS_URL uses "rediss://" scheme, TLS is auto-enabled.
        # These env vars are only needed for custom CA or client certs.
        self._ssl_ca_certs = os.environ.get("REDIS_SSL_CA_CERTS")       # CA bundle path
        self._ssl_certfile = os.environ.get("REDIS_SSL_CERTFILE")       # Client cert path
        self._ssl_keyfile = os.environ.get("REDIS_SSL_KEYFILE")         # Client key path

    def initialize(self):
        """Initialize Redis connection with retry and backoff. Safe to call multiple times."""
        max_retries = 3
        backoff_base = 1  # seconds

        for attempt in range(1, max_retries + 1):
            try:
                import redis as redis_lib

                # Build extra kwargs for TLS when custom certs are provided
                ssl_kwargs = {}
                if self._ssl_ca_certs:
                    ssl_kwargs["ssl_ca_certs"] = self._ssl_ca_certs
                if self._ssl_certfile:
                    ssl_kwargs["ssl_certfile"] = self._ssl_certfile
                if self._ssl_keyfile:
                    ssl_kwargs["ssl_keyfile"] = self._ssl_keyfile

                self._pool = redis_lib.ConnectionPool.from_url(
                    self._redis_url,
                    db=self._db,
                    decode_responses=True,
                    socket_connect_timeout=self._connect_timeout,
                    socket_timeout=self._socket_timeout,
                    retry_on_timeout=True,
                    max_connections=self._max_connections,
                    **ssl_kwargs,
                )
                self._redis = redis_lib.Redis(connection_pool=self._pool)
                # Test connection
                self._redis.ping()
                self._redis_available = True
                logger.info("Redis cache connected successfully")
                return
            except ImportError:
                logger.warning("redis package not installed, using in-memory cache fallback")
                self._redis_available = False
                return
            except Exception as e:
                if attempt < max_retries:
                    wait = backoff_base * (2 ** (attempt - 1))
                    logger.warning(
                        f"Redis connection attempt {attempt}/{max_retries} failed ({e}), "
                        f"retrying in {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    logger.warning(
                        f"Redis not available after {max_retries} attempts ({e}), "
                        f"using in-memory cache fallback"
                    )
                    self._redis_available = False

    def _try_reconnect(self) -> bool:
        """Attempt a single reconnection to Redis. Returns True if successful."""
        if self._redis is None:
            return False
        try:
            self._redis.ping()
            self._redis_available = True
            logger.info("Redis reconnected successfully")
            return True
        except Exception:
            return False

    @property
    def is_redis_available(self) -> bool:
        return self._redis_available

    def get_connection_pool(self):
        """Return the underlying ConnectionPool for sharing with other components (e.g. PriceBroadcaster)."""
        return self._pool

    def _key(self, key: str) -> str:
        """Apply the namespace prefix to a cache key."""
        if self._key_prefix and not key.startswith(self._key_prefix):
            return f"{self._key_prefix}{key}"
        return key

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache. Returns None on miss."""
        full_key = self._key(key)
        try:
            if self._redis_available:
                data = self._redis.get(full_key)
                if data is not None:
                    self._stats["hits"] += 1
                    return json.loads(data)
                self._stats["misses"] += 1
                return None
            else:
                # Fallback: bounded in-memory cache with TTL
                result = self._fallback_cache.get(full_key)
                if result is not None:
                    self._stats["hits"] += 1
                    return result
                self._stats["misses"] += 1
                return None
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"Cache get error for {full_key}: {e}")
            # Try reconnect on failure, fall through to None
            if self._redis_available:
                self._redis_available = False
                self._try_reconnect()
            return None

    def set(self, key: str, value: Any, ttl: int = DEFAULT_CACHE_TTL) -> bool:
        """Set a value in cache with TTL (seconds). Returns True on success."""
        full_key = self._key(key)
        try:
            serialized = json.dumps(value, default=str)
            if self._redis_available:
                self._redis.setex(full_key, ttl, serialized)
            else:
                self._fallback_cache.set(full_key, value, ttl)
            self._stats["sets"] += 1
            return True
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"Cache set error for {full_key}: {e}")
            if self._redis_available:
                self._redis_available = False
                self._try_reconnect()
            return False

    def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        full_key = self._key(key)
        try:
            if self._redis_available:
                self._redis.delete(full_key)
            else:
                self._fallback_cache.delete(full_key)
            return True
        except Exception as e:
            logger.debug(f"Cache delete error for {full_key}: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern using SCAN (not KEYS). Returns count deleted."""
        full_pattern = self._key(pattern)
        try:
            if self._redis_available:
                deleted = 0
                cursor = 0
                while True:
                    cursor, keys = self._redis.scan(cursor=cursor, match=full_pattern, count=100)
                    if keys:
                        deleted += self._redis.delete(*keys)
                    if cursor == 0:
                        break
                return deleted
            else:
                return self._fallback_cache.match_delete(full_pattern)
        except Exception as e:
            logger.debug(f"Cache delete_pattern error for {full_pattern}: {e}")
            return 0

    # ========================
    # Domain-specific helpers
    # ========================

    def get_price(self, symbol: str) -> Optional[Dict]:
        """Get cached live price quote for a symbol."""
        return self.get(f"{PREFIX_PRICE}{symbol}")

    def set_price(self, symbol: str, data: Dict) -> bool:
        """Cache live price quote for a symbol."""
        return self.set(f"{PREFIX_PRICE}{symbol}", data, PRICE_CACHE_TTL)

    def get_analysis(self, symbol: str) -> Optional[Dict]:
        """Get cached analysis result for a symbol."""
        return self.get(f"{PREFIX_ANALYSIS}{symbol}")

    def set_analysis(self, symbol: str, data: Dict) -> bool:
        """Cache analysis result for a symbol."""
        return self.set(f"{PREFIX_ANALYSIS}{symbol}", data, ANALYSIS_CACHE_TTL)

    def get_stock_list(self) -> Optional[Dict]:
        """Get cached stock list (all stocks data)."""
        return self.get(PREFIX_STOCK_LIST)

    def set_stock_list(self, data: Dict) -> bool:
        """Cache stock list (all stocks data)."""
        return self.set(PREFIX_STOCK_LIST, data, STOCK_LIST_CACHE_TTL)

    def get_market_overview(self) -> Optional[Dict]:
        """Get cached market overview."""
        return self.get(f"{PREFIX_MARKET}overview")

    def set_market_overview(self, data: Dict) -> bool:
        """Cache market overview."""
        return self.set(f"{PREFIX_MARKET}overview", data, PRICE_CACHE_TTL)

    def invalidate_stock(self, symbol: str):
        """Invalidate all caches for a specific stock."""
        self.delete(f"{PREFIX_PRICE}{symbol}")
        self.delete(f"{PREFIX_ANALYSIS}{symbol}")
        self.delete(f"{PREFIX_STOCK}{symbol}")

    def invalidate_all(self):
        """Invalidate all caches."""
        if self._redis_available:
            try:
                self._redis.flushdb()
            except Exception as e:
                logger.warning(f"Failed to flush Redis: {e}")
        else:
            self._fallback_cache.clear()

    def get_stats(self) -> Dict:
        """Get cache statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0

        stats = {
            **self._stats,
            "hit_rate_percent": round(hit_rate, 2),
            "backend": "redis" if self._redis_available else "in-memory",
        }

        if self._redis_available:
            try:
                info = self._redis.info("memory")
                stats["redis_memory_used"] = info.get("used_memory_human", "N/A")
                stats["redis_keys"] = self._redis.dbsize()
            except Exception:
                pass
        else:
            stats["in_memory_keys"] = len(self._fallback_cache)

        return stats

    def close(self):
        """Close Redis connection."""
        if self._redis:
            try:
                self._redis.close()
            except Exception:
                pass

    # ========================
    # HASH — per-field stock data
    # ========================

    def set_stock_hash(self, symbol: str, fields: Dict[str, Any]) -> bool:
        """Store individual stock fields as a Redis HASH (enables partial reads)."""
        try:
            if self._redis_available:
                key = self._key(f"stock:{symbol}")
                # Convert all values to strings for Redis HASH
                str_fields = {k: json.dumps(v, default=str) for k, v in fields.items()}
                self._redis.hset(key, mapping=str_fields)
                self._redis.expire(key, PRICE_CACHE_TTL)
                self._stats["sets"] += 1
                return True
            return False
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"HASH set error for {symbol}: {e}")
            return False

    def get_stock_hash(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get all fields from a stock's HASH."""
        try:
            if self._redis_available:
                data = self._redis.hgetall(self._key(f"stock:{symbol}"))
                if data:
                    self._stats["hits"] += 1
                    return {k: json.loads(v) for k, v in data.items()}
                self._stats["misses"] += 1
            return None
        except Exception as e:
            self._stats["errors"] += 1
            return None

    def get_stock_field(self, symbol: str, field: str) -> Optional[Any]:
        """Get a single field from a stock's HASH (e.g., just the price)."""
        try:
            if self._redis_available:
                data = self._redis.hget(self._key(f"stock:{symbol}"), field)
                if data:
                    self._stats["hits"] += 1
                    return json.loads(data)
                self._stats["misses"] += 1
            return None
        except Exception as e:
            self._stats["errors"] += 1
            return None

    def get_stock_fields(self, symbol: str, fields: List[str]) -> Dict[str, Any]:
        """Get multiple fields from a stock's HASH."""
        try:
            if self._redis_available:
                values = self._redis.hmget(self._key(f"stock:{symbol}"), fields)
                result = {}
                for f, v in zip(fields, values):
                    if v is not None:
                        result[f] = json.loads(v)
                if result:
                    self._stats["hits"] += 1
                else:
                    self._stats["misses"] += 1
                return result
            return {}
        except Exception:
            return {}

    # ========================
    # SORTED SET — top movers
    # ========================

    def update_top_movers(self, gainers: Dict[str, float], losers: Dict[str, float]) -> bool:
        """
        Update top gainers and losers using Redis SORTED SETs.

        Args:
            gainers: Dict of {symbol: price_change_percent} for gainers
            losers: Dict of {symbol: price_change_percent} for losers
        """
        try:
            if self._redis_available:
                gk = self._key("top_gainers")
                lk = self._key("top_losers")
                if gainers:
                    self._redis.zadd(gk, gainers)
                    self._redis.expire(gk, PRICE_CACHE_TTL)
                if losers:
                    # Store as positive values, sorted ascending → worst first
                    self._redis.zadd(lk, {k: abs(v) for k, v in losers.items()})
                    self._redis.expire(lk, PRICE_CACHE_TTL)
                return True
            return False
        except Exception as e:
            logger.debug(f"ZSET update error: {e}")
            return False

    def get_top_gainers(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get top N gainers from SORTED SET (highest change % first)."""
        try:
            if self._redis_available:
                results = self._redis.zrevrange(self._key("top_gainers"), 0, count - 1, withscores=True)
                return [{"symbol": sym, "change_pct": score} for sym, score in results]
            return []
        except Exception:
            return []

    def get_top_losers(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get top N losers from SORTED SET (biggest loss first)."""
        try:
            if self._redis_available:
                results = self._redis.zrevrange(self._key("top_losers"), 0, count - 1, withscores=True)
                return [{"symbol": sym, "change_pct": -score} for sym, score in results]
            return []
        except Exception:
            return []

    # ========================
    # PUB/SUB — real-time prices
    # ========================

    def publish_price(self, symbol: str, price_data: Dict) -> bool:
        """Publish a price update to the Redis PUB/SUB channel."""
        try:
            if self._redis_available:
                channel = self._key("channel:prices")
                payload = json.dumps({"symbol": symbol, **price_data}, default=str)
                self._redis.publish(channel, payload)
                return True
            return False
        except Exception as e:
            logger.debug(f"PUB/SUB publish error: {e}")
            return False

    def publish_alert(self, alert_data: Dict) -> bool:
        """Push an alert notification to the Redis alert queue (LIST).
        Caps the queue at ALERT_QUEUE_MAX_LENGTH to prevent unbounded growth."""
        try:
            if self._redis_available:
                queue_key = self._key("alert_queue")
                payload = json.dumps(alert_data, default=str)
                pipe = self._redis.pipeline()
                pipe.rpush(queue_key, payload)
                pipe.ltrim(queue_key, -ALERT_QUEUE_MAX_LENGTH, -1)
                pipe.execute()
                return True
            return False
        except Exception as e:
            logger.debug(f"Alert queue push error: {e}")
            return False

    # ========================
    # Dashboard / introspection helpers
    # ========================

    def get_redis_info(self, section: str = "memory") -> Optional[Dict[str, Any]]:
        """Get Redis INFO for a given section. Returns None if unavailable."""
        if not self._redis_available:
            return None
        try:
            return self._redis.info(section)
        except Exception as e:
            logger.debug(f"Redis INFO error: {e}")
            return None

    def get_dbsize(self) -> int:
        """Get total number of keys in the current Redis database."""
        if not self._redis_available:
            return 0
        try:
            return self._redis.dbsize()
        except Exception:
            return 0

    def scan_keys(
        self, pattern: str = "*", count: int = 100, max_keys: int = 500
    ) -> List[str]:
        """
        Scan Redis keys matching a pattern using SCAN (non-blocking).
        Returns up to max_keys matching key names.
        """
        if not self._redis_available:
            return []
        try:
            keys = []
            cursor = 0
            while True:
                cursor, batch = self._redis.scan(cursor=cursor, match=pattern, count=count)
                for key in batch:
                    if isinstance(key, bytes):
                        key = key.decode("utf-8")
                    keys.append(key)
                    if len(keys) >= max_keys:
                        return keys
                if cursor == 0:
                    break
            return keys
        except Exception as e:
            logger.debug(f"Redis SCAN error: {e}")
            return []

    def get_key_info(self, key: str) -> Optional[Dict[str, Any]]:
        """Get type and TTL for a single Redis key."""
        if not self._redis_available:
            return None
        try:
            key_type = self._redis.type(key)
            if isinstance(key_type, bytes):
                key_type = key_type.decode("utf-8")
            ttl = self._redis.ttl(key)
            return {"type": key_type, "ttl": ttl if ttl > 0 else None}
        except Exception:
            return None

    def get_key_value_preview(self, key: str, max_length: int = 500) -> Optional[Dict[str, Any]]:
        """Get a preview of a key's value for dashboard display."""
        if not self._redis_available:
            return None
        try:
            key_type = self._redis.type(key)
            if isinstance(key_type, bytes):
                key_type = key_type.decode("utf-8")

            info: Dict[str, Any] = {}
            if key_type == "string":
                val = self._redis.get(key)
                if isinstance(val, bytes):
                    val = val.decode("utf-8")
                if val and len(val) > max_length:
                    val = val[:max_length] + "...(truncated)"
                info["value_preview"] = val
            elif key_type == "list":
                info["length"] = self._redis.llen(key)
            elif key_type == "set":
                info["members"] = self._redis.scard(key)
            elif key_type == "zset":
                info["members"] = self._redis.zcard(key)
            elif key_type == "hash":
                info["fields"] = self._redis.hlen(key)
            return info
        except Exception:
            return None


# Module-level singleton
_cache_service: Optional[CacheService] = None
_health_check_task = None


def init_cache_service(redis_url: str = "redis://localhost:6379") -> CacheService:
    """Initialize and return the global cache service singleton."""
    global _cache_service
    _cache_service = CacheService(redis_url=redis_url)
    _cache_service.initialize()
    return _cache_service


def get_cache_service() -> Optional[CacheService]:
    """Get the global cache service instance."""
    return _cache_service


async def start_health_check(interval: int = 60, on_reconnect=None):
    """Start a periodic Redis health check that pings every `interval` seconds
    and attempts reconnection if Redis was lost.

    Args:
        interval: Seconds between health checks.
        on_reconnect: Optional async callback invoked when Redis reconnects
                      after being unavailable (e.g., to restart the alert consumer).
    """
    import asyncio

    global _health_check_task

    async def _loop():
        while True:
            try:
                await asyncio.sleep(interval)
                svc = get_cache_service()
                if svc is None:
                    continue
                if svc._redis is not None:
                    try:
                        svc._redis.ping()
                        if not svc._redis_available:
                            svc._redis_available = True
                            logger.info("Redis health check: reconnected")
                            # Fire reconnect callback (e.g., restart alert consumer)
                            if on_reconnect is not None:
                                try:
                                    await on_reconnect()
                                except Exception as cb_err:
                                    logger.warning(f"Redis on_reconnect callback error: {cb_err}")
                    except Exception:
                        if svc._redis_available:
                            svc._redis_available = False
                            logger.warning("Redis health check: connection lost, using fallback")
                        svc._try_reconnect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Redis health check error: {e}")

    _health_check_task = asyncio.get_event_loop().create_task(_loop())
    logger.info(f"Redis health check started (every {interval}s)")


async def stop_health_check():
    """Stop the periodic Redis health check."""
    global _health_check_task
    if _health_check_task is not None:
        _health_check_task.cancel()
        try:
            await _health_check_task
        except Exception:
            pass
        _health_check_task = None
