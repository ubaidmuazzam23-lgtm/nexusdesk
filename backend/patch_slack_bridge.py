#!/usr/bin/env python3
# Run from: /Users/ubaidkundlik/Downloads/ai-it-support/backend
# ONLY adds image_bytes params to process_slack_message — nothing else changes

path = "app/services/slack_chat_bridge.py"
with open(path) as f:
    src = f.read()

patches_applied = 0

# ── PATCH 1: Add image params to process_slack_message signature ──────────────
old1 = '''def process_slack_message(
    slack_user_id: str,
    user_name: str,
    user_email: str,
    message: str,
    channel: str,
    slack_client,
    say,
):'''

new1 = '''def process_slack_message(
    slack_user_id: str,
    user_name: str,
    user_email: str,
    message: str,
    channel: str,
    slack_client,
    say,
    image_bytes=None,
    image_media_type: str = "image/png",
    screenshot_url: str = "",
):'''

if old1 in src:
    src = src.replace(old1, new1, 1)
    patches_applied += 1
    print("✓ Patch 1: image params added to process_slack_message signature")
else:
    print("✗ Patch 1 NOT found")

# ── PATCH 2: Pass image to chat_service.process_message ──────────────────────
old2 = '''        fake_user = SlackUser()
        response  = chat_service.process_message(db, fake_user, data)'''

new2 = '''        fake_user = SlackUser()
        response  = chat_service.process_message(
            db, fake_user, data,
            image_bytes      = image_bytes,
            image_media_type = image_media_type,
            screenshot_url   = screenshot_url,
        )'''

if old2 in src:
    src = src.replace(old2, new2, 1)
    patches_applied += 1
    print("✓ Patch 2: image passed to chat_service.process_message")
else:
    print("✗ Patch 2 NOT found")

with open(path, "w") as f:
    f.write(src)

print(f"\n{'='*50}")
print(f"Done. {patches_applied}/2 patches applied.")
print(f"{'='*50}")