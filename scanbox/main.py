"""FastAPI application for ScanBox."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from scanbox.config import Config
from scanbox.database import Database
from scanbox.scanner.monitor import scanner_monitor

_db: Database | None = None


def get_db() -> Database:
    """Get the database instance."""
    assert _db is not None, "Database not initialized"
    return _db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: init DB on startup, close on shutdown."""
    global _db
    cfg = Config()
    db_path = cfg.INTERNAL_DATA_DIR / "scanbox.db"
    _db = Database(db_path)
    await _db.init()

    # Mount MCP server if enabled
    if cfg.MCP_ENABLED:
        from scanbox.mcp.server import mcp as mcp_server

        app.mount("/mcp", mcp_server.streamable_http_app())

    # Start scanner monitoring
    if cfg.SCANNER_IP:
        await scanner_monitor.start(cfg.SCANNER_IP)

    yield

    await scanner_monitor.stop()
    await _db.close()
    _db = None


app = FastAPI(
    title="ScanBox",
    description="Medical document scanning, splitting, and archival pipeline",
    version="0.0.1",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Paths that bypass API key auth
_AUTH_EXEMPT = {"/api/health", "/api/openapi.json", "/api/docs", "/api/redoc"}


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """Optional bearer token auth for /api/ routes when SCANBOX_API_KEY is set."""
    cfg = Config()
    if (
        cfg.SCANBOX_API_KEY
        and request.url.path.startswith("/api/")
        and request.url.path not in _AUTH_EXEMPT
    ):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {cfg.SCANBOX_API_KEY}":
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )
    return await call_next(request)


@app.get("/api/health", tags=["system"])
async def health():
    """Check system health — API, database, scanner, LLM, and storage status."""
    cfg = Config()
    checks: dict = {"api": "ok"}

    # Database
    try:
        db = get_db()
        await db.list_persons()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    # Scanner
    if cfg.SCANNER_IP:
        try:
            from scanbox.scanner.escl import ESCLClient

            client = ESCLClient(cfg.SCANNER_IP)
            try:
                await client.get_status()
                checks["scanner"] = "ok"
            finally:
                await client.close()
        except Exception:
            checks["scanner"] = "unreachable"
    else:
        checks["scanner"] = "not configured"

    # Storage
    checks["storage"] = {
        "internal": "ok" if cfg.INTERNAL_DATA_DIR.exists() else "missing",
        "output": "ok" if cfg.OUTPUT_DIR.exists() else "missing",
    }

    # LLM
    checks["llm"] = {
        "provider": cfg.LLM_PROVIDER,
        "model": cfg.llm_model_id(),
        "configured": bool(
            cfg.ANTHROPIC_API_KEY or cfg.OPENAI_API_KEY or cfg.LLM_PROVIDER == "ollama"
        ),
    }

    # PaperlessNGX
    if cfg.PAPERLESS_URL:
        checks["paperless"] = {"url": cfg.PAPERLESS_URL, "configured": True}
    else:
        checks["paperless"] = {"configured": False}

    overall = "ok"
    if checks["database"] != "ok":
        overall = "degraded"
    return {"status": overall, "version": cfg.APP_VERSION, **checks}


# Static files
_static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# Import and include routers after app creation to avoid circular imports
from scanbox.api.batches import router as batches_router  # noqa: E402
from scanbox.api.boundaries import router as boundaries_router  # noqa: E402
from scanbox.api.calibration import router as calibration_router  # noqa: E402
from scanbox.api.documents import router as documents_router  # noqa: E402
from scanbox.api.persons import router as persons_router  # noqa: E402
from scanbox.api.practice import router as practice_router  # noqa: E402
from scanbox.api.scanner import router as scanner_router  # noqa: E402
from scanbox.api.scanning import router as scanning_router  # noqa: E402
from scanbox.api.sessions import router as sessions_router  # noqa: E402
from scanbox.api.setup import router as setup_router  # noqa: E402
from scanbox.api.views import router as views_router  # noqa: E402
from scanbox.api.webhooks import router as webhooks_router  # noqa: E402

app.include_router(persons_router)
app.include_router(sessions_router)
app.include_router(batches_router)
app.include_router(calibration_router)
app.include_router(boundaries_router)
app.include_router(documents_router)
app.include_router(setup_router)
app.include_router(practice_router)
app.include_router(scanner_router)
app.include_router(scanning_router)
app.include_router(webhooks_router)
app.include_router(views_router)
