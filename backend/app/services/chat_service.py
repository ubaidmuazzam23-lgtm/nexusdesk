# Location: backend/app/services/chat_service.py
#
# CLEAN REWRITE — signal-based 4-phase flow, single Claude call, low latency
#
# PHASES:
#   INTAKE  → AI asks questions until it says [READY_TO_SOLVE]
#   SOLVE   → AI gives solutions, up to 3 attempts, then says [NEEDS_ENGINEER]
#   TRIAGE  → Asset Q&A — real values from DB, pinpoints exact asset
#   ESCALATE→ Ticket created, routed to asset owner or domain fallback

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
# SYSTEM PROMPT — single call, signal-based phase control
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an IT support specialist at NexusDesk.

STRICT FORMATTING:
- Plain sentences only. No bullet points, no markdown, no asterisks, no dashes as bullets.
- Under 120 words per response.
- One question at a time.
- Never start with "Certainly", "Absolutely", "Of course", "Great".

YOUR PHASES — follow in order:

PHASE 1 — INTAKE:
Ask focused questions one at a time to fully understand the problem before attempting any fix.
Gather: what system/app, what error message, how long, who else is affected, what they tried.
Keep asking until you have enough context to give a specific targeted solution.
When ready to solve, end your reply with the signal: [READY_TO_SOLVE]

PHASE 2 — SOLVE:
You now have context. Give ONE specific targeted solution per response.
Each attempt must try something meaningfully different.
After 3 failed solve attempts, end your reply with: [NEEDS_ENGINEER]

PHASE 3 — DO NOT handle. The system will take over.

Also always end your reply with this on a new line:
<meta>{"domain":"DOMAIN","severity":"SEVERITY"}</meta>

Domain: networking, hardware, software, security, email_communication, identity_access,
        database, cloud, infrastructure, devops, erp_business_apps, endpoint_management, other
Severity: critical (production/all users), high (user blocked), medium (degraded), low (question)

If the user says something is fixed, reply warmly and briefly. End with <meta>{"domain":"...","severity":"low"}</meta>

IMPORTANT: Never use [NEEDS_ENGINEER] on your own. The system will escalate automatically after 3 solve attempts. Just keep trying to help."""


# ─────────────────────────────────────────────────────────────────────────────
# SESSION
# ─────────────────────────────────────────────────────────────────────────────

def _get_session(sid: str) -> dict:
    if sid not in _sessions:
        _sessions[sid] = {
            "messages":          [],
            "phase":             "intake",   # intake → solve → triage → done
            "solve_attempts":    0,
            "domain":            None,
            "severity":          None,
            "problem":           "",

            # Triage state
            "triage_active":     False,
            "triage_questions":  [],
            "triage_q_index":    0,
            "triage_answers":    [],
            "triage_filters":    {},
            "triage_rows":       [],        # candidate asset rows from DB
            "asset_match":       None,
            "asset_confirmed":   False,
            "asset_context":     {},
            "user_wants_escalate": False,
            "triage_started":     False,
        }
    return _sessions[sid]


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE CLAUDE CALL
# ─────────────────────────────────────────────────────────────────────────────

def _call_claude(session: dict, phase_hint: str = "") -> tuple:
    """
    One API call. Returns (clean_reply, domain, severity, signals).
    signals: set of strings like {'READY_TO_SOLVE', 'NEEDS_ENGINEER'}
    """
    system = SYSTEM_PROMPT
    if phase_hint:
        system += f"\n\nCURRENT PHASE HINT: {phase_hint}"

    resp = _client.messages.create(
        model      = "claude-sonnet-4-5",
        max_tokens = 350,
        system     = system,
        messages   = session["messages"],
    )
    raw = resp.content[0].text.strip()

    # Extract signals
    signals = set()
    if "[READY_TO_SOLVE]" in raw: signals.add("READY_TO_SOLVE")
    if "[NEEDS_ENGINEER]" in raw:  signals.add("NEEDS_ENGINEER")

    # Extract meta
    domain   = session.get("domain") or "other"
    severity = session.get("severity") or "medium"
    m = re.search(r'<meta>(.*?)</meta>', raw, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1).strip())
            d = data.get("domain", "other")
            s = data.get("severity", "medium")
            if d in VALID_DOMAINS: domain   = d
            if s in ["critical","high","medium","low"]: severity = s
        except Exception:
            pass

    # Clean reply
    clean = re.sub(r'\[READY_TO_SOLVE\]|\[NEEDS_ENGINEER\]', '', raw)
    clean = re.sub(r'\s*<meta>.*?</meta>', '', clean, flags=re.DOTALL).strip()

    return clean, domain, severity, signals


# ─────────────────────────────────────────────────────────────────────────────
# TRIAGE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _start_triage(db: Session, session: dict, sid: str) -> ChatMessageResponse:
    """Fetch real assets, generate targeted questions, start Q&A."""
    from app.services.asset_identifier_service import generate_questions, fetch_assets

    domain  = session["domain"] or "other"
    problem = session["problem"]

    # Fetch candidate rows — stored in session for use during answer matching
    rows, _ = fetch_assets(db, domain, problem)
    session["triage_rows"] = rows

    # Generate questions based on actual asset data
    questions = generate_questions(db, domain, problem)

    session["triage_active"]    = True
    session["triage_questions"] = questions
    session["triage_q_index"]   = 1
    session["triage_answers"]   = []
    session["triage_filters"]   = {}
    session["asset_match"]      = None
    session["asset_confirmed"]  = False

    reply = (
        "Before I raise a ticket I need a couple of quick details "
        "to route this to exactly the right person.\n\n"
        + questions[0]
    )

    return ChatMessageResponse(
        session_id        = sid,
        reply             = reply,
        intent            = "context_gathering",
        detected_domain   = domain,
        detected_severity = session["severity"] or "medium",
        resolved          = False,
        can_escalate      = False,
        attempt_number    = session["solve_attempts"],
        context_gathering = True,
    )


def _handle_triage_answer(db: Session, session: dict, sid: str, answer: str) -> ChatMessageResponse:
    """Process one triage answer, run match, ask next question or confirm."""
    from app.services.asset_identifier_service import (
        extract_field_from_answer,
        progressive_match,
    )

    qi        = session["triage_q_index"]
    questions = session["triage_questions"]
    rows      = session["triage_rows"]

    # Map answer to a column+value
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

    # Check match
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
                + ". Go ahead and raise the ticket."
            )
            return ChatMessageResponse(
                session_id        = sid,
                reply             = reply,
                intent            = "ready_to_escalate",
                detected_domain   = session["domain"] or "other",
                detected_severity = session["severity"] or "medium",
                resolved          = False,
                can_escalate      = True,
                attempt_number    = session["solve_attempts"],
                context_gathering = False,
            )

    # More questions?
    if qi < len(questions):
        next_q = questions[qi]
        session["triage_q_index"] += 1
        candidates = len([
            r for r in rows
            if all(v.lower() in str(r.get(c,"")).lower() for c,v in session["triage_filters"].items())
        ]) if session["triage_filters"] else len(rows)

        hint = f" ({candidates} possible matches)" if candidates > 1 else ""
        return ChatMessageResponse(
            session_id        = sid,
            reply             = next_q + hint,
            intent            = "context_gathering",
            detected_domain   = session["domain"] or "other",
            detected_severity = session["severity"] or "medium",
            resolved          = False,
            can_escalate      = False,
            attempt_number    = session["solve_attempts"],
            context_gathering = True,
        )

    # All questions done
    session["triage_active"] = False
    asset = session.get("asset_match")
    if asset:
        name  = asset.get("identifier") or "the asset"
        reply = f"Thanks. I found {name}. The ticket will be routed to the right team. Raise it now."
    else:
        reply = "Thanks for the details. I have enough to route this to the right team. Raise the ticket now."

    return ChatMessageResponse(
        session_id        = sid,
        reply             = reply,
        intent            = "ready_to_escalate",
        detected_domain   = session["domain"] or "other",
        detected_severity = session["severity"] or "medium",
        resolved          = False,
        can_escalate      = True,
        attempt_number    = session["solve_attempts"],
        context_gathering = False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PROCESS MESSAGE
# ─────────────────────────────────────────────────────────────────────────────

def process_message(db: Session, user: User, data: ChatMessageRequest) -> ChatMessageResponse:
    sid     = data.session_id or str(uuid.uuid4())
    session = _get_session(sid)

    # Store problem on first message
    if not session["problem"] and data.message:
        session["problem"] = data.message[:400]

    # Triage Q&A active
    if session["triage_active"]:
        return _handle_triage_answer(db, session, sid, data.message)

    # User asking to escalate — noted but we still complete the solve phase
    user_escalate = any(p in data.message.lower() for p in [
        "please escalate", "escalate this", "escalate now", "just escalate",
        "raise a ticket", "send an engineer", "need an engineer",
        "cant fix", "nothing works", "please just send",
    ])
    if user_escalate:
        session["user_wants_escalate"] = True

    # Append user message
    session["messages"].append({"role": "user", "content": data.message})

    # Resolved check
    if any(p in data.message.lower() for p in ["fixed","works now","that worked","sorted","solved","all good"]):
        session["messages"].append({"role": "assistant", "content": "Glad that sorted it out."})
        return ChatMessageResponse(
            session_id        = sid,
            reply             = "Glad that sorted it out. Feel free to reach out if anything else comes up.",
            intent            = "solve",
            detected_domain   = session["domain"] or "other",
            detected_severity = session["severity"] or "medium",
            resolved          = True,
            can_escalate      = False,
            attempt_number    = session["solve_attempts"],
            context_gathering = False,
        )

    # Phase hint for Claude
    user_wants_escalate = session.get("user_wants_escalate", False)

    if session["phase"] == "intake":
        if user_wants_escalate:
            hint = "PHASE 1 INTAKE: The user is urgently requesting escalation. You have enough context now. Acknowledge their urgency briefly, then end your reply with [READY_TO_SOLVE] immediately — do not ask more questions."
        else:
            hint = "PHASE 1 INTAKE: Ask questions to understand the problem. Do NOT give solutions yet. When you have enough context, end with [READY_TO_SOLVE]."
    elif session["phase"] == "solve":
        session["solve_attempts"] += 1
        n = session["solve_attempts"]
        if user_wants_escalate and n < 3:
            hint = f"PHASE 2 SOLVE: The user wants to escalate but try attempt {n} of 3 first. Acknowledge urgency briefly then give one specific targeted fix. There are {3 - n} attempts remaining after this."
        elif n >= 3:
            hint = f"PHASE 2 SOLVE: Final attempt 3 of 3. Give your best remaining solution. After this the system will automatically escalate to an engineer."
        else:
            hint = f"PHASE 2 SOLVE: Attempt {n} of 3. Give one specific targeted solution. Do not suggest escalation."
    else:
        hint = ""

    try:
        reply, domain, severity, signals = _call_claude(session, hint)

        session["domain"]   = domain
        session["severity"] = severity
        session["messages"].append({"role": "assistant", "content": reply})

        # Phase transitions
        print(f"  [Chat] Phase={session['phase']} attempts={session['solve_attempts']} signals={signals}")
        if "READY_TO_SOLVE" in signals and session["phase"] == "intake":
            session["phase"] = "solve"
            print(f"  [Chat] Phase: intake → solve")
        # Force transition to solve after 3 intake messages even without signal
        elif session["phase"] == "intake" and len([m for m in session["messages"] if m["role"] == "user"]) >= 3:
            session["phase"] = "solve"
            print(f"  [Chat] Phase: intake → solve (forced after 3 user messages)")

        # After exactly 3 solve attempts → start triage (only once)
        if session["phase"] == "solve" and session["solve_attempts"] >= 3 and not session.get("triage_started"):
            session["phase"]          = "triage"
            session["triage_started"] = True
            print(f"  [Chat] Phase: solve → triage after 3 attempts")
            # Return Claude reply + immediately trigger first triage question
            triage_response = _start_triage(db, session, sid)
            # Combine Claude's final solve reply with the first triage question
            combined_reply = reply + "" + triage_response.reply
            return ChatMessageResponse(
                session_id        = sid,
                reply             = combined_reply,
                intent            = "context_gathering",
                detected_domain   = domain,
                detected_severity = severity,
                resolved          = False,
                can_escalate      = False,
                attempt_number    = session["solve_attempts"],
                context_gathering = True,
            )

        return ChatMessageResponse(
            session_id        = sid,
            reply             = reply,
            intent            = "solve",
            detected_domain   = domain,
            detected_severity = severity,
            resolved          = False,
            can_escalate      = False,
            attempt_number    = session["solve_attempts"],
            context_gathering = False,
        )

    except Exception as e:
        print(f"  [Chat] Claude error: {e}")
        return ChatMessageResponse(
            session_id        = sid,
            reply             = "Something went wrong. Please try again in a moment.",
            intent            = "solve",
            detected_domain   = session["domain"] or "other",
            detected_severity = session["severity"] or "medium",
            resolved          = False,
            can_escalate      = False,
            attempt_number    = session["solve_attempts"],
            context_gathering = False,
        )


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

    priority_map = {"critical":TicketPriority.CRITICAL,"high":TicketPriority.HIGH,
                    "medium":TicketPriority.MEDIUM,"low":TicketPriority.LOW}
    sla_map      = {"critical":30,"high":120,"medium":480,"low":1440}

    # Build diagnosis
    msgs       = session.get("messages", [])
    ai_msgs    = [m["content"] for m in msgs if m["role"] == "assistant"]
    diagnosis  = ai_msgs[-1][:500] if ai_msgs else ""

    if asset:
        row = asset.get("row", {})
        diagnosis += (
            f"\n\nAsset Identified:"
            f"\n  Asset:       {asset.get('identifier') or 'N/A'}"
            f"\n  Environment: {asset.get('environment') or 'N/A'}"
            f"\n  Team:        {asset.get('team') or 'N/A'}"
            f"\n  Contact:     {asset.get('contact_email') or 'N/A'}"
            f"\n  Manager:     {asset.get('manager_email') or 'N/A'}"
        )

    if context:
        qs = session.get("triage_questions", [])
        an = session.get("triage_answers", [])
        diagnosis += "\n\nUser answers:\n" + "\n".join(f"  {q} → {a}" for q, a in zip(qs, an))

    # Routing
    domain_str  = str(data.domain).lower().replace("ticketdomain.", "") if data.domain else "other"
    engineer_id = None
    team_id     = None

    contact_email = asset.get("contact_email", "") if asset else ""
    manager_email = asset.get("manager_email", "") if asset else ""

    print(f"  [Route] asset_match={asset}")
    print(f"  [Route] contact_email={contact_email} manager_email={manager_email}")

    # P1 — asset owner
    if contact_email:
        u = db.query(User).filter(User.email == contact_email).first()
        if u and db.query(Engineer).filter(Engineer.user_id == u.id).first():
            engineer_id = u.id
            print(f"  [Route] Asset owner: {contact_email}")

    # P2 — manager's team
    if not engineer_id and manager_email:
        u = db.query(User).filter(User.email == manager_email).first()
        if u:
            t = db.query(Team).filter(Team.manager_id == u.id).first()
            if t:
                team_id = t.id
                print(f"  [Route] Manager team: {manager_email}")

    # P3 — domain team
    if not engineer_id and not team_id:
        team_id = _find_best_team(db, domain_str, user.timezone or "UTC")
        if team_id: print(f"  [Route] Domain team fallback")

    # P4 — individual engineer
    if not engineer_id and not team_id:
        engineer_id = _find_best_engineer(db, domain_str, user.timezone or "UTC")
        if engineer_id: print(f"  [Route] Engineer fallback")

    ticket = Ticket(
        ticket_number    = _generate_ticket_number(db),
        user_id          = user.id,
        engineer_id      = engineer_id,
        team_id          = team_id,
        title            = data.title,
        description      = data.description,
        domain           = TicketDomain(domain_str) if domain_str in [d.value for d in TicketDomain] else TicketDomain.OTHER,
        priority         = priority_map.get(severity, TicketPriority.MEDIUM),
        status           = TicketStatus.OPEN,
        steps_tried      = data.steps_tried,
        ai_diagnosis     = diagnosis.strip() or None,
        ai_attempted     = True,
        user_city        = user.city,
        user_country     = user.country,
        user_timezone    = user.timezone,
        sla_deadline     = datetime.utcnow() + timedelta(minutes=sla_map.get(severity, 480)),
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
    print(f"  [Ticket] {ticket.ticket_number} | {domain_str} | team={team_id} | eng={engineer_id}")

    if data.session_id in _sessions:
        del _sessions[data.session_id]

    # Build response with routing info
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
            # Get manager email
            if team.manager_id:
                mgr = db.query(User).filter(User.id == team.manager_id).first()
                if mgr:
                    team_manager_email = mgr.email
    elif ticket.engineer_id:
        # Find team through TeamMember
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