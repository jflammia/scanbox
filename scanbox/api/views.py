"""Web UI routes serving HTML templates."""

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from scanbox.api.setup import _read_setup
from scanbox.config import Config
from scanbox.main import get_db

router = APIRouter(tags=["views"])

_template_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_template_dir))


@router.get("/")
async def home(request: Request):
    db = get_db()
    persons = await db.list_persons()
    sessions = await db.list_sessions()
    setup_data = _read_setup()

    # Enrich sessions with person name and latest batch id
    persons_map = {p["id"]: p["display_name"] for p in persons}
    enriched_sessions = []
    for s in sessions:
        batches = await db.list_batches(s["id"])
        latest_batch = batches[0] if batches else None
        docs = []
        if latest_batch:
            docs = await db.list_documents(latest_batch["id"])
        enriched_sessions.append(
            {
                **s,
                "person_name": persons_map.get(s["person_id"], "Unknown"),
                "latest_batch_id": latest_batch["id"] if latest_batch else None,
                "document_count": len(docs),
            }
        )

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "persons": persons,
            "sessions": enriched_sessions,
            "setup_completed": setup_data.get("completed", False),
        },
    )


@router.get("/scan/{session_id}/{batch_id}")
async def scan_wizard(request: Request, session_id: str, batch_id: str):
    db = get_db()
    batch = await db.get_batch(batch_id)
    session = await db.get_session(session_id)
    return templates.TemplateResponse(request, "scan.html", {"batch": batch, "session": session})


# Stage labels for the pipeline page (plain English, keyed by ProcessingStage values)
_PIPELINE_STAGE_LABELS: dict[str, str] = {
    "interleaving": "Combining front and back pages",
    "blank_removal": "Removing blank pages",
    "ocr": "Reading text from documents",
    "splitting": "Identifying document boundaries",
    "naming": "Organizing and naming documents",
}


def _stage_result_summary(stage_key: str, result: dict) -> str:
    """Return a short human-readable summary for a completed stage result."""
    if stage_key == "interleaving" and result.get("total_pages"):
        return f"{result['total_pages']} pages combined"
    if stage_key == "blank_removal":
        removed = result.get("removed_indices", [])
        kept = result.get("kept_pages", result.get("total_pages", 0) - len(removed))
        return f"{kept} pages kept, {len(removed)} blank removed"
    if stage_key == "ocr":
        return "Text recognition complete"
    if stage_key == "splitting" and result.get("document_count"):
        n = result["document_count"]
        return f"{n} document{'s' if n != 1 else ''} found"
    if stage_key == "naming" and result.get("documents_named"):
        n = result["documents_named"]
        return f"{n} document{'s' if n != 1 else ''} named"
    return ""


@router.get("/pipeline/{batch_id}")
async def pipeline_page(request: Request, batch_id: str):
    """Pipeline progress and control page."""
    from fastapi import HTTPException

    from scanbox.pipeline.state import PipelineState

    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    session = await db.get_session(batch["session_id"])
    person = await db.get_person(session["person_id"])

    cfg = Config()
    batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch_id

    state = PipelineState.load(batch_dir / "state.json")

    return templates.TemplateResponse(
        request,
        "pipeline.html",
        {
            "batch": batch,
            "person": person,
            "pipeline_status": state.status,
            "stages": {k: v.to_dict() for k, v in state.stages.items()},
            "dlq": [item.to_dict() for item in state.dlq],
            "config": state.config.to_dict(),
            "stage_labels": _PIPELINE_STAGE_LABELS,
        },
    )


@router.get("/results/{batch_id}")
async def results(request: Request, batch_id: str):
    from scanbox.pipeline.state import PipelineState

    db = get_db()
    batch = await db.get_batch(batch_id)
    documents = await db.list_documents(batch_id)

    # Load pipeline summary for the results page
    pipeline_summary = []
    if batch:
        session = await db.get_session(batch["session_id"])
        if session:
            cfg = Config()
            batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch["id"]
            state_path = batch_dir / "state.json"
            if state_path.exists():
                state = PipelineState.load(state_path)
                for key, label in _PIPELINE_STAGE_LABELS.items():
                    ss = state.stages.get(key)
                    if ss and ss.status.value == "completed" and ss.result:
                        summary = _stage_result_summary(key, ss.result)
                        if summary:
                            pipeline_summary.append({"label": label, "summary": summary})

    return templates.TemplateResponse(
        request,
        "results.html",
        {"batch": batch, "documents": documents, "pipeline_summary": pipeline_summary},
    )


@router.get("/batches/{batch_id}/boundaries/edit")
async def boundary_editor(request: Request, batch_id: str):
    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Batch not found")
    documents = await db.list_documents(batch_id)
    total_pages = max((d["end_page"] for d in documents), default=0)

    # Extract boundary pages (pages after which a new document starts)
    boundary_pages = []
    for doc in documents:
        if doc["end_page"] < total_pages:
            boundary_pages.append(doc["end_page"])

    return templates.TemplateResponse(
        request,
        "boundary_editor.html",
        {
            "batch_id": batch_id,
            "total_pages": total_pages,
            "boundary_pages": sorted(boundary_pages),
        },
    )


@router.post("/scan/start")
async def scan_start(
    person_id: str = Form(...),
    new_person_name: str = Form(""),
):
    db = get_db()

    if person_id == "__new__" and new_person_name.strip():
        person = await db.create_person(new_person_name.strip())
        person_id = person["id"]

    session = await db.create_session(person_id)
    batch = await db.create_batch(session["id"])
    return RedirectResponse(
        url=f"/scan/{session['id']}/{batch['id']}",
        status_code=303,
    )


@router.get("/documents/{document_id}/edit", response_class=HTMLResponse)
async def document_edit_form(request: Request, document_id: str):
    db = get_db()
    doc = await db.get_document(document_id)
    if not doc:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Document not found")
    return templates.TemplateResponse(request, "document_edit.html", {"doc": doc})


@router.post("/documents/{document_id}/edit", response_class=HTMLResponse)
async def document_edit_submit(
    request: Request,
    document_id: str,
    document_type: str = Form(""),
    date_of_service: str = Form(""),
    facility: str = Form(""),
    provider: str = Form(""),
    description: str = Form(""),
):
    db = get_db()
    doc = await db.get_document(document_id)
    if not doc:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Document not found")

    updates = {}
    for field in ("document_type", "date_of_service", "facility", "provider", "description"):
        val = locals()[field]
        if val:
            updates[field] = val
    if updates:
        updates["user_edited"] = True
    doc = await db.update_document(document_id, **updates)
    return templates.TemplateResponse(request, "document_card.html", {"doc": doc})


@router.get("/documents/{document_id}/card", response_class=HTMLResponse)
async def document_card(request: Request, document_id: str):
    db = get_db()
    doc = await db.get_document(document_id)
    if not doc:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Document not found")
    return templates.TemplateResponse(request, "document_card.html", {"doc": doc})


@router.get("/persons/list", response_class=HTMLResponse)
async def persons_list(request: Request):
    db = get_db()
    persons = await db.list_persons()
    return templates.TemplateResponse(request, "persons_list.html", {"persons": persons})


@router.post("/persons/add", response_class=HTMLResponse)
async def persons_add(request: Request, display_name: str = Form(...)):
    db = get_db()
    await db.create_person(display_name.strip())
    persons = await db.list_persons()
    return templates.TemplateResponse(request, "persons_list.html", {"persons": persons})


@router.post("/batches/{batch_id}/save", response_class=HTMLResponse)
async def save_batch_html(request: Request, batch_id: str):
    from fastapi import HTTPException

    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch["state"] != "review":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot save in state '{batch['state']}'. Must be 'review'.",
        )

    try:
        from scanbox.api.batches import save_batch

        result = await save_batch(batch_id)
        count = len(result.get("medical_records", []))
    except FileNotFoundError:
        # Batch files may not exist yet (e.g. processing incomplete)
        await db.update_batch_state(batch_id, "saved")
        count = len(await db.list_documents(batch_id))

    return templates.TemplateResponse(
        request,
        "save_result.html",
        {"medical_records_count": count},
    )


@router.post("/batches/{batch_id}/skip-backs", response_class=HTMLResponse)
async def skip_backs_html(request: Request, batch_id: str):
    import asyncio

    from fastapi import HTTPException

    from scanbox.api.scanning import process_after_skip_backs

    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch["state"] != "fronts_done":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot skip backs in state '{batch['state']}'.",
        )
    await db.update_batch_state(batch_id, "backs_skipped")
    asyncio.create_task(process_after_skip_backs(batch_id, db))
    return HTMLResponse('<p class="text-status-success font-medium">Backs skipped</p>')


@router.get("/scanner/status", response_class=HTMLResponse)
async def scanner_status():
    cfg = Config()
    if not cfg.SCANNER_IP:
        return HTMLResponse(
            '<span class="inline-block w-3 h-3 rounded-full bg-gray-300"></span>'
            " <span>No scanner configured</span>"
        )

    try:
        import httpx

        async with httpx.AsyncClient(timeout=3.0) as http:
            resp = await http.get(f"http://{cfg.SCANNER_IP}/eSCL/ScannerStatus")
            if resp.status_code == 200:
                return HTMLResponse(
                    '<span class="inline-block w-3 h-3 rounded-full bg-status-success">'
                    f"</span> Scanner ready ({cfg.SCANNER_IP})"
                )
    except Exception:
        pass

    return HTMLResponse(
        '<span class="inline-block w-3 h-3 rounded-full bg-status-error"></span>'
        f" Can't reach scanner ({cfg.SCANNER_IP})"
    )


@router.get("/settings")
async def settings(request: Request):
    cfg = Config()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "scanner_ip": cfg.SCANNER_IP,
            "paperless_url": cfg.PAPERLESS_URL,
        },
    )


@router.post("/settings/scanner", response_class=HTMLResponse)
async def settings_scanner(scanner_ip: str = Form("")):
    """Save scanner IP from the Settings page."""
    import json

    cfg = Config()
    runtime_path = cfg.config_dir / "runtime.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing runtime config, update scanner_ip
    import contextlib

    data = {}
    if runtime_path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            data = json.loads(runtime_path.read_text())
    data["scanner_ip"] = scanner_ip.strip()
    runtime_path.write_text(json.dumps(data))

    if scanner_ip.strip():
        return HTMLResponse('<p class="text-status-success font-medium mt-2">Scanner IP saved.</p>')
    return HTMLResponse('<p class="text-text-muted font-medium mt-2">Scanner IP cleared.</p>')


_SPINNER = (
    '<div class="w-4 h-4 border-2 border-brand-300 border-t-brand-600 '
    'rounded-full animate-spin inline-block"></div>'
)
_CHECK = '<span class="text-status-success font-bold">&#10003;</span>'
_ERROR_ICON = '<span class="text-status-error font-bold">&#10007;</span>'

_STAGE_LABELS: dict[str, str] = {
    "interleave": "Merging front and back sides...",
    "blank_detect": "Removing blank pages...",
    "ocr": "Running text recognition...",
    "split": "Identifying document boundaries...",
    "name": "Generating filenames...",
    "output": "Writing output files...",
}


def _friendly_error(msg: str) -> str:
    """Convert a technical error message to plain English."""
    lower = msg.lower()
    if "authenticationerror" in lower or "api key" in lower or "authentication" in lower:
        return "No AI service configured. Add your API key in Settings."
    if "connecterror" in lower or "unreachable" in lower or "connection refused" in lower:
        return "Lost connection to the scanner. Is it still on?"
    if "timeout" in lower or "timed out" in lower:
        return "The operation timed out. Please try again."
    # Strip Python exception class prefix (e.g. "ValueError: something" → "something")
    if ": " in msg:
        return msg.split(": ", 1)[1]
    return msg


def _render_progress_event(event: dict, batch_id: str) -> str:
    """Map an event dict to an HTML fragment string."""
    etype = event.get("type", "")

    if etype == "progress":
        stage = event.get("stage", "")
        label = _STAGE_LABELS.get(stage, "Processing...")
        return (
            f'<div class="flex items-center gap-2 text-brand-600 font-medium">'
            f"{_SPINNER} {label}</div>"
        )

    if etype == "page_scanned":
        page = event.get("page", "?")
        return f'<div class="ml-4 text-text-secondary text-sm">Page {page} scanned</div>'

    if etype == "scan_complete":
        count = event.get("count", 0)
        return (
            f'<div class="flex items-center gap-2 font-medium">'
            f"{_CHECK} Scanned {count} pages</div>"
            f'<span x-init="step1Done = true; currentStep = 2" class="hidden"></span>'
        )

    if etype == "stage_complete":
        stage = event.get("stage", "")
        detail = event.get("detail", "")
        label = _STAGE_LABELS.get(stage, stage)
        detail_html = f" — {detail}" if detail else ""
        return (
            f'<div class="flex items-center gap-2 font-medium">{_CHECK} {label}{detail_html}</div>'
        )

    if etype == "done":
        count = event.get("count", 0)
        return (
            f'<div class="flex items-center gap-2 font-medium text-status-success">'
            f"{_CHECK} All done! {count} document{'s' if count != 1 else ''} ready for review</div>"
            f'<a href="/results/{batch_id}" class="underline text-brand-600">'
            f"Review documents</a>"
        )

    if etype == "error":
        raw = event.get("message", "An unexpected error occurred.")
        friendly = _friendly_error(raw)
        return (
            f'<div class="flex items-center gap-2 font-medium text-status-error">'
            f"{_ERROR_ICON} {friendly}</div>"
            f'<a href="/" class="underline text-brand-600">Back to Home</a>'
        )

    return ""


@router.get("/batches/{batch_id}/progress", response_class=HTMLResponse)
async def batch_progress_sse(batch_id: str):
    """SSE stream of HTML progress fragments for the scan wizard."""
    from starlette.responses import StreamingResponse

    from scanbox.api.sse import event_bus

    async def generate():
        async for event in event_bus.subscribe(batch_id):
            html = _render_progress_event(event, batch_id)
            if html:
                yield f"data: {html}\n\n"
            if event.get("type") in ("done", "error"):
                break

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/batches/{batch_id}/scan-fronts", response_class=HTMLResponse)
async def scan_fronts_html(batch_id: str):
    """Start scanning front sides, returning HTML progress feedback."""
    import asyncio

    from scanbox.api.scanning import scan_fronts_task

    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        return HTMLResponse(
            '<p class="text-status-error font-medium">Batch not found.</p>',
            status_code=404,
        )

    cfg = Config()
    if not cfg.SCANNER_IP:
        return HTMLResponse(
            '<p class="text-status-error font-medium">'
            "No scanner configured. Go to Settings to add your scanner's IP address.</p>",
            status_code=422,
        )

    if batch["state"] != "scanning_fronts":
        return HTMLResponse(
            f'<p class="text-status-error font-medium">'
            f"Can't scan right now (status: {batch['state']}).</p>",
            status_code=409,
        )

    asyncio.create_task(scan_fronts_task(batch_id, db))
    return HTMLResponse(
        f'<div hx-ext="sse" sse-connect="/batches/{batch_id}/progress" '
        f'sse-swap="message" hx-swap="beforeend" class="space-y-1"></div>'
    )


@router.post("/batches/{batch_id}/scan-backs", response_class=HTMLResponse)
async def scan_backs_html(batch_id: str):
    """Start scanning back sides, returning HTML progress feedback."""
    import asyncio

    from scanbox.api.scanning import scan_backs_task

    db = get_db()
    batch = await db.get_batch(batch_id)
    if not batch:
        return HTMLResponse(
            '<p class="text-status-error font-medium">Batch not found.</p>',
            status_code=404,
        )

    cfg = Config()
    if not cfg.SCANNER_IP:
        return HTMLResponse(
            '<p class="text-status-error font-medium">'
            "No scanner configured. Go to Settings to add your scanner's IP address.</p>",
            status_code=422,
        )

    if batch["state"] != "fronts_done":
        return HTMLResponse(
            f'<p class="text-status-error font-medium">'
            f"Can't scan backs right now (status: {batch['state']}).</p>",
            status_code=409,
        )

    asyncio.create_task(scan_backs_task(batch_id, db))
    return HTMLResponse(
        f'<div hx-ext="sse" sse-connect="/batches/{batch_id}/progress" '
        f'sse-swap="message" hx-swap="beforeend" class="space-y-1"></div>'
    )
