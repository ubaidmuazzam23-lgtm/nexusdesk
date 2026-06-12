# app/core/redis_client.py
#
# Single source of truth for Redis connectivity.
# Call init_redis() once at startup (main.py lifespan).
# After that, get_sync_redis() / get_async_redis() return the clients
# or None if Redis was not available at startup.
#
# All callers must handle None gracefully — never assume Redis is up.

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_sync: Optional["redis.Redis"] = None       # type: ignore[name-defined]
_async: Optional["aioredis.Redis"] = None   # type: ignore[name-defined]


def init_redis(url: str) -> bool:
    """
    Try to connect to Redis at the given URL.
    Returns True if the connection was established, False otherwise.
    Safe to call multiple times; only the first successful call has effect.
    """
    global _sync, _async

    if not url:
        logger.info("[Redis] No REDIS_URL configured — in-memory mode")
        return False

    try:
        import redis as _redis_lib
        import redis.asyncio as _aioredis_lib

        client = _redis_lib.from_url(
            url,
            socket_connect_timeout=3,
            socket_timeout=3,
            decode_responses=True,
            max_connections=50,   # cap simultaneous connections to avoid overwhelming Upstash
        )
        client.ping()                          # fail fast if unreachable
        _sync = client
        _async = _aioredis_lib.from_url(url, decode_responses=True)

        display = url.split("@")[-1] if "@" in url else url
        logger.info("[Redis] Connected to %s — multi-worker session sharing enabled", display)
        return True

    except Exception as exc:
        logger.info("[Redis] Not available (%s) — in-memory fallback active", exc)
        _sync = None
        _async = None
        return False


def get_sync_redis():
    """Return the sync Redis client, or None if Redis is unavailable."""
    return _sync


def get_async_redis():
    """Return the async Redis client, or None if Redis is unavailable."""
    return _async


def is_redis_available() -> bool:
    return _sync is not None
