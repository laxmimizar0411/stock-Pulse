"""
Integration Tests for Redis-dependent features in StockPulse.

Tests:
  1. Alert pipeline: trigger_alert → Redis queue → consumer dispatch
  2. Rate limiter: sliding window counter via Redis and in-memory fallback
  3. Pub/Sub: price publish → subscribe round-trip
  4. Health check reconnect callback

Run:
    python test_redis_integration.py
"""

import asyncio
import json
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("test_redis_integration")

PASS = 0
FAIL = 0


def ok(name):
    global PASS
    PASS += 1
    logger.info(f"  PASS  {name}")


def fail(name, reason=""):
    global FAIL
    FAIL += 1
    logger.error(f"  FAIL  {name}: {reason}")


# ============================================================
# 1. Rate Limiter Tests
# ============================================================
def test_rate_limiter_memory():
    """Test in-memory sliding window rate limiter."""
    from services.rate_limiter import _check_rate_limit_memory, _mem_counters

    key = "test:rl:memory"
    _mem_counters.pop(key, None)

    # Should allow up to 5 requests
    for i in range(5):
        allowed, count, _ = _check_rate_limit_memory(key, limit=5, window=60)
        if not allowed:
            fail("rl_memory_allow", f"Request {i+1} should be allowed")
            return

    # 6th should be blocked
    allowed, count, _ = _check_rate_limit_memory(key, limit=5, window=60)
    if allowed:
        fail("rl_memory_block", "6th request should be blocked")
        return

    _mem_counters.pop(key, None)
    ok("rate_limiter_memory_window")


def test_rate_limiter_redis():
    """Test Redis-backed rate limiter (skipped if Redis unavailable)."""
    try:
        import redis as redis_lib
    except ImportError:
        logger.info("  SKIP  rate_limiter_redis (redis not installed)")
        return

    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    try:
        r = redis_lib.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        r.ping()
    except Exception:
        logger.info("  SKIP  rate_limiter_redis (Redis not reachable)")
        return

    from services.rate_limiter import _check_rate_limit_redis

    key = "stockpulse:test:rl:redis"
    r.delete(key)

    for i in range(3):
        allowed, count, ttl = _check_rate_limit_redis(r, key, limit=3, window=10)
        assert allowed, f"Request {i+1} should be allowed"

    allowed, count, ttl = _check_rate_limit_redis(r, key, limit=3, window=10)
    if allowed:
        fail("rl_redis_block", "4th request should be blocked")
    else:
        ok("rate_limiter_redis_window")

    r.delete(key)


# ============================================================
# 2. Alert Queue Round-Trip
# ============================================================
def test_alert_queue_roundtrip():
    """Test publish_alert → BLPOP retrieval."""
    try:
        import redis as redis_lib
    except ImportError:
        logger.info("  SKIP  alert_queue_roundtrip (redis not installed)")
        return

    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    try:
        r = redis_lib.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        r.ping()
    except Exception:
        logger.info("  SKIP  alert_queue_roundtrip (Redis not reachable)")
        return

    from services.cache_service import CacheService

    svc = CacheService(redis_url=url)
    svc.initialize()

    if not svc.is_redis_available:
        logger.info("  SKIP  alert_queue_roundtrip (CacheService fallback)")
        return

    queue_key = f"{os.environ.get('REDIS_KEY_PREFIX', 'stockpulse:')}alert_queue"

    # Drain any existing items
    while r.lpop(queue_key):
        pass

    alert_data = {
        "type": "price_above",
        "alert_id": "test_alert_001",
        "symbol": "RELIANCE",
        "message": "Price above 2500",
        "priority": "high",
        "triggered_at": "2026-03-13T00:00:00Z",
    }

    result = svc.publish_alert(alert_data)
    assert result, "publish_alert should return True"

    # BLPOP the item
    item = r.blpop(queue_key, timeout=2)
    if item is None:
        fail("alert_queue_roundtrip", "No item received from BLPOP")
        svc.close()
        return

    _key, raw = item
    parsed = json.loads(raw)
    if parsed.get("alert_id") != "test_alert_001":
        fail("alert_queue_roundtrip", f"Wrong alert_id: {parsed.get('alert_id')}")
    elif parsed.get("symbol") != "RELIANCE":
        fail("alert_queue_roundtrip", f"Wrong symbol: {parsed.get('symbol')}")
    else:
        ok("alert_queue_roundtrip")

    svc.close()


# ============================================================
# 3. Pub/Sub Price Round-Trip
# ============================================================
def test_pubsub_price_roundtrip():
    """Test publish_price → subscriber receives message."""
    try:
        import redis as redis_lib
    except ImportError:
        logger.info("  SKIP  pubsub_price_roundtrip (redis not installed)")
        return

    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    try:
        r = redis_lib.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        r.ping()
    except Exception:
        logger.info("  SKIP  pubsub_price_roundtrip (Redis not reachable)")
        return

    from services.cache_service import CacheService

    svc = CacheService(redis_url=url)
    svc.initialize()

    if not svc.is_redis_available:
        logger.info("  SKIP  pubsub_price_roundtrip (CacheService fallback)")
        return

    prefix = os.environ.get("REDIS_KEY_PREFIX", "stockpulse:")
    channel = f"{prefix}channel:prices"

    # Subscribe with a separate connection
    sub = redis_lib.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
    ps = sub.pubsub()
    ps.subscribe(channel)

    # Wait for subscription confirmation
    msg = ps.get_message(timeout=2)

    # Publish
    svc.publish_price("TCS", {"price": 3500, "change": 50})

    # Receive
    received = ps.get_message(timeout=3)
    if received is None:
        fail("pubsub_price_roundtrip", "No message received")
    elif received["type"] != "message":
        fail("pubsub_price_roundtrip", f"Wrong message type: {received['type']}")
    else:
        data = json.loads(received["data"])
        if data.get("symbol") == "TCS" and data.get("price") == 3500:
            ok("pubsub_price_roundtrip")
        else:
            fail("pubsub_price_roundtrip", f"Unexpected data: {data}")

    ps.unsubscribe()
    ps.close()
    sub.close()
    svc.close()


# ============================================================
# 4. Health Check On-Reconnect Callback
# ============================================================
def test_health_check_callback():
    """Verify the on_reconnect callback parameter is accepted."""
    from services.cache_service import start_health_check, stop_health_check
    import inspect

    sig = inspect.signature(start_health_check)
    if "on_reconnect" in sig.parameters:
        ok("health_check_on_reconnect_param")
    else:
        fail("health_check_on_reconnect_param", "Missing on_reconnect parameter")


# ============================================================
# 5. TLS Config Support
# ============================================================
def test_tls_config():
    """Verify CacheService reads TLS env vars."""
    from services.cache_service import CacheService

    os.environ["REDIS_SSL_CA_CERTS"] = "/tmp/test-ca.pem"
    svc = CacheService(redis_url="redis://localhost:6379")
    if svc._ssl_ca_certs == "/tmp/test-ca.pem":
        ok("tls_config_env_read")
    else:
        fail("tls_config_env_read", f"Expected /tmp/test-ca.pem, got {svc._ssl_ca_certs}")
    del os.environ["REDIS_SSL_CA_CERTS"]


# ============================================================
# Runner
# ============================================================
def main():
    logger.info("=" * 60)
    logger.info("  StockPulse Redis Integration Tests")
    logger.info("=" * 60)

    test_rate_limiter_memory()
    test_rate_limiter_redis()
    test_alert_queue_roundtrip()
    test_pubsub_price_roundtrip()
    test_health_check_callback()
    test_tls_config()

    logger.info("=" * 60)
    logger.info(f"  Results: {PASS} passed, {FAIL} failed")
    logger.info("=" * 60)

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
