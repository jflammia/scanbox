"""First-run setup wizard API and page route."""

import json
import socket
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
async def setup_discover_scanners():
    """Discover scanners via mDNS and return HTML results."""
    from scanbox.scanner.discovery import DISCOVERY_HINT, discover_scanners

    scanners = await discover_scanners(timeout=5.0)

    if scanners:
        cards = ""
        for s in scanners:
            icon_html = (
                f'<img src="/api/scanner/icon?ip={s.ip}" alt="" '
                f'class="w-10 h-10 object-cover rounded"'
                f" onerror=\"this.parentElement.innerHTML='&#128424;'\">"
                if s.icon_url
                else '<div class="text-3xl">&#128424;</div>'
            )
            cards += (
                f'<button type="button" '
                f"@click=\"$refs.scannerIp.value = '{s.ip}'; "
                f"htmx.trigger($refs.verifyForm, 'submit')\" "
                f'class="w-full text-left border border-border rounded-lg p-4 '
                f"flex items-center gap-4 "
                f'hover:border-brand-400 hover:bg-brand-50 transition-colors cursor-pointer">'
                f"{icon_html}"
                f'<div><p class="font-semibold">{s.model}</p>'
                f'<p class="text-sm text-text-secondary">{s.ip}</p></div>'
                f"</button>"
            )
        return HTMLResponse(
            f'<div class="space-y-2">'
            f'<p class="text-status-success font-medium">Found {len(scanners)} scanner(s)</p>'
            f"{cards}</div>"
        )
    return HTMLResponse(f'<p class="text-text-muted text-sm">{DISCOVERY_HINT}</p>')


@router.post("/setup/verify-scanner", response_class=HTMLResponse)
async def setup_verify_scanner(scanner_ip: str = Form("")):
    """Run 4-step verification checklist on a scanner IP."""
    import contextlib

    scanner_ip = scanner_ip.strip()
    if not scanner_ip:
        return HTMLResponse(
            '<p class="text-status-warning font-medium">Enter a scanner IP address.</p>'
        )

    from scanbox.scanner.escl import ESCLClient

    checks: list[tuple[str, bool, str]] = []

    # Check 1: TCP reachability
    try:
        sock = socket.create_connection((scanner_ip, 80), timeout=3)
        sock.close()
        checks.append(("Reaching scanner", True, ""))
    except Exception:
        checks.append(
            (
                "Reaching scanner",
                False,
                "Can't connect — is the scanner powered on and on your network?",
            )
        )
        return _render_checklist(checks, scanner_ip)

    # Check 2-4: eSCL protocol, capabilities, status
    client = ESCLClient(scanner_ip)
    try:
        try:
            status = await client.get_status()
            checks.append(("eSCL protocol", True, ""))
        except Exception:
            checks.append(
                (
                    "eSCL protocol",
                    False,
                    "Scanner responded but doesn't support eSCL/AirScan",
                )
            )
            return _render_checklist(checks, scanner_ip)

        try:
            caps = await client.get_capabilities()
            if caps.has_adf:
                checks.append(("Scanner capabilities", True, "ADF supported"))
            else:
                checks.append(
                    (
                        "Scanner capabilities",
                        False,
                        "No document feeder (ADF) detected",
                    )
                )
                return _render_checklist(checks, scanner_ip)
        except Exception:
            checks.append(
                (
                    "Scanner capabilities",
                    False,
                    "Could not read scanner capabilities",
                )
            )
            return _render_checklist(checks, scanner_ip)

        if status.state.lower() == "idle":
            checks.append(("Scanner ready", True, ""))
        else:
            checks.append(
                (
                    "Scanner ready",
                    False,
                    f"Scanner is busy ({status.state})",
                )
            )
            return _render_checklist(checks, scanner_ip)
    finally:
        await client.close()

    # All passed — save to runtime config
    cfg = Config()
    runtime_path = cfg.config_dir / "runtime.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if runtime_path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            data = json.loads(runtime_path.read_text())
    data["scanner_ip"] = scanner_ip
    runtime_path.write_text(json.dumps(data))

    model = caps.make_and_model or "Scanner"
    icon_html = ""
    if caps.icon_url:
        icon_html = (
            f'<img src="{caps.icon_url}" alt="{model}" class="w-10 h-10 object-cover rounded">'
        )

    return _render_checklist(checks, scanner_ip, model=model, icon_html=icon_html)


def _render_checklist(
    checks: list[tuple[str, bool, str]],
    scanner_ip: str,
    model: str = "",
    icon_html: str = "",
) -> HTMLResponse:
    """Render the verification checklist as HTML."""
    html = '<div class="space-y-2">'
    all_passed = all(passed for _, passed, _ in checks)

    for name, passed, detail in checks:
        icon = "&#10003;" if passed else "&#10007;"
        color = "text-status-success" if passed else "text-status-error"
        detail_html = f' <span class="text-sm text-text-muted">— {detail}</span>' if detail else ""
        html += (
            f'<div class="flex items-center gap-2">'
            f'<span class="{color} font-bold">{icon}</span> {name}{detail_html}'
            f"</div>"
        )

    if all_passed:
        html += (
            f'<div class="flex items-center gap-3 mt-3">'
            f"{icon_html}"
            f'<p class="text-status-success font-semibold">'
            f"Connected to {model} at {scanner_ip}</p>"
            f"</div>"
        )
        html += "</div>"
        html += '<div x-init="setTimeout(() => step = 2, 1500)"></div>'
    else:
        html += "</div>"
        html += (
            '<div class="flex gap-3 mt-4">'
            '<button type="submit" '
            'class="px-4 py-2 rounded-md bg-brand-600 text-white font-medium '
            'hover:bg-brand-700">'
            "Retry</button>"
            '<button type="button" '
            "@click=\"document.getElementById('scanner-verify-result')"
            ".textContent = ''\" "
            'class="px-4 py-2 rounded-md text-text-secondary hover:bg-gray-100">'
            "Try a different scanner</button>"
            "</div>"
        )

    return HTMLResponse(html)


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
    from scanbox.scanner.discovery import BRIDGE_NETWORK_HINT, mdns_available

    data = _read_setup()
    cfg = Config()
    can_discover = mdns_available()
    return templates.TemplateResponse(
        request,
        "setup.html",
        {
            "current_step": data.get("current_step", 1),
            "total_steps": TOTAL_STEPS,
            "scanner_configured": bool(cfg.SCANNER_IP),
            "mdns_available": can_discover,
            "mdns_hint": None if can_discover else BRIDGE_NETWORK_HINT,
        },
    )
