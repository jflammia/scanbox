"""First-run setup wizard API and page route."""

import json
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
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
    """Get the current setup wizard status."""
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
    """Mark setup as complete and optionally save configuration."""
    data = _read_setup()
    data["completed"] = True
    data["current_step"] = TOTAL_STEPS
    if req:
        for key, val in req.model_dump().items():
            if val is not None:
                data[key] = val
    _write_setup(data)
    return {"completed": True}


@router.post("/setup/add-person", response_class=HTMLResponse)
async def setup_add_person(person_name: str = Form(...)):
    from scanbox.main import get_db

    db = get_db()
    person = await db.create_person(person_name.strip())
    return HTMLResponse(
        f'<p class="text-status-success font-medium">Added {person["display_name"]}</p>'
    )


@router.post("/setup/discover-scanners", response_class=HTMLResponse)
async def discover_scanners():
    """Scan common subnets for eSCL scanners and return HTML results."""
    import asyncio
    import xml.etree.ElementTree as ET

    import httpx

    found: list[dict] = []
    sem = asyncio.Semaphore(20)

    async def probe(ip: str, client: httpx.AsyncClient):
        async with sem:
            try:
                resp = await client.get(f"http://{ip}/eSCL/ScannerStatus", timeout=3.0)
                if resp.status_code == 200:
                    # Try to get the model name from ScannerCapabilities
                    name = ip
                    try:
                        caps = await client.get(
                            f"http://{ip}/eSCL/ScannerCapabilities", timeout=3.0
                        )
                        if caps.status_code == 200:
                            root = ET.fromstring(caps.text)
                            for el in root.iter():
                                if el.tag.endswith("MakeAndModel") and el.text:
                                    name = el.text
                                    break
                    except Exception:
                        pass
                    found.append({"ip": ip, "name": name})
            except Exception:
                pass

    # Probe common home network subnets (20 concurrent, 3s timeout)
    subnets = ["192.168.1", "192.168.0", "192.168.10", "192.168.2", "10.0.0", "10.0.1"]
    ips = [f"{subnet}.{host}" for subnet in subnets for host in range(1, 255)]

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(probe(ip, client) for ip in ips))

    if found:
        cards = ""
        for s in found:
            cards += (
                f'<button type="button" '
                f"@click=\"$refs.scannerIp.value = '{s['ip']}'; "
                f"$el.closest('form').requestSubmit()\" "
                f'class="w-full text-left border border-border rounded-lg p-4 '
                f'hover:border-brand-400 hover:bg-brand-50 transition-colors cursor-pointer">'
                f'<p class="font-semibold">{s["name"]}</p>'
                f'<p class="text-sm text-text-secondary">{s["ip"]}</p>'
                f"</button>"
            )
        return HTMLResponse(
            f'<div class="space-y-2">'
            f'<p class="text-status-success font-medium">Found {len(found)} scanner(s)</p>'
            f"{cards}</div>"
        )
    return HTMLResponse(
        '<p class="text-text-muted">No scanners found automatically. '
        "Enter the IP address below.</p>"
    )


@router.post("/setup/test-scanner", response_class=HTMLResponse)
async def setup_test_scanner(scanner_ip: str = Form("")):
    """Save scanner IP and test connectivity, returning HTML feedback."""
    import contextlib

    scanner_ip = scanner_ip.strip()
    if not scanner_ip:
        return HTMLResponse(
            '<p class="text-status-warning font-medium">'
            "No IP entered. You can set this later in Settings.</p>"
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

    # Test connectivity
    from scanbox.scanner.escl import ESCLClient

    client = ESCLClient(scanner_ip)
    try:
        caps = await client.get_capabilities()
        model = caps.make_and_model or "Scanner"
        return HTMLResponse(
            f'<p class="text-status-success font-medium">Connected to {model} at {scanner_ip}</p>'
        )
    except Exception:
        return HTMLResponse(
            f'<p class="text-status-warning font-medium">'
            f"Saved {scanner_ip} but can't reach it yet. Is the scanner on?</p>"
        )
    finally:
        await client.close()


@router.post("/api/setup/test-scanner")
async def test_scanner():
    """Test scanner connectivity by fetching its status."""
    cfg = Config()
    if not cfg.SCANNER_IP:
        return {"success": False, "message": "No scanner IP configured. Set SCANNER_IP."}

    from scanbox.scanner.escl import ESCLClient

    client = ESCLClient(cfg.SCANNER_IP)
    try:
        caps = await client.get_capabilities()
        return {
            "success": True,
            "scanner_ip": cfg.SCANNER_IP,
            "model": caps.make_and_model or "Unknown model",
            "message": "Scanner connected",
        }
    except Exception:
        return {
            "success": False,
            "scanner_ip": cfg.SCANNER_IP,
            "message": "Can't reach the scanner. Is it turned on?",
        }
    finally:
        await client.close()


@router.post("/api/setup/test-llm")
async def test_llm():
    """Test LLM provider connectivity with a simple completion request."""
    cfg = Config()
    model = cfg.llm_model_id()
    try:
        import litellm

        await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": "Reply with OK"}],
            max_tokens=5,
        )
        return {
            "success": True,
            "provider": cfg.LLM_PROVIDER,
            "model": model,
            "message": "LLM provider connected",
        }
    except Exception as e:
        return {
            "success": False,
            "provider": cfg.LLM_PROVIDER,
            "model": model,
            "message": f"LLM connection failed: {e}",
        }


@router.post("/api/setup/test-paperless")
async def test_paperless():
    """Test PaperlessNGX connectivity."""
    cfg = Config()
    if not cfg.PAPERLESS_URL or not cfg.PAPERLESS_API_TOKEN:
        return {"success": False, "message": "PaperlessNGX not configured."}

    from scanbox.api.paperless import PaperlessClient

    client = PaperlessClient(cfg.PAPERLESS_URL, cfg.PAPERLESS_API_TOKEN)
    ok = await client.check_connection()
    if ok:
        return {
            "success": True,
            "paperless_url": cfg.PAPERLESS_URL,
            "message": "Connected to PaperlessNGX",
        }
    return {
        "success": False,
        "paperless_url": cfg.PAPERLESS_URL,
        "message": "Can't connect to PaperlessNGX. Check URL and API token.",
    }


@router.get("/setup")
async def setup_page(request: Request):
    data = _read_setup()
    return templates.TemplateResponse(
        request,
        "setup.html",
        {"current_step": data.get("current_step", 1), "total_steps": TOTAL_STEPS},
    )
