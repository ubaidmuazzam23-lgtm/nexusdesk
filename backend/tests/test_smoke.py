"""
Smoke tests for critical paths.
Run from backend/: PYTHONPATH=. pytest tests/test_smoke.py -v
"""

import os
import sys
import threading
import time
import uuid

import pytest

# Set env vars before any app import
os.environ.setdefault("DATABASE_URL",    "postgresql://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY",      "test-secret-key-minimum-32chars!!")
os.environ.setdefault("JWT_SECRET_KEY",  "test-jwt-secret-minimum-32chars!!")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy-key")
os.environ.setdefault("SMTP_HOST",       "localhost")
os.environ.setdefault("SMTP_PORT",       "25")
os.environ.setdefault("SMTP_USER",       "test@test.com")
os.environ.setdefault("SMTP_PASSWORD",   "testpass")
os.environ.setdefault("FRONTEND_URL",    "http://localhost:3000")
os.environ.setdefault("AI_SERVICES_URL", "http://localhost:8001")


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 1+2: Module imports + FastAPI app startup
# ─────────────────────────────────────────────────────────────────────────────

def test_import_core_config():
    from app.core.config import Settings
    # Verify the code *defaults* are production-safe.
    # A local .env file may legitimately override these for dev — that's fine.
    import inspect
    fields = Settings.model_fields
    assert fields["DEBUG"].default is False,        "Code default for DEBUG must be False"
    assert fields["ENVIRONMENT"].default == "production", "Code default for ENVIRONMENT must be 'production'"


def test_import_core_security():
    from app.core.security import hash_password, verify_password, create_access_token
    assert callable(hash_password)


def test_import_schemas():
    from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
    from app.schemas.auth import LoginRequest, LoginResponse


def test_import_middleware():
    from app.api.v1.middleware.rate_limiter import (
        auth_limiter, chat_limiter, upload_limiter, knowledge_limiter,
    )
    assert callable(auth_limiter)
    assert callable(knowledge_limiter)


def test_import_services_auth():
    from app.services.auth_service import forgot_password


def test_import_services_chat():
    from app.services.chat_service import (
        _get_session, _call_claude, _should_count_attempt, process_message,
    )


def test_import_services_knowledge():
    from app.services.knowledge_service import get_rag_context, _get_anthropic_client


def test_import_services_slack():
    from app.services.slack_service import _get_slack_session, _evict_slack_sessions


def test_import_services_slack_bridge():
    from app.services.slack_chat_bridge import (
        _get_cl, _get_or_create_session, _evict_slack_dicts, _reset_session,
    )


def test_app_startup():
    from app.main import app
    routes = [r.path for r in app.routes]
    assert "/health" in routes
    assert "/" in routes


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 6: chat_service._get_session
# ─────────────────────────────────────────────────────────────────────────────

def test_get_session_creates_with_defaults():
    from app.services.chat_service import _get_session, _sessions
    sid = f"test-{uuid.uuid4()}"
    session = _get_session(sid)

    assert session["flow_step"]      == "broken"
    assert session["domain"]         == "networking"
    assert session["severity"]       == "medium"
    assert session["messages"]       == []
    assert session["solve_attempts"] == 0
    assert session["is_networking"]  is True
    assert session["problem"]        == ""
    assert "_last_accessed" in session

    # Repeated call returns same session
    session2 = _get_session(sid)
    assert session2 is session

    # Cleanup
    _sessions.pop(sid, None)


def test_get_session_updates_last_accessed():
    from app.services.chat_service import _get_session, _sessions
    sid = f"test-{uuid.uuid4()}"
    s1 = _get_session(sid)
    t1 = s1["_last_accessed"]
    time.sleep(0.01)
    _get_session(sid)
    assert s1["_last_accessed"] >= t1
    _sessions.pop(sid, None)


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 7: chat_service._call_claude — handles API error gracefully via mock
# ─────────────────────────────────────────────────────────────────────────────

def test_call_claude_handles_timeout(monkeypatch):
    """_call_claude should propagate exceptions (callers wrap in try/except)."""
    import app.services.chat_service as cs

    class _FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise TimeoutError("Simulated Anthropic timeout")

    monkeypatch.setattr(cs, "_client", _FakeClient())

    session = {
        "messages": [{"role": "user", "content": "BGP down"}],
        "domain": "networking", "severity": "medium",
    }
    with pytest.raises(TimeoutError):
        cs._call_claude(session, "You are a support bot.")


def test_start_ai_analysis_recovers_from_api_error(monkeypatch):
    """_start_ai_analysis must return a response (not raise) when Claude is down."""
    import app.services.chat_service as cs

    class _FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise ConnectionError("Anthropic unreachable")

    monkeypatch.setattr(cs, "_client", _FakeClient())

    sid = f"test-{uuid.uuid4()}"
    session = cs._get_session(sid)
    session["problem"]     = "BGP session dropped"
    session["flow_step"]   = "ai_analysis"
    session["flow_origin"] = "broken"

    result = cs._start_ai_analysis(session, sid)
    assert result is not None
    assert "try again" in result.reply.lower() or "trouble" in result.reply.lower()
    assert result.session_id == sid

    cs._sessions.pop(sid, None)


def test_continue_ai_analysis_recovers_from_api_error(monkeypatch):
    """_continue_ai_analysis must return a response when Claude is down."""
    import app.services.chat_service as cs

    class _FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise ConnectionError("Anthropic unreachable")

    monkeypatch.setattr(cs, "_client", _FakeClient())

    sid = f"test-{uuid.uuid4()}"
    session = cs._get_session(sid)
    session["problem"]     = "DNS not resolving"
    session["flow_step"]   = "ai_analysis"
    session["flow_origin"] = "broken"
    session["messages"]    = [{"role": "user", "content": "DNS not resolving"}]

    result = cs._continue_ai_analysis(session, sid, "still broken")
    assert result is not None
    assert result.session_id == sid

    cs._sessions.pop(sid, None)


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 8: chat_service._should_count_attempt
# ─────────────────────────────────────────────────────────────────────────────

def test_should_count_attempt_screenshot_turn_always_false(monkeypatch):
    import app.services.chat_service as cs

    # Even if Claude would say YES, screenshot turn must return False
    class _AlwaysYes:
        class messages:
            @staticmethod
            def create(**kwargs):
                class R:
                    class content:
                        pass
                r = R()
                r.content = [type("C", (), {"text": "YES"})()]
                return r

    monkeypatch.setattr(cs, "_client", _AlwaysYes())
    result = cs._should_count_attempt("run ping 8.8.8.8", is_screenshot_turn=True)
    assert result is False


def test_should_count_attempt_returns_false_on_api_error(monkeypatch):
    import app.services.chat_service as cs

    class _ErrorClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("API down")

    monkeypatch.setattr(cs, "_client", _ErrorClient())
    result = cs._should_count_attempt("run ping 8.8.8.8", is_screenshot_turn=False)
    assert result is False   # fail-safe: don't count on error


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 9: process_message flow routing
# ─────────────────────────────────────────────────────────────────────────────

def test_process_message_broken_step_routes_to_handle_broken(monkeypatch):
    import app.services.chat_service as cs
    from app.schemas.chat import ChatMessageRequest

    calls = []

    def _fake_handle_broken(session, sid, msg):
        calls.append(("broken", msg))
        return cs._make_response(sid, session, "Are you having issues?")

    monkeypatch.setattr(cs, "_handle_broken", _fake_handle_broken)

    sid = f"test-{uuid.uuid4()}"
    cs._sessions.pop(sid, None)  # ensure fresh session

    req  = ChatMessageRequest(message="My network is down", session_id=sid)
    resp = cs.process_message(None, None, req)

    assert len(calls) == 1
    assert calls[0][0] == "broken"
    assert calls[0][1] == "My network is down"

    cs._sessions.pop(sid, None)


def test_process_message_mid_check_step_uses_claude(monkeypatch):
    import app.services.chat_service as cs
    from app.schemas.chat import ChatMessageRequest

    class _FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                class R: pass
                r = R()
                r.content = [type("C", (), {"text": "YES"})()]
                return r

    monkeypatch.setattr(cs, "_client", _FakeClient())

    sid = f"test-{uuid.uuid4()}"
    session = cs._get_session(sid)
    session["flow_step"] = "mid_check"

    req  = ChatMessageRequest(message="escalate", session_id=sid)
    resp = cs.process_message(None, None, req)
    assert resp is not None

    cs._sessions.pop(sid, None)


def test_process_message_unknown_step_resets_to_broken(monkeypatch):
    """Unknown flow_step should reset to 'broken' and call _handle_broken."""
    import app.services.chat_service as cs
    from app.schemas.chat import ChatMessageRequest

    calls = []

    def _fake_handle_broken(session, sid, msg):
        calls.append("broken")
        return cs._make_response(sid, session, "How can I help?")

    monkeypatch.setattr(cs, "_handle_broken", _fake_handle_broken)

    sid = f"test-{uuid.uuid4()}"
    session = cs._get_session(sid)
    session["flow_step"] = "nonexistent_step_xyz"

    req  = ChatMessageRequest(message="hello", session_id=sid)
    resp = cs.process_message(None, None, req)

    assert "broken" in calls

    cs._sessions.pop(sid, None)


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 10: knowledge_service.get_rag_context with empty collection
# ─────────────────────────────────────────────────────────────────────────────

def test_get_rag_context_empty_collection(monkeypatch):
    import app.services.knowledge_service as ks

    class _FakeCollection:
        def count(self):
            return 0

    monkeypatch.setattr(ks, "_collection", _FakeCollection())

    result = ks.get_rag_context("BGP session dropped", domain="networking")
    assert result == ""


def test_get_rag_context_exception_returns_empty(monkeypatch):
    import app.services.knowledge_service as ks

    def _bad_collection():
        raise RuntimeError("ChromaDB unavailable")

    monkeypatch.setattr(ks, "_get_collection", _bad_collection)

    result = ks.get_rag_context("test query")
    assert result == ""


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 11: rate_limiter blocks after limit exceeded
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limiter_blocks_after_limit():
    from app.api.v1.middleware.rate_limiter import _make_limiter, _windows
    from fastapi import HTTPException

    limiter = _make_limiter(max_calls=3, window_secs=60)

    class _FakeClient:
        host = "192.0.2.1"  # TEST-NET — never a real IP

    class _FakeURL:
        path = "/test/rate-limit-check"

    class _FakeRequest:
        client = _FakeClient()
        url    = _FakeURL()

    req = _FakeRequest()

    # Clear any previous state for this key
    key = f"{req.url.path}:{req.client.host}"
    _windows.pop(key, None)

    # First 3 calls should pass
    for _ in range(3):
        await limiter(req)

    # 4th call must raise 429
    with pytest.raises(HTTPException) as exc_info:
        await limiter(req)

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers

    # Cleanup
    _windows.pop(key, None)


@pytest.mark.asyncio
async def test_rate_limiter_allows_after_window_expires():
    from app.api.v1.middleware.rate_limiter import _make_limiter, _windows
    from fastapi import HTTPException

    limiter = _make_limiter(max_calls=2, window_secs=1)

    class _FakeClient:
        host = "192.0.2.2"

    class _FakeURL:
        path = "/test/rate-window-expire"

    class _FakeRequest:
        client = _FakeClient()
        url    = _FakeURL()

    req = _FakeRequest()
    key = f"{req.url.path}:{req.client.host}"
    _windows.pop(key, None)

    # Fill up
    await limiter(req)
    await limiter(req)

    # Should be blocked now
    with pytest.raises(HTTPException):
        await limiter(req)

    # Wait for window to expire
    time.sleep(1.1)

    # Should pass again
    await limiter(req)

    _windows.pop(key, None)


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 12: auth_service.forgot_password generic message
# ─────────────────────────────────────────────────────────────────────────────

GENERIC_MSG = "If an account exists for that email address, a temporary password has been sent."


def test_forgot_password_nonexistent_email_returns_generic():
    from app.services.auth_service import forgot_password
    from app.schemas.auth import ForgotPasswordRequest

    class _FakeDB:
        def query(self, *a): return self
        def filter(self, *a): return self
        def first(self): return None  # user not found

    result = forgot_password(_FakeDB(), ForgotPasswordRequest(email="nobody@example.com"))
    assert result["message"] == GENERIC_MSG


def test_forgot_password_inactive_user_returns_generic():
    from app.services.auth_service import forgot_password
    from app.schemas.auth import ForgotPasswordRequest

    class _InactiveUser:
        email     = "inactive@example.com"
        full_name = "Inactive"
        is_active = False

    class _FakeDB:
        def query(self, *a): return self
        def filter(self, *a): return self
        def first(self): return _InactiveUser()

    result = forgot_password(_FakeDB(), ForgotPasswordRequest(email="inactive@example.com"))
    assert result["message"] == GENERIC_MSG


def test_forgot_password_existing_user_returns_same_generic(monkeypatch):
    """Existing active user also gets the exact same generic message — no enumeration."""
    from app.services.auth_service import forgot_password
    from app.schemas.auth import ForgotPasswordRequest
    import threading as _threading

    class _ActiveUser:
        email            = "real@example.com"
        full_name        = "Real User"
        is_active        = True
        hashed_password  = "old_hash"

    class _FakeDB:
        def query(self, *a): return self
        def filter(self, *a): return self
        def first(self): return _ActiveUser()
        def commit(self): pass

    # Suppress the email-sending thread
    sent = []
    monkeypatch.setattr(_threading, "Thread", lambda target, args, daemon: type(
        "T", (), {"start": lambda self: sent.append(args[0])}
    )())

    result = forgot_password(_FakeDB(), ForgotPasswordRequest(email="real@example.com"))
    assert result["message"] == GENERIC_MSG


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 13: health endpoint returns degraded when DB is down
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_returns_degraded_on_db_failure(monkeypatch):
    import app.main as main_module

    def _bad_get_db():
        raise Exception("Connection refused")

    monkeypatch.setattr(main_module, "get_db", _bad_get_db)

    result = await main_module.health()
    assert result["status"] == "degraded"
    assert result["db"] is False


@pytest.mark.asyncio
async def test_health_returns_healthy_on_db_success(monkeypatch):
    import app.main as main_module

    class _FakeDB:
        def execute(self, *a): return None

    def _good_get_db():
        yield _FakeDB()

    monkeypatch.setattr(main_module, "get_db", _good_get_db)

    result = await main_module.health()
    assert result["status"] == "healthy"
    assert result["db"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Eviction smoke tests (Check 6d — slack session caps)
# ─────────────────────────────────────────────────────────────────────────────

def test_slack_service_eviction_fires_at_cap():
    from app.services.slack_service import _slack_sessions, _get_slack_session, _SLACK_SESSIONS_MAX

    _slack_sessions.clear()

    # Fill to cap
    for i in range(_SLACK_SESSIONS_MAX):
        _slack_sessions[f"U{i:06d}"] = {"session_id": f"s{i}"}

    assert len(_slack_sessions) == _SLACK_SESSIONS_MAX

    # One more triggers eviction
    _get_slack_session("U_new_trigger")

    # Should be below cap now (evicted 10%)
    assert len(_slack_sessions) < _SLACK_SESSIONS_MAX

    _slack_sessions.clear()


def test_slack_bridge_eviction_fires_at_cap():
    from app.services.slack_chat_bridge import (
        _slack_to_session, _SLACK_SESSION_MAX, _get_or_create_session,
    )

    _slack_to_session.clear()

    for i in range(_SLACK_SESSION_MAX):
        _slack_to_session[f"U{i:06d}"] = f"sess_{i}"

    assert len(_slack_to_session) == _SLACK_SESSION_MAX

    _get_or_create_session("U_new_trigger")

    assert len(_slack_to_session) < _SLACK_SESSION_MAX

    _slack_to_session.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Schema validation (edge cases)
# ─────────────────────────────────────────────────────────────────────────────

def test_chat_message_too_short_rejected():
    from pydantic import ValidationError
    from app.schemas.chat import ChatMessageRequest

    with pytest.raises(ValidationError):
        ChatMessageRequest(message="")


def test_chat_message_too_long_rejected():
    from pydantic import ValidationError
    from app.schemas.chat import ChatMessageRequest

    with pytest.raises(ValidationError):
        ChatMessageRequest(message="x" * 4001)


def test_chat_message_valid():
    from app.schemas.chat import ChatMessageRequest
    req = ChatMessageRequest(message="BGP session dropped", session_id="abc")
    assert req.message == "BGP session dropped"
