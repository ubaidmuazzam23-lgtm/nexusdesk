"""
Scenario tests for ticket-raising logic.
Run: PYTHONPATH=. pytest tests/test_ticket_logic.py -v
Tests run without a real DB or Anthropic API — everything is mocked.
"""

import os, uuid
os.environ.setdefault("DATABASE_URL",     "postgresql://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY",       "test-secret-key-minimum-32chars!!")
os.environ.setdefault("JWT_SECRET_KEY",   "test-jwt-secret-minimum-32chars!!")
os.environ.setdefault("ANTHROPIC_API_KEY","sk-ant-test-dummy-key")
os.environ.setdefault("SMTP_HOST",        "localhost")
os.environ.setdefault("SMTP_PORT",        "25")
os.environ.setdefault("SMTP_USER",        "test@test.com")
os.environ.setdefault("SMTP_PASSWORD",    "testpass")
os.environ.setdefault("FRONTEND_URL",     "http://localhost:3000")
os.environ.setdefault("AI_SERVICES_URL",  "http://localhost:8001")


# ── Fake Claude client ────────────────────────────────────────────────────────

def _fake_response(text: str):
    class _R:
        content = [type("C", (), {"text": text})()]
    return _R()


class _NotResolved:
    """Claude always says issue NOT resolved, attempt IS a real troubleshooting step."""
    class messages:
        @staticmethod
        def create(**kwargs):
            prompt = kwargs.get("messages", [{}])[0].get("content", "")
            if "Is the user confirming" in prompt:
                return _fake_response("NO")
            if "Does this message say they want to raise" in prompt:
                return _fake_response("NO")
            if "Does the following IT support reply give the user a troubleshooting step" in prompt:
                return _fake_response("YES")
            # Default: hint / Claude main reply
            return _fake_response("Step 2: Check the logs.")


class _WantsTicket:
    """Claude says user DOES want to raise a ticket."""
    class messages:
        @staticmethod
        def create(**kwargs):
            prompt = kwargs.get("messages", [{}])[0].get("content", "")
            if "Does this message say they want to raise" in prompt:
                return _fake_response("YES")
            if "Is the user confirming" in prompt:
                return _fake_response("NO")
            return _fake_response("YES")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_session(flow_origin="broken", attempts=0):
    import app.services.chat_service as cs
    sid = f"test-{uuid.uuid4()}"
    session = cs._get_session(sid)
    session["flow_step"]      = "ai_analysis"
    session["flow_origin"]    = flow_origin
    session["problem"]        = "DNS not resolving"
    session["rag_context"]    = ""
    session["solve_attempts"] = attempts
    session["messages"]       = [{"role": "user", "content": "DNS not resolving"}]
    if flow_origin == "major_incident":
        session["severity"] = "critical"
    return sid, session


def _pump(sid, session, n_turns, monkeypatch, fake_client=None):
    """Run n_turns of _continue_ai_analysis, return last result."""
    import app.services.chat_service as cs
    if fake_client:
        monkeypatch.setattr(cs, "_client", fake_client())
    result = None
    for _ in range(n_turns):
        result = cs._continue_ai_analysis(session, sid, "still broken")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 1 — Normal broken, no runbook
# Mid-check fires at attempt 3 (no runbook only)
# ─────────────────────────────────────────────────────────────────────────────

def test_broken_midcheck_fires_at_attempt_3(monkeypatch):
    import app.services.chat_service as cs
    monkeypatch.setattr(cs, "_client", _NotResolved())
    monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

    # Checks use pre-call stored n; mid-check fires when n >= 3 at call start
    sid, session = _make_session("broken", attempts=3)
    result = cs._continue_ai_analysis(session, sid, "still broken")

    assert session["flow_step"] == "mid_check", f"Expected mid_check, got {session['flow_step']}"
    assert session.get("mid_check_done") is True
    assert result.can_escalate is False  # mid-check never auto-escalates
    cs._sessions.pop(sid, None)


def test_broken_midcheck_raise_sets_user_confirmed(monkeypatch):
    """User clicks 'Raise Ticket' at mid-check → user_confirmed_ticket=True, can_escalate=True."""
    import app.services.chat_service as cs
    from app.schemas.chat import ChatMessageRequest

    monkeypatch.setattr(cs, "_client", _WantsTicket())
    monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

    sid, session = _make_session("broken", attempts=2)
    session["flow_step"]    = "mid_check"
    session["mid_check_done"] = True

    req    = ChatMessageRequest(message="escalate", session_id=sid)
    result = cs.process_message(None, None, req)

    assert result.can_escalate is True
    assert session.get("user_confirmed_ticket") is True, "user_confirmed_ticket must be True"
    assert session["flow_step"] == "escalate_ready"
    cs._sessions.pop(sid, None)


def test_broken_midcheck_continue_resumes_ai(monkeypatch):
    """User clicks 'Continue' at mid-check → ai_analysis continues, no ticket."""
    import app.services.chat_service as cs
    from app.schemas.chat import ChatMessageRequest

    class _Continue:
        class messages:
            @staticmethod
            def create(**kwargs):
                prompt = kwargs.get("messages", [{}])[0].get("content", "")
                if "Does this message say they want to raise" in prompt:
                    return _fake_response("NO")
                if "Is the user confirming" in prompt:
                    return _fake_response("NO")
                return _fake_response("Step 3: Try flushing DNS cache.")

    monkeypatch.setattr(cs, "_client", _Continue())
    monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

    sid, session = _make_session("broken", attempts=2)
    session["flow_step"]      = "mid_check"
    session["mid_check_done"] = True

    req    = ChatMessageRequest(message="continue", session_id=sid)
    result = cs.process_message(None, None, req)

    assert result.can_escalate is False
    assert session.get("user_confirmed_ticket") is not True
    assert session["flow_step"] == "ai_analysis"
    cs._sessions.pop(sid, None)


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 2 — Normal broken exhausted at attempt 6
# Must ask for confirmation (can_escalate=True, user_confirmed_ticket NOT set)
# ─────────────────────────────────────────────────────────────────────────────

def test_broken_exhausted_at_6_asks_confirmation(monkeypatch):
    """After 6 attempts: message says 'please confirm', can_escalate=True, no auto-flag."""
    import app.services.chat_service as cs
    monkeypatch.setattr(cs, "_client", _NotResolved())
    monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

    # Checks use pre-call stored n; exhaustion fires when n >= 6 at call start
    sid, session = _make_session("broken", attempts=6)
    session["mid_check_done"] = True  # mid-check already done

    result = cs._continue_ai_analysis(session, sid, "still broken")

    assert result.can_escalate is True
    assert session["flow_step"] == "escalate_ready"
    assert "confirm" in result.reply.lower() or "exhausted" in result.reply.lower(), \
        f"Expected confirmation message, got: {result.reply}"
    # user_confirmed_ticket must NOT be set — bridge shows Yes/No buttons
    assert not session.get("user_confirmed_ticket"), \
        "user_confirmed_ticket must NOT be set at exhaustion — bridge needs to confirm"
    cs._sessions.pop(sid, None)


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 3 — Major incident: auto-raise after 3 attempts
# ─────────────────────────────────────────────────────────────────────────────

def test_major_incident_autoraise_at_3(monkeypatch):
    """Major incident at n=4: immediately raises, user_confirmed_ticket=True."""
    import app.services.chat_service as cs
    monkeypatch.setattr(cs, "_client", _NotResolved())
    monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

    # Checks use pre-call stored n; major incident fires when n >= 4 at call start
    sid, session = _make_session("major_incident", attempts=4)

    result = cs._continue_ai_analysis(session, sid, "still broken")

    assert result.can_escalate is True
    assert session.get("user_confirmed_ticket") is True, \
        "Major incident must set user_confirmed_ticket so bridge skips confirmation"
    assert session["flow_step"] == "escalate_ready"
    assert session["severity"]  == "critical"
    assert "major incident" in result.reply.lower() or "immediately" in result.reply.lower() or "critical" in result.reply.lower(), \
        f"Expected immediate raise message, got: {result.reply}"
    cs._sessions.pop(sid, None)


def test_major_incident_no_raise_before_3(monkeypatch):
    """Major incident at n=2: must NOT auto-raise yet."""
    import app.services.chat_service as cs
    monkeypatch.setattr(cs, "_client", _NotResolved())
    monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

    sid, session = _make_session("major_incident", attempts=1)

    result = cs._continue_ai_analysis(session, sid, "still broken")

    assert session["flow_step"] != "escalate_ready", \
        "Major incident should NOT escalate before 3 attempts"
    assert result.can_escalate is False
    cs._sessions.pop(sid, None)


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 4 — Consult "need help today": 6 exchanges then escalate
# ─────────────────────────────────────────────────────────────────────────────

def test_consult_completes_at_6_exchanges(monkeypatch):
    """Consult: max_attempts=5, increments at START of each _continue call → fires at n=5→6th call."""
    import app.services.chat_service as cs
    monkeypatch.setattr(cs, "_client", _NotResolved())
    monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

    sid, session = _make_session("consult", attempts=4)
    # attempt 4 stored; _continue increments to 5 at start → n=5 >= max_attempts(5) → fires

    result = cs._continue_ai_analysis(session, sid, "here is more context")

    assert result.can_escalate is True
    assert session["flow_step"] == "consult_complete"
    assert "gathered" in result.reply.lower() or "network team" in result.reply.lower(), \
        f"Expected consult wrap-up, got: {result.reply}"
    cs._sessions.pop(sid, None)


def test_consult_does_not_complete_before_6(monkeypatch):
    """Consult at attempts=3 (→ n=4 after increment): must NOT complete yet."""
    import app.services.chat_service as cs
    monkeypatch.setattr(cs, "_client", _NotResolved())
    monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

    sid, session = _make_session("consult", attempts=3)

    result = cs._continue_ai_analysis(session, sid, "here is more context")

    assert session["flow_step"] != "consult_complete", \
        "Consult should NOT complete at exchange 5 (needs 6)"
    assert result.can_escalate is False
    cs._sessions.pop(sid, None)


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 5 — Planning ("not urgently"): 4 exchanges then escalate
# ─────────────────────────────────────────────────────────────────────────────

def test_planning_completes_at_4_exchanges(monkeypatch):
    """Planning: fires at n>=4."""
    import app.services.chat_service as cs
    monkeypatch.setattr(cs, "_client", _NotResolved())
    monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

    # Checks use pre-call stored n; planning fires when n >= 4 at call start
    sid, session = _make_session("planning", attempts=4)

    result = cs._continue_ai_analysis(session, sid, "no rush")

    assert result.can_escalate is True
    assert session["flow_step"] == "consult_complete"
    assert "planning" in result.reply.lower() or "network team" in result.reply.lower(), \
        f"Expected planning wrap-up, got: {result.reply}"
    cs._sessions.pop(sid, None)


def test_planning_does_not_complete_before_4(monkeypatch):
    """Planning at attempts=2 (→ n=3 after increment): must NOT complete yet."""
    import app.services.chat_service as cs
    monkeypatch.setattr(cs, "_client", _NotResolved())
    monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

    sid, session = _make_session("planning", attempts=2)

    result = cs._continue_ai_analysis(session, sid, "no rush")

    assert session["flow_step"] != "consult_complete", \
        "Planning should NOT complete at exchange 3 (needs 4)"
    cs._sessions.pop(sid, None)


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 6 — user_confirmed_ticket NOT set for normal broken exhaustion
# (bridge must show ticket_confirm buttons, not auto-raise)
# ─────────────────────────────────────────────────────────────────────────────

def test_only_mid_check_raise_sets_confirmed_flag(monkeypatch):
    """Exhaustion at 6 must NOT set user_confirmed_ticket — bridge shows confirm buttons."""
    import app.services.chat_service as cs
    monkeypatch.setattr(cs, "_client", _NotResolved())
    monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

    sid, session = _make_session("broken", attempts=6)
    session["mid_check_done"] = True

    cs._continue_ai_analysis(session, sid, "still broken")

    # Bridge should show ticket_confirm — NOT auto-raise
    assert not session.get("user_confirmed_ticket"), \
        "Exhaustion path must NOT set user_confirmed_ticket"
    cs._sessions.pop(sid, None)
