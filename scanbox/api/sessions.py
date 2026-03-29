"""Session management endpoints."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from scanbox.main import get_db

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    person_id: str


@router.get("")
async def list_sessions(person_id: str | None = Query(None)):
    """List scanning sessions with person name, batch count, and document count."""
    db = get_db()
    sessions = await db.list_sessions(person_id=person_id)
    enriched = []
    for s in sessions:
        person = await db.get_person(s["person_id"])
        batches = await db.list_batches(s["id"])
        doc_count = 0
        for b in batches:
            docs = await db.list_documents(b["id"])
            doc_count += len(docs)
        enriched.append(
            {
                **s,
                "person_name": person["display_name"] if person else "Unknown",
                "batch_count": len(batches),
                "document_count": doc_count,
            }
        )
    return {"items": enriched}


@router.post("", status_code=201)
async def create_session(req: CreateSessionRequest):
    """Start a new scanning session for a person."""
    db = get_db()
    person = await db.get_person(req.person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    session = await db.create_session(req.person_id)
    return session


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get a scanning session with batches and person name."""
    db = get_db()
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    person = await db.get_person(session["person_id"])
    batches = await db.list_batches(session_id)
    return {
        **session,
        "person_name": person["display_name"] if person else "Unknown",
        "batches": batches,
    }
