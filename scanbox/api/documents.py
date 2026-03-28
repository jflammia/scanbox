"""Document listing, retrieval, and metadata editing endpoints."""

import json
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from scanbox.config import Config
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


async def _resolve_batch_dir(doc: dict) -> Path:
    """Resolve the batch directory for a document."""
    db = get_db()
    batch = await db.get_batch(doc["batch_id"])
    session = await db.get_session(batch["session_id"])
    cfg = Config()
    return cfg.sessions_dir / session["id"] / "batches" / doc["batch_id"]


@router.get("/api/documents/{document_id}/pdf")
async def get_document_pdf(document_id: str):
    """Download the document PDF file."""
    db = get_db()
    doc = await db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    batch_dir = await _resolve_batch_dir(doc)
    pdf_path = batch_dir / "documents" / doc["filename"]
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Document PDF file not found on disk")

    return FileResponse(pdf_path, media_type="application/pdf", filename=doc["filename"])


@router.get("/api/documents/{document_id}/thumbnail")
async def get_document_thumbnail(document_id: str):
    """Get a JPEG thumbnail of the document's first page."""
    db = get_db()
    doc = await db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    batch_dir = await _resolve_batch_dir(doc)
    pdf_path = batch_dir / "documents" / doc["filename"]
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Document PDF file not found on disk")

    from pdf2image import convert_from_path

    images = convert_from_path(str(pdf_path), first_page=1, last_page=1, dpi=150)
    if not images:
        raise HTTPException(status_code=500, detail="Failed to render page")

    img = images[0]
    # Scale to 300px wide
    ratio = 300 / img.width
    img = img.resize((300, int(img.height * ratio)))

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg")


@router.get("/api/documents/{document_id}/text")
async def get_document_text(document_id: str):
    """Get OCR-extracted text for a document's pages."""
    db = get_db()
    doc = await db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    batch_dir = await _resolve_batch_dir(doc)
    text_path = batch_dir / "text_by_page.json"
    if not text_path.exists():
        raise HTTPException(status_code=404, detail="OCR text not available for this batch")

    text_by_page = json.loads(text_path.read_text())
    pages = []
    for page_num in range(doc["start_page"], doc["end_page"] + 1):
        text = text_by_page.get(str(page_num), "")
        pages.append({"page": page_num, "text": text})

    return {"pages": pages}
