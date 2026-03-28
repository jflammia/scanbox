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
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "persons": persons,
            "sessions": sessions,
            "setup_completed": setup_data.get("completed", False),
        },
    )


@router.get("/scan/{session_id}/{batch_id}")
async def scan_wizard(request: Request, session_id: str, batch_id: str):
    db = get_db()
    batch = await db.get_batch(batch_id)
    session = await db.get_session(session_id)
    return templates.TemplateResponse(request, "scan.html", {"batch": batch, "session": session})


@router.get("/results/{batch_id}")
async def results(request: Request, batch_id: str):
    db = get_db()
    batch = await db.get_batch(batch_id)
    documents = await db.list_documents(batch_id)
    return templates.TemplateResponse(
        request, "results.html", {"batch": batch, "documents": documents}
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
