# Test PDF Import System

Import pre-made PDFs into ScanBox as if they were scanned, bypassing the physical scanner. Two entry points: an API endpoint for interactive dev and pytest fixtures for automated testing. Both share a common import core.

## Problem

The ScanBox pipeline expects `fronts.pdf` + `backs.pdf` in a batch directory, created by the eSCL scanner. During development and CI testing, there's no scanner available. The test fixture PDFs (`tests/fixtures/test_suite/`) are realistic but have no way to enter the pipeline. Developers must either mock the entire scan flow or skip to individual pipeline stages without realistic data.

## Architecture

Two entry points, one shared core:

```
pytest fixture                    API endpoint
load_test_pile("01-standard")    POST /api/batches/import
        \                              /
         \                            /
          v                          v
       import_batch(db, config, fronts_bytes, backs_bytes?, person_name?)
          |
          ├── Create person record (if not exists)
          ├── Create session + batch in DB
          ├── Write PDFs to batch_dir (config.INTERNAL_DATA_DIR/sessions/...)
          ├── Set batch state + page counts
          └── Return (batch_id, session_id, batch_dir)
```

The shared `import_batch()` function lives in `scanbox/api/import_batch.py`. Both the API route and pytest fixtures call it. No changes to the existing pipeline, scanner, or processing code.

## API Endpoint

### `POST /api/batches/import`

Multipart form upload that creates a session and batch from uploaded PDFs.

**Parameters:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `fronts` | file | Yes | — | Front sides PDF |
| `backs` | file | No | — | Back sides PDF. If omitted, batch is single-sided. |
| `person_name` | string | No | `"Test Patient"` | Display name for the person record |

**Behavior:**

1. Validate uploaded files are PDFs (check magic bytes or extension)
2. Call `import_batch()` to create DB records and write files
3. Kick off `_run_processing()` as a background task (same code path as real scanning)
4. Return JSON with batch ID, session ID, and status URL

**Response (201 Created):**
```json
{
  "batch_id": "batch-abc123",
  "session_id": "sess-def456",
  "person_id": "test-patient",
  "state": "processing",
  "has_backs": true,
  "fronts_pages": 13,
  "backs_pages": 13,
  "status_url": "/api/batches/batch-abc123"
}
```

**Error cases:**
- 400 if no `fronts` file provided
- 400 if uploaded file is not a valid PDF (can't be opened by pikepdf)

### Single merged PDF support

If only `fronts` is uploaded (no `backs`), the pipeline runs with `has_backs=False`:
- Interleave stage passes through the fronts PDF unchanged
- Blank removal, OCR, splitting, naming run normally

This means any regular PDF can be imported — not just scan-pair fixtures.

## Shared Import Core

### `scanbox/api/import_batch.py`

```python
async def import_batch(
    db: Database,
    config: Config,
    fronts_bytes: bytes,
    backs_bytes: bytes | None = None,
    person_name: str = "Test Patient",
) -> ImportResult:
```

**`ImportResult` dataclass:**
```python
@dataclass
class ImportResult:
    batch_id: str
    session_id: str
    person_id: str
    batch_dir: Path
    has_backs: bool
    fronts_page_count: int
    backs_page_count: int | None
```

**Steps:**

1. **Person** — look up by name (slugified). If not found, create a new person record.
2. **Session** — create a new session for this person.
3. **Batch** — create a new batch (batch_num=1) in state `backs_done` (if backs provided) or `backs_skipped` (if not).
4. **Files** — write `fronts.pdf` and optionally `backs.pdf` to `config.INTERNAL_DATA_DIR/sessions/{session_id}/batch-{batch_num}/`.
5. **Page counts** — open each PDF with pikepdf to count pages, update batch record.
6. **Return** — `ImportResult` with all IDs and paths.

The caller (API endpoint or pytest fixture) is responsible for triggering the pipeline after import.

## Pytest Fixtures

### Factory Fixture: `load_test_pile`

```python
@pytest.fixture
def load_test_pile(tmp_path, tmp_config):
    """Factory fixture that loads a test suite pile into a ready-to-process state.

    Usage:
        batch_id, ctx = await load_test_pile("01-standard-clean")
        docs = await run_pipeline(ctx)
    """
    async def _load(
        pile_name: str,
        person_name: str | None = None,  # None = read from manifest
    ) -> tuple[str, PipelineContext]:
        ...
    return _load
```

**Behavior:**

1. Read `tests/fixtures/test_suite/{pile_name}/manifest.json` for patient name and metadata
2. Read `fronts.pdf` and `backs.pdf` bytes from the pile directory
3. Call `import_batch()` with `tmp_config` database and directories
4. Build and return a `PipelineContext` pointing at the batch directory
5. If `person_name` is None, use `manifest["patient"]["name"]`

### Stage-Level Fixtures

Pre-configured fixtures that run the pipeline up to a specific stage, leaving the batch ready for the next stage. These use `load_test_pile` internally with the `06-minimal-quick` pile (3 docs, fast).

```python
@pytest.fixture
async def interleaved_batch(load_test_pile):
    """Batch through interleave — batch_dir has combined.pdf. Ready for blank removal."""

@pytest.fixture
async def blanks_removed_batch(load_test_pile):
    """Batch through blank removal — batch_dir has cleaned.pdf. Ready for OCR."""

@pytest.fixture
async def ocr_complete_batch(load_test_pile):
    """Batch through OCR — batch_dir has ocr.pdf + text_by_page.json. Ready for splitting."""

@pytest.fixture
async def split_complete_batch(load_test_pile):
    """Batch through splitting — batch_dir has splits.json. Ready for naming."""
```

Each fixture runs the real pipeline stages up to that point (no mocking of interleave, blank removal, or OCR — these use real tesseract). Only the LLM call in the splitting stage is mocked when needed.

**Stage fixture implementation pattern:**
```python
@pytest.fixture
async def interleaved_batch(load_test_pile):
    batch_id, ctx = await load_test_pile("06-minimal-quick")
    from scanbox.pipeline.interleave import interleave_pages
    interleave_pages(
        ctx.batch_dir / "fronts.pdf",
        ctx.batch_dir / "backs.pdf" if ctx.has_backs else None,
        ctx.batch_dir / "combined.pdf",
    )
    return batch_id, ctx
```

### Fixture Location

All import-related fixtures go in `tests/conftest.py` alongside existing fixtures (or a new `tests/conftest_import.py` if conftest grows too large). The stage fixtures require tesseract as a system dependency — CI already installs it.

## CI Integration

### What CI runs

Integration tests using `load_test_pile` execute against the committed test fixture PDFs:

```python
class TestPipelineWithFixtures:
    async def test_standard_pile_produces_11_documents(self, load_test_pile):
        batch_id, ctx = await load_test_pile("01-standard-clean")
        with patch("scanbox.pipeline.splitter.acompletion") as mock_llm:
            mock_llm.return_value = _mock_split_response(...)
            docs = await run_pipeline(ctx)
        assert len(docs) == 11

    async def test_single_sided_removes_blanks(self, load_test_pile):
        batch_id, ctx = await load_test_pile("02-single-sided-only")
        # Run just interleave + blank removal
        ...
```

### What CI needs

- Python 3.13 (already configured)
- tesseract + ghostscript + poppler (already in CI workflow)
- The test fixture PDFs in `tests/fixtures/test_suite/` (already committed)
- LLM mocked (no API key needed)

No new CI configuration required.

## What Changes

| File | Change |
|------|--------|
| `scanbox/api/import_batch.py` | **New** — shared `import_batch()` function + `ImportResult` dataclass |
| `scanbox/api/scanning.py` | **Modify** — add import route that calls `import_batch()` + triggers processing |
| `tests/conftest.py` | **Modify** — add `load_test_pile` factory fixture + stage-level fixtures |
| `tests/integration/test_pipeline_import.py` | **New** — integration tests using test pile fixtures |

## What Stays the Same

- `scanbox/pipeline/runner.py` — no changes to pipeline
- `scanbox/pipeline/*.py` — no changes to any pipeline stage
- `scanbox/api/sessions.py`, `scanbox/api/batches.py` — existing API unchanged
- `tests/generate_test_suite.py` — fixture generation unchanged
- All existing tests — unaffected

## Out of Scope

- UI for importing PDFs (could add a drag-and-drop later, but API-first for now)
- Automatic fixture regeneration in CI (fixtures are committed, regenerated manually)
- Running the real LLM in CI (always mocked — API keys are not available in CI)
