"""
StockPulse Background Jobs

Shared utilities and job modules for periodic data computation.
"""

import asyncio
import logging
from functools import wraps
from typing import TypeVar, Callable

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds


def with_retry(max_retries: int = MAX_RETRIES, backoff_base: float = BACKOFF_BASE):
    """
    Decorator for async functions that retries on transient database errors
    with exponential backoff.

    Usage:
        @with_retry(max_retries=3)
        async def my_db_operation(...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                    last_exc = e
                    if attempt < max_retries:
                        wait = backoff_base ** attempt
                        logger.warning(
                            "Retry %d/%d for %s after %s (waiting %.1fs)",
                            attempt, max_retries, func.__name__, e, wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(
                            "All %d retries exhausted for %s: %s",
                            max_retries, func.__name__, e,
                        )
                except Exception:
                    # Non-transient errors should not be retried
                    raise
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator
