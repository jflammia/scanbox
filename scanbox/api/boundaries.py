"""Document boundary editor endpoints."""

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from scanbox.config import Config
from scanbox.main import get_db
from scanbox.pipeline.namer import generate_filename
from scanbox.pipeline.splitter import classify_document_pages

logger = logging.getLogger(__name__)

router = APIRouter(tags=["boundaries"])


class SplitRange(BaseModel):
    start_page: int
    end_page: int


class UpdateBoundariesRequest(BaseModel):
    boundaries: list[SplitRange]


@router.get("/api/batches/{batch_id}/boundaries")
async def get_boundaries(batch_id: str):
    """Get current document split boundaries for a batch."""
    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    documents = await db.list_documents(batch_id)
    total_pages = max((d["end_page"] for d in documents), default=0)

    boundaries = [
        {
            "start_page": d["start_page"],
            "end_page": d["end_page"],
            "document_type": d["document_type"],
            "document_id": d["id"],
        }
        for d in documents
    ]
    return {"boundaries": boundaries, "total_pages": total_pages}


@router.put("/api/batches/{batch_id}/boundaries")
async def update_boundaries(batch_id: str, req: UpdateBoundariesRequest):
    """Replace document split boundaries, re-run AI naming, and regenerate documents."""
    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if batch["state"] != "review":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot edit splits in state '{batch['state']}'. Must be 'review'.",
        )

    # Look up person name and batch dir for OCR text
    session = await db.get_session(batch["session_id"])
    person = await db.get_person(session["person_id"])
    person_name = person["display_name"]

    cfg = Config()
    batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch_id
    text_json_path = batch_dir / "text_by_page.json"

    # Load OCR text for AI classification
    page_texts = {}
    if text_json_path.exists():
        raw = json.loads(text_json_path.read_text())
        page_texts = {int(k): v for k, v in raw.items()}

    # Delete existing documents and create new ones from the splits
    await db.delete_documents_by_batch(batch_id)

    new_docs = []
    for split in req.boundaries:
        # Try AI classification if OCR text is available
        doc_type = "Other"
        date_of_service = "unknown"
        facility = "unknown"
        provider = "unknown"
        description = "Document"
        confidence = 0.5

        if page_texts:
            doc_pages = {
                p: page_texts[p]
                for p in range(split.start_page, split.end_page + 1)
                if p in page_texts
            }
            if doc_pages:
                try:
                    metadata = await classify_document_pages(doc_pages, person_name)
                    doc_type = metadata["document_type"]
                    date_of_service = metadata["date_of_service"]
                    facility = metadata["facility"]
                    provider = metadata["provider"]
                    description = metadata["description"]
                    confidence = metadata["confidence"]
                except Exception:
                    logger.warning(
                        "AI classification failed for pages %d-%d, using defaults",
                        split.start_page,
                        split.end_page,
                        exc_info=True,
                    )

        filename = generate_filename(
            person_name=person_name,
            document_type=doc_type,
            date_of_service=date_of_service,
            facility=facility,
            description=description,
        )
        doc = await db.create_document(
            batch_id=batch_id,
            start_page=split.start_page,
            end_page=split.end_page,
            document_type=doc_type,
            date_of_service=date_of_service,
            facility=facility,
            provider=provider,
            description=description,
            confidence=confidence,
            filename=filename,
        )
        new_docs.append(doc)

    return {"documents": new_docs}
