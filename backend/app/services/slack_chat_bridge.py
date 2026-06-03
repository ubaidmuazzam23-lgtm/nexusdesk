# File: backend/app/services/slack_chat_bridge.py
# Bridge between Slack messages and NexusDesk chat_service
# Uses Slack identity — completely separate from NexusDesk web users

import uuid
import logging
from typing import Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Track Slack sessions (slack_user_id → nexusdesk session_id)
_slack_to_session: dict = {}
# Track pending escalations (session_id → slack channel)
_pending_escalations: dict = {}


def _get_or_create_session(slack_user_id: str) -> str:
    """Get existing session or create new one for this Slack user."""
    if slack_user_id not in _slack_to_session:
        _slack_to_session[slack_user_id] = f"slack_{slack_user_id}_{uuid.uuid4().hex[:8]}"
    return _slack_to_session[slack_user_id]


def _reset_session(slack_user_id: str):
    """Reset session after ticket is raised."""
    if slack_user_id in _slack_to_session:
        del _slack_to_session[slack_user_id]


def process_slack_message(
    slack_user_id: str,
    user_name: str,
    user_email: str,
    message: str,
    channel: str,
    slack_client,
    say,
):
    """
    Process a message from Slack through the NexusDesk chat engine.
    Uses Slack identity only — no NexusDesk DB user lookup.
    """
    from app.core.database import SessionLocal
    from app.services import chat_service
    from pydantic import BaseModel

    # Build a fake ChatRequest compatible with process_message
    class SlackChatRequest:
        def __init__(self, session_id, message, user_name, user_email):
            self.session_id  = session_id
            self.message     = message
            self.user_name   = user_name
            self.user_email  = user_email
            self.screenshot  = None

    session_id = _get_or_create_session(slack_user_id)

    # Handle help command
    if message.lower().strip() in ("help", "/help", "?", "commands"):
        say(
            "🤖 *NexusDesk IT Support — Commands*"
            "*Raise a ticket:* Just describe your issue"
            "  _e.g. 'My Salesforce is not accessible'_"
            "  _e.g. 'EC2 instance is down'_"
            "  _e.g. 'Cannot connect to database'_"
            "*Check your tickets:* `my tickets`"
            "*Start fresh:* `new`"
            "*Show this help:* `help`"
            "💡 _Just type your issue naturally — I'll ask the right questions and route it to the correct engineer._"
        )
        return

    # Handle new/reset command
    if message.lower().strip() in ("new", "reset", "start over", "restart"):
        _reset_session(slack_user_id)
        say("✅ Started fresh. Describe your IT issue and I'll help you.")
        return

    # First message — send welcome
    is_new_session = slack_user_id not in _slack_to_session

    # Send welcome on first message
    if is_new_session:
        say(
            f"👋 Hi *{user_name}*! I'm *NexusDesk IT Support*."
            "Just describe your IT issue and I'll diagnose it, troubleshoot it, and raise a ticket to the right engineer."
            "Type `help` anytime to see available commands."
        )

    # Inject user info into chat session
    db = SessionLocal()
    try:
        # Ensure session exists in chat_service
        session = chat_service._get_session(session_id)
        # Override user info with Slack profile
        session["user_name"]  = user_name
        session["user_email"] = user_email
        session["source"]     = "slack"
        session["slack_user_id"] = slack_user_id

        # Build proper ChatMessageRequest
        from app.schemas.chat import ChatMessageRequest

        data = ChatMessageRequest(
            session_id  = session_id,
            message     = message,
            user_name   = user_name,
            user_email  = user_email,
            screenshot  = None,
        )

        # Create a fake user object with Slack identity
        class SlackUser:
            id        = None
            full_name = user_name
            email     = user_email
            city      = "Slack"
            country   = "Remote"
            timezone  = "UTC"
            role      = type("r", (), {"value": "user"})()

        fake_user = SlackUser()

        # Process through chat engine — signature: process_message(db, user, data)
        response = chat_service.process_message(db, fake_user, data)

        # Send reply to Slack
        reply = response.reply if hasattr(response, 'reply') else str(response)

        # Format nicely for Slack
        say(reply)

        # If ticket can be escalated, auto-escalate
        if hasattr(response, 'can_escalate') and response.can_escalate:
            _auto_escalate(
                session_id=session_id,
                slack_user_id=slack_user_id,
                user_name=user_name,
                user_email=user_email,
                channel=channel,
                slack_client=slack_client,
                say=say,
                db=db,
                session=session,
            )

    except Exception as e:
        logger.error(f"Slack bridge error: {e}", exc_info=True)
        say("I ran into an issue processing your request. Please try again.")
    finally:
        db.close()


def _auto_escalate(
    session_id, slack_user_id, user_name, user_email,
    channel, slack_client, say, db, session
):
    """Auto-escalate to ticket after chat flow completes."""
    try:
        from app.services import chat_service

        # Build escalate request
        class EscalateReq:
            def __init__(self, session_id, title, description, domain, priority):
                self.session_id  = session_id
                self.title       = title
                self.description = description
                self.domain      = domain
                self.priority    = priority
                self.steps_tried = ""
                self.complexity  = "moderate"

        messages   = session.get("messages", [])
        user_msgs  = [m["content"] for m in messages if m["role"] == "user"]
        title      = user_msgs[0][:80] if user_msgs else "IT Support Issue"
        domain     = session.get("detected_domain", "other") or "other"
        severity   = session.get("severity", "medium") or "medium"
        diagnosis  = session.get("asset_context", {}).get("diagnosis", "")

        req = EscalateReq(
            session_id  = session_id,
            title       = title,
            description = diagnosis or title,
            domain      = domain,
            priority    = "high" if severity in ("critical","high") else "medium",
        )

        # Create minimal Slack user record in DB (required for ticket FK constraint)
        # This is NOT a NexusDesk account — just a placeholder for the ticket
        from app.models.user import User, UserRole
        from app.core.security import hash_password
        import uuid as _uuid

        slack_db_user = db.query(User).filter(User.email == user_email).first()
        if not slack_db_user:
            slack_db_user = User(
                id              = _uuid.uuid4(),
                email           = user_email,
                full_name       = user_name,
                hashed_password = hash_password(_uuid.uuid4().hex),
                role            = UserRole.USER,
                is_active       = True,
                is_verified     = True,
                city            = "Slack",
                country         = "Remote",
                timezone        = "UTC",
            )
            db.add(slack_db_user)
            db.flush()
            logger.info(f"Created Slack placeholder user: {user_email}")

        # Engineer routing is PURELY from Slack — DB engineer assignment is skipped
        # Override session asset_match contact to prevent DB engineer lookup
        session["asset_context"] = session.get("asset_context", {})

        result = chat_service.escalate_to_ticket(db, slack_db_user, req)

        if result and hasattr(result, 'ticket_number'):

            # Find engineer purely from Slack workspace by job title
            slack_eng = _find_slack_engineer(slack_client, domain, slack_user_id)

            # Build ticket confirmation
            ticket_msg = f"✅ *Ticket {result.ticket_number} raised successfully*\n"
            ticket_msg += f"📋 *Domain:* {domain.replace('_', ' ').title()}\n"
            ticket_msg += f"🔥 *Priority:* {req.priority.upper()}\n"

            if slack_eng:
                ticket_msg += f"\n👨‍💻 *Assigned Engineer:* {slack_eng['name']}\n"
                ticket_msg += f"💼 *Title:* {slack_eng['title']}\n"
                ticket_msg += f"{'🟢 Active now' if slack_eng['active'] else '🔵 Will be notified'}"
            else:
                ticket_msg += "\n👥 No engineer found — check Slack workspace member titles"

            say(ticket_msg)

            # DM engineer on Slack
            if slack_eng:
                _notify_engineer(
                    slack_client      = slack_client,
                    engineer_email    = slack_eng["email"],
                    engineer_slack_id = slack_eng["slack_id"],
                    engineer_name     = slack_eng["name"],
                    ticket_number     = result.ticket_number,
                    title             = title,
                    user_name         = user_name,
                    diagnosis         = diagnosis,
                    priority          = req.priority,
                    domain            = domain,
                )

            # Reset session after ticket raised
            _reset_session(slack_user_id)

    except Exception as e:
        logger.error(f"Auto-escalate error: {e}", exc_info=True)


# Domain → job title keywords mapping
DOMAIN_TITLE_KEYWORDS = {
    "networking":         ["network engineer", "network", "netops", "infrastructure engineer"],
    "security":           ["security engineer", "security", "netskope", "infosec"],
    "cloud":              ["cloud engineer", "cloud", "devops", "platform engineer"],
    "database":           ["database engineer", "dba", "database", "data engineer"],
    "devops":             ["devops", "sre", "platform engineer", "devops engineer"],
    "hardware":           ["hardware engineer", "hardware", "it support", "field engineer"],
    "software":           ["software engineer", "developer", "it support"],
    "identity_access":    ["identity", "iam", "access management", "it support"],
    "endpoint_management":["endpoint", "it support", "desktop engineer"],
    "other":              ["it support", "engineer", "support"],
}


def _find_slack_engineer(slack_client, domain: str, user_slack_id: str = None):
    """
    Find the best available engineer in Slack workspace based on domain.
    Matches job title keywords, prefers active users, picks by timezone proximity.
    """
    try:
        keywords = DOMAIN_TITLE_KEYWORDS.get(domain, DOMAIN_TITLE_KEYWORDS["other"])

        # Get all workspace members
        response = slack_client.users_list()
        members  = response.get("members", [])

        candidates = []
        for member in members:
            # Skip bots, deleted, and the user themselves
            if member.get("is_bot") or member.get("deleted"):
                continue
            if user_slack_id and member["id"] == user_slack_id:
                continue

            profile = member.get("profile", {})
            title   = (profile.get("title") or "").lower()
            name    = profile.get("real_name") or profile.get("display_name") or ""
            email   = profile.get("email") or ""

            # Check if title matches domain keywords
            if any(kw in title for kw in keywords):
                # Check online presence
                try:
                    presence = slack_client.users_getPresence(user=member["id"])
                    is_active = presence.get("presence") == "active"
                except Exception:
                    is_active = False

                candidates.append({
                    "slack_id": member["id"],
                    "name":     name,
                    "email":    email,
                    "title":    profile.get("title", ""),
                    "tz":       member.get("tz", "UTC"),
                    "active":   is_active,
                })

        if not candidates:
            logger.warning(f"No engineers found for domain '{domain}' in Slack workspace")
            return None

        # Prefer active engineers first
        active    = [c for c in candidates if c["active"]]
        chosen    = active[0] if active else candidates[0]

        logger.info(f"Routing to Slack engineer: {chosen['name']} ({chosen['email']}) for domain={domain}")
        return chosen

    except Exception as e:
        logger.error(f"Failed to find Slack engineer: {e}")
        return None


def _notify_engineer(
    slack_client, engineer_email, ticket_number,
    title, user_name, diagnosis, priority, domain,
    engineer_slack_id=None, engineer_name=None
):
    """Send DM to engineer on Slack when ticket is assigned."""
    try:
        # Use provided Slack ID or look up by email
        if engineer_slack_id:
            eng_slack_id = engineer_slack_id
        else:
            result = slack_client.users_lookupByEmail(email=engineer_email)
            if not result or not result.get("user"):
                logger.warning(f"Engineer {engineer_email} not found in Slack workspace")
                return
            eng_slack_id = result["user"]["id"]

        # Build notification message
        priority_emoji = "🔴" if priority == "critical" else "🟠" if priority == "high" else "🟡"
        domain_label   = domain.replace("_", " ").title()

        msg = (
            f"🎫 *New ticket assigned to you*\n\n"
            f"*Ticket:* {ticket_number}  {priority_emoji} {priority.upper()}\n"
            f"*Domain:* {domain_label}\n"
            f"*User:* {user_name}\n"
            f"*Issue:* {title}\n"
        )

        if diagnosis:
            # Show first 400 chars of diagnosis
            short_diag = diagnosis[:400] + "..." if len(diagnosis) > 400 else diagnosis
            msg += f"\n*AI Diagnosis:*\n```{short_diag}```"

        slack_client.chat_postMessage(
            channel=eng_slack_id,
            text=msg,
            mrkdwn=True,
        )
        logger.info(f"Engineer {engineer_email} notified on Slack")

    except Exception as e:
        logger.error(f"Failed to notify engineer {engineer_email} on Slack: {e}")