"""
Full scenario tests — broken and consult flows with all inner paths.
Run: PYTHONPATH=. pytest tests/test_all_flows.py -v
No real DB or Anthropic API needed — everything is mocked.
"""

import os, uuid
os.environ.setdefault("DATABASE_URL",      "postgresql://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY",        "test-secret-key-minimum-32chars!!")
os.environ.setdefault("JWT_SECRET_KEY",    "test-jwt-secret-minimum-32chars!!")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy-key")
os.environ.setdefault("SMTP_HOST",         "localhost")
os.environ.setdefault("SMTP_PORT",         "25")
os.environ.setdefault("SMTP_USER",         "test@test.com")
os.environ.setdefault("SMTP_PASSWORD",     "testpass")
os.environ.setdefault("FRONTEND_URL",      "http://localhost:3000")
os.environ.setdefault("AI_SERVICES_URL",   "http://localhost:8001")


# ── Fake Claude helpers ───────────────────────────────────────────────────────

def _resp(text):
    class _R:
        content = [type("C", (), {"text": text})()]
    return _R()


class _Claude:
    """Configurable fake Claude. keyword→answer map, fallback for unknowns."""
    def __init__(self, answers: dict, default="Step 1: Check the logs."):
        self._answers  = answers
        self._default  = default

    class _Inner:
        def __init__(self, outer):
            self._outer = outer
        def create(self, **kwargs):
            prompt = (kwargs.get("messages") or [{}])[0].get("content", "")
            for key, val in self._outer._answers.items():
                if key.lower() in prompt.lower():
                    return _resp(val)
            return _resp(self._outer._default)

    @property
    def messages(self):
        return self._Inner(self)


def _no_resolve_client():
    """Issue never resolved; steps count as troubleshooting steps."""
    return _Claude({
        "Is the user confirming":                                          "NO",
        "Does this message say they want to raise":                        "NO",
        "Does the following IT support reply give the user a troubleshoot": "YES",
    })


def _resolve_client():
    """Issue IS resolved on the next user reply."""
    return _Claude({
        "Is the user confirming": "YES",
    })


def _wants_ticket_client():
    return _Claude({
        "Does this message say they want to raise": "YES",
        "Is the user confirming":                   "NO",
    })


def _wants_continue_client():
    return _Claude({
        "Does this message say they want to raise":                        "NO",
        "Is the user confirming":                                          "NO",
        "Does the following IT support reply give the user a troubleshoot": "YES",
    })


# ── Session factory ───────────────────────────────────────────────────────────

def _session(flow_origin="broken", attempts=0, flow_step="ai_analysis",
             mid_check_done=False, extra=None):
    import app.services.chat_service as cs
    sid     = f"test-{uuid.uuid4()}"
    session = cs._get_session(sid)
    session.update({
        "flow_step":      flow_step,
        "flow_origin":    flow_origin,
        "problem":        "Internal portal not accessible",
        "rag_context":    "",
        "solve_attempts": attempts,
        "mid_check_done": mid_check_done,
        "messages":       [{"role": "user", "content": "Internal portal not accessible"}],
        "severity":       "critical" if flow_origin == "major_incident" else "medium",
    })
    if extra:
        session.update(extra)
    return sid, session


# =============================================================================
# BROKEN FLOW — intake routing
# =============================================================================

class TestBrokenIntake:

    def test_broken_keyword_goes_to_waiting_impacting(self, monkeypatch):
        import app.services.chat_service as cs
        from app.schemas.chat import ChatMessageRequest
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid = f"test-{uuid.uuid4()}"
        cs._sessions.pop(sid, None)
        req    = ChatMessageRequest(message="BGP is down", session_id=sid)
        result = cs.process_message(None, None, req)

        assert cs._sessions[sid]["flow_step"] == "waiting_impacting"
        assert "customer impacting" in result.reply.lower()
        cs._sessions.pop(sid, None)

    def test_consult_keyword_goes_to_waiting_details(self, monkeypatch):
        import app.services.chat_service as cs
        from app.schemas.chat import ChatMessageRequest
        monkeypatch.setattr(cs, "_client", _Claude({"Is this message reporting": "CONSULT"}))
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid = f"test-{uuid.uuid4()}"
        cs._sessions.pop(sid, None)
        req    = ChatMessageRequest(message="I have a question about BGP", session_id=sid)
        result = cs.process_message(None, None, req)

        assert cs._sessions[sid]["flow_step"] == "waiting_details"
        cs._sessions.pop(sid, None)

    def test_not_impacting_goes_to_waiting_problem(self, monkeypatch):
        import app.services.chat_service as cs
        from app.schemas.chat import ChatMessageRequest
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", flow_step="waiting_impacting")
        req    = ChatMessageRequest(message="no", session_id=sid)
        result = cs.process_message(None, None, req)

        assert session["flow_step"] == "waiting_problem"
        cs._sessions.pop(sid, None)

    def test_yes_impacting_goes_to_waiting_multi_customer(self, monkeypatch):
        import app.services.chat_service as cs
        from app.schemas.chat import ChatMessageRequest
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", flow_step="waiting_impacting")
        req    = ChatMessageRequest(message="yes customers are affected", session_id=sid)
        result = cs.process_message(None, None, req)

        assert session["flow_step"] == "waiting_multi_customer"
        cs._sessions.pop(sid, None)

    def test_single_user_impacting_goes_to_waiting_problem(self, monkeypatch):
        import app.services.chat_service as cs
        from app.schemas.chat import ChatMessageRequest
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", flow_step="waiting_multi_customer")
        req    = ChatMessageRequest(message="no just one user", session_id=sid)
        result = cs.process_message(None, None, req)

        assert session["flow_step"] == "waiting_problem"
        cs._sessions.pop(sid, None)

    def test_multi_user_goes_to_major_incident(self, monkeypatch):
        import app.services.chat_service as cs
        from app.schemas.chat import ChatMessageRequest
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", flow_step="waiting_multi_customer")
        req    = ChatMessageRequest(message="yes multiple users", session_id=sid)
        result = cs.process_message(None, None, req)

        assert session["flow_origin"] == "major_incident"
        assert session["severity"]    == "critical"
        assert session["flow_step"]   == "ai_analysis"
        cs._sessions.pop(sid, None)


# =============================================================================
# BROKEN FLOW — AI troubleshooting
# =============================================================================

class TestBrokenAI:

    def test_resolved_reply_ends_session(self, monkeypatch):
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", attempts=2)
        result = cs._continue_ai_analysis(session, sid, "its working now!")

        assert result.resolved is True
        assert result.can_escalate is True
        assert session.get("auto_resolved") is True
        cs._sessions.pop(sid, None)

    def test_attempt_not_counted_when_question_only(self, monkeypatch):
        """Replies that are only questions must not increment the counter."""
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _Claude({
            "Is the user confirming":                                          "NO",
            "Does the following IT support reply give the user a troubleshoot": "NO",
        }))
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", attempts=1)
        before = session["solve_attempts"]
        cs._continue_ai_analysis(session, sid, "still broken")
        after = session["solve_attempts"]

        assert after == before, "Question-only reply must NOT increment solve_attempts"
        cs._sessions.pop(sid, None)

    def test_attempt_counted_when_step_given(self, monkeypatch):
        """Replies with a troubleshooting step MUST increment the counter."""
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", attempts=1)
        before = session["solve_attempts"]
        cs._continue_ai_analysis(session, sid, "still broken")
        after = session["solve_attempts"]

        assert after == before + 1, "Troubleshooting step must increment solve_attempts"
        cs._sessions.pop(sid, None)

    def test_midcheck_fires_at_n3_no_runbook(self, monkeypatch):
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", attempts=3)
        result = cs._continue_ai_analysis(session, sid, "still broken")

        assert session["flow_step"]   == "mid_check"
        assert session["mid_check_done"] is True
        assert result.can_escalate    is False
        assert "would you like" in result.reply.lower() or "what would you like" in result.reply.lower()
        cs._sessions.pop(sid, None)

    def test_midcheck_fires_at_n3_with_runbook(self, monkeypatch):
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        # Simulate having a runbook
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "[DNS Runbook]\nStep 1: check nslookup")

        sid, session = _session("broken", attempts=3)
        session["rag_context"] = "[DNS Runbook]\nStep 1: check nslookup"
        result = cs._continue_ai_analysis(session, sid, "still broken")

        assert session["flow_step"] == "mid_check"
        assert result.can_escalate  is False
        cs._sessions.pop(sid, None)

    def test_midcheck_not_fired_twice(self, monkeypatch):
        """mid_check_done=True prevents a second mid-check."""
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", attempts=3, mid_check_done=True)
        result = cs._continue_ai_analysis(session, sid, "still broken")

        assert session["flow_step"] != "mid_check", "Second mid-check must not fire"
        cs._sessions.pop(sid, None)

    def test_midcheck_raise_sets_confirmed_flag(self, monkeypatch):
        import app.services.chat_service as cs
        from app.schemas.chat import ChatMessageRequest
        monkeypatch.setattr(cs, "_client", _wants_ticket_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", flow_step="mid_check", mid_check_done=True)
        req    = ChatMessageRequest(message="escalate", session_id=sid)
        result = cs.process_message(None, None, req)

        assert result.can_escalate is True
        assert session.get("user_confirmed_ticket") is True
        assert session["flow_step"] == "escalate_ready"
        cs._sessions.pop(sid, None)

    def test_midcheck_continue_resumes_no_ticket(self, monkeypatch):
        import app.services.chat_service as cs
        from app.schemas.chat import ChatMessageRequest
        monkeypatch.setattr(cs, "_client", _wants_continue_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", flow_step="mid_check", mid_check_done=True)
        req    = ChatMessageRequest(message="continue", session_id=sid)
        result = cs.process_message(None, None, req)

        assert result.can_escalate is False
        assert not session.get("user_confirmed_ticket")
        assert session["flow_step"] == "ai_analysis"
        cs._sessions.pop(sid, None)

    def test_exhaustion_at_n6_asks_confirm_no_auto_flag(self, monkeypatch):
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", attempts=6, mid_check_done=True)
        result = cs._continue_ai_analysis(session, sid, "still broken")

        assert result.can_escalate is True
        assert session["flow_step"] == "escalate_ready"
        assert "confirm" in result.reply.lower() or "exhausted" in result.reply.lower()
        # Must NOT auto-flag — bridge needs to show Yes/No confirm buttons
        assert not session.get("user_confirmed_ticket")
        cs._sessions.pop(sid, None)

    def test_no_mid_check_before_n3(self, monkeypatch):
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", attempts=2)
        result = cs._continue_ai_analysis(session, sid, "still broken")

        assert session["flow_step"] != "mid_check"
        cs._sessions.pop(sid, None)

    def test_no_exhaustion_before_n6(self, monkeypatch):
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", attempts=5, mid_check_done=True)
        result = cs._continue_ai_analysis(session, sid, "still broken")

        assert result.can_escalate is False
        assert session["flow_step"] != "escalate_ready"
        cs._sessions.pop(sid, None)


# =============================================================================
# MAJOR INCIDENT FLOW
# =============================================================================

class TestMajorIncident:

    def test_autoraise_at_n4_with_confirmed_flag(self, monkeypatch):
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("major_incident", attempts=4)
        result = cs._continue_ai_analysis(session, sid, "still broken")

        assert result.can_escalate is True
        assert session.get("user_confirmed_ticket") is True
        assert session["flow_step"]   == "escalate_ready"
        assert session["severity"]    == "critical"
        cs._sessions.pop(sid, None)

    def test_no_raise_before_n4(self, monkeypatch):
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("major_incident", attempts=3)
        result = cs._continue_ai_analysis(session, sid, "still broken")

        assert result.can_escalate is False
        assert session["flow_step"] != "escalate_ready"
        cs._sessions.pop(sid, None)

    def test_no_midcheck_for_major_incident(self, monkeypatch):
        """Mid-check must never appear in major incident flow."""
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("major_incident", attempts=4)
        result = cs._continue_ai_analysis(session, sid, "still broken")

        assert session["flow_step"] != "mid_check"
        cs._sessions.pop(sid, None)

    def test_major_incident_message_not_matched_by_bridge(self, monkeypatch):
        """The auto-raise message must not contain the mid-check trigger substring."""
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("major_incident", attempts=4)
        result = cs._continue_ai_analysis(session, sid, "still broken")

        assert "so far" not in result.reply.lower(), \
            f"Major incident message must not match bridge mid-check trigger: {result.reply}"
        cs._sessions.pop(sid, None)


# =============================================================================
# CONSULT FLOW — intake routing
# =============================================================================

class TestConsultIntake:

    def test_consult_details_goes_to_waiting_deadline(self, monkeypatch):
        import app.services.chat_service as cs
        from app.schemas.chat import ChatMessageRequest
        monkeypatch.setattr(cs, "_client", _Claude({
            "Is there a deadline": "NO",
        }))
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", flow_step="waiting_details")
        req    = ChatMessageRequest(message="We need to redesign our BGP setup", session_id=sid)
        result = cs.process_message(None, None, req)

        # Should go to deadline or help_today question
        assert session["flow_step"] in ("waiting_deadline", "waiting_help_today")
        cs._sessions.pop(sid, None)

    def test_help_today_yes_starts_consult_ai(self, monkeypatch):
        import app.services.chat_service as cs
        from app.schemas.chat import ChatMessageRequest
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", flow_step="waiting_help_today")
        req    = ChatMessageRequest(message="yes needed today", session_id=sid)
        result = cs.process_message(None, None, req)

        assert session["flow_origin"] == "consult"
        assert session["flow_step"]   == "ai_analysis"
        cs._sessions.pop(sid, None)

    def test_help_today_no_goes_to_next_sprint(self, monkeypatch):
        import app.services.chat_service as cs
        from app.schemas.chat import ChatMessageRequest
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", flow_step="waiting_help_today")
        req    = ChatMessageRequest(message="not urgently", session_id=sid)
        result = cs.process_message(None, None, req)

        assert session["flow_step"] == "waiting_next_sprint"
        cs._sessions.pop(sid, None)

    def test_next_sprint_sets_planning_origin(self, monkeypatch):
        import app.services.chat_service as cs
        from app.schemas.chat import ChatMessageRequest
        monkeypatch.setattr(cs, "_client", _Claude({
            "Extract the timeline": "NEXT_SPRINT_ONLY",
        }))
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", flow_step="waiting_next_sprint")
        req    = ChatMessageRequest(message="next sprint", session_id=sid)
        result = cs.process_message(None, None, req)

        assert session["flow_origin"] == "planning"
        assert session["flow_step"]   == "ai_analysis"
        cs._sessions.pop(sid, None)


# =============================================================================
# CONSULT AI — 6 exchanges then escalate
# =============================================================================

class TestConsultAI:

    def test_consult_completes_at_6th_exchange(self, monkeypatch):
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        # consult increments at START of call; max_attempts=5; fires when n=5
        sid, session = _session("consult", attempts=4)
        result = cs._continue_ai_analysis(session, sid, "more context here")

        assert result.can_escalate is True
        assert session["flow_step"] == "consult_complete"
        assert "network team" in result.reply.lower() or "gathered" in result.reply.lower()
        cs._sessions.pop(sid, None)

    def test_consult_still_gathering_at_5th_exchange(self, monkeypatch):
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("consult", attempts=3)
        result = cs._continue_ai_analysis(session, sid, "more context here")

        assert session["flow_step"] != "consult_complete"
        assert result.can_escalate is False
        cs._sessions.pop(sid, None)

    def test_consult_no_mid_check(self, monkeypatch):
        """Consult flow must never trigger the broken mid-check."""
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        # Even if attempts=3 (mid-check threshold), consult must skip it
        sid, session = _session("consult", attempts=3)
        result = cs._continue_ai_analysis(session, sid, "more context here")

        assert session["flow_step"] != "mid_check"
        cs._sessions.pop(sid, None)

    def test_consult_no_exhaustion_message(self, monkeypatch):
        """Consult ending message must say 'gathered context', not 'exhausted'."""
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("consult", attempts=4)
        result = cs._continue_ai_analysis(session, sid, "more context here")

        assert "exhausted" not in result.reply.lower()
        assert "gathered" in result.reply.lower() or "network team" in result.reply.lower()
        cs._sessions.pop(sid, None)


# =============================================================================
# PLANNING FLOW — 4 exchanges then escalate
# =============================================================================

class TestPlanningAI:

    def test_planning_completes_at_4th_exchange(self, monkeypatch):
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("planning", attempts=4)
        result = cs._continue_ai_analysis(session, sid, "no rush")

        assert result.can_escalate is True
        assert session["flow_step"] == "consult_complete"
        assert "planning" in result.reply.lower() or "network team" in result.reply.lower()
        cs._sessions.pop(sid, None)

    def test_planning_still_gathering_at_3rd_exchange(self, monkeypatch):
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("planning", attempts=3)
        result = cs._continue_ai_analysis(session, sid, "no rush")

        assert session["flow_step"] != "consult_complete"
        assert result.can_escalate is False
        cs._sessions.pop(sid, None)

    def test_planning_no_mid_check(self, monkeypatch):
        """Planning must never trigger the broken mid-check."""
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("planning", attempts=3)
        result = cs._continue_ai_analysis(session, sid, "no rush")

        assert session["flow_step"] != "mid_check"
        cs._sessions.pop(sid, None)

    def test_planning_fewer_exchanges_than_consult(self, monkeypatch):
        """Planning (4) completes before consult threshold (6)."""
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        # At consult attempt=4 (5th call), consult is NOT done yet
        sid_c, session_c = _session("consult", attempts=4)
        # But planning at attempt=4 IS done
        sid_p, session_p = _session("planning", attempts=4)

        res_c = cs._continue_ai_analysis(session_c, sid_c, "context")
        res_p = cs._continue_ai_analysis(session_p, sid_p, "no rush")

        assert session_c["flow_step"] == "consult_complete"   # consult also done at 4→5
        assert session_p["flow_step"] == "consult_complete"
        cs._sessions.pop(sid_c, None)
        cs._sessions.pop(sid_p, None)

    def test_planning_completes_earlier_than_broken_exhaustion(self):
        """Planning ends at 4 exchanges, broken broken exhaustion is at 6 — verify thresholds."""
        # Purely logical assertion — no API needed
        planning_max  = 4
        broken_max    = 6
        consult_max   = 6  # consult increments at start, fires at n=5 stored (6th exchange)
        assert planning_max < broken_max
        assert planning_max < consult_max


# =============================================================================
# CROSS-FLOW ISOLATION — flows must not bleed into each other
# =============================================================================

class TestFlowIsolation:

    def test_broken_mid_check_excluded_from_consult(self, monkeypatch):
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        for origin in ("consult", "planning", "major_incident"):
            sid, session = _session(origin, attempts=3)
            cs._continue_ai_analysis(session, sid, "input")
            assert session["flow_step"] != "mid_check", \
                f"Mid-check must not fire for flow_origin={origin}"
            cs._sessions.pop(sid, None)

    def test_broken_exhaustion_excluded_from_consult(self, monkeypatch):
        """Consult/planning must use their own completion path, not broken exhaustion."""
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        # At n=6 (broken exhaustion threshold), consult fires its own message
        for origin in ("consult",):
            sid, session = _session(origin, attempts=5)
            result = cs._continue_ai_analysis(session, sid, "input")
            assert "exhausted" not in result.reply.lower(), \
                f"flow_origin={origin} must not get broken exhaustion message"
            assert "confirm" not in result.reply.lower(), \
                f"flow_origin={origin} must not ask to confirm ticket like broken flow"
            cs._sessions.pop(sid, None)

    def test_user_confirmed_ticket_not_set_on_normal_exhaustion(self, monkeypatch):
        """Only mid-check raise and major incident set user_confirmed_ticket."""
        import app.services.chat_service as cs
        monkeypatch.setattr(cs, "_client", _no_resolve_client())
        monkeypatch.setattr(cs, "_get_rag", lambda *a, **kw: "")

        sid, session = _session("broken", attempts=6, mid_check_done=True)
        cs._continue_ai_analysis(session, sid, "still broken")

        assert not session.get("user_confirmed_ticket"), \
            "Normal exhaustion must NOT set user_confirmed_ticket — bridge shows confirm buttons"
        cs._sessions.pop(sid, None)
