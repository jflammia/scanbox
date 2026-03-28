"""Batch management and scanning trigger endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from scanbox.config import Config
from scanbox.main import get_db
from scanbox.pipeline.output import write_archive, write_medical_records

router = APIRouter(tags=["batches"])


@router.post("/api/sessions/{session_id}/batches", status_code=201)
async def create_batch(session_id: str):
    db = get_db()
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    batch = await db.create_batch(session_id)
    return batch


@router.get("/api/sessions/{session_id}/batches")
async def list_batches(session_id: str):
    db = get_db()
    batches = await db.list_batches(session_id)
    return {"items": batches}


@router.get("/api/batches/{batch_id}")
async def get_batch(batch_id: str):
    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.post("/api/batches/{batch_id}/skip-backs")
async def skip_backs(batch_id: str):
    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch["state"] != "fronts_done":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot skip backs in state '{batch['state']}'. Must be 'fronts_done'.",
        )
    updated = await db.update_batch_state(batch_id, "backs_skipped")
    return updated


@router.post("/api/batches/{batch_id}/scan/fronts", status_code=202)
async def scan_fronts(batch_id: str):
    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    cfg = Config()
    if not cfg.SCANNER_IP:
        raise HTTPException(status_code=503, detail="No scanner configured. Set SCANNER_IP.")

    if batch["state"] != "scanning_fronts":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot scan fronts in state '{batch['state']}'.",
        )

    return {
        "status": "scanning",
        "message": "Scanning front pages...",
        "progress_url": f"/api/batches/{batch_id}/progress",
    }


@router.post("/api/batches/{batch_id}/scan/backs", status_code=202)
async def scan_backs(batch_id: str):
    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    cfg = Config()
    if not cfg.SCANNER_IP:
        raise HTTPException(status_code=503, detail="No scanner configured. Set SCANNER_IP.")

    if batch["state"] != "fronts_done":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot scan backs in state '{batch['state']}'.",
        )

    return {
        "status": "scanning",
        "message": "Scanning back pages...",
        "progress_url": f"/api/batches/{batch_id}/progress",
    }


@router.post("/api/batches/{batch_id}/save")
async def save_batch(batch_id: str):
    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if batch["state"] != "review":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot save in state '{batch['state']}'. Must be 'review'.",
        )

    session = await db.get_session(batch["session_id"])
    person = await db.get_person(session["person_id"])

    cfg = Config()
    scan_date = datetime.now(UTC).strftime("%Y-%m-%d")

    # Locate batch files on disk
    batch_dir = cfg.INTERNAL_DATA_DIR / "sessions" / session["id"] / "batches" / batch_id
    combined_pdf = batch_dir / "combined.pdf"
    docs_dir = batch_dir / "documents"

    # Write archive copy
    archive_path = write_archive(
        combined_pdf=combined_pdf,
        archive_dir=cfg.archive_dir,
        person_slug=person["slug"],
        scan_date=scan_date,
        batch_num=batch["batch_num"],
    )

    # Write each document to medical records
    documents = await db.list_documents(batch_id)
    medical_records = []
    for doc in documents:
        doc_pdf = docs_dir / doc["filename"]
        if doc_pdf.exists():
            dest = write_medical_records(
                doc_pdf=doc_pdf,
                records_dir=cfg.medical_records_dir,
                person_folder=person["folder_name"],
                document_type=doc["document_type"],
                filename=doc["filename"],
            )
            medical_records.append(str(dest))

    await db.update_batch_state(batch_id, "saved")

    return {
        "status": "saved",
        "archive_path": str(archive_path),
        "medical_records": medical_records,
    }
