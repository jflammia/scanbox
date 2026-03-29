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
async def scanbox_adjust_boundaries(batch_id: str, boundaries: list[dict]) -> dict:
    """Adjust document boundaries. Each boundary has start_page and end_page."""
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{_base_url()}/api/batches/{batch_id}/boundaries",
            json={"boundaries": boundaries},
        )
        return resp.json()


# --- Pipeline Status ---


@mcp.tool()
async def scanbox_get_pipeline_status(batch_id: str) -> dict:
    """Get the current processing stage and progress for a batch."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{_base_url()}/api/batches/{batch_id}/progress")
        return resp.json()


@mcp.tool()
async def scanbox_reprocess_batch(batch_id: str) -> dict:
    """Re-run the processing pipeline on a batch's existing scans."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{_base_url()}/api/batches/{batch_id}/reprocess")
        return resp.json()


# --- Save ---


@mcp.tool()
async def scanbox_save_batch(batch_id: str) -> dict:
    """Save all documents to output destinations (archive, medical-records)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{_base_url()}/api/batches/{batch_id}/save")
        return resp.json()


# --- Onboarding & Troubleshooting ---


@mcp.tool()
async def scanbox_setup_guide() -> dict:
    """Get the setup wizard status and a step-by-step guide for configuring ScanBox.

    Returns the current setup progress and instructions for each step:
    scanner connection, LLM provider, PaperlessNGX (optional), and first scan.
    Use this to help users get started or resume an incomplete setup.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{_base_url()}/api/setup/status")
        status = resp.json()

    steps = [
        {
            "step": 1,
            "name": "Scanner Connection",
            "description": "Set the SCANNER_IP environment variable to your scanner's IP address. "
            "The scanner must support eSCL/AirScan protocol. "
            "You may need to enable WebScan in your printer's Embedded Web Server settings.",
            "test_command": "Use scanbox_test_connection(service='scanner') to verify.",
        },
        {
            "step": 2,
            "name": "LLM Provider",
            "description": "Set LLM_PROVIDER to 'anthropic', 'openai', or 'ollama'. "
            "Then set the corresponding API key (ANTHROPIC_API_KEY, OPENAI_API_KEY) "
            "or OLLAMA_URL for local models. The LLM splits scanned pages into documents.",
            "test_command": "Use scanbox_test_connection(service='llm') to verify.",
        },
        {
            "step": 3,
            "name": "Output Directory",
            "description": "The OUTPUT_DIR environment variable controls where organized documents "
            "are saved. Default is /output. Ensure this path is writable.",
        },
        {
            "step": 4,
            "name": "PaperlessNGX (Optional)",
            "description": "Set PAPERLESS_URL and PAPERLESS_API_TOKEN to enable automatic upload "
            "to PaperlessNGX. Skip this step if you don't use Paperless.",
            "test_command": "Use scanbox_test_connection(service='paperless') to verify.",
        },
        {
            "step": 5,
            "name": "Create a Person",
            "description": "Create at least one person profile for organizing scanned documents. "
            "Use scanbox_manage_persons(action='create', display_name='Name').",
        },
        {
            "step": 6,
            "name": "Test Scan",
            "description": "Load 1-5 pages in the scanner and run a test scan. "
            "Create a session, scan fronts, skip backs (if single-sided), "
            "review the AI-split results, then save.",
        },
    ]

    return {
        "setup_completed": status.get("completed", False),
        "current_step": status.get("current_step", 1),
        "total_steps": status.get("total_steps", 6),
        "steps": steps,
    }


@mcp.tool()
async def scanbox_test_connection(service: str) -> dict:
    """Test connectivity to a specific service or all services at once.

    Args:
        service: Which service to test. One of: 'scanner', 'llm', 'paperless', 'all'.
    """
    valid_services = {"scanner", "llm", "paperless", "all"}
    if service not in valid_services:
        return {
            "error": f"Unknown service: {service}. Use one of: {', '.join(sorted(valid_services))}"
        }

    async with httpx.AsyncClient() as client:
        if service == "all":
            results = {}
            for svc in ("scanner", "llm", "paperless"):
                resp = await client.post(f"{_base_url()}/api/setup/test-{svc}")
                data = resp.json()
                results[svc] = data
            return results

        resp = await client.post(f"{_base_url()}/api/setup/test-{service}")
        data = resp.json()
        data["service"] = service
        return data


@mcp.tool()
async def scanbox_diagnose_system() -> dict:
    """Run a comprehensive system diagnostic.

    Checks health of all subsystems (API, database, scanner, LLM, storage, Paperless),
    setup completion status, and session count. Returns a list of issues with
    plain-English explanations and suggested fixes. Use this to troubleshoot problems.
    """
    async with httpx.AsyncClient() as client:
        health_resp = await client.get(f"{_base_url()}/api/health")
        health = health_resp.json()

        setup_resp = await client.get(f"{_base_url()}/api/setup/status")
        setup = setup_resp.json()

        sessions_resp = await client.get(f"{_base_url()}/api/sessions")
        sessions = sessions_resp.json()

    issues = []

    # Check database
    if health.get("database") != "ok":
        issues.append(
            "Database is not responding. The internal data directory may be "
            "missing or corrupted. Check INTERNAL_DATA_DIR."
        )

    # Check scanner
    scanner_status = health.get("scanner", "not configured")
    if scanner_status == "not configured":
        issues.append("Scanner is not configured. Set the SCANNER_IP environment variable.")
    elif scanner_status == "unreachable":
        issues.append(
            "Scanner is unreachable. Check that the scanner is powered on, "
            "connected to the network, and WebScan is enabled in its settings."
        )

    # Check storage
    storage = health.get("storage", {})
    if storage.get("internal") != "ok":
        issues.append("Internal storage directory is missing. Check INTERNAL_DATA_DIR.")
    if storage.get("output") != "ok":
        issues.append("Output directory is missing. Check OUTPUT_DIR and ensure it exists.")

    # Check LLM
    llm = health.get("llm", {})
    if not llm.get("configured"):
        issues.append(
            "LLM provider is not configured. Set LLM_PROVIDER and the "
            "corresponding API key (ANTHROPIC_API_KEY, OPENAI_API_KEY, or OLLAMA_URL)."
        )

    # Check setup
    if not setup.get("completed"):
        issues.append(
            "Initial setup is not complete. Use scanbox_setup_guide() to see remaining steps."
        )

    summary = "All systems operational." if not issues else f"{len(issues)} issue(s) found."

    return {
        "health": health,
        "setup": setup,
        "session_count": len(sessions.get("items", [])),
        "issues": issues,
        "summary": summary,
    }


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


@mcp.prompt()
def onboarding() -> str:
    """Guide a new user through ScanBox setup and first scan."""
    return (
        "Help the user set up ScanBox step by step. Start by running "
        "scanbox_diagnose_system() to check the current state. Then use "
        "scanbox_setup_guide() to see which steps remain. For each step:\n"
        "1. Explain what needs to be configured and why\n"
        "2. Help them set the right environment variables\n"
        "3. Test the connection with scanbox_test_connection()\n"
        "4. Move to the next step once verified\n\n"
        "After setup is complete, walk them through their first scan:\n"
        "- Create a person profile\n"
        "- Create a session and batch\n"
        "- Scan front pages (have them load 1-5 pages in the ADF)\n"
        "- Skip backs if single-sided, or scan backs if double-sided\n"
        "- Review the AI-split documents\n"
        "- Save the results\n\n"
        "Use plain English. The user may not be technical."
    )


@mcp.prompt()
def troubleshoot() -> str:
    """Diagnose and fix issues with ScanBox."""
    return (
        "The user is having trouble with ScanBox. Run scanbox_diagnose_system() "
        "to check all subsystems. For each issue found:\n"
        "1. Explain the problem in plain English\n"
        "2. Suggest the most likely fix\n"
        "3. Test the fix with scanbox_test_connection()\n\n"
        "Common issues:\n"
        "- Scanner unreachable: check power, network, WebScan setting in printer EWS\n"
        "- LLM not configured: need API key or Ollama running locally\n"
        "- Output directory missing: check the volume mount in docker-compose.yml\n"
        "- Processing stuck: try scanbox_reprocess_batch() on the affected batch\n\n"
        "If the issue persists after fixes, check scanbox_health_check() for details."
    )
