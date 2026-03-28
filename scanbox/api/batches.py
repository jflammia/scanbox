"""Batch management and scanning trigger endpoints."""

from fastapi import APIRouter, HTTPException

from scanbox.config import Config
from scanbox.main import get_db

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
