# Headless Execution Guide

Instructions for headless Claude Code agents working on ScanBox without human interaction.

## Getting Started

1. Read `CLAUDE.md` (loaded automatically)
2. Check git log and existing files to understand current state
3. Follow TDD: write test → confirm fail → implement → confirm pass → commit

## Decision Authority

| Situation | Resolution |
|-----------|-----------|
| Ambiguity in specs | **`docs/design.md` wins** over all other docs |
| Neither plan nor spec covers it | Simplest choice that serves a non-technical user |
| Multiple valid approaches | Fewer moving parts wins |
| Library/API behavior unclear | Research via web search, don't guess |
| Pre-commit hook blocks commit | Fix the issue. Never `--no-verify`. |

## Allowed Without Asking

- Fix lint/format/test failures
- Add error handling for edge cases in the design spec
- Create directories and `__init__.py` files
- Run tests, commit, push to feature branches
- Research library APIs via web search

## Never Do

- Change the design (UI layout, pipeline stages, storage model)
- Add features not in the spec
- Skip tests or use `--no-verify`
- Force push or add AI attribution
- Break the API without updating tests

## Environment Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
bash .githooks/setup.sh
python -m tests.generate_fixtures

# macOS system deps
brew install tesseract poppler ghostscript
```

## Workflow

After each change:

1. `ruff format scanbox/ tests/`
2. `ruff check scanbox/ tests/`
3. `pytest` (all 532 tests pass)
4. Commit with conventional message
5. Push to feature branch

## Key Files

| Priority | File | Why |
|----------|------|-----|
| 1 | `CLAUDE.md` | Project overview, patterns, conventions |
| 2 | `docs/design.md` | Authoritative behavior spec |
| 3 | `docs/api-spec.md` | REST API reference |
| 4 | `docs/mcp-server.md` | MCP tools and resources |
| 5 | `.claude/rules/implementation-context.md` | Technical gotchas |
