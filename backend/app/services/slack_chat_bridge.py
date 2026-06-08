# File: backend/app/services/slack_chat_bridge.py
# Bridge between Slack messages and chat_service
# Uses Slack identity — completely separate from web users

import uuid
import logging
from typing import Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Track Slack sessions (slack_user_id → session_id)
_slack_to_session: dict = {}
# Track pending new conversation confirmations
_pending_new: dict = {}
# Track tickets for resolution (ticket_number → user info) — persists across restarts via DB
TICKETS_CHANNEL = "network-tickets"
CONSULT_CHANNEL = "network-consult"


def _get_or_create_session(slack_user_id: str) -> str:
    if slack_user_id not in _slack_to_session:
        _slack_to_session[slack_user_id] = f"slack_{slack_user_id}_{uuid.uuid4().hex[:8]}"
    return _slack_to_session[slack_user_id]


def _reset_session(slack_user_id: str):
    if slack_user_id in _slack_to_session:
        del _slack_to_session[slack_user_id]


def _get_or_create_engineer_consult_channel(slack_client, engineer_slack_id: str, engineer_name: str) -> Optional[str]:
    """Get or create a private consult channel for a specific engineer."""
    try:
        safe_name    = engineer_name.lower().replace(" ", "-").replace("_", "-")[:15]
        channel_name = f"consult-{safe_name}"

        result = slack_client.conversations_list(types="private_channel")
        for ch in result.get("channels", []):
            if ch["name"] == channel_name:
                try:
                    slack_client.conversations_invite(channel=ch["id"], users=engineer_slack_id)
                except Exception:
                    pass
                return ch["id"]

        result     = slack_client.conversations_create(name=channel_name, is_private=True)
        channel_id = result["channel"]["id"]
        slack_client.conversations_invite(channel=channel_id, users=engineer_slack_id)
        slack_client.chat_postMessage(
            channel=channel_id,
            text=(
                f"*Your private consult channel, {engineer_name}*\n\n"
                f"All consultation requests assigned to you will appear here."
            ),
            mrkdwn=True,
        )
        logger.info(f"Created private consult channel #{channel_name} for {engineer_name}")
        return channel_id
    except Exception as e:
        logger.error(f"Failed to get/create consult channel for {engineer_name}: {e}")
        return None


def _get_or_create_consult_channel(slack_client) -> Optional[str]:
    """Get or create #network-consult channel."""
    try:
        result = slack_client.conversations_list(types="public_channel,private_channel")
        for ch in result.get("channels", []):
            if ch["name"] == CONSULT_CHANNEL:
                return ch["id"]
        result     = slack_client.conversations_create(name=CONSULT_CHANNEL)
        channel_id = result["channel"]["id"]
        slack_client.chat_postMessage(
            channel=channel_id,
            text="*Network Consult Channel*\n\nNetwork team consultation requests will be posted here.",
            mrkdwn=True,
        )
        return channel_id
    except Exception as e:
        logger.error(f"Failed to get/create consult channel: {e}")
        return None


def _handle_consult_escalation(slack_client, session, user_name, say, slack_user_id=None, is_planning=False):
    """Post rich consult summary to #network-consult channel and notify user of assigned engineer."""
    try:
        from app.core.config import settings as _settings
        import anthropic as _anthropic
        _cl = _anthropic.Anthropic(api_key=_settings.ANTHROPIC_API_KEY)

        msgs  = session.get("messages", [])
        convo = "\n".join(
            ("User: " if m["role"] == "user" else "Bot: ") + m["content"]
            for m in msgs
        )
        problem = session.get("problem", "Network consultation request")

        try:
            resp = _cl.messages.create(
                model      = "claude-sonnet-4-5",
                max_tokens = 700,
                messages   = [{"role": "user", "content": (
                    "You are writing a detailed consultation brief for a senior network engineer.\n\n"
                    "Conversation:\n" + convo + "\n\n"
                    "Write a detailed consultation brief for a senior network engineer.\n\n"
                    "Based on the conversation, decide which sections are most relevant and useful. "
                    "Always include at minimum: what the user wants, their current setup, key technical details, "
                    "your expert recommendation, and next steps for the engineer.\n\n"
                    "Format rules:\n"
                    "- Use clear section titles in CAPS on their own line\n"
                    "- Plain sentences under each section, no markdown symbols\n"
                    "- Be specific and technical\n"
                    "- The recommendation section must have concrete tool and architecture suggestions\n"
                    "- End with numbered action items for the engineer\n"
                    "- Choose section titles that best fit this specific conversation"
                )}],
            )
            summary = resp.content[0].text.strip()
        except Exception:
            summary = problem

        # Find consulting engineer
        consulting_eng = _find_slack_engineer(slack_client, "networking", slack_user_id)

        # Post to engineer's private consult channel
        if consulting_eng:
            try:
                consult_channel = _get_or_create_engineer_consult_channel(
                    slack_client, consulting_eng["slack_id"], consulting_eng["name"]
                )
                if consult_channel:
                    timeline_label = f"\nTimeline: {session.get('planning_timeline', '')}" if is_planning and session.get('planning_timeline') else ""
                    slack_client.chat_postMessage(
                        channel = consult_channel,
                        text    = (
                            f"*Consult Request from {user_name}*{timeline_label}\n\n"
                            f"{summary}"
                        ),
                        mrkdwn  = True,
                    )
            except Exception as e:
                logger.error(f"Failed to post to consult channel: {e}")

        # Also post to #network-consult for team visibility
        channel_id = _get_or_create_consult_channel(slack_client)
        if channel_id:
            msg = f"*Consult Request from {user_name}*\n"
            if consulting_eng:
                msg += f"*Assigned to:* {consulting_eng['name']}\n\n"
            msg += summary
            slack_client.chat_postMessage(channel=channel_id, text=msg, mrkdwn=True)

        # Tell user who their consulting engineer is
        timeline = session.get("planning_timeline", "")
        if is_planning:
            timeline_msg = f"This has been scheduled for {timeline}. " if timeline else ""
        else:
            timeline_msg = ""

        if consulting_eng:
            say(
                f"I have shared a detailed summary with the network team.\n\n"
                f"{timeline_msg}"
                f"Your assigned engineer is *{consulting_eng['name']}* — {consulting_eng['title']}\n"
                f"Contact: {consulting_eng['email']}\n\n"
                f"They will reach out to you when ready."
            )
        else:
            say(
                f"I have shared a detailed summary with the network team. "
                f"{timeline_msg}"
                f"They will review it and follow up with you."
            )

    except Exception as e:
        logger.error(f"Consult escalation error: {e}")
        say("I have passed this to the network team for follow-up.")


def _get_or_create_tickets_channel(slack_client) -> Optional[str]:
    """Get or create #network-tickets channel, return channel ID."""
    try:
        result = slack_client.conversations_list(types="public_channel,private_channel")
        for ch in result.get("channels", []):
            if ch["name"] == TICKETS_CHANNEL:
                return ch["id"]
        # Create if not exists
        result = slack_client.conversations_create(name=TICKETS_CHANNEL)
        channel_id = result["channel"]["id"]
        # Post welcome message
        slack_client.chat_postMessage(
            channel=channel_id,
            text=(
                "*Network Tickets Channel*\n\n"
                "All network support tickets will be posted here.\n\n"
                "*Engineer Commands:*\n"
                "`resolved T-XXXX` — Close ticket and notify user\n"
                "`assign T-XXXX @engineer` — Reassign ticket\n"
                "`comment T-XXXX <text>` — Add comment, notify user\n"
                "`status T-XXXX` — Show ticket details\n"
                "`snooze T-XXXX 2h` — Snooze for 2 hours"
            ),
            mrkdwn=True,
        )
        return channel_id
    except Exception as e:
        logger.error(f"Failed to get/create tickets channel: {e}")
        return None


def _get_or_create_engineer_channel(slack_client, engineer_slack_id: str, engineer_name: str) -> Optional[str]:
    """Get or create a private channel for a specific engineer."""
    try:
        # Channel name: eng-<engineer_name_lowercase_no_spaces>
        safe_name    = engineer_name.lower().replace(" ", "-").replace("_", "-")[:15]
        channel_name = f"eng-{safe_name}"

        # Check if channel exists
        result = slack_client.conversations_list(types="private_channel")
        for ch in result.get("channels", []):
            if ch["name"] == channel_name:
                # Invite engineer if not already member
                try:
                    slack_client.conversations_invite(channel=ch["id"], users=engineer_slack_id)
                except Exception:
                    pass  # Already a member
                return ch["id"]

        # Create private channel
        result     = slack_client.conversations_create(name=channel_name, is_private=True)
        channel_id = result["channel"]["id"]

        # Invite engineer to their channel
        slack_client.conversations_invite(channel=channel_id, users=engineer_slack_id)

        # Welcome message
        slack_client.chat_postMessage(
            channel=channel_id,
            text=(
                f"*Your private ticket channel, {engineer_name}*\n\n"
                f"All tickets assigned to you will appear here.\n\n"
                f"*Commands:*\n"
                f"`resolved T-XXXX` — Close ticket and notify user\n"
                f"`assign T-XXXX @engineer` — Reassign ticket\n"
                f"`comment T-XXXX <text>` — Send update to user\n"
                f"`status T-XXXX` — Show ticket details"
            ),
            mrkdwn=True,
        )
        logger.info(f"Created private channel #{channel_name} for {engineer_name}")
        return channel_id

    except Exception as e:
        logger.error(f"Failed to get/create engineer channel for {engineer_name}: {e}")
        return None


def _post_ticket_to_channel(slack_client, ticket_number, user_name, priority, incident_report, user_slack_id, engineer_slack_id=None, engineer_name=None):
    """Post new ticket to engineer private channel and #network-tickets."""
    # Post to engineer private channel
    if engineer_slack_id and engineer_name:
        try:
            eng_channel = _get_or_create_engineer_channel(slack_client, engineer_slack_id, engineer_name)
            if eng_channel:
                msg = (
                    f":ticket: *New Ticket: {ticket_number}*\n\n"
                    f"*Reported by:* {user_name}\n"
                    f"*Priority:* {priority.upper()}\n"
                    f"*Domain:* Networking\n\n"
                    f"*Incident Report:*\n{incident_report}\n\n"
                    f"`resolved {ticket_number}` — Close and notify user\n"
                    f"`comment {ticket_number} <text>` — Send update to user\n"
                    f"`status {ticket_number}` — Show details"
                )
                slack_client.chat_postMessage(channel=eng_channel, text=msg, mrkdwn=True)
                logger.info(f"Ticket {ticket_number} posted to engineer channel for {engineer_name}")
        except Exception as e:
            logger.error(f"Failed to post to engineer channel: {e}")

    # Also post to #network-tickets for visibility
    try:
        channel_id = _get_or_create_tickets_channel(slack_client)
        if not channel_id:
            return

        msg = (
            f":ticket: *New Ticket: {ticket_number}*\n\n"
            f"*Reported by:* {user_name}\n"
            f"*Priority:* {priority.upper()}\n"
            f"*Domain:* Networking\n"
            f"*Assigned to:* {engineer_name or 'Unassigned'}\n\n"
            f"*Incident Report:*\n{incident_report}\n\n"
            f"`resolved {ticket_number}` `assign {ticket_number} @eng` `comment {ticket_number} <text>` `status {ticket_number}`"
        )
        slack_client.chat_postMessage(channel=channel_id, text=msg, mrkdwn=True)
        logger.info(f"Ticket {ticket_number} posted to #{TICKETS_CHANNEL}")
    except Exception as e:
        logger.error(f"Failed to post ticket to channel: {e}")


def _handle_engineer_command(message: str, slack_user_id: str, user_name: str, slack_client, say, db):
    """Handle engineer commands in #network-tickets channel."""
    from app.models.ticket import Ticket, TicketStatus
    from datetime import datetime, timedelta

    msg   = message.strip()
    parts = msg.split(" ", 2)
    cmd   = parts[0].lower() if parts else ""
    tnum  = parts[1].upper() if len(parts) > 1 else ""

    # ── resolved T-XXXX ──────────────────────────────────────────────────────
    if cmd == "resolved" and tnum:
        ticket = db.query(Ticket).filter(Ticket.ticket_number == tnum).first()
        if not ticket:
            say(f"Ticket {tnum} not found.")
            return True

        ticket.status      = TicketStatus.RESOLVED
        ticket.resolved_at = datetime.utcnow()
        db.commit()

        # Notify user via Slack DM
        _notify_user_resolved(slack_client, ticket, tnum)
        say(f"Ticket *{tnum}* marked as resolved. User has been notified.")
        return True

    # ── assign T-XXXX @engineer ───────────────────────────────────────────────
    if cmd == "assign" and tnum and len(parts) > 2:
        ticket = db.query(Ticket).filter(Ticket.ticket_number == tnum).first()
        if not ticket:
            say(f"Ticket {tnum} not found.")
            return True

        mention   = parts[2].strip()
        eng_name  = mention.lstrip("@")

        # Find engineer in Slack
        try:
            result  = slack_client.users_list()
            members = result.get("members", [])
            target  = next(
                (m for m in members
                 if m.get("profile", {}).get("display_name", "").lower() == eng_name.lower()
                 or m.get("name", "").lower() == eng_name.lower()),
                None
            )
            if target:
                eng_slack_id = target["id"]
                eng_email    = target.get("profile", {}).get("email", "")
                # DM the new engineer
                slack_client.chat_postMessage(
                    channel=eng_slack_id,
                    text=f"Ticket *{tnum}* has been assigned to you by {user_name}.",
                    mrkdwn=True,
                )
                say(f"Ticket *{tnum}* reassigned to {mention}.")
            else:
                say(f"Engineer {mention} not found in workspace.")
        except Exception as e:
            say(f"Could not reassign: {e}")
        return True

    # ── comment T-XXXX <text> ─────────────────────────────────────────────────
    if cmd == "comment" and tnum and len(parts) > 2:
        ticket = db.query(Ticket).filter(Ticket.ticket_number == tnum).first()
        if not ticket:
            say(f"Ticket {tnum} not found.")
            return True

        comment_text = parts[2].strip()

        # Find the user who raised the ticket and DM them
        from app.models.user import User
        ticket_user = db.query(User).filter(User.id == ticket.user_id).first()
        if ticket_user:
            try:
                result = slack_client.users_lookupByEmail(email=ticket_user.email)
                if result and result.get("user"):
                    slack_client.chat_postMessage(
                        channel=result["user"]["id"],
                        text=(
                            f"Update on your ticket *{tnum}*:\n\n"
                            f"{comment_text}\n\n"
                            f"— {user_name} (Network Engineering)"
                        ),
                        mrkdwn=True,
                    )
                    say(f"Comment sent to user for ticket *{tnum}*.")
                else:
                    say(f"Could not find user to notify for ticket {tnum}.")
            except Exception as e:
                say(f"Comment added but could not notify user: {e}")
        return True

    # ── status T-XXXX ─────────────────────────────────────────────────────────
    if cmd == "status" and tnum:
        ticket = db.query(Ticket).filter(Ticket.ticket_number == tnum).first()
        if not ticket:
            say(f"Ticket {tnum} not found.")
            return True

        from app.models.user import User
        ticket_user = db.query(User).filter(User.id == ticket.user_id).first()
        user_display = ticket_user.full_name if ticket_user else "Unknown"

        status_msg = (
            f"*Ticket {tnum} Status*\n\n"
            f"*Status:* {ticket.status.value.title()}\n"
            f"*Priority:* {ticket.priority.value.upper()}\n"
            f"*Domain:* Networking\n"
            f"*Reported by:* {user_display}\n"
            f"*Created:* {ticket.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
        )
        if ticket.resolved_at:
            status_msg += f"*Resolved:* {ticket.resolved_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
        if ticket.ai_diagnosis:
            status_msg += f"\n*Diagnosis:*\n{ticket.ai_diagnosis[:300]}"

        say(status_msg)
        return True

    # ── snooze T-XXXX 2h ──────────────────────────────────────────────────────
    if cmd == "snooze" and tnum and len(parts) > 2:
        duration = parts[2].strip().lower()
        hours = 2
        if duration.endswith("h"):
            try: hours = int(duration[:-1])
            except: hours = 2
        elif duration.endswith("m"):
            try: hours = int(duration[:-1]) / 60
            except: hours = 0.5

        say(f"Ticket *{tnum}* snoozed for {duration}. You will be reminded after.")
        return True

    return False


def _notify_user_resolved(slack_client, ticket, ticket_number: str):
    """DM the user who raised the ticket to notify resolution."""
    try:
        from app.models.user import User
        from app.core.database import SessionLocal
        db = SessionLocal()
        ticket_user = db.query(User).filter(User.id == ticket.user_id).first()
        db.close()

        if not ticket_user or not ticket_user.email:
            return

        result = slack_client.users_lookupByEmail(email=ticket_user.email)
        if not result or not result.get("user"):
            return

        user_slack_id = result["user"]["id"]
        slack_client.chat_postMessage(
            channel=user_slack_id,
            text=(
                f"Your ticket *{ticket_number}* has been resolved.\n\n"
                f"Issue: {ticket.title}\n"
                f"Status: Resolved\n\n"
                f"If the issue persists, please raise a new ticket."
            ),
            mrkdwn=True,
        )
        logger.info(f"User notified of resolution for {ticket_number}")
    except Exception as e:
        logger.error(f"Failed to notify user of resolution: {e}")


def process_slack_message(
    slack_user_id: str,
    user_name: str,
    user_email: str,
    message: str,
    channel: str,
    slack_client,
    say,
):
    from app.core.database import SessionLocal
    from app.services import chat_service

    session_id = _get_or_create_session(slack_user_id)
    db = SessionLocal()

    try:
        # ── Engineer commands (work from any channel) ─────────────────────────
        msg_lower = message.lower().strip()
        if any(msg_lower.startswith(cmd) for cmd in ["resolved ", "assign ", "comment ", "status ", "snooze "]):
            handled = _handle_engineer_command(message, slack_user_id, user_name, slack_client, say, db)
            if handled:
                return

        # ── Help command ──────────────────────────────────────────────────────
        if msg_lower in ("help", "/help", "?", "commands"):
            say(
                "🤖 *Network Support Bot — Commands*\n\n"
                "*Report an issue:* Just describe what's broken\n"
                "  _e.g. 'BGP session dropped between our router and ISP'_\n"
                "  _e.g. 'Users cannot access the VPN'_\n"
                "  _e.g. 'DNS not resolving internal hostnames'_\n\n"
                "*Start fresh:* `new`\n"
                "*Show this help:* `help`\n\n"
                "💡 _I'll ask a few questions, search our runbooks, and route to the right engineer if needed._"
            )
            return

        # ── New/reset command ─────────────────────────────────────────────────
        if msg_lower in ("new", "reset", "start over", "restart"):
            _reset_session(slack_user_id)
            _pending_new[slack_user_id] = True
            say("Do you want to start a new conversation?")
            return

        # ── New conversation confirmation ─────────────────────────────────────
        if _pending_new.get(slack_user_id):
            if msg_lower in ("yes", "yeah", "y", "sure", "ok", "okay", "yep"):
                del _pending_new[slack_user_id]
                say(
                    "Is something actively broken right now, or do you have a question "
                    "or need a consult from the network team?"
                )
                return
            elif msg_lower in ("no", "nope", "n", "cancel"):
                del _pending_new[slack_user_id]
                say("No problem — your previous session is still active.")
                return

        # ── Welcome on first message ──────────────────────────────────────────
        is_new_session = slack_user_id not in _slack_to_session
        if is_new_session:
            say(
                f"👋 Hi *{user_name}*! I'm the *Network Support Bot*.\n\n"
                "Type `help` anytime to see available commands."
            )
            # Create session but don't process yet — wait for user's actual message
            _get_or_create_session(slack_user_id)
            session = chat_service._get_session(_slack_to_session[slack_user_id])
            session["user_name"]     = user_name
            session["user_email"]    = user_email
            session["source"]        = "slack"
            session["slack_user_id"] = slack_user_id
            return

        # ── Process through chat engine ───────────────────────────────────────
        session = chat_service._get_session(session_id)
        session["user_name"]     = user_name
        session["user_email"]    = user_email
        session["source"]        = "slack"
        session["slack_user_id"] = slack_user_id

        from app.schemas.chat import ChatMessageRequest
        data = ChatMessageRequest(
            session_id = session_id,
            message    = message,
            user_name  = user_name,
            user_email = user_email,
            screenshot = None,
        )

        class SlackUser:
            id        = None
            full_name = user_name
            email     = user_email
            city      = "Slack"
            country   = "Remote"
            timezone  = "UTC"
            role      = type("r", (), {"value": "user"})()

        fake_user = SlackUser()
        response  = chat_service.process_message(db, fake_user, data)
        reply     = (response.reply if hasattr(response, "reply") else str(response)).strip()

        if reply:
            say(reply)

        if hasattr(response, "can_escalate") and response.can_escalate:
            _auto_escalate(
                session_id    = session_id,
                slack_user_id = slack_user_id,
                user_name     = user_name,
                user_email    = user_email,
                channel       = channel,
                slack_client  = slack_client,
                say           = say,
                db            = db,
                session       = session,
            )

    except Exception as e:
        logger.error(f"Slack bridge error: {e}", exc_info=True)
        say("I ran into an issue processing your request. Please try again.")
    finally:
        db.close()


def _auto_escalate(session_id, slack_user_id, user_name, user_email, channel, slack_client, say, db, session):
    try:
        from app.services import chat_service

        class EscalateReq:
            def __init__(self, session_id, title, description, domain, priority):
                self.session_id  = session_id
                self.title       = title
                self.description = description
                self.domain      = domain
                self.priority    = priority
                self.steps_tried = ""
                self.complexity  = "moderate"

        messages  = session.get("messages", [])
        user_msgs = [m["content"] for m in messages if m["role"] == "user"]
        title     = user_msgs[0][:80] if user_msgs else "IT Support Issue"
        severity  = session.get("severity", "medium") or "medium"
        diagnosis = session.get("asset_context", {}).get("diagnosis", "")

        req = EscalateReq(
            session_id  = session_id,
            title       = title,
            description = diagnosis or title,
            domain      = "networking",
            priority    = "high" if severity in ("critical", "high") else "medium",
        )

        # Ensure DB user exists for FK constraint
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

        # Check flow type
        is_consult      = session.get("flow_origin") == "consult"
        is_planning     = session.get("flow_origin") == "planning"
        is_major        = session.get("flow_origin") == "major_incident"

        # Override severity for major incidents
        if is_major:
            req.priority = "critical"

        if is_consult or is_planning:
            _handle_consult_escalation(
                slack_client   = slack_client,
                session        = session,
                user_name      = user_name,
                say            = say,
                slack_user_id  = slack_user_id,
                is_planning    = is_planning,
            )
            _reset_session(slack_user_id)
            return

        ticket_result = chat_service.escalate_to_ticket(db, slack_db_user, req)

        if not ticket_result or not hasattr(ticket_result, "ticket_number"):
            return

        # Generate AI incident report
        from app.core.config import settings as _settings
        import anthropic as _anthropic
        _cl = _anthropic.Anthropic(api_key=_settings.ANTHROPIC_API_KEY)

        msgs  = session.get("messages", [])
        convo = "\n".join(
            ("User: " if m["role"] == "user" else "Bot: ") + m["content"]
            for m in msgs
        )

        try:
            resp = _cl.messages.create(
                model      = "claude-sonnet-4-5",
                max_tokens = 400,
                messages   = [{"role": "user", "content": (
                    "Write a professional IT incident report for a network engineer. "
                    "Plain text only, no markdown symbols.\n\n"
                    "Support conversation:\n" + convo + "\n\n"
                    "Format:\n"
                    "Issue Summary: (1-2 sentences)\n"
                    "Steps Already Tried:\n1. ...\n2. ...\n"
                    "Current Status: (what was found)\n"
                    "Recommended Next Action: (what engineer should check first)"
                )}],
            )
            incident_report = resp.content[0].text.strip()
        except Exception:
            incident_report = diagnosis or title

        # Routing — try asset owner first, then fallback to time/availability
        slack_eng = None
        asset_match = session.get("asset_match")
        contact_email = (asset_match or {}).get("contact_email", "")

        if contact_email:
            # Try to find asset owner in Slack by email
            try:
                result = slack_client.users_lookupByEmail(email=contact_email)
                if result and result.get("user"):
                    member  = result["user"]
                    profile = member.get("profile", {})
                    try:
                        presence  = slack_client.users_getPresence(user=member["id"])
                        is_active = presence.get("presence") == "active"
                    except Exception:
                        is_active = False
                    slack_eng = {
                        "slack_id": member["id"],
                        "name":     profile.get("real_name") or profile.get("display_name") or "",
                        "email":    contact_email,
                        "title":    profile.get("title", ""),
                        "active":   is_active,
                    }
                    logger.info(f"Routing to asset owner: {contact_email} → {slack_eng['name']}")
                    print(f"  [Route] Asset owner Slack found: {contact_email} → {slack_eng['name']}")
            except Exception as e:
                logger.error(f"Asset owner Slack lookup failed for {contact_email}: {e}")
                print(f"  [Route] Asset owner lookup error: {e}")

        # Fallback to time/availability routing if asset owner not found in Slack
        if not slack_eng:
            slack_eng = _find_slack_engineer(slack_client, "networking", slack_user_id)
            if slack_eng:
                logger.info(f"Fallback routing to: {slack_eng['email']}")

        # User-facing ticket confirmation
        try:
            summary_resp = _cl.messages.create(
                model      = "claude-sonnet-4-5",
                max_tokens = 80,
                messages   = [{"role": "user", "content": (
                    "Summarise this IT support issue in one clear professional sentence (max 20 words):\n" +
                    "\n".join(f"User: {m}" for m in user_msgs[:5])
                )}],
            )
            issue_summary = summary_resp.content[0].text.strip().strip('"')
        except Exception:
            issue_summary = user_msgs[0][:120] if user_msgs else "Network issue reported"

        ticket_msg = (
            f"*Ticket {ticket_result.ticket_number} has been raised.*\n\n"
            f"*Issue:* {issue_summary}\n"
            f"*Domain:* Networking\n"
            f"*Priority:* {req.priority.upper()}\n\n"
        )
        if slack_eng:
            ticket_msg += f"*Assigned to:* {slack_eng['name']}"
            if slack_eng.get("title"):
                ticket_msg += f" — {slack_eng['title']}"
            ticket_msg += "\n"
            if slack_eng.get("email"):
                ticket_msg += f"*Contact:* {slack_eng['email']}\n"
            status = "Available" if slack_eng["active"] else "Offline — will be notified"
            ticket_msg += f"*Engineer status:* {status}\n\n"
        else:
            ticket_msg += "*Assigned to:* Network Engineering team\n\n"

        if is_major:
            ticket_msg += "This is a CRITICAL incident. The assigned engineer has been notified immediately and will respond urgently."
        else:
            ticket_msg += "The assigned engineer will review this and follow up shortly."

        say(ticket_msg)

        # Post to engineer private channel + #network-tickets
        _post_ticket_to_channel(
            slack_client      = slack_client,
            ticket_number     = ticket_result.ticket_number,
            user_name         = user_name,
            priority          = req.priority,
            incident_report   = incident_report,
            user_slack_id     = slack_user_id,
            engineer_slack_id = slack_eng["slack_id"] if slack_eng else None,
            engineer_name     = slack_eng["name"] if slack_eng else None,
        )

        # Also DM the assigned engineer individually
        if slack_eng:
            try:
                slack_client.chat_postMessage(
                    channel = slack_eng["slack_id"],
                    text    = (
                        f"New ticket assigned to you: *{ticket_result.ticket_number}*\n"
                        f"Check *#{TICKETS_CHANNEL}* for full details."
                    ),
                    mrkdwn  = True,
                )
            except Exception as e:
                logger.error(f"Failed to DM engineer: {e}")

        _reset_session(slack_user_id)

    except Exception as e:
        logger.error(f"Auto-escalate error: {e}", exc_info=True)


DOMAIN_TITLE_KEYWORDS = {
    "networking":          ["network engineer", "network", "netops", "infrastructure engineer"],
    "security":            ["security engineer", "security", "netskope", "infosec"],
    "cloud":               ["cloud engineer", "cloud", "devops", "platform engineer"],
    "database":            ["database engineer", "dba", "database", "data engineer"],
    "devops":              ["devops", "sre", "platform engineer", "devops engineer"],
    "hardware":            ["hardware engineer", "hardware", "it support", "field engineer"],
    "software":            ["software engineer", "developer", "it support"],
    "identity_access":     ["identity", "iam", "access management", "it support"],
    "endpoint_management": ["endpoint", "it support", "desktop engineer"],
    "other":               ["it support", "engineer", "support"],
}


def _find_slack_engineer(slack_client, domain: str, user_slack_id: str = None):
    try:
        keywords = DOMAIN_TITLE_KEYWORDS.get(domain, DOMAIN_TITLE_KEYWORDS["other"])
        response = slack_client.users_list()
        members  = response.get("members", [])
        candidates = []

        for member in members:
            if member.get("is_bot") or member.get("deleted"):
                continue
            if user_slack_id and member["id"] == user_slack_id:
                continue

            profile = member.get("profile", {})
            title   = (profile.get("title") or "").lower()
            name    = profile.get("real_name") or profile.get("display_name") or ""
            email   = profile.get("email") or ""

            if any(kw in title for kw in keywords):
                try:
                    presence  = slack_client.users_getPresence(user=member["id"])
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
            return None

        # Score by timezone proximity to user (UTC+5:30 = Asia/Kolkata default)
        import pytz
        from datetime import datetime
        now = datetime.utcnow()

        # Get user timezone offset — default Asia/Kolkata
        try:
            user_tz     = pytz.timezone("Asia/Kolkata")
            user_offset = user_tz.utcoffset(now).total_seconds() / 3600
        except Exception:
            user_offset = 5.5

        def score_engineer(eng):
            # Active bonus
            score = 10 if eng["active"] else 0
            # Timezone proximity bonus
            try:
                eng_tz     = pytz.timezone(eng["tz"])
                eng_offset = eng_tz.utcoffset(now).total_seconds() / 3600
                diff       = abs(user_offset - eng_offset)
                score     += max(0, 5 - diff)  # closer timezone = higher score
            except Exception:
                pass
            return score

        candidates.sort(key=score_engineer, reverse=True)
        return candidates[0]

    except Exception as e:
        logger.error(f"Failed to find Slack engineer: {e}")
        return None