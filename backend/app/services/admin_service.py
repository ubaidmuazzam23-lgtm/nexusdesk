# File: backend/app/services/admin_service.py

import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime
import secrets
import string
import threading

from app.models.user import User, UserRole

logger = logging.getLogger(__name__)
from app.models.engineer import Engineer, AvailabilityStatus
from app.models.ticket import Ticket, TicketStatus
from app.core.security import hash_password
from app.schemas.admin import (
    CreateEngineerRequest, UpdateEngineerRequest,
    EngineerResponse, PlatformOverviewResponse, AdminTicketResponse,
)
from app.services.email_service import (
    send_engineer_credentials_email,
    send_engineer_deactivated_email,
    send_engineer_reactivated_email,
)


_ENGINEER_ID_MAX_ATTEMPTS = 100


def _generate_engineer_id(db: Session) -> str:
    for _ in range(_ENGINEER_ID_MAX_ATTEMPTS):
        eid = f"ENG-{secrets.randbelow(9000) + 1000}"
        if not db.query(Engineer).filter(Engineer.engineer_id == eid).first():
            return eid
    raise RuntimeError("Could not generate a unique engineer ID after multiple attempts")


def _generate_temp_password(length: int = 10) -> str:
    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits + '#@!$'
    pwd = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice('#@!$'),
    ]
    pwd += [secrets.choice(chars) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(pwd)
    return ''.join(pwd)


def create_engineer(db: Session, data: CreateEngineerRequest, admin_user: User) -> EngineerResponse:
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    engineer_id   = _generate_engineer_id(db)
    temp_password = _generate_temp_password()

    user = User(
        email=data.email,
        hashed_password=hash_password(temp_password),
        full_name=data.full_name,
        role=UserRole.ENGINEER,
        is_active=True,
        is_verified=False,
        timezone=data.timezone,
    )
    db.add(user)
    db.flush()

    engineer = Engineer(
        user_id=user.id,
        engineer_id=engineer_id,
        domain_expertise=data.domain_expertise,
        region=data.region,
        timezone=data.timezone,
        seniority_level=data.seniority_level,
        max_ticket_capacity=data.max_ticket_capacity,
        is_activated=False,
        availability_status=AvailabilityStatus.AWAY,
        temp_password_hash=hash_password(temp_password),
    )
    db.add(engineer)
    db.commit()
    db.refresh(engineer)
    db.refresh(user)

    logger.info("[AUDIT] admin=%s created engineer=%s email=%s region=%s",
                admin_user.email, engineer_id, data.email, data.region)

    threading.Thread(
        target=send_engineer_credentials_email,
        args=(user.email, user.full_name, engineer_id, temp_password),
        daemon=True
    ).start()

    return _engineer_to_response(engineer, user)


def list_engineers(db: Session, region: str = None, status: str = None, search: str = None) -> list:
    query = db.query(Engineer, User).join(User, Engineer.user_id == User.id)
    if region:
        query = query.filter(Engineer.region == region)
    if status == 'active':
        query = query.filter(Engineer.is_activated == True, User.is_active == True)
    elif status == 'pending':
        query = query.filter(Engineer.is_activated == False)
    elif status == 'deactivated':
        query = query.filter(User.is_active == False)
    if search:
        s = f"%{search.lower()}%"
        query = query.filter(
            (User.full_name.ilike(s)) | (User.email.ilike(s)) |
            (Engineer.engineer_id.ilike(s)) | (Engineer.region.ilike(s))
        )
    return [_engineer_to_response(eng, usr) for eng, usr in query.all()]


def get_engineer(db: Session, engineer_id: str) -> EngineerResponse:
    result = db.query(Engineer, User).join(User, Engineer.user_id == User.id).filter(
        Engineer.engineer_id == engineer_id
    ).first()
    if not result:
        raise HTTPException(status_code=404, detail="Engineer not found")
    return _engineer_to_response(*result)


def update_engineer(db: Session, engineer_id: str, data: UpdateEngineerRequest, admin_user: User) -> EngineerResponse:
    result = db.query(Engineer, User).join(User, Engineer.user_id == User.id).filter(
        Engineer.engineer_id == engineer_id
    ).first()
    if not result:
        raise HTTPException(status_code=404, detail="Engineer not found")
    engineer, user = result
    if data.full_name is not None: user.full_name = data.full_name
    if data.domain_expertise is not None: engineer.domain_expertise = data.domain_expertise
    if data.region is not None: engineer.region = data.region
    if data.timezone is not None: engineer.timezone = data.timezone
    if data.seniority_level is not None: engineer.seniority_level = data.seniority_level
    if data.max_ticket_capacity is not None: engineer.max_ticket_capacity = data.max_ticket_capacity
    if data.is_active is not None: user.is_active = data.is_active
    db.commit()
    db.refresh(engineer)
    db.refresh(user)
    logger.info("[AUDIT] admin=%s updated engineer=%s fields=%s",
                admin_user.email, engineer_id, data.model_dump(exclude_none=True))
    return _engineer_to_response(engineer, user)


def deactivate_engineer(db: Session, engineer_id: str, admin_user: User) -> dict:
    result = db.query(Engineer, User).join(User, Engineer.user_id == User.id).filter(
        Engineer.engineer_id == engineer_id
    ).first()
    if not result:
        raise HTTPException(status_code=404, detail="Engineer not found")
    engineer, user = result
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Engineer is already deactivated")
    user.is_active = False
    engineer.availability_status = AvailabilityStatus.AWAY
    db.commit()
    logger.info("[AUDIT] admin=%s deactivated engineer=%s email=%s",
                admin_user.email, engineer_id, user.email)
    threading.Thread(target=send_engineer_deactivated_email, args=(user.email, user.full_name, engineer_id), daemon=True).start()
    return {"message": f"Engineer {engineer_id} deactivated"}


def reactivate_engineer(db: Session, engineer_id: str, admin_user: User) -> dict:
    result = db.query(Engineer, User).join(User, Engineer.user_id == User.id).filter(
        Engineer.engineer_id == engineer_id
    ).first()
    if not result:
        raise HTTPException(status_code=404, detail="Engineer not found")
    engineer, user = result
    if user.is_active:
        raise HTTPException(status_code=400, detail="Engineer is already active")
    user.is_active = True
    engineer.availability_status = AvailabilityStatus.AVAILABLE
    db.commit()
    logger.info("[AUDIT] admin=%s reactivated engineer=%s email=%s",
                admin_user.email, engineer_id, user.email)
    threading.Thread(target=send_engineer_reactivated_email, args=(user.email, user.full_name, engineer_id), daemon=True).start()
    return {"message": f"Engineer {engineer_id} reactivated"}


# ── Admin Tickets ─────────────────────────────────────────────────────────────

_TICKET_LIST_LIMIT = 500


def list_all_tickets(
    db: Session,
    status: str = None,
    domain: str = None,
    priority: str = None,
    search: str = None,
) -> list:
    query = db.query(Ticket)

    if status:
        query = query.filter(Ticket.status == status)
    if domain:
        query = query.filter(Ticket.domain == domain)
    if priority:
        query = query.filter(Ticket.priority == priority)
    if search:
        s = f"%{search.lower()}%"
        query = query.filter(
            (Ticket.ticket_number.ilike(s)) |
            (Ticket.title.ilike(s)) |
            (Ticket.description.ilike(s))
        )

    tickets = query.order_by(Ticket.created_at.desc()).limit(_TICKET_LIST_LIMIT).all()
    return [_ticket_to_response(db, t) for t in tickets]


def _ticket_to_response(db: Session, ticket: Ticket) -> AdminTicketResponse:
    # User info
    user = db.query(User).filter(User.id == ticket.user_id).first()
    user_name    = user.full_name if user else "Unknown"
    user_email   = user.email if user else ""

    # Engineer info
    engineer_name     = None
    engineer_id_str   = None
    engineer_email    = None
    engineer_region   = None
    engineer_timezone = None
    engineer_seniority = None

    if ticket.engineer_id:
        eng_user = db.query(User).filter(User.id == ticket.engineer_id).first()
        eng      = db.query(Engineer).filter(Engineer.user_id == ticket.engineer_id).first()
        if eng_user:
            engineer_name     = eng_user.full_name
            engineer_email    = eng_user.email
            engineer_timezone = eng_user.timezone
        if eng:
            engineer_id_str   = eng.engineer_id
            engineer_region   = eng.region
            engineer_seniority = eng.seniority_level.value if eng.seniority_level else None

    return AdminTicketResponse(
        id=ticket.id,
        ticket_number=ticket.ticket_number,
        title=ticket.title,
        description=ticket.description,
        domain=ticket.domain,
        priority=ticket.priority,
        status=ticket.status,
        complexity=ticket.complexity,
        ai_diagnosis=ticket.ai_diagnosis,
        steps_tried=ticket.steps_tried,
        resolution_notes=ticket.resolution_notes,
        sla_deadline=ticket.sla_deadline,
        sla_breached=ticket.sla_breached,
        user_name=user_name,
        user_email=user_email,
        user_city=ticket.user_city,
        user_country=ticket.user_country,
        user_timezone=ticket.user_timezone,
        engineer_name=engineer_name,
        engineer_id=engineer_id_str,
        engineer_email=engineer_email,
        engineer_region=engineer_region,
        engineer_timezone=engineer_timezone,
        engineer_seniority=engineer_seniority,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        resolved_at=ticket.resolved_at,
    )


# ── Platform Overview ─────────────────────────────────────────────────────────

def get_platform_overview(db: Session) -> PlatformOverviewResponse:
    from datetime import date
    total_users        = db.query(User).filter(User.role == UserRole.USER).count()
    total_engineers    = db.query(Engineer).count()
    total_tickets      = db.query(Ticket).count()
    open_tickets       = db.query(Ticket).filter(Ticket.status.in_(['open', 'in_progress'])).count()
    engineers_available = db.query(Engineer).filter(Engineer.availability_status == AvailabilityStatus.AVAILABLE).count()
    engineers_busy     = db.query(Engineer).filter(Engineer.availability_status == AvailabilityStatus.BUSY).count()
    engineers_away     = db.query(Engineer).filter(Engineer.availability_status == AvailabilityStatus.AWAY).count()
    regions            = db.query(Engineer.region).distinct().all()
    active_regions     = [r[0] for r in regions if r[0]]

    today = datetime.utcnow().date()
    resolved_today = db.query(Ticket).filter(
        Ticket.status == TicketStatus.RESOLVED,
        Ticket.resolved_at >= datetime.combine(today, datetime.min.time()),
    ).count() if hasattr(datetime, 'combine') else 0

    ai_resolved_today = db.query(Ticket).filter(
        Ticket.ai_resolved == True,
        Ticket.resolved_at >= datetime.combine(today, datetime.min.time()),
    ).count() if hasattr(datetime, 'combine') else 0

    ai_resolution_rate = (ai_resolved_today / resolved_today * 100) if resolved_today > 0 else 0.0

    return PlatformOverviewResponse(
        total_users=total_users,
        total_engineers=total_engineers,
        total_tickets=total_tickets,
        open_tickets=open_tickets,
        resolved_today=resolved_today,
        ai_resolved_today=ai_resolved_today,
        ai_resolution_rate=ai_resolution_rate,
        engineers_available=engineers_available,
        engineers_busy=engineers_busy,
        engineers_away=engineers_away,
        sla_compliance_rate=100.0,
        active_regions=active_regions,
    )


def _engineer_to_response(engineer: Engineer, user: User) -> EngineerResponse:
    return EngineerResponse(
        id=engineer.id, user_id=engineer.user_id,
        engineer_id=engineer.engineer_id,
        full_name=user.full_name, email=user.email,
        domain_expertise=engineer.domain_expertise or [],
        region=engineer.region, timezone=engineer.timezone,
        seniority_level=engineer.seniority_level,
        max_ticket_capacity=engineer.max_ticket_capacity,
        availability_status=engineer.availability_status,
        active_ticket_count=engineer.active_ticket_count,
        is_activated=engineer.is_activated, is_active=user.is_active,
        total_resolved=engineer.total_resolved,
        avg_resolution_time=engineer.avg_resolution_time,
        sla_compliance_rate=engineer.sla_compliance_rate,
        created_at=engineer.created_at,
    )