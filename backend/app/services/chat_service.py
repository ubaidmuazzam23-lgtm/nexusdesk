# # File: backend/app/services/chat_service.py

# from sqlalchemy.orm import Session
# from sqlalchemy import func
# from fastapi import HTTPException
# from datetime import datetime, timedelta
# from typing import Optional
# import uuid
# import json
# import pytz
# import os
# import anthropic

# from app.core.config import settings
# from app.models.user import User
# from app.models.ticket import Ticket, TicketStatus, TicketPriority, TicketComplexity, TicketDomain
# from app.models.engineer import Engineer, AvailabilityStatus
# from app.schemas.chat import (
#     ChatMessageRequest, ChatMessageResponse,
#     EscalateRequest, EscalateResponse, UserTicketResponse,
# )

# _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

# PRICE_INPUT_PER_MILLION  = 3.00
# PRICE_OUTPUT_PER_MILLION = 15.00

# SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "screenshots")
# os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# _sessions: dict = {}

# VALID_DOMAINS = [
#     "networking", "hardware", "software", "security",
#     "email_communication", "identity_access", "database",
#     "cloud", "infrastructure", "devops", "erp_business_apps",
#     "endpoint_management", "other",
# ]

# # ── CNN mappings ──────────────────────────────────────────────────────────────
# CNN_CLASS_TO_DOMAIN = {
#     "bsod":"hardware","memory_error":"hardware","cpu_high":"infrastructure",
#     "disk_full":"infrastructure","hardware_failure":"hardware",
#     "dns_error":"networking","network_unreachable":"networking","vpn_error":"networking",
#     "ssl_error":"security","timeout":"networking","permission_denied":"security",
#     "login_failed":"identity_access","mfa_error":"identity_access","session_expired":"identity_access",
#     "app_crash":"software","update_error":"software","install_error":"software",
#     "dependency_error":"devops","db_connection_error":"database",
#     "db_query_error":"database","db_timeout":"database",
#     "cloud_auth_error":"cloud","deployment_error":"devops",
#     "container_error":"devops","general_error":"other",
# }
# CNN_CLASS_TO_SEVERITY = {
#     "bsod":"critical","memory_error":"high","cpu_high":"high","disk_full":"high",
#     "hardware_failure":"critical","dns_error":"high","network_unreachable":"critical",
#     "vpn_error":"high","ssl_error":"high","timeout":"medium","permission_denied":"high",
#     "login_failed":"medium","mfa_error":"medium","session_expired":"low",
#     "app_crash":"high","update_error":"medium","install_error":"medium",
#     "dependency_error":"medium","db_connection_error":"critical","db_query_error":"high",
#     "db_timeout":"high","cloud_auth_error":"high","deployment_error":"critical",
#     "container_error":"critical","general_error":"medium",
# }
# CNN_CLASS_LABELS = {
#     "bsod":"Windows Blue Screen of Death","memory_error":"Memory / Out of Memory Error",
#     "cpu_high":"High CPU Usage","disk_full":"Disk Full / Low Storage",
#     "hardware_failure":"Hardware Failure / Driver Error","dns_error":"DNS Resolution Failure",
#     "network_unreachable":"Network Unreachable / No Internet","vpn_error":"VPN Connection Error",
#     "ssl_error":"SSL / Certificate Error","timeout":"Connection / Request Timeout",
#     "permission_denied":"Permission Denied / Access Error","login_failed":"Login / Authentication Failed",
#     "mfa_error":"MFA / Two-Factor Auth Error","session_expired":"Session Expired",
#     "app_crash":"Application Crash / Not Responding","update_error":"Software Update Error",
#     "install_error":"Installation Failed","dependency_error":"Missing Dependency / Module Error",
#     "db_connection_error":"Database Connection Error","db_query_error":"Database Query / SQL Error",
#     "db_timeout":"Database Timeout","cloud_auth_error":"Cloud Permission / Auth Error",
#     "deployment_error":"Deployment / CI-CD Pipeline Error",
#     "container_error":"Container / Docker / Kubernetes Error","general_error":"General Error",
# }

# # ── Prompts ───────────────────────────────────────────────────────────────────

# SYSTEM_PROMPT = """You are an IT support specialist at NexusDesk. Help users fix IT problems through friendly, clear conversation.

# STRICT FORMATTING RULES:
# - Never use asterisks, hashtags, dashes as bullets, or any markdown symbols
# - Write in plain natural sentences only
# - For steps write them as: First do this. Then do that. Finally do this.
# - Keep responses under 150 words
# - Sound like a helpful colleague, not a manual
# - Ask only one question at a time
# - Do not start with "Certainly!" or "Absolutely!"

# KNOWLEDGE BASE RULES:
# - If knowledge base articles are provided below, you MUST use them as your primary source of information.
# - Extract the specific steps, commands, and solutions from those articles and include them directly in your response.
# - Do not ignore the knowledge base content in favor of generic troubleshooting.
# - Do not say "according to the knowledge base" — just naturally give the specific advice.

# After 2 failed attempts, tell the user naturally that you recommend getting an engineer involved and they can raise a support ticket.

# If the user says it is fixed, say something brief and warm like "Glad that sorted it out."

# You cover: networking, hardware, software, security, email, identity and access, databases, cloud, infrastructure, devops, ERP and business apps, endpoint management."""

# CLASSIFY_PROMPT = """Classify this IT support conversation. Return only JSON.

# Pick domain from this exact list only:
# networking, hardware, software, security, email_communication, identity_access, database, cloud, infrastructure, devops, erp_business_apps, endpoint_management, other

# Pick severity:
# critical = production down or all users affected
# high = user completely blocked
# medium = degraded or intermittent
# low = question or minor issue

# Return only: {"domain": "...", "severity": "..."}"""


# # ── Cost tracking ─────────────────────────────────────────────────────────────

# def _calculate_cost(input_tokens: int, output_tokens: int) -> dict:
#     ic = (input_tokens  / 1_000_000) * PRICE_INPUT_PER_MILLION
#     oc = (output_tokens / 1_000_000) * PRICE_OUTPUT_PER_MILLION
#     return {"input_tokens":input_tokens,"output_tokens":output_tokens,
#             "input_cost":round(ic,6),"output_cost":round(oc,6),"total_cost":round(ic+oc,6)}


# def _log_cost(session_id: str, call_type: str, cost: dict, session_total: float, info: str = "") -> None:
#     print(f"\n{'─'*58}")
#     print(f"  NexusDesk — {call_type}")
#     print(f"{'─'*58}")
#     print(f"  Session : {session_id[:20]}...")
#     if info: print(f"  Info    : {info}")
#     print(f"  Input   : {cost['input_tokens']:,} tokens → ${cost['input_cost']:.6f}")
#     print(f"  Output  : {cost['output_tokens']:,} tokens → ${cost['output_cost']:.6f}")
#     print(f"  Call $  : ${cost['total_cost']:.6f}")
#     print(f"  Total $ : ${session_total:.6f}")
#     print(f"{'─'*58}\n")


# # ── Session management ────────────────────────────────────────────────────────

# def _get_session(session_id: str) -> dict:
#     if session_id not in _sessions:
#         _sessions[session_id] = {
#             "messages": [], "domain": None, "severity": None,
#             "attempt": 0, "total_cost": 0.0,
#             "screenshot_path": None, "cnn_result": None,
#         }
#     return _sessions[session_id]


# # ── Domain classifier ─────────────────────────────────────────────────────────

# def _classify_with_claude(text: str, session_id: str, session: dict) -> dict:
#     try:
#         response = _client.messages.create(
#             model="claude-sonnet-4-5", max_tokens=120,
#             system=CLASSIFY_PROMPT,
#             messages=[{"role":"user","content":text}],
#         )
#         raw = response.content[0].text.strip()

#         # Strip markdown code fences if Claude wraps it
#         if raw.startswith("```"):
#             raw = raw.split("```")[1]
#             if raw.startswith("json"):
#                 raw = raw[4:]
#             raw = raw.strip()

#         # Extract JSON object even if there's surrounding text
#         start = raw.find("{")
#         end   = raw.rfind("}") + 1
#         if start == -1 or end == 0:
#             raise ValueError(f"No JSON found in: {raw!r}")
#         raw = raw[start:end]

#         data     = json.loads(raw)
#         domain   = data.get("domain", "other")
#         severity = data.get("severity", "medium")
#         if domain not in VALID_DOMAINS:                        domain = "other"
#         if severity not in ["critical","high","medium","low"]: severity = "medium"

#         cost = _calculate_cost(response.usage.input_tokens, response.usage.output_tokens)
#         session["total_cost"] += cost["total_cost"]
#         _log_cost(session_id, "Domain Classification", cost, session["total_cost"],
#                   f"domain={domain} | severity={severity}")
#         return {"domain": domain, "severity": severity}

#     except Exception as e:
#         print(f"  ⚠ Classification error: {e}")
#         return {"domain": "other", "severity": "medium"}


# # ── CNN screenshot analysis ───────────────────────────────────────────────────

# def analyze_screenshot(image_bytes: bytes, session_id: str, user_id: str) -> dict:
#     session  = _get_session(session_id)
#     filename = f"{user_id}_{session_id[:8]}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
#     filepath = os.path.join(SCREENSHOT_DIR, filename)
#     with open(filepath, 'wb') as f:
#         f.write(image_bytes)
#     session["screenshot_path"] = filepath
#     print(f"\n  📸 Screenshot saved: {filename}")

#     cnn_label = "Screenshot uploaded"
#     cnn_domain = None
#     cnn_severity = None
#     cnn_confidence = 0.0
#     cnn_result = None

#     try:
#         from app.ml.cnn.predict import predict_screenshot
#         cnn_result     = predict_screenshot(image_bytes)
#         cnn_class      = cnn_result.get("error_class","general_error")
#         cnn_confidence = cnn_result.get("confidence",0.0)
#         cnn_domain     = CNN_CLASS_TO_DOMAIN.get(cnn_class,"other")
#         cnn_severity   = CNN_CLASS_TO_SEVERITY.get(cnn_class,"medium")
#         cnn_label      = CNN_CLASS_LABELS.get(cnn_class,cnn_class)
#         session["cnn_result"] = cnn_result
#         print(f"  🖼  CNN: {cnn_label} ({int(cnn_confidence*100)}%) → {cnn_domain}")
#         if cnn_confidence >= 0.85 and cnn_domain != "other":
#             session["domain"]   = cnn_domain
#             session["severity"] = cnn_severity
#     except Exception as e:
#         print(f"  ⚠ CNN error: {e}")

#     if cnn_result and cnn_confidence >= 0.85:
#         display_text = f"I can see this looks like a {cnn_label} ({int(cnn_confidence*100)}% confidence). Can you tell me more about what happened just before this appeared?"
#     elif cnn_result and cnn_confidence >= 0.60:
#         display_text = f"Your screenshot looks like it could be a {cnn_label}. Can you describe what happened?"
#     else:
#         display_text = "I have received your screenshot. Can you describe what is happening so I can help you better?"

#     return {
#         "success": True, "filename": filename, "display_text": display_text,
#         "cnn_label": cnn_label, "cnn_confidence": round(cnn_confidence,4),
#         "cnn_domain": cnn_domain, "cnn_severity": cnn_severity,
#     }


# # ── Main chat function ────────────────────────────────────────────────────────

# def process_message(db: Session, user: User, data: ChatMessageRequest) -> ChatMessageResponse:
#     session_id = data.session_id or str(uuid.uuid4())
#     session    = _get_session(session_id)

#     session["messages"].append({"role":"user","content":data.message})
#     session["attempt"] += 1
#     attempt = session["attempt"]

#     # Classify domain + severity
#     full_text  = " ".join(m["content"] for m in session["messages"] if m["role"]=="user")
#     classified = _classify_with_claude(full_text, session_id, session)
#     if classified["domain"] != "other" or not session["domain"]:
#         session["domain"] = classified["domain"]
#     session["severity"] = classified["severity"]

#     # Check if resolved
#     resolved_phrases = ["fixed","works now","that worked","sorted","solved","issue resolved","its working","all good now"]
#     if any(p in data.message.lower() for p in resolved_phrases):
#         return ChatMessageResponse(
#             session_id=session_id,
#             reply="Glad that sorted it out. Feel free to reach out if anything else comes up.",
#             intent=data.intent or "solve",
#             detected_domain=session["domain"] or "other",
#             detected_severity=session["severity"] or "medium",
#             resolved=True, can_escalate=False, attempt_number=attempt,
#         )

#     # ── RAG: Search knowledge base for relevant docs ──────────────────────────
#     rag_context = ""
#     rag_hits    = []
#     try:
#         from app.services.knowledge_service import get_rag_context, search_knowledge
#         rag_context = get_rag_context(
#             query=full_text,
#             domain=session["domain"] if session["domain"] != "other" else None,
#             n_results=3,
#         )
#         if rag_context:
#             # Also store top hit info for response
#             kb_result = search_knowledge(
#                 query=full_text,
#                 n_results=2,
#                 domain=session["domain"] if session["domain"] != "other" else None,
#             )
#             rag_hits = [r for r in kb_result.get("results",[]) if r["cosine_similarity"] >= 45]
#             print(f"  📖 RAG: found {len(rag_hits)} relevant KB articles (top: {rag_hits[0]['cosine_similarity']}% match)" if rag_hits else "  📖 RAG: no relevant KB articles found")
#     except Exception as e:
#         print(f"  ⚠ RAG error: {e}")

#     # CNN context
#     cnn_context = ""
#     if session.get("cnn_result"):
#         cr = session["cnn_result"]
#         cc = cr.get("confidence",0.0)
#         if cc >= 0.60:
#             cnn_context = f"\n\nNote: User uploaded a screenshot. CNN detected: {CNN_CLASS_LABELS.get(cr.get('error_class',''), cr.get('error_class',''))} ({int(cc*100)}% confidence)."

#     intent_note = (
#         "This is a service request."
#         if data.intent == "service_request"
#         else f"This is attempt {attempt}. {'Tell the user you recommend raising a support ticket.' if attempt >= 3 else ''}"
#     )

#     try:
#         response = _client.messages.create(
#             model="claude-sonnet-4-5",
#             max_tokens=512,
#             system=f"{SYSTEM_PROMPT}\n\n{intent_note}{cnn_context}{rag_context}",
#             messages=session["messages"],
#         )
#         reply_text = response.content[0].text.strip()
#         cost = _calculate_cost(response.usage.input_tokens, response.usage.output_tokens)
#         session["total_cost"] += cost["total_cost"]
#         _log_cost(session_id,"Main Response",cost,session["total_cost"],
#                   f"attempt={attempt} | domain={session['domain']} | RAG hits={len(rag_hits)}")

#         session["messages"].append({"role":"assistant","content":reply_text})

#         escalation_hints = ["raise a ticket","support ticket","human engineer","engineer will","escalat","take over"]
#         can_escalate = attempt >= 3 and any(h in reply_text.lower() for h in escalation_hints)

#         return ChatMessageResponse(
#             session_id=session_id, reply=reply_text,
#             intent=data.intent or "solve",
#             detected_domain=session["domain"],
#             detected_severity=session["severity"],
#             resolved=False, can_escalate=can_escalate, attempt_number=attempt,
#         )

#     except Exception as e:
#         print(f"\n⚠ Claude error: {e}")
#         return ChatMessageResponse(
#             session_id=session_id,
#             reply="Having a temporary issue on my end. Please try again in a moment.",
#             intent=data.intent or "solve",
#             detected_domain=session["domain"] or "other",
#             detected_severity=session["severity"] or "medium",
#             resolved=False, can_escalate=False, attempt_number=attempt,
#         )


# # ── Ticket number ─────────────────────────────────────────────────────────────

# def _generate_ticket_number(db: Session) -> str:
#     max_t = db.query(func.max(Ticket.ticket_number)).scalar()
#     if max_t:
#         try: return f"T-{str(int(max_t.split('-')[1])+1).zfill(4)}"
#         except: pass
#     return f"T-{str(db.query(Ticket).count()+1001).zfill(4)}"


# # ── Routing engine ────────────────────────────────────────────────────────────

# def _find_best_engineer(db: Session, domain: TicketDomain, user_timezone: str = "UTC") -> Optional[str]:
#     engineers = db.query(Engineer, User).join(User, Engineer.user_id == User.id).filter(
#         Engineer.is_activated == True, User.is_active == True,
#         Engineer.availability_status == AvailabilityStatus.AVAILABLE,
#     ).all()
#     if not engineers: return None
#     best, best_score = None, -999
#     for eng, usr in engineers:
#         score = 0
#         domain_val = domain.value if hasattr(domain, "value") else str(domain).lower()
#         if domain_val in (eng.domain_expertise or []): score += 10
#         try:
#             user_tz = pytz.timezone(user_timezone); eng_tz = pytz.timezone(eng.timezone)
#             now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
#             tz_diff = abs(user_tz.utcoffset(now_utc).total_seconds() - eng_tz.utcoffset(now_utc).total_seconds()) / 3600
#             if tz_diff == 0: score += 5
#             elif tz_diff <= 3: score += 3
#             elif tz_diff <= 6: score += 1
#         except: pass
#         score -= eng.active_ticket_count
#         if score > best_score: best_score = score; best = usr.id
#     return best


# # ── Escalate ──────────────────────────────────────────────────────────────────

# def escalate_to_ticket(db: Session, user: User, data: EscalateRequest) -> EscalateResponse:
#     session         = _sessions.get(data.session_id, {})
#     severity        = session.get("severity","medium")
#     screenshot_path = session.get("screenshot_path")
#     cnn_result      = session.get("cnn_result") or {}  # guard against None when no screenshot uploaded
#     engineer_user_id = _find_best_engineer(db, data.domain, user.timezone or "UTC")

#     priority_map = {"critical":TicketPriority.CRITICAL,"high":TicketPriority.HIGH,"medium":TicketPriority.MEDIUM,"low":TicketPriority.LOW}
#     sla_map      = {"critical":30,"high":120,"medium":480,"low":1440}

#     ai_diagnosis = ""
#     messages     = session.get("messages",[])
#     ai_msgs      = [m["content"] for m in messages if m["role"]=="assistant"]
#     if ai_msgs: ai_diagnosis = ai_msgs[-1][:500]
#     if cnn_result.get("error_class"):
#         ai_diagnosis += f"\n\nCNN Screenshot Detection: {CNN_CLASS_LABELS.get(cnn_result['error_class'],cnn_result['error_class'])} ({int(cnn_result.get('confidence',0)*100)}% confidence)"

#     cnn_image_result = None
#     if screenshot_path:
#         cnn_image_result = os.path.basename(screenshot_path)
#         if cnn_result.get("error_class"):
#             cnn_image_result += f" | {CNN_CLASS_LABELS.get(cnn_result['error_class'],cnn_result['error_class'])} ({int(cnn_result.get('confidence',0)*100)}%)"

#     # ── Complexity prediction ─────────────────────────────────────────────────
#     import json as _json
#     import asyncio
#     ticket_text = f"{data.title} {data.description}"
#     model_predictions = {}
#     complexity_result = "moderate"
#     try:
#         from app.ml.complexity_verdict import claude_verify_complexity, generate_model_predictions
#         try:
#             import httpx as _httpx
#             key = settings.ANTHROPIC_API_KEY
#             _resp = _httpx.post(
#                 "https://api.anthropic.com/v1/messages",
#                 headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
#                 json={
#                     "model": "claude-sonnet-4-5",
#                     "max_tokens": 5,
#                     "system": "Rate this IT ticket 2 or 3. 2=moderate. 3=complex/P1/outage/business halted/50+users. Reply with number only.",
#                     "messages": [{"role": "user", "content": ticket_text[:800]}]
#                 },
#                 timeout=12.0
#             )
#             raw = _resp.json()["content"][0]["text"].strip()
#             print(f"  🔍 Raw verdict: {repr(raw)}")
#             claude_verdict = "complex" if "3" in raw else "moderate"
#         except Exception as _e:
#             print(f"  ⚠ Verdict error: {_e}")
#             claude_verdict = "moderate"
#         all_preds = generate_model_predictions(claude_verdict, ticket_text)
#         model_predictions = all_preds
#         complexity_result = all_preds.get("consensus", "moderate")
#         print(f"  🧠 All Models: RNN={all_preds['models'].get('rnn',{}).get('complexity','?')} | LSTM={all_preds['models'].get('lstm',{}).get('complexity','?')} | GRU={all_preds['models'].get('gru',{}).get('complexity','?')} | BiLSTM={all_preds['models'].get('bilstm',{}).get('complexity','?')} | Consensus={complexity_result}")
#     except Exception as e:
#         print(f"  ⚠️  Prediction error: {e}")

#     complexity_map = {"simple": TicketComplexity.SIMPLE, "moderate": TicketComplexity.MODERATE, "complex": TicketComplexity.COMPLEX}

#     ticket = Ticket(
#         ticket_number=_generate_ticket_number(db),
#         user_id=user.id, engineer_id=engineer_user_id,
#         title=data.title, description=data.description,
#         domain=TicketDomain(str(data.domain).lower().replace("ticketdomain.", "")) if data.domain else TicketDomain.OTHER,
#         priority=priority_map.get(severity,TicketPriority.MEDIUM),
#         status=TicketStatus.OPEN,
#         complexity=complexity_map.get(complexity_result, TicketComplexity.MODERATE),
#         steps_tried=data.steps_tried,
#         ai_diagnosis=ai_diagnosis.strip() or None,
#         ai_attempted=True, cnn_image_result=cnn_image_result,
#         user_city=user.city, user_country=user.country, user_timezone=user.timezone,
#         sla_deadline=datetime.utcnow() + timedelta(minutes=sla_map.get(severity,480)),
#         model_predictions=_json.dumps(model_predictions) if model_predictions else None,
#     )
#     db.add(ticket)
#     if engineer_user_id:
#         eng = db.query(Engineer).filter(Engineer.user_id==engineer_user_id).first()
#         if eng: eng.active_ticket_count += 1
#     db.commit(); db.refresh(ticket)

#     print(f"\n  🎯 Ticket: {ticket.ticket_number} | Domain: {data.domain if isinstance(data.domain, str) else data.domain.value} | Engineer: {engineer_user_id or 'Unassigned'}\n")
#     if data.session_id in _sessions: del _sessions[data.session_id]

#     return EscalateResponse(
#         ticket_id=ticket.id, ticket_number=ticket.ticket_number,
#         message=f"Ticket {ticket.ticket_number} created and assigned to the best available engineer.",
#     )


# # ── User tickets ──────────────────────────────────────────────────────────────

# def get_user_tickets(db: Session, user: User) -> list:
#     return [_user_ticket_response(db,t) for t in
#             db.query(Ticket).filter(Ticket.user_id==user.id).order_by(Ticket.created_at.desc()).all()]


# def get_user_ticket(db: Session, user: User, ticket_id: str) -> UserTicketResponse:
#     ticket = db.query(Ticket).filter(Ticket.id==ticket_id, Ticket.user_id==user.id).first()
#     if not ticket: raise HTTPException(status_code=404, detail="Ticket not found")
#     return _user_ticket_response(db, ticket)


# def _user_ticket_response(db: Session, ticket: Ticket) -> UserTicketResponse:
#     engineer_name=engineer_id_str=engineer_city=engineer_country=engineer_timezone=None
#     if ticket.engineer_id:
#         eng_user = db.query(User).filter(User.id==ticket.engineer_id).first()
#         eng      = db.query(Engineer).filter(Engineer.user_id==ticket.engineer_id).first()
#         if eng_user:
#             engineer_name=eng_user.full_name;engineer_city=eng_user.city
#             engineer_country=eng_user.country;engineer_timezone=eng_user.timezone
#         if eng: engineer_id_str=eng.engineer_id
#     return UserTicketResponse(
#         id=ticket.id,ticket_number=ticket.ticket_number,
#         title=ticket.title,domain=ticket.domain,
#         priority=ticket.priority,status=ticket.status,
#         engineer_name=engineer_name,engineer_id=engineer_id_str,
#         engineer_city=engineer_city,engineer_country=engineer_country,
#         engineer_timezone=engineer_timezone,
#         created_at=ticket.created_at,updated_at=ticket.updated_at,
#         resolved_at=ticket.resolved_at,
#     )

# File: backend/app/services/chat_service.py

from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException
from datetime import datetime, timedelta
from typing import Optional
import uuid
import json
import pytz
import os
import anthropic

from app.core.config import settings
from app.models.user import User
from app.models.ticket import Ticket, TicketStatus, TicketPriority, TicketComplexity, TicketDomain
from app.models.engineer import Engineer, AvailabilityStatus
from app.schemas.chat import (
    ChatMessageRequest, ChatMessageResponse,
    EscalateRequest, EscalateResponse, UserTicketResponse,
)

_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

PRICE_INPUT_PER_MILLION  = 3.00
PRICE_OUTPUT_PER_MILLION = 15.00

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

_sessions: dict = {}

VALID_DOMAINS = [
    "networking", "hardware", "software", "security",
    "email_communication", "identity_access", "database",
    "cloud", "infrastructure", "devops", "erp_business_apps",
    "endpoint_management", "other",
]

# ── CNN mappings ──────────────────────────────────────────────────────────────
CNN_CLASS_TO_DOMAIN = {
    "bsod":"hardware","memory_error":"hardware","cpu_high":"infrastructure",
    "disk_full":"infrastructure","hardware_failure":"hardware",
    "dns_error":"networking","network_unreachable":"networking","vpn_error":"networking",
    "ssl_error":"security","timeout":"networking","permission_denied":"security",
    "login_failed":"identity_access","mfa_error":"identity_access","session_expired":"identity_access",
    "app_crash":"software","update_error":"software","install_error":"software",
    "dependency_error":"devops","db_connection_error":"database",
    "db_query_error":"database","db_timeout":"database",
    "cloud_auth_error":"cloud","deployment_error":"devops",
    "container_error":"devops","general_error":"other",
}
CNN_CLASS_TO_SEVERITY = {
    "bsod":"critical","memory_error":"high","cpu_high":"high","disk_full":"high",
    "hardware_failure":"critical","dns_error":"high","network_unreachable":"critical",
    "vpn_error":"high","ssl_error":"high","timeout":"medium","permission_denied":"high",
    "login_failed":"medium","mfa_error":"medium","session_expired":"low",
    "app_crash":"high","update_error":"medium","install_error":"medium",
    "dependency_error":"medium","db_connection_error":"critical","db_query_error":"high",
    "db_timeout":"high","cloud_auth_error":"high","deployment_error":"critical",
    "container_error":"critical","general_error":"medium",
}
CNN_CLASS_LABELS = {
    "bsod":"Windows Blue Screen of Death","memory_error":"Memory / Out of Memory Error",
    "cpu_high":"High CPU Usage","disk_full":"Disk Full / Low Storage",
    "hardware_failure":"Hardware Failure / Driver Error","dns_error":"DNS Resolution Failure",
    "network_unreachable":"Network Unreachable / No Internet","vpn_error":"VPN Connection Error",
    "ssl_error":"SSL / Certificate Error","timeout":"Connection / Request Timeout",
    "permission_denied":"Permission Denied / Access Error","login_failed":"Login / Authentication Failed",
    "mfa_error":"MFA / Two-Factor Auth Error","session_expired":"Session Expired",
    "app_crash":"Application Crash / Not Responding","update_error":"Software Update Error",
    "install_error":"Installation Failed","dependency_error":"Missing Dependency / Module Error",
    "db_connection_error":"Database Connection Error","db_query_error":"Database Query / SQL Error",
    "db_timeout":"Database Timeout","cloud_auth_error":"Cloud Permission / Auth Error",
    "deployment_error":"Deployment / CI-CD Pipeline Error",
    "container_error":"Container / Docker / Kubernetes Error","general_error":"General Error",
}

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an IT support specialist at NexusDesk. Help users fix IT problems through friendly, clear conversation.

STRICT FORMATTING RULES:
- Never use asterisks, hashtags, dashes as bullets, or any markdown symbols
- Write in plain natural sentences only
- For steps write them as: First do this. Then do that. Finally do this.
- Keep responses under 150 words
- Sound like a helpful colleague, not a manual
- Ask only one question at a time
- Do not start with "Certainly!" or "Absolutely!"

KNOWLEDGE BASE RULES:
- If knowledge base articles are provided below, you MUST use them as your primary source of information.
- Extract the specific steps, commands, and solutions from those articles and include them directly in your response.
- Do not ignore the knowledge base content in favor of generic troubleshooting.
- Do not say "according to the knowledge base" — just naturally give the specific advice.

After 2 failed attempts, tell the user naturally that you recommend getting an engineer involved and they can raise a support ticket.

If the user says it is fixed, say something brief and warm like "Glad that sorted it out."

You cover: networking, hardware, software, security, email, identity and access, databases, cloud, infrastructure, devops, ERP and business apps, endpoint management."""

CLASSIFY_PROMPT = """Classify this IT support conversation. Return only JSON.

Pick domain from this exact list only:
networking, hardware, software, security, email_communication, identity_access, database, cloud, infrastructure, devops, erp_business_apps, endpoint_management, other

Pick severity:
critical = production down or all users affected
high = user completely blocked
medium = degraded or intermittent
low = question or minor issue

Return only: {"domain": "...", "severity": "..."}"""


# ── Cost tracking ─────────────────────────────────────────────────────────────

def _calculate_cost(input_tokens: int, output_tokens: int) -> dict:
    ic = (input_tokens  / 1_000_000) * PRICE_INPUT_PER_MILLION
    oc = (output_tokens / 1_000_000) * PRICE_OUTPUT_PER_MILLION
    return {"input_tokens":input_tokens,"output_tokens":output_tokens,
            "input_cost":round(ic,6),"output_cost":round(oc,6),"total_cost":round(ic+oc,6)}


def _log_cost(session_id: str, call_type: str, cost: dict, session_total: float, info: str = "") -> None:
    print(f"\n{'─'*58}")
    print(f"  NexusDesk — {call_type}")
    print(f"{'─'*58}")
    print(f"  Session : {session_id[:20]}...")
    if info: print(f"  Info    : {info}")
    print(f"  Input   : {cost['input_tokens']:,} tokens → ${cost['input_cost']:.6f}")
    print(f"  Output  : {cost['output_tokens']:,} tokens → ${cost['output_cost']:.6f}")
    print(f"  Call $  : ${cost['total_cost']:.6f}")
    print(f"  Total $ : ${session_total:.6f}")
    print(f"{'─'*58}\n")


# ── Session management ────────────────────────────────────────────────────────

def _get_session(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "messages": [], "domain": None, "severity": None,
            "attempt": 0, "total_cost": 0.0,
            "screenshot_path": None, "cnn_result": None,
        }
    return _sessions[session_id]


# ── Domain classifier ─────────────────────────────────────────────────────────

def _classify_with_claude(text: str, session_id: str, session: dict) -> dict:
    try:
        response = _client.messages.create(
            model="claude-sonnet-4-5", max_tokens=120,
            system=CLASSIFY_PROMPT,
            messages=[{"role":"user","content":text}],
        )
        raw = response.content[0].text.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"No JSON found in: {raw!r}")
        raw = raw[start:end]

        data     = json.loads(raw)
        domain   = data.get("domain", "other")
        severity = data.get("severity", "medium")
        if domain not in VALID_DOMAINS:                        domain = "other"
        if severity not in ["critical","high","medium","low"]: severity = "medium"

        cost = _calculate_cost(response.usage.input_tokens, response.usage.output_tokens)
        session["total_cost"] += cost["total_cost"]
        _log_cost(session_id, "Domain Classification", cost, session["total_cost"],
                  f"domain={domain} | severity={severity}")
        return {"domain": domain, "severity": severity}

    except Exception as e:
        print(f"  ⚠ Classification error: {e}")
        return {"domain": "other", "severity": "medium"}


# ── CNN screenshot analysis ───────────────────────────────────────────────────

def analyze_screenshot(image_bytes: bytes, session_id: str, user_id: str) -> dict:
    session  = _get_session(session_id)
    filename = f"{user_id}_{session_id[:8]}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    with open(filepath, 'wb') as f:
        f.write(image_bytes)
    session["screenshot_path"] = filepath
    print(f"\n  📸 Screenshot saved: {filename}")

    cnn_label      = "Screenshot uploaded"
    cnn_domain     = None
    cnn_severity   = None
    cnn_confidence = 0.0
    cnn_result     = None

    try:
        from app.ml.cnn.predict import predict_screenshot
        cnn_result     = predict_screenshot(image_bytes)
        cnn_class      = cnn_result.get("error_class","general_error")
        cnn_confidence = cnn_result.get("confidence",0.0)
        cnn_domain     = CNN_CLASS_TO_DOMAIN.get(cnn_class,"other")
        cnn_severity   = CNN_CLASS_TO_SEVERITY.get(cnn_class,"medium")
        cnn_label      = CNN_CLASS_LABELS.get(cnn_class,cnn_class)
        session["cnn_result"] = cnn_result
        print(f"  🖼  CNN: {cnn_label} ({int(cnn_confidence*100)}%) → {cnn_domain}")
        if cnn_confidence >= 0.85 and cnn_domain != "other":
            session["domain"]   = cnn_domain
            session["severity"] = cnn_severity
    except Exception as e:
        print(f"  ⚠ CNN error: {e}")

    if cnn_result and cnn_confidence >= 0.85:
        display_text = f"I can see this looks like a {cnn_label} ({int(cnn_confidence*100)}% confidence). Can you tell me more about what happened just before this appeared?"
    elif cnn_result and cnn_confidence >= 0.60:
        display_text = f"Your screenshot looks like it could be a {cnn_label}. Can you describe what happened?"
    else:
        display_text = "I have received your screenshot. Can you describe what is happening so I can help you better?"

    return {
        "success": True, "filename": filename, "display_text": display_text,
        "cnn_label": cnn_label, "cnn_confidence": round(cnn_confidence,4),
        "cnn_domain": cnn_domain, "cnn_severity": cnn_severity,
    }


# ── Main chat function ────────────────────────────────────────────────────────

def process_message(db: Session, user: User, data: ChatMessageRequest) -> ChatMessageResponse:
    session_id = data.session_id or str(uuid.uuid4())
    session    = _get_session(session_id)

    session["messages"].append({"role":"user","content":data.message})
    session["attempt"] += 1
    attempt = session["attempt"]

    full_text  = " ".join(m["content"] for m in session["messages"] if m["role"]=="user")
    classified = _classify_with_claude(full_text, session_id, session)
    if classified["domain"] != "other" or not session["domain"]:
        session["domain"] = classified["domain"]
    session["severity"] = classified["severity"]

    resolved_phrases = ["fixed","works now","that worked","sorted","solved","issue resolved","its working","all good now"]
    if any(p in data.message.lower() for p in resolved_phrases):
        return ChatMessageResponse(
            session_id=session_id,
            reply="Glad that sorted it out. Feel free to reach out if anything else comes up.",
            intent=data.intent or "solve",
            detected_domain=session["domain"] or "other",
            detected_severity=session["severity"] or "medium",
            resolved=True, can_escalate=False, attempt_number=attempt,
        )

    rag_context = ""
    rag_hits    = []
    try:
        from app.services.knowledge_service import get_rag_context, search_knowledge
        rag_context = get_rag_context(
            query=full_text,
            domain=session["domain"] if session["domain"] != "other" else None,
            n_results=3,
        )
        if rag_context:
            kb_result = search_knowledge(
                query=full_text,
                n_results=2,
                domain=session["domain"] if session["domain"] != "other" else None,
            )
            rag_hits = [r for r in kb_result.get("results",[]) if r["cosine_similarity"] >= 45]
            print(f"  📖 RAG: found {len(rag_hits)} relevant KB articles (top: {rag_hits[0]['cosine_similarity']}% match)" if rag_hits else "  📖 RAG: no relevant KB articles found")
    except Exception as e:
        print(f"  ⚠ RAG error: {e}")

    cnn_context = ""
    if session.get("cnn_result"):
        cr = session["cnn_result"]
        cc = cr.get("confidence",0.0)
        if cc >= 0.60:
            cnn_context = f"\n\nNote: User uploaded a screenshot. CNN detected: {CNN_CLASS_LABELS.get(cr.get('error_class',''), cr.get('error_class',''))} ({int(cc*100)}% confidence)."

    intent_note = (
        "This is a service request."
        if data.intent == "service_request"
        else f"This is attempt {attempt}. {'Tell the user you recommend raising a support ticket.' if attempt >= 3 else ''}"
    )

    try:
        response = _client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=512,
            system=f"{SYSTEM_PROMPT}\n\n{intent_note}{cnn_context}{rag_context}",
            messages=session["messages"],
        )
        reply_text = response.content[0].text.strip()
        cost = _calculate_cost(response.usage.input_tokens, response.usage.output_tokens)
        session["total_cost"] += cost["total_cost"]
        _log_cost(session_id,"Main Response",cost,session["total_cost"],
                  f"attempt={attempt} | domain={session['domain']} | RAG hits={len(rag_hits)}")

        session["messages"].append({"role":"assistant","content":reply_text})

        escalation_hints = ["raise a ticket","support ticket","human engineer","engineer will","escalat","take over"]
        can_escalate = attempt >= 3 and any(h in reply_text.lower() for h in escalation_hints)

        return ChatMessageResponse(
            session_id=session_id, reply=reply_text,
            intent=data.intent or "solve",
            detected_domain=session["domain"],
            detected_severity=session["severity"],
            resolved=False, can_escalate=can_escalate, attempt_number=attempt,
        )

    except Exception as e:
        print(f"\n⚠ Claude error: {e}")
        return ChatMessageResponse(
            session_id=session_id,
            reply="Having a temporary issue on my end. Please try again in a moment.",
            intent=data.intent or "solve",
            detected_domain=session["domain"] or "other",
            detected_severity=session["severity"] or "medium",
            resolved=False, can_escalate=False, attempt_number=attempt,
        )


# ── Ticket number ─────────────────────────────────────────────────────────────

def _generate_ticket_number(db: Session) -> str:
    max_t = db.query(func.max(Ticket.ticket_number)).scalar()
    if max_t:
        try: return f"T-{str(int(max_t.split('-')[1])+1).zfill(4)}"
        except: pass
    return f"T-{str(db.query(Ticket).count()+1001).zfill(4)}"


# ── Routing engine ────────────────────────────────────────────────────────────

def _find_best_engineer(
    db: Session,
    domain: TicketDomain,
    user_timezone: str = "UTC",
    user_city: str = ""
) -> Optional[str]:
    engineers = db.query(Engineer, User).join(User, Engineer.user_id == User.id).filter(
        Engineer.is_activated == True,
        User.is_active == True,
        Engineer.availability_status == AvailabilityStatus.AVAILABLE,
    ).all()
    if not engineers: return None

    best, best_score = None, -999
    # Use naive datetime for correct utcoffset calculation
    now_naive = datetime.utcnow()

    for eng, usr in engineers:
        score = 0

        # Domain match — highest priority
        domain_val = domain.value if hasattr(domain, "value") else str(domain).lower()
        if domain_val in (eng.domain_expertise or []):
            score += 10

        # City match tiebreaker
        if user_city and usr.city and usr.city.strip().lower() == user_city.strip().lower():
            score += 2

        # Timezone proximity — fixed with naive datetime
        try:
            user_tz  = pytz.timezone(user_timezone)
            eng_tz   = pytz.timezone(usr.timezone or "UTC")
            user_off = user_tz.utcoffset(now_naive).total_seconds() / 3600
            eng_off  = eng_tz.utcoffset(now_naive).total_seconds() / 3600
            tz_diff  = abs(user_off - eng_off)
            if tz_diff == 0:
                score += 5
            elif tz_diff <= 3:
                score += 3
            elif tz_diff <= 6:
                score += 1
        except Exception:
            pass

        # Workload penalty
        score -= eng.active_ticket_count

        if score > best_score:
            best_score = score
            best = usr.id

    return best


# ── Escalate ──────────────────────────────────────────────────────────────────

def escalate_to_ticket(db: Session, user: User, data: EscalateRequest) -> EscalateResponse:
    session          = _sessions.get(data.session_id, {})
    severity         = session.get("severity", "medium")
    screenshot_path  = session.get("screenshot_path")
    cnn_result       = session.get("cnn_result") or {}

    # ── Routing — now passes user city for tiebreaker ─────────────────────────
    engineer_user_id = _find_best_engineer(
        db,
        data.domain,
        user.timezone or "UTC",
        user.city or ""
    )

    priority_map = {"critical":TicketPriority.CRITICAL,"high":TicketPriority.HIGH,"medium":TicketPriority.MEDIUM,"low":TicketPriority.LOW}
    sla_map      = {"critical":30,"high":120,"medium":480,"low":1440}

    ai_diagnosis = ""
    messages     = session.get("messages", [])
    ai_msgs      = [m["content"] for m in messages if m["role"] == "assistant"]
    if ai_msgs: ai_diagnosis = ai_msgs[-1][:500]
    if cnn_result.get("error_class"):
        ai_diagnosis += f"\n\nCNN Screenshot Detection: {CNN_CLASS_LABELS.get(cnn_result['error_class'],cnn_result['error_class'])} ({int(cnn_result.get('confidence',0)*100)}% confidence)"

    cnn_image_result = None
    if screenshot_path:
        cnn_image_result = os.path.basename(screenshot_path)
        if cnn_result.get("error_class"):
            cnn_image_result += f" | {CNN_CLASS_LABELS.get(cnn_result['error_class'],cnn_result['error_class'])} ({int(cnn_result.get('confidence',0)*100)}%)"

    # ── Complexity prediction ─────────────────────────────────────────────────
    import json as _json
    ticket_text       = f"{data.title} {data.description}"
    model_predictions = {}
    complexity_result = "moderate"
    try:
        from app.ml.complexity_verdict import generate_model_predictions
        import httpx as _httpx
        key   = settings.ANTHROPIC_API_KEY
        _resp = _httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-5",
                "max_tokens": 5,
                "system": "Rate this IT ticket 2 or 3. 2=moderate. 3=complex/P1/outage/business halted/50+users. Reply with number only.",
                "messages": [{"role": "user", "content": ticket_text[:800]}]
            },
            timeout=12.0
        )
        raw = _resp.json()["content"][0]["text"].strip()
        print(f"  🔍 Raw verdict: {repr(raw)}")
        claude_verdict = "complex" if "3" in raw else "moderate"
    except Exception as _e:
        print(f"  ⚠ Verdict error: {_e}")
        claude_verdict = "moderate"

    try:
        all_preds         = generate_model_predictions(claude_verdict, ticket_text)
        model_predictions = all_preds
        complexity_result = all_preds.get("consensus", "moderate")
        print(f"  🧠 All Models: RNN={all_preds['models'].get('rnn',{}).get('complexity','?')} | LSTM={all_preds['models'].get('lstm',{}).get('complexity','?')} | GRU={all_preds['models'].get('gru',{}).get('complexity','?')} | BiLSTM={all_preds['models'].get('bilstm',{}).get('complexity','?')} | Consensus={complexity_result}")
    except Exception as e:
        print(f"  ⚠️  Prediction error: {e}")

    complexity_map = {
        "simple":   TicketComplexity.SIMPLE,
        "moderate": TicketComplexity.MODERATE,
        "complex":  TicketComplexity.COMPLEX
    }

    ticket = Ticket(
        ticket_number    = _generate_ticket_number(db),
        user_id          = user.id,
        engineer_id      = engineer_user_id,
        title            = data.title,
        description      = data.description,
        domain           = TicketDomain(str(data.domain).lower().replace("ticketdomain.", "")) if data.domain else TicketDomain.OTHER,
        priority         = priority_map.get(severity, TicketPriority.MEDIUM),
        status           = TicketStatus.OPEN,
        complexity       = complexity_map.get(complexity_result, TicketComplexity.MODERATE),
        steps_tried      = data.steps_tried,
        ai_diagnosis     = ai_diagnosis.strip() or None,
        ai_attempted     = True,
        cnn_image_result = cnn_image_result,
        user_city        = user.city,
        user_country     = user.country,
        user_timezone    = user.timezone,
        sla_deadline     = datetime.utcnow() + timedelta(minutes=sla_map.get(severity, 480)),
        model_predictions= _json.dumps(model_predictions) if model_predictions else None,
    )
    db.add(ticket)
    if engineer_user_id:
        eng = db.query(Engineer).filter(Engineer.user_id == engineer_user_id).first()
        if eng: eng.active_ticket_count += 1
    db.commit()
    db.refresh(ticket)

    print(f"\n  🎯 Ticket: {ticket.ticket_number} | Domain: {data.domain if isinstance(data.domain, str) else data.domain.value} | Engineer: {engineer_user_id or 'Unassigned'}\n")
    if data.session_id in _sessions:
        del _sessions[data.session_id]

    return EscalateResponse(
        ticket_id     = ticket.id,
        ticket_number = ticket.ticket_number,
        message       = f"Ticket {ticket.ticket_number} created and assigned to the best available engineer.",
    )


# ── User tickets ──────────────────────────────────────────────────────────────

def get_user_tickets(db: Session, user: User) -> list:
    return [_user_ticket_response(db, t) for t in
            db.query(Ticket).filter(Ticket.user_id == user.id).order_by(Ticket.created_at.desc()).all()]


def get_user_ticket(db: Session, user: User, ticket_id: str) -> UserTicketResponse:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user.id).first()
    if not ticket: raise HTTPException(status_code=404, detail="Ticket not found")
    return _user_ticket_response(db, ticket)


def _user_ticket_response(db: Session, ticket: Ticket) -> UserTicketResponse:
    engineer_name = engineer_id_str = engineer_city = engineer_country = engineer_timezone = None
    if ticket.engineer_id:
        eng_user = db.query(User).filter(User.id == ticket.engineer_id).first()
        eng      = db.query(Engineer).filter(Engineer.user_id == ticket.engineer_id).first()
        if eng_user:
            engineer_name     = eng_user.full_name
            engineer_city     = eng_user.city
            engineer_country  = eng_user.country
            engineer_timezone = eng_user.timezone
        if eng:
            engineer_id_str = eng.engineer_id
    return UserTicketResponse(
        id               = ticket.id,
        ticket_number    = ticket.ticket_number,
        title            = ticket.title,
        domain           = ticket.domain,
        priority         = ticket.priority,
        status           = ticket.status,
        engineer_name    = engineer_name,
        engineer_id      = engineer_id_str,
        engineer_city    = engineer_city,
        engineer_country = engineer_country,
        engineer_timezone= engineer_timezone,
        created_at       = ticket.created_at,
        updated_at       = ticket.updated_at,
        resolved_at      = ticket.resolved_at,
    )

