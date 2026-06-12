# File: backend/app/services/engineer_service.py

import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from app.models.user import User
from app.models.engineer import Engineer, AvailabilityStatus
from app.models.ticket import Ticket, TicketMessage, TicketStatus
from app.schemas.engineer import (
    EngineerProfileResponse, UpdateAvailabilityRequest,
    TicketResponse, TicketMessageResponse,
    UpdateTicketRequest, EngineerStatsResponse
)


# ── Profile ───────────────────────────────────────────────────────────────────

def get_engineer_profile(db: Session, user: User) -> EngineerProfileResponse:
    engineer = db.query(Engineer).filter(Engineer.user_id == user.id).first()
    if not engineer:
        raise HTTPException(status_code=404, detail="Engineer profile not found")
    return EngineerProfileResponse(
        engineer_id=engineer.engineer_id,
        full_name=user.full_name,
        email=user.email,
        domain_expertise=engineer.domain_expertise or [],
        region=engineer.region,
        timezone=engineer.timezone,
        seniority_level=engineer.seniority_level,
        max_ticket_capacity=engineer.max_ticket_capacity,
        availability_status=engineer.availability_status,
        active_ticket_count=engineer.active_ticket_count,
        total_resolved=engineer.total_resolved,
        avg_resolution_time=engineer.avg_resolution_time,
        sla_compliance_rate=engineer.sla_compliance_rate,
    )


# ── Availability ──────────────────────────────────────────────────────────────

def update_availability(db: Session, user: User, data: UpdateAvailabilityRequest) -> dict:
    engineer = db.query(Engineer).filter(Engineer.user_id == user.id).first()
    if not engineer:
        raise HTTPException(status_code=404, detail="Engineer profile not found")

    engineer.availability_status = data.status
    db.commit()

    return {"message": f"Availability updated to {data.status.value}", "status": data.status.value}


# ── Tickets ───────────────────────────────────────────────────────────────────

def get_engineer_tickets(db: Session, user: User, status: str = None) -> list:
    query = db.query(Ticket).filter(Ticket.engineer_id == user.id)
    if status:
        query = query.filter(Ticket.status == status)
    # Sort by priority then created_at
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    tickets = query.limit(200).all()
    tickets.sort(key=lambda t: (priority_order.get(t.priority.value, 99), t.created_at))
    return [_ticket_to_response(db, t) for t in tickets]


def get_ticket(db: Session, user: User, ticket_id: str) -> TicketResponse:
    ticket = db.query(Ticket).filter(
        Ticket.id == ticket_id,
        Ticket.engineer_id == user.id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _ticket_to_response(db, ticket)


def update_ticket(db: Session, user: User, ticket_id: str, data: UpdateTicketRequest) -> TicketResponse:
    ticket = db.query(Ticket).filter(
        Ticket.id == ticket_id,
        Ticket.engineer_id == user.id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if data.status:
        old_status = ticket.status
        ticket.status = data.status

        # If resolved — update engineer stats
        if data.status == TicketStatus.RESOLVED:
            ticket.resolved_at = datetime.utcnow()
            engineer = db.query(Engineer).filter(Engineer.user_id == user.id).first()
            if engineer:
                engineer.total_resolved += 1
                engineer.active_ticket_count = max(0, engineer.active_ticket_count - 1)

        # If in progress — increment active count
        elif data.status == TicketStatus.IN_PROGRESS and old_status == TicketStatus.OPEN:
            engineer = db.query(Engineer).filter(Engineer.user_id == user.id).first()
            if engineer:
                engineer.active_ticket_count += 1

    if data.resolution_notes:
        ticket.resolution_notes = data.resolution_notes

        # ── Auto-index into knowledge base on resolve ─────────────────────────
        # Builds a KB article from this ticket so future similar issues
        # benefit from this engineer's solution automatically.
        if data.status == TicketStatus.RESOLVED or ticket.status == TicketStatus.RESOLVED:
            try:
                from app.services.knowledge_service import upload_document
                domain = ticket.domain.value if hasattr(ticket.domain, "value") else str(ticket.domain)

                kb_text = f"""Issue: {ticket.title}

Description: {ticket.description or 'N/A'}

Steps Already Tried: {ticket.steps_tried or 'N/A'}

Resolution: {data.resolution_notes}

AI Diagnosis: {ticket.ai_diagnosis or 'N/A'}
"""
                upload_document(
                    content=kb_text.encode("utf-8"),
                    filename=f"ticket_{ticket.ticket_number}.txt",
                    title=f"Resolved: {ticket.title[:80]}",
                    domain=domain,
                    description=f"Auto-indexed from resolved ticket {ticket.ticket_number}",
                    uploaded_by=str(user.id),
                    uploaded_by_role="engineer_auto",
                )
                logger.info("[KB] Auto-indexed ticket %s [%s]", ticket.ticket_number, domain)
            except Exception as e:
                logger.warning("[KB] Auto-index failed (non-critical): %s", e)
        # ─────────────────────────────────────────────────────────────────────

    db.commit()
    db.refresh(ticket)
    return _ticket_to_response(db, ticket)


def add_message(db: Session, user: User, ticket_id: str, message: str) -> TicketMessageResponse:
    ticket = db.query(Ticket).filter(
        Ticket.id == ticket_id,
        Ticket.engineer_id == user.id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    msg = TicketMessage(
        ticket_id=ticket.id,
        sender_id=user.id,
        message=message,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return TicketMessageResponse(
        id=msg.id,
        sender_id=msg.sender_id,
        sender_name=user.full_name,
        message=msg.message,
        created_at=msg.created_at,
    )


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_engineer_stats(db: Session, user: User) -> EngineerStatsResponse:
    engineer = db.query(Engineer).filter(Engineer.user_id == user.id).first()
    if not engineer:
        raise HTTPException(status_code=404, detail="Engineer profile not found")

    week_ago = datetime.utcnow() - timedelta(days=7)
    this_week = db.query(Ticket).filter(
        Ticket.engineer_id == user.id,
        Ticket.status == TicketStatus.RESOLVED,
        Ticket.resolved_at >= week_ago,
    ).count()

    return EngineerStatsResponse(
        total_resolved=engineer.total_resolved,
        active_tickets=engineer.active_ticket_count,
        avg_resolution_time=engineer.avg_resolution_time,
        sla_compliance_rate=engineer.sla_compliance_rate,
        this_week_resolved=this_week,
    )


# ── Helper ────────────────────────────────────────────────────────────────────

def _ticket_to_response(db: Session, ticket: Ticket) -> TicketResponse:
    user = db.query(User).filter(User.id == ticket.user_id).first()
    messages = db.query(TicketMessage).filter(
        TicketMessage.ticket_id == ticket.id
    ).order_by(TicketMessage.created_at).all()

    # Batch-load all senders in one query to avoid N+1
    sender_ids   = {msg.sender_id for msg in messages if msg.sender_id}
    sender_map   = {
        u.id: u
        for u in db.query(User).filter(User.id.in_(sender_ids)).all()
    } if sender_ids else {}

    msg_responses = []
    for msg in messages:
        sender = sender_map.get(msg.sender_id)
        msg_responses.append(TicketMessageResponse(
            id=msg.id,
            sender_id=msg.sender_id,
            sender_name=sender.full_name if sender else "Unknown",
            message=msg.message,
            created_at=msg.created_at,
        ))

    return TicketResponse(
        id=ticket.id,
        ticket_number=ticket.ticket_number,
        title=ticket.title,
        description=ticket.description,
        domain=ticket.domain,
        priority=ticket.priority,
        status=ticket.status,
        complexity=ticket.complexity,
        ai_diagnosis=ticket.ai_diagnosis,
        ai_confidence=ticket.ai_confidence,
        steps_tried=ticket.steps_tried,
        cnn_image_result=ticket.cnn_image_result,
        resolution_notes=ticket.resolution_notes,
        user_name=user.full_name if user else "Unknown",
        user_email=user.email if user else "",
        user_city=ticket.user_city,
        user_country=ticket.user_country,
        user_timezone=ticket.user_timezone,
        sla_deadline=ticket.sla_deadline,
        sla_breached=ticket.sla_breached,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        messages=msg_responses,
    )


def resolve_ticket(db: Session, user: User, ticket_id: str, resolution_notes: str) -> TicketResponse:
    """Dedicated resolve function — sets status, timestamps, decrements count, auto-indexes KB."""
    ticket = db.query(Ticket).filter(
        Ticket.id == ticket_id,
        Ticket.engineer_id == user.id,
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if not resolution_notes.strip():
        raise HTTPException(status_code=400, detail="Resolution notes are required")

    ticket.status           = TicketStatus.RESOLVED
    ticket.resolved_at      = datetime.utcnow()
    ticket.resolution_notes = resolution_notes

    engineer = db.query(Engineer).filter(Engineer.user_id == user.id).first()
    if engineer:
        engineer.total_resolved    += 1
        engineer.active_ticket_count = max(0, engineer.active_ticket_count - 1)

    # ── Auto-index into knowledge base ────────────────────────────────────────
    try:
        from app.services.knowledge_service import upload_document
        domain = ticket.domain.value if hasattr(ticket.domain, "value") else str(ticket.domain)
        kb_text = f"""Issue: {ticket.title}

Description: {ticket.description or 'N/A'}

Steps Already Tried: {ticket.steps_tried or 'N/A'}

Resolution: {resolution_notes}

AI Diagnosis: {ticket.ai_diagnosis or 'N/A'}
"""
        upload_document(
            content=kb_text.encode("utf-8"),
            filename=f"ticket_{ticket.ticket_number}.txt",
            title=f"Resolved: {ticket.title[:80]}",
            domain=domain,
            description=f"Auto-indexed from resolved ticket {ticket.ticket_number}",
            uploaded_by=str(user.id),
            uploaded_by_role="engineer_auto",
        )
        logger.info("[KB] Auto-indexed ticket %s [%s]", ticket.ticket_number, domain)
    except Exception as e:
        logger.warning("[KB] Auto-index failed (non-critical): %s", e)
    # ─────────────────────────────────────────────────────────────────────────

    db.commit()
    db.refresh(ticket)
    return _ticket_to_response(db, ticket)