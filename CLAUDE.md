# CLAUDE.md

Development guide for AI agents working on ScanBox.

## Project Overview

ScanBox is a **fully implemented** self-hosted Docker application that controls a network scanner via eSCL, processes scans through an automated pipeline, and outputs professionally named documents. 532 tests, 94% coverage, all three phases complete.

**Three interfaces, one backend:**
- **REST API** (`/api/*`) — primary interface with OpenAPI docs at `/api/docs`
- **MCP Server** (`/mcp`) — 17 tools for AI agent integration, enabled via `MCP_ENABLED=true`
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
│   └── runner.py          # Pipeline orchestration with checkpointing
├── api/
│   ├── persons.py         # CRUD for people
│   ├── sessions.py        # Session management
│   ├── scanning.py        # Background scan tasks (fronts, backs, processing)
│   ├── batches.py         # Batch status, reprocess, page thumbnails
│   ├── documents.py       # Document CRUD, PDF/thumbnail/text serving
│   ├── boundaries.py      # Document boundary editor
│   ├── setup.py           # First-run wizard (test scanner/LLM/Paperless)
│   ├── practice.py        # Practice run wizard
│   ├── scanner.py         # Scanner status/capabilities API
│   ├── sse.py             # EventBus for SSE progress streaming
│   ├── paperless.py       # PaperlessNGX client
│   ├── webhooks.py        # Webhook registration and dispatch
│   └── views.py           # HTML template routes
├── mcp/
│   └── server.py          # 17 MCP tools, 2 resources, 2 prompts
└── templates/             # Jinja2 + jinja2-fragments
```

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
bash .githooks/setup.sh
python -m tests.generate_fixtures

# Test
pytest                          # all 532 tests
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
brew install tesseract poppler ghostscript
```

## Principles

Non-negotiable. Follow even when not asked:

1. **Fix root causes.** Never work around failures or silence errors.
2. **No AI attribution.** No `Co-Authored-By`, `Signed-off-by`, or similar trailers.
3. **Format before commit.** `ruff format` — the pre-commit hook enforces this.
4. **Verify CI after push.** If red, fix immediately.
5. **TDD.** Write failing tests first, then implement.
6. **Design spec is authoritative.** `docs/design.md` is the single source of truth.
7. **Plain English for users.** Never show technical jargon in the UI.
8. **Minimal changes.** Don't refactor, add docstrings, or "improve" code beyond the task.
9. **No speculative abstractions.** Build what's needed now, not what might be needed later.

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
- **Checkpointing:** Each stage writes to disk before the next begins. `state.json` tracks progress per batch. Pipeline resumes from last checkpoint on crash.
- **Batch states:** `scanning_fronts → fronts_done → scanning_backs → backs_done → processing → review → saved`
- **AI splitting:** One litellm call per batch (all pages). Response validated for contiguous, non-overlapping, full-coverage page ranges.

### eSCL Protocol
- Endpoints at `http://{ip}/eSCL/...` (capital S, C, L)
- POST `/ScanJobs` → 201 with `Location` header → GET `NextDocument` in loop → 404 means ADF empty
- No authentication. Simplex ADF only (two-pass duplex is a hardware limitation).

### Storage
- **Internal volume** (`/app/data`): sessions, batches, processing state — safety net
- **Output volume** (`/output`): archive + organized medical records — user-facing
- **PaperlessNGX**: REST API upload (`POST /api/documents/post_document/`), not filesystem

### Frontend
- **htmx 2.0** for server communication + SSE progress (self-hosted, no CDN)
- **Alpine.js 3.15** for client-side UI state (self-hosted)
- **Tailwind CSS 4.2** via standalone CLI at Docker build time (no Node.js)
- **jinja2-fragments** for partial template rendering on htmx requests

### Dependencies
- `litellm==1.82.6` — exact pin due to supply chain incident on 1.82.7/1.82.8
- `pikepdf` — use `allow_overwriting_input=True` when saving to same path
- `ocrmypdf` — requires tesseract, ghostscript (since v17), poppler as system packages

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

### JSON key types
`text_by_page.json` uses string keys (`"1"`, `"2"`) since JSON doesn't support integer keys. Access as `text_data["1"]`, not `text_data[1]`.

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/design.md` | **Single source of truth** — behavior, architecture, error handling |
| `docs/api-spec.md` | REST API reference — all endpoints with examples |
| `docs/mcp-server.md` | MCP server — 17 tools, 2 resources, 2 prompts |
| `docs/ui-spec.md` | Visual design — components, layouts, accessibility |
| `docs/plans/2026-03-28-scanbox-implementation.md` | Original implementation plan (all tasks complete) |

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
