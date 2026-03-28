"""MCP server for ScanBox — AI agent integration via Model Context Protocol."""

import httpx
from mcp.server.fastmcp import FastMCP

from scanbox.config import Config

mcp = FastMCP("scanbox")

_BASE_URL = "http://localhost:8090"


def _base_url() -> str:
    """Get the base URL for internal API calls."""
    return _BASE_URL


# --- Health & Status ---


@mcp.tool()
async def scanbox_health_check() -> dict:
    """Check system health — scanner connectivity, LLM availability, storage status."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{_base_url()}/api/health")
        return resp.json()


@mcp.tool()
async def scanbox_get_scanner_status() -> dict:
    """Get the current scanner status with a human-readable message."""
    cfg = Config()
    return {
        "scanner_ip": cfg.SCANNER_IP or "not configured",
        "message": "Scanner configured" if cfg.SCANNER_IP else "No scanner configured",
    }


# --- Persons ---


@mcp.tool()
async def scanbox_manage_persons(action: str, display_name: str = "", person_id: str = "") -> dict:
    """Create, list, get, or delete person profiles. Actions: list, create, get, delete."""
    async with httpx.AsyncClient() as client:
        if action == "list":
            resp = await client.get(f"{_base_url()}/api/persons")
            return resp.json()
        elif action == "create":
            resp = await client.post(
                f"{_base_url()}/api/persons", json={"display_name": display_name}
            )
            return resp.json()
        elif action == "get":
            resp = await client.get(f"{_base_url()}/api/persons/{person_id}")
            return resp.json()
        elif action == "delete":
            resp = await client.delete(f"{_base_url()}/api/persons/{person_id}")
            return {"deleted": resp.status_code == 204}
        return {"error": f"Unknown action: {action}"}


# --- Sessions ---


@mcp.tool()
async def scanbox_create_session(person_id: str) -> dict:
    """Create a new scanning session for a person. Also creates the first batch."""
    async with httpx.AsyncClient() as client:
        session_resp = await client.post(
            f"{_base_url()}/api/sessions", json={"person_id": person_id}
        )
        session = session_resp.json()
        batch_resp = await client.post(f"{_base_url()}/api/sessions/{session['id']}/batches")
        batch = batch_resp.json()
        return {
            "session_id": session["id"],
            "batch_id": batch["id"],
            "message": "Session created. Ready to scan front pages.",
        }


@mcp.tool()
async def scanbox_list_sessions(person_id: str = "") -> dict:
    """List all scanning sessions, optionally filtered by person."""
    async with httpx.AsyncClient() as client:
        params = {}
        if person_id:
            params["person_id"] = person_id
        resp = await client.get(f"{_base_url()}/api/sessions", params=params)
        return resp.json()


# --- Scanning ---


@mcp.tool()
async def scanbox_scan_fronts(batch_id: str) -> dict:
    """Start scanning front pages. The scanner's ADF begins feeding immediately."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{_base_url()}/api/batches/{batch_id}/scan/fronts")
        return resp.json()


@mcp.tool()
async def scanbox_scan_backs(batch_id: str) -> dict:
    """Start scanning back pages (after the stack has been flipped)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{_base_url()}/api/batches/{batch_id}/scan/backs")
        return resp.json()


@mcp.tool()
async def scanbox_skip_backs(batch_id: str) -> dict:
    """Skip back-side scanning for single-sided documents."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{_base_url()}/api/batches/{batch_id}/skip-backs")
        return resp.json()


# --- Batches ---


@mcp.tool()
async def scanbox_get_batch_status(batch_id: str) -> dict:
    """Get the current status and processing stage of a batch."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{_base_url()}/api/batches/{batch_id}")
        return resp.json()


# --- Documents ---


@mcp.tool()
async def scanbox_list_documents(batch_id: str) -> dict:
    """List all documents in a batch."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{_base_url()}/api/batches/{batch_id}/documents")
        return resp.json()


@mcp.tool()
async def scanbox_get_document(document_id: str) -> dict:
    """Get details of a specific document."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{_base_url()}/api/documents/{document_id}")
        return resp.json()


@mcp.tool()
async def scanbox_update_document(
    document_id: str,
    document_type: str = "",
    date_of_service: str = "",
    facility: str = "",
    provider: str = "",
    description: str = "",
) -> dict:
    """Update document metadata (type, date, facility, provider, description)."""
    updates = {}
    if document_type:
        updates["document_type"] = document_type
    if date_of_service:
        updates["date_of_service"] = date_of_service
    if facility:
        updates["facility"] = facility
    if provider:
        updates["provider"] = provider
    if description:
        updates["description"] = description

    async with httpx.AsyncClient() as client:
        resp = await client.put(f"{_base_url()}/api/documents/{document_id}", json=updates)
        return resp.json()


# --- Boundaries ---


@mcp.tool()
async def scanbox_adjust_boundaries(batch_id: str, splits: list[dict]) -> dict:
    """Adjust document boundaries. Each split has start_page and end_page."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_base_url()}/api/batches/{batch_id}/splits",
            json={"splits": splits},
        )
        return resp.json()


# --- Save ---


@mcp.tool()
async def scanbox_save_batch(batch_id: str) -> dict:
    """Save all documents to output destinations (archive, medical-records)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{_base_url()}/api/batches/{batch_id}/save")
        return resp.json()


# --- Resources ---


@mcp.resource("scanbox://status")
async def get_status() -> str:
    """Current system status."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{_base_url()}/api/health")
        return str(resp.json())


@mcp.resource("scanbox://sessions")
async def get_sessions() -> str:
    """List of all sessions."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{_base_url()}/api/sessions")
        return str(resp.json())


# --- Prompts ---


@mcp.prompt()
def review_batch(batch_id: str) -> str:
    """Generate a prompt for reviewing documents in a batch."""
    return (
        f"Please review the documents in batch {batch_id}. "
        "List each document with its type, date, and facility. "
        "Flag any that look incorrect or have low confidence. "
        "Suggest corrections for any metadata that seems wrong."
    )


@mcp.prompt()
def classify_document(document_id: str) -> str:
    """Generate a prompt for classifying a specific document."""
    return (
        f"Look at document {document_id} and determine: "
        "1. What type of medical document is this? "
        "2. What is the date of service? "
        "3. Which facility or provider issued it? "
        "4. Write a brief description."
    )
