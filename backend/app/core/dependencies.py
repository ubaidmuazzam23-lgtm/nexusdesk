# Location: ./backend/app/core/dependencies.py

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User, UserRole

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated"
        )

    return user


def require_role(*roles: UserRole):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {[r.value for r in roles]}"
            )
        return current_user
    return role_checker


# ── Role shortcuts ─────────────────────────────────────────────────────────────

def require_user(current_user: User = Depends(get_current_user)) -> User:
    return require_role(UserRole.USER)(current_user)

def require_engineer(current_user: User = Depends(get_current_user)) -> User:
    return require_role(UserRole.ENGINEER)(current_user)

def require_manager(current_user: User = Depends(get_current_user)) -> User:
    return require_role(UserRole.MANAGER)(current_user)

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    return require_role(UserRole.ADMIN)(current_user)

def require_manager_or_admin(current_user: User = Depends(get_current_user)) -> User:
    return require_role(UserRole.MANAGER, UserRole.ADMIN)(current_user)