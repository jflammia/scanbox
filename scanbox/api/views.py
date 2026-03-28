"""Web UI routes serving HTML templates."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

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
    return templates.TemplateResponse(
        request, "home.html", {"persons": persons, "sessions": sessions}
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
