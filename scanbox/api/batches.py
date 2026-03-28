"""Batch management and scanning trigger endpoints."""

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from scanbox.api.scanning import (
    process_after_skip_backs,
    scan_backs_task,
    scan_fronts_task,
)
from scanbox.config import Config
from scanbox.main import get_db
from scanbox.pipeline.output import write_archive, write_medical_records

router = APIRouter(tags=["batches"])


@router.post("/api/sessions/{session_id}/batches", status_code=201)
async def create_batch(session_id: str):
    """Create a new scan batch within a session."""
    db = get_db()
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    batch = await db.create_batch(session_id)
    return batch


@router.get("/api/sessions/{session_id}/batches")
async def list_batches(session_id: str):
    """List all batches in a session."""
    db = get_db()
    batches = await db.list_batches(session_id)
    return {"items": batches}


@router.get("/api/batches/{batch_id}")
async def get_batch(batch_id: str):
    """Get batch details and current state."""
    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.post("/api/batches/{batch_id}/skip-backs")
async def skip_backs(batch_id: str):
    """Skip back-side scanning for single-sided documents."""
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
    asyncio.create_task(process_after_skip_backs(batch_id, db))
    return updated


@router.post("/api/batches/{batch_id}/scan/fronts", status_code=202)
async def scan_fronts(batch_id: str):
    """Start scanning front sides via the ADF scanner."""
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

    asyncio.create_task(scan_fronts_task(batch_id, db))

    return {
        "status": "scanning",
        "message": "Scanning front pages...",
        "progress_url": f"/api/batches/{batch_id}/progress",
    }


@router.post("/api/batches/{batch_id}/scan/backs", status_code=202)
async def scan_backs(batch_id: str):
    """Start scanning back sides via the ADF scanner."""
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

    asyncio.create_task(scan_backs_task(batch_id, db))

    return {
        "status": "scanning",
        "message": "Scanning back pages...",
        "progress_url": f"/api/batches/{batch_id}/progress",
    }


@router.get("/api/batches/{batch_id}/progress")
async def batch_progress(batch_id: str):
    """Get the current processing progress for a batch."""
    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {
        "batch_id": batch_id,
        "state": batch["state"],
        "processing_stage": batch.get("processing_stage"),
    }


@router.get("/api/batches/{batch_id}/progress/stream")
async def batch_progress_stream(batch_id: str):
    """SSE stream of real-time progress events for a batch."""
    import json

    from fastapi.responses import StreamingResponse

    from scanbox.api.sse import event_bus

    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    async def generate():
        async for event in event_bus.subscribe(batch_id):
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") in ("done", "error"):
                break

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/api/batches/{batch_id}/save")
async def save_batch(batch_id: str):
    """Save batch documents to archive and medical records folders."""
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
