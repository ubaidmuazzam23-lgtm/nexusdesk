# Location: ./backend/app/models/team.py

from sqlalchemy import Column, String, Boolean, DateTime, Enum, Integer, ARRAY, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.core.database import Base


class TeamMemberRole(str, enum.Enum):
    LEAD   = "lead"
    MEMBER = "member"


class Team(Base):
    __tablename__ = "teams"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id             = Column(String, unique=True, nullable=False)
    name                = Column(String, nullable=False)
    description         = Column(String, nullable=True)
    domain_focus        = Column(ARRAY(String), nullable=False, default=[])
    region              = Column(String, nullable=False)
    timezone            = Column(String, nullable=False, default="UTC")
    manager_id          = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_active           = Column(Boolean, default=True)
    max_ticket_capacity = Column(Integer, default=20)
    active_ticket_count = Column(Integer, default=0)
    total_resolved      = Column(Integer, default=0)
    avg_resolution_time = Column(Integer, default=0)
    sla_compliance_rate = Column(Integer, default=100)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    manager             = relationship("User", foreign_keys=[manager_id])
    members             = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Team {self.team_id} — {self.name}>"


class TeamMember(Base):
    __tablename__ = "team_members"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id      = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    user_id      = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_in_team = Column(Enum(TeamMemberRole), default=TeamMemberRole.MEMBER)
    joined_at    = Column(DateTime, default=datetime.utcnow)

    team         = relationship("Team", back_populates="members")
    user         = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_member"),
    )

    def __repr__(self):
        return f"<TeamMember team={self.team_id} user={self.user_id}>"


class TeamMessage(Base):
    __tablename__ = "team_messages"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id    = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    sender_id  = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    message    = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    team   = relationship("Team", foreign_keys=[team_id])
    sender = relationship("User", foreign_keys=[sender_id])

    def __repr__(self):
        return f"<TeamMessage team={self.team_id} sender={self.sender_id}>"