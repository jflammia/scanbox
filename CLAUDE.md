# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## What Is ScanBox?

A self-hosted Docker application with an **API-first architecture** that controls a network scanner via the eSCL protocol, processes scans through an automated pipeline (interleave duplex pages, remove blanks, OCR, AI document splitting), and outputs professionally named medical records.

**Three interfaces, one engine:**
- **REST API** — primary interface; the web UI and all integrations are consumers of this API
- **MCP Server** — Model Context Protocol for native AI agent integration (Claude, etc.)
- **Web UI** — human-friendly interface built on htmx + Alpine.js, consuming the API

The target user is non-technical — the web UI must be dead-simple. But the API and MCP server make ScanBox equally accessible to AI agents, scripts, and automation workflows.

## Current State

**This project is in early implementation.** The repo contains:
- Design spec: `docs/design.md` (authoritative — read this before any implementation work)
- API spec: `docs/api-spec.md` (REST API reference for all endpoints)
- MCP spec: `docs/mcp-server.md` (MCP server tools, resources, and prompts)
- UI spec: `docs/ui-spec.md` (visual design, components, screen layouts, interaction patterns)
- Implementation plan: `docs/plans/2026-03-28-scanbox-implementation.md` (21+ tasks, 3 phases)
- Project scaffold: Dockerfile, docker-compose.yml, pyproject.toml, CI/CD workflows
- Git workflow: hooks, quality gates, conventional commits (all configured)
- No application code yet (just `scanbox/__init__.py` placeholder)

**Start here:** Read the implementation plan, then execute tasks in order.

## Operating Principles

Non-negotiable. Follow even when the user doesn't ask:

- **Never work around failures.** Diagnose and fix the root cause.
- **Never add AI attribution.** No `Co-Authored-By`, `Signed-off-by`, or similar trailers.
- **Always run `ruff format` before committing.** Pre-commit hook blocks unformatted code.
- **Verify CI after pushing.** Check CI status — if red, fix immediately.
- **TDD.** Write failing tests first, then implement. Every task in the plan follows this pattern.
- **Read the design spec.** When the plan says "see design spec," read `docs/design.md` for the authoritative behavior. Don't guess.

## Commands

```bash
# First-time setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
bash .githooks/setup.sh              # Git hooks + rebase config
brew install tesseract poppler ghostscript  # macOS system deps
python -m tests.generate_fixtures    # Generate test PDFs

# Test
pytest                                # All tests
pytest tests/unit/ -v                 # Unit tests
pytest tests/integration/ -v          # Integration tests
pytest -k "interleave"               # Pattern match

# Lint
ruff format scanbox/ tests/          # Auto-format
ruff check scanbox/ tests/           # Check style (line-length=100)

# Run
docker compose up                     # http://localhost:8090
```

## Architecture

```
     Consumers (any can drive ScanBox)
┌──────────┬──────────┬──────────┐
│  Web UI  │ AI Agent │ Scripts  │
│ (browser)│ (MCP/API)│ (curl)   │
└────┬─────┴────┬─────┴────┬─────┘
     │          │          │
     ▼          ▼          ▼
┌─────────────────────────────────┐
│  FastAPI Backend (API-first)    │
│  REST API · MCP Server · SSE   │
│  Webhooks · OpenAPI docs        │
├─────────────────────────────────┤
│  Processing Pipeline            │
│  Interleave → Blank Removal     │
│  → OCR → AI Split → Name → Save│
└─────────────────────────────────┘
     │          │          │
     ▼          ▼          ▼
  Scanner   Output Dir  PaperlessNGX
  (eSCL)    (volume)    (optional)
```

### Source Layout

| Directory | Responsibility |
|-----------|---------------|
| `scanbox/config.py` | Environment variable config with defaults |
| `scanbox/models.py` | Shared Pydantic models (BatchState, SplitDocument, Person) |
| `scanbox/database.py` | SQLite via aiosqlite (sessions, batches, documents, persons) |
| `scanbox/scanner/` | eSCL protocol: capabilities, status, start job, get pages |
| `scanbox/pipeline/` | Processing stages: interleave, blank_detect, ocr, splitter, namer, output, runner |
| `scanbox/api/` | FastAPI routes: persons, sessions, scanning, batches, documents, setup, SSE, webhooks |
| `scanbox/mcp/` | MCP server: tools, resources, prompts for AI agent integration |
| `scanbox/templates/` | Jinja2 HTML: home, scan wizard, results cards, setup, practice run, settings |
| `static/` | Tailwind CSS, Alpine.js, icons |
| `tests/` | Unit, integration, E2E tests + fixture generator |

### Key Technical Details

- **API-first**: REST API at `/api/*` is the primary interface. OpenAPI spec at `/api/openapi.json`. Interactive docs at `/api/docs`. Web UI consumes the same API.
- **MCP server**: Enable with `MCP_ENABLED=true`. Exposes tools for scanning, reviewing, and saving. See `docs/mcp-server.md`.
- **Webhooks**: Register URLs to receive `scan.completed`, `processing.completed`, `save.completed` events. See `docs/api-spec.md`.
- **eSCL protocol**: HTTP REST + XML. Endpoints: `/eSCL/ScannerCapabilities`, `/eSCL/ScannerStatus`, `/eSCL/ScanJobs` (POST to start, GET NextDocument in loop, DELETE to cancel). See `docs/design.md` "Scanner Communication" section.
- **Pipeline checkpointing**: Each stage writes output to disk before the next begins. `state.json` in each batch dir tracks progress. On crash, pipeline resumes from last completed stage.
- **Batch state machine**: `scanning_fronts → fronts_done → scanning_backs → backs_done → processing → review → saved`. See `docs/design.md` "Persistence & Progress" section.
- **AI splitting**: litellm==1.82.6 (pinned — supply chain incident on 1.82.7/1.82.8) calls any LLM with a structured prompt. Response is validated (contiguous, non-overlapping, full coverage). See `docs/design.md` "Stage 4" section.
- **Frontend**: htmx 2.0 for server-driven HTML swapping + SSE progress. Alpine.js 3.15 for client-side UI state. Tailwind CSS 4.2 (standalone CLI, no Node.js). jinja2-fragments for rendering partial template blocks.
- **Two storage volumes**: Internal (`/app/data` — sessions, processing state) and Output (`/output` — archive + medical records folder). PaperlessNGX via REST API, not filesystem.
- **Tech stack research**: See `.claude/rules/tech-stack-2026.md` for full version rationale and security notes.

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/design.md` | **Single source of truth** for all behavior, UX, architecture, and error handling |
| `docs/api-spec.md` | REST API reference — endpoints, request/response formats, examples |
| `docs/mcp-server.md` | MCP server specification — tools, resources, prompts for AI agents |
| `docs/ui-spec.md` | Visual design — components, layouts, accessibility, interaction patterns |
| `docs/plans/2026-03-28-scanbox-implementation.md` | Task-by-task implementation plan |

**When in doubt, the design spec answers it.**

## Implementation Plan

`docs/plans/2026-03-28-scanbox-implementation.md` contains tasks across 3 phases:

| Phase | Tasks | Deliverables |
|-------|-------|-------------|
| **1: Pipeline Core** | 1-10 | Config, models, test fixtures, interleave, blank detect, namer, splitter, OCR, output, pipeline runner, eSCL client. All TDD. |
| **2: API + Web UI** | 11-17 | Database, FastAPI app, scanning/processing/document APIs, SSE, web UI templates, E2E test. |
| **3: Polish + Integration** | 18+ | Setup wizard, practice run, boundary editor, MCP server, webhooks, Docker verification. |

Phase 1 tasks have **complete code in every step** — tests and implementations ready to type in. Phase 2-3 tasks define behavior and reference the design spec for details.

**Execute tasks in order.** Each task depends on the previous. Each task ends with a commit.

## Git Workflow

**Linear history only. No merge commits.**

| Operation | Correct | Wrong |
|-----------|---------|-------|
| Update branch | `git rebase origin/main` | `git merge main` |
| Pull changes | `git pull` (configured to rebase) | - |
| Integrate to main | `git merge --ff-only <branch>` | `git merge <branch>` |

Git config enforces this: `pull.rebase=true`, `merge.ff=only`.

### Commits

- **Conventional commits required**: `feat:`, `fix:`, `docs:`, `ci:`, `chore:`, `refactor:`, `test:`, `perf:`, `build:`, `style:`, `revert:`
- **Never add AI attribution trailers**
- **Squash merge** feature/fix PRs
- **Regular merge** release-please Release PRs

### Quality Gates

1. **Permission deny rules** (`.claude/settings.json`) — hard-block force push, hard reset, checkout-dot, clean -f
2. **Git pre-commit hook** (`.githooks/pre-commit`) — ruff check + format before commit
3. **Claude Code hooks** (`.claude/settings.json`) — lint + format + tests before commit; lint + format + pull before push
4. **GitHub CI** — Lint + Test + Docker Build on push/PR

## Key Conventions

- Python >= 3.13
- ruff line-length: 100
- All env vars in `scanbox/config.py` with sensible defaults
- LLM provider configurable via `LLM_PROVIDER` env var (anthropic, openai, ollama)
- PaperlessNGX integration is optional
- MCP server is opt-in via `MCP_ENABLED=true`
- API authentication is optional via `SCANBOX_API_KEY` (off by default for local use)
- Target user (web UI) is non-technical — plain English, no jargon
- Every automated decision is a suggestion the user (or their AI agent) can override

## CI/CD

`ci.yml`: lint + test + docker build on push/PR.
`lint-pr.yml`: conventional commit PR title validation.
`release-please.yml`: auto-changelog + version bump on push to main.
`release.yml`: multi-arch Docker image (amd64+arm64) to GHCR.
