# Location: ./backend/app/api/v1/routes/teams.py

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List

from app.core.database import get_db
from app.core.dependencies import require_role, get_current_user
from app.models.user import User, UserRole
from app.models.team import Team, TeamMember, TeamMessage
from app.schemas.team import (
    CreateTeamRequest, UpdateTeamRequest,
    AddMemberRequest, TeamResponse,
    TeamMemberResponse, CreateManagerRequest,
    ManagerResponse,
)
from app.services.team_service import (
    create_team, list_teams, get_team,
    update_team, deactivate_team, reactivate_team,
    add_member, remove_member, get_team_members,
    create_manager, list_managers,
    deactivate_manager, reactivate_manager,
)

router = APIRouter(prefix="/teams", tags=["Teams"])


def get_admin(current_user: User = Depends(require_role(UserRole.ADMIN))) -> User:
    return current_user


def get_any_authenticated(current_user: User = Depends(get_current_user)) -> User:
    return current_user


# ── Teams ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=TeamResponse, status_code=201)
def create_new_team(
    data: CreateTeamRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return create_team(db, data)


@router.get("", response_model=List[TeamResponse])
def list_all_teams(
    region: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return list_teams(db, region, status, search)


@router.get("/{team_id}", response_model=TeamResponse)
def get_single_team(
    team_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return get_team(db, team_id)


@router.patch("/{team_id}", response_model=TeamResponse)
def update_existing_team(
    team_id: str,
    data: UpdateTeamRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return update_team(db, team_id, data)


@router.delete("/{team_id}")
def deactivate_existing_team(
    team_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return deactivate_team(db, team_id)


@router.post("/{team_id}/reactivate")
def reactivate_existing_team(
    team_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return reactivate_team(db, team_id)


# ── Members ───────────────────────────────────────────────────────────────────

@router.get("/{team_id}/members", response_model=List[TeamMemberResponse])
def get_members(
    team_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return get_team_members(db, team_id)


@router.post("/{team_id}/members", response_model=TeamResponse)
def add_team_member(
    team_id: str,
    data: AddMemberRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return add_member(db, team_id, data)


@router.delete("/{team_id}/members/{engineer_id}", response_model=TeamResponse)
def remove_team_member(
    team_id: str,
    engineer_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return remove_member(db, team_id, engineer_id)


# ── Chat REST ─────────────────────────────────────────────────────────────────

@router.get("/{team_id}/chat")
def get_chat_history(
    team_id: str,
    limit: int = Query(100, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    team = db.query(Team).filter(Team.team_id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    messages = db.query(TeamMessage).filter(
        TeamMessage.team_id == team.id
    ).order_by(TeamMessage.created_at.asc()).limit(limit).all()

    result = []
    for msg in messages:
        sender = db.query(User).filter(User.id == msg.sender_id).first()
        result.append({
            "id":          str(msg.id),
            "message":     msg.message,
            "sender_id":   str(msg.sender_id),
            "sender_name": sender.full_name if sender else "Unknown",
            "sender_role": sender.role.lower() if sender and isinstance(sender.role, str) else (sender.role.value.lower() if sender else "unknown"),
            "timestamp":   msg.created_at.isoformat(),
        })
    return result


# ── Managers ──────────────────────────────────────────────────────────────────

@router.post("/managers/create", response_model=ManagerResponse, status_code=201)
def create_new_manager(
    data: CreateManagerRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return create_manager(db, data, admin)


@router.get("/managers/list", response_model=List[ManagerResponse])
def list_all_managers(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return list_managers(db)


@router.delete("/managers/{manager_id}")
def deactivate_existing_manager(
    manager_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return deactivate_manager(db, manager_id)


@router.post("/managers/{manager_id}/reactivate")
def reactivate_existing_manager(
    manager_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return reactivate_manager(db, manager_id)