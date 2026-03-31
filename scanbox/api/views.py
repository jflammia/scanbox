"""Web UI routes serving HTML templates."""

import contextlib
import json
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

    cfg = Config()
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "persons": persons,
            "sessions": enriched_sessions,
            "setup_completed": setup_data.get("completed", False),
            "scanner_configured": bool(cfg.SCANNER_IP),
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

    import json as json_mod

    from scanbox.models import DOCUMENT_TYPES

    stages_dict = {k: v.to_dict() for k, v in state.stages.items()}
    dlq_list = [item.to_dict() for item in state.dlq]

    return templates.TemplateResponse(
        request,
        "pipeline.html",
        {
            "batch": batch,
            "person": person,
            "pipeline_status": state.status,
            "stages": stages_dict,
            "dlq": dlq_list,
            "stages_json": json_mod.dumps(stages_dict),
            "dlq_json": json_mod.dumps(dlq_list),
            "config": state.config.to_dict(),
            "stage_labels": _PIPELINE_STAGE_LABELS,
            "document_types": DOCUMENT_TYPES,
            "excluded_pages": state.excluded_pages,
            "excluded_documents": state.excluded_documents,
        },
    )


@router.get("/results/{batch_id}")
async def results(request: Request, batch_id: str):
    from scanbox.pipeline.state import PipelineState

    db = get_db()
    batch = await db.get_batch(batch_id)
    documents = await db.list_documents(batch_id)

    # Load pipeline summary and exclusion data from state.json
    pipeline_summary = []
    excluded_documents = []
    dlq_count = 0
    if batch:
        session = await db.get_session(batch["session_id"])
        if session:
            cfg = Config()
            batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch["id"]
            state_path = batch_dir / "state.json"
            if state_path.exists():
                state = PipelineState.load(state_path)
                excluded_documents = state.excluded_documents
                dlq_count = len(state.dlq)
                for key, label in _PIPELINE_STAGE_LABELS.items():
                    ss = state.stages.get(key)
                    if ss and ss.status.value == "completed" and ss.result:
                        summary = _stage_result_summary(key, ss.result)
                        if summary:
                            pipeline_summary.append({"label": label, "summary": summary})

    return templates.TemplateResponse(
        request,
        "results.html",
        {
            "batch": batch,
            "documents": documents,
            "pipeline_summary": pipeline_summary,
            "excluded_documents": excluded_documents,
            "dlq_count": dlq_count,
        },
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
    from scanbox.scanner.monitor import scanner_monitor

    state = scanner_monitor.state
    if not state.ip:
        return HTMLResponse(
            '<a href="/scanner" class="flex items-center gap-2 no-underline text-text-muted '
            'hover:text-text-secondary">'
            '<span class="inline-block w-3 h-3 rounded-full bg-gray-300"></span>'
            " <span>No scanner &mdash; set one up</span>"
            "</a>"
        )

    if state.connected:
        model = state.capabilities.make_and_model if state.capabilities else state.ip
        return HTMLResponse(
            '<a href="/scanner" class="flex items-center gap-2 no-underline text-text-muted '
            'hover:text-text-secondary">'
            '<span class="inline-block w-3 h-3 rounded-full bg-status-success"></span>'
            f" <span>{model}</span>"
            "</a>"
        )
    else:
        return HTMLResponse(
            '<a href="/scanner" class="flex items-center gap-2 no-underline text-text-muted '
            'hover:text-text-secondary">'
            '<span class="inline-block w-3 h-3 rounded-full bg-status-error"></span>'
            f" <span>Can't reach scanner ({state.ip})</span>"
            "</a>"
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
            "app_version": cfg.APP_VERSION,
        },
    )


@router.post("/settings/scanner", response_class=HTMLResponse)
async def settings_scanner(scanner_ip: str = Form("")):
    """Save scanner IP from the Settings page."""
    cfg = Config()
    runtime_path = cfg.config_dir / "runtime.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)

    data = {}
    if runtime_path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            data = json.loads(runtime_path.read_text())
    data["scanner_ip"] = scanner_ip.strip()
    runtime_path.write_text(json.dumps(data))

    if scanner_ip.strip():
        return HTMLResponse('<p class="text-status-success font-medium mt-2">Scanner IP saved.</p>')
    return HTMLResponse('<p class="text-text-muted font-medium mt-2">Scanner IP cleared.</p>')


@router.get("/scanner")
async def scanner_page(request: Request):
    """Dedicated scanner configuration page."""
    from scanbox.scanner.discovery import BRIDGE_NETWORK_HINT, mdns_available

    cfg = Config()
    can_discover = mdns_available()
    return templates.TemplateResponse(
        request,
        "scanner.html",
        {
            "scanner_ip": cfg.SCANNER_IP,
            "mdns_available": can_discover,
            "mdns_hint": None if can_discover else BRIDGE_NETWORK_HINT,
        },
    )


@router.get("/scanner/status-card", response_class=HTMLResponse)
async def scanner_status_card():
    """Rich status card partial for the scanner page."""
    from scanbox.scanner.monitor import scanner_monitor

    state = scanner_monitor.state
    if not state.ip:
        return HTMLResponse(
            '<div class="flex items-center gap-4">'
            '<span class="w-4 h-4 rounded-full bg-gray-300 flex-shrink-0"></span>'
            "<div>"
            '<p class="font-medium">No scanner configured</p>'
            '<p class="text-sm text-text-muted">'
            "Enter an IP address below or scan your network to find scanners.</p>"
            "</div>"
            "</div>"
        )

    if state.connected:
        model = state.capabilities.make_and_model if state.capabilities else "Scanner"
        adf_text = "Paper loaded" if state.status and state.status.adf_loaded else "Empty"
        return HTMLResponse(
            '<div class="flex items-center gap-4">'
            '<img src="/api/scanner/icon" alt="" class="w-10 h-10 object-contain rounded"'
            " onerror=\"this.style.display='none'\">"
            "<div>"
            '<div class="flex items-center gap-2">'
            '<span class="w-3 h-3 rounded-full bg-status-success flex-shrink-0"></span>'
            '<span class="font-medium">Connected</span>'
            "</div>"
            f'<p class="text-lg font-semibold">{model}</p>'
            f'<p class="text-sm text-text-secondary">{state.ip}</p>'
            f'<p class="text-sm text-text-muted">Document feeder: {adf_text}</p>'
            "</div>"
            "</div>"
        )
    else:
        return HTMLResponse(
            '<div class="flex items-center gap-4">'
            '<span class="w-4 h-4 rounded-full bg-status-error flex-shrink-0"></span>'
            "<div>"
            f'<p class="font-medium">Can\'t reach scanner</p>'
            f'<p class="text-sm text-text-secondary">{state.ip}</p>'
            '<p class="text-sm text-text-muted">'
            "Check that the scanner is on and connected to your network.</p>"
            "</div>"
            "</div>"
        )


@router.post("/scanner/set-ip", response_class=HTMLResponse)
async def set_scanner_ip(request: Request):
    """Save a scanner IP and test the connection."""
    from scanbox.scanner.monitor import scanner_monitor

    form = await request.form()
    scanner_ip = str(form.get("scanner_ip", "")).strip()

    if not scanner_ip:
        return HTMLResponse(
            '<p class="text-status-warning font-medium">Enter a scanner IP address.</p>'
        )

    # Save to runtime config
    cfg = Config()
    runtime_path = cfg.config_dir / "runtime.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if runtime_path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            data = json.loads(runtime_path.read_text())
    data["scanner_ip"] = scanner_ip
    runtime_path.write_text(json.dumps(data))

    # Restart monitor with new IP and test connection
    await scanner_monitor.start(scanner_ip)
    state = await scanner_monitor.refresh_now()

    if state.connected:
        model = state.capabilities.make_and_model if state.capabilities else "Scanner"
        return HTMLResponse(
            f'<p class="text-status-success font-medium">Connected to {model} at {scanner_ip}</p>'
        )
    else:
        return HTMLResponse(
            f'<p class="text-status-warning font-medium">'
            f"Saved {scanner_ip} but can't reach it yet. Is the scanner on?</p>"
        )


@router.post("/scanner/discover", response_class=HTMLResponse)
async def discover_scanners_html():
    """Discover scanners on the network and return HTML cards."""
    from scanbox.scanner.discovery import (
        BRIDGE_NETWORK_HINT,
        DISCOVERY_HINT,
        discover_scanners,
        mdns_available,
    )

    if not mdns_available():
        return HTMLResponse(
            '<div class="bg-status-warning/10 border border-status-warning/30 rounded-lg p-4">'
            '<p class="font-medium text-status-warning">Scanner discovery unavailable</p>'
            f'<p class="text-sm text-text-secondary mt-1">{BRIDGE_NETWORK_HINT}</p>'
            "</div>"
        )

    scanners = await discover_scanners(timeout=5.0)
    if not scanners:
        return HTMLResponse(
            '<p class="text-text-muted text-sm py-2">No scanners found on your network.</p>'
            '<p class="text-text-muted text-xs">'
            f"{DISCOVERY_HINT}</p>"
        )

    cards = ""
    for s in scanners:
        if s.icon_url:
            icon_html = (
                f'<img src="/api/scanner/icon?ip={s.ip}" alt="" '
                f'class="w-12 h-12 object-contain rounded"'
                f" onerror=\"this.parentElement.innerHTML='&#128424;'\">"
            )
        else:
            icon_html = '<div class="text-3xl">&#128424;</div>'
        cards += (
            f'<form class="inline" hx-post="/scanner/set-ip" hx-target="#scanner-set-result" '
            f'hx-swap="innerHTML">'
            f'<input type="hidden" name="scanner_ip" value="{s.ip}">'
            f'<button type="submit" '
            f'class="w-full text-left border border-border rounded-lg p-4 '
            f"flex items-center gap-4 "
            f'hover:border-brand-400 hover:bg-brand-50 transition-colors cursor-pointer">'
            f"{icon_html}"
            f'<div class="flex-1"><p class="font-semibold">{s.model}</p>'
            f'<p class="text-sm text-text-secondary">{s.ip}</p></div>'
            f'<span class="text-sm text-brand-600 font-medium">Use this scanner</span>'
            f"</button>"
            f"</form>"
        )
    return HTMLResponse(
        f'<div class="space-y-2">'
        f'<p class="text-status-success font-medium">Found {len(scanners)} scanner(s)</p>'
        f"{cards}</div>"
    )


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
