"""
Regime Persistence Store

Saves and retrieves regime state from Redis (real-time) and optionally
PostgreSQL (long-term history).

Redis keys:
    brain:regime:current   - JSON of current regime + probabilities
    brain:regime:history   - Redis list of historical regime entries (capped)
"""

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from brain.models.events import MarketRegime

logger = logging.getLogger(__name__)

_CURRENT_KEY = "brain:regime:current"
_HISTORY_KEY = "brain:regime:history"
_MAX_HISTORY_LEN = 365  # keep at most 1 year of daily entries in Redis


class RegimeStore:
    """
    Persistence layer for market regime state.

    Args:
        cache_service: Redis-compatible async client (must support
                       ``set``, ``get``, ``lpush``, ``ltrim``, ``lrange``).
        ts_store: Optional PostgreSQL timeseries store for long-term history.
    """

    def __init__(
        self,
        cache_service: Any = None,
        ts_store: Any = None,
    ):
        self._cache = cache_service
        self._ts_store = ts_store

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def save_regime(
        self,
        regime: MarketRegime,
        probabilities: Dict[str, float],
        regime_date: date,
    ) -> None:
        """
        Persist the current regime to Redis (and optionally Postgres).

        Args:
            regime: The detected market regime.
            probabilities: Dict with bull_prob, bear_prob, sideways_prob.
            regime_date: The date this regime applies to.
        """
        entry = {
            "regime": regime.value,
            "probabilities": probabilities,
            "date": regime_date.isoformat(),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        serialized = json.dumps(entry)

        if self._cache is not None:
            try:
                await self._cache.set(_CURRENT_KEY, serialized)
                await self._cache.lpush(_HISTORY_KEY, serialized)
                await self._cache.ltrim(_HISTORY_KEY, 0, _MAX_HISTORY_LEN - 1)
                logger.debug(
                    "Regime saved to Redis: %s on %s", regime.value, regime_date
                )
            except Exception:
                logger.exception("Failed to save regime to Redis")
        else:
            logger.debug(
                "No cache service configured; regime not persisted to Redis."
            )

        # Optional: persist to PostgreSQL
        if self._ts_store is not None:
            try:
                await self._persist_to_pg(entry)
            except Exception:
                logger.exception("Failed to save regime to PostgreSQL")

    async def _persist_to_pg(self, entry: Dict[str, Any]) -> None:
        """Write regime entry to the timeseries store (best-effort)."""
        # This is a placeholder for the actual Postgres write.
        # The ts_store is expected to expose an execute or insert method.
        logger.debug("PostgreSQL regime persistence: %s", entry)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_current_regime(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve the current regime from Redis.

        Returns:
            Dict with keys ``regime``, ``probabilities``, ``date``, ``saved_at``
            or None if unavailable.
        """
        if self._cache is None:
            return None

        try:
            raw = await self._cache.get(_CURRENT_KEY)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            logger.exception("Failed to read current regime from Redis")
            return None

    async def get_history(self, days: int = 90) -> List[Dict[str, Any]]:
        """
        Retrieve regime history from Redis.

        Args:
            days: Maximum number of entries to return.

        Returns:
            List of regime dicts ordered newest-first.
        """
        if self._cache is None:
            return []

        try:
            count = min(days, _MAX_HISTORY_LEN)
            raw_list = await self._cache.lrange(_HISTORY_KEY, 0, count - 1)
            return [json.loads(item) for item in raw_list]
        except Exception:
            logger.exception("Failed to read regime history from Redis")
            return []
