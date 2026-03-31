# CLAUDE.md

Development guide for AI agents working on ScanBox.

## Project Overview

ScanBox is a **fully implemented** self-hosted Docker application that controls a network scanner via eSCL, processes scans through an automated pipeline, and outputs professionally named documents. 812 tests, 87% coverage, all three phases complete.

**Three interfaces, one backend:**
- **REST API** (`/api/*`) — 65+ endpoints with OpenAPI docs at `/api/docs`
- **MCP Server** (`/mcp`) — 27 tools for AI agent integration, enabled via `MCP_ENABLED=true`
- **Web UI** (`/`) — htmx + Alpine.js wizard-guided workflow

## Source Layout

```
scanbox/
├── config.py              # Env var config with defaults
├── models.py              # Pydantic: BatchState, SplitDocument, Person
├── database.py            # SQLite via aiosqlite
├── main.py                # FastAPI app, lifespan, health, MCP mount
├── scanner/
│   ├── escl.py            # eSCL HTTP client (capabilities, status, scan jobs)
│   └── models.py          # ScannerStatus, ScannerCapabilities
├── pipeline/
│   ├── interleave.py      # Merge front/back PDFs
│   ├── blank_detect.py    # Remove blank pages (Pillow, 1% threshold)
│   ├── ocr.py             # OCR via ocrmypdf subprocess
│   ├── splitter.py        # AI document splitting via litellm
│   ├── namer.py           # Professional filename generation
│   ├── output.py          # PDF splitting, metadata, Index.csv
│   ├── runner.py          # Stage-aware pipeline with pause/resume/DLQ
│   └── state.py           # PipelineState, StageState, DLQItem, PipelineConfig
├── api/
│   ├── persons.py         # CRUD for people
│   ├── sessions.py        # Session management
│   ├── scanning.py        # Background scan tasks, PDF import endpoint
│   ├── import_batch.py    # Shared import_batch() for API + test fixtures
│   ├── batches.py         # Batch status, pipeline control, DLQ, exclusions
│   ├── documents.py       # Document CRUD, PDF/thumbnail/text serving
│   ├── boundaries.py      # Document boundary editor
│   ├── setup.py           # First-run wizard (test scanner/LLM/Paperless)
│   ├── practice.py        # Practice run wizard
│   ├── scanner.py         # Scanner status/capabilities API
│   ├── sse.py             # EventBus for SSE progress streaming
│   ├── paperless.py       # PaperlessNGX client
│   ├── webhooks.py        # Webhook registration and dispatch
│   └── views.py           # HTML template routes + pipeline page
├── mcp/
│   └── server.py          # 27 MCP tools, 4 resources, 4 prompts
└── templates/             # Jinja2 + jinja2-fragments (incl. pipeline.html)
```

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
bash .githooks/setup.sh
python -m tests.generate_fixtures

# Test
pytest                          # all 812 tests
pytest tests/unit/ -v           # unit tests only
pytest tests/integration/ -v    # integration tests
pytest -k "pattern"             # filter

# Coverage
coverage run --source=scanbox -m pytest
coverage report                 # CI requires >= 85%

# Lint
ruff format scanbox/ tests/
ruff check scanbox/ tests/      # line-length=100

# Run
docker compose up               # http://localhost:8090

# System deps (macOS)
brew install tesseract poppler ghostscript ocrmypdf
```

## Principles

Non-negotiable. Follow even when not asked:

1. **Fix root causes.** Never work around failures or silence errors.
2. **No AI attribution.** No `Co-Authored-By`, `Signed-off-by`, or similar trailers.
3. **Format before commit.** `ruff format` — the pre-commit hook enforces this.
4. **Verify CI after push.** If red, fix immediately.
5. **TDD.** Write failing tests first, then implement.
6. **Verify locally before merging.** Run the actual code path — not just unit tests — to confirm the fix works. For frontend: render the template and check the output. For API changes: call the endpoint. For browser behavior (Alpine, htmx, SSE): test in a real browser or verify the generated JS/HTML is valid. CI passing is necessary but not sufficient.
7. **Design spec is authoritative.** `docs/design.md` is the single source of truth.
8. **Plain English for users.** Never show technical jargon in the UI.
9. **Minimal changes.** Don't refactor, add docstrings, or "improve" code beyond the task.
10. **No speculative abstractions.** Build what's needed now, not what might be needed later.
11. **Never block the UI on backend work.** Show what's available now, stream updates as they arrive. Scanning, OCR, splitting, and naming are async — the user should always see immediate feedback (page count, thumbnails, progress) without waiting for processing to finish. If a backend job fails, the user still sees what was captured.

## Git Workflow

**Linear history only. No merge commits.**

```
git pull                          # configured to rebase
git rebase origin/main            # update branch (never merge)
git merge --ff-only <branch>      # integrate to main
```

**Conventional commits:** `feat:`, `fix:`, `test:`, `docs:`, `ci:`, `chore:`, `refactor:`

**PR workflow:** Feature branch → squash merge → delete branch.

## Quality Gates

Four layers, innermost to outermost:

1. **Pre-commit hook** (`.githooks/pre-commit`) — ruff check + format
2. **Claude Code hooks** (`.claude/settings.json`) — lint + format + full test suite before `git commit`; lint + format + rebase before `git push`
3. **Permission deny rules** — force push, hard reset, checkout-dot, clean -f are blocked
4. **GitHub CI** — lint, test with coverage (>= 85%), Docker build

## Key Technical Details

### Pipeline
- **Stage-aware execution:** Pipeline runs 5 stages (interleave → blank removal → OCR → splitting → naming). Each stage checkpoints to `state.json` with status, timestamps, and results. `PipelineState` class in `scanbox/pipeline/state.py` manages all transitions.
- **Pause/resume:** Auto-advances on success. Pauses on stage errors or low-confidence splits. Batch goes to `PAUSED` state. User can resume, retry, skip, or advance via API.
- **DLQ (Dead Letter Queue):** Configurable `PIPELINE_AUTO_ADVANCE_ON_ERROR=true` skips problems and queues them. DLQ items stored in `state.json`, manageable via API.
- **Batch states:** `scanning_fronts → fronts_done → scanning_backs → backs_done → processing → [paused] → review → saved`
- **AI splitting:** One litellm call per batch (all pages, `max_tokens=4096`). Response validated for contiguous, non-overlapping, full-coverage page ranges. Missing `end_page` defaults to `start_page`.
- **Pipeline control API:** `GET /api/batches/{id}/pipeline` for full state. `POST .../resume`, `.../retry`, `.../skip`, `.../advance` for control. DLQ endpoints for item management.
- **Page/document exclusion:** `POST/DELETE /api/batches/{id}/exclude/page/{num}` and `.../document/{idx}`. Exclusions persist in `state.json`.

### eSCL Protocol
- Endpoints at `http://{ip}/eSCL/...` (capital S, C, L)
- POST `/ScanJobs` → 201 with `Location` header → GET `NextDocument` in loop → 404 means ADF empty
- No authentication. Simplex ADF only (two-pass duplex is a hardware limitation).
- **Multi-page PDF responses:** When scan format is PDF, the scanner can return all pages in a single `NextDocument` response. Count pages from the PDF content (`len(pdf.pages)`), not from the number of HTTP responses.

### Storage
- **Internal volume** (`/app/data`): sessions, batches, processing state — safety net
- **Output volume** (`/output`): archive + organized medical records — user-facing
- **PaperlessNGX**: REST API upload (`POST /api/documents/post_document/`), not filesystem

### Frontend
- **htmx 2.0** for server communication + SSE progress (self-hosted, no CDN)
- **Alpine.js 3.15** for client-side UI state (self-hosted)
- **Tailwind CSS 4.2** via standalone CLI at Docker build time (no Node.js)
- **jinja2-fragments** for partial template rendering on htmx requests
- **Alpine `x-init`/`x-data` expressions** are evaluated via `new AsyncFunction(expr)`. Use `let`/`const`, not `var` — `var` throws `SyntaxError` in this context. Jinja values can be interpolated directly: `x-init="let s = '{{ batch.state }}'"`.
- **Tailwind CSS coverage test** (`test_css_coverage.py`) checks that all classes used in templates exist in the compiled `app.css`. New Tailwind classes fail this test until the Docker build recompiles CSS. Use inline `style=""` for one-off properties (e.g., spinner border colors) rather than adding classes that aren't in the compiled CSS.
- **`<img>` tags can't send auth headers.** Any `/api/*` endpoint loaded via `<img src="">` must be in the `_AUTH_EXEMPT` set in `main.py`, or it will 401 when `SCANBOX_API_KEY` is set. The `onerror` handler hides the broken image silently.

### SSE Events
- **Publisher is authoritative.** Event keys are defined in `scanning.py` (scan events) and `pipeline/runner.py` (pipeline events). The consumer in `views.py:_render_progress_event` must match those keys exactly.
- **Key reference:** `scan_complete` uses `"pages"`, `done` uses `"document_count"`. If you add new event types, grep for the publish call to find the canonical key names.
- **Events are fire-and-forget.** `EventBus` is in-memory with no persistence. If the browser disconnects, old events are lost. The scan wizard uses `x-init` state restore on page reload as the recovery mechanism.

### Dependencies
- `litellm==1.82.6` — exact pin due to supply chain incident on 1.82.7/1.82.8
- `pikepdf` — use `allow_overwriting_input=True` when saving to same path
- `ocrmypdf` — requires tesseract, ghostscript (since v17), poppler as system packages

### Test Fixture Framework
- **Medical document generator:** `tests/medical_documents/` — composable framework for generating test PDFs. 11 document types, 8 artifact types (duplicates, shuffled pages, wrong patient, etc.), configurable patient context.
- **Test suite:** 13 pre-committed piles in `tests/fixtures/test_suite/` covering all pipeline scenarios (standard, single-sided, chaos, stress test, etc.).
- **PDF import:** `POST /api/batches/import` injects PDFs into the pipeline without a scanner. `load_test_pile` pytest fixture loads test piles by name.
- **Stage fixtures:** `interleaved_batch`, `blanks_removed_batch`, `ocr_complete_batch` — pre-processed batches for testing individual stages.
- **Commands:** `/test-pdfs` for generating/verifying fixtures. `python -m tests.generate_test_suite` for regeneration.
- **E2E tests:** `tests/integration/test_e2e_pipeline.py` runs real pipeline stages against fixture PDFs. LLM tests use local MLX-LM when available, skip gracefully when not.

## Mocking Patterns

Patterns discovered during development — follow these when writing tests:

### Lazy imports in endpoints
Setup endpoints (`scanbox/api/setup.py`) import ESCLClient, litellm, and PaperlessClient inside function bodies. Patch at the **source module**, not the endpoint module:
```python
@patch("scanbox.scanner.escl.ESCLClient")        # not scanbox.api.setup.ESCLClient
@patch("litellm.acompletion")                     # not scanbox.api.setup.litellm
@patch("scanbox.api.paperless.PaperlessClient.check_connection")
```

### Module-level config singletons
`scanbox/pipeline/splitter.py` imports `config` at module level. `monkeypatch.setenv` won't work — patch the config object:
```python
@patch("scanbox.pipeline.splitter.config")
async def test_model(self, mock_config):
    mock_config.llm_model_id.return_value = "gpt-4o-mini"
```

### pikepdf in tests
Use `BytesIO` from `io`, not `pikepdf.BytesIO` (doesn't exist). When creating test PDFs:
```python
pdf = pikepdf.Pdf.new()
pdf.add_blank_page(page_size=(612, 792))
pdf.save(buf)
```

### Pipeline return type
`run_pipeline()` returns `PipelineResult` (not `list[SplitDocument]`). Access documents via `result.documents`. When mocking in tests:
```python
from scanbox.models import PipelineResult
mock_pipeline.return_value = PipelineResult(status="completed", documents=[...])
```

### JSON key types
`text_by_page.json` uses string keys (`"1"`, `"2"`) since JSON doesn't support integer keys. Access as `text_data["1"]`, not `text_data[1]`.

### Batch state in view tests
Results page (`/results/{batch_id}`) redirects non-terminal batches. Tests that hit `/results/` must set the batch state to `review` or `saved` first, or they'll get a 303 instead of 200.

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/design.md` | **Single source of truth** — behavior, architecture, error handling |
| `docs/api-spec.md` | REST API reference — all endpoints with examples |
| `docs/mcp-server.md` | MCP server — 27 tools, 4 resources, 4 prompts |
| `docs/ui-spec.md` | Visual design — components, layouts, accessibility |
| `docs/superpowers/specs/` | Design specs for pipeline control, test import, medical doc generator |
| `docs/superpowers/plans/` | Implementation plans for each subsystem |

## CI/CD

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | Push/PR to main | Lint + test (85% coverage gate) + Docker build |
| `lint-pr.yml` | PR | Conventional commit title validation |
| `release-please.yml` | Push to main | Auto-changelog + version bump |
| `release.yml` | Release tag | Multi-arch Docker image (amd64+arm64) to GHCR |

## V1 Scope Boundaries

Explicitly out of scope — do not add these:

- Barcode separator sheets, multi-scanner support, mobile-responsive UI
- ntfy notifications, direct EHR/Epic upload, document deduplication
- Heuristic-only splitting (without LLM), custom output routing per document
- Manual page reorder for interleaving, reopening past sessions for new scans
