"""First-run setup wizard API and page route."""

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from scanbox.config import Config

router = APIRouter(tags=["setup"])

_template_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_template_dir))

TOTAL_STEPS = 6


def _setup_path() -> Path:
    cfg = Config()
    return cfg.config_dir / "setup.json"


def _read_setup() -> dict:
    path = _setup_path()
    if path.exists():
        return json.loads(path.read_text())
    return {"completed": False, "current_step": 1}


def _write_setup(data: dict) -> None:
    path = _setup_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


@router.get("/api/setup/status")
async def setup_status():
    data = _read_setup()
    return {
        "completed": data.get("completed", False),
        "current_step": data.get("current_step", 1),
        "total_steps": TOTAL_STEPS,
    }


class SetupCompleteRequest(BaseModel):
    scanner_ip: str | None = None
    llm_provider: str | None = None
    llm_api_key: str | None = None
    paperless_url: str | None = None
    paperless_token: str | None = None


@router.post("/api/setup/complete")
async def complete_setup(req: SetupCompleteRequest | None = None):
    data = _read_setup()
    data["completed"] = True
    data["current_step"] = TOTAL_STEPS
    if req:
        for key, val in req.model_dump().items():
            if val is not None:
                data[key] = val
    _write_setup(data)
    return {"completed": True}


@router.get("/setup")
async def setup_page(request: Request):
    data = _read_setup()
    return templates.TemplateResponse(
        request,
        "setup.html",
        {"current_step": data.get("current_step", 1), "total_steps": TOTAL_STEPS},
    )
