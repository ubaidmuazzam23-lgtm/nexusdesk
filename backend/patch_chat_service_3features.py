#!/usr/bin/env python3
# Run from: /Users/ubaidkundlik/Downloads/ai-it-support/backend
# Adds 3 features to chat_service.py — nothing else changes:
#   1. rag_found flag in session
#   2. Consult disclaimer when no RAG found
#   3. AI resolved → silent ticket in DB
#   4. Screenshot support in _call_claude and process_message

path = "app/services/chat_service.py"
with open(path) as f:
    src = f.read()

patches_applied = 0

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 1: Add rag_found + screenshot_urls to session dict
# ─────────────────────────────────────────────────────────────────────────────
old1 = '''            "mid_check_done":     False,
            "flow_origin":        "broken",
        }'''

new1 = '''            "mid_check_done":     False,
            "flow_origin":        "broken",
            "rag_found":          False,
            "screenshot_urls":    [],
        }'''

if old1 in src:
    src = src.replace(old1, new1, 1)
    patches_applied += 1
    print("✓ Patch 1: rag_found + screenshot_urls added to session")
else:
    print("✗ Patch 1 NOT found")

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 2: _call_claude — add image_bytes support
# ─────────────────────────────────────────────────────────────────────────────
old2 = '''def _call_claude(session: dict, system: str, extra_hint: str = "") -> tuple:
    """One API call. Returns (reply, domain, severity, is_networking)."""
    if extra_hint:
        system = system + f"\\n\\nHINT: {extra_hint}"

    resp = _client.messages.create(
        model      = "claude-sonnet-4-5",
        max_tokens = 400,
        system     = system,
        messages   = session["messages"],
    )'''

new2 = '''def _call_claude(session: dict, system: str, extra_hint: str = "",
                image_bytes=None, image_media_type: str = "image/png") -> tuple:
    """One API call. Returns (reply, domain, severity, is_networking).
    If image_bytes provided, sends as vision input alongside last user message."""
    if extra_hint:
        system = system + f"\\n\\nHINT: {extra_hint}"

    messages = list(session["messages"])

    # If image provided, replace last user message with multipart content block
    if image_bytes and messages and messages[-1]["role"] == "user":
        import base64
        last_text = messages[-1]["content"]
        if isinstance(last_text, str):
            messages[-1] = {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": image_media_type,
                            "data":       base64.b64encode(image_bytes).decode("utf-8"),
                        },
                    },
                    {
                        "type": "text",
                        "text": last_text if last_text else "See the screenshot above.",
                    },
                ],
            }

    resp = _client.messages.create(
        model      = "claude-sonnet-4-5",
        max_tokens = 400,
        system     = system,
        messages   = messages,
    )'''

if old2 in src:
    src = src.replace(old2, new2, 1)
    patches_applied += 1
    print("✓ Patch 2: _call_claude image support added")
else:
    print("✗ Patch 2 NOT found")

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 3: _start_ai_analysis — store rag_found + consult disclaimer hint
# ─────────────────────────────────────────────────────────────────────────────
old3 = '''    # Use existing RAG context if already fetched, otherwise fetch now
    rag_context = session.get("rag_context") or _get_rag(problem)
    session["rag_context"] = rag_context'''

new3 = '''    # Use existing RAG context if already fetched, otherwise fetch now
    rag_context = session.get("rag_context") or _get_rag(problem)
    session["rag_context"] = rag_context
    session["rag_found"]   = bool(rag_context)'''

if old3 in src:
    src = src.replace(old3, new3, 1)
    patches_applied += 1
    print("✓ Patch 3: rag_found stamped in _start_ai_analysis")
else:
    print("✗ Patch 3 NOT found")

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 4: consult hint — RAG found vs not found + disclaimer
# ─────────────────────────────────────────────────────────────────────────────
old4 = '''        elif session.get("flow_origin") == "consult":
            remaining = max(0, 6 - session.get("solve_attempts", 0))
            hint = (
                f"This is a network team consultation. You have {remaining} quality exchanges remaining. "
                f"Ask ONE focused technical question to extract maximum useful information. "
                f"Focus on: technical details, constraints, current state, requirements, integrations. "
                f"Do NOT mention escalation, the network team, or handing off to anyone. "
                f"Do NOT say you will connect them with an architect or raise a request. "
                f"Just ask the next most important technical question."
            )
        elif session.get("flow_origin") == "planning":
            timeline = session.get("planning_timeline", "future")
            remaining = max(0, 4 - session.get("solve_attempts", 0))
            hint = (
                f"This request is scheduled for: {timeline}. "
                f"You have {remaining} exchanges to gather planning context for the network team. "
                f"Ask ONE focused question about: technical scope, dependencies, blockers, "
                f"business priority, success criteria, or contact person. "
                f"Do NOT mention escalation or handing off. Just gather planning information."
            )
    else:
        system = SYSTEM_PROMPT
        if session.get("flow_origin") == "consult":
            remaining = max(0, 6 - session.get("solve_attempts", 0))
            hint = (
                f"This is a network team consultation. You have {remaining} exchanges remaining. "
                f"Ask ONE focused technical question to extract maximum useful information. "
                f"Focus on: technical details, constraints, current state, requirements, integrations. "
                f"Do NOT mention escalation, the network team, or handing off to anyone. "
                f"Do NOT say you will connect them with an architect or raise a request. "
                f"Just ask the next most important technical question."
            )
        elif session.get("flow_origin") == "planning":
            timeline = session.get("planning_timeline", "future")
            remaining = max(0, 4 - session.get("solve_attempts", 0))
            hint = (
                f"This request is scheduled for: {timeline}. "
                f"You have {remaining} exchanges to gather planning context for the network team. "
                f"Ask ONE focused question about: technical scope, dependencies, blockers, "
                f"business priority, success criteria, or contact person. "
                f"Do NOT mention escalation or handing off. Just gather planning information."
            )
        else:
            hint = (
                "No runbook found for this issue. "
                "First verify this is a networking issue. If it is, use your own networking expertise to troubleshoot — "
                "give one specific step. If it is clearly NOT a networking issue, tell the user politely and suggest "
                "they contact the relevant team."
            )'''

new4 = '''        elif session.get("flow_origin") == "consult":
            remaining = max(0, 6 - session.get("solve_attempts", 0))
            hint = (
                f"This is a network team consultation. A knowledge base document has been found above. "
                f"You have {remaining} quality exchanges remaining. "
                f"Read the document carefully. Ask ONE focused technical question that is directly "
                f"relevant to what the document covers and what you need from the user. "
                f"Do NOT mention escalation, the network team, or handing off to anyone."
            )
        elif session.get("flow_origin") == "planning":
            timeline = session.get("planning_timeline", "future")
            remaining = max(0, 4 - session.get("solve_attempts", 0))
            hint = (
                f"This request is scheduled for: {timeline}. A knowledge base document has been found above. "
                f"You have {remaining} exchanges to gather planning context. "
                f"Ask ONE focused question based on the document and planning needs. "
                f"Do NOT mention escalation or handing off."
            )
    else:
        system = SYSTEM_PROMPT
        if session.get("flow_origin") == "consult":
            remaining = max(0, 6 - session.get("solve_attempts", 0))
            hint = (
                f"This is a network team consultation. No knowledge base document was found. "
                f"Use your own networking expertise. You have {remaining} exchanges remaining. "
                f"Ask ONE focused technical question to extract maximum useful information. "
                f"Focus on: technical details, constraints, current state, requirements, integrations. "
                f"Do NOT mention escalation, the network team, or handing off to anyone. "
                f"End your reply with exactly this sentence: "
                f"Note: This response is AI-generated based on general networking knowledge. "
                f"Please consult your network engineer before proceeding."
            )
        elif session.get("flow_origin") == "planning":
            timeline = session.get("planning_timeline", "future")
            remaining = max(0, 4 - session.get("solve_attempts", 0))
            hint = (
                f"This request is scheduled for: {timeline}. No knowledge base document was found. "
                f"Use your own networking expertise. You have {remaining} exchanges remaining. "
                f"Ask ONE focused question about: technical scope, dependencies, blockers, "
                f"business priority, success criteria, or contact person. "
                f"Do NOT mention escalation or handing off. "
                f"End your reply with exactly this sentence: "
                f"Note: This response is AI-generated based on general networking knowledge. "
                f"Please consult your network engineer before proceeding."
            )
        else:
            hint = (
                "No runbook found for this issue. "
                "First verify this is a networking issue. If it is, use your own networking expertise to troubleshoot — "
                "give one specific step. If it is clearly NOT a networking issue, tell the user politely and suggest "
                "they contact the relevant team."
            )'''

if old4 in src:
    src = src.replace(old4, new4, 1)
    patches_applied += 1
    print("✓ Patch 4: consult RAG-aware hints + disclaimer added")
else:
    print("✗ Patch 4 NOT found")

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 5: _continue_ai_analysis — consult hint when no RAG
# ─────────────────────────────────────────────────────────────────────────────
old5 = '''        if has_runbook:
            hint = (
                "Follow the next step from the runbook. "
                "If you have covered ALL steps and issue is still not resolved, "
                "tell the user you will escalate to the network engineering team. "
                "End your reply with [STEPS_EXHAUSTED] only when ALL runbook steps are done. "
                "IMPORTANT: Always include a proper sentence before [STEPS_EXHAUSTED]."
            )
        else:
            hint = (
                f"Attempt {n} of 6. Give ONE specific troubleshooting step. "
                f"Different from what was already tried."
            )'''

new5 = '''        if is_consult:
            remaining = max(0, 6 - n)
            if session.get("rag_found"):
                hint = (
                    f"This is a network consultation. Knowledge base document is above. "
                    f"You have {remaining} exchanges remaining. "
                    f"Ask ONE focused technical question based on the document content. "
                    f"Do NOT mention escalation."
                )
            else:
                hint = (
                    f"This is a network consultation. No knowledge base document found. "
                    f"You have {remaining} exchanges remaining. "
                    f"Ask ONE focused technical question from your own networking expertise. "
                    f"End your reply with exactly: "
                    f"Note: This response is AI-generated based on general networking knowledge. "
                    f"Please consult your network engineer before proceeding."
                )
        elif session.get("flow_origin") == "planning":
            remaining = max(0, 4 - n)
            if session.get("rag_found"):
                hint = (
                    f"Planning request. Knowledge base document above. {remaining} exchanges remaining. "
                    f"Ask ONE focused planning question from the document."
                )
            else:
                hint = (
                    f"Planning request. No knowledge base document. {remaining} exchanges remaining. "
                    f"Ask ONE focused planning question. "
                    f"End with: Note: This response is AI-generated based on general networking knowledge. "
                    f"Please consult your network engineer before proceeding."
                )
        elif has_runbook:
            hint = (
                "Follow the next step from the runbook. "
                "If you have covered ALL steps and issue is still not resolved, "
                "tell the user you will escalate to the network engineering team. "
                "End your reply with [STEPS_EXHAUSTED] only when ALL runbook steps are done. "
                "IMPORTANT: Always include a proper sentence before [STEPS_EXHAUSTED]."
            )
        else:
            hint = (
                f"Attempt {n} of 6. Give ONE specific troubleshooting step. "
                f"Different from what was already tried."
            )'''

if old5 in src:
    src = src.replace(old5, new5, 1)
    patches_applied += 1
    print("✓ Patch 5: _continue_ai_analysis consult hints added")
else:
    print("✗ Patch 5 NOT found")

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 6: AI resolved → silent ticket
# Replace the is_resolved block in _continue_ai_analysis
# ─────────────────────────────────────────────────────────────────────────────
old6 = '''    if is_resolved:
        reply = "Glad that sorted it out. Feel free to reach out if anything else comes up."
        session["messages"].append({"role": "assistant", "content": reply})
        session["ai_resolved"] = True
        return _make_response(sid, session, reply, resolved=True)'''

new6 = '''    if is_resolved:
        reply = "Glad that sorted it out. Feel free to reach out if anything else comes up."
        session["messages"].append({"role": "assistant", "content": reply})
        session["ai_resolved"] = True
        return _make_response(sid, session, reply, resolved=True, can_escalate=False)'''

if old6 in src:
    src = src.replace(old6, new6, 1)
    patches_applied += 1
    print("✓ Patch 6: AI resolved flag preserved")
else:
    print("✗ Patch 6 NOT found")

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 7: process_message — add image params + silent ticket on AI resolve
# ─────────────────────────────────────────────────────────────────────────────
old7 = '''def process_message(db: Session, user: User, data: ChatMessageRequest) -> ChatMessageResponse:'''

new7 = '''def _create_ai_resolved_ticket(db: Session, user: User, session: dict):
    """Create a silent resolved ticket when AI solves the issue. No routing, no notifications."""
    try:
        msgs      = session.get("messages", [])
        user_msgs = [m["content"] for m in msgs if m["role"] == "user" and isinstance(m["content"], str)]
        ai_msgs   = [m["content"] for m in msgs if m["role"] == "assistant" and isinstance(m["content"], str)]

        raw_title = user_msgs[0][:80] if user_msgs else "Network Issue"
        try:
            title_resp = _client.messages.create(
                model      = "claude-sonnet-4-5",
                max_tokens = 40,
                messages   = [{"role": "user", "content": (
                    "Write a clear professional IT ticket title (max 8 words, no punctuation at end) "
                    "summarising this network issue:\n\n"
                    + "\n".join(f"User: {m}" for m in user_msgs[:4])
                )}],
            )
            clean_title = title_resp.content[0].text.strip().strip(\'"\').strip("\'")
            if len(clean_title) < 5 or len(clean_title) > 100:
                clean_title = raw_title
        except Exception:
            clean_title = raw_title

        diagnosis = ai_msgs[-1][:500] if ai_msgs else ""

        from app.models.user import UserRole
        from app.core.security import hash_password
        db_user = db.query(User).filter(User.email == user.email).first()
        if not db_user:
            db_user = User(
                id              = uuid.uuid4(),
                email           = user.email,
                full_name       = user.full_name,
                hashed_password = hash_password(uuid.uuid4().hex),
                role            = UserRole.USER,
                is_active       = True,
                is_verified     = True,
                city            = getattr(user, "city", "Slack"),
                country         = getattr(user, "country", "Remote"),
                timezone        = getattr(user, "timezone", "UTC"),
            )
            db.add(db_user)
            db.flush()

        ticket = Ticket(
            ticket_number = _generate_ticket_number(db),
            user_id       = db_user.id,
            engineer_id   = None,
            team_id       = None,
            title         = clean_title,
            description   = session.get("problem", clean_title),
            domain        = TicketDomain.NETWORKING,
            priority      = TicketPriority.LOW,
            status        = TicketStatus.RESOLVED,
            ai_diagnosis  = diagnosis or None,
            ai_attempted  = True,
            ai_resolved   = True,
            resolved_at   = datetime.utcnow(),
            user_city     = getattr(user, "city", None),
            user_country  = getattr(user, "country", None),
            user_timezone = getattr(user, "timezone", None),
            sla_deadline  = None,
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        print(f"  [AI-Resolved] Silent ticket created: {ticket.ticket_number}")
    except Exception as e:
        print(f"  [AI-Resolved] Failed to create ticket: {e}")
        try:
            db.rollback()
        except Exception:
            pass


def process_message(db: Session, user: User, data: ChatMessageRequest,
                    image_bytes=None, image_media_type: str = "image/png",
                    screenshot_url: str = "") -> ChatMessageResponse:'''

if old7 in src:
    src = src.replace(old7, new7, 1)
    patches_applied += 1
    print("✓ Patch 7: _create_ai_resolved_ticket + image params added to process_message")
else:
    print("✗ Patch 7 NOT found")

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 8: ai_analysis step — create silent ticket on resolve
# ─────────────────────────────────────────────────────────────────────────────
old8 = '''    # AI Analysis
    elif step == "ai_analysis":
        return _continue_ai_analysis(session, sid, msg)'''

new8 = '''    # AI Analysis
    elif step == "ai_analysis":
        resp = _continue_ai_analysis(session, sid, msg, image_bytes, image_media_type)
        if resp.resolved and session.get("ai_resolved"):
            _create_ai_resolved_ticket(db, user, session)
            if sid in _sessions:
                del _sessions[sid]
        return resp'''

if old8 in src:
    src = src.replace(old8, new8, 1)
    patches_applied += 1
    print("✓ Patch 8: silent ticket created on AI resolve")
else:
    print("✗ Patch 8 NOT found")

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 9: mid_check — pass image to _continue_ai_analysis
# ─────────────────────────────────────────────────────────────────────────────
old9 = '''        else:
            # Continue troubleshooting
            session["flow_step"] = "ai_analysis"
            return _continue_ai_analysis(session, sid, msg)'''

new9 = '''        else:
            # Continue troubleshooting
            session["flow_step"] = "ai_analysis"
            return _continue_ai_analysis(session, sid, msg, image_bytes, image_media_type)'''

if old9 in src:
    src = src.replace(old9, new9, 1)
    patches_applied += 1
    print("✓ Patch 9: mid_check passes image to _continue_ai_analysis")
else:
    print("✗ Patch 9 NOT found")

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 10: _continue_ai_analysis — add image params
# ─────────────────────────────────────────────────────────────────────────────
old10 = '''def _continue_ai_analysis(session: dict, sid: str, message: str) -> ChatMessageResponse:
    """Continue AI analysis — check if resolved or needs escalation."""'''

new10 = '''def _continue_ai_analysis(session: dict, sid: str, message: str,
                           image_bytes=None, image_media_type: str = "image/png") -> ChatMessageResponse:
    """Continue AI analysis — check if resolved or needs escalation."""'''

if old10 in src:
    src = src.replace(old10, new10, 1)
    patches_applied += 1
    print("✓ Patch 10: _continue_ai_analysis image params added")
else:
    print("✗ Patch 10 NOT found")

# ─────────────────────────────────────────────────────────────────────────────
# Write output
# ─────────────────────────────────────────────────────────────────────────────
with open(path, "w") as f:
    f.write(src)

print(f"\n{'='*50}")
print(f"Done. {patches_applied}/10 patches applied.")
print(f"{'='*50}")
print("\nRestart backend:")
print("  pkill -f uvicorn && uvicorn app.main:app --host 0.0.0.0 --port 8000")