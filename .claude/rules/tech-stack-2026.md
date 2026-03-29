# Tech Stack Research — March 2026

This file captures the results of a comprehensive research effort on 2026-03-28 to ensure ScanBox uses the latest best practices. All version numbers and recommendations are current as of this date.

## CRITICAL: litellm Security Incident

**Pin litellm to exactly 1.82.6.** Versions 1.82.7 and 1.82.8 were compromised in a supply chain attack on March 24, 2026 (poisoned Trivy GitHub Action in litellm's CI/CD, TeamPCP threat actor). Both malicious versions have been yanked from PyPI. litellm has paused all new releases pending a security review.

`pip install litellm` currently resolves to 1.82.6 (safe). The `==1.82.6` pin in pyproject.toml prevents accidentally installing a future compromised version.

**Action if you installed during the March 24-25 window:** Audit your environment for credential exfiltration.

## Dependency Versions

| Package | Version | Why This Version |
|---------|---------|-----------------|
| Python | 3.13.x | Sweet spot: stable, broad library support, improved error messages. 3.14 is too new (some C extensions lack wheels). |
| FastAPI | >= 0.135.0 | v0.135 added native SSE support. Pydantic v2 only (v1 dropped in 0.128). |
| pikepdf | >= 10.5 | Gold standard for PDF split/merge/metadata. Same author as ocrmypdf. MPL-2.0. |
| ocrmypdf | >= 17.4 | Requires Ghostscript now (in addition to Tesseract). Handles deskew, rotation, multi-core. |
| litellm | == 1.82.6 | Exact pin. See security incident above. |
| Pillow | >= 12.1 | Image processing for blank page detection. No lighter alternative exists. |
| pdf2image | >= 1.17 | Wraps Poppler's pdftoppm. Still needed — pikepdf can't render pages to images. |
| httpx | >= 0.28 | Best async HTTP client. Project in maintenance mode but fully stable. |
| aiosqlite | >= 0.22 | Standard async SQLite. No newer alternatives. |
| jinja2-fragments | >= 1.5 | Renders individual Jinja2 blocks for htmx partial updates. Drop-in for FastAPI's Jinja2Templates. |
| htmx | 2.0.8 | **NEW — added to stack.** Server-driven HTML swapping + SSE extension for progress. ~14KB. |
| Alpine.js | 3.15.x | Client-side UI state (dropdowns, modals, toggles). Complements htmx. ~15KB. |
| Tailwind CSS | 4.2.x | CSS-native config, Rust engine. Use standalone CLI at Docker build time — no Node.js. |
| Ruff | >= 0.15 | Now with `target-version = "py313"` and `UP` (pyupgrade) + `B` (bugbear) + `SIM` (simplify) rules. |
| pytest-asyncio | >= 1.3 | Standard async test support. Use `asyncio_mode = "auto"`. |
| mcp | >= 1.0 | Model Context Protocol SDK for AI agent integration. Exposes ScanBox tools/resources to MCP clients. |

## Frontend Stack: htmx + Alpine.js + Tailwind CSS

The original design spec listed "Alpine.js + Tailwind CSS." Research shows htmx should be added:

- **htmx** handles all server communication: scanning triggers, status updates, form submissions, page swaps. Its SSE extension (`hx-ext="sse"`) is perfect for the scanning progress indicator — 3 HTML attributes, zero custom JavaScript.
- **Alpine.js** handles client-side UI state that doesn't involve the server: dropdowns, modals, form validation feedback, expand/collapse.
- **Tailwind CSS v4** handles styling. Use the standalone CLI binary at Docker build time to generate minified CSS. No Node.js dependency.

The combination replaces all custom JavaScript we'd otherwise write for fetch polling, DOM updates, and UI interactions.

### htmx SSE Pattern for Scanning Progress

Server (FastAPI):
```python
from fastapi.responses import StreamingResponse

@app.get("/api/batches/{batch_id}/progress")
async def batch_progress(batch_id: str):
    async def generate():
        async for update in pipeline.progress_stream(batch_id):
            html = render_progress_fragment(update)
            yield f"data: {html}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

Client (HTML):
```html
<div hx-ext="sse" sse-connect="/api/batches/123/progress" sse-swap="message">
    <div id="progress">Starting...</div>
</div>
```

### jinja2-fragments for Partial Rendering

Instead of duplicating templates for htmx responses, use `jinja2-fragments` to render individual blocks:

```python
from jinja2_fragments.fastapi import Jinja2Blocks

templates = Jinja2Blocks(directory="scanbox/templates")

@app.get("/batches/{id}")
async def get_batch(request: Request, id: str):
    batch = await get_batch(id)
    # Full page for direct navigation, just the cards block for htmx
    block = "cards" if request.headers.get("HX-Request") else None
    return templates.TemplateResponse("results.html", {"batch": batch}, block_name=block)
```

### Tailwind CSS v4 in Docker (No Node.js)

Download the standalone CLI binary at Docker build time:

```dockerfile
# In Dockerfile build stage
ARG TAILWIND_VERSION=4.2.0
ADD https://github.com/tailwindlabs/tailwindcss/releases/download/v${TAILWIND_VERSION}/tailwindcss-linux-x64 /usr/local/bin/tailwindcss
RUN chmod +x /usr/local/bin/tailwindcss
COPY static/css/input.css static/css/input.css
COPY scanbox/templates/ scanbox/templates/
RUN tailwindcss -i static/css/input.css -o static/css/app.css --minify
```

## Docker Base Image

**Use `python:3.13-slim`** (based on Debian Trixie). Bookworm (Debian 12) is entering LTS in August 2026 and is no longer recommended for new projects.

System deps for the runtime image:
```
tesseract-ocr tesseract-ocr-eng ghostscript poppler-utils
```

Note: `ghostscript` is a new requirement for ocrmypdf >= 17.

## Claude Code Development Workflow

### Quality Gates (All Active)

1. **Pre-commit hook** (`.githooks/pre-commit`) — ruff check + format before every commit
2. **Claude Code PreToolUse hooks** (`.claude/settings.json`) — lint + format + full test suite before `git commit`; lint + format + rebase before `git push`
3. **Permission deny rules** — force push, hard reset, checkout-dot, clean -f blocked
4. **GitHub CI** — lint + test with coverage (>= 85% gate) + Docker build
5. **Worktree enforcement** — hooks enforce isolated worktrees for parallel agents

## Decisions NOT Changed

These were evaluated and confirmed as still correct:

- **FastAPI over Litestar**: FastAPI has 10x the ecosystem. Litestar's 2x serialization speed doesn't matter for this app.
- **pikepdf over pypdf**: pikepdf is faster and handles malformed PDFs. pypdf is pure-Python fallback but not needed.
- **No PyMuPDF**: AGPL license is incompatible with MIT-licensed project.
- **No SANE/sane-airscan**: Direct eSCL HTTP is simpler and has fewer dependencies in Docker.
- **SQLite over PostgreSQL**: Single-user app, no concurrency concerns. aiosqlite is sufficient.
- **Server-rendered over SPA**: htmx + Jinja2 is simpler, more accessible, and requires no JS build step.
