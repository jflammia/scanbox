# Scan Wizard Real-Time Feedback

Replace the silent scan wizard with SSE-driven real-time progress showing every stage as it happens — page counts during scanning, pipeline stage checklist during processing, clear error messages on failure.

## Architecture

The existing EventBus + SSE infrastructure publishes events for every pipeline stage. The scan wizard template connects to an HTML SSE stream that renders each event as a progress line item. Events accumulate (append, not replace) so the user sees the full history.

## New SSE HTML Endpoint

### `GET /batches/{batch_id}/progress` (SSE, HTML fragments)

Subscribes to `event_bus` for the batch. Each event renders as an HTML fragment sent as an SSE `message` event. The template uses `hx-ext="sse"` with `sse-connect` and `sse-swap="beforeend"` to append each fragment.

**Event rendering:**

| Event | HTML |
|-------|------|
| `{type: "progress", stage: "scanning_fronts"}` | Spinner + "Scanning pages from feeder..." |
| `{type: "page_scanned", side: "fronts", page: N}` | Indented "Page N scanned" |
| `{type: "scan_complete", side: "fronts", pages: N}` | Checkmark + "Scanned N pages" + Alpine trigger `step1Done=true; currentStep=2` |
| `{type: "progress", stage: "scanning_backs"}` | Spinner + "Scanning back sides..." |
| `{type: "page_scanned", side: "backs", page: N}` | Indented "Page N scanned" |
| `{type: "scan_complete", side: "backs", pages: N}` | Checkmark + "Scanned N back pages" |
| `{type: "progress", stage: "interleaving", detail: "..."}` | Spinner + "Combining front and back pages..." |
| `{type: "stage_complete", stage: "interleaving", detail: "..."}` | Checkmark + detail |
| `{type: "progress", stage: "blank_removal", detail: "..."}` | Spinner + "Checking for blank pages..." |
| `{type: "stage_complete", stage: "blank_removal", detail: "..."}` | Checkmark + detail (e.g., "3 pages, 0 blank removed") |
| `{type: "progress", stage: "ocr", detail: "..."}` | Spinner + "Reading text from your documents..." |
| `{type: "stage_complete", stage: "ocr", detail: "..."}` | Checkmark + "OCR complete" |
| `{type: "progress", stage: "splitting", detail: "..."}` | Spinner + "Analyzing documents..." |
| `{type: "stage_complete", stage: "splitting", detail: "..."}` | Checkmark + detail |
| `{type: "progress", stage: "naming", detail: "..."}` | Spinner + "Naming your documents..." |
| `{type: "stage_complete", stage: "naming", detail: "..."}` | Checkmark + detail |
| `{type: "done", document_count: N}` | Checkmark + "All done! N documents ready for review" + link to results page |
| `{type: "error", message: "..."}` | Red X + plain-English error + action link |

**Error message mapping:**

| Error contains | User-facing message |
|---------------|---------------------|
| `AuthenticationError` or `API Key` | "No AI service configured. Add your API key in Settings." |
| `ConnectError` or `unreachable` (scanner) | "Lost connection to the scanner. Is it still on?" |
| Other | The error message, stripped of class names and stack traces |

## Pipeline Changes

### Per-page scanning progress

Modify `_acquire_pages()` in `scanbox/api/scanning.py` to accept an `on_page` callback and call it after each page is pulled from the ADF:

```python
async def _acquire_pages(scanner, output_pdf, on_page=None):
    # ... existing loop ...
    while page_data := await scanner.get_next_page(job_url):
        page_count += 1
        # ... write page ...
        if on_page:
            await on_page(page_count)
```

`scan_fronts_task` and `scan_backs_task` pass a callback that publishes `page_scanned` events:

```python
async def on_page(n):
    await event_bus.publish(batch_id, {"type": "page_scanned", "side": "fronts", "page": n})
```

### Per-stage completion events

Modify `_run_processing()` to publish `stage_complete` events after each pipeline stage finishes (in addition to the existing `progress` events at stage start). The `on_progress` callback in the pipeline runner fires at stage START. Add a second event after each stage completes with the result detail:

- After interleaving: `{type: "stage_complete", stage: "interleaving", detail: "Combined into N pages"}`
- After blank removal: `{type: "stage_complete", stage: "blank_removal", detail: "N pages, M blank removed"}`
- After OCR: `{type: "stage_complete", stage: "ocr", detail: "OCR complete"}`
- After splitting: `{type: "stage_complete", stage: "splitting", detail: "Found N documents"}`
- After naming: `{type: "stage_complete", stage: "naming", detail: "All documents named"}`

## Template Changes (`scan.html`)

### SSE connection flow

After the user clicks "Scan Front Sides" and the POST succeeds, the progress area connects to the SSE stream:

```html
<div id="scan-progress"
     hx-ext="sse"
     sse-connect="/batches/{{ batch.id }}/progress"
     sse-swap="message"
     hx-swap="beforeend"
     class="space-y-1">
</div>
```

Each SSE event appends a new HTML line. The user sees:

```
Scanning pages from feeder...
  Page 1 scanned
  Page 2 scanned
  Page 3 scanned
✓ Scanned 3 pages

Combining front and back pages...
✓ Combined into 3 pages

Checking for blank pages...
✓ 3 pages, 0 blank removed

Reading text from your documents...
✓ OCR complete

Analyzing documents...
✓ Found 2 documents

Naming your documents...
✓ All done! 2 documents ready for review
→ Review Documents
```

### Step transitions

Step transitions are still driven by Alpine.js, but triggered by HTML fragments from the SSE stream instead of polling:

- `scan_complete` for fronts includes `x-init="step1Done = true; currentStep = 2"`
- `scan_complete` for backs includes `x-init="step2Done = true; currentStep = 3"`
- `done` includes a link to `/results/{batch_id}`

### Step 2 (Backs) and Step 3 (Processing)

Step 2 still shows the flip illustration and "Scan Back Sides" / "Skip" buttons. When scanning backs, the same SSE stream continues appending.

Step 3 is removed as a separate visual step — processing progress appears directly in the SSE progress area after scanning completes. The user sees a continuous flow from scanning through to "All done!"

### Scan buttons

The "Scan Front Sides" and "Scan Back Sides" buttons:
1. POST to the existing `/batches/{id}/scan-fronts` or `/batches/{id}/scan-backs` endpoint
2. The HTML response now returns the SSE connection div (instead of a polling div)
3. Button is disabled/hidden after click to prevent double-scanning

## Modified Endpoints

### `POST /batches/{batch_id}/scan-fronts` (HTML)

Updated response — instead of returning a polling div, returns:
- Error HTML if scanner not configured or wrong batch state
- The SSE connection div on success (starts accumulating progress)

### `POST /batches/{batch_id}/scan-backs` (HTML)

Same pattern as scan-fronts.

### Removed

- `GET /batches/{batch_id}/scan-status` (polling endpoint) — replaced by SSE
- `GET /batches/{batch_id}/scan-back-status` (polling endpoint) — replaced by SSE

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `scanbox/api/views.py` | Modify | Add SSE progress endpoint, update scan-fronts/backs responses, remove polling endpoints |
| `scanbox/api/scanning.py` | Modify | Add per-page callback to `_acquire_pages`, add `stage_complete` events |
| `scanbox/templates/scan.html` | Modify | SSE connection, remove Step 3 static content |
| `tests/` | Modify | Update scan wizard tests for new SSE behavior |

## Out of Scope

- Results page changes
- Save flow changes
- Document boundary editor
- Any changes to the JSON API or MCP tools
