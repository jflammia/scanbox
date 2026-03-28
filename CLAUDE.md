# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Operating Principles

These are non-negotiable. Follow them even when the user doesn't explicitly ask:

- **Never work around failures.** If CI fails, a push is rejected, or a workflow breaks — diagnose and fix the root cause. Do not use manual workarounds.
- **Never add AI attribution.** No `Co-Authored-By: Claude`, `Signed-off-by`, or similar trailers in commits, PRs, or any git metadata.
- **Always run `ruff format` before committing.** The pre-commit hook will block unformatted code. Format proactively rather than getting blocked.
- **Verify CI after pushing.** Run `gh run list --limit 2` and confirm green. If red, fix it immediately.

## Commands

```bash
# Install
pip install -e ".[dev]"              # Dev dependencies (includes pytest, ruff)

# Repo setup (run once after clone)
bash .githooks/setup.sh              # Git hooks + rebase config

# Test
pytest                                # All tests
pytest tests/unit/                    # Unit tests only
pytest tests/integration/             # Integration tests only
pytest -k "interleave"               # Pattern match

# Lint
ruff format scanbox/ tests/          # Auto-format (run BEFORE committing)
ruff check scanbox/ tests/           # Check style (line-length=100)

# Commit flow (always this sequence)
git add <files>
git commit -m "..."                   # Pre-commit hook checks lint+format
git pull                              # Rebase on remote (autostash handles dirty state)
git push                              # Claude Code hook: lint + format + pull before push

# Run locally
docker compose up                     # Start ScanBox at http://localhost:8090

# GitHub
gh issue list --state open            # Check for issues
gh run list --limit 5                 # Check CI status
gh pr list                            # Check for Release PRs
gh pr merge <N> --merge --admin       # Merge a Release PR (regular merge, not squash)
```

## Architecture

**Data flow:** Scanner (eSCL HTTP) -> FastAPI backend -> Processing pipeline (interleave -> blank removal -> OCR -> AI split -> name) -> Output (files + PaperlessNGX API)

**Key layers:**
- `scanbox/scanner/` - eSCL protocol client for HP scanner communication
- `scanbox/pipeline/` - Document processing: interleave, blank detection, OCR, AI splitting, naming, output
- `scanbox/api/` - FastAPI route handlers for sessions, scanning, processing, documents
- `scanbox/templates/` - Jinja2 HTML templates for the web UI
- `scanbox/config.py` - All configuration via environment variables
- `scanbox/database.py` - SQLite for sessions, batches, documents

**Tech stack:** Python 3.12, FastAPI, pikepdf, ocrmypdf, litellm (multi-provider LLM), Alpine.js + Tailwind CSS

**Design spec:** `docs/design.md` — the authoritative design document

## CI/CD

GitHub Actions: `ci.yml` runs lint + test + docker build on push/PR. `lint-pr.yml` enforces conventional commits in PR titles. `release-please.yml` auto-creates a Release PR with changelog + version bump on each push to main. Merging the Release PR triggers `release.yml` which builds multi-arch (amd64+arm64) Docker image to GHCR. Use conventional commit prefixes in PR titles (`feat:`, `fix:`, `docs:`, etc.).

## Git Workflow

**Linear history only. No merge commits.**

| Operation | Correct | Wrong |
|-----------|---------|-------|
| Update branch | `git rebase origin/main` | `git merge main` |
| Pull changes | `git pull` (configured to rebase) | - |
| Integrate to main | `git merge --ff-only <branch>` | `git merge <branch>` |

Git config enforces this: `pull.rebase=true`, `merge.ff=only`. Run `bash .githooks/setup.sh` after cloning.

Destructive operations are hard-blocked in `.claude/settings.json` (deny rules): force push, hard reset, checkout-dot, clean -f. These block even in bypass mode.

### Commits & PRs

- **Conventional commits required**: `feat:`, `fix:`, `docs:`, `ci:`, `chore:`, `refactor:`, `test:`, `perf:`, `build:`, `style:`, `revert:`
- **Never add AI attribution trailers**
- **Squash merge** feature/fix PRs (PR title becomes the conventional commit release-please parses)
- **Regular merge** release-please Release PRs (not squash)

## Quality Gates

Four layers block bad code from reaching main:

1. **Permission deny rules** (`.claude/settings.json`) — hard-block force push, hard reset, checkout-dot, clean -f. Cannot be bypassed.
2. **Git pre-commit hook** (`.githooks/pre-commit`) — runs `ruff check` + `ruff format --check` before every commit. Activate with: `bash .githooks/setup.sh`
3. **Claude Code hooks** (`.claude/settings.json`) — runs lint + format + tests before `git commit`, lint + format + `git pull --rebase` before `git push`
4. **GitHub branch protection** — PRs require Lint, Test, and Docker Build checks to pass

If a commit is blocked, fix the issue first. Do not bypass with `--no-verify`.

## Key Conventions

- ruff line-length is 100
- Python >= 3.12 required
- All env vars loaded in `scanbox/config.py` with sensible defaults
- LLM provider is configurable (Anthropic, OpenAI, Ollama) via `LLM_PROVIDER` env var
- PaperlessNGX integration is optional
