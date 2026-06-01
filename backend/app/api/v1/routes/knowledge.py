# File: backend/app/api/v1/routes/knowledge.py

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.core.dependencies import require_role, get_current_user
from app.models.user import User, UserRole
from app.services.knowledge_service import (
    upload_document, search_knowledge, list_documents,
    delete_document, get_similar_docs_for_ticket,
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


def admin_or_engineer(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in [UserRole.ADMIN, UserRole.ENGINEER]:
        raise HTTPException(status_code=403, detail="Admin or Engineer access required")
    return current_user


class SearchRequest(BaseModel):
    query: str
    n_results: int = 5
    domain: Optional[str] = None


ALLOWED_EXTENSIONS = (".pdf", ".txt", ".md", ".docx")
ALLOWED_TYPES = [
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
]


@router.post("/upload")
async def upload_doc(
    file: UploadFile = File(...),
    title: str = Form(...),
    domain: str = Form("other"),
    description: str = Form(""),
    current_user: User = Depends(admin_or_engineer),
):
    if not (any(file.filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS) or
            file.content_type in ALLOWED_TYPES):
        raise HTTPException(status_code=400, detail="Only PDF, TXT, MD, DOCX files accepted")
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 20MB.")
    return upload_document(
        content=contents,
        filename=file.filename,
        title=title,
        domain=domain,
        description=description,
        uploaded_by=str(current_user.id),
        uploaded_by_role=current_user.role.value,
    )


@router.post("/search")
def search_docs(data: SearchRequest, current_user: User = Depends(get_current_user)):
    return search_knowledge(query=data.query, n_results=data.n_results, domain=data.domain)


@router.get("/documents")
def get_documents(domain: Optional[str] = None, current_user: User = Depends(get_current_user)):
    return list_documents(domain=domain)


@router.delete("/documents/{doc_id}")
def delete_doc(doc_id: str, current_user: User = Depends(admin_or_engineer)):
    if not delete_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document deleted"}


@router.get("/ticket-similarity/{ticket_id}")
def ticket_similarity(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_or_engineer),
):
    from app.models.ticket import Ticket
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    domain = ticket.domain.value if hasattr(ticket.domain, "value") else str(ticket.domain)
    query  = " ".join(filter(None, [ticket.title, ticket.description, ticket.steps_tried]))
    return get_similar_docs_for_ticket(query=query, domain=domain, n_results=5)