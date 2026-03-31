"""Scanner status and capabilities API endpoints."""

from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from scanbox.config import Config
from scanbox.scanner.discovery import (
    BRIDGE_NETWORK_HINT,
    DISCOVERY_HINT,
    discover_scanners,
    mdns_available,
)
from scanbox.scanner.escl import ESCLClient

router = APIRouter(tags=["scanner"])


@router.get("/api/scanner/status")
async def scanner_status():
    """Get the current scanner status as JSON."""
    cfg = Config()
    if not cfg.SCANNER_IP:
        raise HTTPException(status_code=503, detail="No scanner configured. Set SCANNER_IP.")

    client = ESCLClient(cfg.SCANNER_IP)
    try:
        status = await client.get_status()
        return {
            "status": status.state.lower(),
            "ip": cfg.SCANNER_IP,
            "adf_loaded": status.adf_loaded,
            "adf_state": status.adf_state,
            "message": _status_message(status.state, status.adf_loaded),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Can't reach the scanner. Is it turned on?",
        ) from exc
    finally:
        await client.close()


@router.get("/api/scanner/capabilities")
async def scanner_capabilities():
    """Get scanner capabilities (model, resolutions, formats, ADF support)."""
    cfg = Config()
    if not cfg.SCANNER_IP:
        raise HTTPException(status_code=503, detail="No scanner configured. Set SCANNER_IP.")

    client = ESCLClient(cfg.SCANNER_IP)
    try:
        caps = await client.get_capabilities()
        return {
            "make_and_model": caps.make_and_model,
            "has_adf": caps.has_adf,
            "has_duplex_adf": caps.has_duplex_adf,
            "supported_resolutions": caps.supported_resolutions,
            "supported_formats": caps.supported_formats,
            "icon_url": "/api/scanner/icon" if caps.icon_url else None,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Can't reach the scanner. Is it turned on?",
        ) from exc
    finally:
        await client.close()


@router.get("/api/scanner/icon")
async def scanner_icon():
    """Proxy the scanner's icon image."""
    cfg = Config()
    if not cfg.SCANNER_IP:
        raise HTTPException(status_code=404, detail="No scanner configured")

    client = ESCLClient(cfg.SCANNER_IP)
    try:
        caps = await client.get_capabilities()
        if not caps.icon_url:
            raise HTTPException(status_code=404, detail="Scanner has no icon")

        parsed = urlparse(caps.icon_url)
        icon_path = parsed.path  # e.g., /ipp/images/printer.png
        icon_url = f"http://{cfg.SCANNER_IP}{icon_path}"

        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(icon_url)
            if resp.status_code == 200:
                return Response(
                    content=resp.content,
                    media_type=resp.headers.get("content-type", "image/png"),
                )
        raise HTTPException(status_code=404, detail="Could not fetch scanner icon")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Could not fetch scanner icon") from None
    finally:
        await client.close()


@router.get("/api/scanner/mdns-available")
async def scanner_mdns_check():
    """Check if mDNS discovery is available (host networking vs bridge)."""
    available = mdns_available()
    return {
        "available": available,
        "hint": None if available else BRIDGE_NETWORK_HINT,
    }


@router.post("/api/scanner/discover")
async def scanner_discover(timeout: float = Query(default=5.0)):
    """Discover eSCL scanners on the local network via mDNS."""
    if not mdns_available():
        return {
            "scanners": [],
            "count": 0,
            "mdns_available": False,
            "hint": BRIDGE_NETWORK_HINT,
        }
    timeout = max(1.0, min(30.0, timeout))
    scanners = await discover_scanners(timeout=timeout)
    return {
        "scanners": [
            {
                "ip": s.ip,
                "port": s.port,
                "model": s.model,
                "name": s.name,
                "uuid": s.uuid,
                "icon_url": s.icon_url,
                "secure": s.secure,
            }
            for s in scanners
        ],
        "count": len(scanners),
        "mdns_available": True,
        "hint": DISCOVERY_HINT if len(scanners) == 0 else None,
    }


def _status_message(state: str, adf_loaded: bool) -> str:
    state_lower = state.lower()
    if state_lower == "idle" and adf_loaded:
        return "Scanner ready — pages loaded in feeder"
    if state_lower == "idle":
        return "Scanner ready"
    if state_lower == "processing":
        return "Scanner is busy"
    return f"Scanner state: {state}"
