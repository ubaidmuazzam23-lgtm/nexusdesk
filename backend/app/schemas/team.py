# Location: ./backend/app/schemas/team.py

from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
import uuid

from app.models.team import TeamMemberRole

VALID_DOMAINS = [
    "networking", "hardware", "software", "security",
    "email_communication", "identity_access", "database",
    "cloud", "infrastructure", "devops", "erp_business_apps",
    "endpoint_management",
]

VALID_REGIONS = ["India", "Europe", "US", "Asia Pacific", "Middle East", "Africa"]


# ── Team ──────────────────────────────────────────────────────────────────────

class CreateTeamRequest(BaseModel):
    name: str
    description: Optional[str] = None
    domain_focus: List[str]
    region: str
    timezone: str
    manager_id: Optional[str] = None
    max_ticket_capacity: int = 20

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Team name must be at least 2 characters")
        return v.strip()

    @field_validator("domain_focus")
    @classmethod
    def validate_domains(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one domain is required")
        return v

    @field_validator("max_ticket_capacity")
    @classmethod
    def validate_capacity(cls, v: int) -> int:
        if v < 1 or v > 200:
            raise ValueError("Capacity must be between 1 and 200")
        return v


class UpdateTeamRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    domain_focus: Optional[List[str]] = None
    region: Optional[str] = None
    timezone: Optional[str] = None
    manager_id: Optional[str] = None
    max_ticket_capacity: Optional[int] = None
    is_active: Optional[bool] = None


class TeamMemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str
    engineer_id: Optional[str] = None
    role_in_team: TeamMemberRole
    domain_expertise: List[str] = []
    availability_status: Optional[str] = None
    active_ticket_count: int = 0
    joined_at: datetime

    class Config:
        from_attributes = True


class TeamResponse(BaseModel):
    id: uuid.UUID
    team_id: str
    name: str
    description: Optional[str]
    domain_focus: List[str]
    region: str
    timezone: str
    manager_id: Optional[uuid.UUID]
    manager_name: Optional[str]
    manager_email: Optional[str]
    is_active: bool
    max_ticket_capacity: int
    active_ticket_count: int
    total_resolved: int
    avg_resolution_time: int
    sla_compliance_rate: int
    member_count: int
    members: List[TeamMemberResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True


# ── Team Member Management ─────────────────────────────────────────────────────

class AddMemberRequest(BaseModel):
    engineer_id: str  # ENG-XXXX
    role_in_team: TeamMemberRole = TeamMemberRole.MEMBER


class RemoveMemberRequest(BaseModel):
    engineer_id: str  # ENG-XXXX


class UpdateMemberRoleRequest(BaseModel):
    engineer_id: str
    role_in_team: TeamMemberRole


# ── Manager ───────────────────────────────────────────────────────────────────

class CreateManagerRequest(BaseModel):
    full_name: str
    email: str
    timezone: str = "UTC"
    city: Optional[str] = None
    country: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Full name must be at least 2 characters")
        return v.strip()


class ManagerResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    is_active: bool
    city: Optional[str]
    country: Optional[str]
    timezone: Optional[str]
    created_at: datetime
    teams: List[str] = []  # list of team_ids managed

    class Config:
        from_attributes = True