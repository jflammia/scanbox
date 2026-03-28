# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## What Is ScanBox?

A self-hosted Docker web app that controls a network scanner via the eSCL protocol, processes scans through an automated pipeline (interleave duplex pages, remove blanks, OCR, AI document splitting), and outputs professionally named medical records. The target user is non-technical — the UI must be dead-simple.

## Current State

**This project is in early implementation.** The repo contains:
- Design spec: `docs/design.md` (authoritative — read this before any implementation work)
- UI spec: `docs/ui-spec.md` (visual design, components, screen layouts, interaction patterns)
- Implementation plan: `docs/plans/2026-03-28-scanbox-implementation.md` (21 tasks, 3 phases)
- Project scaffold: Dockerfile, docker-compose.yml, pyproject.toml, CI/CD workflows
- Git workflow: hooks, quality gates, conventional commits (all configured)
- No application code yet (just `scanbox/__init__.py` placeholder)

**Start here:** Read the implementation plan, then execute tasks in order.

## Operating Principles

Non-negotiable. Follow even when the user doesn't ask:

- **Never work around failures.** Diagnose and fix the root cause.
- **Never add AI attribution.** No `Co-Authored-By`, `Signed-off-by`, or similar trailers.
- **Always run `ruff format` before committing.** Pre-commit hook blocks unformatted code.
- **Verify CI after pushing.** `gh run list --limit 2` — if red, fix immediately.
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

# GitHub
gh run list --limit 5                 # CI status
gh pr list                            # Open PRs
```

## Architecture

```
Scanner (eSCL HTTP) → FastAPI backend → Processing pipeline → Output
                                         │
                                         ├── Interleave (duplex pages)
                                         ├── Blank removal (ink coverage)
                                         ├── OCR (ocrmypdf/Tesseract)
                                         ├── AI split (litellm → any LLM)
                                         ├── Name (medical conventions)
                                         └── Save (files + PaperlessNGX API)
```

### Source Layout

| Directory | Responsibility |
|-----------|---------------|
| `scanbox/config.py` | Environment variable config with defaults |
| `scanbox/models.py` | Shared Pydantic models (BatchState, SplitDocument, Person) |
| `scanbox/database.py` | SQLite via aiosqlite (sessions, batches, documents, persons) |
| `scanbox/scanner/` | eSCL protocol: capabilities, status, start job, get pages |
| `scanbox/pipeline/` | Processing stages: interleave, blank_detect, ocr, splitter, namer, output, runner |
| `scanbox/api/` | FastAPI routes: persons, sessions, scanning, batches, documents, setup, SSE |
| `scanbox/templates/` | Jinja2 HTML: home, scan wizard, results cards, setup, practice run, settings |
| `static/` | Tailwind CSS, Alpine.js, icons |
| `tests/` | Unit, integration, E2E tests + fixture generator |

### Key Technical Details

- **eSCL protocol**: HTTP REST + XML. Endpoints: `/eSCL/ScannerCapabilities`, `/eSCL/ScannerStatus`, `/eSCL/ScanJobs` (POST to start, GET NextDocument in loop, DELETE to cancel). See `docs/design.md` "Scanner Communication" section.
- **Pipeline checkpointing**: Each stage writes output to disk before the next begins. `state.json` in each batch dir tracks progress. On crash, pipeline resumes from last completed stage.
- **Batch state machine**: `scanning_fronts → fronts_done → scanning_backs → backs_done → processing → review → saved`. See `docs/design.md` "Persistence & Progress" section.
- **AI splitting**: litellm==1.82.6 (pinned — supply chain incident on 1.82.7/1.82.8) calls any LLM with a structured prompt. Response is validated (contiguous, non-overlapping, full coverage). See `docs/design.md` "Stage 4" section.
- **Frontend**: htmx 2.0 for server-driven HTML swapping + SSE progress. Alpine.js 3.15 for client-side UI state. Tailwind CSS 4.2 (standalone CLI, no Node.js). jinja2-fragments for rendering partial template blocks.
- **Two storage volumes**: Internal (`/app/data` — sessions, processing state) and Output (`/output` — archive + medical records folder). PaperlessNGX via REST API, not filesystem.
- **Tech stack research**: See `.claude/rules/tech-stack-2026.md` for full version rationale and security notes.

## Design Spec

`docs/design.md` is the **single source of truth** for all behavior, UX, error handling, and architecture decisions. It covers:

- Core design principle: Human Authority (automation suggests, user decides)
- Scanner communication (eSCL protocol, endpoints, XML formats)
- Web UI wireframes (session setup, scan wizard, results cards, boundary editor)
- UX design rules (friendly language, non-technical target user, no jargon)
- Processing pipeline (6 stages with exact inputs/outputs)
- Persistence and crash recovery (state machine, checkpointing)
- Storage architecture (internal vs output vs PaperlessNGX API)
- Date handling (extracted from OCR, embedded in PDF metadata + PaperlessNGX)
- Testing strategy (4-layer: unit, integration, E2E, in-app practice run)
- Privacy (LLM provider comparison, text-only data sent)
- Deployment (multi-arch Docker, runs on laptop or server)

**When in doubt, the design spec answers it.**

## Implementation Plan

`docs/plans/2026-03-28-scanbox-implementation.md` contains 21 tasks across 3 phases:

| Phase | Tasks | Deliverables |
|-------|-------|-------------|
| **1: Pipeline Core** | 1-10 | Config, models, test fixtures, interleave, blank detect, namer, splitter, OCR, output, pipeline runner, eSCL client. All TDD. |
| **2: API + Web UI** | 11-17 | Database, FastAPI app, scanning/processing/document APIs, SSE, web UI templates, E2E test. |
| **3: Polish** | 18-21 | First-run setup wizard, in-app practice run, document boundary editor, Docker verification. |

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
- Target user is non-technical — UI language must be plain English, no jargon
- Every automated decision is a suggestion the user can override

## CI/CD

`ci.yml`: lint + test + docker build on push/PR.
`lint-pr.yml`: conventional commit PR title validation.
`release-please.yml`: auto-changelog + version bump on push to main.
`release.yml`: multi-arch Docker image (amd64+arm64) to GHCR.
