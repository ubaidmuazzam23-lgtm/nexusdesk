# File: backend/app/api/v1/routes/analytics.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from datetime import datetime, timedelta
from collections import defaultdict

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.user import User, UserRole
from app.models.ticket import Ticket, TicketStatus, TicketDomain, TicketPriority

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def get_admin(current_user: User = Depends(require_role(UserRole.ADMIN))) -> User:
    return current_user


@router.get("/overview")
def analytics_overview(db: Session = Depends(get_db), admin: User = Depends(get_admin)):
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total        = db.query(func.count(Ticket.id)).scalar() or 0
    open_        = db.query(func.count(Ticket.id)).filter(Ticket.status == TicketStatus.OPEN).scalar() or 0
    in_progress  = db.query(func.count(Ticket.id)).filter(Ticket.status == TicketStatus.IN_PROGRESS).scalar() or 0
    resolved     = db.query(func.count(Ticket.id)).filter(Ticket.status == TicketStatus.RESOLVED).scalar() or 0
    this_week    = db.query(func.count(Ticket.id)).filter(Ticket.created_at >= week_ago).scalar() or 0
    this_month   = db.query(func.count(Ticket.id)).filter(Ticket.created_at >= month_ago).scalar() or 0

    # SLA compliance
    total_with_sla = db.query(func.count(Ticket.id)).filter(Ticket.sla_deadline.isnot(None)).scalar() or 0
    breached = db.query(func.count(Ticket.id)).filter(
        Ticket.sla_deadline.isnot(None),
        Ticket.sla_breached == True
    ).scalar() or 0
    sla_compliance = round(((total_with_sla - breached) / total_with_sla * 100), 1) if total_with_sla > 0 else 100.0

    # AI resolution rate
    ai_resolved = db.query(func.count(Ticket.id)).filter(
        Ticket.ai_attempted == True,
        Ticket.status == TicketStatus.RESOLVED,
        Ticket.engineer_id.is_(None)
    ).scalar() or 0

    return {
        "total": total,
        "open": open_,
        "in_progress": in_progress,
        "resolved": resolved,
        "this_week": this_week,
        "this_month": this_month,
        "sla_compliance": sla_compliance,
        "sla_breached": breached,
        "ai_resolution_rate": round((ai_resolved / resolved * 100), 1) if resolved > 0 else 0,
    }


@router.get("/by-domain")
def analytics_by_domain(db: Session = Depends(get_db), admin: User = Depends(get_admin)):
    rows = db.query(
        Ticket.domain,
        func.count(Ticket.id).label("total"),
        func.sum(case((Ticket.status == TicketStatus.RESOLVED, 1), else_=0)).label("resolved"),
        func.sum(case((Ticket.status == TicketStatus.OPEN, 1), else_=0)).label("open"),
    ).group_by(Ticket.domain).all()

    domain_labels = {
        "networking": "Networking", "hardware": "Hardware", "software": "Software",
        "security": "Security", "email_communication": "Email & Comm",
        "identity_access": "Identity & Access", "database": "Database",
        "cloud": "Cloud", "infrastructure": "Infrastructure", "devops": "DevOps",
        "erp_business_apps": "ERP & Business", "endpoint_management": "Endpoint Mgmt",
        "other": "Other",
    }

    return [
        {
            "domain": r.domain.value if hasattr(r.domain, "value") else str(r.domain),
            "label": domain_labels.get(r.domain.value if hasattr(r.domain, "value") else str(r.domain), str(r.domain)),
            "total": r.total,
            "resolved": r.resolved or 0,
            "open": r.open or 0,
        }
        for r in rows
    ]


@router.get("/by-priority")
def analytics_by_priority(db: Session = Depends(get_db), admin: User = Depends(get_admin)):
    rows = db.query(
        Ticket.priority,
        func.count(Ticket.id).label("total"),
        func.sum(case((Ticket.status == TicketStatus.RESOLVED, 1), else_=0)).label("resolved"),
    ).group_by(Ticket.priority).all()

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    colors = {"critical": "#ef4444", "high": "#f97316", "medium": "#eab308", "low": "#6b7280"}

    result = [
        {
            "priority": r.priority.value if hasattr(r.priority, "value") else str(r.priority),
            "total": r.total,
            "resolved": r.resolved or 0,
            "color": colors.get(r.priority.value if hasattr(r.priority, "value") else str(r.priority), "#6b7280"),
        }
        for r in rows
    ]
    return sorted(result, key=lambda x: order.get(x["priority"], 99))


@router.get("/over-time")
def analytics_over_time(days: int = 30, db: Session = Depends(get_db), admin: User = Depends(get_admin)):
    start = datetime.utcnow() - timedelta(days=days)
    tickets = db.query(Ticket.created_at, Ticket.status).filter(Ticket.created_at >= start).all()

    daily: dict = defaultdict(lambda: {"created": 0, "resolved": 0})
    for t_created, t_status in tickets:
        day = t_created.strftime("%Y-%m-%d")
        daily[day]["created"] += 1
        if t_status == TicketStatus.RESOLVED:
            daily[day]["resolved"] += 1

    # Fill missing days
    result = []
    for i in range(days):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        result.append({
            "date": day,
            "label": (start + timedelta(days=i)).strftime("%b %d"),
            "created": daily[day]["created"],
            "resolved": daily[day]["resolved"],
        })
    return result


@router.get("/resolution-time")
def analytics_resolution_time(db: Session = Depends(get_db), admin: User = Depends(get_admin)):
    from sqlalchemy import extract

    # Compute average resolution minutes per priority fully in the DB
    rows = db.query(
        Ticket.priority,
        func.avg(
            func.extract("epoch", Ticket.resolved_at - Ticket.created_at) / 60
        ).label("avg_minutes"),
        func.count(Ticket.id).label("count"),
    ).filter(
        Ticket.status == TicketStatus.RESOLVED,
        Ticket.resolved_at.isnot(None),
    ).group_by(Ticket.priority).all()

    if not rows:
        return {"avg_minutes": 0, "by_priority": {}}

    by_priority = {}
    total_minutes = 0.0
    total_count   = 0
    for r in rows:
        p = r.priority.value if hasattr(r.priority, "value") else str(r.priority)
        avg_mins = round(float(r.avg_minutes or 0), 1)
        by_priority[p] = avg_mins
        total_minutes += float(r.avg_minutes or 0) * r.count
        total_count   += r.count

    overall_avg = round(total_minutes / total_count, 1) if total_count else 0

    return {
        "avg_minutes": overall_avg,
        "by_priority": by_priority,
    }

# Add this to: backend/app/api/v1/routes/analytics.py
# (paste after the existing /over-time route)

@router.get("/slack-overview")
def slack_overview(db: Session = Depends(get_db), admin: User = Depends(get_admin)):
    """All analytics — every ticket comes from Slack."""
    from sqlalchemy import or_

    now        = datetime.utcnow()
    week_ago   = now - timedelta(days=7)
    month_ago  = now - timedelta(days=30)

    total       = db.query(func.count(Ticket.id)).scalar() or 0
    open_       = db.query(func.count(Ticket.id)).filter(Ticket.status == TicketStatus.OPEN).scalar() or 0
    in_progress = db.query(func.count(Ticket.id)).filter(Ticket.status == TicketStatus.IN_PROGRESS).scalar() or 0
    resolved    = db.query(func.count(Ticket.id)).filter(Ticket.status == TicketStatus.RESOLVED).scalar() or 0
    this_week   = db.query(func.count(Ticket.id)).filter(Ticket.created_at >= week_ago).scalar() or 0
    this_month  = db.query(func.count(Ticket.id)).filter(Ticket.created_at >= month_ago).scalar() or 0

    # AI solved: ai_attempted=True, resolved, no engineer assigned
    ai_solved = db.query(func.count(Ticket.id)).filter(
        Ticket.ai_attempted  == True,
        Ticket.status        == TicketStatus.RESOLVED,
        Ticket.engineer_id.is_(None),
    ).scalar() or 0

    # Routed to engineer: resolved with an engineer assigned
    routed = db.query(func.count(Ticket.id)).filter(
        Ticket.status      == TicketStatus.RESOLVED,
        Ticket.engineer_id.isnot(None),
    ).scalar() or 0

    # Unresolved = open + in_progress
    unresolved = open_ + in_progress

    ai_pct     = round((ai_solved / resolved * 100), 1) if resolved > 0 else 0
    routed_pct = round((routed    / resolved * 100), 1) if resolved > 0 else 0

    # By domain
    domain_rows = db.query(
        Ticket.domain,
        func.count(Ticket.id).label("total"),
        func.sum(case((Ticket.status == TicketStatus.RESOLVED, 1), else_=0)).label("resolved"),
        func.sum(case((Ticket.status == TicketStatus.OPEN,     1), else_=0)).label("open"),
        func.sum(case((Ticket.ai_attempted == True, 1), else_=0)).label("ai_attempted"),
    ).group_by(Ticket.domain).all()

    domain_labels = {
        "networking":"Networking","hardware":"Hardware","software":"Software",
        "security":"Security","email_communication":"Email & Comm",
        "identity_access":"Identity & Access","database":"Database",
        "cloud":"Cloud","infrastructure":"Infrastructure","devops":"DevOps",
        "erp_business_apps":"ERP & Business","endpoint_management":"Endpoint Mgmt","other":"Other",
    }

    domains = [
        {
            "domain":   r.domain.value if hasattr(r.domain, "value") else str(r.domain),
            "label":    domain_labels.get(r.domain.value if hasattr(r.domain, "value") else str(r.domain), str(r.domain)),
            "total":    r.total,
            "resolved": r.resolved    or 0,
            "open":     r.open        or 0,
            "ai_tried": r.ai_attempted or 0,
        }
        for r in domain_rows
    ]

    # By priority
    priority_rows = db.query(
        Ticket.priority,
        func.count(Ticket.id).label("total"),
        func.sum(case((Ticket.status == TicketStatus.RESOLVED, 1), else_=0)).label("resolved"),
    ).group_by(Ticket.priority).all()

    order = {"critical":0,"high":1,"medium":2,"low":3}
    priorities = sorted([
        {
            "priority": r.priority.value if hasattr(r.priority, "value") else str(r.priority),
            "total":    r.total,
            "resolved": r.resolved or 0,
        }
        for r in priority_rows
    ], key=lambda x: order.get(x["priority"], 99))

    # Over time (30 days)
    from collections import defaultdict
    start   = now - timedelta(days=30)
    t_rows  = db.query(Ticket.created_at, Ticket.status, Ticket.engineer_id, Ticket.ai_attempted).filter(
        Ticket.created_at >= start
    ).all()

    daily: dict = defaultdict(lambda: {"created":0,"ai_solved":0,"routed":0})
    for t_created, t_status, t_eng, t_ai in t_rows:
        day = t_created.strftime("%Y-%m-%d")
        daily[day]["created"] += 1
        if t_status == TicketStatus.RESOLVED:
            if t_ai and t_eng is None:
                daily[day]["ai_solved"] += 1
            elif t_eng is not None:
                daily[day]["routed"]    += 1

    time_series = []
    for i in range(30):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        time_series.append({
            "date":     day,
            "label":    (start + timedelta(days=i)).strftime("%b %d"),
            "created":  daily[day]["created"],
            "ai_solved":daily[day]["ai_solved"],
            "routed":   daily[day]["routed"],
        })

    # Recent tickets (last 8)
    recent = db.query(Ticket).order_by(Ticket.created_at.desc()).limit(8).all()
    recent_tickets = []
    for t in recent:
        from app.models.user import User as UserModel
        eng = db.query(UserModel).filter(UserModel.id == t.engineer_id).first() if t.engineer_id else None
        recent_tickets.append({
            "ticket_number": t.ticket_number,
            "title":         t.title,
            "domain":        t.domain.value if hasattr(t.domain, "value") else str(t.domain),
            "priority":      t.priority.value if hasattr(t.priority, "value") else str(t.priority),
            "status":        t.status.value if hasattr(t.status, "value") else str(t.status),
            "engineer_name": eng.full_name if eng else None,
            "ai_attempted":  t.ai_attempted or False,
            "ai_resolved":   t.ai_resolved  or False,
            "user_city":     t.user_city,
            "created_at":    t.created_at.isoformat(),
        })

    return {
        "total":        total,
        "open":         open_,
        "in_progress":  in_progress,
        "resolved":     resolved,
        "unresolved":   unresolved,
        "ai_solved":    ai_solved,
        "routed":       routed,
        "ai_pct":       ai_pct,
        "routed_pct":   routed_pct,
        "this_week":    this_week,
        "this_month":   this_month,
        "domains":      domains,
        "priorities":   priorities,
        "time_series":  time_series,
        "recent":       recent_tickets,
    }