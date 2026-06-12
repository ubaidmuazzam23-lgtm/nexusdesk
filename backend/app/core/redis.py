# Thin wrapper — delegates to redis_client.py which handles lazy init.
# Kept for backward compatibility; prefer importing from redis_client directly.

from app.core.redis_client import get_async_redis


async def get_redis():
    """Return the async Redis client or None if Redis is unavailable."""
    return get_async_redis()
