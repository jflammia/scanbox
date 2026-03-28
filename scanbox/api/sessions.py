"""Session management endpoints."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from scanbox.main import get_db

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    person_id: str


@router.get("")
async def list_sessions(person_id: str | None = Query(None)):
    db = get_db()
    sessions = await db.list_sessions(person_id=person_id)
    return {"items": sessions}


@router.post("", status_code=201)
async def create_session(req: CreateSessionRequest):
    db = get_db()
    person = await db.get_person(req.person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    session = await db.create_session(req.person_id)
    return session


@router.get("/{session_id}")
async def get_session(session_id: str):
    db = get_db()
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
