# File: backend/app/services/slack_service.py
# NexusDesk Slack Bot — Socket Mode
# Completely isolated from NexusDesk web users
# All identity comes from Slack profiles

import os
import re
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Slack sessions (keyed by Slack user ID) ───────────────────────────────────
_slack_sessions: dict = {}


def _get_slack_session(slack_user_id: str) -> dict:
    if slack_user_id not in _slack_sessions:
        _slack_sessions[slack_user_id] = {
            "session_id":    f"slack_{slack_user_id}",
            "slack_user_id": slack_user_id,
        }
    return _slack_sessions[slack_user_id]


def start_slack_bot():
    """Start the Slack bot in a background thread using Socket Mode."""
    try:
        import ssl
        import certifi
        import os

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

        # ── Helper: get user profile ──────────────────────────────────────────
        def _get_profile(client, slack_user_id: str):
            try:
                user_info = client.users_info(user=slack_user_id)
                profile   = user_info["user"]["profile"]
                name  = profile.get("real_name") or profile.get("display_name") or "Slack User"
                email = profile.get("email", f"{slack_user_id}@slack.user")
            except Exception:
                name  = "Slack User"
                email = f"{slack_user_id}@slack.user"
            return name, email

        # ── Event deduplication — Slack retries if no ACK within 3s ─────────
        # Store seen event IDs in a small rolling set so retries are dropped.
        _seen_event_ids: set = set()
        _seen_event_ids_order: list = []
        _SEEN_MAX = 500  # keep last 500 event IDs in memory

        def _is_duplicate(event_id: str) -> bool:
            if not event_id:
                return False
            if event_id in _seen_event_ids:
                return True
            _seen_event_ids.add(event_id)
            _seen_event_ids_order.append(event_id)
            if len(_seen_event_ids_order) > _SEEN_MAX:
                oldest = _seen_event_ids_order.pop(0)
                _seen_event_ids.discard(oldest)
            return False

        # ── Text messages ─────────────────────────────────────────────────────
        @app.event("message")
        def handle_message(event, say, client):
            # Drop Slack retries — same event_id means already processed
            if _is_duplicate(event.get("event_id") or event.get("client_msg_id")):
                return
            # Ignore bot messages
            if event.get("bot_id"):
                return
            subtype = event.get("subtype", "")
            files   = event.get("files", [])

            # Any non-empty subtype except file_share (which carries images) — ignore
            if subtype and subtype != "file_share":
                return
            # file_share with no images = spurious re-fire of a text message
            if subtype == "file_share" and not any(
                f.get("mimetype", "").startswith("image/") for f in files
            ):
                return

            slack_user_id = event.get("user")
            text          = (event.get("text") or "").strip()
            channel       = event.get("channel")
            files         = event.get("files", [])

            if not slack_user_id:
                return

            user_name, user_email = _get_profile(client, slack_user_id)

            # ── Image attachment in message ───────────────────────────────────
            image_files = [
                f for f in files
                if (f.get("mimetype", "")).startswith("image/")
            ]
            if image_files:
                img       = image_files[0]
                file_url  = img.get("url_private_download") or img.get("url_private")
                mimetype  = img.get("mimetype", "image/png")
                try:
                    from app.services.slack_chat_bridge import process_slack_message
                    process_slack_message(
                        slack_user_id = slack_user_id,
                        user_name     = user_name,
                        user_email    = user_email,
                        message       = text or "[image uploaded]",
                        channel       = channel,
                        slack_client  = client,
                        say           = say,
                        file_url      = file_url,
                        file_mimetype = mimetype,
                    )
                except Exception as e:
                    logger.error(f"Slack image processing error: {e}")
                    say("Sorry, I couldn't analyse that image. Please try again.")
                return

            # ── Plain text message ────────────────────────────────────────────
            if not text:
                return

            try:
                from app.services.slack_chat_bridge import process_slack_message
                process_slack_message(
                    slack_user_id = slack_user_id,
                    user_name     = user_name,
                    user_email    = user_email,
                    message       = text,
                    channel       = channel,
                    slack_client  = client,
                    say           = say,
                )
            except Exception as e:
                logger.error(f"Slack message processing error: {e}")
                say("Sorry, I ran into an issue. Please try again.")

        # ── file_shared event (fallback for files not attached to a message) ──
        @app.event("file_shared")
        def handle_file_shared(event, say, client):
            if _is_duplicate(event.get("event_id")):
                return
            """
            Fires when a file is shared in a DM that doesn't carry a message body.
            Fetches file info, checks it's an image, then routes through bridge.
            """
            slack_user_id = event.get("user_id")
            channel_id    = event.get("channel_id")
            file_id       = event.get("file_id")

            if not slack_user_id or not file_id:
                return

            user_name, user_email = _get_profile(client, slack_user_id)

            try:
                file_info = client.files_info(file=file_id)
                f         = file_info.get("file", {})
                mimetype  = f.get("mimetype", "")
                if not mimetype.startswith("image/"):
                    # Not an image — ignore silently
                    return
                file_url = f.get("url_private_download") or f.get("url_private")
                if not file_url:
                    return
            except Exception as e:
                logger.error(f"Could not fetch file info for {file_id}: {e}")
                return

            try:
                from app.services.slack_chat_bridge import process_slack_message
                process_slack_message(
                    slack_user_id = slack_user_id,
                    user_name     = user_name,
                    user_email    = user_email,
                    message       = "[image uploaded]",
                    channel       = channel_id,
                    slack_client  = client,
                    say           = say,
                    file_url      = file_url,
                    file_mimetype = mimetype,
                )
            except Exception as e:
                logger.error(f"Slack file_shared processing error: {e}")
                say("Sorry, I couldn't analyse that image. Please try again.")

        # ── Button click handler ──────────────────────────────────────────────
        @app.action(re.compile(r".*"))
        def handle_action(ack, body, client, say):
            ack()

            slack_user_id = body.get("user", {}).get("id")
            channel_id    = body.get("channel", {}).get("id") or (
                body.get("container", {}).get("channel_id")
            )
            actions = body.get("actions", [])
            if not actions or not slack_user_id:
                return

            action   = actions[0]
            value    = action.get("value", "")
            block_id = action.get("block_id", "")

            # Get original message text for the disabled confirmation
            original_text = ""
            for block in body.get("message", {}).get("blocks", []):
                if block.get("type") == "section":
                    original_text = block.get("text", {}).get("text", "").strip("*")
                    break

            # Friendly label for the selected value
            label_map = {
                "broken":                  "Something is Broken",
                "consult":                 "Question / Consult",
                "yes":                     "Yes",
                "no":                      "No",
                "deadline_yes":            "Yes, there is a deadline",
                "deadline_no":             "No fixed deadline",
                "continue":                "Continue Troubleshooting",
                "escalate":                "Raise a Support Ticket",
                "next sprint":             "Next Sprint",
                "next release":            "Next Release",
                "next sprint and release": "Next Sprint & Release",
                "no rush":                 "No Rush",
            }
            selected_label = label_map.get(value, value.title())

            # Replace the button message with a static confirmation
            msg_ts = body.get("message", {}).get("ts")
            if msg_ts and channel_id:
                try:
                    client.chat_update(
                        channel = channel_id,
                        ts      = msg_ts,
                        text    = original_text,
                        blocks  = [
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": f"{original_text}"},
                            },
                            {
                                "type": "context",
                                "elements": [
                                    {
                                        "type": "mrkdwn",
                                        "text": f"✅  *Selected:* {selected_label}",
                                    }
                                ],
                            },
                        ],
                    )
                except Exception as e:
                    logger.error(f"Button disable failed: {e}")

            user_name, user_email = _get_profile(client, slack_user_id)

            try:
                from app.services.slack_chat_bridge import process_slack_message
                process_slack_message(
                    slack_user_id = slack_user_id,
                    user_name     = user_name,
                    user_email    = user_email,
                    message       = value,
                    channel       = channel_id,
                    slack_client  = client,
                    say           = say,
                )
            except Exception as e:
                logger.error(f"Button action error: {e}")
                say("Sorry, something went wrong. Please try again.")
        def handle_mention(event, say):
            say("Hi! Please DM me directly to raise an IT support ticket. 👋")

        # ── Start Socket Mode in background thread ────────────────────────────
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