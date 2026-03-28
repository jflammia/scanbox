"""Document listing, retrieval, and metadata editing endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from scanbox.main import get_db

router = APIRouter(tags=["documents"])


class UpdateDocumentRequest(BaseModel):
    document_type: str | None = None
    date_of_service: str | None = None
    facility: str | None = None
    provider: str | None = None
    description: str | None = None


@router.get("/api/batches/{batch_id}/documents")
async def list_documents(batch_id: str):
    """List all documents in a batch."""
    db = get_db()
    docs = await db.list_documents(batch_id)
    return {"items": docs}


@router.get("/api/documents/{document_id}")
async def get_document(document_id: str):
    """Get document metadata by ID."""
    db = get_db()
    doc = await db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.put("/api/documents/{document_id}")
async def update_document(document_id: str, req: UpdateDocumentRequest):
    """Update document metadata (type, date, provider, etc.)."""
    db = get_db()
    doc = await db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if updates:
        updates["user_edited"] = True
    updated = await db.update_document(document_id, **updates)
    return updated
