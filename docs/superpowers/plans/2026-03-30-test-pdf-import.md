# Test PDF Import System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Enable pre-made PDFs to enter the ScanBox pipeline without a physical scanner — via an API endpoint for interactive dev and pytest fixtures for automated/CI testing.

**Architecture:** Shared `import_batch()` function in `scanbox/api/import_batch.py` creates DB records (person, session, batch) and writes PDFs to the correct batch directory. The API endpoint and pytest fixtures both call this function, then trigger the existing pipeline. No changes to the pipeline itself.

**Tech Stack:** FastAPI (multipart upload), pikepdf (page counting), aiosqlite (DB), pytest fixtures, httpx (API testing)

**Spec:** `docs/superpowers/specs/2026-03-30-test-pdf-import-design.md`

---

## File Map

### New files

| File | Responsibility |
|------|---------------|
| `scanbox/api/import_batch.py` | Shared `import_batch()` + `ImportResult` dataclass |
| `tests/unit/test_import_batch.py` | Unit tests for `import_batch()` |
| `tests/integration/test_import_api.py` | API endpoint integration tests |
| `tests/integration/test_pipeline_import.py` | Pipeline integration tests using test fixtures |

### Modified files

| File | Change |
|------|--------|
| `scanbox/api/scanning.py` | Add `POST /api/batches/import` endpoint |
| `scanbox/main.py` | Import and include the scanning router (already done — scanning routes are in `scanning.py` but we need to check if the router is mounted) |
| `tests/conftest.py` | Add `load_test_pile` factory fixture + stage-level fixtures + `db` fixture |

---

## Task 1: Create `import_batch()` core function

**Files:**
- Create: `scanbox/api/import_batch.py`
- Test: `tests/unit/test_import_batch.py`

- [x] **Step 1: Write failing tests for import_batch**

Create `tests/unit/test_import_batch.py`:

```python
"""Tests for the shared import_batch function."""

import pikepdf
import pytest

from scanbox.api.import_batch import ImportResult, import_batch
from scanbox.database import Database


def _make_pdf_bytes(num_pages: int = 3) -> bytes:
    """Create a valid PDF with the given number of blank pages."""
    from io import BytesIO

    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.add_blank_page(page_size=(612, 792))
    buf = BytesIO()
    pdf.save(buf)
    return buf.getvalue()


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.init()
    yield database
    await database.close()


class TestImportBatch:
    async def test_returns_import_result(self, db, tmp_path):
        fronts = _make_pdf_bytes(3)
        result = await import_batch(db, tmp_path, fronts)
        assert isinstance(result, ImportResult)
        assert result.batch_id.startswith("batch-")
        assert result.session_id.startswith("sess-")
        assert result.fronts_page_count == 3
        assert result.backs_page_count is None
        assert result.has_backs is False

    async def test_creates_person_session_batch(self, db, tmp_path):
        fronts = _make_pdf_bytes(2)
        result = await import_batch(db, tmp_path, fronts, person_name="Elena Martinez")
        person = await db.get_person(result.person_id)
        assert person is not None
        assert person["display_name"] == "Elena Martinez"
        session = await db.get_session(result.session_id)
        assert session is not None
        batch = await db.get_batch(result.batch_id)
        assert batch is not None
        assert batch["state"] == "backs_skipped"

    async def test_with_backs(self, db, tmp_path):
        fronts = _make_pdf_bytes(5)
        backs = _make_pdf_bytes(5)
        result = await import_batch(db, tmp_path, fronts, backs_bytes=backs)
        assert result.has_backs is True
        assert result.fronts_page_count == 5
        assert result.backs_page_count == 5
        batch = await db.get_batch(result.batch_id)
        assert batch["state"] == "backs_done"

    async def test_writes_pdfs_to_batch_dir(self, db, tmp_path):
        fronts = _make_pdf_bytes(3)
        backs = _make_pdf_bytes(3)
        result = await import_batch(db, tmp_path, fronts, backs_bytes=backs)
        assert (result.batch_dir / "fronts.pdf").exists()
        assert (result.batch_dir / "backs.pdf").exists()

    async def test_fronts_only_no_backs_file(self, db, tmp_path):
        fronts = _make_pdf_bytes(2)
        result = await import_batch(db, tmp_path, fronts)
        assert (result.batch_dir / "fronts.pdf").exists()
        assert not (result.batch_dir / "backs.pdf").exists()

    async def test_default_person_name(self, db, tmp_path):
        fronts = _make_pdf_bytes(1)
        result = await import_batch(db, tmp_path, fronts)
        person = await db.get_person(result.person_id)
        assert person["display_name"] == "Test Patient"

    async def test_reuses_existing_person(self, db, tmp_path):
        fronts = _make_pdf_bytes(1)
        r1 = await import_batch(db, tmp_path, fronts, person_name="John Doe")
        r2 = await import_batch(db, tmp_path, fronts, person_name="John Doe")
        assert r1.person_id == r2.person_id
        # But different sessions
        assert r1.session_id != r2.session_id

    async def test_page_counts_match_pdf(self, db, tmp_path):
        fronts = _make_pdf_bytes(7)
        backs = _make_pdf_bytes(7)
        result = await import_batch(db, tmp_path, fronts, backs_bytes=backs)
        batch = await db.get_batch(result.batch_id)
        assert batch["fronts_page_count"] == 7
        assert batch["backs_page_count"] == 7
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_import_batch.py -v 2>&1 | tail -5`
Expected: FAIL — `ImportError: cannot import name 'import_batch'`

- [x] **Step 3: Implement import_batch**

Create `scanbox/api/import_batch.py`:

```python
"""Shared batch import function — creates DB records and writes PDFs.

Used by both the API import endpoint and pytest fixtures to inject
pre-made PDFs into the pipeline without a physical scanner.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pikepdf

from scanbox.database import Database


@dataclass
class ImportResult:
    """Result of importing PDFs into a new batch."""

    batch_id: str
    session_id: str
    person_id: str
    batch_dir: Path
    has_backs: bool
    fronts_page_count: int
    backs_page_count: int | None


async def import_batch(
    db: Database,
    data_dir: Path,
    fronts_bytes: bytes,
    backs_bytes: bytes | None = None,
    person_name: str = "Test Patient",
) -> ImportResult:
    """Import PDFs into a new session and batch.

    Creates person (if needed), session, and batch records in the database.
    Writes fronts.pdf and optionally backs.pdf to the batch directory.
    Sets batch state to 'backs_done' (if backs provided) or 'backs_skipped'.

    Args:
        db: Database instance
        data_dir: Root data directory (config.INTERNAL_DATA_DIR)
        fronts_bytes: Raw bytes of the fronts PDF
        backs_bytes: Raw bytes of the backs PDF, or None for single-sided
        person_name: Display name for the person record

    Returns:
        ImportResult with all IDs, paths, and page counts
    """
    # Find or create person
    person = await _find_or_create_person(db, person_name)

    # Create session and batch
    session = await db.create_session(person["id"])
    batch = await db.create_batch(session["id"])

    # Write PDFs to batch directory
    batch_dir = data_dir / "sessions" / session["id"] / "batches" / batch["id"]
    batch_dir.mkdir(parents=True, exist_ok=True)

    fronts_path = batch_dir / "fronts.pdf"
    fronts_path.write_bytes(fronts_bytes)
    fronts_page_count = _count_pages(fronts_bytes)

    backs_page_count = None
    has_backs = backs_bytes is not None
    if has_backs:
        backs_path = batch_dir / "backs.pdf"
        backs_path.write_bytes(backs_bytes)
        backs_page_count = _count_pages(backs_bytes)

    # Update batch state and page counts
    state = "backs_done" if has_backs else "backs_skipped"
    await db.update_batch_state(
        batch["id"],
        state,
        fronts_page_count=fronts_page_count,
        backs_page_count=backs_page_count or 0,
    )

    return ImportResult(
        batch_id=batch["id"],
        session_id=session["id"],
        person_id=person["id"],
        batch_dir=batch_dir,
        has_backs=has_backs,
        fronts_page_count=fronts_page_count,
        backs_page_count=backs_page_count,
    )


async def _find_or_create_person(db: Database, display_name: str) -> dict:
    """Look up a person by name, or create if not found."""
    persons = await db.list_persons()
    for p in persons:
        if p["display_name"] == display_name:
            return p
    return await db.create_person(display_name)


def _count_pages(pdf_bytes: bytes) -> int:
    """Count pages in a PDF from raw bytes."""
    pdf = pikepdf.Pdf.open(BytesIO(pdf_bytes))
    return len(pdf.pages)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_import_batch.py -v`
Expected: All 8 tests PASS

- [x] **Step 5: Format and lint**

Run: `ruff format scanbox/api/import_batch.py tests/unit/test_import_batch.py && ruff check scanbox/api/import_batch.py tests/unit/test_import_batch.py`

- [x] **Step 6: Commit**

```bash
git add scanbox/api/import_batch.py tests/unit/test_import_batch.py
git commit -m "feat: add shared import_batch function for injecting PDFs into pipeline"
```

---

## Task 2: Add API endpoint `POST /api/batches/import`

**Files:**
- Modify: `scanbox/api/scanning.py`
- Test: `tests/integration/test_import_api.py`

- [x] **Step 1: Write failing tests for the API endpoint**

Create `tests/integration/test_import_api.py`:

```python
"""Tests for POST /api/batches/import endpoint."""

import pikepdf
import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app, get_db


def _make_pdf_bytes(num_pages: int = 3) -> bytes:
    from io import BytesIO

    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.add_blank_page(page_size=(612, 792))
    buf = BytesIO()
    pdf.save(buf)
    return buf.getvalue()


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "output").mkdir()

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestImportEndpoint:
    async def test_fronts_only(self, client):
        fronts = _make_pdf_bytes(3)
        resp = await client.post(
            "/api/batches/import",
            files={"fronts": ("fronts.pdf", fronts, "application/pdf")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "batch_id" in data
        assert data["has_backs"] is False
        assert data["fronts_pages"] == 3

    async def test_fronts_and_backs(self, client):
        fronts = _make_pdf_bytes(5)
        backs = _make_pdf_bytes(5)
        resp = await client.post(
            "/api/batches/import",
            files={
                "fronts": ("fronts.pdf", fronts, "application/pdf"),
                "backs": ("backs.pdf", backs, "application/pdf"),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["has_backs"] is True
        assert data["fronts_pages"] == 5
        assert data["backs_pages"] == 5

    async def test_custom_person_name(self, client):
        fronts = _make_pdf_bytes(1)
        resp = await client.post(
            "/api/batches/import",
            files={"fronts": ("fronts.pdf", fronts, "application/pdf")},
            data={"person_name": "Elena Martinez"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["person_id"] == "elena-martinez"

    async def test_missing_fronts_returns_400(self, client):
        resp = await client.post("/api/batches/import")
        assert resp.status_code == 422  # FastAPI validation error

    async def test_invalid_pdf_returns_400(self, client):
        resp = await client.post(
            "/api/batches/import",
            files={"fronts": ("fronts.pdf", b"not a pdf", "application/pdf")},
        )
        assert resp.status_code == 400

    async def test_batch_state_after_import(self, client):
        fronts = _make_pdf_bytes(2)
        resp = await client.post(
            "/api/batches/import",
            files={"fronts": ("fronts.pdf", fronts, "application/pdf")},
        )
        batch_id = resp.json()["batch_id"]
        # Check batch via API
        batch_resp = await client.get(f"/api/batches/{batch_id}")
        assert batch_resp.status_code == 200
        # State should be backs_skipped or processing (background task may have started)
        assert batch_resp.json()["state"] in ("backs_skipped", "processing", "review", "error")

    async def test_status_url_in_response(self, client):
        fronts = _make_pdf_bytes(1)
        resp = await client.post(
            "/api/batches/import",
            files={"fronts": ("fronts.pdf", fronts, "application/pdf")},
        )
        data = resp.json()
        assert "status_url" in data
        assert data["batch_id"] in data["status_url"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_import_api.py -v 2>&1 | tail -5`
Expected: FAIL — 404 (endpoint doesn't exist yet)

- [x] **Step 3: Add the import endpoint to scanning.py**

Read `scanbox/api/scanning.py` first, then add the import endpoint. The scanning module doesn't currently have a router — it's called directly by other modules. We need to add a router.

Add to the top of `scanbox/api/scanning.py`:

```python
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from scanbox.api.import_batch import import_batch
from scanbox.main import get_db

router = APIRouter(prefix="/api", tags=["scanning"])
```

Add the endpoint at the bottom of the file:

```python
@router.post("/batches/import", status_code=201)
async def import_batch_endpoint(
    fronts: UploadFile = File(...),
    backs: UploadFile | None = File(None),
    person_name: str = Form("Test Patient"),
):
    """Import pre-made PDFs as a new batch, bypassing the scanner.

    Accepts fronts PDF (required) and optional backs PDF.
    Creates person, session, and batch records, then triggers pipeline processing.
    """
    from scanbox.config import Config

    db = get_db()
    cfg = Config()

    fronts_bytes = await fronts.read()

    # Validate fronts is a real PDF
    try:
        pikepdf.Pdf.open(BytesIO(fronts_bytes))
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Invalid PDF file for fronts"})

    backs_bytes = None
    if backs is not None:
        backs_bytes = await backs.read()
        if backs_bytes:
            try:
                pikepdf.Pdf.open(BytesIO(backs_bytes))
            except Exception:
                return JSONResponse(
                    status_code=400, content={"detail": "Invalid PDF file for backs"}
                )
        else:
            backs_bytes = None

    result = await import_batch(
        db=db,
        data_dir=cfg.INTERNAL_DATA_DIR,
        fronts_bytes=fronts_bytes,
        backs_bytes=backs_bytes,
        person_name=person_name,
    )

    # Trigger pipeline processing as background task
    import asyncio

    asyncio.create_task(
        _run_processing(result.batch_id, db, has_backs=result.has_backs)
    )

    return {
        "batch_id": result.batch_id,
        "session_id": result.session_id,
        "person_id": result.person_id,
        "state": "processing",
        "has_backs": result.has_backs,
        "fronts_pages": result.fronts_page_count,
        "backs_pages": result.backs_page_count,
        "status_url": f"/api/batches/{result.batch_id}",
    }
```

- [x] **Step 4: Register the router in main.py**

Add to `scanbox/main.py` (in the router imports section around line 136-145):

```python
from scanbox.api.scanning import router as scanning_router  # noqa: E402
```

And in the `app.include_router` section:

```python
app.include_router(scanning_router)
```

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest tests/integration/test_import_api.py -v`
Expected: All 7 tests PASS

- [x] **Step 6: Format and lint**

Run: `ruff format scanbox/api/scanning.py scanbox/api/import_batch.py scanbox/main.py tests/integration/test_import_api.py && ruff check scanbox/api/scanning.py scanbox/api/import_batch.py scanbox/main.py tests/integration/test_import_api.py`

- [x] **Step 7: Commit**

```bash
git add scanbox/api/scanning.py scanbox/api/import_batch.py scanbox/main.py tests/integration/test_import_api.py
git commit -m "feat: add POST /api/batches/import endpoint for PDF injection"
```

---

## Task 3: Add pytest `load_test_pile` factory fixture

**Files:**
- Modify: `tests/conftest.py`
- Test: `tests/integration/test_pipeline_import.py`

- [x] **Step 1: Write integration tests that use the fixture**

Create `tests/integration/test_pipeline_import.py`:

```python
"""Integration tests: load test pile fixtures and verify pipeline readiness."""

import json
from pathlib import Path

import pikepdf
import pytest


SUITE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "test_suite"


class TestLoadTestPile:
    async def test_loads_standard_pile(self, load_test_pile):
        batch_id, ctx = await load_test_pile("01-standard-clean")
        assert ctx.batch_dir.exists()
        assert (ctx.batch_dir / "fronts.pdf").exists()
        assert (ctx.batch_dir / "backs.pdf").exists()
        assert ctx.has_backs is True

    async def test_loads_single_sided(self, load_test_pile):
        batch_id, ctx = await load_test_pile("02-single-sided-only")
        assert (ctx.batch_dir / "fronts.pdf").exists()
        # Single-sided piles still have a backs.pdf (all blank pages)
        assert ctx.has_backs is True

    async def test_uses_manifest_patient_name(self, load_test_pile):
        batch_id, ctx = await load_test_pile("01-standard-clean")
        assert ctx.person_name == "Elena R. Martinez"

    async def test_uses_custom_patient_name(self, load_test_pile):
        batch_id, ctx = await load_test_pile("01-standard-clean", person_name="Override Name")
        assert ctx.person_name == "Override Name"

    async def test_different_patient_pile(self, load_test_pile):
        batch_id, ctx = await load_test_pile("11-different-patient")
        assert ctx.person_name == "John A. Doe"

    async def test_minimal_pile(self, load_test_pile):
        batch_id, ctx = await load_test_pile("06-minimal-quick")
        fronts = pikepdf.Pdf.open(ctx.batch_dir / "fronts.pdf")
        assert len(fronts.pages) == 3

    async def test_page_counts_match_manifest(self, load_test_pile):
        batch_id, ctx = await load_test_pile("01-standard-clean")
        manifest = json.loads(
            (SUITE_DIR / "01-standard-clean" / "manifest.json").read_text()
        )
        fronts = pikepdf.Pdf.open(ctx.batch_dir / "fronts.pdf")
        assert len(fronts.pages) == manifest["num_sheets"]

    async def test_returns_valid_batch_id(self, load_test_pile):
        batch_id, ctx = await load_test_pile("06-minimal-quick")
        assert batch_id.startswith("batch-")

    async def test_pipeline_context_fields(self, load_test_pile):
        batch_id, ctx = await load_test_pile("01-standard-clean")
        assert ctx.person_slug is not None
        assert ctx.person_folder is not None
        assert ctx.batch_num == 1
        assert ctx.scan_date is not None
        assert ctx.output_dir.exists()
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_pipeline_import.py -v 2>&1 | tail -5`
Expected: FAIL — `load_test_pile` fixture not found

- [x] **Step 3: Add load_test_pile fixture to conftest.py**

Add to `tests/conftest.py`:

```python
import json
import shutil
from datetime import UTC, datetime

from scanbox.api.import_batch import import_batch
from scanbox.database import Database
from scanbox.pipeline.runner import PipelineContext

SUITE_DIR = FIXTURES_DIR / "test_suite"


@pytest.fixture
async def db(tmp_path):
    """Isolated database for testing."""
    database = Database(tmp_path / "data" / "scanbox.db")
    await database.init()
    yield database
    await database.close()


@pytest.fixture
def load_test_pile(tmp_path, db):
    """Factory fixture: load a test suite pile into a ready-to-process state.

    Usage:
        batch_id, ctx = await load_test_pile("01-standard-clean")
        docs = await run_pipeline(ctx)
    """

    async def _load(
        pile_name: str,
        person_name: str | None = None,
    ) -> tuple[str, PipelineContext]:
        pile_dir = SUITE_DIR / pile_name

        # Read manifest for patient name and metadata
        manifest_path = pile_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if person_name is None:
            person_name = manifest["patient"]["name"]

        # Read PDF files
        fronts_bytes = (pile_dir / "fronts.pdf").read_bytes()
        backs_path = pile_dir / "backs.pdf"
        backs_bytes = backs_path.read_bytes() if backs_path.exists() else None

        # Import into database
        data_dir = tmp_path / "data"
        result = await import_batch(
            db=db,
            data_dir=data_dir,
            fronts_bytes=fronts_bytes,
            backs_bytes=backs_bytes,
            person_name=person_name,
        )

        # Build PipelineContext
        person = await db.get_person(result.person_id)
        output_dir = tmp_path / "output"
        output_dir.mkdir(exist_ok=True)

        ctx = PipelineContext(
            batch_dir=result.batch_dir,
            output_dir=output_dir,
            person_name=person["display_name"],
            person_slug=person["slug"],
            person_folder=person["folder_name"],
            batch_num=1,
            scan_date=datetime.now(UTC).strftime("%Y-%m-%d"),
            has_backs=result.has_backs,
        )

        return result.batch_id, ctx

    return _load
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_pipeline_import.py -v`
Expected: All 9 tests PASS

- [x] **Step 5: Format and lint**

Run: `ruff format tests/conftest.py tests/integration/test_pipeline_import.py && ruff check tests/conftest.py tests/integration/test_pipeline_import.py`

- [x] **Step 6: Commit**

```bash
git add tests/conftest.py tests/integration/test_pipeline_import.py
git commit -m "feat: add load_test_pile pytest fixture for pipeline integration tests"
```

---

## Task 4: Add stage-level fixtures

**Files:**
- Modify: `tests/conftest.py`
- Test: `tests/integration/test_pipeline_import.py`

- [x] **Step 1: Write tests for stage-level fixtures**

Add to `tests/integration/test_pipeline_import.py`:

```python
class TestStageFixtures:
    async def test_interleaved_has_combined_pdf(self, interleaved_batch):
        batch_id, ctx = interleaved_batch
        assert (ctx.batch_dir / "combined.pdf").exists()

    async def test_blanks_removed_has_cleaned_pdf(self, blanks_removed_batch):
        batch_id, ctx = blanks_removed_batch
        assert (ctx.batch_dir / "cleaned.pdf").exists()

    async def test_ocr_complete_has_text(self, ocr_complete_batch):
        batch_id, ctx = ocr_complete_batch
        assert (ctx.batch_dir / "ocr.pdf").exists()
        assert (ctx.batch_dir / "text_by_page.json").exists()
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_pipeline_import.py::TestStageFixtures -v 2>&1 | tail -5`
Expected: FAIL — fixtures not found

- [x] **Step 3: Add stage-level fixtures to conftest.py**

Add to `tests/conftest.py` after the `load_test_pile` fixture:

```python
from scanbox.pipeline.interleave import interleave_pages
from scanbox.pipeline.blank_detect import remove_blank_pages


@pytest.fixture
async def interleaved_batch(load_test_pile):
    """Batch through interleave — batch_dir has combined.pdf."""
    batch_id, ctx = await load_test_pile("06-minimal-quick")
    interleave_pages(
        ctx.batch_dir / "fronts.pdf",
        ctx.batch_dir / "backs.pdf" if ctx.has_backs else None,
        ctx.batch_dir / "combined.pdf",
    )
    return batch_id, ctx


@pytest.fixture
async def blanks_removed_batch(load_test_pile):
    """Batch through blank removal — batch_dir has cleaned.pdf."""
    batch_id, ctx = await load_test_pile("06-minimal-quick")
    interleave_pages(
        ctx.batch_dir / "fronts.pdf",
        ctx.batch_dir / "backs.pdf" if ctx.has_backs else None,
        ctx.batch_dir / "combined.pdf",
    )
    remove_blank_pages(
        ctx.batch_dir / "combined.pdf",
        ctx.batch_dir / "cleaned.pdf",
        threshold=0.01,
    )
    return batch_id, ctx


@pytest.fixture
async def ocr_complete_batch(load_test_pile):
    """Batch through OCR — batch_dir has ocr.pdf + text_by_page.json."""
    batch_id, ctx = await load_test_pile("06-minimal-quick")
    interleave_pages(
        ctx.batch_dir / "fronts.pdf",
        ctx.batch_dir / "backs.pdf" if ctx.has_backs else None,
        ctx.batch_dir / "combined.pdf",
    )
    remove_blank_pages(
        ctx.batch_dir / "combined.pdf",
        ctx.batch_dir / "cleaned.pdf",
        threshold=0.01,
    )
    from scanbox.pipeline.ocr import run_ocr

    run_ocr(
        ctx.batch_dir / "cleaned.pdf",
        ctx.batch_dir / "ocr.pdf",
        ctx.batch_dir / "text_by_page.json",
    )
    return batch_id, ctx
```

Note: The `interleave_pages`, `remove_blank_pages`, and `run_ocr` function signatures should be verified by reading the source files before implementing. The signatures shown above follow the patterns from the pipeline runner. Adjust if the actual signatures differ.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_pipeline_import.py::TestStageFixtures -v`
Expected: All 3 tests PASS (requires tesseract installed for OCR test)

If tesseract is not installed, the OCR test will fail. Add a skip marker:
```python
pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="tesseract not installed",
)
```

- [x] **Step 5: Format and lint**

Run: `ruff format tests/conftest.py tests/integration/test_pipeline_import.py && ruff check tests/conftest.py tests/integration/test_pipeline_import.py`

- [x] **Step 6: Commit**

```bash
git add tests/conftest.py tests/integration/test_pipeline_import.py
git commit -m "feat: add stage-level fixtures (interleaved, blanks_removed, ocr_complete)"
```

---

## Task 5: Run full test suite and verify

- [x] **Step 1: Format all new/modified code**

Run: `ruff format scanbox/api/import_batch.py scanbox/api/scanning.py scanbox/main.py tests/conftest.py tests/unit/test_import_batch.py tests/integration/test_import_api.py tests/integration/test_pipeline_import.py`

- [x] **Step 2: Lint all new/modified code**

Run: `ruff check scanbox/api/import_batch.py scanbox/api/scanning.py scanbox/main.py tests/conftest.py tests/unit/test_import_batch.py tests/integration/test_import_api.py tests/integration/test_pipeline_import.py`
Expected: No errors

- [x] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: All existing tests still pass + new tests pass

- [x] **Step 4: Test the API endpoint manually**

```bash
# Generate a test pile
.venv/bin/python -m tests.generate_medical_pile minimal

# Test the import endpoint with curl (requires running server)
# Or test via pytest — already covered in test_import_api.py
```

- [x] **Step 5: Commit if any fixes were needed**

```bash
git add -A
git commit -m "chore: final formatting and test fixes for import system"
```
