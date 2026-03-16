"""
Redis-backed API Rate Limiting for StockPulse

Uses a sliding-window counter via Redis INCR + EXPIRE.
Falls back to an in-memory dict when Redis is unavailable.

Usage:
    from services.rate_limiter import rate_limiter_middleware

    # Add to FastAPI app (in server.py)
    app.middleware("http")(rate_limiter_middleware)
"""

import logging
import os
import time
from collections import defaultdict
from typing import Dict, Tuple

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration via environment
# ---------------------------------------------------------------------------
# Default: 120 requests per 60 seconds per IP
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "120"))
RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))  # seconds

# Heavier endpoints get tighter limits
TIGHT_LIMIT_PATHS = {
    "/api/stocks/{symbol}/llm-insight": 10,
    "/api/reports/generate": 10,
    "/api/reports/generate-pdf": 10,
    "/api/backtest/run": 20,
    "/api/screener": 30,
    "/api/pipeline/run": 10,
}

# Exempt health checks and static assets
EXEMPT_PREFIXES = ("/api/health", "/docs", "/openapi.json", "/ws/")


# ---------------------------------------------------------------------------
# In-memory fallback (for single-instance when Redis is unavailable)
# ---------------------------------------------------------------------------
_mem_counters: Dict[str, list] = defaultdict(list)


def _cleanup_window(key: str, window: int):
    """Remove expired timestamps from the in-memory counter."""
    cutoff = time.time() - window
    _mem_counters[key] = [t for t in _mem_counters[key] if t > cutoff]


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------
def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a reverse proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_limit_for_path(path: str) -> int:
    """Return the request limit for a given path."""
    for pattern, limit in TIGHT_LIMIT_PATHS.items():
        # Simple prefix match (patterns with {param} match the prefix)
        prefix = pattern.split("{")[0]
        if path.startswith(prefix):
            return limit
    return RATE_LIMIT_REQUESTS


def _check_rate_limit_redis(redis_client, key: str, limit: int, window: int) -> Tuple[bool, int, int]:
    """Check rate limit using Redis INCR + EXPIRE.
    Returns (allowed, current_count, ttl_remaining)."""
    try:
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = pipe.execute()

        # Set expiry on first request in the window
        if ttl == -1:
            redis_client.expire(key, window)
            ttl = window

        return count <= limit, count, max(ttl, 0)
    except Exception as e:
        logger.debug(f"Rate limit Redis error: {e}")
        return True, 0, 0  # Allow on Redis error


def _check_rate_limit_memory(key: str, limit: int, window: int) -> Tuple[bool, int, int]:
    """Check rate limit using in-memory sliding window."""
    _cleanup_window(key, window)
    _mem_counters[key].append(time.time())
    count = len(_mem_counters[key])
    return count <= limit, count, window


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
async def rate_limiter_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """FastAPI middleware that enforces per-IP rate limits via Redis."""
    path = request.url.path

    # Skip exempt paths
    for prefix in EXEMPT_PREFIXES:
        if path.startswith(prefix):
            return await call_next(request)

    client_ip = _get_client_ip(request)
    limit = _get_limit_for_path(path)
    window = RATE_LIMIT_WINDOW

    # Build rate-limit key
    prefix = os.environ.get("REDIS_KEY_PREFIX", "stockpulse:")
    rl_key = f"{prefix}rl:{client_ip}"

    # Try Redis first, fall back to in-memory
    allowed = True
    count = 0
    remaining_ttl = window

    try:
        from services.cache_service import get_cache_service
        cache_svc = get_cache_service()
        if cache_svc and cache_svc.is_redis_available and cache_svc._redis:
            allowed, count, remaining_ttl = _check_rate_limit_redis(
                cache_svc._redis, rl_key, limit, window
            )
        else:
            allowed, count, remaining_ttl = _check_rate_limit_memory(
                rl_key, limit, window
            )
    except Exception:
        allowed, count, remaining_ttl = _check_rate_limit_memory(
            rl_key, limit, window
        )

    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded. Please slow down.",
                "retry_after": remaining_ttl,
            },
            headers={
                "Retry-After": str(remaining_ttl),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(remaining_ttl),
            },
        )

    # Proceed with the request
    response = await call_next(request)

    # Add rate-limit headers to successful responses
    remaining = max(limit - count, 0)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(remaining_ttl)

    return response
