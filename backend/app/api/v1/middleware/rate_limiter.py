"""
Sliding-window rate limiter — FastAPI dependency.

When Redis is available (init_redis() succeeded at startup) the limiter uses
a Redis sorted-set per IP so all workers share the same counter.
When Redis is unavailable the limiter falls back to an in-memory deque per IP
(same behaviour as before Redis was added).

Usage:
    @router.post("/login")
    def login(request: Request, _: None = Depends(auth_limiter), ...):
        ...
"""

import os
import time
import threading
import uuid as _uuid
from collections import deque
from typing import Callable

from fastapi import Request, HTTPException


# ── Proxy for _windows so tests can pop() and also clean Redis keys ──────────

class _WindowStore:
    """
    Dict-like in-memory store for sliding-window deques.

    Tests import _windows and call _windows.pop(key, None) for cleanup.
    This class ensures that pop() also removes the corresponding Redis key so
    rate-limit counters don't bleed between test runs when Redis is configured.
    """

    def __init__(self):
        self._d: dict = {}

    # ── Dict interface used by the limiter internals ──────────────────────────

    def __contains__(self, key):
        return key in self._d

    def __getitem__(self, key):
        return self._d[key]

    def __setitem__(self, key, value):
        self._d[key] = value

    def items(self):
        return self._d.items()

    def __len__(self):
        return len(self._d)

    # ── pop() mirrors the delete to Redis so test cleanup works across workers ─

    def pop(self, key, default=None):
        self._d.pop(key, None)
        try:
            from app.core.redis_client import get_sync_redis
            r = get_sync_redis()
            if r:
                r.delete(f"rl:{key}")
        except Exception:
            pass
        return default


_lock     = threading.Lock()
_windows  = _WindowStore()

_CLEANUP_EVERY = 300
_last_cleanup  = -_CLEANUP_EVERY

_TRUSTED_PROXY = os.getenv("TRUSTED_PROXY", "0").strip() == "1"


def _get_client_ip(request: Request) -> str:
    if _TRUSTED_PROXY:
        real_ip = request.headers.get("X-Real-IP", "").strip()
        if real_ip:
            return real_ip
    return request.client.host if request.client else "unknown"


def _make_limiter(max_calls: int, window_secs: int) -> Callable:
    """Return a FastAPI dependency that enforces max_calls per window_secs per IP."""

    async def _check(request: Request) -> None:
        global _last_cleanup
        ip  = _get_client_ip(request)
        key = f"{request.url.path}:{ip}"
        now = time.time()

        # ── Redis path — shared across all workers ────────────────────────────
        try:
            from app.core.redis_client import get_sync_redis
            r = get_sync_redis()
        except Exception:
            r = None

        if r is not None:
            redis_key = f"rl:{key}"
            member    = f"{now}:{_uuid.uuid4().hex[:8]}"
            cutoff    = now - window_secs
            try:
                pipe = r.pipeline()
                pipe.zremrangebyscore(redis_key, "-inf", cutoff)   # drop old entries
                pipe.zadd(redis_key, {member: now})                 # record this request
                pipe.zcard(redis_key)                               # count active entries
                pipe.expire(redis_key, window_secs + 5)            # TTL = window + buffer
                results = pipe.execute()
                count   = results[2]

                if count > max_calls:
                    r.zrem(redis_key, member)   # undo the entry we just added
                    raise HTTPException(
                        status_code=429,
                        detail=f"Too many requests. Limit: {max_calls} per {window_secs}s.",
                        headers={"Retry-After": str(window_secs)},
                    )
                return
            except HTTPException:
                raise
            except Exception:
                pass   # Redis error → fall through to in-memory

        # ── In-memory path (no Redis or Redis error) ──────────────────────────
        cutoff = now - window_secs

        with _lock:
            if key not in _windows:
                _windows[key] = deque()
            dq = _windows[key]

            while dq and dq[0] < cutoff:
                dq.popleft()

            if len(dq) >= max_calls:
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many requests. Limit: {max_calls} per {window_secs}s.",
                    headers={"Retry-After": str(window_secs)},
                )

            dq.append(now)

            if now - _last_cleanup > _CLEANUP_EVERY:
                _last_cleanup = now
                stale = [k for k, q in list(_windows.items()) if not q]
                for k in stale:
                    _windows.pop(k, None)

    return _check


# ── Named limiters ────────────────────────────────────────────────────────────
auth_limiter       = _make_limiter(max_calls=10,  window_secs=60)
chat_limiter       = _make_limiter(max_calls=30,  window_secs=60)
upload_limiter     = _make_limiter(max_calls=20,  window_secs=60)
knowledge_limiter  = _make_limiter(max_calls=20,  window_secs=60)
admin_limiter      = _make_limiter(max_calls=20,  window_secs=60)
