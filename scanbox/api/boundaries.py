"""Document boundary editor endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from scanbox.main import get_db
from scanbox.pipeline.namer import generate_filename

router = APIRouter(tags=["boundaries"])


class SplitRange(BaseModel):
    start_page: int
    end_page: int


class UpdateSplitsRequest(BaseModel):
    splits: list[SplitRange]


@router.get("/api/batches/{batch_id}/splits")
async def get_splits(batch_id: str):
    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    documents = await db.list_documents(batch_id)
    total_pages = max((d["end_page"] for d in documents), default=0)

    splits = [
        {
            "start_page": d["start_page"],
            "end_page": d["end_page"],
            "document_type": d["document_type"],
            "document_id": d["id"],
        }
        for d in documents
    ]
    return {"splits": splits, "total_pages": total_pages}


@router.post("/api/batches/{batch_id}/splits")
async def update_splits(batch_id: str, req: UpdateSplitsRequest):
    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if batch["state"] != "review":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot edit splits in state '{batch['state']}'. Must be 'review'.",
        )

    # Look up person name for filename generation
    session = await db.get_session(batch["session_id"])
    person = await db.get_person(session["person_id"])
    person_name = person["display_name"]

    # Delete existing documents and create new ones from the splits
    await db.delete_documents_by_batch(batch_id)

    new_docs = []
    for split in req.splits:
        filename = generate_filename(
            person_name=person_name,
            document_type="Other",
            date_of_service="unknown",
        )
        doc = await db.create_document(
            batch_id=batch_id,
            start_page=split.start_page,
            end_page=split.end_page,
            document_type="Other",
            filename=filename,
        )
        new_docs.append(doc)

    return {"documents": new_docs}
