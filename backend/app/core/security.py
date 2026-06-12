# File: backend/app/core/security.py

import uuid
import threading
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT denylist ──────────────────────────────────────────────────────────────
#
# In-memory store (single-worker fallback): jti → expiry_epoch
# Redis store (multi-worker): key "jti_deny:{jti}" with TTL = token remaining lifetime
#
# When Redis is available all workers share the denylist automatically.
# When Redis is unavailable each worker maintains its own in-memory set;
# tokens from worker A are still valid on worker B until they expire naturally —
# this is acceptable in the single-worker configuration.

_denylist: dict[str, float] = {}
_denylist_lock = threading.Lock()


def _get_redis():
    try:
        from app.core.redis_client import get_sync_redis
        return get_sync_redis()
    except Exception:
        return None


def _cleanup_denylist() -> None:
    """Remove expired entries from the in-memory denylist (called under lock)."""
    now = datetime.utcnow().timestamp()
    expired = [k for k, v in list(_denylist.items()) if v < now]
    for k in expired:
        _denylist.pop(k, None)


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access", "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        jti = payload.get("jti")
        if jti:
            r = _get_redis()
            if r is not None:
                try:
                    if r.exists(f"jti_deny:{jti}"):
                        return None   # token has been invalidated (logout)
                except Exception:
                    # Redis error — fall back to in-memory check
                    with _denylist_lock:
                        if jti in _denylist:
                            return None
            else:
                with _denylist_lock:
                    if jti in _denylist:
                        return None
        return payload
    except JWTError:
        return None


def invalidate_token(token: str) -> None:
    """Add a token's JTI to the denylist so it cannot be used after logout."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        jti = payload.get("jti")
        exp = payload.get("exp")
        if not jti or not exp:
            return

        r = _get_redis()
        if r is not None:
            try:
                ttl = max(1, int(float(exp) - datetime.utcnow().timestamp()))
                r.setex(f"jti_deny:{jti}", ttl, "1")
                return
            except Exception:
                pass   # Redis write failed — fall through to in-memory

        # In-memory fallback
        with _denylist_lock:
            _denylist[jti] = float(exp)
            _cleanup_denylist()

    except JWTError:
        pass   # already invalid token — nothing to do
