"""
Feature Store — Lightweight Redis + PostgreSQL feature storage.

Provides point-in-time correct feature retrieval using the existing
Redis cache (online store) and PostgreSQL time-series store (offline store).

Design decisions:
    - Uses Redis for latest features per symbol (online serving, <5ms)
    - Uses PostgreSQL for historical features (offline training)
    - Feature versioning via Redis key namespacing
    - TTL: 5s during market hours, 300s post-market
    - Lightweight alternative to full Feast — same API surface, less complexity

Usage:
    store = FeatureStore(redis_client, pg_pool)
    await store.put_online("RELIANCE", features_dict)
    features = await store.get_online("RELIANCE")
    history = await store.get_historical("RELIANCE", start, end)
"""

import json
import logging
from datetime import datetime, timedelta, timezone, time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("brain.features.feature_store")

IST = timezone(timedelta(hours=5, minutes=30))

# Market hours for TTL logic
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# Feature key prefix and version
FEATURE_KEY_PREFIX = "brain:features"
FEATURE_VERSION = "v1"


def _is_market_hours() -> bool:
    """Check if we're currently in Indian market trading hours."""
    now = datetime.now(IST)
    if now.weekday() >= 5:  # Saturday, Sunday
        return False
    current_time = now.time()
    return MARKET_OPEN <= current_time <= MARKET_CLOSE


def _feature_key(symbol: str, version: str = FEATURE_VERSION) -> str:
    """Generate Redis key for a symbol's features."""
    return f"{FEATURE_KEY_PREFIX}:{version}:{symbol.upper()}"


def _feature_meta_key(symbol: str, version: str = FEATURE_VERSION) -> str:
    """Generate Redis key for feature metadata."""
    return f"{FEATURE_KEY_PREFIX}:{version}:{symbol.upper()}:meta"


class FeatureStore:
    """
    Lightweight feature store backed by Redis (online) and PostgreSQL (offline).

    The store is designed with the same API surface as Feast to allow
    future migration if scale demands it.
    """

    def __init__(
        self,
        redis_client=None,
        pg_pool=None,
        market_hours_ttl: int = 5,
        post_market_ttl: int = 300,
        mongo_db=None,
    ):
        """
        Args:
            redis_client: aioredis/redis-py async client (existing cache_service).
            pg_pool: asyncpg connection pool (existing timeseries_store).
            market_hours_ttl: TTL in seconds during market hours (default: 5s).
            post_market_ttl: TTL in seconds outside market hours (default: 300s).
            mongo_db: MongoDB database instance for feature persistence.
        """
        self.redis = redis_client
        self.pg = pg_pool
        self.mongo_db = mongo_db
        self.market_hours_ttl = market_hours_ttl
        self.post_market_ttl = post_market_ttl
        self._stats = {
            "puts": 0,
            "gets": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

    @property
    def _ttl(self) -> int:
        """Dynamic TTL based on market hours."""
        return self.market_hours_ttl if _is_market_hours() else self.post_market_ttl

    # -----------------------------------------------------------------------
    # Online Store (Redis)
    # -----------------------------------------------------------------------

    async def put_online(
        self,
        symbol: str,
        features: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Store latest features for a symbol in Redis.

        Args:
            symbol: Stock symbol (e.g. RELIANCE).
            features: Dict of feature_name → value.
            metadata: Optional metadata (computation timestamp, source, etc.).

        Returns:
            True if stored successfully.
        """
        if not self.redis:
            logger.debug("[NO REDIS] Would store %d features for %s", len(features), symbol)
            self._stats["puts"] += 1
            return True

        try:
            key = _feature_key(symbol)
            ttl = self._ttl

            # Serialize features as JSON
            payload = json.dumps(features, default=str)
            await self.redis.setex(key, ttl, payload)

            # Store metadata if provided
            if metadata:
                meta_key = _feature_meta_key(symbol)
                meta_payload = json.dumps({
                    **metadata,
                    "updated_at": datetime.now(IST).isoformat(),
                    "version": FEATURE_VERSION,
                    "feature_count": len(features),
                    "ttl_seconds": ttl,
                }, default=str)
                await self.redis.setex(meta_key, ttl, meta_payload)

            self._stats["puts"] += 1
            return True

        except Exception:
            logger.exception("Error storing features for %s", symbol)
            return False

    async def get_online(
        self,
        symbol: str,
        feature_names: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get latest features for a symbol from Redis.

        Args:
            symbol: Stock symbol.
            feature_names: Optional filter — return only these features.

        Returns:
            Dict of features, or None if not found/expired.
        """
        self._stats["gets"] += 1

        if not self.redis:
            logger.debug("[NO REDIS] Feature lookup for %s skipped", symbol)
            self._stats["cache_misses"] += 1
            return None

        try:
            key = _feature_key(symbol)
            raw = await self.redis.get(key)

            if raw is None:
                self._stats["cache_misses"] += 1
                return None

            self._stats["cache_hits"] += 1
            features = json.loads(raw)

            if feature_names:
                return {k: v for k, v in features.items() if k in feature_names}
            return features

        except Exception:
            logger.exception("Error retrieving features for %s", symbol)
            self._stats["cache_misses"] += 1
            return None

    async def get_online_batch(
        self,
        symbols: List[str],
        feature_names: Optional[List[str]] = None,
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Get features for multiple symbols in batch.

        Returns a dict mapping symbol → features (or None if not cached).
        """
        result = {}
        for symbol in symbols:
            result[symbol] = await self.get_online(symbol, feature_names)
        return result

    async def get_feature_metadata(self, symbol: str) -> Optional[Dict]:
        """Get metadata for a symbol's cached features."""
        if not self.redis:
            return None
        try:
            key = _feature_meta_key(symbol)
            raw = await self.redis.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    # -----------------------------------------------------------------------
    # Offline Store (PostgreSQL)
    # -----------------------------------------------------------------------

    async def put_historical(
        self,
        symbol: str,
        timestamp: datetime,
        features: Dict[str, Any],
    ) -> bool:
        """
        Store a historical feature snapshot in PostgreSQL.

        This is used for ML training with point-in-time correct features.

        Args:
            symbol: Stock symbol.
            timestamp: Point-in-time timestamp.
            features: Feature dict.

        Returns:
            True if stored successfully.
        """
        if not self.pg:
            logger.debug("[NO PG] Would store historical features for %s at %s", symbol, timestamp)
            return True

        try:
            await self.pg.execute(
                """
                INSERT INTO brain_feature_snapshots (symbol, timestamp, features, version)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (symbol, timestamp, version)
                DO UPDATE SET features = $3
                """,
                symbol.upper(),
                timestamp,
                json.dumps(features, default=str),
                FEATURE_VERSION,
            )
            return True
        except Exception:
            logger.exception("Error storing historical features for %s", symbol)
            return False

    async def get_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        feature_names: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get historical feature snapshots for training.

        Returns list of feature dicts with point-in-time correct values
        (only uses features that were available at each timestamp).

        Args:
            symbol: Stock symbol.
            start: Start of time range.
            end: End of time range.
            feature_names: Optional filter.

        Returns:
            List of dicts, each with 'timestamp' and feature values.
        """
        if not self.pg:
            logger.debug("[NO PG] Historical feature lookup for %s skipped", symbol)
            return []

        try:
            rows = await self.pg.fetch(
                """
                SELECT timestamp, features
                FROM brain_feature_snapshots
                WHERE symbol = $1
                  AND timestamp >= $2
                  AND timestamp <= $3
                  AND version = $4
                ORDER BY timestamp ASC
                """,
                symbol.upper(),
                start,
                end,
                FEATURE_VERSION,
            )

            results = []
            for row in rows:
                features = json.loads(row["features"])
                if feature_names:
                    features = {k: v for k, v in features.items() if k in feature_names}
                features["timestamp"] = row["timestamp"].isoformat()
                results.append(features)

            return results
        except Exception:
            logger.exception("Error retrieving historical features for %s", symbol)
            return []

    # -----------------------------------------------------------------------
    # Schema management
    # -----------------------------------------------------------------------

    async def ensure_schema(self):
        """Create the PostgreSQL table for historical features if it doesn't exist."""
        if not self.pg:
            return

        try:
            await self.pg.execute("""
                CREATE TABLE IF NOT EXISTS brain_feature_snapshots (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    features JSONB NOT NULL,
                    version VARCHAR(10) NOT NULL DEFAULT 'v1',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE (symbol, timestamp, version)
                );

                CREATE INDEX IF NOT EXISTS idx_brain_features_symbol_ts
                ON brain_feature_snapshots (symbol, timestamp);
            """)
            logger.info("Brain feature store schema ensured")
        except Exception:
            logger.exception("Error creating feature store schema")

    # -----------------------------------------------------------------------
    # Stats
    # -----------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return feature store statistics."""
        hit_rate = 0.0
        total = self._stats["cache_hits"] + self._stats["cache_misses"]
        if total > 0:
            hit_rate = self._stats["cache_hits"] / total * 100.0

        return {
            **self._stats,
            "cache_hit_rate": round(hit_rate, 2),
            "current_ttl": self._ttl,
            "is_market_hours": _is_market_hours(),
            "version": FEATURE_VERSION,
        }

    # -----------------------------------------------------------------------
    # MongoDB Persistence Layer (for Engine abstraction)
    # -----------------------------------------------------------------------

    async def store_features(
        self,
        symbol: str,
        features: Dict[str, Any],
    ) -> bool:
        """
        Store computed features in MongoDB (abstraction for engine.py).
        
        This method provides a clean interface for the Brain engine to persist
        features without directly accessing MongoDB collections.
        
        Args:
            symbol: Stock symbol
            features: Computed feature dictionary
            
        Returns:
            True if stored successfully, False otherwise
        """
        if self.mongo_db is None or not features:
            return False
        
        try:
            await self.mongo_db["brain_features"].update_one(
                {"symbol": symbol.upper()},
                {"$set": {
                    "symbol": symbol.upper(),
                    "features": features,
                    "feature_count": len(features),
                    "computed_at": datetime.now(IST).isoformat(),
                }},
                upsert=True,
            )
            logger.debug("Stored %d features for %s", len(features), symbol)
            return True
        except Exception:
            logger.exception("Error storing features for %s in MongoDB", symbol)
            return False

    async def get_features(
        self,
        symbol: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve stored features from MongoDB (abstraction for engine.py).
        
        This method provides a clean interface for the Brain engine to retrieve
        features without directly accessing MongoDB collections.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Feature document dict, or None if not found
        """
        if self.mongo_db is None:
            return None
        
        try:
            doc = await self.mongo_db["brain_features"].find_one(
                {"symbol": symbol.upper()},
                {"_id": 0},
            )
            return doc
        except Exception:
            logger.exception("Error retrieving features for %s from MongoDB", symbol)
            return None
