#!/usr/bin/env python3
# Run from: /Users/ubaidkundlik/Downloads/ai-it-support/backend
# ONLY adds image detection to handle_message — nothing else changes

path = "app/services/slack_service.py"
with open(path) as f:
    src = f.read()

patches_applied = 0

# ── PATCH 1: Add image download helper before start_slack_bot ────────────────
old1 = '''def start_slack_bot():'''

new1 = '''def _download_slack_image(client, file_info: dict) -> tuple:
    """Download image from Slack. Returns (bytes, media_type, permalink) or (None, None, '')."""
    try:
        import urllib.request
        url       = file_info.get("url_private_download") or file_info.get("url_private", "")
        mimetype  = file_info.get("mimetype", "image/png")
        permalink = file_info.get("permalink", "")
        if not url:
            return None, None, ""
        token = client.token
        req   = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            image_bytes = resp.read()
        logger.info(f"Downloaded Slack image: {len(image_bytes)} bytes type={mimetype}")
        return image_bytes, mimetype, permalink
    except Exception as e:
        logger.error(f"Failed to download Slack image: {e}")
        return None, None, ""


def start_slack_bot():'''

if old1 in src:
    src = src.replace(old1, new1, 1)
    patches_applied += 1
    print("✓ Patch 1: _download_slack_image helper added")
else:
    print("✗ Patch 1 NOT found")

# ── PATCH 2: Replace handle_message to support file_share + image detection ──
old2 = '''        # ── Handle DMs and messages ───────────────────────────────────────────
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
                say("Sorry, I ran into an issue. Please try again.")'''

new2 = '''        # ── Handle DMs and messages ───────────────────────────────────────────
        @app.event("message")
        def handle_message(event, say, client):
            # Ignore bot messages
            if event.get("bot_id"):
                return
            # Allow file_share subtype, ignore all others
            subtype = event.get("subtype", "")
            if subtype and subtype not in ("file_share",):
                return

            slack_user_id = event.get("user")
            text          = (event.get("text") or "").strip()
            channel       = event.get("channel")
            files         = event.get("files", [])

            if not slack_user_id:
                return

            # Ignore if no text and no files
            if not text and not files:
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

            # Check for image attachment
            image_bytes      = None
            image_media_type = "image/png"
            screenshot_url   = ""
            for f in files:
                mime = f.get("mimetype", "")
                if mime.startswith("image/"):
                    img, mt, url = _download_slack_image(client, f)
                    if img:
                        image_bytes      = img
                        image_media_type = mt or "image/png"
                        screenshot_url   = url
                        break  # use first image only

            # Process message through NexusDesk chat engine
            try:
                from app.services.slack_chat_bridge import process_slack_message
                process_slack_message(
                    slack_user_id    = slack_user_id,
                    user_name        = user_name,
                    user_email       = user_email,
                    message          = text,
                    channel          = channel,
                    slack_client     = client,
                    say              = say,
                    image_bytes      = image_bytes,
                    image_media_type = image_media_type,
                    screenshot_url   = screenshot_url,
                )
            except Exception as e:
                logger.error(f"Slack message processing error: {e}", exc_info=True)
                say("Sorry, I ran into an issue. Please try again.")'''

if old2 in src:
    src = src.replace(old2, new2, 1)
    patches_applied += 1
    print("✓ Patch 2: handle_message updated with image detection")
else:
    print("✗ Patch 2 NOT found")

with open(path, "w") as f:
    f.write(src)

print(f"\n{'='*50}")
print(f"Done. {patches_applied}/2 patches applied.")
print(f"{'='*50}")