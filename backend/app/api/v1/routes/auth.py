# File: backend/app/api/v1/routes/auth.py

from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import invalidate_token
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest, LoginRequest, LoginResponse,
    RefreshRequest, RefreshResponse, ActivateEngineerRequest,
    UserResponse, ForgotPasswordRequest,
)
from app.services.auth_service import (
    register_user, login_user, refresh_access_token,
    forgot_password, activate_engineer_with_credentials,
)
from app.api.v1.middleware.rate_limiter import auth_limiter

router = APIRouter(prefix="/auth", tags=["Auth"])

# Optional bearer — allows logout to work with or without a token header
_optional_bearer = HTTPBearer(auto_error=False)


@router.post("/register", response_model=UserResponse, status_code=201)
def register(
    data: UserRegisterRequest,
    db: Session = Depends(get_db),
    _: None = Depends(auth_limiter),
):
    return register_user(db, data)


@router.post("/login", response_model=LoginResponse)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
    _: None = Depends(auth_limiter),
):
    return login_user(db, data)


@router.post("/refresh", response_model=RefreshResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    return refresh_access_token(db, data.refresh_token)


@router.post("/forgot-password")
def forgot_pwd(
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    _: None = Depends(auth_limiter),
):
    return forgot_password(db, data)


@router.post("/activate-engineer")
def activate(
    data: ActivateEngineerRequest,
    db: Session = Depends(get_db),
    _: None = Depends(auth_limiter),
):
    return activate_engineer_with_credentials(db, data.email, data.temp_password, data.new_password)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
def logout(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
):
    if credentials:
        invalidate_token(credentials.credentials)
    return {"message": "Logged out successfully"}
