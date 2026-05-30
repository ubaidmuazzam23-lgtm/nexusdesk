# Location: ./backend/app/schemas/auth.py

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
import uuid
from app.models.user import UserRole


class UserRegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    city: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = "UTC"

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8: raise ValueError('Password must be at least 8 characters')
        if not any(c.isupper() for c in v): raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.isdigit() for c in v): raise ValueError('Password must contain at least one number')
        return v

    @field_validator('full_name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v.strip()) < 2: raise ValueError('Full name must be at least 2 characters')
        return v.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: UserRole
    full_name: str
    email: str
    user_id: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ActivateEngineerRequest(BaseModel):
    email: EmailStr
    temp_password: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8: raise ValueError('Password must be at least 8 characters')
        if not any(c.isupper() for c in v): raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.isdigit() for c in v): raise ValueError('Password must contain at least one number')
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8: raise ValueError('Password must be at least 8 characters')
        if not any(c.isupper() for c in v): raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.isdigit() for c in v): raise ValueError('Password must contain at least one number')
        return v


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    city: Optional[str]
    country: Optional[str]
    timezone: Optional[str]

    class Config:
        from_attributes = True