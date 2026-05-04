# File: backend/app/models/ticket.py

from sqlalchemy import Column, JSON, String, Boolean, DateTime, Enum, Integer, Text, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.core.database import Base


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketDomain(str, enum.Enum):
    NETWORKING          = "networking"
    HARDWARE            = "hardware"
    SOFTWARE            = "software"
    SECURITY            = "security"
    EMAIL_COMMUNICATION = "email_communication"
    IDENTITY_ACCESS     = "identity_access"
    DATABASE            = "database"
    CLOUD               = "cloud"
    INFRASTRUCTURE      = "infrastructure"
    DEVOPS              = "devops"
    ERP_BUSINESS_APPS   = "erp_business_apps"
    ENDPOINT_MANAGEMENT = "endpoint_management"
    OTHER               = "other"


class TicketComplexity(str, enum.Enum):
    SIMPLE   = "simple"
    MODERATE = "moderate"
    COMPLEX  = "complex"


class Ticket(Base):
    __tablename__ = "tickets"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_number  = Column(String, unique=True, nullable=False)

    user_id        = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    engineer_id    = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    title          = Column(String, nullable=False)
    description    = Column(Text, nullable=False)
    domain         = Column(Enum(TicketDomain, values_callable=lambda x: [e.value for e in x]), nullable=False, default=TicketDomain.OTHER)
    priority       = Column(Enum(TicketPriority), nullable=False, default=TicketPriority.MEDIUM)
    status         = Column(Enum(TicketStatus), nullable=False, default=TicketStatus.OPEN)
    complexity         = Column(Enum(TicketComplexity), nullable=True)
    model_predictions  = Column(JSON, nullable=True)

    ai_diagnosis       = Column(Text, nullable=True)
    ai_confidence      = Column(Float, nullable=True)
    ai_attempted       = Column(Boolean, default=False)
    ai_resolved        = Column(Boolean, default=False)
    cnn_image_result   = Column(String, nullable=True)
    steps_tried        = Column(Text, nullable=True)

    resolution_notes   = Column(Text, nullable=True)
    resolved_at        = Column(DateTime, nullable=True)

    sla_deadline       = Column(DateTime, nullable=True)
    sla_breached       = Column(Boolean, default=False)

    user_city          = Column(String, nullable=True)
    user_country       = Column(String, nullable=True)
    user_timezone      = Column(String, nullable=True)

    created_at         = Column(DateTime, default=datetime.utcnow)
    updated_at         = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user               = relationship("User", foreign_keys=[user_id])
    engineer           = relationship("User", foreign_keys=[engineer_id])
    messages           = relationship("TicketMessage", back_populates="ticket", cascade="all, delete-orphan")


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id  = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)
    sender_id  = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    message    = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket     = relationship("Ticket", back_populates="messages")
    sender     = relationship("User", foreign_keys=[sender_id])