# Location: backend/app/schemas/chat.py

from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
from app.models.ticket import TicketDomain, TicketPriority, TicketStatus


class ChatMessageRequest(BaseModel):
    message:    str
    session_id: Optional[str] = None
    intent:     Optional[str] = "solve"


class ChatMessageResponse(BaseModel):
    session_id:        str
    reply:             str
    intent:            str
    detected_domain:   Optional[str] = None
    detected_severity: Optional[str] = None
    resolved:          bool = False
    can_escalate:      bool = False
    attempt_number:    int  = 1
    context_gathering: bool = False


class ScreenshotUploadResponse(BaseModel):
    success:          bool
    filename:         Optional[str]   = None
    display_text:     Optional[str]   = None
    cnn_label:        Optional[str]   = None
    cnn_confidence:   Optional[float] = None
    cnn_domain:       Optional[str]   = None
    cnn_severity:     Optional[str]   = None
    error:            Optional[str]   = None


class EscalateRequest(BaseModel):
    session_id:  str
    title:       str
    description: str
    domain:      Optional[str] = None
    priority:    TicketPriority
    steps_tried: Optional[str] = None


class EscalateResponse(BaseModel):
    ticket_id:     uuid.UUID
    ticket_number: str
    message:       str
    routing_type:      Optional[str] = None
    routing_reason:    Optional[str] = None
    engineer_name:     Optional[str] = None
    engineer_id:       Optional[str] = None
    engineer_email:    Optional[str] = None
    engineer_city:     Optional[str] = None
    engineer_timezone: Optional[str] = None
    team_name:         Optional[str] = None
    team_id:           Optional[str] = None
    asset_instance:    Optional[str] = None
    asset_environment: Optional[str] = None
    asset_team:        Optional[str] = None


class UserTicketResponse(BaseModel):
    id:                  uuid.UUID
    ticket_number:       str
    title:               str
    domain:              Optional[str]      = None
    priority:            TicketPriority
    status:              TicketStatus
    # Engineer info
    engineer_name:       Optional[str]      = None
    engineer_id:         Optional[str]      = None
    engineer_email:      Optional[str]      = None
    engineer_city:       Optional[str]      = None
    engineer_country:    Optional[str]      = None
    engineer_timezone:   Optional[str]      = None
    # Team info
    team_name:           Optional[str]      = None
    team_id:             Optional[str]      = None
    team_manager_email:  Optional[str]      = None

    created_at:          datetime
    updated_at:          datetime
    resolved_at:         Optional[datetime] = None

    class Config:
        from_attributes = True