"""FastAPI application for ScanBox."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from scanbox.config import Config
from scanbox.database import Database

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
    yield
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


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Static files
_static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# Import and include routers after app creation to avoid circular imports
from scanbox.api.batches import router as batches_router  # noqa: E402
from scanbox.api.documents import router as documents_router  # noqa: E402
from scanbox.api.persons import router as persons_router  # noqa: E402
from scanbox.api.sessions import router as sessions_router  # noqa: E402
from scanbox.api.views import router as views_router  # noqa: E402

app.include_router(persons_router)
app.include_router(sessions_router)
app.include_router(batches_router)
app.include_router(documents_router)
app.include_router(views_router)
