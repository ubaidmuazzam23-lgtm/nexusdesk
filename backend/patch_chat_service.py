#!/usr/bin/env python3
# Run from: /Users/ubaidkundlik/Downloads/ai-it-support/backend
# Usage: python patch_chat_service.py

import re

path = "app/services/chat_service.py"

with open(path, "r") as f:
    src = f.read()

# ── PATCH 1: stamp ai_resolved when bot resolves ──────────────────────────────
old1 = '''    if is_resolved:
        reply = "Glad that sorted it out. Feel free to reach out if anything else comes up."
        session["messages"].append({"role": "assistant", "content": reply})
        return _make_response(sid, session, reply, resolved=True)'''

new1 = '''    if is_resolved:
        reply = "Glad that sorted it out. Feel free to reach out if anything else comes up."
        session["messages"].append({"role": "assistant", "content": reply})
        session["ai_resolved"] = True
        return _make_response(sid, session, reply, resolved=True)'''

if old1 in src:
    src = src.replace(old1, new1, 1)
    print("✓ Patch 1 applied — ai_resolved stamp")
else:
    print("✗ Patch 1 NOT found — check manually")

# ── PATCH 2: AI-generated title + ai_resolved flag on ticket ─────────────────
old2 = '''    ticket = Ticket(
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
    )'''

new2 = '''    # Generate clean AI title from conversation
    msgs      = session.get("messages", [])
    user_msgs = [m["content"] for m in msgs if m["role"] == "user"]
    raw_title = data.title or (user_msgs[0] if user_msgs else "Network Issue")
    try:
        title_resp = _client.messages.create(
            model      = "claude-sonnet-4-5",
            max_tokens = 40,
            messages   = [{"role": "user", "content": (
                "Write a clear professional IT ticket title (max 8 words, no punctuation at end) "
                "summarising this network issue:\\n\\n"
                + "\\n".join(f"User: {m}" for m in user_msgs[:4])
            )}],
        )
        clean_title = title_resp.content[0].text.strip().strip(\'"\').strip("\'")
        if len(clean_title) < 5 or len(clean_title) > 100:
            clean_title = raw_title[:80]
    except Exception:
        clean_title = raw_title[:80]

    ai_resolved_flag = session.get("ai_resolved", False)

    ticket = Ticket(
        ticket_number = _generate_ticket_number(db),
        user_id       = user.id,
        engineer_id   = engineer_id,
        team_id       = team_id,
        title         = clean_title,
        description   = data.description,
        domain        = TicketDomain.NETWORKING,
        priority      = priority_map.get(severity, TicketPriority.MEDIUM),
        status        = TicketStatus.OPEN,
        steps_tried   = data.steps_tried,
        ai_diagnosis  = diagnosis.strip() or None,
        ai_attempted  = True,
        ai_resolved   = ai_resolved_flag,
        user_city     = user.city,
        user_country  = user.country,
        user_timezone = user.timezone,
        sla_deadline  = datetime.utcnow() + timedelta(minutes=sla_map.get(severity, 480)),
    )'''

if old2 in src:
    src = src.replace(old2, new2, 1)
    print("✓ Patch 2 applied — AI title + ai_resolved flag")
else:
    print("✗ Patch 2 NOT found — check manually")

with open(path, "w") as f:
    f.write(src)

print("\nDone. Restart backend:")
print("  pkill -f uvicorn && uvicorn app.main:app --host 0.0.0.0 --port 8000")