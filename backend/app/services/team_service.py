# Location: ./backend/app/services/team_service.py

from sqlalchemy.orm import Session
from fastapi import HTTPException
import secrets
import string
import threading

from app.models.user import User, UserRole
from app.models.engineer import Engineer
from app.models.team import Team, TeamMember, TeamMemberRole
from app.core.security import hash_password
from app.schemas.team import (
    CreateTeamRequest, UpdateTeamRequest,
    CreateManagerRequest, AddMemberRequest,
    TeamResponse, TeamMemberResponse,
    ManagerResponse,
)
from app.services.email_service import send_engineer_credentials_email


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_team_id(db: Session) -> str:
    while True:
        tid = f"TM-{secrets.randbelow(9000) + 1000}"
        if not db.query(Team).filter(Team.team_id == tid).first():
            return tid


def _generate_temp_password(length: int = 10) -> str:
    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits
    pwd = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(string.ascii_uppercase),
    ]
    pwd += [secrets.choice(chars) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)


def _team_to_response(db: Session, team: Team) -> TeamResponse:
    manager_name = None
    manager_email = None
    if team.manager_id:
        mgr = db.query(User).filter(User.id == team.manager_id).first()
        if mgr:
            manager_name = mgr.full_name
            manager_email = mgr.email

    members = []
    for tm in team.members:
        usr = db.query(User).filter(User.id == tm.user_id).first()
        eng = db.query(Engineer).filter(Engineer.user_id == tm.user_id).first()
        if usr:
            members.append(TeamMemberResponse(
                id=tm.id,
                user_id=tm.user_id,
                full_name=usr.full_name,
                email=usr.email,
                engineer_id=eng.engineer_id if eng else None,
                role_in_team=tm.role_in_team,
                domain_expertise=eng.domain_expertise if eng else [],
                availability_status=eng.availability_status.value if eng else None,
                active_ticket_count=eng.active_ticket_count if eng else 0,
                joined_at=tm.joined_at,
            ))

    return TeamResponse(
        id=team.id,
        team_id=team.team_id,
        name=team.name,
        description=team.description,
        domain_focus=team.domain_focus or [],
        region=team.region,
        timezone=team.timezone,
        manager_id=team.manager_id,
        manager_name=manager_name,
        manager_email=manager_email,
        is_active=team.is_active,
        max_ticket_capacity=team.max_ticket_capacity,
        active_ticket_count=team.active_ticket_count,
        total_resolved=team.total_resolved,
        avg_resolution_time=team.avg_resolution_time,
        sla_compliance_rate=team.sla_compliance_rate,
        member_count=len(members),
        members=members,
        created_at=team.created_at,
    )


# ── Team CRUD ─────────────────────────────────────────────────────────────────

def create_team(db: Session, data: CreateTeamRequest) -> TeamResponse:
    # Validate manager if provided
    if data.manager_id:
        mgr = db.query(User).filter(User.id == data.manager_id).first()
        if not mgr:
            raise HTTPException(status_code=404, detail="Manager user not found")
        if mgr.role != UserRole.MANAGER:
            raise HTTPException(status_code=400, detail="Assigned user is not a manager")

    team_id = _generate_team_id(db)
    team = Team(
        team_id=team_id,
        name=data.name,
        description=data.description,
        domain_focus=data.domain_focus,
        region=data.region,
        timezone=data.timezone,
        manager_id=data.manager_id if data.manager_id else None,
        max_ticket_capacity=data.max_ticket_capacity,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return _team_to_response(db, team)


def list_teams(
    db: Session,
    region: str = None,
    status: str = None,
    search: str = None,
) -> list:
    query = db.query(Team)
    if region:
        query = query.filter(Team.region == region)
    if status == "active":
        query = query.filter(Team.is_active == True)
    elif status == "inactive":
        query = query.filter(Team.is_active == False)
    if search:
        s = f"%{search.lower()}%"
        query = query.filter(
            (Team.name.ilike(s)) | (Team.team_id.ilike(s)) | (Team.region.ilike(s))
        )
    teams = query.order_by(Team.created_at.desc()).all()
    return [_team_to_response(db, t) for t in teams]


def get_team(db: Session, team_id: str) -> TeamResponse:
    team = db.query(Team).filter(Team.team_id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return _team_to_response(db, team)


def update_team(db: Session, team_id: str, data: UpdateTeamRequest) -> TeamResponse:
    team = db.query(Team).filter(Team.team_id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if data.name is not None:
        team.name = data.name
    if data.description is not None:
        team.description = data.description
    if data.domain_focus is not None:
        team.domain_focus = data.domain_focus
    if data.region is not None:
        team.region = data.region
    if data.timezone is not None:
        team.timezone = data.timezone
    if data.max_ticket_capacity is not None:
        team.max_ticket_capacity = data.max_ticket_capacity
    if data.is_active is not None:
        team.is_active = data.is_active
    if data.manager_id is not None:
        mgr = db.query(User).filter(User.id == data.manager_id).first()
        if not mgr or mgr.role != UserRole.MANAGER:
            raise HTTPException(status_code=400, detail="Invalid manager")
        team.manager_id = data.manager_id

    db.commit()
    db.refresh(team)
    return _team_to_response(db, team)


def deactivate_team(db: Session, team_id: str) -> dict:
    team = db.query(Team).filter(Team.team_id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if not team.is_active:
        raise HTTPException(status_code=400, detail="Team is already inactive")
    team.is_active = False
    db.commit()
    return {"message": f"Team {team_id} deactivated"}


def reactivate_team(db: Session, team_id: str) -> dict:
    team = db.query(Team).filter(Team.team_id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.is_active:
        raise HTTPException(status_code=400, detail="Team is already active")
    team.is_active = True
    db.commit()
    return {"message": f"Team {team_id} reactivated"}


# ── Member Management ─────────────────────────────────────────────────────────

def add_member(db: Session, team_id: str, data: AddMemberRequest) -> TeamResponse:
    team = db.query(Team).filter(Team.team_id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    eng = db.query(Engineer).filter(Engineer.engineer_id == data.engineer_id).first()
    if not eng:
        raise HTTPException(status_code=404, detail="Engineer not found")
    if not eng.is_activated:
        raise HTTPException(status_code=400, detail="Engineer account is not activated yet")

    # Check already in team
    existing = db.query(TeamMember).filter(
        TeamMember.team_id == team.id,
        TeamMember.user_id == eng.user_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Engineer is already in this team")

    member = TeamMember(
        team_id=team.id,
        user_id=eng.user_id,
        role_in_team=data.role_in_team,
    )
    db.add(member)
    db.commit()
    db.refresh(team)
    return _team_to_response(db, team)


def remove_member(db: Session, team_id: str, engineer_id: str) -> TeamResponse:
    team = db.query(Team).filter(Team.team_id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    eng = db.query(Engineer).filter(Engineer.engineer_id == engineer_id).first()
    if not eng:
        raise HTTPException(status_code=404, detail="Engineer not found")

    member = db.query(TeamMember).filter(
        TeamMember.team_id == team.id,
        TeamMember.user_id == eng.user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Engineer is not in this team")

    db.delete(member)
    db.commit()
    db.refresh(team)
    return _team_to_response(db, team)


def get_team_members(db: Session, team_id: str) -> list:
    team = db.query(Team).filter(Team.team_id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return _team_to_response(db, team).members


# ── Manager CRUD ──────────────────────────────────────────────────────────────

def create_manager(db: Session, data: CreateManagerRequest, admin_user: User) -> ManagerResponse:
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    temp_password = _generate_temp_password()
    user = User(
        email=data.email,
        hashed_password=hash_password(temp_password),
        full_name=data.full_name,
        role=UserRole.MANAGER,
        is_active=True,
        is_verified=False,
        timezone=data.timezone,
        city=data.city,
        country=data.country,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Send credentials email (reuse engineer email template)
    threading.Thread(
        target=send_engineer_credentials_email,
        args=(user.email, user.full_name, "MANAGER", temp_password),
        daemon=True,
    ).start()

    return _manager_to_response(db, user)


def list_managers(db: Session) -> list:
    managers = db.query(User).filter(User.role == UserRole.MANAGER).all()
    return [_manager_to_response(db, m) for m in managers]


def deactivate_manager(db: Session, manager_id: str) -> dict:
    user = db.query(User).filter(User.id == manager_id, User.role == UserRole.MANAGER).first()
    if not user:
        raise HTTPException(status_code=404, detail="Manager not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Manager is already deactivated")
    user.is_active = False
    db.commit()
    return {"message": f"Manager {user.full_name} deactivated"}


def reactivate_manager(db: Session, manager_id: str) -> dict:
    user = db.query(User).filter(User.id == manager_id, User.role == UserRole.MANAGER).first()
    if not user:
        raise HTTPException(status_code=404, detail="Manager not found")
    if user.is_active:
        raise HTTPException(status_code=400, detail="Manager is already active")
    user.is_active = True
    db.commit()
    return {"message": f"Manager {user.full_name} reactivated"}


def _manager_to_response(db: Session, user: User) -> ManagerResponse:
    # Get teams this manager manages
    teams = db.query(Team).filter(Team.manager_id == user.id).all()
    team_ids = [t.team_id for t in teams]

    return ManagerResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        is_active=user.is_active,
        city=user.city,
        country=user.country,
        timezone=user.timezone,
        created_at=user.created_at,
        teams=team_ids,
    )