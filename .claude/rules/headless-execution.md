# Headless Execution Guide

This project is designed to be implemented by **headless Claude Code agents** without human interaction during each task. This file explains how to work autonomously.

## How to Start Implementation

1. Read `CLAUDE.md` (loaded automatically)
2. Read the implementation plan: `docs/plans/2026-03-28-scanbox-implementation.md`
3. Check which tasks are already completed: look at existing files and git log
4. Start the next incomplete task
5. Follow TDD: write test → run to confirm fail → implement → run to confirm pass → commit

## Decision Authority

When implementing, you will encounter ambiguity. Here's how to resolve it:

| Situation | What to Do |
|-----------|-----------|
| Plan says one thing, design spec says another | **Design spec wins** (`docs/design.md`) |
| Neither plan nor spec covers it | Make the simplest choice that serves a non-technical user |
| Multiple valid approaches | Pick the one with fewer moving parts |
| External dependency question (API format, library behavior) | Research via web search or Context7, don't guess |
| Test is hard to write for this case | Write it anyway — if it's hard to test, the design may need simplifying |
| Pre-commit hook blocks your commit | Fix the issue (format, lint, test failure). Never `--no-verify`. |

## What You Can Do Without Asking

- Implement any task in the plan
- Fix lint/format issues
- Add error handling for edge cases described in the design spec
- Create directories and `__init__.py` files
- Install Python packages listed in pyproject.toml
- Run tests and fix failures
- Commit and push to main (for small changes) or create a PR (for larger changes)
- Research library APIs via web search

## What You Should NOT Do

- Change the design (UI layout, pipeline stages, storage model) — that's in the spec
- Add features not in the plan or design spec
- Skip tests
- Use `--no-verify` on commits
- Force push
- Add AI attribution to commits
- Make breaking changes to the API without updating tests

## Environment Setup (Run Once)

If the venv doesn't exist yet:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
bash .githooks/setup.sh
```

If fixtures don't exist yet:

```bash
python -m tests.generate_fixtures
```

On macOS, install system deps:

```bash
brew install tesseract poppler ghostscript
```

## Progress Tracking

After completing each task:
1. All tests pass: `pytest tests/unit/ -v` (at minimum)
2. Code is formatted: `ruff format scanbox/ tests/`
3. Code passes lint: `ruff check scanbox/ tests/`
4. Changes are committed with a conventional commit message
5. Check which task is next in the plan

## Phase Boundaries

At the end of each phase, run the full test suite and commit a milestone:

```bash
ruff format scanbox/ tests/
ruff check scanbox/ tests/
pytest -v
git add -A
git commit -m "milestone: complete Phase N — [description]"
git push
```

## Key Files to Read Before Starting

| Priority | File | Why |
|----------|------|-----|
| 1 | `CLAUDE.md` | Project overview, architecture, conventions |
| 2 | `docs/plans/2026-03-28-scanbox-implementation.md` | Task-by-task implementation with code |
| 3 | `docs/design.md` | Authoritative spec for all behavior |
| 4 | `.claude/rules/implementation-context.md` | Design decisions, gotchas, technical notes |
| 5 | `pyproject.toml` | Dependencies and tool config |
