# Location: backend/app/services/chat_service.py
#
# REWRITE — Flow-based, RAG-driven, no hardcoded domain logic
#
# FLOW (from diagram):
#   START → Is something actively broken?
#     YES → Is it customer impacting?
#       YES → More than 1 customer? → YES → ITSM Major Incident
#                                   → NO  → AI Analysis (RAG)
#       NO  → AI Analysis (RAG)
#     NO  → Consult/question flow → deadline check → AI Analysis (RAG)
#
#   AI Analysis:
#     Search Notion/Confluence runbooks
#     Answer from runbook content only
#     Try to resolve
#     Still not resolved → Is it a networking issue? → YES → raise ticket
#                                                    → NO  → redirect

from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Optional
import uuid
import json
import re
import pytz
import os
import anthropic

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.models.user import User
from app.models.ticket import Ticket, TicketStatus, TicketPriority, TicketDomain
from app.models.engineer import Engineer, AvailabilityStatus
from app.models.team import Team, TeamMember
from app.schemas.chat import (
    ChatMessageRequest, ChatMessageResponse,
    EscalateRequest, EscalateResponse, UserTicketResponse,
)

logger = logging.getLogger(__name__)

_client    = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

_SESSION_MAX_SIZE  = 5_000
_SESSION_TTL_SECS  = 7_200   # 2 hours
_SESSION_REDIS_TTL = 7_500   # slightly longer than memory TTL
_MSG_CAP           = 100     # max messages kept per session (sliding window)

_sessions: dict = {}
_sessions_lock  = threading.Lock()

# Bounded pool for fire-and-forget Redis session writes.
# 16 workers × ~10ms Upstash RTT ≈ 1,600 writes/s throughput —
# enough headroom for 500 concurrent users without blocking process_message.
_redis_write_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="redis-save")


def _get_redis():
    """Return sync Redis client or None (never raises)."""
    try:
        from app.core.redis_client import get_sync_redis
        return get_sync_redis()
    except Exception:
        return None


def _save_session(sid: str, session: dict) -> None:
    """Fire-and-forget Redis session persist. Returns immediately; write happens in background."""
    r = _get_redis()
    if r is None:
        return
    try:
        import json as _json
        data = _json.dumps(session, default=str)
    except Exception:
        return
    # Serialize on the calling thread (session is still in scope / stable),
    # then hand the actual network write to the pool so process_message is not blocked.
    def _write():
        try:
            r.setex(f"session:{sid}", _SESSION_REDIS_TTL, data)
        except Exception as _e:
            logger.debug("[Session] Redis async save failed for %s: %s", sid, _e)
    try:
        _redis_write_pool.submit(_write)
    except RuntimeError:
        pass  # pool shut down (test teardown) — ignore


def _delete_session_redis(sid: str) -> None:
    """Remove session from Redis (called on ticket escalation). Silent no-op on failure."""
    r = _get_redis()
    if r is None:
        return
    try:
        r.delete(f"session:{sid}")
    except Exception:
        pass

# Serialises ticket number generation + DB commit to prevent duplicates under concurrency
_ticket_creation_lock = threading.Lock()


def _evict_old_sessions() -> None:
    # Called inside _sessions_lock — do NOT acquire lock here.
    if len(_sessions) < _SESSION_MAX_SIZE:
        return
    now   = datetime.utcnow().timestamp()
    # Snapshot keys to avoid dict-changed-during-iteration
    stale = [sid for sid, s in list(_sessions.items())
             if now - s.get("_last_accessed", now) > _SESSION_TTL_SECS]
    for sid in stale:
        _sessions.pop(sid, None)
    if len(_sessions) >= _SESSION_MAX_SIZE:
        snapshot = list(_sessions.items())
        oldest   = sorted(snapshot, key=lambda kv: kv[1].get("_last_accessed", 0))
        for sid, _ in oldest[:max(1, len(_sessions) // 10)]:
            _sessions.pop(sid, None)


def _sweep_expired_sessions() -> None:
    """Proactive sweeper — removes all sessions idle > _SESSION_TTL_SECS.
    Runs independently of _SESSION_MAX_SIZE so memory is reclaimed on schedule."""
    now = datetime.utcnow().timestamp()
    with _sessions_lock:
        stale = [sid for sid, s in list(_sessions.items())
                 if now - s.get("_last_accessed", now) > _SESSION_TTL_SECS]
        for sid in stale:
            _sessions.pop(sid, None)
    if stale:
        logger.info("[Session] Swept %d expired session(s) (idle > %ds)", len(stale), _SESSION_TTL_SECS)


def _start_session_sweeper(interval_secs: int = 900) -> None:
    """Start a daemon thread that calls _sweep_expired_sessions every interval_secs."""
    def _run() -> None:
        while True:
            time.sleep(interval_secs)
            try:
                _sweep_expired_sessions()
            except Exception:
                pass  # never let the sweeper crash the process

    t = threading.Thread(target=_run, daemon=True, name="session-sweeper")
    t.start()
    logger.info("[Session] Sweeper started — interval=%ds TTL=%ds", interval_secs, _SESSION_TTL_SECS)


_start_session_sweeper()

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

VALID_DOMAINS = [
    "networking","hardware","software","security","email_communication",
    "identity_access","database","cloud","infrastructure","devops",
    "erp_business_apps","endpoint_management","other",
]

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT — RAG-driven, flow-based
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Network IT support specialist. You handle ALL networking issues including DNS, BGP, OSPF, EIGRP, VPN, firewall, routing, switching, Netskope, VLAN, MPLS, SD-WAN, wireless, and any routing protocol problem.

STRICT FORMATTING:
- Plain sentences only. No bullet points, no markdown, no asterisks.
- Never use markdown links like [text](url) — write URLs as plain text only.
- Under 150 words per response.
- One question at a time.
- Never start with "Certainly", "Absolutely", "Of course", "Great".

KNOWLEDGE BASE PRIORITY:
- If knowledge base content is provided → read it fully and follow the most relevant procedure step by step.
- If no knowledge base content is relevant → use your own networking expertise to troubleshoot.
- Always try to solve the issue before suggesting escalation.

SCOPE: Handle ALL networking issues yourself — DNS, BGP, OSPF, EIGRP, MPLS, VPN, firewall, routing, switching, Netskope, VLAN, SD-WAN, wireless, peering, AS numbers, routing protocols, network security. NEVER tell the user to contact a specialist or team mid-conversation. Exhaust all troubleshooting steps first, then escalate via ticket. Only redirect away if the issue is clearly not networking at all (e.g. printer driver, HR software, payroll system, broken hardware).

PLACEHOLDERS: Never show any placeholder in commands. Before writing any command, scan the entire conversation for known values (IP addresses, hostnames, URLs, AS numbers, interface names, router-ids, peer IPs, group names) and substitute them directly. If a value is not yet known, ask the user for that specific value first — in the same message, before showing any command. Never show angle-bracket tokens like <hostname>, <url>, <ip>, <internal-portal-url>, or any similar placeholder to the user. Never invent or guess a value.

NO ACTIONS: You can only give steps. You have no access to any system — you cannot add, configure, update, restart, modify, or action anything. You cannot touch Netskope, firewalls, DNS servers, routers, switches, or any admin tool. Never use phrases like "I am adding", "I am configuring", "I have done this", "I will update". If a fix requires someone with admin access (e.g. adding a domain to Netskope steering policy), tell the user exactly what needs to be done and by whom. CRITICAL: Never say anything like "Would you like me to raise a ticket", "Should I escalate this", "I have gathered enough information", "I'll raise a support ticket", or any phrase suggesting ticket creation or escalation — the support system handles this automatically and will prompt the user when the time comes. Simply keep giving the next troubleshooting step until you run out of steps, then stop and wait.

COMMANDS: Always show Mac/Linux AND Windows versions for every command.

Also always end your reply with:
<meta>{"domain":"DOMAIN","severity":"SEVERITY","is_networking":"true/false"}</meta>

Domain: networking, hardware, software, security, email_communication, identity_access,
        database, cloud, infrastructure, devops, erp_business_apps, endpoint_management, other
Severity: critical (production/all users), high (user blocked), medium (degraded), low (question)
is_networking: true if this is clearly a networking issue, false if not

If the user says something is fixed, reply warmly and briefly."""

FLOW_PROMPT = """You are a Network IT support specialist running a structured triage flow.

CURRENT FLOW STEP: {step}

STRICT RULES:
- Ask ONLY the question for the current step.
- Under 80 words.
- Plain text only.
- Never start with "Certainly", "Absolutely", "Of course".

Always end with: <meta>{{"domain":"networking","severity":"{severity}","is_networking":"true"}}</meta>"""


# ─────────────────────────────────────────────────────────────────────────────
# SESSION
# ─────────────────────────────────────────────────────────────────────────────

def _get_session(sid: str) -> dict:
    # Fast path: session already in local cache — hold lock only for microseconds.
    with _sessions_lock:
        if sid in _sessions:
            _sessions[sid]["_last_accessed"] = datetime.utcnow().timestamp()
            return _sessions[sid]

    # Cache miss: probe Redis WITHOUT holding the global lock so concurrent
    # threads don't serialize through the ~10 ms Upstash round-trip.
    restored = None
    r = _get_redis()
    if r is not None:
        try:
            import json as _json
            raw = r.get(f"session:{sid}")
            if raw:
                restored = _json.loads(raw)
                logger.debug("[Session] Restored from Redis: %s", sid)
        except Exception as _e:
            logger.debug("[Session] Redis restore failed for %s: %s", sid, _e)

    # Re-acquire lock to write — double-check in case another thread populated
    # the same session while we were waiting for the Redis response.
    with _sessions_lock:
        if sid not in _sessions:
            _evict_old_sessions()
            _sessions[sid] = restored if restored is not None else {
                "messages":           [],
                "flow_step":          "broken",
                "domain":             "networking",
                "severity":           "medium",
                "problem":            "",
                "rag_context":        "",
                "solve_attempts":     0,
                "is_networking":      True,
                "triage_active":      False,
                "triage_questions":   [],
                "triage_q_index":     0,
                "triage_answers":     [],
                "triage_filters":     {},
                "triage_rows":        [],
                "asset_match":        None,
                "asset_confirmed":    False,
                "asset_context":      {},
                "triage_started":     False,
                "mid_check_done":     False,
                "flow_origin":        "broken",
                "screenshot_analysis": None,
                "is_screenshot_turn":  False,
            }
        _sessions[sid]["_last_accessed"] = datetime.utcnow().timestamp()
        return _sessions[sid]


# ─────────────────────────────────────────────────────────────────────────────
# CLAUDE CALL
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# CLAUDE CALL
# ─────────────────────────────────────────────────────────────────────────────

def _call_claude(session: dict, system: str, extra_hint: str = "", trim_for_consult: bool = False) -> tuple:
    """One API call. Returns (reply, domain, severity, is_networking)."""
    if extra_hint:
        system = system + f"\n\nHINT: {extra_hint}"

    messages = session["messages"]
    if trim_for_consult and len(messages) > 4:
        messages = messages[-4:]

    last_exc = None
    for _attempt in range(3):
        try:
            resp = _client.messages.create(
                model      = "claude-sonnet-4-5",
                max_tokens = 400,
                system     = system,
                messages   = messages,
            )
            break
        except Exception as _exc:
            last_exc = _exc
            _s = str(_exc).lower()
            if _attempt < 2 and any(x in _s for x in ["rate_limit", "overloaded", "529", "500", "503", "timeout"]):
                time.sleep(1.5 ** _attempt)
                continue
            raise
    else:
        raise last_exc
    raw = resp.content[0].text.strip()

    domain        = "networking"
    severity      = session.get("severity") or "medium"
    is_networking = True

    m = re.search(r'<meta>(.*?)</meta>', raw, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1).strip())
            d = data.get("domain", "networking")
            s = data.get("severity", "medium")
            n = data.get("is_networking", "true")
            if d in VALID_DOMAINS: domain = d
            if s in ["critical","high","medium","low"]: severity = s
            is_networking = str(n).lower() != "false"
        except Exception:
            pass

    clean = re.sub(r'\s*<meta>.*?</meta>', '', raw, flags=re.DOTALL).strip()
    clean = re.sub(r'\[READY_TO_SOLVE\]|\[NEEDS_ENGINEER\]', '', clean).strip()
    clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean).strip()

    return clean, domain, severity, is_networking



# ─────────────────────────────────────────────────────────────────────────────
# ATTEMPT CLASSIFIER  — Claude decides, no hardcoded keywords
# ─────────────────────────────────────────────────────────────────────────────

def _should_count_attempt(reply: str, is_screenshot_turn: bool) -> bool:
    """
    Count as a troubleshooting attempt only when the bot gives an actual
    troubleshooting step — anything that tells the user to DO something.
    Replies that are purely information-gathering questions do NOT count.

    Screenshot turns NEVER count regardless of reply content.
    """
    if is_screenshot_turn:
        return False

    try:
        resp = _client.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 5,
            messages   = [{"role": "user", "content": (
                "Does the following IT support reply give the user a troubleshooting step to perform?\n\n"
                "Reply YES if the reply tells the user to DO something — examples:\n"
                "- Run a command (ping, nslookup, traceroute, ipconfig, etc.)\n"
                "- Check, open, navigate to, or look at a setting or page\n"
                "- Enable, disable, install, uninstall, or restart something\n"
                "- Try reconnecting, clearing, flushing, or resetting something\n"
                "- Follow a numbered step from a runbook\n\n"
                "Reply NO if the reply is ONLY asking the user for information — examples:\n"
                "- 'What OS are you on?'\n"
                "- 'Are you using Netskope?'\n"
                "- 'Can you describe what happens?'\n"
                "- 'What error message do you see?'\n"
                "- Any question gathering context before troubleshooting starts\n\n"
                "If the reply contains BOTH a question AND a step, reply YES.\n\n"
                f"Reply:\n{reply[:600]}"
            )}],
        )
        return "YES" in resp.content[0].text.strip().upper()
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# RAG CONTEXT
# ─────────────────────────────────────────────────────────────────────────────

def _get_rag(query: str) -> str:
    """Search knowledge base for relevant runbook content."""
    try:
        from app.services.knowledge_service import get_rag_context
        result = get_rag_context(query, domain="networking", n_results=10)
        logger.info("[RAG] _get_rag query=%.80s result_len=%d", query, len(result))
        return result
    except Exception as exc:
        logger.warning("[RAG] _get_rag failed: %s", exc)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# FLOW STEP HANDLERS
# ─────────────────────────────────────────────────────────────────────────────

def _ask_broken(session: dict, sid: str) -> ChatMessageResponse:
    """Step 1: Is something actively broken?"""
    reply = "Is something actively broken right now, or do you have a question or need a consult from the network team?"
    session["messages"].append({"role": "assistant", "content": reply})
    session["flow_step"] = "waiting_broken"
    return _make_response(sid, session, reply, can_escalate=False)


def _handle_broken(session: dict, sid: str, message: str) -> Optional[ChatMessageResponse]:
    """Handle response to 'is something broken' — keyword fast-path then Claude fallback."""
    msg = message.lower().strip()

    consult_direct = ["consult", "question", "advice", "guidance", "help with", "how do i",
                      "wondering", "planning", "need to know", "asking about"]
    if any(s in msg for s in consult_direct):
        session["flow_step"] = "waiting_details"
        reply = "What is it regarding? Please provide more detail — designs, links, screenshots, Epic tickets or any other context that would help."
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)

    broken_direct = ["broken", "down", "not working", "outage", "crash", "fail", "error",
                     "can't access", "cannot access", "unreachable", "not responding"]
    if any(s in msg for s in broken_direct):
        session["flow_step"] = "waiting_impacting"
        reply = "Is this customer impacting? Are end users or customers unable to access services because of this?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)

    try:
        resp = _client.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 10,
            messages   = [{"role": "user", "content": (
                "Is this message reporting a broken/urgent IT issue (BROKEN) or asking a question/consult (CONSULT)? "
                "Reply only BROKEN or CONSULT.\n"
                f"Message: {msg}"
            )}],
        )
        intent = resp.content[0].text.strip().upper()
    except Exception:
        intent = "BROKEN"

    if "CONSULT" in intent:
        session["flow_step"] = "waiting_details"
        reply = "What is it regarding? Please provide more detail — designs, links, screenshots, Epic tickets or any other context that would help."
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)
    else:
        session["flow_step"] = "waiting_impacting"
        reply = "Is this customer impacting? Are end users or customers unable to access services because of this?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)


def _handle_impacting(session: dict, sid: str, message: str) -> ChatMessageResponse:
    """Handle response to 'is it customer impacting'."""
    msg = message.lower().strip()
    yes_signals = ["yes", "yeah", "customers", "users", "impacting", "affected", "multiple",
                   "many", "all", "everyone", "widespread"]

    if any(s in msg for s in yes_signals):
        session["flow_step"] = "waiting_multi_customer"
        reply = "Are more than one customer or user impacted by this?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)
    else:
        session["flow_step"] = "waiting_problem"
        session["customer_impacting"] = False  # not customer-impacting → auto-raise at 4
        reply = "Can you describe what's happening? What exactly is the issue?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)


def _handle_multi_customer(session: dict, sid: str, message: str) -> ChatMessageResponse:
    """Handle response to 'more than 1 customer'."""
    msg = message.lower().strip()
    yes_signals = ["yes", "yeah", "multiple", "many", "more than", "several",
                   "all", "everyone", "widespread", "2", "3", "4", "5"]

    if any(s in msg for s in yes_signals):
        session["flow_step"]      = "ai_analysis"
        session["flow_origin"]    = "major_incident"
        session["severity"]       = "critical"
        session["solve_attempts"] = 0
        return _start_ai_analysis(session, sid)
    else:
        session["flow_step"] = "waiting_problem"
        session["customer_impacting"] = True  # single user, customer-impacting → mid-check at 3
        reply = "Can you describe what's happening? What is the customer experiencing?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)


def _handle_consult(session: dict, sid: str, message: str) -> ChatMessageResponse:
    """Handle consult/question flow."""
    msg = message.lower().strip()
    yes_signals = ["yes", "yeah", "i do", "need", "question", "consult", "help", "advice"]

    if any(s in msg for s in yes_signals):
        session["flow_step"] = "waiting_details"
        reply = ("What is it regarding? Please provide more detail — designs, links, "
                 "screenshots, Epic tickets or any other context that would help.")
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)
    else:
        reply = "No problem. Feel free to reach out if you need anything from the network team."
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)


def _handle_details(session: dict, sid: str, message: str) -> ChatMessageResponse:
    """After collecting consult details → detect deadline from description or ask."""
    session["problem"] = message[:400]

    try:
        resp = _client.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 10,
            messages   = [{"role": "user", "content": (
                f"Does this message mention a deadline, timeline, or urgency? Reply YES or NO only.\nMessage: {message}"
            )}],
        )
        has_deadline_in_desc = "YES" in resp.content[0].text.upper()
    except Exception:
        has_deadline_in_desc = False

    if has_deadline_in_desc:
        session["flow_step"] = "waiting_help_today"
        reply = "Do you need help with this today?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)
    else:
        session["flow_step"] = "waiting_deadline"
        reply = "Is there a hard deadline on this request?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)


def _handle_deadline(session: dict, sid: str, message: str) -> ChatMessageResponse:
    """Handle deadline question — use Claude to interpret yes/no."""
    msg = message.lower().strip()

    # Button sends distinct values — handle directly without Claude call
    if msg == "deadline_yes":
        has_deadline = True
    elif msg == "deadline_no":
        has_deadline = False
    else:
        try:
            resp = _client.messages.create(
                model      = "claude-sonnet-4-5",
                max_tokens = 10,
                messages   = [{"role": "user", "content": (
                    f"Does this message indicate there IS a deadline or time constraint? "
                    f"Reply only YES or NO.\nMessage: {msg}"
                )}],
            )
            has_deadline = "YES" in resp.content[0].text.upper()
        except Exception:
            has_deadline = any(s in msg for s in ["yes", "yeah", "deadline", "urgent", "asap",
                               "today", "tomorrow", "by end", "next month", "this week", "due"])

    # If deadline exists → ask for the specific date, then help_today
    if has_deadline:
        session["flow_step"] = "waiting_deadline_date"
        reply = "What is the deadline?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)

    # No deadline → skip date, go straight to help today
    session["flow_step"] = "waiting_help_today"
    reply = "Do you need help with this today?"
    session["messages"].append({"role": "assistant", "content": reply})
    return _make_response(sid, session, reply, can_escalate=False)


def _handle_help_today(session: dict, sid: str, message: str) -> ChatMessageResponse:
    """Handle 'need help today' question."""
    msg = message.lower().strip()
    yes_signals = ["yes", "yeah", "today", "now", "asap", "immediately", "need it now", "right now"]

    if any(s in msg for s in yes_signals) or (msg == "urgent") or ("urgent" in msg and "not" not in msg):
        session["flow_step"]   = "ai_analysis"
        session["flow_origin"] = "consult"
        return _start_ai_analysis(session, sid)
    else:
        session["flow_step"] = "waiting_next_sprint"
        reply = "When should the network team pick this up? (Next sprint / Next release / Next sprint and release / Specific date / No rush)"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)


# ─────────────────────────────────────────────────────────────────────────────
# AI ANALYSIS — RAG driven
# ─────────────────────────────────────────────────────────────────────────────

def _start_ai_analysis(session: dict, sid: str) -> ChatMessageResponse:
    """Start AI analysis using RAG from knowledge base."""
    session["flow_step"] = "ai_analysis"

    # Build problem string
    problem = session.get("problem", "")
    if not problem:
        user_msgs = [m["content"] for m in session["messages"] if m["role"] == "user"]
        problem   = " ".join(user_msgs[:3])

    is_consult_or_planning = session.get("flow_origin") in ("consult", "planning")
    rag_context = session.get("rag_context") or _get_rag(problem)
    session["rag_context"] = rag_context
    logger.info("[RAG] flow_origin=%s rag_found=%s query=%.80s",
                session.get("flow_origin"), bool(rag_context), problem)

    screenshot_ctx = ""
    if session.get("screenshot_analysis"):
        screenshot_ctx = (
            f"\n\nSCREENSHOT ANALYSIS:\n{session['screenshot_analysis']}\n"
            "Use this visual context to inform your next step."
        )

    is_screenshot_turn = session.get("is_screenshot_turn", False)
    flow_origin        = session.get("flow_origin")
    n                  = session.get("solve_attempts", 0)

    if rag_context:
        system = (
            "You are a Network IT support specialist handling all networking issues including DNS, BGP, OSPF, VPN, firewall, routing, switching, Netskope, and any network connectivity problems.\n\n"
            "FORMATTING: Plain sentences only. No markdown. No asterisks. No bullet points.\n"
            "Never use markdown links like [text](url) — write URLs as plain text only.\n"
            "Under 150 words. One question at a time.\n"
            "Never start with Certainly, Absolutely, Of course, Great.\n\n"
            "COMMANDS: Always show Mac/Linux AND Windows versions for every command.\n\n"
            "NETWORKING SCOPE: Handle ALL networking issues yourself — DNS, BGP, OSPF, VPN, firewall, "
            "routing, switching, Netskope, VLAN, MPLS, SD-WAN, wireless, routing protocols, peering. "
            "NEVER tell the user to contact a BGP specialist or routing team mid-conversation. "
            "Exhaust all troubleshooting steps first. NEVER say 'Would you like me to raise a ticket', 'Should I escalate', 'I have gathered enough information', or anything suggesting ticket creation — the system handles escalation automatically. Keep giving the next step until you run out of steps, then stop. "
            "Only redirect if clearly not networking at all (printer driver, HR software, payroll).\n\n"
            "PLACEHOLDERS: Never show any placeholder in commands. "
            "Before writing any command, scan the entire conversation for known values (IP addresses, hostnames, URLs, AS numbers, interface names) and substitute them directly. "
            "If a value is not yet known, ask the user for that specific value IN THE SAME MESSAGE before showing the command — do not show the command with a placeholder, do not invent a value, do not use angle-bracket tokens like <hostname> or <url> or <internal-portal-url> or similar. "
            "Ask the question, wait for the answer, then show the command with the real value substituted.\n\n"
            + "KNOWLEDGE BASE — RUNBOOK PROCEDURES:\n\n"
            + ("" if is_consult_or_planning else
               "RUNBOOK INSTRUCTION: A runbook procedure is provided below. "
               "First check: does this runbook directly match the user's specific problem? "
               "If YES — follow Step 1 of that procedure. Address the user directly using 'you', never third-person meta-instructions like 'Ask the user'. "
               "If NO (e.g. runbook is about Netskope but user has a DHCP/BGP/hardware issue) — ignore the runbook completely and use your own networking expertise for the first diagnostic step.\n\n")
            + f"{rag_context}"
            + f"{screenshot_ctx}\n\n"
            + ("" if is_consult_or_planning else "Now give Step 1 of the matching procedure. Nothing else.")
        )
        hint = "Give Step 1 of the matching runbook procedure. Address the user directly using 'you' — never say 'Ask the user' or use third-person meta-instructions. Speak as if you are the support agent talking to the user."

        if flow_origin == "major_incident":
            n_mi = session.get("solve_attempts", 0)
            if n_mi >= 3:
                hint = (
                    "You have enough information. Summarise the incident and tell the user "
                    "a CRITICAL ticket is being raised now. End with [STEPS_EXHAUSTED]."
                )
            else:
                hint = (
                    "This is a MAJOR INCIDENT affecting multiple customers. "
                    + ("Follow the runbook procedure for this incident type." if rag_context else
                       "Ask the single most important question to understand scope, impact, or recent changes.")
                )
        elif flow_origin == "consult":
            remaining   = max(0, 6 - n)
            problem_ctx = f"The consultation is about: {session.get('problem', '')}. " if session.get("problem") else ""
            hint = (
                f"This is a network team consultation. You have {remaining} quality exchanges remaining. "
                f"{problem_ctx}"
                "Ask ONE focused technical question for the network engineer — infrastructure, devices, scale, "
                "IP ranges, security requirements, or constraints. "
                "Do NOT provide solutions, commands, or implementation steps. "
                "Do NOT mention escalation or handing off."
            )
        elif flow_origin == "planning":
            timeline  = session.get("planning_timeline", "future")
            remaining = max(0, 4 - n)
            hint = (
                f"This request is scheduled for: {timeline}. "
                f"You have {remaining} exchanges to gather planning context. "
                "Ask ONE focused question about technical scope, dependencies, blockers, "
                "business priority, or success criteria. Do NOT mention escalation."
            )
    else:
        system = SYSTEM_PROMPT + (f"\n\n{screenshot_ctx}" if screenshot_ctx else "")
        if flow_origin == "consult":
            remaining   = max(0, 6 - n)
            problem_ctx = f"The consultation is about: {session.get('problem', '')}. " if session.get("problem") else ""
            hint = (
                f"This is a network team consultation. You have {remaining} exchanges remaining. "
                f"{problem_ctx}"
                "Ask ONE focused technical question for the network engineer — infrastructure, devices, scale, "
                "IP ranges, security requirements, or constraints. "
                "Do NOT provide solutions, commands, or implementation steps. "
                "Do NOT mention escalation or handing off."
            )
        elif flow_origin == "planning":
            timeline  = session.get("planning_timeline", "future")
            remaining = max(0, 4 - n)
            hint = (
                f"This request is scheduled for: {timeline}. "
                f"You have {remaining} exchanges to gather planning context. "
                "Ask ONE focused question about technical scope, dependencies, blockers, "
                "business priority, or success criteria. Do NOT mention escalation."
            )
        elif session.get("screenshot_analysis"):
            hint = (
                f"The user confirmed this screenshot shows their issue: {session['screenshot_analysis'][:300]}\n\n"
                "You already know the problem from the screenshot. Skip intake questions. "
                "Go straight to the first specific diagnostic step based on what you can see."
            )
        else:
            hint = (
                "No runbook found. Use your networking expertise — give one specific first diagnostic step. "
                "If clearly not a networking issue, tell the user politely and redirect."
            )

    # For the broken flow with a runbook, trim the intake Q&A so Claude sees only
    # the problem description — prevents it continuing the "ask questions" pattern.
    if rag_context and flow_origin not in ("consult", "planning", "major_incident"):
        user_msgs    = [m for m in session["messages"] if m["role"] == "user"]
        call_session = {**session, "messages": user_msgs[-1:] if user_msgs else session["messages"]}
    else:
        call_session = session

    try:
        reply, domain, severity, is_networking = _call_claude(call_session, system, hint)
    except Exception as e:
        logger.error("[Chat] _call_claude failed in _start_ai_analysis: %s", e)
        reply         = "I'm having trouble reaching the AI service right now. Please try again in a moment."
        domain        = session.get("domain", "networking")
        severity      = session.get("severity", "medium")
        is_networking = True

    session["domain"]       = domain
    session["severity"]     = severity
    session["is_networking"] = is_networking

    # Disclaimer for consult/planning when no RAG document was found
    if session.get("flow_origin") in ("consult", "planning") and not rag_context:
        if "AI-generated" not in reply:
            reply += (
                "\n\nNote: This response is AI-generated based on general networking knowledge. "
                "Please verify with your network engineer before implementing."
            )

    # ── Attempt counting — Claude classifies, screenshot turn always 0 ────────
    # consult/planning: every exchange counts (they gather context, not steps)
    # broken/major_incident: only count when reply contains a real troubleshooting step
    if session.get("flow_origin") in ("consult", "planning"):
        if not is_screenshot_turn:
            session["solve_attempts"] += 1
    else:
        if _should_count_attempt(reply, is_screenshot_turn):
            session["solve_attempts"] += 1

    # Reset screenshot turn flag after this reply
    session["is_screenshot_turn"] = False

    session["messages"].append({"role": "assistant", "content": reply})
    return _make_response(sid, session, reply, can_escalate=False)


def _continue_ai_analysis(session: dict, sid: str, message: str) -> ChatMessageResponse:
    """Continue AI analysis — check if resolved or needs escalation."""
    # Check if resolved — include last bot question for context so short replies
    # like "yes" / "no" are judged against what was actually asked, not in isolation
    try:
        # Get last assistant message for context
        prior_msgs    = session.get("messages", [])
        last_bot_msg  = next(
            (m["content"] for m in reversed(prior_msgs) if m["role"] == "assistant"),
            ""
        )

        resp = _client.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 10,
            messages   = [{"role": "user", "content": (
                "You are checking whether an IT support issue has been resolved.\n\n"
                f"The support bot just said:\n{last_bot_msg}\n\n"
                f"The user replied:\n{message}\n\n"
                "Is the user confirming the issue is now resolved or working correctly?\n"
                "Reply YES if they say any of: it is working, fixed, resolved, session is up, "
                "established, connected, accessible, showing routes, State/PfxRcd has a number, "
                "can access now, ping succeeds, IP resolved correctly, or any clear success signal.\n"
                "Reply NO if they are still troubleshooting, reporting an error, or answering "
                "a question without confirming success.\n"
                "Reply YES or NO only."
            )}],
        )
        is_resolved = "YES" in resp.content[0].text.upper()
    except Exception:
        is_resolved = False

    if is_resolved:
        reply = "Glad that sorted it out. Feel free to reach out if anything else comes up."
        session["messages"].append({"role": "assistant", "content": reply})
        # Silently raise a ticket marked as resolved — captured in analytics as "resolved by AI"
        session["auto_resolved"] = True
        return _make_response(sid, session, reply, resolved=True, can_escalate=True)

    is_screenshot_turn = session.get("is_screenshot_turn", False)

    # Retry RAG if the session had no runbook context — covers stale sessions that
    # were already in ai_analysis when a new problem message arrives.
    rag_context = session.get("rag_context") or _get_rag(message) or _get_rag(session.get("problem", ""))
    if rag_context:
        session["rag_context"] = rag_context
    has_runbook = bool(rag_context)
    logger.debug("[Major] flow_origin=%s attempts=%s rag=%s", session.get("flow_origin"), session["solve_attempts"], has_runbook)

    # Inject screenshot context if present
    screenshot_ctx = ""
    if session.get("screenshot_analysis"):
        screenshot_ctx = (
            f"\n\nSCREENSHOT ANALYSIS:\n{session['screenshot_analysis']}\n"
            "Use this visual context when deciding the next troubleshooting step."
        )

    rag_instruction = (
        "STRICT INSTRUCTION: Follow the runbook procedures exactly. "
        "Ask only what the runbook requires for the current step. "
        "Do NOT ask questions outside of the runbook steps. "
        "When ALL runbook steps are exhausted and issue is still not resolved, end with [STEPS_EXHAUSTED]."
    )
    if rag_context:
        system = (
            SYSTEM_PROMPT
            + "\n\nKNOWLEDGE BASE — RUNBOOK PROCEDURES:\n"
            + rag_context
            + "\n\n"
            + (screenshot_ctx + "\n\n" if screenshot_ctx else "")
            + rag_instruction
        )
    else:
        system = SYSTEM_PROMPT + (f"\n\n{screenshot_ctx}" if screenshot_ctx else "")

    n         = session["solve_attempts"]
    is_consult = session.get("flow_origin") == "consult"

    if is_consult:
        max_attempts = 5  # 1 increment in _start_ai_analysis + 5 here = 6 total questions
    else:
        max_attempts = 6

    # For consult — increment now so the completion check fires on the 6th exchange
    if is_consult and not is_screenshot_turn:
        session["solve_attempts"] += 1
        n = session["solve_attempts"]

    is_major         = session.get("flow_origin") == "major_incident"
    not_impacting    = session.get("customer_impacting") is False  # explicitly set False in intake

    # Flow 1: major incident — auto-raise at 4 attempts
    if is_major and n >= 4:
        reply = "This is a major incident affecting multiple users. Raising a critical ticket now and alerting the network engineering team immediately."
        session["messages"].append({"role": "assistant", "content": reply})
        session["domain"]                = "networking"
        session["severity"]              = "critical"
        session["flow_step"]             = "escalate_ready"
        session["user_confirmed_ticket"] = True
        return _make_response(sid, session, reply, can_escalate=True)

    # Flow 3: not customer-impacting — auto-raise at 4 attempts (no mid-check, no confirmation)
    if not_impacting and n >= 4:
        reply = "I have completed all standard troubleshooting steps. Raising a ticket now for the network engineering team to investigate further."
        session["messages"].append({"role": "assistant", "content": reply})
        session["flow_step"]             = "escalate_ready"
        session["user_confirmed_ticket"] = True
        return _make_response(sid, session, reply, can_escalate=True)

    # Flow 2: single user, customer-impacting — ask confirmation at 6 attempts
    if n >= max_attempts and not is_consult:
        reply = "I have exhausted all troubleshooting steps I can and the issue is still not resolved. We need a network engineer to take this further. Please confirm to raise a ticket."
        session["messages"].append({"role": "assistant", "content": reply})
        session["flow_step"] = "escalate_ready"
        return _make_response(sid, session, reply, can_escalate=True)
    elif n >= max_attempts and is_consult:
        reply = "I have gathered enough context. I will share this with the network team who will follow up with you."
        session["messages"].append({"role": "assistant", "content": reply})
        session["flow_step"] = "consult_complete"
        return _make_response(sid, session, reply, can_escalate=True)
    elif n >= 4 and session.get("flow_origin") == "planning":
        reply = "I have all the planning details I need. I will share this with the network team so they are ready when the time comes."
        session["messages"].append({"role": "assistant", "content": reply})
        session["flow_step"] = "consult_complete"
        return _make_response(sid, session, reply, can_escalate=True)
    else:
        # Mid-point check at attempt 3 (no runbook only, broken flow only)
        if not has_runbook and n >= 3 and not session.get("mid_check_done") and not is_consult and session.get("flow_origin") not in ("planning", "major_incident") and session.get("customer_impacting") is not False:
            session["mid_check_done"] = True
            reply = (
                "I have tried 3 troubleshooting steps so far and the issue is still not resolved. "
                "Would you like me to try a few more steps, or shall I raise a ticket and escalate this to the network engineering team?"
            )
            session["messages"].append({"role": "assistant", "content": reply})
            session["flow_step"] = "mid_check"
            return _make_response(sid, session, reply, can_escalate=False)

        # Runbook mid-check at step 3 — broken flow only, never consult/planning
        if has_runbook and n >= 3 and not session.get("mid_check_done") and session.get("flow_origin") not in ("major_incident", "consult", "planning") and session.get("customer_impacting") is not False:
            session["mid_check_done"] = True
            reply = (
                "I have gone through several troubleshooting steps and the issue is still not resolved. "
                "Would you like me to continue with more steps, or shall I raise a ticket and escalate to the network engineering team?"
            )
            session["messages"].append({"role": "assistant", "content": reply})
            session["flow_step"] = "mid_check"
            return _make_response(sid, session, reply, can_escalate=False)

        # Get last user message to anchor the hint
        last_user_msg = next(
            (m["content"] for m in reversed(session.get("messages", [])) if m["role"] == "user"),
            ""
        )

        if has_runbook:
            screenshot_hint = ""
            if session.get("screenshot_analysis"):
                screenshot_hint = (
                    f"A screenshot was already analysed showing: {session['screenshot_analysis'][:200]}. "
                    "Do NOT ask what the problem is — you already know from the screenshot. "
                )
            mid_done = session.get("mid_check_done", False)
            hint = (
                f"The user just replied: {last_user_msg}\n\n"
                f"{screenshot_hint}"
                "Read that reply as the output or answer to the previous step. "
                "Do NOT ask for that information again. "
                "Look at the runbook and give the next step based on what the user just told you. "
                "Do NOT repeat any step already given in the conversation. "
                + (
                    "If ALL runbook steps are exhausted and the issue is still not resolved, "
                    "tell the user the network team needs to take over and end with [STEPS_EXHAUSTED]. "
                    "Always include a full sentence before [STEPS_EXHAUSTED]."
                    if mid_done else
                    "Do NOT emit [STEPS_EXHAUSTED] yet — follow the runbook steps in order first."
                )
            )
        else:
            screenshot_hint = ""
            if session.get("screenshot_analysis"):
                screenshot_hint = (
                    f"A screenshot was already analysed earlier showing: {session['screenshot_analysis'][:200]}. "
                    "You already know the issue from that — do NOT ask what the problem is or what application is affected. "
                )
            # Consult/planning — gather info for engineer, never solve
            if is_consult or session.get("flow_origin") == "planning":
                remaining = max(0, 6 - n)
                hint = (
                    f"The user just replied: {last_user_msg}\n\n"
                    f"This is a network team consultation. You have {remaining} exchanges remaining. "
                    f"Your goal is to gather maximum useful technical information for the network engineer who will implement this. "
                    f"Ask ONE focused technical question about the network infrastructure, devices, scale, IP ranges, security requirements, or constraints. "
                    f"Do NOT ask for contact details, email addresses, or non-technical information. "
                    f"Do NOT provide configuration steps, commands, implementation plans, or solutions. "
                    f"Do NOT mention escalation, the network team, or handing off to anyone. "
                    f"Just ask the single most valuable technical question for the engineer."
                )
            else:
                hint = (
                    f"The user just replied: {last_user_msg}\n\n"
                    f"{screenshot_hint}"
                    "Read the user reply as the output or answer to your previous step. "
                    "Do NOT ask for information already visible in the conversation or screenshot. "
                    "CRITICAL: Before showing any command, scan the full conversation for IP addresses, "
                    "hostnames, AS numbers, interface names, or any other values already provided. "
                    "Substitute them directly into commands — never use placeholders like <ip>, "
                    "<destination>, <remote-peer-ip> when the real value is already known. "
                    f"This is attempt {n} of 6. Based on everything in the conversation, "
                    "give the ONE most logical next troubleshooting step. "
                    "Different from anything already tried."
                )

        try:
            reply, domain, severity, is_networking = _call_claude(session, system, hint)
        except Exception as e:
            logger.error("[Chat] _call_claude failed in _continue_ai_analysis: %s", e)
            reply         = "I'm having trouble reaching the AI service right now. Please try again in a moment."
            domain        = session.get("domain", "networking")
            severity      = session.get("severity", "medium")
            is_networking = True
            escalate      = False
            session["messages"].append({"role": "assistant", "content": reply})
            return _make_response(sid, session, reply, can_escalate=False)

        escalate = "[STEPS_EXHAUSTED]" in reply
        reply    = reply.replace("[STEPS_EXHAUSTED]", "").strip()

        if not reply:
            reply    = "I have gone through all the troubleshooting steps. I will now escalate this to the network engineering team."
            escalate = True

        # Disclaimer for consult/planning when no RAG document found
        if is_consult and not has_runbook:
            if "AI-generated" not in reply:
                reply += (
                    "\n\nNote: This response is AI-generated based on general networking knowledge. "
                    "Please verify with your network engineer before implementing."
                )

        # ── Attempt counting — Claude classifies, screenshot turn always 0 ────
        # consult: already incremented at top of function
        # planning: every exchange counts (context gathering)
        # broken/major_incident: only real troubleshooting steps count
        if session.get("flow_origin") == "planning":
            if not is_screenshot_turn:
                session["solve_attempts"] += 1
        elif not is_consult:
            if _should_count_attempt(reply, is_screenshot_turn):
                session["solve_attempts"] += 1

        # Reset screenshot turn flag
        session["is_screenshot_turn"] = False

        session["messages"].append({"role": "assistant", "content": reply})
        session["domain"]        = domain
        session["severity"]      = severity
        session["is_networking"] = is_networking

        if not escalate:
            return _make_response(sid, session, reply, can_escalate=False)

    # Escalation — skip triage, go straight to ticket confirmation
    session["flow_step"] = "escalate_ready"
    return _make_response(sid, session, reply, can_escalate=True)


# ─────────────────────────────────────────────────────────────────────────────
# TRIAGE
# ─────────────────────────────────────────────────────────────────────────────

def _start_triage_db(db: Optional[Session], session: dict, sid: str) -> ChatMessageResponse:
    """Start asset triage from DB."""
    try:
        if db:
            from app.services.asset_identifier_service import generate_questions, fetch_assets
            domain    = session["domain"] or "networking"
            problem   = session["problem"]
            rows, _   = fetch_assets(db, domain, problem)
            questions = generate_questions(db, domain, problem)
            session["triage_rows"] = rows
        else:
            questions = ["What is the name of the affected device or system?",
                        "What environment is this? (Production / Staging / Development)"]
            session["triage_rows"] = []
    except Exception:
        questions = ["What is the name of the affected device or system?",
                    "What environment is this? (Production / Staging / Development)"]
        session["triage_rows"] = []

    session["triage_active"]    = True
    session["triage_questions"] = questions
    session["triage_q_index"]   = 1
    session["triage_answers"]   = []
    session["triage_filters"]   = {}
    session["flow_step"]        = "triage"

    reply = ("Before I raise this ticket I need a couple of quick details "
             "to route this to exactly the right engineer.\n\n" + questions[0])
    return _make_response(sid, session, reply, can_escalate=False, context_gathering=True)


def _handle_triage_answer(db: Session, session: dict, sid: str, answer: str) -> ChatMessageResponse:
    """Process one triage answer."""
    try:
        from app.services.asset_identifier_service import extract_field_from_answer, progressive_match
        qi        = session["triage_q_index"]
        questions = session["triage_questions"]
        rows      = session["triage_rows"]

        if qi > 0 and qi <= len(questions):
            prev_q = questions[qi - 1]
            session["triage_answers"].append(answer)
            extracted = extract_field_from_answer(prev_q, answer, rows)
            col = extracted.get("column")
            val = extracted.get("value")
            if col and val:
                session["triage_filters"][col] = val
                session["asset_context"][col]  = val
                logger.debug("[Triage] Filter set: col=%s", col)

        if session["triage_filters"]:
            result = progressive_match(db, session["triage_filters"], rows)
            session["asset_match"] = result.get("matched")
            candidates             = result.get("candidates", 0)
            logger.debug("[Triage] Candidates: %s confident=%s", candidates, result["confident"])

            if result["confident"]:
                session["asset_confirmed"] = True
                session["triage_active"]   = False
                asset = result["matched"]
                name  = asset.get("identifier") or "the asset"
                env   = asset.get("environment") or ""
                team  = asset.get("team") or ""
                reply = (
                    f"Found it. This is {name}"
                    + (f" in the {env} environment" if env else "")
                    + (f", owned by {team}" if team else "")
                    + ". Raising the ticket now."
                )
                return _make_response(sid, session, reply, can_escalate=True)

        qi = session["triage_q_index"]
        if qi < len(questions):
            next_q = questions[qi]
            session["triage_q_index"] += 1
            candidates = len([
                r for r in rows
                if all(v.lower() in str(r.get(c,"")).lower()
                       for c, v in session["triage_filters"].items())
            ]) if session["triage_filters"] else len(rows)
            hint = f" ({candidates} possible matches)" if candidates > 1 else ""
            return _make_response(sid, session, next_q + hint, can_escalate=False, context_gathering=True)

    except Exception as e:
        logger.error("[Triage] Error: %s", e)

    session["triage_active"] = False
    reply = "Thanks for the details. Raising the ticket now and routing to the network engineering team."
    return _make_response(sid, session, reply, can_escalate=True)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _make_response(
    sid: str, session: dict, reply: str,
    resolved: bool = False,
    can_escalate: bool = False,
    context_gathering: bool = False,
) -> ChatMessageResponse:
    return ChatMessageResponse(
        session_id        = sid,
        reply             = reply,
        intent            = "solve",
        detected_domain   = session.get("domain") or "networking",
        detected_severity = session.get("severity") or "medium",
        resolved          = resolved,
        can_escalate      = can_escalate,
        attempt_number    = session.get("solve_attempts", 0),
        context_gathering = context_gathering,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PROCESS MESSAGE
# ─────────────────────────────────────────────────────────────────────────────

def process_message(db: Session, user: User, data: ChatMessageRequest) -> ChatMessageResponse:
    sid     = data.session_id or str(uuid.uuid4())
    session = _get_session(sid)

    # Bind session to authenticated user — prevents user A accessing user B's session
    if user is not None:
        uid = str(user.id)
        if "_user_id" not in session:
            session["_user_id"] = uid
        elif session["_user_id"] != uid:
            sid     = str(uuid.uuid4())
            session = _get_session(sid)
            session["_user_id"] = uid

    msg = data.message.strip()

    # Store problem on first message
    if not session["problem"] and msg:
        session["problem"] = msg[:400]

    # Enforce sliding-window message cap before appending — prevents per-session OOM
    if len(session["messages"]) >= _MSG_CAP:
        session["messages"] = session["messages"][-(  _MSG_CAP - 1):]

    # Append user message
    session["messages"].append({"role": "user", "content": msg})

    step = session["flow_step"]
    logger.debug("[Chat] sid=%s step=%s", sid, step)

    # ── FLOW ROUTING ──────────────────────────────────────────────────────────
    # All branches assign to _result (no early returns) so _save_session can be
    # called once here before returning.  Business logic is unchanged.

    if step == "broken":
        session["problem"] = msg[:400]
        _result = _handle_broken(session, sid, msg)

    elif step == "waiting_broken":
        _result = _handle_broken(session, sid, msg)

    elif step == "waiting_impacting":
        _result = _handle_impacting(session, sid, msg)

    elif step == "waiting_multi_customer":
        _result = _handle_multi_customer(session, sid, msg)

    elif step == "waiting_consult":
        _result = _handle_consult(session, sid, msg)

    elif step == "waiting_details":
        _result = _handle_details(session, sid, msg)

    elif step == "waiting_deadline":
        _result = _handle_deadline(session, sid, msg)

    elif step == "waiting_deadline_date":
        session["deadline_date"] = msg
        session["flow_step"]     = "waiting_help_today"
        reply = "Do you need help with this today?"
        session["messages"].append({"role": "assistant", "content": reply})
        _result = _make_response(sid, session, reply, can_escalate=False)

    elif step == "waiting_help_today":
        _result = _handle_help_today(session, sid, msg)

    elif step == "waiting_problem":
        session["problem"]     = msg[:400]
        session["flow_step"]   = "ai_analysis"
        session["flow_origin"] = "broken"
        rag_context = _get_rag(msg)
        session["rag_context"] = rag_context
        _result = _start_ai_analysis(session, sid)

    elif step == "mid_check":
        try:
            resp = _client.messages.create(
                model      = "claude-sonnet-4-5",
                max_tokens = 5,
                messages   = [{"role": "user", "content": (
                    f"Does this message say they want to raise a ticket or escalate to an engineer? "
                    f"Reply YES or NO only.\nMessage: {msg}"
                )}],
            )
            wants_ticket = "YES" in resp.content[0].text.strip().upper()
        except Exception:
            wants_ticket = any(w in msg.lower() for w in ["ticket", "escalate", "raise", "engineer", "no", "nope"])

        if wants_ticket:
            session["flow_step"] = "escalate_ready"
            session["user_confirmed_ticket"] = True
            reply = "Raising a ticket now and escalating to the network engineering team."
            session["messages"].append({"role": "assistant", "content": reply})
            _result = _make_response(sid, session, reply, can_escalate=True)
        else:
            session["flow_step"] = "ai_analysis"
            _result = _continue_ai_analysis(session, sid, msg)

    elif step == "ai_analysis":
        _result = _continue_ai_analysis(session, sid, msg)

    elif step == "waiting_next_sprint":
        try:
            resp = _client.messages.create(
                model      = "claude-sonnet-4-5",
                max_tokens = 30,
                messages   = [{"role": "user", "content": (
                    f"Extract the timeline from this message. Reply with one of: "
                    f"NEXT_SPRINT_AND_RELEASE, NEXT_SPRINT_ONLY, NEXT_RELEASE_ONLY, SPECIFIC_DATE, NO_RUSH\n"
                    f"Message: {msg}"
                )}],
            )
            timeline_code = resp.content[0].text.strip().upper()
        except Exception:
            timeline_code = "NEXT_SPRINT_ONLY" if "sprint" in msg.lower() else "NO_RUSH"

        timeline_map = {
            "NEXT_SPRINT_AND_RELEASE": "next sprint and next release",
            "NEXT_SPRINT_ONLY":        "next sprint",
            "NEXT_RELEASE_ONLY":       "next release",
            "SPECIFIC_DATE":           msg.strip(),
            "NO_RUSH":                 "no fixed timeline",
        }
        session["planning_timeline"] = timeline_map.get(timeline_code, "next sprint")
        session["flow_step"]         = "ai_analysis"
        session["flow_origin"]       = "planning"
        session["solve_attempts"]    = 0
        _result = _start_ai_analysis(session, sid)

    elif step in ("major_incident", "next_sprint", "consult_complete", "escalate_ready"):
        reply = "Is there anything else I can help with?"
        session["messages"].append({"role": "assistant", "content": reply})
        _result = _make_response(sid, session, reply)

    else:
        session["flow_step"] = "broken"
        session["problem"]   = msg[:400]
        _result = _handle_broken(session, sid, msg)

    # Persist session mutations to Redis so any worker can continue the conversation
    _save_session(sid, session)
    return _result


# ─────────────────────────────────────────────────────────────────────────────
# SCREENSHOT — Vision analysis via Claude
# ─────────────────────────────────────────────────────────────────────────────

def _detect_media_type(image_bytes: bytes) -> str:
    """Detect image media type from magic bytes. Fallback to jpeg."""
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if image_bytes[:3] == b'\xff\xd8\xff':
        return "image/jpeg"
    if image_bytes[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return "image/webp"
    # Default — Claude Vision accepts jpeg for unknown formats
    return "image/jpeg"


def analyze_screenshot(image_bytes: bytes, session_id: str, user_id: str, media_type: str = None) -> dict:
    """
    Analyze screenshot using Claude Vision.
    Stores analysis in session for context injection.
    This turn never counts as a solve attempt (is_screenshot_turn=True).
    """
    session  = _get_session(session_id)
    filename = f"{user_id}_{session_id[:8]}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    session["screenshot_path"] = filepath

    # Detect real media type from bytes — never trust the caller blindly
    detected_type = _detect_media_type(image_bytes)
    supported = {"image/png", "image/jpeg", "image/gif", "image/webp"}
    if media_type and media_type in supported:
        if detected_type != media_type and detected_type != "image/jpeg":
            media_type = detected_type
    else:
        media_type = detected_type

    logger.debug("[Vision] size=%d detected=%s using=%s", len(image_bytes), detected_type, media_type)

    # Call Claude Vision
    try:
        import base64
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        resp = _client.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 300,
            messages   = [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": media_type,
                            "data":       b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "You are an IT support specialist analysing a screenshot. "
                            "In 2-3 plain sentences describe: what screen or application is shown, "
                            "any error message or code visible, and the relevant network or system state. "
                            "Rules: plain sentences only, no bullet points, no numbered lists, "
                            "no markdown, no asterisks, no headers. "
                            "Be specific — include exact error codes and URLs if visible."
                        ),
                    },
                ],
            }],
        )
        analysis = resp.content[0].text.strip()
        # Strip markdown links before storing — prevents them leaking into future prompts
        analysis = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', analysis)
    except Exception as e:
        logger.error("Vision analysis failed: %s", e)
        analysis = "Screenshot received but could not be analysed."

    # Store in session — will be injected into next AI turn's context
    session["screenshot_analysis"] = analysis
    # Mark this as a screenshot turn so attempt counter is skipped
    session["is_screenshot_turn"]  = True
    _save_session(session_id, session)

    # Generate a proper support reply from the analysis
    try:
        disp_resp = _client.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 120,
            messages   = [{
                "role": "user",
                "content": (
                    "You are a network IT support specialist. "
                    "A user sent a screenshot. Here is what it shows:\n\n"
                    f"{analysis}\n\n"
                    "Write one short plain-text response (max 2 sentences) that: "
                    "acknowledges what you can see, names the specific error if present, "
                    "and says what you will do next to help. "
                    "No bullet points, no markdown, no asterisks. "
                    "Never use markdown links like [text](url) — write URLs as plain text only. "
                    "Do not start with Certainly, Absolutely, Of course, Great."
                ),
            }],
        )
        display_text = disp_resp.content[0].text.strip()
        # Hard strip any markdown links that slipped through: [text](url) → text
        display_text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', display_text)
    except Exception:
        # Fallback — use analysis directly but keep it short
        display_text = f"I can see {analysis[:200].rstrip('.')}. Let me help you troubleshoot this."

    return {
        "success":        True,
        "filename":       filename,
        "display_text":   display_text,
        "analysis":       analysis,
        "cnn_label":      None,
        "cnn_confidence": 0.0,
        "cnn_domain":     None,
        "cnn_severity":   None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ROUTING
# ─────────────────────────────────────────────────────────────────────────────

def _generate_ticket_number(db: Session) -> str:
    max_t = db.query(func.max(Ticket.ticket_number)).scalar()
    if max_t:
        try:
            return f"T-{str(int(max_t.split('-')[1]) + 1).zfill(4)}"
        except Exception:
            pass
    return f"T-{str(db.query(Ticket).count() + 1001).zfill(4)}"


def _find_best_team(db: Session, domain: str, tz: str = "UTC") -> Optional[str]:
    teams = db.query(Team).filter(Team.is_active == True).all()
    if not teams: return None
    best_id, best_score = None, -999
    now = datetime.utcnow()
    for t in teams:
        score = 10 if domain in (t.domain_focus or []) else 0
        try:
            diff = abs(
                pytz.timezone(tz).utcoffset(now).total_seconds() -
                pytz.timezone(t.timezone or "UTC").utcoffset(now).total_seconds()
            ) / 3600
            score += 5 if diff == 0 else 3 if diff <= 3 else 1 if diff <= 6 else 0
        except Exception as e:
            logger.debug("Team tz offset calc skipped: %s", e)
        score -= t.active_ticket_count
        if score > best_score:
            best_score = score
            best_id    = t.id
    return best_id


def _find_best_engineer(db: Session, domain: str, tz: str = "UTC") -> Optional[str]:
    engs = db.query(Engineer, User).join(User, Engineer.user_id == User.id).filter(
        Engineer.is_activated == True,
        User.is_active == True,
        Engineer.availability_status == AvailabilityStatus.AVAILABLE,
    ).all()
    if not engs: return None
    best_id, best_score = None, -999
    now = datetime.utcnow()
    for eng, usr in engs:
        score = 10 if domain in (eng.domain_expertise or []) else 0
        try:
            diff = abs(
                pytz.timezone(tz).utcoffset(now).total_seconds() -
                pytz.timezone(usr.timezone or "UTC").utcoffset(now).total_seconds()
            ) / 3600
            score += 5 if diff == 0 else 3 if diff <= 3 else 1 if diff <= 6 else 0
        except Exception as e:
            logger.debug("Engineer tz offset calc skipped: %s", e)
        score -= eng.active_ticket_count
        if score > best_score:
            best_score = score
            best_id    = usr.id
    return best_id


# ─────────────────────────────────────────────────────────────────────────────
# ESCALATE
# ─────────────────────────────────────────────────────────────────────────────

def escalate_to_ticket(db: Session, user: User, data: EscalateRequest) -> EscalateResponse:
    with _sessions_lock:
        session = dict(_sessions.get(data.session_id, {}))
    severity = session.get("severity", "medium")
    asset    = session.get("asset_match")
    context  = session.get("asset_context", {})

    priority_map = {"critical": TicketPriority.CRITICAL, "high": TicketPriority.HIGH,
                    "medium": TicketPriority.MEDIUM, "low": TicketPriority.LOW}
    sla_map      = {"critical": 30, "high": 120, "medium": 480, "low": 1440}

    msgs    = session.get("messages", [])
    ai_msgs = [m["content"] for m in msgs if m["role"] == "assistant"]

    if context.get("diagnosis"):
        diagnosis = context["diagnosis"]
    else:
        diagnosis = ai_msgs[-1][:500] if ai_msgs else ""
        if asset:
            diagnosis += (
                f"\n\nAsset: {asset.get('identifier') or 'N/A'}"
                f"\nEnvironment: {asset.get('environment') or 'N/A'}"
                f"\nTeam: {asset.get('team') or 'N/A'}"
            )
        if context:
            qs = session.get("triage_questions", [])
            an = session.get("triage_answers", [])
            diagnosis += "\n\nUser answers:\n" + "\n".join(f"  {q} → {a}" for q, a in zip(qs, an))

    # Inject screenshot analysis into ticket diagnosis if present
    if session.get("screenshot_analysis"):
        diagnosis += f"\n\nScreenshot Analysis:\n{session['screenshot_analysis']}"

    domain_str   = "networking"
    engineer_id  = None
    team_id      = None
    routing_path = "unassigned"   # tracks how engineer/team was ultimately found

    contact_email = asset.get("contact_email", "") if asset else ""
    manager_email = asset.get("manager_email", "") if asset else ""

    logger.debug("[Route] asset_match present=%s", asset is not None)

    if contact_email:
        u = db.query(User).filter(User.email == contact_email).first()
        if u:
            eng = db.query(Engineer).filter(Engineer.user_id == u.id).first()
            if eng:
                engineer_id  = u.id
                routing_path = "asset_owner"
                logger.debug("[Route] Routed to asset owner engineer")
            else:
                t = db.query(Team).filter(Team.manager_id == u.id).first()
                if t:
                    team_id      = t.id
                    routing_path = "asset_manager_team"
                    logger.debug("[Route] Routed via manager to team")
                    members = db.query(TeamMember).filter(TeamMember.team_id == t.id).all()
                    best_eng_id, best_score = None, -999
                    for m in members:
                        eu = db.query(User).filter(User.id == m.user_id).first()
                        eo = db.query(Engineer).filter(Engineer.user_id == m.user_id).first()
                        if not eu or not eo or not eo.is_activated: continue
                        if eo.availability_status != AvailabilityStatus.AVAILABLE: continue
                        score = -eo.active_ticket_count
                        if score > best_score:
                            best_score  = score
                            best_eng_id = eu.id
                    if best_eng_id:
                        engineer_id  = best_eng_id
                        team_id      = None
                        routing_path = "asset_manager_engineer"

    if not engineer_id and manager_email:
        u = db.query(User).filter(User.email == manager_email).first()
        if u:
            t = db.query(Team).filter(Team.manager_id == u.id).first()
            if t:
                team_id      = t.id
                routing_path = "manager_email_team"

    if not engineer_id and not team_id:
        team_id = _find_best_team(db, domain_str, user.timezone or "UTC")
        if team_id:
            routing_path = "domain_team"
            logger.debug("[Route] Domain team fallback applied")

    if not engineer_id and not team_id:
        engineer_id = _find_best_engineer(db, domain_str, user.timezone or "UTC")
        if engineer_id:
            routing_path = "best_available_engineer"
            logger.debug("[Route] Engineer direct fallback applied")

    with _ticket_creation_lock:
        ticket = Ticket(
            ticket_number = _generate_ticket_number(db),
            user_id       = user.id,
            engineer_id   = engineer_id,
            team_id       = team_id,
            title         = data.title,
            description   = data.description,
            domain        = TicketDomain.NETWORKING,
            priority      = priority_map.get(severity, TicketPriority.MEDIUM),
            status        = TicketStatus.OPEN,
            steps_tried   = data.steps_tried,
            ai_diagnosis  = diagnosis.strip() or None,
            ai_attempted  = True,
            user_city     = user.city,
            user_country  = user.country,
            user_timezone = user.timezone,
            sla_deadline  = datetime.utcnow() + timedelta(minutes=sla_map.get(severity, 480)),
        )
        db.add(ticket)

        if team_id:
            t = db.query(Team).filter(Team.id == team_id).first()
            if t: t.active_ticket_count += 1
        if engineer_id:
            e = db.query(Engineer).filter(Engineer.user_id == engineer_id).first()
            if e: e.active_ticket_count += 1

        db.commit()
        db.refresh(ticket)
    logger.info("[Ticket] %s created | team_assigned=%s | engineer_assigned=%s",
                ticket.ticket_number, team_id is not None, engineer_id is not None)

    with _sessions_lock:
        _sessions.pop(data.session_id, None)
    _delete_session_redis(data.session_id)

    eng_name = eng_email = eng_city = eng_tz = eng_id_str = None
    t_name   = t_id_str = None
    r_type   = r_reason = None

    _routing_reason_map = {
        "asset_owner":              "Routed to the registered owner of this asset.",
        "asset_manager_engineer":   "Routed to best available engineer in the asset manager's team.",
        "asset_manager_team":       "Routed to the asset manager's team.",
        "manager_email_team":       "Routed to the team managed by the asset manager.",
        "domain_team":              "Routed to best matching team by domain and timezone.",
        "best_available_engineer":  "Routed to the best available engineer by domain and timezone.",
    }

    if engineer_id:
        eu = db.query(User).filter(User.id == engineer_id).first()
        eo = db.query(Engineer).filter(Engineer.user_id == engineer_id).first()
        if eu:
            eng_name  = eu.full_name
            eng_email = eu.email
            eng_city  = eu.city
            eng_tz    = eu.timezone
        if eo:
            eng_id_str = eo.engineer_id
        r_type   = routing_path
        r_reason = _routing_reason_map.get(routing_path, "Routed to engineer.")
    elif team_id:
        to = db.query(Team).filter(Team.id == team_id).first()
        if to:
            t_name   = to.name
            t_id_str = to.team_id
        r_type   = routing_path
        r_reason = _routing_reason_map.get(routing_path, "Routed to team.")

    return EscalateResponse(
        ticket_id         = ticket.id,
        ticket_number     = ticket.ticket_number,
        message           = f"Ticket {ticket.ticket_number} raised.",
        routing_type      = r_type,
        routing_reason    = r_reason,
        engineer_name     = eng_name,
        engineer_id       = eng_id_str,
        engineer_email    = eng_email,
        engineer_city     = eng_city,
        engineer_timezone = eng_tz,
        team_name         = t_name,
        team_id           = t_id_str,
        asset_instance    = asset.get("identifier") if asset else None,
        asset_environment = asset.get("environment") if asset else None,
        asset_team        = asset.get("team") if asset else None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# USER TICKETS
# ─────────────────────────────────────────────────────────────────────────────

def get_user_tickets(db: Session, user: User) -> list:
    return [_ticket_resp(db, t) for t in
            db.query(Ticket).filter(Ticket.user_id == user.id)
            .order_by(Ticket.created_at.desc()).limit(100).all()]


def get_user_ticket(db: Session, user: User, ticket_id: str) -> UserTicketResponse:
    t = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user.id).first()
    if not t:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _ticket_resp(db, t)


def _ticket_resp(db: Session, ticket: Ticket) -> UserTicketResponse:
    eng_name = eng_id = eng_city = eng_country = eng_tz = eng_email = None
    team_name = team_id_str = team_manager_email = None

    if ticket.engineer_id:
        eu = db.query(User).filter(User.id == ticket.engineer_id).first()
        eo = db.query(Engineer).filter(Engineer.user_id == ticket.engineer_id).first()
        if eu:
            eng_name    = eu.full_name
            eng_email   = eu.email
            eng_city    = eu.city
            eng_country = eu.country
            eng_tz      = eu.timezone
        if eo:
            eng_id = eo.engineer_id

    if ticket.team_id:
        team = db.query(Team).filter(Team.id == ticket.team_id).first()
        if team:
            team_name   = team.name
            team_id_str = team.team_id
            if team.manager_id:
                mgr = db.query(User).filter(User.id == team.manager_id).first()
                if mgr:
                    team_manager_email = mgr.email
    elif ticket.engineer_id:
        member = db.query(TeamMember).filter(TeamMember.user_id == ticket.engineer_id).first()
        if member:
            team = db.query(Team).filter(Team.id == member.team_id).first()
            if team:
                team_name   = team.name
                team_id_str = team.team_id
                if team.manager_id:
                    mgr = db.query(User).filter(User.id == team.manager_id).first()
                    if mgr:
                        team_manager_email = mgr.email

    return UserTicketResponse(
        id                  = ticket.id,
        ticket_number       = ticket.ticket_number,
        title               = ticket.title,
        domain              = ticket.domain,
        priority            = ticket.priority,
        status              = ticket.status,
        engineer_name       = eng_name,
        engineer_id         = eng_id,
        engineer_email      = eng_email,
        engineer_city       = eng_city,
        engineer_country    = eng_country,
        engineer_timezone   = eng_tz,
        team_name           = team_name,
        team_id             = team_id_str,
        team_manager_email  = team_manager_email,
        created_at          = ticket.created_at,
        updated_at          = ticket.updated_at,
        resolved_at         = ticket.resolved_at,
    )