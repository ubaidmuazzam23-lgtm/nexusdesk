# File: backend/app/services/slack_service.py
# NexusDesk Slack Bot — Socket Mode
# Completely isolated from NexusDesk web users
# All identity comes from Slack profiles

import os
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Slack sessions (keyed by Slack user ID) ───────────────────────────────────
# Each Slack user gets their own isolated chat session
_slack_sessions: dict = {}


def _get_slack_session(slack_user_id: str) -> dict:
    if slack_user_id not in _slack_sessions:
        _slack_sessions[slack_user_id] = {
            "session_id": f"slack_{slack_user_id}",
            "slack_user_id": slack_user_id,
        }
    return _slack_sessions[slack_user_id]


def start_slack_bot():
    """Start the Slack bot in a background thread using Socket Mode."""
    try:
        import ssl
        import certifi
        import os

        # Fix for corporate SSL proxy (Netskope) intercepting WebSocket connections
        corp_cert = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
        if corp_cert and os.path.exists(corp_cert):
            ssl_context = ssl.create_default_context(cafile=corp_cert)
            os.environ["SSL_CERT_FILE"]      = corp_cert
            os.environ["REQUESTS_CA_BUNDLE"] = corp_cert

        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
        from app.core.config import settings

        if not settings.SLACK_BOT_TOKEN or not settings.SLACK_APP_TOKEN:
            logger.warning("Slack tokens not configured — Slack bot not started")
            return

        app = App(token=settings.SLACK_BOT_TOKEN)

        # ── Handle DMs and messages ───────────────────────────────────────────
        @app.event("message")
        def handle_message(event, say, client):
            # Ignore bot messages
            if event.get("bot_id") or event.get("subtype"):
                return

            slack_user_id = event.get("user")
            text          = event.get("text", "").strip()
            channel       = event.get("channel")

            if not slack_user_id or not text:
                return

            # Get Slack user profile
            try:
                user_info = client.users_info(user=slack_user_id)
                profile   = user_info["user"]["profile"]
                user_name  = profile.get("real_name") or profile.get("display_name") or "Slack User"
                user_email = profile.get("email", f"{slack_user_id}@slack.user")
            except Exception:
                user_name  = "Slack User"
                user_email = f"{slack_user_id}@slack.user"

            # Process message through NexusDesk chat engine
            try:
                from app.services.slack_chat_bridge import process_slack_message
                response = process_slack_message(
                    slack_user_id=slack_user_id,
                    user_name=user_name,
                    user_email=user_email,
                    message=text,
                    channel=channel,
                    slack_client=client,
                    say=say,
                )
            except Exception as e:
                logger.error(f"Slack message processing error: {e}")
                say("Sorry, I ran into an issue. Please try again.")

        # ── Handle app mentions in channels ──────────────────────────────────
        @app.event("app_mention")
        def handle_mention(event, say):
            say("Hi! Please DM me directly to raise an IT support ticket. 👋")

        # ── Start Socket Mode handler in background thread ────────────────────
        handler = SocketModeHandler(app, settings.SLACK_APP_TOKEN)

        def run():
            logger.info("🔌 Slack bot started — Socket Mode")
            print("\n  🔌 Slack Bot: Connected via Socket Mode\n")
            handler.start()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    except ImportError:
        logger.warning("slack-bolt not installed. Run: pip install slack-bolt")
    except Exception as e:
        logger.error(f"Failed to start Slack bot: {e}")