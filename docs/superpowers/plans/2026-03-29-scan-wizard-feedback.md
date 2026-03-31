# Scan Wizard Real-Time Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace the silent scan wizard with SSE-driven real-time progress showing page counts, pipeline stages, and clear error messages.

**Architecture:** The existing EventBus publishes events for every pipeline stage. A new SSE HTML endpoint renders each event as an HTML fragment. The scan template connects via htmx's SSE extension (`sse-connect`) with `beforeend` swap to accumulate a progress checklist in real-time. Per-page scan events and per-stage completion events are added to the pipeline.

**Tech Stack:** FastAPI SSE (StreamingResponse), htmx SSE extension (already loaded), EventBus (existing)

**Spec:** `docs/superpowers/specs/2026-03-29-scan-wizard-feedback-design.md`

---

### Task 1: Add per-page scan events and stage completion events

**Files:**
- Modify: `scanbox/api/scanning.py:25-47` (_acquire_pages) and `scanbox/api/scanning.py:50-79` (scan_fronts_task)
- Modify: `scanbox/pipeline/runner.py:69-168` (run_pipeline stages)
- Test: `tests/unit/test_scanning.py` (existing) and `tests/unit/test_runner.py` (if exists)

- [x] **Step 1: Add on_page callback to _acquire_pages**

In `scanbox/api/scanning.py`, modify `_acquire_pages` to accept and call an `on_page` callback:

```python
async def _acquire_pages(
    scanner: ESCLClient, output_pdf: Path, on_page: callable = None
) -> int:
    """Scan all pages from the ADF into a single PDF. Returns page count."""
    job_url = await scanner.start_scan()

    pages: list[bytes] = []
    while True:
        page_data = await scanner.get_next_page(job_url)
        if page_data is None:
            break
        pages.append(page_data)
        if on_page:
            await on_page(len(pages))

    if not pages:
        return 0

    # Merge individual page PDFs into one combined PDF
    combined = pikepdf.Pdf.new()
    for page_bytes in pages:
        page_pdf = pikepdf.Pdf.open(BytesIO(page_bytes))
        combined.pages.extend(page_pdf.pages)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    combined.save(output_pdf)
    return len(pages)
```

- [x] **Step 2: Publish page_scanned events in scan_fronts_task and scan_backs_task**

In `scan_fronts_task`, pass an `on_page` callback:

```python
        async def on_page(n):
            await event_bus.publish(
                batch_id, {"type": "page_scanned", "side": "fronts", "page": n}
            )

        page_count = await _acquire_pages(scanner, fronts_pdf, on_page=on_page)
```

Same pattern in `scan_backs_task` with `"side": "backs"`.

- [x] **Step 3: Add stage_complete events in _run_processing**

In `_run_processing`, add a second callback that fires after each stage completes. Add `stage_complete` events after each stage in `run_pipeline`.

The cleanest approach: modify `run_pipeline` in `scanbox/pipeline/runner.py` to call `on_progress` twice per stage — once at start, once at completion with a `"complete": True` flag. Or add a separate `on_stage_complete` callback.

Simpler: add `stage_complete` event publishing directly in `_run_processing` after `run_pipeline` returns. But that only fires once at the end, not per stage.

Best approach: modify `run_pipeline` to call the callback with a `done` flag after each stage:

In `scanbox/pipeline/runner.py`, update the `progress` helper and add `stage_done` helper:

```python
    async def progress(stage: ProcessingStage, detail: str = ""):
        _write_state(ctx, stage)
        if on_progress:
            await on_progress(stage.value, detail)

    async def stage_done(stage: ProcessingStage, detail: str = ""):
        if on_progress:
            await on_progress(stage.value, detail, complete=True)
```

And update the `on_progress` callback signature in runner.py:

```python
async def run_pipeline(
    ctx: PipelineContext,
    on_progress: callable = None,
) -> list[SplitDocument]:
```

The callback now receives `(stage_name, detail, complete=False)`.

Then after each stage, call `stage_done`:

```python
    # Stage 1: Interleave
    if current_stage == ProcessingStage.INTERLEAVING:
        await progress(ProcessingStage.INTERLEAVING, "Combining front and back pages...")
        # ... existing code ...
        total_pages = len(pikepdf.Pdf.open(combined_path).pages)
        await stage_done(ProcessingStage.INTERLEAVING, f"Combined into {total_pages} pages")
        current_stage = ProcessingStage.BLANK_REMOVAL
```

And in `_run_processing` in scanning.py, update the `on_progress` callback:

```python
    async def on_progress(stage_name: str, detail: str = "", complete: bool = False):
        event_type = "stage_complete" if complete else "progress"
        await event_bus.publish(
            batch_id,
            {"type": event_type, "stage": stage_name, "detail": detail},
        )
        if not complete:
            await dispatch_webhook_event(
                "processing.stage_completed",
                {"batch_id": batch_id, "stage": stage_name, "detail": detail},
            )
```

- [x] **Step 4: Add stage_done calls after each pipeline stage**

In `scanbox/pipeline/runner.py`, add `stage_done` calls:

After interleaving (after line 76):
```python
        total_pages = len(pikepdf.Pdf.open(combined_path).pages)
        await stage_done(ProcessingStage.INTERLEAVING, f"Combined into {total_pages} pages")
```

After blank removal (after line 87):
```python
        kept = result.total_pages - len(result.removed_indices)
        await stage_done(
            ProcessingStage.BLANK_REMOVAL,
            f"{kept} pages, {len(result.removed_indices)} blank removed",
        )
```

After OCR (after line 95):
```python
        await stage_done(ProcessingStage.OCR, "OCR complete")
```

After splitting (after line 108):
```python
        await stage_done(ProcessingStage.SPLITTING, f"Found {len(documents)} documents")
```

After naming (after line 168):
```python
        await stage_done(ProcessingStage.NAMING, "All documents named")
```

- [x] **Step 5: Run tests**

Run: `. .venv/bin/activate && python -m pytest tests/ --ignore=tests/unit/test_fixtures.py -q`
Expected: All pass (the callback changes are backward-compatible since `complete` defaults to False)

- [x] **Step 6: Commit**

```bash
git add scanbox/api/scanning.py scanbox/pipeline/runner.py
git commit -m "feat: add per-page scan events and stage completion events"
```

---

### Task 2: Add SSE HTML progress endpoint

**Files:**
- Modify: `scanbox/api/views.py`

- [x] **Step 1: Add the SSE progress endpoint**

In `scanbox/api/views.py`, add a new endpoint that subscribes to the event bus and streams HTML fragments:

```python
@router.get("/batches/{batch_id}/progress", response_class=HTMLResponse)
async def batch_progress_sse(batch_id: str):
    """SSE stream of HTML progress fragments for the scan wizard."""
    from starlette.responses import StreamingResponse

    from scanbox.api.sse import event_bus

    async def generate():
        async for event in event_bus.subscribe(batch_id):
            html = _render_progress_event(event, batch_id)
            if html:
                yield f"data: {html}\n\n"
            if event.get("type") in ("done", "error"):
                break

    return StreamingResponse(generate(), media_type="text/event-stream")


def _render_progress_event(event: dict, batch_id: str) -> str:
    """Render an event bus event as an HTML fragment for the SSE stream."""
    etype = event.get("type", "")
    stage = event.get("stage", "")
    detail = event.get("detail", "")

    spinner = (
        '<div class="w-4 h-4 border-2 border-brand-300 border-t-brand-600 '
        'rounded-full animate-spin inline-block"></div>'
    )
    check = '<span class="text-status-success font-bold">&#10003;</span>'
    error_icon = '<span class="text-status-error font-bold">&#10007;</span>'

    if etype == "progress":
        labels = {
            "scanning_fronts": "Scanning pages from feeder...",
            "scanning_backs": "Scanning back sides...",
            "interleaving": "Combining front and back pages...",
            "blank_removal": "Checking for blank pages...",
            "ocr": "Reading text from your documents...",
            "splitting": "Analyzing documents...",
            "naming": "Naming your documents...",
        }
        label = labels.get(stage, detail or stage)
        return (
            f'<div class="flex items-center gap-2 text-text-secondary" '
            f'id="stage-{stage}">{spinner} {label}</div>'
        )

    if etype == "page_scanned":
        page = event.get("page", "?")
        return f'<div class="ml-6 text-sm text-text-muted">Page {page} scanned</div>'

    if etype == "scan_complete":
        side = event.get("side", "")
        pages = event.get("pages", 0)
        label = f"Scanned {pages} {'front ' if side == 'fronts' else 'back '}pages"
        # Include Alpine trigger for step transitions
        alpine = ""
        if side == "fronts":
            alpine = ' x-init="step1Done = true; currentStep = 2"'
        elif side == "backs":
            alpine = ' x-init="step2Done = true; currentStep = 3"'
        return (
            f'<div class="flex items-center gap-2 text-status-success font-medium"'
            f'{alpine}>{check} {label}</div>'
        )

    if etype == "stage_complete":
        return (
            f'<div class="flex items-center gap-2 text-status-success">'
            f'{check} {detail}</div>'
        )

    if etype == "done":
        count = event.get("document_count", 0)
        return (
            f'<div class="flex items-center gap-2 text-status-success font-semibold mt-2">'
            f'{check} All done! {count} documents ready for review</div>'
            f'<a href="/results/{batch_id}" '
            f'class="inline-block mt-3 bg-brand-600 text-white px-6 py-3 rounded-lg '
            f'font-semibold hover:bg-brand-700 transition-colors no-underline">'
            f'Review Documents</a>'
        )

    if etype == "error":
        msg = _friendly_error(event.get("message", "Something went wrong"))
        return (
            f'<div class="flex items-center gap-2 text-status-error font-medium mt-2">'
            f'{error_icon} {msg}</div>'
            f'<a href="/" class="text-sm text-brand-600 hover:text-brand-700 mt-2 '
            f'inline-block no-underline">Back to Home</a>'
        )

    return ""


def _friendly_error(msg: str) -> str:
    """Convert technical error messages to plain English."""
    lower = msg.lower()
    if "authenticationerror" in lower or "api key" in lower or "api_key" in lower:
        return "No AI service configured. Add your API key in Settings."
    if "connecterror" in lower or "unreachable" in lower or "connection refused" in lower:
        return "Lost connection to the scanner. Is it still on?"
    if "timeout" in lower:
        return "The operation timed out. Please try again."
    # Strip Python exception class prefixes
    if ": " in msg:
        msg = msg.split(": ", 1)[-1]
    return msg
```

- [x] **Step 2: Update scan-fronts to return SSE connection**

Replace the `scan_fronts_html` response. Instead of returning a polling div, return the SSE connection:

```python
    asyncio.create_task(scan_fronts_task(batch_id, db))
    return HTMLResponse(
        f'<div hx-ext="sse" sse-connect="/batches/{batch_id}/progress" '
        f'sse-swap="message" hx-swap="beforeend" class="space-y-1"></div>'
    )
```

- [x] **Step 3: Update scan-backs to return SSE connection**

Same pattern for `scan_backs_html`:

```python
    asyncio.create_task(scan_backs_task(batch_id, db))
    return HTMLResponse(
        f'<div hx-ext="sse" sse-connect="/batches/{batch_id}/progress" '
        f'sse-swap="message" hx-swap="beforeend" class="space-y-1"></div>'
    )
```

- [x] **Step 4: Remove the old polling endpoints**

Delete `scan_status_html` and `scan_back_status_html` — they're replaced by SSE.

- [x] **Step 5: Add w-4 and h-4 CSS classes if missing**

Check `static/css/app.css` for `.w-4` and `.h-4`. If missing, add:

```css
.w-4 { width: 1rem; }
.h-4 { height: 1rem; }
```

Also add `.inline-block` for the spinner (should already exist).

- [x] **Step 6: Run tests, fix broken ones**

Run: `. .venv/bin/activate && python -m pytest tests/ --ignore=tests/unit/test_fixtures.py -q`

Tests referencing the old polling endpoints (`scan-status`, `scan-back-status`) or `hx-trigger="every 2s"` need updating. Update assertions to check for `sse-connect` instead.

- [x] **Step 7: Commit**

```bash
git add scanbox/api/views.py static/css/app.css tests/
git commit -m "feat: add SSE HTML progress endpoint, replace polling"
```

---

### Task 3: Rewrite scan template for SSE

**Files:**
- Modify: `scanbox/templates/scan.html`

- [x] **Step 1: Update scan.html**

The key changes:
1. Scan buttons target a shared progress area that connects to SSE
2. Step 3 (Processing) is simplified — processing progress appears in the SSE stream automatically
3. "Skip backs" triggers processing and the SSE stream continues

The scan buttons POST to `/batches/{id}/scan-fronts` or `/batches/{id}/scan-backs`, targeting `#step1-progress` or `#step2-progress`. The response is the SSE connection div that starts accumulating progress lines.

Update the button in Step 1:
```html
      <button class="bg-brand-600 text-white text-lg px-8 py-4 min-h-14 rounded-lg font-semibold hover:bg-brand-700 active:bg-brand-800 focus:outline-none focus:ring-3 focus:ring-brand-500 focus:ring-offset-2 transition-colors duration-150"
              hx-post="/batches/{{ batch.id }}/scan-fronts"
              hx-target="#step1-progress"
              hx-swap="innerHTML"
              hx-disabled-elt="this">
        Scan Front Sides
      </button>
```

Note `hx-disabled-elt="this"` prevents double-clicking.

Update the button in Step 2 similarly, and add `hx-disabled-elt="this"`.

Update Step 3 to show a simpler waiting message — the actual progress comes from the SSE stream in the step1/step2 progress areas:

```html
  {# Step 3: Processing #}
  <section class="bg-surface-raised border border-border rounded-lg p-6"
           x-show="currentStep >= 3" x-transition>
    <div class="flex items-center gap-3 mb-4">
      <span class="flex items-center justify-center w-8 h-8 rounded-full bg-brand-100 text-brand-700 text-sm font-bold">3</span>
      <h2 class="text-xl font-semibold">Processing</h2>
    </div>
    <p class="text-lg text-text-secondary">Your documents are being processed. Progress appears above.</p>
  </section>
```

- [x] **Step 2: Run template tests**

Run: `. .venv/bin/activate && python -m pytest tests/e2e/test_ui_comprehensive.py::TestScanPage -v`

Update assertions for `hx-disabled-elt` and removal of `hx-trigger="every 2s"`.

- [x] **Step 3: Commit**

```bash
git add scanbox/templates/scan.html tests/
git commit -m "feat: rewrite scan template with SSE progress"
```

---

### Task 4: Test, rebuild, verify

- [x] **Step 1: Run full test suite**

```bash
. .venv/bin/activate && python -m pytest tests/ --ignore=tests/unit/test_fixtures.py -q
```

- [x] **Step 2: Lint**

```bash
ruff format scanbox/ tests/
ruff check scanbox/ tests/
```

- [x] **Step 3: Commit any fixes**

```bash
git add -A && git commit -m "chore: fix lint and test issues"
```

- [x] **Step 4: Rebuild Docker container**

```bash
podman compose down && podman compose up -d --build
```

- [x] **Step 5: Verify in browser**

Navigate to http://localhost:8090, start a scan, and confirm:
- Page-by-page progress appears during scanning
- Pipeline stages appear with spinners then checkmarks
- Error messages are clear and actionable
- "Review Documents" link appears on completion

- [x] **Step 6: Push and create PR**

```bash
git push -u origin <branch>
gh pr create --title "feat: real-time scan wizard progress via SSE" --body "..."
gh pr merge <number> --squash --delete-branch
git checkout main && git pull --rebase
```
