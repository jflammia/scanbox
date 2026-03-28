"""Practice run wizard API and page route."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

from scanbox.config import Config

router = APIRouter(tags=["practice"])

_template_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_template_dir))

TOTAL_STEPS = 4


def _practice_path() -> Path:
    cfg = Config()
    return cfg.config_dir / "practice.json"


def _read_practice() -> dict:
    path = _practice_path()
    if path.exists():
        return json.loads(path.read_text())
    return {"completed": False, "current_step": 1, "steps_done": []}


def _write_practice(data: dict) -> None:
    path = _practice_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


@router.get("/api/practice/status")
async def practice_status():
    data = _read_practice()
    return {
        "completed": data.get("completed", False),
        "current_step": data.get("current_step", 1),
        "total_steps": TOTAL_STEPS,
        "steps_done": data.get("steps_done", []),
    }


@router.post("/api/practice/step/{step}/complete")
async def complete_step(step: int):
    data = _read_practice()
    current = data.get("current_step", 1)

    if step != current:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot complete step {step}. Current step is {current}.",
        )

    steps_done = data.get("steps_done", [])
    if step not in steps_done:
        steps_done.append(step)

    next_step = step + 1
    completed = next_step > TOTAL_STEPS

    data["current_step"] = TOTAL_STEPS if completed else next_step
    data["steps_done"] = steps_done
    data["completed"] = completed
    _write_practice(data)

    return {
        "current_step": data["current_step"],
        "completed": completed,
        "total_steps": TOTAL_STEPS,
    }


@router.post("/api/practice/reset")
async def reset_practice():
    data = {"completed": False, "current_step": 1, "steps_done": []}
    _write_practice(data)
    return {"current_step": 1, "completed": False, "total_steps": TOTAL_STEPS}


@router.get("/practice")
async def practice_page(request: Request):
    data = _read_practice()
    return templates.TemplateResponse(
        request,
        "practice.html",
        {
            "current_step": data.get("current_step", 1),
            "total_steps": TOTAL_STEPS,
            "completed": data.get("completed", False),
        },
    )
