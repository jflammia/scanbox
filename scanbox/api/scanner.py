"""Scanner status and capabilities API endpoints."""

from fastapi import APIRouter, HTTPException

from scanbox.config import Config
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
        }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Can't reach the scanner. Is it turned on?",
        ) from exc
    finally:
        await client.close()


def _status_message(state: str, adf_loaded: bool) -> str:
    state_lower = state.lower()
    if state_lower == "idle" and adf_loaded:
        return "Scanner ready — pages loaded in feeder"
    if state_lower == "idle":
        return "Scanner ready"
    if state_lower == "processing":
        return "Scanner is busy"
    return f"Scanner state: {state}"
