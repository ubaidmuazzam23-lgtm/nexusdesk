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

SYSTEM_PROMPT = """You are a Network IT support specialist. You handle ALL networking issues including DNS, BGP, OSPF, EIGRP, VPN, firewall, routing, switching, Netskope, VLAN, MPLS, SD-WAN, wireless, and any routing protocol problem.

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

SCOPE: Handle ALL networking issues yourself — DNS, BGP, OSPF, EIGRP, MPLS, VPN, firewall, routing, switching, Netskope, VLAN, SD-WAN, wireless, peering, AS numbers, routing protocols, network security. NEVER tell the user to contact a BGP specialist, routing team, or network engineering team mid-conversation. If you cannot solve it yourself, exhaust all troubleshooting steps first, then escalate via ticket. Only redirect away if the issue is clearly not networking at all (e.g. printer driver, HR software, payroll system, laptop screen broken).

DNS / NETSKOPE DETECTION — CRITICAL:
Whenever conversation contains ANY of these signals:
- "site can't be reached", "this site can't be reached"
- "ERR_NAME_NOT_RESOLVED", "cannot resolve host", "could not find host"
- "connection error" for a specific URL or application
- Any specific URL or domain name that is not accessible
- "cannot access" any specific application or URL

IMMEDIATELY run this DNS check flow:
Step 1: If you do NOT already have the exact domain or URL from the conversation, ask for it.
  Ask: "What is the exact URL or domain name you are trying to access?"
  Never give a command with a placeholder. Only proceed once you have the real domain.
Step 2: Ask the user to run the DNS check using the REAL domain substituted in:
  Mac/Linux: host real-domain.example.com
  Windows: nslookup real-domain.example.com
Step 3: Analyse result:
  - IP starts with 191.x.x.x → Netskope routing correct, check app layer
  - Any other IP (103.x, 52.x, 142.x etc.) → Netskope routing issue. Ask user to disconnect and reconnect Netskope, then run DNS check again.
  - NXDOMAIN or cannot resolve → DNS zone issue, check BIND9 and zone files
Step 4: If IP is still wrong after reconnect → ask user to flush DNS cache:
  Mac: sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder
  Windows: ipconfig /flushdns
  Then run DNS check again.
Step 5: If IP is still wrong after flush → tell user this domain is not in the Netskope steering policy and must be added by the network team. Do not ask for the URL again — you already have it. End with [STEPS_EXHAUSTED].

PLACEHOLDERS: Never show any placeholder in commands. Before writing any command, scan the entire conversation for known values (IP addresses, hostnames, AS numbers, interface names, router-ids, peer IPs, group names) and substitute them directly. Examples of forbidden placeholders: <destination-ip>, <remote-peer-ip>, <hostname>, <group-name>, <interface>, <as-number>, <your-portal-url>. If a value is not yet known, ask for it first. Never show a placeholder to the user.

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
            # Screenshot state
            "screenshot_analysis": None,   # filled when user sends image
            "is_screenshot_turn":  False,  # True for the one turn after image arrives
        }
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

    resp = _client.messages.create(
        model      = "claude-sonnet-4-5",
        max_tokens = 400,
        system     = system,
        messages   = messages,
    )
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
    Ask Claude whether this reply contains a real diagnostic action
    (command to run, service to restart, config change) as opposed to
    a visual/UI navigation step or informational question.

    Screenshot turns NEVER count regardless of reply content.
    """
    # Screenshot turn → never count
    if is_screenshot_turn:
        return False

    try:
        resp = _client.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 5,
            messages   = [{"role": "user", "content": (
                "Does the following IT support reply ask the user to run a real diagnostic "
                "command, restart a service, flush a cache, or make a config change?\n\n"
                "Reply YES only if the reply contains an actual command to execute "
                "(e.g. ping, nslookup, traceroute, ipconfig /flushdns, systemctl restart, "
                "show ip bgp summary, configure terminal, disconnect/reconnect a service).\n\n"
                "Reply NO if the reply:\n"
                "- Asks a question to gather information (e.g. 'what AS number?', 'which vendor?', 'what OS?')\n"
                "- Gives navigation instructions (click, open settings, go to)\n"
                "- Explains or describes something\n"
                "- Confirms a diagnosis without giving a command to run\n"
                "- Asks the user to confirm something\n\n"
                f"Reply:\n{reply[:600]}"
            )}],
        )
        return "YES" in resp.content[0].text.strip().upper()
    except Exception:
        # Fail safe — don't count on error
        return False


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
        session["flow_step"] = "waiting_multi_customer"
        reply = "Are more than one customer or user impacted by this?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)
    else:
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
        session["flow_step"]   = "ai_analysis"
        session["flow_origin"] = "major_incident"
        session["severity"]    = "critical"
        session["solve_attempts"] = 0
        return _start_ai_analysis(session, sid)
    else:
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
    yes_signals = ["yes", "yeah", "today", "now", "urgent", "asap", "immediately"]

    if any(s in msg for s in yes_signals):
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

    # Fetch RAG for all flows including consult
    is_consult_or_planning = session.get("flow_origin") in ("consult", "planning")
    rag_context = session.get("rag_context") or _get_rag(problem)
    session["rag_context"] = rag_context

    # Inject screenshot analysis into context if present
    screenshot_ctx = ""
    if session.get("screenshot_analysis"):
        screenshot_ctx = (
            f"\n\nSCREENSHOT ANALYSIS:\n{session['screenshot_analysis']}\n"
            "Use this visual context to inform your next step."
        )

    is_screenshot_turn = session.get("is_screenshot_turn", False)

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
            "Troubleshoot fully, then escalate via ticket if unresolved. "
            "Only redirect if clearly not networking at all (printer driver, HR software, payroll).\n\n"
            + "KNOWLEDGE BASE: Reference material is provided below for context.\n\n"
            + ("" if is_consult_or_planning else
               "CRITICAL RULE: Read the ENTIRE runbook first. Find the most relevant procedure. "
               "Execute Step 1 of that procedure RIGHT NOW. "
               "DO NOT ask questions not in the runbook procedure.\n\n")
            + f"{rag_context}"
            + f"{screenshot_ctx}\n\n"
            + ("" if is_consult_or_planning else "Now execute Step 1 of the most relevant procedure. Nothing else.")
        )
        hint = "Execute Step 1 of the most relevant procedure from the runbook right now."

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
            problem_ctx = f"The consultation is about: {session.get('problem', '')}. " if session.get("problem") else ""
            hint = (
                f"This is a network team consultation. You have {remaining} quality exchanges remaining. "
                f"{problem_ctx}"
                f"Your goal is to gather maximum useful technical information for the network engineer who will implement this. "
                f"Ask ONE focused technical question about the network infrastructure, devices, scale, IP ranges, security requirements, or constraints. "
                f"Do NOT ask for contact details, email addresses, or non-technical information. "
                f"Do NOT provide configuration steps, commands, implementation plans, or solutions. "
                f"Do NOT mention escalation, the network team, or handing off to anyone. "
                f"Just ask the single most valuable technical question for the engineer."
            )
        elif session.get("flow_origin") == "planning":
            timeline  = session.get("planning_timeline", "future")
            remaining = max(0, 4 - session.get("solve_attempts", 0))
            hint = (
                f"This request is scheduled for: {timeline}. "
                f"You have {remaining} exchanges to gather planning context for the network team. "
                f"Ask ONE focused question about: technical scope, dependencies, blockers, "
                f"business priority, success criteria, or contact person. "
                f"Do NOT mention escalation or handing off. Just gather planning information."
            )
    else:
        system = SYSTEM_PROMPT + (f"\n\n{screenshot_ctx}" if screenshot_ctx else "")
        if session.get("flow_origin") == "consult":
            remaining = max(0, 6 - session.get("solve_attempts", 0))
            hint = (
                f"This is a network team consultation. You have {remaining} exchanges remaining. "
                f"Your goal is to gather maximum useful technical information for the network engineer who will implement this. "
                f"Ask ONE focused technical question about the network infrastructure, devices, scale, IP ranges, security requirements, or constraints. "
                f"Do NOT ask for contact details, email addresses, or non-technical information. "
                f"Do NOT provide configuration steps, commands, implementation plans, or solutions. "
                f"Do NOT mention escalation, the network team, or handing off to anyone. "
                f"Just ask the single most valuable technical question for the engineer."
            )
        elif session.get("flow_origin") == "planning":
            timeline  = session.get("planning_timeline", "future")
            remaining = max(0, 4 - session.get("solve_attempts", 0))
            hint = (
                f"This request is scheduled for: {timeline}. "
                f"You have {remaining} exchanges to gather planning context for the network team. "
                f"Ask ONE focused question about: technical scope, dependencies, blockers, "
                f"business priority, success criteria, or contact person. "
                f"Do NOT mention escalation or handing off. Just gather planning information."
            )
        else:
            screenshot_analysis = session.get("screenshot_analysis", "")
            if screenshot_analysis:
                hint = (
                    f"The user confirmed this screenshot shows their issue: {screenshot_analysis[:300]}\n\n"
                    "You already know exactly what the problem is from the screenshot. "
                    "Do NOT ask what the problem is, what command they ran, or what they were troubleshooting. "
                    "Skip all intake questions. Go straight to the first specific diagnostic step "
                    "based on what you can see in the screenshot."
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

    # Disclaimer for consult/planning when no RAG document was found
    if session.get("flow_origin") in ("consult", "planning") and not rag_context:
        if "AI-generated" not in reply:
            reply += (
                "\n\nNote: This response is AI-generated based on general networking knowledge. "
                "Please verify with your network engineer before implementing."
            )

    # ── Attempt counting — Claude classifies, screenshot turn always 0 ────────
    if session.get("flow_origin") in ("consult", "planning", "major_incident"):
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
        from app.core.config import settings as _s
        import anthropic as _a
        _cl = _a.Anthropic(api_key=_s.ANTHROPIC_API_KEY)

        # Get last assistant message for context
        prior_msgs    = session.get("messages", [])
        last_bot_msg  = next(
            (m["content"] for m in reversed(prior_msgs) if m["role"] == "assistant"),
            ""
        )

        resp = _cl.messages.create(
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

    # Only increment here for non-screenshot turns; the actual reply-based
    # counting happens after we get the reply below
    rag_context = session.get("rag_context", "")
    has_runbook = bool(rag_context)
    print(f"  [Major] flow_origin={session.get('flow_origin')} solve_attempts={session['solve_attempts']}")

    # Inject screenshot context if present
    screenshot_ctx = ""
    if session.get("screenshot_analysis"):
        screenshot_ctx = (
            f"\n\nSCREENSHOT ANALYSIS:\n{session['screenshot_analysis']}\n"
            "Use this visual context when deciding the next troubleshooting step."
        )

    if rag_context:
        system = SYSTEM_PROMPT + (
            f"\n\n{rag_context}"
            f"{screenshot_ctx}\n\n"
            "STRICT INSTRUCTION: Follow the runbook procedures exactly. "
            "Do NOT ask questions outside of the runbook steps. "
            "When ALL runbook steps are exhausted and issue is still not resolved, end with [STEPS_EXHAUSTED]."
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

    if n >= max_attempts and not is_consult:
        reply = "I have tried all the troubleshooting steps I can and the issue is still not resolved. We need a network engineer to take this further."
        session["messages"].append({"role": "assistant", "content": reply})
        session["flow_step"] = "escalate_ready"
        return _make_response(sid, session, reply, can_escalate=True)
    elif session.get("flow_origin") == "major_incident" and n >= 4:
        reply = "I have gathered enough details. Raising a CRITICAL ticket immediately and notifying the network engineering team."
        session["messages"].append({"role": "assistant", "content": reply})
        session["domain"]    = "networking"
        session["severity"]  = "critical"
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
        if not has_runbook and n >= 3 and not session.get("mid_check_done") and not is_consult and session.get("flow_origin") not in ("planning", "major_incident"):
            session["mid_check_done"] = True
            reply = (
                "I have tried 3 troubleshooting steps so far and the issue is still not resolved. "
                "Would you like me to try a few more steps, or shall I raise a ticket and escalate this to the network engineering team?"
            )
            session["messages"].append({"role": "assistant", "content": reply})
            session["flow_step"] = "mid_check"
            return _make_response(sid, session, reply, can_escalate=False)

        # Runbook mid-check at step 3 — broken flow only, never consult/planning
        if has_runbook and n >= 3 and not session.get("mid_check_done") and session.get("flow_origin") not in ("major_incident", "consult", "planning"):
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

        reply, domain, severity, is_networking = _call_claude(session, system, hint)

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
        if session.get("flow_origin") in ("consult", "planning", "major_incident"):
            if not is_screenshot_turn and not is_consult:  # consult already incremented above
                session["solve_attempts"] += 1
        else:
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

    # Append user message
    session["messages"].append({"role": "user", "content": msg})

    step = session["flow_step"]
    print(f"  [Chat] Flow step={step}")

    # ── FLOW ROUTING ──────────────────────────────────────────────────────────

    if step == "broken":
        session["problem"] = msg[:400]
        return _handle_broken(session, sid, msg)

    elif step == "waiting_broken":
        return _handle_broken(session, sid, msg)

    elif step == "waiting_impacting":
        return _handle_impacting(session, sid, msg)

    elif step == "waiting_multi_customer":
        return _handle_multi_customer(session, sid, msg)

    elif step == "waiting_consult":
        return _handle_consult(session, sid, msg)

    elif step == "waiting_details":
        return _handle_details(session, sid, msg)

    elif step == "waiting_deadline":
        return _handle_deadline(session, sid, msg)

    elif step == "waiting_deadline_date":
        # User typed their deadline — store it and ask help today
        session["deadline_date"] = msg
        session["flow_step"]     = "waiting_help_today"
        reply = "Do you need help with this today?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, can_escalate=False)

    elif step == "waiting_help_today":
        return _handle_help_today(session, sid, msg)

    elif step == "waiting_problem":
        session["problem"]     = msg[:400]
        session["flow_step"]   = "ai_analysis"
        session["flow_origin"] = "broken"
        rag_context = _get_rag(msg)
        session["rag_context"] = rag_context
        return _start_ai_analysis(session, sid)

    elif step == "mid_check":
        # Use Claude to determine intent — escalate or continue troubleshooting
        try:
            from app.core.config import settings as _s
            import anthropic as _a
            _cl = _a.Anthropic(api_key=_s.ANTHROPIC_API_KEY)
            resp = _cl.messages.create(
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
            reply = "Raising a ticket now and escalating to the network engineering team."
            session["messages"].append({"role": "assistant", "content": reply})
            return _make_response(sid, session, reply, can_escalate=True)
        else:
            session["flow_step"] = "ai_analysis"
            return _continue_ai_analysis(session, sid, msg)

    elif step == "ai_analysis":
        return _continue_ai_analysis(session, sid, msg)

    elif step == "waiting_next_sprint":
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

    elif step in ("major_incident", "next_sprint", "consult_complete", "escalate_ready"):
        reply = "Is there anything else I can help with?"
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply)

    else:
        session["flow_step"] = "broken"
        session["problem"]   = msg[:400]
        return _handle_broken(session, sid, msg)


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

    print(f"  [Vision] size={len(image_bytes)} detected={detected_type} using={media_type} first={image_bytes[:8].hex()}")

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
        analysis = f"Screenshot received (analysis unavailable: {e})"

    # Store in session — will be injected into next AI turn's context
    session["screenshot_analysis"] = analysis
    # Mark this as a screenshot turn so attempt counter is skipped
    session["is_screenshot_turn"]  = True

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

    # Inject screenshot analysis into ticket diagnosis if present
    if session.get("screenshot_analysis"):
        diagnosis += f"\n\nScreenshot Analysis:\n{session['screenshot_analysis']}"

    domain_str  = "networking"
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