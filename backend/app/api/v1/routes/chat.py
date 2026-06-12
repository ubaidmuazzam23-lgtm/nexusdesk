# File: backend/app/api/v1/routes/chat.py

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
import os
import re

from app.core.database import get_db
from app.core.dependencies import require_role, get_current_user
from app.models.user import User, UserRole
from app.schemas.chat import (
    ChatMessageRequest, ChatMessageResponse,
    EscalateRequest, EscalateResponse,
    UserTicketResponse, ScreenshotUploadResponse,
)
from app.services.chat_service import (
    process_message, escalate_to_ticket,
    get_user_tickets, get_user_ticket,
    analyze_screenshot, SCREENSHOT_DIR,
)
from app.api.v1.middleware.rate_limiter import chat_limiter, upload_limiter

router = APIRouter(prefix="/chat", tags=["Chat"])


def get_user(current_user: User = Depends(require_role(UserRole.USER))) -> User:
    return current_user


@router.post("/message", response_model=ChatMessageResponse)
def chat_message(
    data: ChatMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user),
    _: None = Depends(chat_limiter),
):
    return process_message(db, user, data)


@router.post("/upload-screenshot", response_model=ScreenshotUploadResponse)
async def upload_screenshot(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_user),
    _: None = Depends(upload_limiter),
):
    """Upload a screenshot — saved to disk + analyzed by CNN."""
    allowed = ["image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"]
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only image files accepted (PNG, JPEG, WEBP)")
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 10MB.")
    result = analyze_screenshot(contents, session_id, str(user.id))
    return ScreenshotUploadResponse(**result)


@router.get("/screenshot/{filename}")
async def get_screenshot(
    filename: str,
    current_user: User = Depends(get_current_user),  # any authenticated user or engineer
):
    """Serve a stored screenshot — accessible by users and engineers."""
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(filepath)


@router.post("/escalate", response_model=EscalateResponse)
def escalate(
    data: EscalateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user),
):
    return escalate_to_ticket(db, user, data)


@router.get("/tickets", response_model=List[UserTicketResponse])
def user_tickets(
    db: Session = Depends(get_db),
    user: User = Depends(get_user),
):
    return get_user_tickets(db, user)


@router.get("/tickets/{ticket_id}", response_model=UserTicketResponse)
def user_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_user),
):
    return get_user_ticket(db, user, ticket_id)