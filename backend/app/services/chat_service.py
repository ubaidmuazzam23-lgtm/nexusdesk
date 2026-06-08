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

from app.core.config import settings
from app.models.user import User
from app.models.ticket import Ticket, TicketStatus, TicketPriority, TicketDomain
from app.models.engineer import Engineer, AvailabilityStatus
from app.models.team import Team, TeamMember
from app.schemas.chat import (
    ChatMessageRequest, ChatMessageResponse,
    EscalateRequest, EscalateResponse, UserTicketResponse,
)

_client    = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
_sessions: dict = {}

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

SYSTEM_PROMPT = """You are a Network IT support specialist. You ONLY handle networking issues.

STRICT FORMATTING:
- Plain sentences only. No bullet points, no markdown, no asterisks.
- Never use markdown links like [text](url) — write URLs as plain text only.
- Under 150 words per response.
- One question at a time.
- Never start with "Certainly", "Absolutely", "Of course", "Great".

KNOWLEDGE BASE PRIORITY:
- If knowledge base content is provided → read it fully and follow the most relevant procedure.
- If no knowledge base content is relevant → use your own networking expertise.
- Always try to solve the issue.

DNS / NETSKOPE DETECTION — CRITICAL:
Whenever conversation contains ANY of these signals:
- "site can't be reached", "this site can't be reached"
- "ERR_NAME_NOT_RESOLVED", "cannot resolve host", "could not find host"
- "connection error" for a specific URL or application
- Any specific URL or domain name that is not accessible
- "cannot access" any specific application or URL

IMMEDIATELY run this DNS check flow — do NOT ask generic questions:
Step 1: Ask user to run DNS check:
  Mac/Linux: host <url>
  Windows: nslookup <url>
Step 2: Analyse result:
  - IP starts with 191.x.x.x → Netskope routing correct, check app layer
  - Any other IP (103.x, 52.x, 142.x etc.) → "DNS is resolving to [IP] instead of 191.x.x.x — this is a Netskope routing issue. Please disconnect and reconnect Netskope, then run the DNS check again."
  - NXDOMAIN or cannot resolve → DNS zone issue, check BIND9 and zone files

PLACEHOLDERS: Ask for real values when you see <placeholder> in runbook. Never show placeholders.

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
    if sid not in _sessions:
        _sessions[sid] = {
            "messages":           [],
            "flow_step":          "broken",     # broken → impacting → multi_customer → ai_analysis
                                                 #        → consult → details → deadline → help_today → ai_analysis
            "domain":             "networking",  # always networking
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
        }
    return _sessions[sid]


# ─────────────────────────────────────────────────────────────────────────────
# CLAUDE CALL
# ─────────────────────────────────────────────────────────────────────────────

def _call_claude(session: dict, system: str, extra_hint: str = "") -> tuple:
    """One API call. Returns (reply, domain, severity, is_networking)."""
    if extra_hint:
        system = system + f"\n\nHINT: {extra_hint}"

    resp = _client.messages.create(
        model      = "claude-sonnet-4-5",
        max_tokens = 400,
        system     = system,
        messages   = session["messages"],
    )
    raw = resp.content[0].text.strip()

    domain       = "networking"
    severity     = session.get("severity") or "medium"
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

    return clean, domain, severity, is_networking


# ─────────────────────────────────────────────────────────────────────────────
# RAG CONTEXT
# ─────────────────────────────────────────────────────────────────────────────

def _get_rag(query: str) -> str:
    """Search knowledge base for relevant runbook content."""
    try:
        from app.services.knowledge_service import get_rag_context
        return get_rag_context(query, domain="networking", n_results=10)
    except Exception:
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
    """Handle response to 'is something broken' — use Claude to detect intent."""
    msg = message.lower().strip()

    # Direct consult signals — skip question, go straight to details
    consult_direct = ["consult", "question", "advice", "guidance", "help with", "how do i",
                      "wondering", "planning", "need to know", "asking about"]
    if any(s in msg for s in consult_direct):
        session["flow_step"] = "waiting_details"
        reply = "What is it regarding? Please provide more detail — designs, links, screenshots, Epic tickets or any other context that would help."
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)

    # Direct broken signals
    broken_direct = ["broken", "down", "not working", "outage", "crash", "fail", "error",
                     "can't access", "cannot access", "unreachable", "not responding"]
    if any(s in msg for s in broken_direct):
        session["flow_step"] = "waiting_impacting"
        reply = "Is this customer impacting? Are end users or customers unable to access services because of this?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)

    # Ambiguous — use Claude to detect intent
    try:
        from app.core.config import settings as _s
        import anthropic as _a
        _cl = _a.Anthropic(api_key=_s.ANTHROPIC_API_KEY)
        resp = _cl.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 10,
            messages   = [{"role": "user", "content": (
                f"Is this message reporting a broken/urgent IT issue (BROKEN) or asking a question/consult (CONSULT)? "
                f"Reply only BROKEN or CONSULT.\nMessage: {msg}"
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
        # Customer impacting → ask how many
        session["flow_step"] = "waiting_multi_customer"
        reply = "Are more than one customer or user impacted by this?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)
    else:
        # Not customer impacting → ask for problem description first
        session["flow_step"] = "waiting_problem"
        reply = "Can you describe what's happening? What exactly is the issue?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)


def _handle_multi_customer(session: dict, sid: str, message: str) -> ChatMessageResponse:
    """Handle response to 'more than 1 customer'."""
    msg = message.lower().strip()
    yes_signals = ["yes", "yeah", "multiple", "many", "more than", "several",
                   "all", "everyone", "widespread", "2", "3", "4", "5"]

    if any(s in msg for s in yes_signals):
        # Major incident → AI gathers info then raises CRITICAL ticket
        session["flow_step"]   = "ai_analysis"
        session["flow_origin"] = "major_incident"
        session["severity"]    = "critical"
        session["solve_attempts"] = 0
        return _start_ai_analysis(session, sid)
    else:
        # Single customer → ask for problem description first
        session["flow_step"] = "waiting_problem"
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

    # Use Claude to detect if deadline is already mentioned in the description
    try:
        from app.core.config import settings as _s
        import anthropic as _a
        _cl = _a.Anthropic(api_key=_s.ANTHROPIC_API_KEY)
        resp = _cl.messages.create(
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
        # Deadline already mentioned — skip asking, go to need help today
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

    # Use Claude to determine if user has a deadline
    from app.core.config import settings as _s
    import anthropic as _a
    _cl = _a.Anthropic(api_key=_s.ANTHROPIC_API_KEY)
    try:
        resp = _cl.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 10,
            messages   = [{"role": "user", "content": (
                f"Does this message indicate there IS a deadline or time constraint? "
                f"Reply only YES or NO.\nMessage: {msg}"
            )}],
        )
        has_deadline = "YES" in resp.content[0].text.upper()
    except Exception:
        # Fallback to keyword check
        has_deadline = any(s in msg for s in ["yes", "yeah", "deadline", "urgent", "asap",
                           "today", "tomorrow", "by end", "next month", "this week", "due"])

    if has_deadline:
        session["flow_step"] = "waiting_help_today"
        reply = "Do you need help with this today?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)
    else:
        # Even with no deadline, ask if they need help today
        session["flow_step"] = "waiting_help_today"
        reply = "Do you need help with this today?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)


def _handle_help_today(session: dict, sid: str, message: str) -> ChatMessageResponse:
    """Handle 'need help today' question."""
    msg = message.lower().strip()
    yes_signals = ["yes", "yeah", "today", "now", "urgent", "asap", "immediately"]

    if any(s in msg for s in yes_signals):
        # Need help today → AI analysis
        session["flow_step"]   = "ai_analysis"
        session["flow_origin"] = "consult"
        return _start_ai_analysis(session, sid)
    else:
        # Not needed today → ask combined sprint/release question
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

    # Get RAG context from knowledge base
    problem = session.get("problem", "")
    if not problem:
        # Build problem from conversation
        user_msgs = [m["content"] for m in session["messages"] if m["role"] == "user"]
        problem   = " ".join(user_msgs[:3])

    # Use existing RAG context if already fetched, otherwise fetch now
    rag_context = session.get("rag_context") or _get_rag(problem)
    session["rag_context"] = rag_context

    # Build system with RAG
    if rag_context:
        system = (
            "You are a Network IT support specialist handling all networking issues including DNS, BGP, OSPF, VPN, firewall, routing, switching, Netskope, and any network connectivity problems.\n\n"
            "FORMATTING: Plain sentences only. No markdown. No asterisks. No bullet points.\n"
            "Never use markdown links like [text](url) — write URLs as plain text only.\n"
            "Under 150 words. One question at a time.\n"
            "Never start with Certainly, Absolutely, Of course, Great.\n\n"
            "COMMANDS: Always show Mac/Linux AND Windows versions for every command.\n\n"
            "NETWORKING SCOPE: Only handle networking issues. If the issue is clearly not networking "
            "(e.g. printer driver, HR software bug, payroll system) tell the user this is outside your scope "
            "and suggest they contact the relevant team. Do not raise a ticket for non-networking issues.\n\n"
            "KNOWLEDGE BASE: A runbook is provided below. Follow it exactly for issues it covers. "
            "For issues NOT in the runbook, use your own networking expertise to troubleshoot.\n\n"
            "CRITICAL RULE: Read the ENTIRE runbook first. Find the most relevant procedure. "
            "Execute Step 1 of that procedure RIGHT NOW. "
            "DO NOT ask questions not in the runbook procedure.\n\n"
            f"{rag_context}\n\n"
            "Now execute Step 1 of the most relevant procedure. Nothing else."
        )
        hint = "Execute Step 1 of the most relevant procedure from the runbook right now."
        # Override for consult flow — don't follow troubleshooting steps
        if session.get("flow_origin") == "major_incident":
            n_mi = session.get("solve_attempts", 0)
            if n_mi == 0:
                hint = (
                    "This is a MAJOR INCIDENT affecting multiple customers. "
                    "Ask focused triage questions to understand scope. "
                    "Ask: How many customers are affected and which services are down?"
                )
            elif n_mi == 1:
                hint = "Ask: What is the current impact level — complete outage, degraded service, or intermittent?"
            elif n_mi == 2:
                hint = "Ask: When did this start and were there any recent changes or maintenance?"
            else:
                hint = (
                    "You have enough information. "
                    "Summarise the incident clearly and tell the user a CRITICAL ticket is being raised immediately. "
                    "End with [STEPS_EXHAUSTED]."
                )
        elif session.get("flow_origin") == "consult":
            remaining = max(0, 6 - session.get("solve_attempts", 0))
            hint = (
                f"This is a network team consultation. You have {remaining} quality exchanges remaining. "
                f"Ask ONE focused technical question to extract maximum useful information. "
                f"Focus on: technical details, constraints, current state, requirements, integrations. "
                f"Do NOT mention escalation, the network team, or handing off to anyone. "
                f"Do NOT say you will connect them with an architect or raise a request. "
                f"Just ask the next most important technical question."
            )
        elif session.get("flow_origin") == "planning":
            timeline = session.get("planning_timeline", "future")
            remaining = max(0, 4 - session.get("solve_attempts", 0))
            hint = (
                f"This request is scheduled for: {timeline}. "
                f"You have {remaining} exchanges to gather planning context for the network team. "
                f"Ask ONE focused question about: technical scope, dependencies, blockers, "
                f"business priority, success criteria, or contact person. "
                f"Do NOT mention escalation or handing off. Just gather planning information."
            )
    else:
        system = SYSTEM_PROMPT
        if session.get("flow_origin") == "consult":
            remaining = max(0, 6 - session.get("solve_attempts", 0))
            hint = (
                f"This is a network team consultation. You have {remaining} exchanges remaining. "
                f"Ask ONE focused technical question to extract maximum useful information. "
                f"Focus on: technical details, constraints, current state, requirements, integrations. "
                f"Do NOT mention escalation, the network team, or handing off to anyone. "
                f"Do NOT say you will connect them with an architect or raise a request. "
                f"Just ask the next most important technical question."
            )
        elif session.get("flow_origin") == "planning":
            timeline = session.get("planning_timeline", "future")
            remaining = max(0, 4 - session.get("solve_attempts", 0))
            hint = (
                f"This request is scheduled for: {timeline}. "
                f"You have {remaining} exchanges to gather planning context for the network team. "
                f"Ask ONE focused question about: technical scope, dependencies, blockers, "
                f"business priority, success criteria, or contact person. "
                f"Do NOT mention escalation or handing off. Just gather planning information."
            )
        else:
            hint = (
                "No runbook found for this issue. "
                "First verify this is a networking issue. If it is, use your own networking expertise to troubleshoot — "
                "give one specific step. If it is clearly NOT a networking issue, tell the user politely and suggest "
                "they contact the relevant team."
            )

    reply, domain, severity, is_networking = _call_claude(session, system, hint)

    session["domain"]       = domain
    session["severity"]     = severity
    session["is_networking"] = is_networking

    # Only count as attempt if bot gave actual fix/command, not just an info question
    # Detect if reply contains a command or fix action
    has_command = any(kw in reply.lower() for kw in [
        "run this", "run the", "execute", "try this", "type this",
        "nslookup", "ping", "flush", "restart", "reconnect", "disconnect",
        "sudo", "ipconfig", "systemctl", "rndc", "traceroute", "host ",
        "check if", "verify", "open terminal", "command prompt"
    ])
    if has_command or session.get("flow_origin") in ("consult", "planning", "major_incident"):
        session["solve_attempts"] += 1

    session["messages"].append({"role": "assistant", "content": reply})

    return _make_response(sid, session, reply, can_escalate=False)


def _continue_ai_analysis(session: dict, sid: str, message: str) -> ChatMessageResponse:
    """Continue AI analysis — check if resolved or needs escalation."""
    # Check if resolved — use Claude to avoid false positives like ERR_NAME_NOT_RESOLVED
    try:
        from app.core.config import settings as _s
        import anthropic as _a
        _cl = _a.Anthropic(api_key=_s.ANTHROPIC_API_KEY)
        resp = _cl.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 10,
            messages   = [{"role": "user", "content": (
                f"Is the user saying their IT issue is now fixed/resolved/working? "
                f"Reply YES or NO only. Do not say YES if they are just describing an error message.\\n"
                f"Message: {message}"
            )}],
        )
        is_resolved = "YES" in resp.content[0].text.upper()
    except Exception:
        is_resolved = False

    if is_resolved:
        reply = "Glad that sorted it out. Feel free to reach out if anything else comes up."
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, resolved=True)

    session["solve_attempts"] += 1
    rag_context = session.get("rag_context", "")
    has_runbook = bool(rag_context)
    print(f"  [Major] flow_origin={session.get('flow_origin')} solve_attempts={session['solve_attempts']}")

    if rag_context:
        system = SYSTEM_PROMPT + (
            f"\n\n{rag_context}\n\n"
            "STRICT INSTRUCTION: Follow the runbook procedures exactly. "
            "Do NOT ask questions outside of the runbook steps. "
            "When ALL runbook steps are exhausted and issue is still not resolved, end with [STEPS_EXHAUSTED]."
        )
    else:
        system = SYSTEM_PROMPT

    n = session["solve_attempts"]
    is_consult = session.get("flow_origin") == "consult"

    # Consult flow — no attempt limits, no mid-check, no escalation message
    # Just keep advising until user is satisfied, then post summary to #network-consult
    if is_consult:
        max_attempts = 6  # 6 exchanges then post summary to network-consult
    else:
        # Runbook: follow all steps until [STEPS_EXHAUSTED]
        # No runbook: 6 attempts total
        max_attempts = 10 if has_runbook else 6

    if n >= max_attempts and not is_consult:
        escalate = True
        reply    = "I have exhausted all troubleshooting steps. I will now escalate this to the network engineering team."
        session["messages"].append({"role": "assistant", "content": reply})
    elif session.get("flow_origin") == "major_incident" and n >= 4:
        reply = "I have gathered enough details. Raising a CRITICAL ticket immediately and notifying the network engineering team."
        session["messages"].append({"role": "assistant", "content": reply})
        session["domain"]   = "networking"
        session["severity"] = "critical"
        session["flow_step"] = "triage"
        session["triage_started"] = True
        return _make_response(sid, session, reply, can_escalate=True)
    elif n >= max_attempts and is_consult:
        # Consult — wrap up and post summary to #network-consult
        reply = "I have gathered enough context. I will share this with the network team who will follow up with you."
        session["messages"].append({"role": "assistant", "content": reply})
        session["flow_step"] = "consult_complete"
        return _make_response(sid, session, reply, can_escalate=True)
    elif n >= 4 and session.get("flow_origin") == "planning":
        # Planning — wrap up and post planning brief to #network-consult
        reply = "I have all the planning details I need. I will share this with the network team so they are ready when the time comes."
        session["messages"].append({"role": "assistant", "content": reply})
        session["flow_step"] = "consult_complete"
        return _make_response(sid, session, reply, can_escalate=True)
    else:
        # Mid-point check at attempt 3 (no runbook only, broken flow only — not consult)
        if not has_runbook and n == 3 and not session.get("mid_check_done") and not is_consult and session.get("flow_origin") not in ("planning", "major_incident"):
            session["mid_check_done"] = True
            reply = (
                "I have tried 3 troubleshooting steps so far and the issue is still not resolved. "
                "Would you like me to try a few more steps, or shall I raise a ticket and escalate this to the network engineering team?"
            )
            session["messages"].append({"role": "assistant", "content": reply})
            session["flow_step"] = "mid_check"
            return _make_response(sid, session, reply, can_escalate=False)

        # Runbook mid-check at step 5 (first 2 are usually diagnostic questions)
        if has_runbook and n == 5 and not session.get("mid_check_done") and session.get("flow_origin") != "major_incident":
            session["mid_check_done"] = True
            reply = (
                "I have gone through several troubleshooting steps and the issue is still not resolved. "
                "Would you like me to continue with more steps, or shall I raise a ticket and escalate to the network engineering team?"
            )
            session["messages"].append({"role": "assistant", "content": reply})
            session["flow_step"] = "mid_check"
            return _make_response(sid, session, reply, can_escalate=False)

        if has_runbook:
            hint = (
                "Follow the next step from the runbook. "
                "If you have covered ALL steps and issue is still not resolved, "
                "tell the user you will escalate to the network engineering team. "
                "End your reply with [STEPS_EXHAUSTED] only when ALL runbook steps are done. "
                "IMPORTANT: Always include a proper sentence before [STEPS_EXHAUSTED]."
            )
        else:
            hint = (
                f"Attempt {n} of 6. Give ONE specific troubleshooting step. "
                f"Different from what was already tried."
            )

        reply, domain, severity, is_networking = _call_claude(session, system, hint)

        escalate = "[STEPS_EXHAUSTED]" in reply
        reply    = reply.replace("[STEPS_EXHAUSTED]", "").strip()

        if not reply:
            reply = "I have gone through all the troubleshooting steps. I will now escalate this to the network engineering team."
            escalate = True

        session["messages"].append({"role": "assistant", "content": reply})
        session["domain"]        = domain
        session["severity"]      = severity
        session["is_networking"] = is_networking

        if not escalate:
            return _make_response(sid, session, reply, can_escalate=False)

    # Escalate to triage
    session["flow_step"]      = "triage"
    session["triage_started"] = True
    return _make_response(sid, session, reply, can_escalate=False)


# ─────────────────────────────────────────────────────────────────────────────
# TRIAGE
# ─────────────────────────────────────────────────────────────────────────────

def _start_triage_db(db: Optional[Session], session: dict, sid: str) -> ChatMessageResponse:
    """Start asset triage from DB."""
    try:
        if db:
            from app.services.asset_identifier_service import generate_questions, fetch_assets
            domain  = session["domain"] or "networking"
            problem = session["problem"]
            rows, _ = fetch_assets(db, domain, problem)
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
                print(f"  [Triage] Filter: {col}={val}")

        if session["triage_filters"]:
            result = progressive_match(db, session["triage_filters"], rows)
            session["asset_match"] = result.get("matched")
            candidates             = result.get("candidates", 0)
            print(f"  [Triage] Candidates: {candidates} confident={result['confident']}")

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
        print(f"  [Triage] Error: {e}")

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

    msg = data.message.strip()

    # Store problem on first message
    if not session["problem"] and msg:
        session["problem"] = msg[:400]

    # Triage active — handle answer
    if session["triage_active"]:
        session["messages"].append({"role": "user", "content": msg})
        return _handle_triage_answer(db, session, sid, msg)

    # Triage started but not yet active — start triage on next message
    if session.get("flow_step") == "triage" and not session.get("triage_active") and session.get("triage_started"):
        session["messages"].append({"role": "user", "content": msg})
        return _start_triage_db(db, session, sid)

    # Append user message
    session["messages"].append({"role": "user", "content": msg})

    step = session["flow_step"]
    print(f"  [Chat] Flow step={step}")

    # ── FLOW ROUTING ──────────────────────────────────────────────────────────

    # Step 1: Ask if broken (first message)
    if step == "broken":
        session["problem"] = msg[:400]
        return _handle_broken(session, sid, msg)

    # Step 2: Waiting for broken answer
    elif step == "waiting_broken":
        return _handle_broken(session, sid, msg)

    # Step 3: Waiting for customer impacting answer
    elif step == "waiting_impacting":
        return _handle_impacting(session, sid, msg)

    # Step 4: Waiting for multi-customer answer
    elif step == "waiting_multi_customer":
        return _handle_multi_customer(session, sid, msg)

    # Step 5: Consult flow
    elif step == "waiting_consult":
        return _handle_consult(session, sid, msg)

    elif step == "waiting_details":
        return _handle_details(session, sid, msg)

    elif step == "waiting_deadline":
        return _handle_deadline(session, sid, msg)

    elif step == "waiting_help_today":
        return _handle_help_today(session, sid, msg)

    # Waiting for problem description — immediately search runbook and start AI
    elif step == "waiting_problem":
        session["problem"] = msg[:400]
        session["flow_step"] = "ai_analysis"
        session["flow_origin"] = "broken"
        # Get RAG context immediately based on problem description
        rag_context = _get_rag(msg)
        session["rag_context"] = rag_context
        return _start_ai_analysis(session, sid)

    # Mid-check — user decides continue or escalate
    elif step == "mid_check":
        msg_lower = msg.lower()
        if any(w in msg_lower for w in ["ticket", "escalate", "raise", "engineer", "no", "nope", "just raise"]):
            session["flow_step"]      = "triage"
            session["triage_started"] = True
            return _start_triage_db(db, session, sid)
        else:
            # Continue troubleshooting
            session["flow_step"] = "ai_analysis"
            return _continue_ai_analysis(session, sid, msg)

    # AI Analysis
    elif step == "ai_analysis":
        return _continue_ai_analysis(session, sid, msg)

    # Combined sprint/release question
    elif step == "waiting_next_sprint":
        # Use Claude to detect timeline from user answer
        try:
            from app.core.config import settings as _s
            import anthropic as _a
            _cl = _a.Anthropic(api_key=_s.ANTHROPIC_API_KEY)
            resp = _cl.messages.create(
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
        return _start_ai_analysis(session, sid)

    # Major incident, next sprint, consult complete — done
    elif step in ("major_incident", "next_sprint", "consult_complete"):
        reply = "Is there anything else I can help with?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply)

    # Default — start flow
    else:
        session["flow_step"] = "broken"
        session["problem"]   = msg[:400]
        return _handle_broken(session, sid, msg)


# ─────────────────────────────────────────────────────────────────────────────
# SCREENSHOT
# ─────────────────────────────────────────────────────────────────────────────

def analyze_screenshot(image_bytes: bytes, session_id: str, user_id: str) -> dict:
    session  = _get_session(session_id)
    filename = f"{user_id}_{session_id[:8]}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    session["screenshot_path"] = filepath
    return {
        "success":        True,
        "filename":       filename,
        "display_text":   "Screenshot received. Can you describe what you are seeing?",
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
        try: return f"T-{str(int(max_t.split('-')[1]) + 1).zfill(4)}"
        except: pass
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
        except Exception: pass
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
        except Exception: pass
        score -= eng.active_ticket_count
        if score > best_score:
            best_score = score
            best_id    = usr.id
    return best_id


# ─────────────────────────────────────────────────────────────────────────────
# ESCALATE
# ─────────────────────────────────────────────────────────────────────────────

def escalate_to_ticket(db: Session, user: User, data: EscalateRequest) -> EscalateResponse:
    session  = _sessions.get(data.session_id, {})
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

    domain_str  = "networking"  # always networking
    engineer_id = None
    team_id     = None

    contact_email = asset.get("contact_email", "") if asset else ""
    manager_email = asset.get("manager_email", "") if asset else ""

    print(f"  [Route] asset_match={asset}")
    print(f"  [Route] contact_email={contact_email} manager_email={manager_email}")

    if contact_email:
        u = db.query(User).filter(User.email == contact_email).first()
        if u:
            eng = db.query(Engineer).filter(Engineer.user_id == u.id).first()
            if eng:
                engineer_id = u.id
                print(f"  [Route] Asset owner: {contact_email}")
            else:
                t = db.query(Team).filter(Team.manager_id == u.id).first()
                if t:
                    team_id = t.id
                    print(f"  [Route] Manager → team: {contact_email}")
                    members = db.query(TeamMember).filter(TeamMember.team_id == t.id).all()
                    best_eng_id, best_score = None, -999
                    for m in members:
                        eu = db.query(User).filter(User.id == m.user_id).first()
                        eo = db.query(Engineer).filter(Engineer.user_id == m.user_id).first()
                        if not eu or not eo or not eo.is_activated: continue
                        if str(eo.availability_status) not in ("available", "AvailabilityStatus.AVAILABLE"): continue
                        score = -eo.active_ticket_count
                        if score > best_score:
                            best_score  = score
                            best_eng_id = eu.id
                    if best_eng_id:
                        engineer_id = best_eng_id
                        team_id     = None

    if not engineer_id and manager_email:
        u = db.query(User).filter(User.email == manager_email).first()
        if u:
            t = db.query(Team).filter(Team.manager_id == u.id).first()
            if t:
                team_id = t.id

    if not engineer_id and not team_id:
        team_id = _find_best_team(db, domain_str, user.timezone or "UTC")
        if team_id: print(f"  [Route] Domain team fallback")

    if not engineer_id and not team_id:
        engineer_id = _find_best_engineer(db, domain_str, user.timezone or "UTC")
        if engineer_id: print(f"  [Route] Engineer fallback")

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
    print(f"  [Ticket] {ticket.ticket_number} | networking | team={team_id} | eng={engineer_id}")

    if data.session_id in _sessions:
        del _sessions[data.session_id]

    eng_name = eng_email = eng_city = eng_tz = eng_id_str = None
    t_name   = t_id_str = None
    r_type   = r_reason = None

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
        r_type   = "asset_owner"
        r_reason = "Routed to the registered owner of this asset."
    elif team_id:
        to = db.query(Team).filter(Team.id == team_id).first()
        if to:
            t_name   = to.name
            t_id_str = to.team_id
        r_type   = "domain_team"
        r_reason = "Routed to best matching team by domain and timezone."

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
            .order_by(Ticket.created_at.desc()).all()]


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