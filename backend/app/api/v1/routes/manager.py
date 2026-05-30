# Location: ./backend/app/api/v1/routes/manager.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.team import Team, TeamMember
from app.models.engineer import Engineer
from app.models.ticket import Ticket, TicketStatus

router = APIRouter(prefix="/manager", tags=["Manager"])


def get_manager(current_user: User = Depends(get_current_user)) -> User:
    role = current_user.role.lower() if isinstance(current_user.role, str) else current_user.role.value.lower()
    if role != "manager":
        raise HTTPException(status_code=403, detail="Manager access required")
    return current_user


def _get_manager_team(db: Session, user: User) -> Team:
    team = db.query(Team).filter(Team.manager_id == user.id, Team.is_active == True).first()
    if not team:
        raise HTTPException(status_code=404, detail="No active team assigned to this manager")
    return team


# ── My Team ───────────────────────────────────────────────────────────────────

@router.get("/my-team")
def get_my_team(db: Session = Depends(get_db), manager: User = Depends(get_manager)):
    team = _get_manager_team(db, manager)
    members = []
    for tm in team.members:
        usr = db.query(User).filter(User.id == tm.user_id).first()
        eng = db.query(Engineer).filter(Engineer.user_id == tm.user_id).first()
        if usr:
            members.append({
                "id": str(tm.id),
                "user_id": str(tm.user_id),
                "full_name": usr.full_name,
                "email": usr.email,
                "engineer_id": eng.engineer_id if eng else None,
                "role_in_team": tm.role_in_team.value if hasattr(tm.role_in_team, 'value') else str(tm.role_in_team),
                "domain_expertise": eng.domain_expertise if eng else [],
                "availability_status": eng.availability_status.value if eng and eng.availability_status else "away",
                "active_ticket_count": eng.active_ticket_count if eng else 0,
                "total_resolved": eng.total_resolved if eng else 0,
                "sla_compliance_rate": eng.sla_compliance_rate if eng else 100,
                "joined_at": tm.joined_at.isoformat() if tm.joined_at else None,
            })
    return {
        "id": str(team.id),
        "team_id": team.team_id,
        "name": team.name,
        "description": team.description,
        "domain_focus": team.domain_focus or [],
        "region": team.region,
        "timezone": team.timezone,
        "is_active": team.is_active,
        "max_ticket_capacity": team.max_ticket_capacity,
        "active_ticket_count": team.active_ticket_count,
        "total_resolved": team.total_resolved,
        "avg_resolution_time": team.avg_resolution_time,
        "sla_compliance_rate": team.sla_compliance_rate,
        "member_count": len(members),
        "members": members,
        "created_at": team.created_at.isoformat() if team.created_at else None,
    }


# ── Overview Stats ────────────────────────────────────────────────────────────

@router.get("/overview")
def get_overview(db: Session = Depends(get_db), manager: User = Depends(get_manager)):
    team = _get_manager_team(db, manager)

    # Get all member user IDs
    member_ids = [tm.user_id for tm in team.members]

    # Tickets assigned to team
    team_tickets = db.query(Ticket).filter(Ticket.team_id == team.id).all()
    open_tickets = [t for t in team_tickets if t.status in [TicketStatus.OPEN, TicketStatus.IN_PROGRESS]]
    resolved_tickets = [t for t in team_tickets if t.status == TicketStatus.RESOLVED]
    breached = [t for t in team_tickets if t.sla_breached]

    # Member availability
    available = 0
    busy = 0
    away = 0
    for mid in member_ids:
        eng = db.query(Engineer).filter(Engineer.user_id == mid).first()
        if eng:
            status = eng.availability_status.value if hasattr(eng.availability_status, 'value') else str(eng.availability_status)
            if status == 'available': available += 1
            elif status == 'busy': busy += 1
            else: away += 1

    return {
        "team_name": team.name,
        "team_id": team.team_id,
        "total_members": len(member_ids),
        "available_members": available,
        "busy_members": busy,
        "away_members": away,
        "total_tickets": len(team_tickets),
        "open_tickets": len(open_tickets),
        "resolved_tickets": len(resolved_tickets),
        "sla_breached": len(breached),
        "sla_compliance_rate": team.sla_compliance_rate,
        "avg_resolution_time": team.avg_resolution_time,
    }


# ── Tickets ───────────────────────────────────────────────────────────────────

@router.get("/tickets")
def get_team_tickets(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    manager: User = Depends(get_manager),
):
    team = _get_manager_team(db, manager)
    query = db.query(Ticket).filter(Ticket.team_id == team.id)
    if status:
        query = query.filter(Ticket.status == status)
    tickets = query.order_by(Ticket.created_at.desc()).all()

    result = []
    for t in tickets:
        user = db.query(User).filter(User.id == t.user_id).first()
        engineer = db.query(User).filter(User.id == t.engineer_id).first() if t.engineer_id else None
        eng_profile = db.query(Engineer).filter(Engineer.user_id == t.engineer_id).first() if t.engineer_id else None
        result.append({
            "id": str(t.id),
            "ticket_number": t.ticket_number,
            "title": t.title,
            "description": t.description,
            "domain": t.domain.value if hasattr(t.domain, 'value') else str(t.domain),
            "priority": t.priority.value if hasattr(t.priority, 'value') else str(t.priority),
            "status": t.status.value if hasattr(t.status, 'value') else str(t.status),
            "complexity": t.complexity.value if t.complexity and hasattr(t.complexity, 'value') else str(t.complexity) if t.complexity else None,
            "user_name": user.full_name if user else "Unknown",
            "user_email": user.email if user else "",
            "user_city": t.user_city,
            "user_timezone": t.user_timezone,
            "engineer_name": engineer.full_name if engineer else None,
            "engineer_id": eng_profile.engineer_id if eng_profile else None,
            "sla_deadline": t.sla_deadline.isoformat() if t.sla_deadline else None,
            "sla_breached": t.sla_breached,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
        })
    return result


# ── Assign ticket to engineer ─────────────────────────────────────────────────

@router.patch("/tickets/{ticket_id}/assign")
def assign_ticket(
    ticket_id: str,
    body: dict,
    db: Session = Depends(get_db),
    manager: User = Depends(get_manager),
):
    team = _get_manager_team(db, manager)
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.team_id == team.id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found in your team")

    engineer_id = body.get("engineer_id")
    eng = db.query(Engineer).filter(Engineer.engineer_id == engineer_id).first()
    if not eng:
        raise HTTPException(status_code=404, detail="Engineer not found")

    # Check engineer is in this team
    member = db.query(TeamMember).filter(
        TeamMember.team_id == team.id,
        TeamMember.user_id == eng.user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=400, detail="Engineer is not a member of your team")

    old_engineer_id = ticket.engineer_id
    ticket.engineer_id = eng.user_id
    if ticket.status == TicketStatus.OPEN:
        ticket.status = TicketStatus.IN_PROGRESS

    # Update workload counts
    if old_engineer_id:
        old_eng = db.query(Engineer).filter(Engineer.user_id == old_engineer_id).first()
        if old_eng:
            old_eng.active_ticket_count = max(0, old_eng.active_ticket_count - 1)

    eng.active_ticket_count += 1
    db.commit()
    return {"message": f"Ticket assigned to {eng.engineer_id}"}


# ── Member availability update ────────────────────────────────────────────────

@router.patch("/members/{engineer_id}/availability")
def update_member_availability(
    engineer_id: str,
    body: dict,
    db: Session = Depends(get_db),
    manager: User = Depends(get_manager),
):
    team = _get_manager_team(db, manager)
    eng = db.query(Engineer).filter(Engineer.engineer_id == engineer_id).first()
    if not eng:
        raise HTTPException(status_code=404, detail="Engineer not found")

    member = db.query(TeamMember).filter(
        TeamMember.team_id == team.id,
        TeamMember.user_id == eng.user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=400, detail="Engineer is not in your team")

    from app.models.engineer import AvailabilityStatus
    status = body.get("status", "available")
    eng.availability_status = AvailabilityStatus(status)
    db.commit()
    return {"message": f"Availability updated to {status}"}