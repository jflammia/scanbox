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
    db = get_db()
    persons = await db.list_persons()
    return {"items": persons}


@router.post("", status_code=201)
async def create_person(req: CreatePersonRequest):
    db = get_db()
    person = await db.create_person(req.display_name)
    return person


@router.get("/{person_id}")
async def get_person(person_id: str):
    db = get_db()
    person = await db.get_person(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


@router.put("/{person_id}")
async def update_person(person_id: str, req: UpdatePersonRequest):
    db = get_db()
    person = await db.get_person(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    updated = await db.update_person(person_id, req.display_name)
    return updated


@router.delete("/{person_id}", status_code=204)
async def delete_person(person_id: str):
    db = get_db()
    person = await db.get_person(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    deleted = await db.delete_person(person_id)
    if not deleted:
        raise HTTPException(status_code=409, detail="Person has sessions and cannot be deleted")
