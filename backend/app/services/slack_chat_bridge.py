# # File: backend/app/services/slack_chat_bridge.py
# # Bridge between Slack messages and chat_service
# # Uses Slack identity — completely separate from web users

# import os
# import uuid
# import logging
# import re as _re
# from typing import Optional
# from sqlalchemy.orm import Session

# logger = logging.getLogger(__name__)

# # ── Button helper ─────────────────────────────────────────────────────────────
# def _say_blocks(say, block_fn):
#     """Send a Block Kit message. Falls back to plain text if blocks fail."""
#     try:
#         payload = block_fn()
#         say(text=payload["text"], blocks=payload["blocks"])
#     except Exception as e:
#         logger.error(f"Block send failed: {e}")
#         say(block_fn()["text"])


# # Reply text → Block Kit dispatcher
# # Maps substrings of chat_service reply text to block functions
# _REPLY_TO_BLOCK = None   # lazy-loaded to avoid circular import

# def _say_reply(say, reply: str, blocks_mod):
#     """Send reply as Block Kit buttons if it matches a button question, else plain text."""
#     global _REPLY_TO_BLOCK
#     if _REPLY_TO_BLOCK is None:
#         _REPLY_TO_BLOCK = [
#             ("Is this customer impacting?",                blocks_mod.customer_impacting),
#             ("Are more than one customer",                 blocks_mod.multi_customer),
#             ("Is there a hard deadline",                   blocks_mod.hard_deadline),
#             ("Do you need help with this today",           blocks_mod.help_today),
#             ("When should the network team pick this up",  blocks_mod.next_sprint),
#             ("I have tried 3 troubleshooting steps",       blocks_mod.mid_check_no_runbook),
#             ("I have gone through several troubleshooting",blocks_mod.mid_check_runbook),
#         ]
#     for substr, block_fn in _REPLY_TO_BLOCK:
#         if substr.lower() in reply.lower():
#             _say_blocks(say, block_fn)
#             return
#     # Plain text fallback
#     say(reply)

# # Track Slack sessions (slack_user_id → session_id)
# _slack_to_session: dict = {}
# # Track pending new conversation confirmations
# _pending_new: dict = {}
# # Track users waiting for ticket raise confirmation (session_id → True)
# _pending_ticket_confirm: dict = {}
# TICKETS_CHANNEL = "network-tickets"
# CONSULT_CHANNEL = "network-consult"


# def _get_or_create_session(slack_user_id: str) -> str:
#     if slack_user_id not in _slack_to_session:
#         _slack_to_session[slack_user_id] = f"slack_{slack_user_id}_{uuid.uuid4().hex[:8]}"
#     return _slack_to_session[slack_user_id]


# def _reset_session(slack_user_id: str):
#     if slack_user_id in _slack_to_session:
#         del _slack_to_session[slack_user_id]
#     _pending_ticket_confirm.pop(slack_user_id, None)


# # ─────────────────────────────────────────────────────────────────────────────
# # IMAGE ANALYSIS — Slack DM
# # ─────────────────────────────────────────────────────────────────────────────

# def analyze_slack_image(
#     file_url: str,
#     slack_client,
#     session_id: str,
#     slack_user_id: str,
#     file_mimetype: str = None,
# ) -> str:
#     """
#     Download image from Slack, run Claude Vision analysis,
#     store result in session for context injection.
#     Returns the user-facing description string.
#     This turn is always marked is_screenshot_turn=True → 0 attempts consumed.
#     """
#     try:
#         import requests
#         from app.core.config import settings as _s

#         token = _s.SLACK_BOT_TOKEN

#         # Use the Slack SDK's own HTTP session via the client — it handles
#         # auth headers correctly for private file downloads
#         image_bytes = None

#         # Method 1: requests with Bearer token (standard)
#         try:
#             resp = requests.get(
#                 file_url,
#                 headers={"Authorization": f"Bearer {token}"},
#                 timeout=15,
#                 allow_redirects=True,
#             )
#             ct = resp.headers.get("Content-Type", "")
#             if resp.status_code == 200 and "text/html" not in ct:
#                 image_bytes = resp.content
#                 print(f"  [ImageDownload] method=bearer size={len(image_bytes)} ct={ct}")
#         except Exception as e:
#             print(f"  [ImageDownload] bearer failed: {e}")

#         # Method 2: files_info → re-fetch with SDK client session
#         if not image_bytes:
#             try:
#                 # Extract file ID from URL: .../files-pri/TEAM/FILE_ID/name.ext
#                 file_id = None
#                 for part in file_url.split("/"):
#                     if part.startswith("F") and len(part) > 8:
#                         file_id = part
#                         break

#                 if file_id:
#                     info      = slack_client.files_info(file=file_id)
#                     fobj      = info.get("file", {})
#                     fresh_url = fobj.get("url_private_download") or fobj.get("url_private")
#                     if fresh_url:
#                         resp = requests.get(
#                             fresh_url,
#                             headers={"Authorization": f"Bearer {token}"},
#                             timeout=15,
#                             allow_redirects=True,
#                         )
#                         ct = resp.headers.get("Content-Type", "")
#                         if resp.status_code == 200 and "text/html" not in ct:
#                             image_bytes = resp.content
#                             print(f"  [ImageDownload] method=files_info size={len(image_bytes)} ct={ct}")
#                         else:
#                             print(f"  [ImageDownload] files_info fetch failed status={resp.status_code} ct={ct}")
#                             print(f"  [ImageDownload] response preview: {resp.content[:200]}")
#             except Exception as e:
#                 print(f"  [ImageDownload] files_info method failed: {e}")

#         if not image_bytes:
#             # Scope issue — bot token likely missing files:read
#             print("  [ImageDownload] ALL methods failed — bot token may be missing files:read scope")
#             raise ValueError(
#                 "Could not download image. Ensure the Slack bot has 'files:read' scope. "
#                 "Go to api.slack.com/apps → OAuth & Permissions → Bot Token Scopes → add files:read → reinstall app."
#             )

#         logger.debug("[ImageDebug] size=%d slack_mimetype=%s", len(image_bytes), file_mimetype)

#         # Re-use existing Vision analysis in chat_service, passing mimetype
#         from app.services.chat_service import analyze_screenshot
#         result = analyze_screenshot(image_bytes, session_id, slack_user_id, media_type=file_mimetype)
#         return result.get("display_text", "Screenshot received. What would you like help with?")

#     except Exception as e:
#         logger.error(f"Slack image analysis failed: {e}")
#         # Still mark screenshot turn so attempt counter is not incremented
#         from app.services import chat_service
#         sess = chat_service._get_session(session_id)
#         sess["is_screenshot_turn"] = True
#         return "I received your screenshot but couldn't analyse it. Can you describe what you're seeing?"


# def _get_or_create_engineer_consult_channel(slack_client, engineer_slack_id: str, engineer_name: str) -> Optional[str]:
#     """Get or create a private consult channel for a specific engineer."""
#     try:
#         safe_name    = engineer_name.lower().replace(" ", "-").replace("_", "-")[:15]
#         channel_name = f"consult-{safe_name}"

#         result = slack_client.conversations_list(types="private_channel")
#         for ch in result.get("channels", []):
#             if ch["name"] == channel_name:
#                 try:
#                     slack_client.conversations_invite(channel=ch["id"], users=engineer_slack_id)
#                 except Exception:
#                     pass
#                 return ch["id"]

#         result     = slack_client.conversations_create(name=channel_name, is_private=True)
#         channel_id = result["channel"]["id"]
#         slack_client.conversations_invite(channel=channel_id, users=engineer_slack_id)
#         slack_client.chat_postMessage(
#             channel=channel_id,
#             text=(
#                 f"*Your private consult channel, {engineer_name}*\n\n"
#                 f"All consultation requests assigned to you will appear here."
#             ),
#             mrkdwn=True,
#         )
#         logger.info(f"Created private consult channel #{channel_name} for {engineer_name}")
#         return channel_id
#     except Exception as e:
#         logger.error(f"Failed to get/create consult channel for {engineer_name}: {e}")
#         return None


# def _get_or_create_consult_channel(slack_client) -> Optional[str]:
#     """Get or create #network-consult channel."""
#     try:
#         result = slack_client.conversations_list(types="public_channel,private_channel")
#         for ch in result.get("channels", []):
#             if ch["name"] == CONSULT_CHANNEL:
#                 return ch["id"]
#         result     = slack_client.conversations_create(name=CONSULT_CHANNEL)
#         channel_id = result["channel"]["id"]
#         slack_client.chat_postMessage(
#             channel=channel_id,
#             text="*Network Consult Channel*\n\nNetwork team consultation requests will be posted here.",
#             mrkdwn=True,
#         )
#         return channel_id
#     except Exception as e:
#         logger.error(f"Failed to get/create consult channel: {e}")
#         return None


# def _handle_consult_escalation(slack_client, session, user_name, say, slack_user_id=None, is_planning=False):
#     """Post rich consult summary to #network-consult channel and notify user of assigned engineer."""
#     try:
#         from app.core.config import settings as _settings
#         import anthropic as _anthropic
#         _cl = _anthropic.Anthropic(api_key=_settings.ANTHROPIC_API_KEY)

#         msgs  = session.get("messages", [])
#         convo = "\n".join(
#             ("User: " if m["role"] == "user" else "Bot: ") + m["content"]
#             for m in msgs
#         )
#         problem = session.get("problem", "Network consultation request")

#         # Append screenshot analysis to convo context if present
#         if session.get("screenshot_analysis"):
#             convo += f"\n\nScreenshot Analysis:\n{session['screenshot_analysis']}"

#         try:
#             resp = _cl.messages.create(
#                 model      = "claude-sonnet-4-5",
#                 max_tokens = 700,
#                 messages   = [{"role": "user", "content": (
#                     "You are writing a detailed consultation brief for a senior network engineer.\n\n"
#                     "Conversation:\n" + convo + "\n\n"
#                     "Write a detailed consultation brief for a senior network engineer.\n\n"
#                     "Based on the conversation, decide which sections are most relevant and useful. "
#                     "Always include at minimum: what the user wants, their current setup, key technical details, "
#                     "your expert recommendation, and next steps for the engineer.\n\n"
#                     "Format rules:\n"
#                     "- Use clear section titles in CAPS on their own line\n"
#                     "- Plain sentences under each section, no markdown symbols\n"
#                     "- Be specific and technical\n"
#                     "- The recommendation section must have concrete tool and architecture suggestions\n"
#                     "- End with numbered action items for the engineer\n"
#                     "- Choose section titles that best fit this specific conversation"
#                 )}],
#             )
#             summary = resp.content[0].text.strip()
#         except Exception:
#             summary = problem

#         consulting_eng = _find_slack_engineer(slack_client, "networking", slack_user_id)

#         if consulting_eng:
#             try:
#                 consult_channel = _get_or_create_engineer_consult_channel(
#                     slack_client, consulting_eng["slack_id"], consulting_eng["name"]
#                 )
#                 if consult_channel:
#                     timeline_label = f"\nTimeline: {session.get('planning_timeline', '')}" if is_planning and session.get('planning_timeline') else ""
#                     slack_client.chat_postMessage(
#                         channel = consult_channel,
#                         text    = (
#                             f"*Consult Request from {user_name}*{timeline_label}\n\n"
#                             f"{summary}"
#                         ),
#                         mrkdwn  = True,
#                     )
#             except Exception as e:
#                 logger.error(f"Failed to post to consult channel: {e}")

#         channel_id = _get_or_create_consult_channel(slack_client)
#         if channel_id:
#             msg = f"*Consult Request from {user_name}*\n"
#             if consulting_eng:
#                 msg += f"*Assigned to:* {consulting_eng['name']}\n\n"
#             msg += summary
#             slack_client.chat_postMessage(channel=channel_id, text=msg, mrkdwn=True)

#         timeline = session.get("planning_timeline", "")
#         if is_planning:
#             timeline_msg = f"This has been scheduled for {timeline}. " if timeline else ""
#         else:
#             timeline_msg = ""

#         if consulting_eng:
#             say(
#                 f"I have shared a detailed summary with the network team.\n\n"
#                 f"{timeline_msg}"
#                 f"Your assigned engineer is *{consulting_eng['name']}* — {consulting_eng['title']}\n"
#                 f"Contact: {consulting_eng['email']}\n\n"
#                 f"They will reach out to you when ready."
#             )
#         else:
#             say(
#                 f"I have shared a detailed summary with the network team. "
#                 f"{timeline_msg}"
#                 f"They will review it and follow up with you."
#             )

#     except Exception as e:
#         logger.error(f"Consult escalation error: {e}")
#         say("I have passed this to the network team for follow-up.")


# def _get_or_create_tickets_channel(slack_client) -> Optional[str]:
#     """Get or create #network-tickets channel, return channel ID."""
#     try:
#         result = slack_client.conversations_list(types="public_channel,private_channel")
#         for ch in result.get("channels", []):
#             if ch["name"] == TICKETS_CHANNEL:
#                 return ch["id"]
#         result = slack_client.conversations_create(name=TICKETS_CHANNEL)
#         channel_id = result["channel"]["id"]
#         slack_client.chat_postMessage(
#             channel=channel_id,
#             text=(
#                 "*Network Tickets Channel*\n\n"
#                 "All network support tickets will be posted here.\n\n"
#                 "*Engineer Commands:*\n"
#                 "`resolved T-XXXX` — Close ticket and notify user\n"
#                 "`assign T-XXXX @engineer` — Reassign ticket\n"
#                 "`comment T-XXXX <text>` — Add comment, notify user\n"
#                 "`status T-XXXX` — Show ticket details\n"
#                 "`snooze T-XXXX 2h` — Snooze for 2 hours"
#             ),
#             mrkdwn=True,
#         )
#         return channel_id
#     except Exception as e:
#         logger.error(f"Failed to get/create tickets channel: {e}")
#         return None


# def _get_or_create_engineer_channel(slack_client, engineer_slack_id: str, engineer_name: str) -> Optional[str]:
#     """Get or create a private channel for a specific engineer."""
#     try:
#         safe_name    = engineer_name.lower().replace(" ", "-").replace("_", "-")[:15]
#         channel_name = f"eng-{safe_name}"

#         result = slack_client.conversations_list(types="private_channel")
#         for ch in result.get("channels", []):
#             if ch["name"] == channel_name:
#                 try:
#                     slack_client.conversations_invite(channel=ch["id"], users=engineer_slack_id)
#                 except Exception:
#                     pass
#                 return ch["id"]

#         result     = slack_client.conversations_create(name=channel_name, is_private=True)
#         channel_id = result["channel"]["id"]

#         slack_client.conversations_invite(channel=channel_id, users=engineer_slack_id)

#         slack_client.chat_postMessage(
#             channel=channel_id,
#             text=(
#                 f"*Your private ticket channel, {engineer_name}*\n\n"
#                 f"All tickets assigned to you will appear here.\n\n"
#                 f"*Commands:*\n"
#                 f"`resolved T-XXXX` — Close ticket and notify user\n"
#                 f"`assign T-XXXX @engineer` — Reassign ticket\n"
#                 f"`comment T-XXXX <text>` — Send update to user\n"
#                 f"`status T-XXXX` — Show ticket details"
#             ),
#             mrkdwn=True,
#         )
#         logger.info(f"Created private channel #{channel_name} for {engineer_name}")
#         return channel_id

#     except Exception as e:
#         logger.error(f"Failed to get/create engineer channel for {engineer_name}: {e}")
#         return None


# def _upload_screenshot(slack_client, channel_id: str, screenshot_path: str, ticket_number: str):
#     """Upload screenshot to a Slack channel using files_upload_v2."""
#     try:
#         import os
#         if not screenshot_path or not os.path.exists(screenshot_path):
#             return

#         filename = os.path.basename(screenshot_path)
#         filesize = os.path.getsize(screenshot_path)

#         # Step 1 — get upload URL
#         url_resp = slack_client.files_getUploadURLExternal(
#             filename = filename,
#             length   = filesize,
#         )
#         if not url_resp.get("ok"):
#             logger.error(f"[Screenshot] getUploadURL failed: {url_resp}")
#             return

#         upload_url = url_resp["upload_url"]
#         file_id    = url_resp["file_id"]

#         # Step 2 — upload bytes to the URL
#         import requests as _req
#         with open(screenshot_path, "rb") as f:
#             up = _req.post(upload_url, files={"file": (filename, f, "image/png")}, timeout=30)
#         if up.status_code != 200:
#             logger.error(f"[Screenshot] upload POST failed: {up.status_code} {up.text[:200]}")
#             return

#         # Step 3 — complete the upload and share to channel
#         complete_resp = slack_client.files_completeUploadExternal(
#             files            = [{"id": file_id, "title": f"Screenshot — {ticket_number}"}],
#             channel_id       = channel_id,
#             initial_comment  = f"Screenshot submitted with ticket {ticket_number}",
#         )
#         if complete_resp.get("ok"):
#             logger.info(f"[Screenshot] Uploaded {filename} to channel {channel_id} for {ticket_number}")
#             print(f"  [Screenshot] Upload success for {ticket_number}")
#         else:
#             logger.error(f"[Screenshot] completeUpload failed: {complete_resp}")

#     except Exception as e:
#         logger.error(f"[Screenshot] Upload error: {e}")
#         print(f"  [Screenshot] Upload error: {e}")
#     """Post new ticket to engineer private channel and #network-tickets."""
#     if engineer_slack_id and engineer_name:
#         try:
#             eng_channel = _get_or_create_engineer_channel(slack_client, engineer_slack_id, engineer_name)
#             if eng_channel:
#                 msg = (
#                     f":ticket: *New Ticket: {ticket_number}*\n\n"
#                     f"*Reported by:* {user_name}\n"
#                     f"*Priority:* {priority.upper()}\n"
#                     f"*Domain:* Networking\n\n"
#                     f"*Incident Report:*\n{incident_report}\n\n"
#                     f"*Commands:*\n"
#                     f"`resolved {ticket_number}` — Close and notify user\n"
#                     f"`assign {ticket_number} @engineer` — Reassign to another engineer\n"
#                     f"`comment {ticket_number} <text>` — Send update to user\n"
#                     f"`status {ticket_number}` — Show details"
#                 )
#                 slack_client.chat_postMessage(channel=eng_channel, text=msg, mrkdwn=True)
#                 # Upload screenshot if available
#                 if screenshot_path and os.path.exists(screenshot_path):
#                     _upload_screenshot(slack_client, eng_channel, screenshot_path, ticket_number)
#                 logger.info(f"Ticket {ticket_number} posted to engineer channel for {engineer_name}")
#         except Exception as e:
#             logger.error(f"Failed to post to engineer channel: {e}")

#     try:
#         channel_id = _get_or_create_tickets_channel(slack_client)
#         if not channel_id:
#             return

#         msg = (
#             f":ticket: *New Ticket: {ticket_number}*\n\n"
#             f"*Reported by:* {user_name}\n"
#             f"*Priority:* {priority.upper()}\n"
#             f"*Domain:* Networking\n"
#             f"*Assigned to:* {engineer_name or 'Unassigned'}\n\n"
#             f"*Incident Report:*\n{incident_report}\n\n"
#             f"`resolved {ticket_number}` `assign {ticket_number} @eng` `comment {ticket_number} <text>` `status {ticket_number}`"
#         )
#         slack_client.chat_postMessage(channel=channel_id, text=msg, mrkdwn=True)
#         # Upload screenshot to #network-tickets too
#         if screenshot_path and os.path.exists(screenshot_path):
#             _upload_screenshot(slack_client, channel_id, screenshot_path, ticket_number)
#         logger.info(f"Ticket {ticket_number} posted to #{TICKETS_CHANNEL}")
#     except Exception as e:
#         logger.error(f"Failed to post ticket to channel: {e}")


# def _post_ticket_to_channel(slack_client, ticket_number, user_name, priority, incident_report, user_slack_id, engineer_slack_id=None, engineer_name=None, screenshot_path=None):
#     """Post new ticket to engineer private channel and #network-tickets."""
#     if engineer_slack_id and engineer_name:
#         try:
#             eng_channel = _get_or_create_engineer_channel(slack_client, engineer_slack_id, engineer_name)
#             if eng_channel:
#                 msg = (
#                     f":ticket: *New Ticket: {ticket_number}*\n\n"
#                     f"*Reported by:* {user_name}\n"
#                     f"*Priority:* {priority.upper()}\n"
#                     f"*Domain:* Networking\n\n"
#                     f"*Incident Report:*\n{incident_report}\n\n"
#                     f"*Commands:*\n"
#                     f"`resolved {ticket_number}` — Close and notify user\n"
#                     f"`assign {ticket_number} @engineer` — Reassign to another engineer\n"
#                     f"`comment {ticket_number} <text>` — Send update to user\n"
#                     f"`status {ticket_number}` — Show details"
#                 )
#                 slack_client.chat_postMessage(channel=eng_channel, text=msg, mrkdwn=True)
#                 # Upload screenshot if available
#                 if screenshot_path and os.path.exists(screenshot_path):
#                     _upload_screenshot(slack_client, eng_channel, screenshot_path, ticket_number)
#                 logger.info(f"Ticket {ticket_number} posted to engineer channel for {engineer_name}")
#         except Exception as e:
#             logger.error(f"Failed to post to engineer channel: {e}")

#     try:
#         channel_id = _get_or_create_tickets_channel(slack_client)
#         if not channel_id:
#             return
#         msg = (
#             f":ticket: *New Ticket: {ticket_number}*\n\n"
#             f"*Reported by:* {user_name}\n"
#             f"*Priority:* {priority.upper()}\n"
#             f"*Domain:* Networking\n"
#             f"*Assigned to:* {engineer_name or 'Unassigned'}\n\n"
#             f"*Incident Report:*\n{incident_report}\n\n"
#             f"`resolved {ticket_number}` `assign {ticket_number} @eng` `comment {ticket_number} <text>` `status {ticket_number}`"
#         )
#         slack_client.chat_postMessage(channel=channel_id, text=msg, mrkdwn=True)
#         # Upload screenshot to #network-tickets too
#         if screenshot_path and os.path.exists(screenshot_path):
#             _upload_screenshot(slack_client, channel_id, screenshot_path, ticket_number)
#         logger.info(f"Ticket {ticket_number} posted to #{TICKETS_CHANNEL}")
#     except Exception as e:
#         logger.error(f"Failed to post ticket to channel: {e}")


# def _handle_engineer_command(message: str, slack_user_id: str, user_name: str, slack_client, say, db):
#     """Handle engineer commands in #network-tickets channel."""
#     from app.models.ticket import Ticket, TicketStatus
#     from datetime import datetime

#     msg   = message.strip()
#     parts = msg.split(" ", 2)
#     cmd   = parts[0].lower() if parts else ""
#     tnum  = parts[1].upper() if len(parts) > 1 else ""

#     if cmd == "resolved" and tnum:
#         ticket = db.query(Ticket).filter(Ticket.ticket_number == tnum).first()
#         if not ticket:
#             say(f"Ticket {tnum} not found.")
#             return True
#         ticket.status      = TicketStatus.RESOLVED
#         ticket.resolved_at = datetime.utcnow()
#         db.commit()
#         _notify_user_resolved(slack_client, ticket, tnum)
#         say(f"Ticket *{tnum}* marked as resolved. User has been notified.")
#         return True

#     if cmd == "assign" and tnum and len(parts) > 2:
#         ticket = db.query(Ticket).filter(Ticket.ticket_number == tnum).first()
#         if not ticket:
#             say(f"Ticket {tnum} not found.")
#             return True
#         mention  = parts[2].strip()
#         eng_name = mention.lstrip("@")
#         try:
#             result  = slack_client.users_list()
#             members = result.get("members", [])
#             target  = next(
#                 (m for m in members
#                  if m.get("profile", {}).get("display_name", "").lower() == eng_name.lower()
#                  or m.get("name", "").lower() == eng_name.lower()),
#                 None
#             )
#             if target:
#                 eng_slack_id = target["id"]
#                 slack_client.chat_postMessage(
#                     channel=eng_slack_id,
#                     text=f"Ticket *{tnum}* has been assigned to you by {user_name}.",
#                     mrkdwn=True,
#                 )
#                 say(f"Ticket *{tnum}* reassigned to {mention}.")
#             else:
#                 say(f"Engineer {mention} not found in workspace.")
#         except Exception as e:
#             say(f"Could not reassign: {e}")
#         return True

#     if cmd == "comment" and tnum and len(parts) > 2:
#         ticket = db.query(Ticket).filter(Ticket.ticket_number == tnum).first()
#         if not ticket:
#             say(f"Ticket {tnum} not found.")
#             return True
#         comment_text = parts[2].strip()
#         from app.models.user import User
#         ticket_user = db.query(User).filter(User.id == ticket.user_id).first()
#         if ticket_user:
#             try:
#                 result = slack_client.users_lookupByEmail(email=ticket_user.email)
#                 if result and result.get("user"):
#                     slack_client.chat_postMessage(
#                         channel=result["user"]["id"],
#                         text=(
#                             f"Update on your ticket *{tnum}*:\n\n"
#                             f"{comment_text}\n\n"
#                             f"— {user_name} (Network Engineering)"
#                         ),
#                         mrkdwn=True,
#                     )
#                     say(f"Comment sent to user for ticket *{tnum}*.")
#                 else:
#                     say(f"Could not find user to notify for ticket {tnum}.")
#             except Exception as e:
#                 say(f"Comment added but could not notify user: {e}")
#         return True

#     if cmd == "status" and tnum:
#         ticket = db.query(Ticket).filter(Ticket.ticket_number == tnum).first()
#         if not ticket:
#             say(f"Ticket {tnum} not found.")
#             return True
#         from app.models.user import User
#         ticket_user  = db.query(User).filter(User.id == ticket.user_id).first()
#         user_display = ticket_user.full_name if ticket_user else "Unknown"
#         status_msg = (
#             f"*Ticket {tnum} Status*\n\n"
#             f"*Status:* {ticket.status.value.title()}\n"
#             f"*Priority:* {ticket.priority.value.upper()}\n"
#             f"*Domain:* Networking\n"
#             f"*Reported by:* {user_display}\n"
#             f"*Created:* {ticket.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
#         )
#         if ticket.resolved_at:
#             status_msg += f"*Resolved:* {ticket.resolved_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
#         if ticket.ai_diagnosis:
#             status_msg += f"\n*Diagnosis:*\n{ticket.ai_diagnosis[:300]}"
#         say(status_msg)
#         return True

#     if cmd == "snooze" and tnum and len(parts) > 2:
#         duration = parts[2].strip().lower()
#         say(f"Ticket *{tnum}* snoozed for {duration}. You will be reminded after.")
#         return True

#     return False


# def _notify_user_resolved(slack_client, ticket, ticket_number: str):
#     """DM the user who raised the ticket to notify resolution."""
#     try:
#         from app.models.user import User
#         from app.core.database import SessionLocal
#         db = SessionLocal()
#         ticket_user = db.query(User).filter(User.id == ticket.user_id).first()
#         db.close()

#         if not ticket_user or not ticket_user.email:
#             return

#         result = slack_client.users_lookupByEmail(email=ticket_user.email)
#         if not result or not result.get("user"):
#             return

#         user_slack_id = result["user"]["id"]
#         slack_client.chat_postMessage(
#             channel=user_slack_id,
#             text=(
#                 f"Your ticket *{ticket_number}* has been resolved.\n\n"
#                 f"Issue: {ticket.title}\n"
#                 f"Status: Resolved\n\n"
#                 f"If the issue persists, please raise a new ticket."
#             ),
#             mrkdwn=True,
#         )
#         logger.info(f"User notified of resolution for {ticket_number}")
#     except Exception as e:
#         logger.error(f"Failed to notify user of resolution: {e}")


# def process_slack_message(
#     slack_user_id: str,
#     user_name: str,
#     user_email: str,
#     message: str,
#     channel: str,
#     slack_client,
#     say,
#     file_url: str = None,       # set when message contains an image
#     file_mimetype: str = None,  # e.g. "image/png"
# ):
#     from app.core.database import SessionLocal
#     from app.services import chat_service
#     from app.services import slack_blocks as blocks

#     session_id = _get_or_create_session(slack_user_id)
#     db = SessionLocal()

#     try:
#         msg_lower = message.lower().strip()

#         # ── Engineer commands ─────────────────────────────────────────────────
#         if any(msg_lower.startswith(cmd) for cmd in ["resolved ", "assign ", "comment ", "status ", "snooze "]):
#             handled = _handle_engineer_command(message, slack_user_id, user_name, slack_client, say, db)
#             if handled:
#                 return

#         # ── Help command ──────────────────────────────────────────────────────
#         if msg_lower in ("help", "/help", "?", "commands"):
#             say(
#                 "🤖 *Network Support Bot — Commands*\n\n"
#                 "*Report an issue:* Just describe what's broken\n"
#                 "  _e.g. 'BGP session dropped between our router and ISP'_\n"
#                 "  _e.g. 'Users cannot access the VPN'_\n"
#                 "  _e.g. 'DNS not resolving internal hostnames'_\n\n"
#                 "*Send a screenshot:* Upload an image — I'll analyse it automatically\n\n"
#                 "*Start fresh:* `new`\n"
#                 "*Show this help:* `help`\n\n"
#                 "💡 _I'll ask a few questions, search our runbooks, and route to the right engineer if needed._"
#             )
#             return

#         # ── New/reset command ─────────────────────────────────────────────────
#         if msg_lower in ("new", "reset", "start over", "restart"):
#             _reset_session(slack_user_id)
#             _pending_new[slack_user_id] = True
#             say("Do you want to start a new conversation?")
#             return

#         # ── New conversation confirmation ─────────────────────────────────────
#         if _pending_new.get(slack_user_id):
#             if msg_lower in ("yes", "yeah", "y", "sure", "ok", "okay", "yep"):
#                 del _pending_new[slack_user_id]
#                 _say_blocks(say, blocks.broken_or_consult)
#                 return
#             elif msg_lower in ("no", "nope", "n", "cancel"):
#                 del _pending_new[slack_user_id]
#                 say("No problem — your previous session is still active.")
#                 return

#         # ── Ticket raise confirmation ─────────────────────────────────────────
#         # User was asked "raise a ticket?" and is now replying
#         if _pending_ticket_confirm.get(slack_user_id):
#             del _pending_ticket_confirm[slack_user_id]
#             session = chat_service._get_session(session_id)

#             # Claude interprets yes/no from free-form reply
#             try:
#                 from app.core.config import settings as _s
#                 import anthropic as _a
#                 _cl = _a.Anthropic(api_key=_s.ANTHROPIC_API_KEY)
#                 resp = _cl.messages.create(
#                     model      = "claude-sonnet-4-5",
#                     max_tokens = 5,
#                     messages   = [{"role": "user", "content": (
#                         f"Does this message confirm they want to raise a support ticket? "
#                         f"Reply YES or NO only.\nMessage: {message}"
#                     )}],
#                 )
#                 confirmed = "YES" in resp.content[0].text.strip().upper()
#             except Exception:
#                 confirmed = msg_lower in ("yes", "yeah", "y", "sure", "ok", "raise", "please")

#             if confirmed:
#                 _auto_escalate(
#                     session_id    = session_id,
#                     slack_user_id = slack_user_id,
#                     user_name     = user_name,
#                     user_email    = user_email,
#                     channel       = channel,
#                     slack_client  = slack_client,
#                     say           = say,
#                     db            = db,
#                     session       = session,
#                 )
#             else:
#                 say("No problem. Let me know if you need anything else or want to continue troubleshooting.")
#             return

#         # ── Screenshot confirmation ───────────────────────────────────────────
#         # User was shown screenshot analysis and asked "is this the issue?"
#         # Skip if message is the image upload placeholder — that's not a user reply
#         session = chat_service._get_session(session_id)
#         if session.get("flow_step") == "waiting_screenshot_confirm" and "[image uploaded]" not in msg_lower:
#             try:
#                 from app.core.config import settings as _s
#                 import anthropic as _a
#                 _cl = _a.Anthropic(api_key=_s.ANTHROPIC_API_KEY)
#                 resp = _cl.messages.create(
#                     model      = "claude-sonnet-4-5",
#                     max_tokens = 5,
#                     messages   = [{"role": "user", "content": (
#                         f"Does this message confirm yes, that is the issue? "
#                         f"Reply YES or NO only.\nMessage: {message}"
#                     )}],
#                 )
#                 confirmed = "YES" in resp.content[0].text.strip().upper()
#             except Exception:
#                 confirmed = msg_lower in ("yes", "yeah", "y", "yep", "correct", "that's it", "exactly")

#             if confirmed:
#                 # User confirmed — start troubleshooting using stored analysis
#                 analysis = session.get("screenshot_analysis", "")
#                 session["flow_step"]   = "ai_analysis"
#                 session["messages"].append({"role": "user", "content": f"[Screenshot confirmed] {analysis[:300]}"})
#                 import re as _re
#                 follow = chat_service._start_ai_analysis(session, session_id)
#                 follow_text = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', follow.reply)
#                 say(follow_text)
#             else:
#                 # User said no or described something different — treat their message as the problem
#                 session["flow_step"]   = "waiting_problem"
#                 session["problem"]     = message[:400]
#                 session["rag_context"] = ""   # clear so RAG is re-fetched for new problem
#                 say("Got it. Can you describe the issue in more detail so I can help you correctly?")
#             return

#         # ── Welcome on first message ──────────────────────────────────────────
#         is_new_session = slack_user_id not in _slack_to_session
#         if is_new_session:
#             say(
#                 f"👋 Hi *{user_name}*! I'm the *Network Support Bot*.\n\n"
#                 "Type `help` anytime to see available commands."
#             )
#             _get_or_create_session(slack_user_id)
#             session = chat_service._get_session(_slack_to_session[slack_user_id])
#             session["user_name"]     = user_name
#             session["user_email"]    = user_email
#             session["source"]        = "slack"
#             session["slack_user_id"] = slack_user_id
#             return

#         # ── Image / screenshot ────────────────────────────────────────────────
#         if file_url and file_mimetype and file_mimetype.startswith("image/"):
#             session = chat_service._get_session(session_id)
#             session["user_name"]     = user_name
#             session["user_email"]    = user_email
#             session["source"]        = "slack"
#             session["slack_user_id"] = slack_user_id

#             display_text = analyze_slack_image(
#                 file_url      = file_url,
#                 slack_client  = slack_client,
#                 session_id    = session_id,
#                 slack_user_id = slack_user_id,
#                 file_mimetype = file_mimetype,
#             )

#             import re as _re
#             display_text = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', display_text)

#             analysis = session.get("screenshot_analysis", "")
#             flow_step = session.get("flow_step", "")

#             # Already waiting for confirmation — don't re-fire
#             if flow_step == "waiting_screenshot_confirm":
#                 return

#             if flow_step == "waiting_problem" and analysis:
#                 # ── First screenshot — describe + ask confirmation ─────────────
#                 # Store analysis and pre-fetch RAG so it's ready when user confirms
#                 session["problem"] = analysis[:400]
#                 try:
#                     from app.core.config import settings as _s
#                     import anthropic as _a
#                     _cl = _a.Anthropic(api_key=_s.ANTHROPIC_API_KEY)
#                     q_resp = _cl.messages.create(
#                         model      = "claude-sonnet-4-5",
#                         max_tokens = 30,
#                         messages   = [{"role": "user", "content": (
#                             "Extract the core IT issue from this screenshot analysis as a 3-6 word "
#                             "search query. Include error code and technology if visible. Plain text only.\n\n"
#                             f"{analysis[:300]}"
#                         )}],
#                     )
#                     rag_query = q_resp.content[0].text.strip()
#                 except Exception:
#                     rag_query = analysis[:200]

#                 rag_context = chat_service._get_rag(rag_query)
#                 session["rag_context"]          = rag_context
#                 session["flow_step"]            = "waiting_screenshot_confirm"
#                 session["flow_origin"]          = session.get("flow_origin") or "broken"
#                 session["is_screenshot_turn"]   = True   # never counts as attempt

#                 # Say the analysis then ask confirmation
#                 say(display_text)
#                 _say_blocks(say, blocks.screenshot_confirm)

#             elif flow_step == "ai_analysis":
#                 # ── Mid-conversation screenshot — inject context, continue, 0 attempts ──
#                 session["is_screenshot_turn"] = True   # blocks attempt counter
#                 say(display_text)
#                 # Continue analysis — do NOT manually append message, process_message does it
#                 from app.schemas.chat import ChatMessageRequest
#                 data = ChatMessageRequest(
#                     session_id = session_id,
#                     message    = f"[Screenshot attached] {analysis[:200]}",
#                     user_name  = user_name,
#                     user_email = user_email,
#                     screenshot = None,
#                 )

#                 class SlackUser:
#                     id        = None
#                     full_name = user_name
#                     email     = user_email
#                     city      = "Slack"
#                     country   = "Remote"
#                     timezone  = "UTC"
#                     role      = type("r", (), {"value": "user"})()

#                 response  = chat_service.process_message(db, SlackUser(), data)
#                 next_step = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1',
#                             response.reply if hasattr(response, "reply") else str(response))
#                 if next_step:
#                     say(next_step)
#                 if hasattr(response, "can_escalate") and response.can_escalate:
#                     _pending_ticket_confirm[slack_user_id] = True
#                     from app.services import slack_blocks as blocks
#                     _say_blocks(say, blocks.ticket_confirm)
#             else:
#                 # Any other step — just show the analysis, store context
#                 session["is_screenshot_turn"] = True
#                 say(display_text)
#             return

#         # ── Normal text message through chat engine ───────────────────────────
#         # If waiting for screenshot confirmation, drop spurious Slack re-fires
#         session = chat_service._get_session(session_id)
#         if session.get("flow_step") == "waiting_screenshot_confirm" and not file_url:
#             return

#         session["user_name"]     = user_name
#         session["user_email"]    = user_email
#         session["source"]        = "slack"
#         session["slack_user_id"] = slack_user_id

#         from app.schemas.chat import ChatMessageRequest
#         data = ChatMessageRequest(
#             session_id = session_id,
#             message    = message,
#             user_name  = user_name,
#             user_email = user_email,
#             screenshot = None,
#         )

#         class SlackUser:
#             id        = None
#             full_name = user_name
#             email     = user_email
#             city      = "Slack"
#             country   = "Remote"
#             timezone  = "UTC"
#             role      = type("r", (), {"value": "user"})()

#         fake_user = SlackUser()
#         response  = chat_service.process_message(db, fake_user, data)
#         reply     = (response.reply if hasattr(response, "reply") else str(response)).strip()

#         if reply:
#             _say_reply(say, reply, blocks)

#         if hasattr(response, "can_escalate") and response.can_escalate:
#             flow_origin  = session.get("flow_origin", "broken")
#             auto_resolved = session.get("auto_resolved", False)

#             if auto_resolved:
#                 # Issue resolved by AI — silently raise ticket and mark resolved
#                 # No message to user, no confirmation prompt
#                 _auto_escalate_resolved(
#                     session_id    = session_id,
#                     slack_user_id = slack_user_id,
#                     user_name     = user_name,
#                     user_email    = user_email,
#                     db            = db,
#                     session       = session,
#                 )
#             elif flow_origin in ("consult", "planning"):
#                 _auto_escalate(
#                     session_id    = session_id,
#                     slack_user_id = slack_user_id,
#                     user_name     = user_name,
#                     user_email    = user_email,
#                     channel       = channel,
#                     slack_client  = slack_client,
#                     say           = say,
#                     db            = db,
#                     session       = session,
#                 )
#             else:
#                 # Broken / major incident — ask user first
#                 _pending_ticket_confirm[slack_user_id] = True
#                 _say_blocks(say, blocks.ticket_confirm)

#     except Exception as e:
#         logger.error(f"Slack bridge error: {e}", exc_info=True)
#         say("I ran into an issue processing your request. Please try again.")
#     finally:
#         db.close()


# def _auto_escalate_resolved(session_id, slack_user_id, user_name, user_email, db, session):
#     """
#     Silently raise a ticket and immediately mark it resolved.
#     Called when AI resolves the issue without escalation.
#     User sees nothing — ticket exists only for analytics.
#     """
#     try:
#         from app.services import chat_service
#         from datetime import datetime

#         class EscalateReq:
#             def __init__(self, session_id, title, description, domain, priority):
#                 self.session_id  = session_id
#                 self.title       = title
#                 self.description = description
#                 self.domain      = domain
#                 self.priority    = priority
#                 self.steps_tried = ""
#                 self.complexity  = "moderate"

#         messages  = session.get("messages", [])
#         user_msgs = [m["content"] for m in messages if m["role"] == "user"]
#         title     = user_msgs[0][:80] if user_msgs else "IT Support Issue"
#         severity  = session.get("severity", "medium") or "medium"

#         req = EscalateReq(
#             session_id  = session_id,
#             title       = title,
#             description = f"[Resolved by AI] {title}",
#             domain      = "networking",
#             priority    = "low",   # resolved issues are low priority
#         )

#         # Ensure DB user exists
#         from app.models.user import User, UserRole
#         from app.core.security import hash_password
#         import uuid as _uuid

#         slack_db_user = db.query(User).filter(User.email == user_email).first()
#         if not slack_db_user:
#             slack_db_user = User(
#                 id              = _uuid.uuid4(),
#                 email           = user_email,
#                 full_name       = user_name,
#                 hashed_password = hash_password(_uuid.uuid4().hex),
#                 role            = UserRole.USER,
#                 is_active       = True,
#                 is_verified     = True,
#                 city            = "Slack",
#                 country         = "Remote",
#                 timezone        = "UTC",
#             )
#             db.add(slack_db_user)
#             db.flush()

#         ticket_result = chat_service.escalate_to_ticket(db, slack_db_user, req)

#         if ticket_result and hasattr(ticket_result, "ticket_number"):
#             # Immediately mark resolved
#             from app.models.ticket import Ticket, TicketStatus
#             ticket = db.query(Ticket).filter(
#                 Ticket.ticket_number == ticket_result.ticket_number
#             ).first()
#             if ticket:
#                 ticket.status      = TicketStatus.RESOLVED
#                 ticket.resolved_at = datetime.utcnow()
#                 db.commit()
#                 logger.info("[AutoResolve] Ticket %s raised and marked resolved (AI resolved)", ticket_result.ticket_number)

#         _reset_session(slack_user_id)

#     except Exception as e:
#         logger.error(f"Auto-resolve ticket error: {e}", exc_info=True)


# def _auto_escalate(session_id, slack_user_id, user_name, user_email, channel, slack_client, say, db, session):
#     try:
#         from app.services import chat_service

#         class EscalateReq:
#             def __init__(self, session_id, title, description, domain, priority):
#                 self.session_id  = session_id
#                 self.title       = title
#                 self.description = description
#                 self.domain      = domain
#                 self.priority    = priority
#                 self.steps_tried = ""
#                 self.complexity  = "moderate"

#         messages  = session.get("messages", [])
#         user_msgs = [m["content"] for m in messages if m["role"] == "user"]
#         title     = user_msgs[0][:80] if user_msgs else "IT Support Issue"
#         severity  = session.get("severity", "medium") or "medium"
#         diagnosis = session.get("asset_context", {}).get("diagnosis", "")

#         req = EscalateReq(
#             session_id  = session_id,
#             title       = title,
#             description = diagnosis or title,
#             domain      = "networking",
#             priority    = "high" if severity in ("critical", "high") else "medium",
#         )

#         # Ensure DB user exists for FK constraint
#         from app.models.user import User, UserRole
#         from app.core.security import hash_password
#         import uuid as _uuid

#         slack_db_user = db.query(User).filter(User.email == user_email).first()
#         if not slack_db_user:
#             slack_db_user = User(
#                 id              = _uuid.uuid4(),
#                 email           = user_email,
#                 full_name       = user_name,
#                 hashed_password = hash_password(_uuid.uuid4().hex),
#                 role            = UserRole.USER,
#                 is_active       = True,
#                 is_verified     = True,
#                 city            = "Slack",
#                 country         = "Remote",
#                 timezone        = "UTC",
#             )
#             db.add(slack_db_user)
#             db.flush()

#         is_consult  = session.get("flow_origin") == "consult"
#         is_planning = session.get("flow_origin") == "planning"
#         is_major    = session.get("flow_origin") == "major_incident"

#         if is_major:
#             req.priority = "critical"

#         if is_consult or is_planning:
#             _handle_consult_escalation(
#                 slack_client  = slack_client,
#                 session       = session,
#                 user_name     = user_name,
#                 say           = say,
#                 slack_user_id = slack_user_id,
#                 is_planning   = is_planning,
#             )
#             _reset_session(slack_user_id)
#             return

#         ticket_result = chat_service.escalate_to_ticket(db, slack_db_user, req)

#         if not ticket_result or not hasattr(ticket_result, "ticket_number"):
#             return

#         # Generate AI incident report — include screenshot analysis if available
#         from app.core.config import settings as _settings
#         import anthropic as _anthropic
#         _cl = _anthropic.Anthropic(api_key=_settings.ANTHROPIC_API_KEY)

#         msgs  = session.get("messages", [])
#         convo = "\n".join(
#             ("User: " if m["role"] == "user" else "Bot: ") + m["content"]
#             for m in msgs
#         )
#         # Append screenshot analysis to the convo so it appears in the incident report
#         if session.get("screenshot_analysis"):
#             convo += f"\n\nScreenshot Analysis:\n{session['screenshot_analysis']}"

#         try:
#             resp = _cl.messages.create(
#                 model      = "claude-sonnet-4-5",
#                 max_tokens = 1000,
#                 messages   = [{"role": "user", "content": (
#                     "Write a detailed professional IT incident report for a network engineer. "
#                     "Plain text only, no markdown symbols, no asterisks, no bullet points.\n\n"
#                     "Support conversation:\n" + convo + "\n\n"
#                     "Format exactly as follows:\n\n"
#                     "Issue Summary: (2-3 sentences describing the full problem)\n\n"
#                     "Steps Already Tried:\n"
#                     "1. (each troubleshooting step that was attempted, be specific)\n"
#                     "2. ...\n"
#                     "(include ALL steps from the conversation, numbered)\n\n"
#                     "Current Status: (detailed description of what was found, what worked, what didn't)\n\n"
#                     "Recommended Next Action: (specific actionable steps the engineer should take first, "
#                     "include commands if relevant)\n\n"
#                     "Be thorough — include all technical details, IP addresses, AS numbers, "
#                     "error codes, and configuration details mentioned in the conversation."
#                 )}],
#             )
#             incident_report = resp.content[0].text.strip()
#         except Exception:
#             incident_report = diagnosis or title

#         # Routing — asset owner first, then fallback
#         slack_eng     = None
#         asset_match   = session.get("asset_match")
#         contact_email = (asset_match or {}).get("contact_email", "")

#         if contact_email:
#             try:
#                 result = slack_client.users_lookupByEmail(email=contact_email)
#                 if result and result.get("user"):
#                     member  = result["user"]
#                     profile = member.get("profile", {})
#                     try:
#                         presence  = slack_client.users_getPresence(user=member["id"])
#                         is_active = presence.get("presence") == "active"
#                     except Exception:
#                         is_active = False
#                     slack_eng = {
#                         "slack_id": member["id"],
#                         "name":     profile.get("real_name") or profile.get("display_name") or "",
#                         "email":    contact_email,
#                         "title":    profile.get("title", ""),
#                         "active":   is_active,
#                     }
#                     logger.info(f"Routing to asset owner: {contact_email} → {slack_eng['name']}")
#             except Exception as e:
#                 logger.error(f"Asset owner Slack lookup failed for {contact_email}: {e}")

#         if not slack_eng:
#             slack_eng = _find_slack_engineer(slack_client, "networking", slack_user_id)
#             if slack_eng:
#                 logger.info(f"Fallback routing to: {slack_eng['email']}")

#         # User-facing ticket confirmation
#         try:
#             summary_resp = _cl.messages.create(
#                 model      = "claude-sonnet-4-5",
#                 max_tokens = 80,
#                 messages   = [{"role": "user", "content": (
#                     "Summarise this IT support issue in one clear professional sentence (max 20 words):\n" +
#                     "\n".join(f"User: {m}" for m in user_msgs[:5])
#                 )}],
#             )
#             issue_summary = summary_resp.content[0].text.strip().strip('"')
#         except Exception:
#             issue_summary = user_msgs[0][:120] if user_msgs else "Network issue reported"

#         ticket_msg = (
#             f"*Ticket {ticket_result.ticket_number} has been raised.*\n\n"
#             f"*Issue:* {issue_summary}\n"
#             f"*Domain:* Networking\n"
#             f"*Priority:* {req.priority.upper()}\n\n"
#         )
#         if slack_eng:
#             ticket_msg += f"*Assigned to:* {slack_eng['name']}"
#             if slack_eng.get("title"):
#                 ticket_msg += f" — {slack_eng['title']}"
#             ticket_msg += "\n"
#             if slack_eng.get("email"):
#                 ticket_msg += f"*Contact:* {slack_eng['email']}\n"
#             status = "Available" if slack_eng["active"] else "Offline — will be notified"
#             ticket_msg += f"*Engineer status:* {status}\n\n"
#         else:
#             ticket_msg += "*Assigned to:* Network Engineering team\n\n"

#         if is_major:
#             ticket_msg += "This is a CRITICAL incident. The assigned engineer has been notified immediately and will respond urgently."
#         else:
#             ticket_msg += "The assigned engineer will review this and follow up shortly."

#         say(ticket_msg)

#         _post_ticket_to_channel(
#             slack_client      = slack_client,
#             ticket_number     = ticket_result.ticket_number,
#             user_name         = user_name,
#             priority          = req.priority,
#             incident_report   = incident_report,
#             user_slack_id     = slack_user_id,
#             engineer_slack_id = slack_eng["slack_id"] if slack_eng else None,
#             engineer_name     = slack_eng["name"] if slack_eng else None,
#             screenshot_path   = session.get("screenshot_path"),
#         )
#         logger.debug("[Screenshot] path at escalation present=%s", bool(session.get("screenshot_path")))

#         if slack_eng:
#             try:
#                 slack_client.chat_postMessage(
#                     channel = slack_eng["slack_id"],
#                     text    = (
#                         f"New ticket assigned to you: *{ticket_result.ticket_number}*\n"
#                         f"Check *#{TICKETS_CHANNEL}* for full details."
#                     ),
#                     mrkdwn  = True,
#                 )
#             except Exception as e:
#                 logger.error(f"Failed to DM engineer: {e}")

#         _reset_session(slack_user_id)

#     except Exception as e:
#         logger.error(f"Auto-escalate error: {e}", exc_info=True)


# DOMAIN_TITLE_KEYWORDS = {
#     "networking":          ["network engineer", "network", "netops", "infrastructure engineer"],
#     "security":            ["security engineer", "security", "netskope", "infosec"],
#     "cloud":               ["cloud engineer", "cloud", "devops", "platform engineer"],
#     "database":            ["database engineer", "dba", "database", "data engineer"],
#     "devops":              ["devops", "sre", "platform engineer", "devops engineer"],
#     "hardware":            ["hardware engineer", "hardware", "it support", "field engineer"],
#     "software":            ["software engineer", "developer", "it support"],
#     "identity_access":     ["identity", "iam", "access management", "it support"],
#     "endpoint_management": ["endpoint", "it support", "desktop engineer"],
#     "other":               ["it support", "engineer", "support"],
# }


# def _find_slack_engineer(slack_client, domain: str, user_slack_id: str = None):
#     try:
#         keywords = DOMAIN_TITLE_KEYWORDS.get(domain, DOMAIN_TITLE_KEYWORDS["other"])
#         response = slack_client.users_list()
#         members  = response.get("members", [])
#         candidates = []

#         for member in members:
#             if member.get("is_bot") or member.get("deleted"):
#                 continue
#             if user_slack_id and member["id"] == user_slack_id:
#                 continue

#             profile = member.get("profile", {})
#             title   = (profile.get("title") or "").lower()
#             name    = profile.get("real_name") or profile.get("display_name") or ""
#             email   = profile.get("email") or ""

#             if any(kw in title for kw in keywords):
#                 try:
#                     presence  = slack_client.users_getPresence(user=member["id"])
#                     is_active = presence.get("presence") == "active"
#                 except Exception:
#                     is_active = False

#                 candidates.append({
#                     "slack_id": member["id"],
#                     "name":     name,
#                     "email":    email,
#                     "title":    profile.get("title", ""),
#                     "tz":       member.get("tz", "UTC"),
#                     "active":   is_active,
#                 })

#         if not candidates:
#             return None

#         import pytz
#         from datetime import datetime
#         now = datetime.utcnow()

#         try:
#             user_tz     = pytz.timezone("Asia/Kolkata")
#             user_offset = user_tz.utcoffset(now).total_seconds() / 3600
#         except Exception:
#             user_offset = 5.5

#         def score_engineer(eng):
#             score = 10 if eng["active"] else 0
#             try:
#                 eng_tz     = pytz.timezone(eng["tz"])
#                 eng_offset = eng_tz.utcoffset(now).total_seconds() / 3600
#                 diff       = abs(user_offset - eng_offset)
#                 score     += max(0, 5 - diff)
#             except Exception:
#                 pass
#             return score

#         candidates.sort(key=score_engineer, reverse=True)
#         return candidates[0]

#     except Exception as e:
#         logger.error(f"Failed to find Slack engineer: {e}")
#         return None

# File: backend/app/services/slack_chat_bridge.py
# Bridge between Slack messages and chat_service
# Uses Slack identity — completely separate from web users

import os
import uuid
import logging
import re as _re
from typing import Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Anthropic client singleton ────────────────────────────────────────────────
_cl = None

def _get_cl():
    global _cl
    if _cl is None:
        import anthropic as _anthropic
        from app.core.config import settings as _settings
        _cl = _anthropic.Anthropic(api_key=_settings.ANTHROPIC_API_KEY)
    return _cl


# ── Button helper ─────────────────────────────────────────────────────────────
def _say_blocks(say, block_fn):
    """Send a Block Kit message. Falls back to plain text if blocks fail."""
    try:
        payload = block_fn()
        say(text=payload["text"], blocks=payload["blocks"])
    except Exception as e:
        logger.error(f"Block send failed: {e}")
        say(block_fn()["text"])


# Reply text → Block Kit dispatcher
# Maps substrings of chat_service reply text to block functions
_REPLY_TO_BLOCK = None   # lazy-loaded to avoid circular import

def _say_reply(say, reply: str, blocks_mod):
    """Send reply as Block Kit buttons if it matches a button question, else plain text."""
    global _REPLY_TO_BLOCK
    if _REPLY_TO_BLOCK is None:
        _REPLY_TO_BLOCK = [
            ("Is this customer impacting?",                blocks_mod.customer_impacting),
            ("Are more than one customer",                 blocks_mod.multi_customer),
            ("Is there a hard deadline",                   blocks_mod.hard_deadline),
            ("Do you need help with this today",           blocks_mod.help_today),
            ("When should the network team pick this up",  blocks_mod.next_sprint),
            ("I have tried 3 troubleshooting steps so far", blocks_mod.mid_check_no_runbook),
            ("I have gone through several troubleshooting", blocks_mod.mid_check_runbook),
        ]
    for substr, block_fn in _REPLY_TO_BLOCK:
        if substr.lower() in reply.lower():
            _say_blocks(say, block_fn)
            return
    # Plain text fallback
    say(reply)

# Track Slack sessions (slack_user_id → session_id)
_slack_to_session: dict = {}
# Track pending new conversation confirmations
_pending_new: dict = {}
# Track users waiting for ticket raise confirmation (slack_user_id → True)
_pending_ticket_confirm: dict = {}

_SLACK_SESSION_MAX = 10_000  # ~10k concurrent Slack users max

TICKETS_CHANNEL = "network-tickets"
CONSULT_CHANNEL = "network-consult"


def _evict_slack_dicts() -> None:
    """Drop oldest 10% of session entries when cap is reached."""
    if len(_slack_to_session) >= _SLACK_SESSION_MAX:
        evict_n = max(1, _SLACK_SESSION_MAX // 10)
        for uid in list(_slack_to_session.keys())[:evict_n]:
            _slack_to_session.pop(uid, None)
            _pending_new.pop(uid, None)
            _pending_ticket_confirm.pop(uid, None)


def _get_or_create_session(slack_user_id: str) -> str:
    if slack_user_id not in _slack_to_session:
        _evict_slack_dicts()
        _slack_to_session[slack_user_id] = f"slack_{slack_user_id}_{uuid.uuid4().hex[:8]}"
    return _slack_to_session[slack_user_id]


def _reset_session(slack_user_id: str):
    if slack_user_id in _slack_to_session:
        del _slack_to_session[slack_user_id]
    _pending_ticket_confirm.pop(slack_user_id, None)
    _pending_new.pop(slack_user_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# IMAGE ANALYSIS — Slack DM
# ─────────────────────────────────────────────────────────────────────────────

def analyze_slack_image(
    file_url: str,
    slack_client,
    session_id: str,
    slack_user_id: str,
    file_mimetype: str = None,
) -> str:
    """
    Download image from Slack, run Claude Vision analysis,
    store result in session for context injection.
    Returns the user-facing description string.
    This turn is always marked is_screenshot_turn=True → 0 attempts consumed.
    """
    try:
        import requests
        from app.core.config import settings as _s

        token = _s.SLACK_BOT_TOKEN

        # Use the Slack SDK's own HTTP session via the client — it handles
        # auth headers correctly for private file downloads
        image_bytes = None

        # Method 1: requests with Bearer token (standard)
        try:
            resp = requests.get(
                file_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
                allow_redirects=True,
            )
            ct = resp.headers.get("Content-Type", "")
            if resp.status_code == 200 and "text/html" not in ct:
                image_bytes = resp.content
                logger.debug("[ImageDownload] bearer OK size=%d ct=%s", len(image_bytes), ct)
        except Exception as e:
            logger.debug("[ImageDownload] bearer failed: %s", e)

        # Method 2: files_info → re-fetch with SDK client session
        if not image_bytes:
            try:
                # Extract file ID from URL: .../files-pri/TEAM/FILE_ID/name.ext
                file_id = None
                for part in file_url.split("/"):
                    if part.startswith("F") and len(part) > 8:
                        file_id = part
                        break

                if file_id:
                    info      = slack_client.files_info(file=file_id)
                    fobj      = info.get("file", {})
                    fresh_url = fobj.get("url_private_download") or fobj.get("url_private")
                    if fresh_url:
                        resp = requests.get(
                            fresh_url,
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=15,
                            allow_redirects=True,
                        )
                        ct = resp.headers.get("Content-Type", "")
                        if resp.status_code == 200 and "text/html" not in ct:
                            image_bytes = resp.content
                            logger.debug("[ImageDownload] files_info OK size=%d ct=%s", len(image_bytes), ct)
                        else:
                            logger.warning("[ImageDownload] files_info fetch failed status=%d ct=%s",
                                           resp.status_code, ct)
            except Exception as e:
                logger.debug("[ImageDownload] files_info method failed: %s", e)

        if not image_bytes:
            logger.warning("[ImageDownload] ALL methods failed — bot token may be missing files:read scope")
            raise ValueError(
                "Could not download image. Ensure the Slack bot has 'files:read' scope. "
                "Go to api.slack.com/apps → OAuth & Permissions → Bot Token Scopes → add files:read → reinstall app."
            )

        logger.debug("[ImageDebug] size=%d slack_mimetype=%s", len(image_bytes), file_mimetype)

        # Re-use existing Vision analysis in chat_service, passing mimetype
        from app.services.chat_service import analyze_screenshot
        result = analyze_screenshot(image_bytes, session_id, slack_user_id, media_type=file_mimetype)
        return result.get("display_text", "Screenshot received. What would you like help with?")

    except Exception as e:
        logger.error(f"Slack image analysis failed: {e}")
        # Still mark screenshot turn so attempt counter is not incremented
        from app.services import chat_service
        sess = chat_service._get_session(session_id)
        sess["is_screenshot_turn"] = True
        return "I received your screenshot but couldn't analyse it. Can you describe what you're seeing?"


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
        cursor = None
        while True:
            kwargs = {"types": "public_channel,private_channel", "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            result = slack_client.conversations_list(**kwargs)
            for ch in result.get("channels", []):
                if ch["name"] == CONSULT_CHANNEL:
                    return ch["id"]
            cursor = (result.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
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
        _acl = _get_cl()

        msgs  = session.get("messages", [])
        convo = "\n".join(
            ("User: " if m["role"] == "user" else "Bot: ") + m["content"]
            for m in msgs
        )
        problem = session.get("problem", "Network consultation request")

        # Append screenshot analysis to convo context if present
        if session.get("screenshot_analysis"):
            convo += f"\n\nScreenshot Analysis:\n{session['screenshot_analysis']}"

        try:
            resp = _acl.messages.create(
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

        consulting_eng = _find_slack_engineer(slack_client, "networking", slack_user_id)

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

        channel_id = _get_or_create_consult_channel(slack_client)
        if channel_id:
            msg = f"*Consult Request from {user_name}*\n"
            if consulting_eng:
                msg += f"*Assigned to:* {consulting_eng['name']}\n\n"
            msg += summary
            slack_client.chat_postMessage(channel=channel_id, text=msg, mrkdwn=True)

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
        cursor = None
        while True:
            kwargs = {"types": "public_channel,private_channel", "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            result = slack_client.conversations_list(**kwargs)
            for ch in result.get("channels", []):
                if ch["name"] == TICKETS_CHANNEL:
                    return ch["id"]
            cursor = (result.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        result = slack_client.conversations_create(name=TICKETS_CHANNEL)
        channel_id = result["channel"]["id"]
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
        safe_name    = engineer_name.lower().replace(" ", "-").replace("_", "-")[:15]
        channel_name = f"eng-{safe_name}"

        # Fetch all pages of private channels
        cursor = None
        while True:
            kwargs = {"types": "private_channel", "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            result = slack_client.conversations_list(**kwargs)
            for ch in result.get("channels", []):
                if ch["name"] == channel_name:
                    try:
                        slack_client.conversations_invite(channel=ch["id"], users=engineer_slack_id)
                    except Exception:
                        pass
                    return ch["id"]
            cursor = (result.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break

        result     = slack_client.conversations_create(name=channel_name, is_private=True)
        channel_id = result["channel"]["id"]

        slack_client.conversations_invite(channel=channel_id, users=engineer_slack_id)

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


def _upload_screenshot(slack_client, channel_id: str, screenshot_path: str, ticket_number: str):
    """Upload screenshot to a Slack channel using files_upload_v2."""
    try:
        import os
        if not screenshot_path or not os.path.exists(screenshot_path):
            return

        filename = os.path.basename(screenshot_path)
        filesize = os.path.getsize(screenshot_path)

        # Step 1 — get upload URL
        url_resp = slack_client.files_getUploadURLExternal(
            filename = filename,
            length   = filesize,
        )
        if not url_resp.get("ok"):
            logger.error(f"[Screenshot] getUploadURL failed: {url_resp}")
            return

        upload_url = url_resp["upload_url"]
        file_id    = url_resp["file_id"]

        # Step 2 — upload bytes to the URL
        import requests as _req
        with open(screenshot_path, "rb") as f:
            up = _req.post(upload_url, files={"file": (filename, f, "image/png")}, timeout=30)
        if up.status_code != 200:
            logger.error(f"[Screenshot] upload POST failed: {up.status_code} {up.text[:200]}")
            return

        # Step 3 — complete the upload and share to channel
        complete_resp = slack_client.files_completeUploadExternal(
            files            = [{"id": file_id, "title": f"Screenshot — {ticket_number}"}],
            channel_id       = channel_id,
            initial_comment  = f"Screenshot submitted with ticket {ticket_number}",
        )
        if complete_resp.get("ok"):
            logger.info("[Screenshot] Uploaded %s to channel %s for %s", filename, channel_id, ticket_number)
        else:
            logger.error("[Screenshot] completeUpload failed: %s", complete_resp)

    except Exception as e:
        logger.error("[Screenshot] Upload error: %s", e)


def _post_ticket_to_channel(slack_client, ticket_number, user_name, priority, incident_report,
                            user_slack_id, engineer_slack_id=None, engineer_name=None,
                            screenshot_path=None, user_email=None, user_timezone=None):
    """Post new ticket to engineer private channel and #network-tickets."""
    contact_block = ""
    if user_email:
        contact_block += f"*User Email:* {user_email}\n"
    if user_timezone and user_timezone not in ("UTC", "Slack", "Remote"):
        contact_block += f"*User Timezone:* {user_timezone}\n"
    if contact_block:
        contact_block = contact_block.rstrip("\n") + "\n\n"

    if engineer_slack_id and engineer_name:
        try:
            eng_channel = _get_or_create_engineer_channel(slack_client, engineer_slack_id, engineer_name)
            if eng_channel:
                msg = (
                    f":ticket: *New Ticket: {ticket_number}*\n\n"
                    f"*Reported by:* {user_name}\n"
                    f"{contact_block}"
                    f"*Priority:* {priority.upper()}\n"
                    f"*Domain:* Networking\n\n"
                    f"*Incident Report:*\n{incident_report}\n\n"
                    f"*Commands:*\n"
                    f"`resolved {ticket_number}` — Close and notify user\n"
                    f"`assign {ticket_number} @engineer` — Reassign to another engineer\n"
                    f"`comment {ticket_number} <text>` — Send update to user\n"
                    f"`status {ticket_number}` — Show details"
                )
                slack_client.chat_postMessage(channel=eng_channel, text=msg, mrkdwn=True)
                if screenshot_path and os.path.exists(screenshot_path):
                    _upload_screenshot(slack_client, eng_channel, screenshot_path, ticket_number)
                logger.info(f"Ticket {ticket_number} posted to engineer channel for {engineer_name}")
        except Exception as e:
            logger.error(f"Failed to post to engineer channel: {e}")

    try:
        channel_id = _get_or_create_tickets_channel(slack_client)
        if not channel_id:
            return
        msg = (
            f":ticket: *New Ticket: {ticket_number}*\n\n"
            f"*Reported by:* {user_name}\n"
            f"{contact_block}"
            f"*Priority:* {priority.upper()}\n"
            f"*Domain:* Networking\n"
            f"*Assigned to:* {engineer_name or 'Unassigned'}\n\n"
            f"*Incident Report:*\n{incident_report}\n\n"
            f"`resolved {ticket_number}` `assign {ticket_number} @eng` `comment {ticket_number} <text>` `status {ticket_number}`"
        )
        slack_client.chat_postMessage(channel=channel_id, text=msg, mrkdwn=True)
        # Upload screenshot to #network-tickets too
        if screenshot_path and os.path.exists(screenshot_path):
            _upload_screenshot(slack_client, channel_id, screenshot_path, ticket_number)
        logger.info(f"Ticket {ticket_number} posted to #{TICKETS_CHANNEL}")
    except Exception as e:
        logger.error(f"Failed to post ticket to channel: {e}")


def _handle_engineer_command(message: str, slack_user_id: str, user_name: str, slack_client, say, db):
    """Handle engineer commands in #network-tickets channel."""
    from app.models.ticket import Ticket, TicketStatus
    from datetime import datetime

    msg   = message.strip()
    parts = msg.split(" ", 2)
    cmd   = parts[0].lower() if parts else ""
    tnum  = parts[1].upper() if len(parts) > 1 else ""

    if cmd == "resolved" and tnum:
        ticket = db.query(Ticket).filter(Ticket.ticket_number == tnum).first()
        if not ticket:
            say(f"Ticket {tnum} not found.")
            return True
        ticket.status      = TicketStatus.RESOLVED
        ticket.resolved_at = datetime.utcnow()
        db.commit()
        _notify_user_resolved(slack_client, ticket, tnum)
        say(f"Ticket *{tnum}* marked as resolved. User has been notified.")
        return True

    if cmd == "assign" and tnum and len(parts) > 2:
        ticket = db.query(Ticket).filter(Ticket.ticket_number == tnum).first()
        if not ticket:
            say(f"Ticket {tnum} not found.")
            return True
        mention  = parts[2].strip()
        try:
            import re as _re
            # Slack converts @mention to <@USERID> or <@USERID|name> in message payload
            _slack_id_match = _re.match(r'<@([A-Z0-9]+)(?:\|[^>]*)?>', mention, _re.IGNORECASE)

            # Fetch all pages
            members = []
            cursor  = None
            while True:
                kwargs = {"limit": 200}
                if cursor:
                    kwargs["cursor"] = cursor
                result  = slack_client.users_list(**kwargs)
                members.extend(result.get("members", []))
                cursor = (result.get("response_metadata") or {}).get("next_cursor")
                if not cursor:
                    break

            if _slack_id_match:
                # Direct ID lookup — most reliable
                eng_user_id = _slack_id_match.group(1).upper()
                target = next((m for m in members if m["id"] == eng_user_id), None)
            else:
                # Plain text name fallback (e.g. typed without @mention autocomplete)
                eng_name = mention.lstrip("@").lower()
                def _matches(m):
                    p = m.get("profile", {})
                    return (
                        (p.get("display_name", "").lower()            == eng_name) or
                        (p.get("display_name_normalized", "").lower() == eng_name) or
                        (m.get("name", "").lower()                    == eng_name) or
                        (p.get("real_name", "").lower()               == eng_name)
                    )
                target = next((m for m in members if not m.get("is_bot") and _matches(m)), None)
            if target:
                eng_slack_id  = target["id"]
                new_eng_name  = target.get("profile", {}).get("real_name") or target.get("name", eng_name)
                target_email  = target.get("profile", {}).get("email", "")
                from app.models.user import User as _User
                target_db_user = db.query(_User).filter(_User.email == target_email).first() if target_email else None
                if target_db_user:
                    ticket.engineer_id = target_db_user.id
                    db.commit()

                # Post full ticket to new engineer's private channel
                try:
                    eng_channel = _get_or_create_engineer_channel(slack_client, eng_slack_id, new_eng_name)
                    if eng_channel:
                        from app.models.user import User as _U
                        ticket_user = db.query(_U).filter(_U.id == ticket.user_id).first()
                        contact_block = ""
                        if ticket_user and ticket_user.email:
                            contact_block += f"*User Email:* {ticket_user.email}\n"
                        if ticket_user and ticket_user.timezone and ticket_user.timezone not in ("UTC", "Slack", "Remote"):
                            contact_block += f"*User Timezone:* {ticket_user.timezone}\n"
                        if contact_block:
                            contact_block += "\n"
                        reporter = ticket_user.full_name if ticket_user else "Unknown"
                        msg = (
                            f":ticket: *Ticket Reassigned to You: {tnum}*\n"
                            f"_Reassigned by {user_name}_\n\n"
                            f"*Reported by:* {reporter}\n"
                            f"{contact_block}"
                            f"*Priority:* {ticket.priority.value.upper()}\n"
                            f"*Domain:* Networking\n\n"
                            f"*Diagnosis:*\n{ticket.ai_diagnosis[:600] if ticket.ai_diagnosis else 'See conversation history.'}\n\n"
                            f"*Commands:*\n"
                            f"`resolved {tnum}` — Close and notify user\n"
                            f"`assign {tnum} @engineer` — Reassign again\n"
                            f"`comment {tnum} <text>` — Send update to user\n"
                            f"`status {tnum}` — Show details"
                        )
                        slack_client.chat_postMessage(channel=eng_channel, text=msg, mrkdwn=True)
                except Exception as e:
                    logger.error(f"Failed to post reassignment to engineer channel: {e}")
                    # Fallback to DM
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

    if cmd == "comment" and tnum and len(parts) > 2:
        ticket = db.query(Ticket).filter(Ticket.ticket_number == tnum).first()
        if not ticket:
            say(f"Ticket {tnum} not found.")
            return True
        comment_text = parts[2].strip()
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

    if cmd == "status" and tnum:
        ticket = db.query(Ticket).filter(Ticket.ticket_number == tnum).first()
        if not ticket:
            say(f"Ticket {tnum} not found.")
            return True
        from app.models.user import User
        ticket_user  = db.query(User).filter(User.id == ticket.user_id).first()
        user_display = ticket_user.full_name if ticket_user else "Unknown"
        status_msg = (
            f"*Ticket {tnum} Status*\n\n"
            f"*Status:* {ticket.status.value.title()}\n"
            f"*Priority:* {ticket.priority.value.upper()}\n"
            f"*Domain:* Networking\n"
            f"*Reported by:* {user_display}\n"
        )
        if ticket_user and ticket_user.email:
            status_msg += f"*User Email:* {ticket_user.email}\n"
        if ticket_user and ticket_user.timezone and ticket_user.timezone not in ("UTC", "Slack", "Remote"):
            status_msg += f"*User Timezone:* {ticket_user.timezone}\n"
        status_msg += f"*Created:* {ticket.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
        if ticket.resolved_at:
            status_msg += f"*Resolved:* {ticket.resolved_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
        if ticket.ai_diagnosis:
            status_msg += f"\n*Diagnosis:*\n{ticket.ai_diagnosis[:300]}"
        say(status_msg)
        return True

    if cmd == "snooze" and tnum and len(parts) > 2:
        duration = parts[2].strip().lower()
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
    file_url: str = None,       # set when message contains an image
    file_mimetype: str = None,  # e.g. "image/png"
):
    from app.core.database import SessionLocal
    from app.services import chat_service
    from app.services import slack_blocks as blocks

    session_id = _get_or_create_session(slack_user_id)
    db = SessionLocal()

    try:
        msg_lower = message.lower().strip()
        logger.info(f"[SlackMsg] user={slack_user_id} channel={channel} msg={message!r}")

        # ── Engineer commands ─────────────────────────────────────────────────
        # Match on first word so spacing/formatting variations don't break routing
        _first_word = msg_lower.split()[0] if msg_lower.split() else ""
        if _first_word in ("resolved", "assign", "comment", "status", "snooze"):
            logger.info(f"[EngineerCmd] user={slack_user_id} channel={channel} msg={message!r}")
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
                "*Send a screenshot:* Upload an image — I'll analyse it automatically\n\n"
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
                _say_blocks(say, blocks.broken_or_consult)
                return
            elif msg_lower in ("no", "nope", "n", "cancel"):
                del _pending_new[slack_user_id]
                say("No problem — your previous session is still active.")
                return

        # ── Ticket raise confirmation ─────────────────────────────────────────
        # User was asked "raise a ticket?" and is now replying
        if _pending_ticket_confirm.get(slack_user_id):
            del _pending_ticket_confirm[slack_user_id]
            session = chat_service._get_session(session_id)

            # Claude interprets yes/no from free-form reply
            try:
                resp = _get_cl().messages.create(
                    model      = "claude-sonnet-4-5",
                    max_tokens = 5,
                    messages   = [{"role": "user", "content": (
                        f"Does this message confirm they want to raise a support ticket? "
                        f"Reply YES or NO only.\nMessage: {message}"
                    )}],
                )
                confirmed = "YES" in resp.content[0].text.strip().upper()
            except Exception:
                confirmed = msg_lower in ("yes", "yeah", "y", "sure", "ok", "raise", "please")

            if confirmed:
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
            else:
                say("I have exhausted all troubleshooting steps available to me. If the issue persists, please start a new conversation to raise a ticket.")
                _reset_session(slack_user_id)
            return

        # ── Screenshot confirmation ───────────────────────────────────────────
        # User was shown screenshot analysis and asked "is this the issue?"
        # Skip if message is the image upload placeholder — that's not a user reply
        session = chat_service._get_session(session_id)
        if session.get("flow_step") == "waiting_screenshot_confirm" and "[image uploaded]" not in msg_lower:
            try:
                resp = _get_cl().messages.create(
                    model      = "claude-sonnet-4-5",
                    max_tokens = 5,
                    messages   = [{"role": "user", "content": (
                        f"Does this message confirm yes, that is the issue? "
                        f"Reply YES or NO only.\nMessage: {message}"
                    )}],
                )
                confirmed = "YES" in resp.content[0].text.strip().upper()
            except Exception:
                confirmed = msg_lower in ("yes", "yeah", "y", "yep", "correct", "that's it", "exactly")

            if confirmed:
                # User confirmed — start troubleshooting using stored analysis
                analysis = session.get("screenshot_analysis", "")
                session["flow_step"]   = "ai_analysis"
                session["messages"].append({"role": "user", "content": f"[Screenshot confirmed] {analysis[:300]}"})
                import re as _re
                follow = chat_service._start_ai_analysis(session, session_id)
                follow_text = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', follow.reply)
                say(follow_text)
            else:
                # User said no or described something different — treat their message as the problem
                session["flow_step"]   = "waiting_problem"
                session["problem"]     = message[:400]
                session["rag_context"] = ""   # clear so RAG is re-fetched for new problem
                say("Got it. Can you describe the issue in more detail so I can help you correctly?")
            return

        # ── Welcome on first message ──────────────────────────────────────────
        is_new_session = slack_user_id not in _slack_to_session
        if is_new_session:
            say(
                f"👋 Hi *{user_name}*! I'm the *Network Support Bot*.\n\n"
                "Type `help` anytime to see available commands."
            )
            _get_or_create_session(slack_user_id)
            session = chat_service._get_session(_slack_to_session[slack_user_id])
            session["user_name"]     = user_name
            session["user_email"]    = user_email
            session["source"]        = "slack"
            session["slack_user_id"] = slack_user_id
            return

        # ── Image / screenshot ────────────────────────────────────────────────
        if file_url and file_mimetype and file_mimetype.startswith("image/"):
            session = chat_service._get_session(session_id)
            session["user_name"]     = user_name
            session["user_email"]    = user_email
            session["source"]        = "slack"
            session["slack_user_id"] = slack_user_id

            display_text = analyze_slack_image(
                file_url      = file_url,
                slack_client  = slack_client,
                session_id    = session_id,
                slack_user_id = slack_user_id,
                file_mimetype = file_mimetype,
            )

            import re as _re
            display_text = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', display_text)

            analysis = session.get("screenshot_analysis", "")
            flow_step = session.get("flow_step", "")

            # Already waiting for confirmation — don't re-fire
            if flow_step == "waiting_screenshot_confirm":
                return

            if flow_step == "waiting_problem" and analysis:
                # ── First screenshot — describe + ask confirmation ─────────────
                # Store analysis and pre-fetch RAG so it's ready when user confirms
                session["problem"] = analysis[:400]
                try:
                    q_resp = _get_cl().messages.create(
                        model      = "claude-sonnet-4-5",
                        max_tokens = 30,
                        messages   = [{"role": "user", "content": (
                            "Extract the core IT issue from this screenshot analysis as a 3-6 word "
                            "search query. Include error code and technology if visible. Plain text only.\n\n"
                            f"{analysis[:300]}"
                        )}],
                    )
                    rag_query = q_resp.content[0].text.strip()
                except Exception:
                    rag_query = analysis[:200]

                rag_context = chat_service._get_rag(rag_query)
                session["rag_context"]          = rag_context
                session["flow_step"]            = "waiting_screenshot_confirm"
                session["flow_origin"]          = session.get("flow_origin") or "broken"
                session["is_screenshot_turn"]   = True   # never counts as attempt

                # Say the analysis then ask confirmation
                say(display_text)
                _say_blocks(say, blocks.screenshot_confirm)

            elif flow_step == "ai_analysis":
                # ── Mid-conversation screenshot — inject context, continue, 0 attempts ──
                session["is_screenshot_turn"] = True   # blocks attempt counter
                say(display_text)
                # Continue analysis — do NOT manually append message, process_message does it
                from app.schemas.chat import ChatMessageRequest
                data = ChatMessageRequest(
                    session_id = session_id,
                    message    = f"[Screenshot attached] {analysis[:200]}",
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

                response  = chat_service.process_message(db, SlackUser(), data)
                next_step = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1',
                            response.reply if hasattr(response, "reply") else str(response))
                if next_step:
                    say(next_step)
                if hasattr(response, "can_escalate") and response.can_escalate:
                    _ss_session   = chat_service._get_session(session_id)
                    _ss_origin    = _ss_session.get("flow_origin", "broken")
                    _ss_confirmed = _ss_session.get("user_confirmed_ticket", False)
                    _ss_auto_res  = _ss_session.get("auto_resolved", False)
                    if _ss_auto_res:
                        _auto_escalate_resolved(
                            session_id=session_id, slack_user_id=slack_user_id,
                            user_name=user_name, user_email=user_email,
                            db=db, session=_ss_session,
                        )
                    elif _ss_confirmed or _ss_origin == "major_incident":
                        _auto_escalate(
                            session_id=session_id, slack_user_id=slack_user_id,
                            user_name=user_name, user_email=user_email,
                            channel=channel, slack_client=slack_client,
                            say=say, db=db, session=_ss_session,
                        )
                    else:
                        _pending_ticket_confirm[slack_user_id] = True
                        _say_blocks(say, blocks.ticket_confirm)
            else:
                # Any other step — just show the analysis, store context
                session["is_screenshot_turn"] = True
                say(display_text)
            return

        # ── Normal text message through chat engine ───────────────────────────
        # If waiting for screenshot confirmation, drop spurious Slack re-fires
        session = chat_service._get_session(session_id)
        if session.get("flow_step") == "waiting_screenshot_confirm" and not file_url:
            return

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
            _say_reply(say, reply, blocks)

        if hasattr(response, "can_escalate") and response.can_escalate:
            flow_origin   = session.get("flow_origin", "broken")
            auto_resolved = session.get("auto_resolved", False)
            user_confirmed = session.get("user_confirmed_ticket", False)

            if auto_resolved:
                # Issue resolved by AI — silently raise ticket and mark resolved
                _auto_escalate_resolved(
                    session_id    = session_id,
                    slack_user_id = slack_user_id,
                    user_name     = user_name,
                    user_email    = user_email,
                    db            = db,
                    session       = session,
                )
            elif flow_origin in ("consult", "planning"):
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
            elif user_confirmed or flow_origin == "major_incident":
                # User already confirmed (clicked "Raise Ticket" at mid-check) or
                # major incident — raise immediately, no second confirmation
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
            else:
                # Steps exhausted — ask user to confirm before raising
                _pending_ticket_confirm[slack_user_id] = True
                _say_blocks(say, blocks.ticket_confirm)

    except Exception as e:
        logger.error(f"Slack bridge error: {e}", exc_info=True)
        say("I ran into an issue processing your request. Please try again.")
    finally:
        db.close()


def _auto_escalate_resolved(session_id, slack_user_id, user_name, user_email, db, session):
    """
    Silently raise a ticket and immediately mark it resolved.
    Called when AI resolves the issue without escalation.
    User sees nothing — ticket exists only for analytics.
    """
    try:
        from app.services import chat_service
        from datetime import datetime

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
        severity  = session.get("severity", "medium") or "medium"

        _flow_triggers = {"broken", "consult", "planning", "yes", "no", "y", "n",
                          "not working", "outage", "help", "urgent", "major incident"}
        _problem = session.get("problem", "").strip()
        if not _problem:
            _problem = next(
                (m for m in user_msgs if m.strip().lower() not in _flow_triggers and len(m.strip()) > 10),
                user_msgs[0] if user_msgs else ""
            )
        title = _problem[:80] if _problem else "IT Support Issue"

        req = EscalateReq(
            session_id  = session_id,
            title       = title,
            description = f"[Resolved by AI] {title}",
            domain      = "networking",
            priority    = "low",   # resolved issues are low priority
        )

        # Ensure DB user exists
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

        ticket_result = chat_service.escalate_to_ticket(db, slack_db_user, req)

        if ticket_result and hasattr(ticket_result, "ticket_number"):
            # Immediately mark resolved
            from app.models.ticket import Ticket, TicketStatus
            ticket = db.query(Ticket).filter(
                Ticket.ticket_number == ticket_result.ticket_number
            ).first()
            if ticket:
                ticket.status      = TicketStatus.RESOLVED
                ticket.resolved_at = datetime.utcnow()
                db.commit()
                logger.info("[AutoResolve] Ticket %s raised and marked resolved (AI resolved)", ticket_result.ticket_number)

        _reset_session(slack_user_id)

    except Exception as e:
        logger.error(f"Auto-resolve ticket error: {e}", exc_info=True)


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
        severity  = session.get("severity", "medium") or "medium"
        diagnosis = session.get("asset_context", {}).get("diagnosis", "")

        # Use session problem description; fall back to first substantive user message
        _flow_triggers = {"broken", "consult", "planning", "yes", "no", "y", "n",
                          "not working", "outage", "help", "urgent", "major incident"}
        _problem = session.get("problem", "").strip()
        if not _problem:
            _problem = next(
                (m for m in user_msgs if m.strip().lower() not in _flow_triggers and len(m.strip()) > 10),
                user_msgs[0] if user_msgs else ""
            )
        title = _problem[:80] if _problem else "IT Support Issue"

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

        # Fetch real timezone/location from Slack profile
        user_tz = "UTC"
        user_city = "Remote"
        try:
            slack_info = slack_client.users_info(user=slack_user_id)
            if slack_info and slack_info.get("user"):
                slack_profile = slack_info["user"]
                user_tz = slack_profile.get("tz") or "UTC"
                tz_label = slack_profile.get("tz_label", "")
                user_city = tz_label if tz_label else user_tz
        except Exception as e:
            logger.warning(f"Could not fetch Slack timezone for {slack_user_id}: {e}")

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
                city            = user_city,
                country         = "Remote",
                timezone        = user_tz,
            )
            db.add(slack_db_user)
            db.flush()
        else:
            slack_db_user.timezone = user_tz
            slack_db_user.city = user_city

        is_consult  = session.get("flow_origin") == "consult"
        is_planning = session.get("flow_origin") == "planning"
        is_major    = session.get("flow_origin") == "major_incident"

        if is_major:
            req.priority = "critical"

        if is_consult or is_planning:
            _handle_consult_escalation(
                slack_client  = slack_client,
                session       = session,
                user_name     = user_name,
                say           = say,
                slack_user_id = slack_user_id,
                is_planning   = is_planning,
            )
            _reset_session(slack_user_id)
            return

        ticket_result = chat_service.escalate_to_ticket(db, slack_db_user, req)

        if not ticket_result or not hasattr(ticket_result, "ticket_number"):
            return

        # Generate AI incident report — include screenshot analysis if available
        _acl  = _get_cl()
        msgs  = session.get("messages", [])
        convo = "\n".join(
            ("User: " if m["role"] == "user" else "Bot: ") + m["content"]
            for m in msgs
        )
        # Append screenshot analysis to the convo so it appears in the incident report
        if session.get("screenshot_analysis"):
            convo += f"\n\nScreenshot Analysis:\n{session['screenshot_analysis']}"

        try:
            resp = _acl.messages.create(
                model      = "claude-sonnet-4-5",
                max_tokens = 1000,
                messages   = [{"role": "user", "content": (
                    "Write a detailed professional IT incident report for a network engineer. "
                    "Plain text only, no markdown symbols, no asterisks, no bullet points.\n\n"
                    "Support conversation:\n" + convo + "\n\n"
                    "Format exactly as follows:\n\n"
                    "Issue Summary: (2-3 sentences describing the full problem)\n\n"
                    "Steps Already Tried:\n"
                    "1. (each troubleshooting step that was attempted, be specific)\n"
                    "2. ...\n"
                    "(include ALL steps from the conversation, numbered)\n\n"
                    "Current Status: (detailed description of what was found, what worked, what didn't)\n\n"
                    "Recommended Next Action: (specific actionable steps the engineer should take first, "
                    "include commands if relevant)\n\n"
                    "Be thorough — include all technical details, IP addresses, AS numbers, "
                    "error codes, and configuration details mentioned in the conversation."
                )}],
            )
            incident_report = resp.content[0].text.strip()
        except Exception:
            incident_report = diagnosis or title

        # Persist incident report as ai_diagnosis on the ticket
        try:
            from app.core.database import SessionLocal as _SL
            _db2 = _SL()
            from app.models.ticket import Ticket as _T
            _t = _db2.query(_T).filter(_T.ticket_number == ticket_result.ticket_number).first()
            if _t:
                _t.ai_diagnosis = incident_report
                _db2.commit()
            _db2.close()
        except Exception as _e:
            logger.warning(f"Could not persist ai_diagnosis: {_e}")

        # Routing — asset owner first, then fallback
        slack_eng     = None
        asset_match   = session.get("asset_match")
        contact_email = (asset_match or {}).get("contact_email", "")

        if contact_email:
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
            except Exception as e:
                logger.error(f"Asset owner Slack lookup failed for {contact_email}: {e}")

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

        _post_ticket_to_channel(
            slack_client      = slack_client,
            ticket_number     = ticket_result.ticket_number,
            user_name         = user_name,
            priority          = req.priority,
            incident_report   = incident_report,
            user_slack_id     = slack_user_id,
            engineer_slack_id = slack_eng["slack_id"] if slack_eng else None,
            engineer_name     = slack_eng["name"] if slack_eng else None,
            screenshot_path   = session.get("screenshot_path"),
            user_email        = user_email,
            user_timezone     = user_tz,
        )
        logger.debug("[Screenshot] path at escalation present=%s", bool(session.get("screenshot_path")))

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

        import pytz
        from datetime import datetime
        now = datetime.utcnow()

        try:
            user_tz     = pytz.timezone("Asia/Kolkata")
            user_offset = user_tz.utcoffset(now).total_seconds() / 3600
        except Exception:
            user_offset = 5.5

        def score_engineer(eng):
            score = 10 if eng["active"] else 0
            try:
                eng_tz     = pytz.timezone(eng["tz"])
                eng_offset = eng_tz.utcoffset(now).total_seconds() / 3600
                diff       = abs(user_offset - eng_offset)
                score     += max(0, 5 - diff)
            except Exception:
                pass
            return score

        candidates.sort(key=score_engineer, reverse=True)
        return candidates[0]

    except Exception as e:
        logger.error(f"Failed to find Slack engineer: {e}")
        return None
    
    
