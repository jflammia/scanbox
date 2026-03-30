# Stage-Aware Pipeline with Granular Error Handling

Redesign the pipeline runner to support stage-level pause/resume, document-level error isolation, a dead letter queue (DLQ) for deferred problem handling, and full observability at every step.

## Problem

The current pipeline (`scanbox/pipeline/runner.py`) runs all 5 stages as a single uninterruptible operation. If any stage fails, the entire batch goes to `error` state with no way to inspect intermediate results, retry individual stages, or skip problematic items. Users have no visibility into what each stage produced — they see "processing..." then either results or an error.

## Execution Model

Three flows, one pipeline:

**Happy path:** All stages auto-advance. User sees a progress checklist (stage-by-stage), then lands on results. Each stage's output is inspectable even though no intervention was needed.

**Error with pause:** Stage-level errors (tesseract crash, LLM timeout) pause the pipeline. Document-level issues (low confidence splits, ambiguous boundaries) isolate affected documents while the rest continue. User sees what went wrong, can fix or exclude, and resume.

**Error with DLQ (configured):** A per-batch or global setting. When enabled, errors don't pause — problem items are pushed to a dead letter queue and the pipeline continues with what it can. The DLQ is reviewable later.

## Pipeline State Machine

### Extended state.json

Replace the current flat `{"stage": "..."}` with a richer state model:

```json
{
  "stage": "splitting",
  "status": "paused",
  "stages": {
    "interleaving": {
      "status": "completed",
      "started_at": "2026-03-30T14:00:00Z",
      "completed_at": "2026-03-30T14:00:02Z",
      "result": {"total_pages": 26}
    },
    "blank_removal": {
      "status": "completed",
      "started_at": "2026-03-30T14:00:02Z",
      "completed_at": "2026-03-30T14:00:03Z",
      "result": {"kept": 19, "removed": 7, "removed_indices": [1, 3, 5, 7, 9, 11, 13]}
    },
    "ocr": {
      "status": "completed",
      "started_at": "2026-03-30T14:00:03Z",
      "completed_at": "2026-03-30T14:00:45Z",
      "result": {"pages_processed": 19}
    },
    "splitting": {
      "status": "paused",
      "started_at": "2026-03-30T14:00:45Z",
      "error": null,
      "result": {
        "documents_found": 11,
        "low_confidence": [
          {"start_page": 7, "end_page": 8, "confidence": 0.45, "reason": "ambiguous boundary"}
        ]
      }
    },
    "naming": {
      "status": "pending"
    }
  },
  "dlq": [],
  "config": {
    "auto_advance_on_error": false,
    "confidence_threshold": 0.7
  }
}
```

### Stage Statuses

Each stage has one of:
- `pending` — not yet started
- `running` — currently executing
- `completed` — finished successfully
- `paused` — finished with issues that need user attention (document-level)
- `error` — stage-level failure (crash, timeout, etc.)
- `skipped` — user chose to skip this stage

### Pipeline-Level Status

The overall pipeline status is derived:
- `running` — a stage is currently executing
- `paused` — a stage is in `paused` or `error` status, waiting for user action
- `completed` — all stages are `completed` or `skipped`

### Batch State Extension

Add a new batch state `PAUSED` between `PROCESSING` and `REVIEW`:

```
PROCESSING → PAUSED → PROCESSING (resume) → REVIEW
PROCESSING → REVIEW (happy path, no pause needed)
PROCESSING → ERROR (unrecoverable)
```

The `PAUSED` state means the pipeline stopped at a stage checkpoint and is waiting for user action.

## Stage Results & Inspectability

Every stage writes its results to disk (most already do). The state.json `result` field for each stage provides a summary. API endpoints expose these for inspection.

| Stage | Output files | Result summary |
|-------|-------------|----------------|
| Interleaving | `combined.pdf` | `{total_pages}` |
| Blank removal | `cleaned.pdf`, `blank_removal.json` | `{kept, removed, removed_indices}` |
| OCR | `ocr.pdf`, `text_by_page.json` | `{pages_processed}` |
| Splitting | `splits.json` | `{documents_found, low_confidence: [...]}` |
| Naming | `documents/*.pdf`, `splits.json` (updated) | `{documents_named, filenames: [...]}` |

No new files — the pipeline already produces all of these. The change is recording the summary in state.json and exposing it via API.

## Document-Level Error Isolation

### During Splitting

The splitter may produce documents with low confidence. Instead of failing the whole stage:

1. Splitter returns all documents (high and low confidence)
2. Pipeline checks each document's confidence against `confidence_threshold` (default 0.7)
3. Documents above threshold continue to naming
4. Documents below threshold are flagged in `state.json` as `low_confidence`
5. If DLQ mode is off: pipeline pauses, batch state goes to `PAUSED`
6. If DLQ mode is on: low-confidence documents are moved to `dlq` array, rest continue

### During Naming

If a specific document fails to name (e.g., invalid characters, metadata embedding error):

1. Error is caught per-document, not per-stage
2. Successfully named documents proceed
3. Failed documents are flagged or moved to DLQ
4. Pipeline pauses if not in DLQ mode

### DLQ Structure

```json
{
  "dlq": [
    {
      "id": "dlq-001",
      "stage": "splitting",
      "document": {"start_page": 7, "end_page": 8, "document_type": "Other", "confidence": 0.45},
      "reason": "Confidence 0.45 below threshold 0.7",
      "added_at": "2026-03-30T14:00:46Z"
    }
  ]
}
```

DLQ items can be:
- **Retried** — push back into the pipeline at the appropriate stage
- **Manually resolved** — user provides the correct metadata, pipeline continues
- **Discarded** — user decides these pages aren't needed

## API Endpoints

### New Endpoints

```
GET  /api/batches/{batch_id}/pipeline          — Full pipeline state (all stages, results, DLQ)
POST /api/batches/{batch_id}/pipeline/resume    — Resume a paused pipeline
POST /api/batches/{batch_id}/pipeline/retry     — Retry the current failed/paused stage
POST /api/batches/{batch_id}/pipeline/skip      — Skip the current stage and advance
POST /api/batches/{batch_id}/pipeline/advance   — Advance from a paused stage (accept current results)
GET  /api/batches/{batch_id}/pipeline/stage/{stage}  — Get results for a specific stage
GET  /api/batches/{batch_id}/dlq               — List DLQ items
POST /api/batches/{batch_id}/dlq/{item_id}/retry    — Retry a DLQ item
POST /api/batches/{batch_id}/dlq/{item_id}/resolve  — Manually resolve a DLQ item
DELETE /api/batches/{batch_id}/dlq/{item_id}        — Discard a DLQ item
```

### Modified Endpoints

```
GET  /api/batches/{batch_id}                   — Now includes pipeline_status and current_stage
GET  /api/batches/{batch_id}/progress/stream   — SSE events now include stage results and DLQ additions
POST /api/batches/{batch_id}/reprocess         — Now accepts optional start_stage parameter
```

### Batch Import Integration

`POST /api/batches/import` gains an optional `pipeline_config` parameter:

```json
{
  "auto_advance_on_error": false,
  "confidence_threshold": 0.7,
  "start_stage": "interleaving"
}
```

## SSE Event Enhancements

New event types alongside existing ones:

```json
{"type": "stage_result", "stage": "blank_removal", "result": {"kept": 19, "removed": 7}}
{"type": "pipeline_paused", "stage": "splitting", "reason": "2 documents below confidence threshold"}
{"type": "dlq_item_added", "item_id": "dlq-001", "stage": "splitting", "reason": "..."}
{"type": "pipeline_resumed", "stage": "splitting"}
```

## Configuration

### Per-Batch Config

Stored in `state.json` under `config`:

```json
{
  "auto_advance_on_error": false,
  "confidence_threshold": 0.7
}
```

Set via:
- `POST /api/batches/import` body
- `POST /api/batches/{batch_id}/pipeline/configure` (new endpoint)
- Default from global config

### Global Config

Two new env vars:

```
PIPELINE_AUTO_ADVANCE_ON_ERROR=false    # default: pause on errors
PIPELINE_CONFIDENCE_THRESHOLD=0.7       # default: 0.7
```

Added to `Config` class.

## Runner Refactoring

### Current: Linear execution

```python
async def run_pipeline(ctx, on_progress) -> list[SplitDocument]:
    # stage 1...
    # stage 2...
    # stage 3...
    # stage 4...
    # stage 5...
    return documents
```

### New: Stage-aware execution with checkpointing

```python
async def run_pipeline(ctx, on_progress, pipeline_config=None) -> PipelineResult:
    state = PipelineState.load(ctx)

    for stage in state.pending_stages():
        state.mark_running(stage)
        try:
            result = await _run_stage(stage, ctx, state)
            state.mark_completed(stage, result)
            await _emit_stage_result(stage, result, on_progress)

            # Check for document-level issues
            issues = _check_for_issues(stage, result, pipeline_config)
            if issues:
                if pipeline_config.auto_advance_on_error:
                    state.add_to_dlq(issues)
                else:
                    state.mark_paused(stage, issues)
                    return PipelineResult(status="paused", state=state)

        except Exception as e:
            state.mark_error(stage, str(e))
            if pipeline_config.auto_advance_on_error:
                state.add_to_dlq(stage_error=e)
                continue
            return PipelineResult(status="paused", state=state)

    return PipelineResult(status="completed", state=state, documents=...)
```

Key changes:
- `run_pipeline` returns a `PipelineResult` (not just documents) with status and full state
- Each stage is independently callable via `_run_stage(stage, ctx, state)`
- State is a proper class (`PipelineState`) with methods, not a raw dict
- Document-level issues are detected after each stage
- DLQ items are accumulated in state
- Pipeline can resume from any stage by reloading state

### PipelineResult

```python
@dataclass
class PipelineResult:
    status: str  # "completed", "paused", "error"
    state: PipelineState
    documents: list[SplitDocument] | None = None
    paused_stage: str | None = None
    paused_reason: str | None = None
```

### PipelineState Class

```python
class PipelineState:
    stages: dict[str, StageState]
    dlq: list[DLQItem]
    config: PipelineConfig

    @classmethod
    def load(cls, ctx: PipelineContext) -> PipelineState: ...
    def save(self, ctx: PipelineContext) -> None: ...
    def pending_stages(self) -> list[ProcessingStage]: ...
    def mark_running(self, stage: ProcessingStage) -> None: ...
    def mark_completed(self, stage: ProcessingStage, result: dict) -> None: ...
    def mark_paused(self, stage: ProcessingStage, issues: list) -> None: ...
    def mark_error(self, stage: ProcessingStage, error: str) -> None: ...
    def add_to_dlq(self, items: list[DLQItem]) -> None: ...
    def resume_from(self, stage: ProcessingStage) -> None: ...
```

## What Changes

| File | Change |
|------|--------|
| `scanbox/models.py` | Add `PAUSED` to `BatchState`, add `PipelineResult`, `PipelineConfig`, `DLQItem`, `StageState` models |
| `scanbox/pipeline/runner.py` | Refactor to stage-aware execution with `PipelineState` class, `_run_stage()` dispatcher, document-level error isolation |
| `scanbox/config.py` | Add `PIPELINE_AUTO_ADVANCE_ON_ERROR`, `PIPELINE_CONFIDENCE_THRESHOLD` |
| `scanbox/api/batches.py` | Add pipeline control endpoints (resume, retry, skip, advance, stage results, DLQ) |
| `scanbox/api/scanning.py` | Update `_run_processing` to handle `PipelineResult` status (paused vs completed) |
| `scanbox/api/import_batch.py` | Accept `pipeline_config` parameter |
| `scanbox/api/sse.py` | No changes (event bus already supports arbitrary events) |
| `tests/conftest.py` | Update `load_test_pile` to support pipeline_config |

## What Stays the Same

- All 5 pipeline stages (interleave, blank removal, OCR, splitting, naming) — same logic
- SSE event bus infrastructure
- Database schema (no new tables — DLQ is in state.json)
- Existing API endpoints (backward compatible — new fields are additive)
- MCP tools (enhancement is a separate subsystem)
- UI (enhancement is a separate subsystem)

## Backward Compatibility

- `run_pipeline()` still works with the old signature (pipeline_config defaults to auto-advance, no DLQ)
- Existing `state.json` format (just `{"stage": "..."}`) is auto-migrated to the new format on load
- Existing API consumers see new fields in responses but don't need to use them
- `POST /api/batches/{batch_id}/reprocess` still works (creates fresh state)
