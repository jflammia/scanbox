"""Practice run wizard API and page route."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

from scanbox.config import Config
from scanbox.main import get_db
from scanbox.scanner.escl import ESCLClient

logger = logging.getLogger(__name__)

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
    """Get the current practice run status and step progress."""
    data = _read_practice()
    return {
        "completed": data.get("completed", False),
        "current_step": data.get("current_step", 1),
        "total_steps": TOTAL_STEPS,
        "steps_done": data.get("steps_done", []),
    }


@router.post("/api/practice/step/{step}/complete")
async def complete_step(step: int):
    """Mark a practice run step as complete and advance to the next."""
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


@router.post("/api/practice/step/{step}/validate")
async def validate_step(step: int):
    """Validate a practice run step by testing the actual subsystem."""
    if step < 1 or step > TOTAL_STEPS:
        raise HTTPException(
            status_code=400, detail=f"Invalid step {step}. Must be 1-{TOTAL_STEPS}."
        )

    cfg = Config()

    if step == 1:
        # Validate scanner connectivity
        if not cfg.SCANNER_IP:
            return {"valid": False, "message": "No scanner configured. Set SCANNER_IP."}
        try:
            client = ESCLClient(cfg.SCANNER_IP)
            try:
                caps = await client.get_capabilities()
                return {
                    "valid": True,
                    "message": f"Scanner connected: {caps.make_and_model or 'Unknown model'}",
                }
            finally:
                await client.close()
        except Exception as e:
            return {"valid": False, "message": f"Cannot reach scanner: {e}"}

    elif step == 2:
        # Validate LLM connectivity
        try:
            import litellm

            await litellm.acompletion(
                model=cfg.llm_model_id(),
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return {"valid": True, "message": f"LLM provider connected ({cfg.LLM_PROVIDER})."}
        except Exception as e:
            return {"valid": False, "message": str(e)}

    elif step == 3:
        # Validate storage directories
        internal_ok = cfg.INTERNAL_DATA_DIR.exists()
        output_ok = cfg.OUTPUT_DIR.exists()
        if internal_ok and output_ok:
            return {"valid": True, "message": "Storage directories are ready."}
        missing = []
        if not internal_ok:
            missing.append("internal data")
        if not output_ok:
            missing.append("output")
        return {"valid": False, "message": f"Missing directories: {', '.join(missing)}."}

    elif step == 4:
        # Validate at least one person exists
        db = get_db()
        persons = await db.list_persons()
        if persons:
            return {"valid": True, "message": f"Found {len(persons)} person(s)."}
        return {"valid": False, "message": "No persons created yet. Create at least one person."}

    return {"valid": False, "message": "Unknown step."}


@router.post("/api/practice/reset")
async def reset_practice():
    """Reset the practice run to step 1."""
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
