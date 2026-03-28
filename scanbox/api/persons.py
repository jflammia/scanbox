"""Person profile CRUD endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from scanbox.main import get_db

router = APIRouter(prefix="/api/persons", tags=["persons"])


class CreatePersonRequest(BaseModel):
    display_name: str


class UpdatePersonRequest(BaseModel):
    display_name: str


@router.get("")
async def list_persons():
    """List all person profiles."""
    db = get_db()
    persons = await db.list_persons()
    return {"items": persons}


@router.post("", status_code=201)
async def create_person(req: CreatePersonRequest):
    """Create a new person profile."""
    db = get_db()
    person = await db.create_person(req.display_name)
    return person


@router.get("/{person_id}")
async def get_person(person_id: str):
    """Get a person profile by ID."""
    db = get_db()
    person = await db.get_person(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


@router.put("/{person_id}")
async def update_person(person_id: str, req: UpdatePersonRequest):
    """Update a person's display name."""
    db = get_db()
    person = await db.get_person(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    updated = await db.update_person(person_id, req.display_name)
    return updated


@router.delete("/{person_id}", status_code=204)
async def delete_person(person_id: str):
    """Delete a person profile. Fails if the person has existing sessions."""
    db = get_db()
    person = await db.get_person(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    deleted = await db.delete_person(person_id)
    if not deleted:
        raise HTTPException(status_code=409, detail="Person has sessions and cannot be deleted")
