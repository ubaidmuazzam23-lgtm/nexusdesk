# File: backend/app/api/v1/routes/admin.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.user import User, UserRole
from app.schemas.admin import (
    CreateEngineerRequest, UpdateEngineerRequest,
    EngineerResponse, PlatformOverviewResponse, AdminTicketResponse,
)
from app.services.admin_service import (
    create_engineer, list_engineers, get_engineer,
    update_engineer, deactivate_engineer, reactivate_engineer,
    get_platform_overview, list_all_tickets,
)
from app.api.v1.middleware.rate_limiter import admin_limiter

router = APIRouter(prefix="/admin", tags=["Admin"])


def get_admin(current_user: User = Depends(require_role(UserRole.ADMIN))) -> User:
    return current_user


@router.get("/overview", response_model=PlatformOverviewResponse)
def overview(db: Session = Depends(get_db), admin: User = Depends(get_admin)):
    return get_platform_overview(db)


@router.post("/engineers", response_model=EngineerResponse, status_code=201)
def create_eng(
    data: CreateEngineerRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
    _: None = Depends(admin_limiter),
):
    return create_engineer(db, data, admin)


@router.get("/engineers", response_model=List[EngineerResponse])
def list_engs(
    region: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return list_engineers(db, region, status, search)


@router.get("/engineers/{engineer_id}", response_model=EngineerResponse)
def get_eng(engineer_id: str, db: Session = Depends(get_db), admin: User = Depends(get_admin)):
    return get_engineer(db, engineer_id)


@router.patch("/engineers/{engineer_id}", response_model=EngineerResponse)
def update_eng(
    engineer_id: str,
    data: UpdateEngineerRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
    _: None = Depends(admin_limiter),
):
    return update_engineer(db, engineer_id, data, admin)


@router.delete("/engineers/{engineer_id}")
def deactivate_eng(
    engineer_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
    _: None = Depends(admin_limiter),
):
    return deactivate_engineer(db, engineer_id, admin)


@router.post("/engineers/{engineer_id}/reactivate")
def reactivate_eng(
    engineer_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
    _: None = Depends(admin_limiter),
):
    return reactivate_engineer(db, engineer_id, admin)


@router.get("/tickets", response_model=List[AdminTicketResponse])
def all_tickets(
    status: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    return list_all_tickets(db, status, domain, priority, search)
