# Stage-Aware Pipeline Control — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the pipeline runner to support stage-level pause/resume, document-level error isolation, a dead letter queue (DLQ) for deferred problem handling, and full observability at every step.

**Architecture:** Replace the current linear `run_pipeline()` with a `PipelineState` class that manages stage transitions and a stage dispatcher that can pause/resume at any checkpoint. The API gets new pipeline control endpoints. Existing behavior (auto-advance, happy path) is the default — no breaking changes.

**Tech Stack:** Python 3.13+ dataclasses, Pydantic models, FastAPI, pikepdf, aiosqlite

**Spec:** `docs/superpowers/specs/2026-03-30-pipeline-control-design.md`

---

## File Map

### New files

| File | Responsibility |
|------|---------------|
| `scanbox/pipeline/state.py` | `PipelineState` class, `StageState`, `DLQItem`, `PipelineConfig` — state management, serialization, stage transitions |
| `tests/unit/test_pipeline_state.py` | Tests for PipelineState class |
| `tests/unit/test_pipeline_control.py` | Tests for the refactored runner (pause, resume, DLQ) |
| `tests/integration/test_pipeline_api.py` | Tests for new pipeline control API endpoints |

### Modified files

| File | Change |
|------|--------|
| `scanbox/models.py` | Add `PAUSED` to `BatchState`, add `PipelineResult` model |
| `scanbox/config.py` | Add `PIPELINE_AUTO_ADVANCE_ON_ERROR`, `PIPELINE_CONFIDENCE_THRESHOLD` |
| `scanbox/pipeline/runner.py` | Refactor to use `PipelineState`, stage dispatcher, document-level error isolation |
| `scanbox/api/batches.py` | Add pipeline control endpoints (resume, retry, skip, advance, stage results, DLQ) |
| `scanbox/api/scanning.py` | Update `_run_processing` to handle `PipelineResult` status |
| `tests/unit/test_runner.py` | Update existing tests for new `run_pipeline` return type |

---

## Task 1: Add PipelineState class and supporting models

**Files:**
- Create: `scanbox/pipeline/state.py`
- Modify: `scanbox/models.py`
- Modify: `scanbox/config.py`
- Test: `tests/unit/test_pipeline_state.py`

This is the foundational data model that everything else builds on.

- [ ] **Step 1: Write tests for PipelineState**

Create `tests/unit/test_pipeline_state.py`:

```python
"""Tests for PipelineState management."""

import json
from pathlib import Path

import pytest

from scanbox.models import ProcessingStage
from scanbox.pipeline.state import DLQItem, PipelineConfig, PipelineState, StageStatus


class TestPipelineConfig:
    def test_defaults(self):
        cfg = PipelineConfig()
        assert cfg.auto_advance_on_error is False
        assert cfg.confidence_threshold == 0.7

    def test_custom(self):
        cfg = PipelineConfig(auto_advance_on_error=True, confidence_threshold=0.5)
        assert cfg.auto_advance_on_error is True
        assert cfg.confidence_threshold == 0.5


class TestPipelineStateCreation:
    def test_fresh_state(self):
        state = PipelineState.new()
        assert state.current_stage == ProcessingStage.INTERLEAVING
        assert state.status == "running"
        for stage in ProcessingStage:
            if stage == ProcessingStage.DONE:
                continue
            assert state.stages[stage.value].status == StageStatus.PENDING

    def test_pending_stages(self):
        state = PipelineState.new()
        pending = state.pending_stages()
        assert len(pending) == 5
        assert pending[0] == ProcessingStage.INTERLEAVING


class TestPipelineStateTransitions:
    def test_mark_running(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        assert state.stages["interleaving"].status == StageStatus.RUNNING

    def test_mark_completed(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.INTERLEAVING, {"total_pages": 13})
        assert state.stages["interleaving"].status == StageStatus.COMPLETED
        assert state.stages["interleaving"].result == {"total_pages": 13}
        assert state.stages["interleaving"].completed_at is not None

    def test_mark_paused(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.SPLITTING)
        state.mark_paused(ProcessingStage.SPLITTING, "2 low confidence documents")
        assert state.stages["splitting"].status == StageStatus.PAUSED
        assert state.status == "paused"

    def test_mark_error(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.OCR)
        state.mark_error(ProcessingStage.OCR, "tesseract not found")
        assert state.stages["ocr"].status == StageStatus.ERROR
        assert state.stages["ocr"].error == "tesseract not found"

    def test_mark_skipped(self):
        state = PipelineState.new()
        state.mark_skipped(ProcessingStage.INTERLEAVING)
        assert state.stages["interleaving"].status == StageStatus.SKIPPED

    def test_resume_from(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.SPLITTING)
        state.mark_paused(ProcessingStage.SPLITTING, "issue")
        state.resume_from(ProcessingStage.SPLITTING)
        assert state.stages["splitting"].status == StageStatus.PENDING
        assert state.status == "running"


class TestDLQ:
    def test_add_to_dlq(self):
        state = PipelineState.new()
        item = DLQItem(
            stage="splitting",
            document={"start_page": 7, "end_page": 8, "confidence": 0.4},
            reason="Low confidence",
        )
        state.add_to_dlq(item)
        assert len(state.dlq) == 1
        assert state.dlq[0].stage == "splitting"
        assert state.dlq[0].id.startswith("dlq-")

    def test_remove_from_dlq(self):
        state = PipelineState.new()
        item = DLQItem(stage="splitting", document={}, reason="test")
        state.add_to_dlq(item)
        item_id = state.dlq[0].id
        state.remove_from_dlq(item_id)
        assert len(state.dlq) == 0

    def test_remove_nonexistent_raises(self):
        state = PipelineState.new()
        with pytest.raises(ValueError, match="not found"):
            state.remove_from_dlq("dlq-nonexistent")


class TestPipelineStatePersistence:
    def test_save_and_load(self, tmp_path):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.INTERLEAVING, {"total_pages": 5})
        state.config.confidence_threshold = 0.5
        state.save(tmp_path / "state.json")

        loaded = PipelineState.load(tmp_path / "state.json")
        assert loaded.stages["interleaving"].status == StageStatus.COMPLETED
        assert loaded.stages["interleaving"].result == {"total_pages": 5}
        assert loaded.config.confidence_threshold == 0.5

    def test_load_missing_creates_fresh(self, tmp_path):
        loaded = PipelineState.load(tmp_path / "nonexistent.json")
        assert loaded.current_stage == ProcessingStage.INTERLEAVING

    def test_load_legacy_format(self, tmp_path):
        """Old state.json with just {"stage": "ocr"} should auto-migrate."""
        legacy = {"stage": "ocr"}
        (tmp_path / "state.json").write_text(json.dumps(legacy))
        loaded = PipelineState.load(tmp_path / "state.json")
        # Stages before OCR should be completed
        assert loaded.stages["interleaving"].status == StageStatus.COMPLETED
        assert loaded.stages["blank_removal"].status == StageStatus.COMPLETED
        assert loaded.stages["ocr"].status == StageStatus.PENDING
        assert loaded.stages["splitting"].status == StageStatus.PENDING


class TestOverallStatus:
    def test_running(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        assert state.status == "running"

    def test_paused(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.SPLITTING)
        state.mark_paused(ProcessingStage.SPLITTING, "issue")
        assert state.status == "paused"

    def test_completed(self):
        state = PipelineState.new()
        for stage in [ProcessingStage.INTERLEAVING, ProcessingStage.BLANK_REMOVAL,
                      ProcessingStage.OCR, ProcessingStage.SPLITTING, ProcessingStage.NAMING]:
            state.mark_running(stage)
            state.mark_completed(stage, {})
        assert state.status == "completed"

    def test_error(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.OCR)
        state.mark_error(ProcessingStage.OCR, "crash")
        assert state.status == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_pipeline_state.py -v 2>&1 | tail -5`
Expected: FAIL — ImportError

- [ ] **Step 3: Add PAUSED to BatchState and PipelineResult to models.py**

In `scanbox/models.py`, add `PAUSED = "paused"` to `BatchState` enum (after `PROCESSING`). Add `PipelineResult`:

```python
class PipelineResult(BaseModel):
    """Result from a pipeline run — may be completed, paused, or errored."""
    status: str  # "completed", "paused", "error"
    documents: list[SplitDocument] = Field(default_factory=list)
    paused_stage: str | None = None
    paused_reason: str | None = None
    error_stage: str | None = None
    error_message: str | None = None
```

- [ ] **Step 4: Add config settings**

In `scanbox/config.py`, add to `Config.__init__`:

```python
# Pipeline control
self.PIPELINE_AUTO_ADVANCE_ON_ERROR: bool = (
    os.getenv("PIPELINE_AUTO_ADVANCE_ON_ERROR", "").lower() in ("true", "1", "yes")
)
self.PIPELINE_CONFIDENCE_THRESHOLD: float = float(
    os.getenv("PIPELINE_CONFIDENCE_THRESHOLD", "0.7")
)
```

- [ ] **Step 5: Implement PipelineState class**

Create `scanbox/pipeline/state.py`:

```python
"""Pipeline state management — stage transitions, DLQ, persistence."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from scanbox.models import ProcessingStage


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PAUSED = "paused"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class StageState:
    status: StageStatus = StageStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    pause_reason: str | None = None
    result: dict | None = None


@dataclass
class DLQItem:
    stage: str
    document: dict
    reason: str
    id: str = ""
    added_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"dlq-{uuid.uuid4().hex[:8]}"
        if not self.added_at:
            self.added_at = datetime.now(UTC).isoformat()


@dataclass
class PipelineConfig:
    auto_advance_on_error: bool = False
    confidence_threshold: float = 0.7


# Ordered list of processing stages (excludes DONE)
STAGE_ORDER = [
    ProcessingStage.INTERLEAVING,
    ProcessingStage.BLANK_REMOVAL,
    ProcessingStage.OCR,
    ProcessingStage.SPLITTING,
    ProcessingStage.NAMING,
]


@dataclass
class PipelineState:
    stages: dict[str, StageState] = field(default_factory=dict)
    dlq: list[DLQItem] = field(default_factory=list)
    config: PipelineConfig = field(default_factory=PipelineConfig)

    @classmethod
    def new(cls, config: PipelineConfig | None = None) -> PipelineState:
        stages = {stage.value: StageState() for stage in STAGE_ORDER}
        return cls(stages=stages, config=config or PipelineConfig())

    @property
    def current_stage(self) -> ProcessingStage | None:
        for stage in STAGE_ORDER:
            ss = self.stages.get(stage.value)
            if ss and ss.status in (StageStatus.PENDING, StageStatus.RUNNING,
                                     StageStatus.PAUSED, StageStatus.ERROR):
                return stage
        return None

    @property
    def status(self) -> str:
        for stage in STAGE_ORDER:
            ss = self.stages[stage.value]
            if ss.status == StageStatus.RUNNING:
                return "running"
            if ss.status == StageStatus.PAUSED:
                return "paused"
            if ss.status == StageStatus.ERROR:
                return "error"
        # All completed or skipped
        all_done = all(
            self.stages[s.value].status in (StageStatus.COMPLETED, StageStatus.SKIPPED)
            for s in STAGE_ORDER
        )
        return "completed" if all_done else "running"

    def pending_stages(self) -> list[ProcessingStage]:
        return [
            s for s in STAGE_ORDER
            if self.stages[s.value].status == StageStatus.PENDING
        ]

    def mark_running(self, stage: ProcessingStage) -> None:
        self.stages[stage.value].status = StageStatus.RUNNING
        self.stages[stage.value].started_at = datetime.now(UTC).isoformat()

    def mark_completed(self, stage: ProcessingStage, result: dict) -> None:
        ss = self.stages[stage.value]
        ss.status = StageStatus.COMPLETED
        ss.completed_at = datetime.now(UTC).isoformat()
        ss.result = result

    def mark_paused(self, stage: ProcessingStage, reason: str) -> None:
        ss = self.stages[stage.value]
        ss.status = StageStatus.PAUSED
        ss.pause_reason = reason

    def mark_error(self, stage: ProcessingStage, error: str) -> None:
        ss = self.stages[stage.value]
        ss.status = StageStatus.ERROR
        ss.error = error

    def mark_skipped(self, stage: ProcessingStage) -> None:
        self.stages[stage.value].status = StageStatus.SKIPPED

    def resume_from(self, stage: ProcessingStage) -> None:
        ss = self.stages[stage.value]
        ss.status = StageStatus.PENDING
        ss.pause_reason = None
        ss.error = None

    def add_to_dlq(self, item: DLQItem) -> None:
        self.dlq.append(item)

    def remove_from_dlq(self, item_id: str) -> DLQItem:
        for i, item in enumerate(self.dlq):
            if item.id == item_id:
                return self.dlq.pop(i)
        raise ValueError(f"DLQ item {item_id} not found")

    def save(self, path: Path) -> None:
        data = {
            "stages": {
                name: {
                    "status": ss.status.value,
                    "started_at": ss.started_at,
                    "completed_at": ss.completed_at,
                    "error": ss.error,
                    "pause_reason": ss.pause_reason,
                    "result": ss.result,
                }
                for name, ss in self.stages.items()
            },
            "dlq": [
                {
                    "id": item.id,
                    "stage": item.stage,
                    "document": item.document,
                    "reason": item.reason,
                    "added_at": item.added_at,
                }
                for item in self.dlq
            ],
            "config": {
                "auto_advance_on_error": self.config.auto_advance_on_error,
                "confidence_threshold": self.config.confidence_threshold,
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> PipelineState:
        if not path.exists():
            return cls.new()

        raw = json.loads(path.read_text())

        # Legacy format migration: {"stage": "ocr"}
        if "stage" in raw and "stages" not in raw:
            return cls._migrate_legacy(raw)

        state = cls.new()

        # Load config
        if "config" in raw:
            state.config = PipelineConfig(**raw["config"])

        # Load stages
        for name, stage_data in raw.get("stages", {}).items():
            if name in state.stages:
                ss = state.stages[name]
                ss.status = StageStatus(stage_data["status"])
                ss.started_at = stage_data.get("started_at")
                ss.completed_at = stage_data.get("completed_at")
                ss.error = stage_data.get("error")
                ss.pause_reason = stage_data.get("pause_reason")
                ss.result = stage_data.get("result")

        # Load DLQ
        for item_data in raw.get("dlq", []):
            state.dlq.append(DLQItem(
                id=item_data["id"],
                stage=item_data["stage"],
                document=item_data["document"],
                reason=item_data["reason"],
                added_at=item_data.get("added_at", ""),
            ))

        return state

    @classmethod
    def _migrate_legacy(cls, raw: dict) -> PipelineState:
        """Migrate old {"stage": "ocr"} format to new format."""
        state = cls.new()
        target_stage = raw["stage"]

        # Mark all stages before target as completed
        for stage in STAGE_ORDER:
            if stage.value == target_stage:
                break
            state.stages[stage.value].status = StageStatus.COMPLETED

        return state
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_pipeline_state.py -v`
Expected: All tests PASS

- [ ] **Step 7: Format and lint**

Run: `ruff format scanbox/pipeline/state.py scanbox/models.py scanbox/config.py tests/unit/test_pipeline_state.py && ruff check scanbox/pipeline/state.py scanbox/models.py scanbox/config.py tests/unit/test_pipeline_state.py`

- [ ] **Step 8: Commit**

```bash
git add scanbox/pipeline/state.py scanbox/models.py scanbox/config.py tests/unit/test_pipeline_state.py
git commit -m "feat: add PipelineState class with stage transitions, DLQ, and legacy migration"
```

---

## Task 2: Refactor pipeline runner to use PipelineState

**Files:**
- Modify: `scanbox/pipeline/runner.py`
- Modify: `tests/unit/test_runner.py`
- Test: `tests/unit/test_pipeline_control.py`

This is the core refactoring — replace the linear runner with the stage-aware one. The key constraint: **existing tests must keep passing** (with minimal signature adjustments for the new return type).

- [ ] **Step 1: Write tests for new pipeline behavior**

Create `tests/unit/test_pipeline_control.py`:

```python
"""Tests for stage-aware pipeline control (pause, resume, DLQ)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pikepdf

from scanbox.models import ProcessingStage, PipelineResult, SplitDocument
from scanbox.pipeline.runner import PipelineContext, run_pipeline
from scanbox.pipeline.state import PipelineConfig, PipelineState


def _make_pdf(path: Path, num_pages: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.add_blank_page(page_size=(612, 792))
    pdf.save(path)


def _make_ctx(tmp_path: Path) -> PipelineContext:
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir(parents=True, exist_ok=True)
    return PipelineContext(
        batch_dir=batch_dir,
        output_dir=tmp_path / "output",
        person_name="Jane Doe",
        person_slug="jane-doe",
        person_folder="Jane_Doe",
        batch_num=1,
        scan_date="2026-03-30",
        has_backs=False,
    )


class TestPipelineReturnsResult:
    @patch("scanbox.pipeline.runner.split_documents")
    @patch("scanbox.pipeline.runner.run_ocr")
    @patch("scanbox.pipeline.runner.remove_blank_pages")
    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_returns_pipeline_result(
        self, mock_interleave, mock_blank, mock_ocr, mock_split, tmp_path
    ):
        ctx = _make_ctx(tmp_path)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 2)

        mock_interleave.side_effect = lambda f, b, o: _make_pdf(o, 2)
        mock_result = MagicMock()
        mock_result.removed_indices = []
        mock_result.total_pages = 2
        mock_blank.side_effect = lambda i, o, t: (mock_result, _make_pdf(o, 2))[0]
        mock_ocr.side_effect = lambda i, o, t: (
            _make_pdf(o, 2),
            t.write_text(json.dumps({"1": "A", "2": "B"})),
        )
        mock_split.return_value = [
            SplitDocument(start_page=1, end_page=2, document_type="Lab Results", confidence=0.95)
        ]

        result = await run_pipeline(ctx)
        assert isinstance(result, PipelineResult)
        assert result.status == "completed"
        assert len(result.documents) == 1


class TestLowConfidencePause:
    @patch("scanbox.pipeline.runner.split_documents")
    @patch("scanbox.pipeline.runner.run_ocr")
    @patch("scanbox.pipeline.runner.remove_blank_pages")
    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_pauses_on_low_confidence(
        self, mock_interleave, mock_blank, mock_ocr, mock_split, tmp_path
    ):
        ctx = _make_ctx(tmp_path)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 3)

        mock_interleave.side_effect = lambda f, b, o: _make_pdf(o, 3)
        mock_result = MagicMock()
        mock_result.removed_indices = []
        mock_result.total_pages = 3
        mock_blank.side_effect = lambda i, o, t: (mock_result, _make_pdf(o, 3))[0]
        mock_ocr.side_effect = lambda i, o, t: (
            _make_pdf(o, 3),
            t.write_text(json.dumps({"1": "A", "2": "B", "3": "C"})),
        )
        mock_split.return_value = [
            SplitDocument(start_page=1, end_page=2, confidence=0.95),
            SplitDocument(start_page=3, end_page=3, confidence=0.3),  # Below threshold
        ]

        config = PipelineConfig(confidence_threshold=0.7)
        result = await run_pipeline(ctx, pipeline_config=config)
        assert result.status == "paused"
        assert result.paused_stage == "splitting"


class TestDLQMode:
    @patch("scanbox.pipeline.runner.split_documents")
    @patch("scanbox.pipeline.runner.run_ocr")
    @patch("scanbox.pipeline.runner.remove_blank_pages")
    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_dlq_mode_continues_past_low_confidence(
        self, mock_interleave, mock_blank, mock_ocr, mock_split, tmp_path
    ):
        ctx = _make_ctx(tmp_path)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 3)

        mock_interleave.side_effect = lambda f, b, o: _make_pdf(o, 3)
        mock_result = MagicMock()
        mock_result.removed_indices = []
        mock_result.total_pages = 3
        mock_blank.side_effect = lambda i, o, t: (mock_result, _make_pdf(o, 3))[0]
        mock_ocr.side_effect = lambda i, o, t: (
            _make_pdf(o, 3),
            t.write_text(json.dumps({"1": "A", "2": "B", "3": "C"})),
        )
        mock_split.return_value = [
            SplitDocument(start_page=1, end_page=2, confidence=0.95),
            SplitDocument(start_page=3, end_page=3, confidence=0.3),
        ]

        config = PipelineConfig(auto_advance_on_error=True, confidence_threshold=0.7)
        result = await run_pipeline(ctx, pipeline_config=config)
        assert result.status == "completed"
        # Low confidence doc should still be in documents (not removed)
        assert len(result.documents) == 2

        # DLQ should have the low-confidence item
        state = PipelineState.load(ctx.batch_dir / "state.json")
        assert len(state.dlq) == 1
        assert state.dlq[0].stage == "splitting"


class TestStageError:
    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_stage_error_pauses_pipeline(self, mock_interleave, tmp_path):
        ctx = _make_ctx(tmp_path)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 2)

        mock_interleave.side_effect = RuntimeError("Interleave failed")

        result = await run_pipeline(ctx)
        assert result.status == "error"
        assert result.error_stage == "interleaving"
        assert "Interleave failed" in result.error_message

    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_stage_error_dlq_mode_skips(self, mock_interleave, tmp_path):
        ctx = _make_ctx(tmp_path)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 2)

        mock_interleave.side_effect = RuntimeError("Interleave failed")

        config = PipelineConfig(auto_advance_on_error=True)
        result = await run_pipeline(ctx, pipeline_config=config)
        # Stage error in DLQ mode should still error (can't skip interleave)
        assert result.status == "error"


class TestStateJsonUpdated:
    @patch("scanbox.pipeline.runner.split_documents")
    @patch("scanbox.pipeline.runner.run_ocr")
    @patch("scanbox.pipeline.runner.remove_blank_pages")
    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_state_json_has_stage_results(
        self, mock_interleave, mock_blank, mock_ocr, mock_split, tmp_path
    ):
        ctx = _make_ctx(tmp_path)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 2)

        mock_interleave.side_effect = lambda f, b, o: _make_pdf(o, 2)
        mock_result = MagicMock()
        mock_result.removed_indices = []
        mock_result.total_pages = 2
        mock_blank.side_effect = lambda i, o, t: (mock_result, _make_pdf(o, 2))[0]
        mock_ocr.side_effect = lambda i, o, t: (
            _make_pdf(o, 2),
            t.write_text(json.dumps({"1": "A", "2": "B"})),
        )
        mock_split.return_value = [
            SplitDocument(start_page=1, end_page=2, confidence=0.9)
        ]

        await run_pipeline(ctx)

        state = PipelineState.load(ctx.batch_dir / "state.json")
        assert state.stages["interleaving"].status.value == "completed"
        assert state.stages["interleaving"].result is not None
        assert state.stages["blank_removal"].status.value == "completed"
        assert state.stages["ocr"].status.value == "completed"
        assert state.stages["splitting"].status.value == "completed"
        assert state.stages["naming"].status.value == "completed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_pipeline_control.py -v 2>&1 | tail -5`
Expected: FAIL

- [ ] **Step 3: Refactor runner.py**

Rewrite `scanbox/pipeline/runner.py` to use `PipelineState`. Key changes:

1. `run_pipeline` now returns `PipelineResult` instead of `list[SplitDocument]`
2. Add optional `pipeline_config: PipelineConfig | None` parameter
3. Load/save state using `PipelineState` class
4. Each stage is wrapped in try/except for error isolation
5. After splitting, check document confidence against threshold
6. State is saved after every stage transition

The function signature becomes:
```python
async def run_pipeline(
    ctx: PipelineContext,
    on_progress: callable = None,
    pipeline_config: PipelineConfig | None = None,
) -> PipelineResult:
```

The stage execution loop:
```python
state = PipelineState.load(_state_path(ctx))
if pipeline_config:
    state.config = pipeline_config

for stage in state.pending_stages():
    state.mark_running(stage)
    state.save(_state_path(ctx))
    try:
        result = await _run_stage(stage, ctx, state, on_progress)
        state.mark_completed(stage, result)
        state.save(_state_path(ctx))
        # ... check for issues after splitting ...
    except Exception as e:
        state.mark_error(stage, str(e))
        state.save(_state_path(ctx))
        return PipelineResult(status="error", error_stage=stage.value, error_message=str(e))
```

Extract each stage's logic into `_run_stage(stage, ctx, state, on_progress)` which dispatches to the existing stage functions and returns a result dict.

After splitting stage: check confidence threshold, flag low-confidence documents in state, either pause or add to DLQ based on config.

After all stages complete, read final documents from splits.json and return `PipelineResult(status="completed", documents=docs)`.

**Backward compatibility:** The old `_read_state` and `_write_state` functions should be removed. `PipelineContext` dataclass stays the same. The `on_progress` callback signature stays the same.

- [ ] **Step 4: Update existing tests in test_runner.py**

The existing tests in `tests/unit/test_runner.py` need updates:

1. `TestPipelineState` class: update to test new `PipelineState.load` and `.save` instead of old `_read_state`/`_write_state`
2. `TestRunPipeline` class: update assertions — `run_pipeline` now returns `PipelineResult` not `list[SplitDocument]`. Access documents via `result.documents`.
3. Import `PipelineResult` from `scanbox.models`

Key changes per test:
- `docs = await run_pipeline(ctx, on_progress=on_progress)` → `result = await run_pipeline(ctx, on_progress=on_progress)` then `docs = result.documents`
- `assert len(docs) == 2` → `assert len(result.documents) == 2`
- State assertions: verify `PipelineState.load` works instead of raw JSON

- [ ] **Step 5: Run all pipeline tests**

Run: `pytest tests/unit/test_runner.py tests/unit/test_pipeline_control.py tests/unit/test_pipeline_state.py -v`
Expected: All tests PASS

- [ ] **Step 6: Format and lint**

Run: `ruff format scanbox/pipeline/runner.py tests/unit/test_runner.py tests/unit/test_pipeline_control.py && ruff check scanbox/pipeline/runner.py tests/unit/test_runner.py tests/unit/test_pipeline_control.py`

- [ ] **Step 7: Commit**

```bash
git add scanbox/pipeline/runner.py tests/unit/test_runner.py tests/unit/test_pipeline_control.py
git commit -m "feat: refactor pipeline runner to stage-aware execution with pause/resume and DLQ"
```

---

## Task 3: Update scanning.py to handle PipelineResult

**Files:**
- Modify: `scanbox/api/scanning.py`
- Modify: `tests/unit/test_scanning.py` (if affected)

The `_run_processing` function in scanning.py calls `run_pipeline` and expects `list[SplitDocument]`. It now returns `PipelineResult`. Update the handler to set batch state based on the result status.

- [ ] **Step 1: Update _run_processing in scanning.py**

Read `scanbox/api/scanning.py` lines 142-222 (the `_run_processing` function). Key changes:

1. `documents: list[SplitDocument] = await run_pipeline(ctx, on_progress=on_progress)` → `result: PipelineResult = await run_pipeline(ctx, on_progress=on_progress)`
2. After the call, check `result.status`:
   - `"completed"` → create documents in DB, set state to `review` (existing behavior)
   - `"paused"` → set batch state to `paused`, publish SSE event `{"type": "pipeline_paused", "stage": result.paused_stage, "reason": result.paused_reason}`
   - `"error"` → set batch state to `error` with error message (existing behavior)
3. Access documents via `result.documents` instead of `documents`

Also import `PipelineResult` and `PipelineConfig` from models/state.

- [ ] **Step 2: Run existing scanning tests**

Run: `pytest tests/unit/test_scanning.py -v`
Expected: Tests pass (may need minor updates for new return type)

- [ ] **Step 3: Format and lint**

Run: `ruff format scanbox/api/scanning.py && ruff check scanbox/api/scanning.py`

- [ ] **Step 4: Commit**

```bash
git add scanbox/api/scanning.py tests/unit/test_scanning.py
git commit -m "feat: update _run_processing to handle PipelineResult (paused, completed, error)"
```

---

## Task 4: Add pipeline control API endpoints

**Files:**
- Modify: `scanbox/api/batches.py`
- Test: `tests/integration/test_pipeline_api.py`

Add endpoints for pipeline inspection, resume, retry, skip, and DLQ management.

- [ ] **Step 1: Write tests for pipeline API endpoints**

Create `tests/integration/test_pipeline_api.py`:

```python
"""Tests for pipeline control API endpoints."""

import json
from io import BytesIO
from pathlib import Path

import pikepdf
import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app
from scanbox.pipeline.state import DLQItem, PipelineConfig, PipelineState, StageStatus


def _make_pdf_bytes(num_pages: int = 3) -> bytes:
    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.add_blank_page(page_size=(612, 792))
    buf = BytesIO()
    pdf.save(buf)
    return buf.getvalue()


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "output").mkdir()
    from scanbox.main import lifespan
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def _import_batch(client, num_pages=3):
    """Helper: import a batch and return batch_id."""
    fronts = _make_pdf_bytes(num_pages)
    resp = await client.post(
        "/api/batches/import",
        files={"fronts": ("fronts.pdf", fronts, "application/pdf")},
    )
    return resp.json()["batch_id"]


class TestGetPipelineState:
    async def test_returns_pipeline_state(self, client):
        batch_id = await _import_batch(client)
        resp = await client.get(f"/api/batches/{batch_id}/pipeline")
        assert resp.status_code == 200
        data = resp.json()
        assert "stages" in data
        assert "dlq" in data
        assert "config" in data
        assert "status" in data


class TestDLQEndpoints:
    async def test_list_dlq_empty(self, client):
        batch_id = await _import_batch(client)
        resp = await client.get(f"/api/batches/{batch_id}/dlq")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_discard_dlq_item(self, client, tmp_path, monkeypatch):
        batch_id = await _import_batch(client)
        # Manually add a DLQ item to state.json
        from scanbox.config import Config
        from scanbox.main import get_db
        cfg = Config()
        db = get_db()
        batch = await db.get_batch(batch_id)
        session = await db.get_session(batch["session_id"])
        batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch_id
        state = PipelineState.load(batch_dir / "state.json")
        state.add_to_dlq(DLQItem(stage="splitting", document={"start_page": 1}, reason="test"))
        state.save(batch_dir / "state.json")

        # List DLQ
        resp = await client.get(f"/api/batches/{batch_id}/dlq")
        items = resp.json()["items"]
        assert len(items) == 1
        item_id = items[0]["id"]

        # Discard
        resp = await client.delete(f"/api/batches/{batch_id}/dlq/{item_id}")
        assert resp.status_code == 200

        # Verify removed
        resp = await client.get(f"/api/batches/{batch_id}/dlq")
        assert len(resp.json()["items"]) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_pipeline_api.py -v 2>&1 | tail -5`
Expected: FAIL — 404 endpoints don't exist

- [ ] **Step 3: Add pipeline control endpoints to batches.py**

Add these endpoints to `scanbox/api/batches.py`:

```python
@router.get("/api/batches/{batch_id}/pipeline")
async def get_pipeline_state(batch_id: str):
    """Get full pipeline state including all stage results and DLQ."""

@router.post("/api/batches/{batch_id}/pipeline/resume")
async def resume_pipeline(batch_id: str):
    """Resume a paused pipeline from the paused stage."""

@router.post("/api/batches/{batch_id}/pipeline/retry")
async def retry_pipeline_stage(batch_id: str):
    """Retry the current failed/paused stage."""

@router.post("/api/batches/{batch_id}/pipeline/skip")
async def skip_pipeline_stage(batch_id: str):
    """Skip the current stage and advance to the next."""

@router.post("/api/batches/{batch_id}/pipeline/advance")
async def advance_pipeline(batch_id: str):
    """Accept current results and advance from a paused stage."""

@router.get("/api/batches/{batch_id}/pipeline/stage/{stage}")
async def get_stage_result(batch_id: str, stage: str):
    """Get results for a specific pipeline stage."""

@router.get("/api/batches/{batch_id}/dlq")
async def list_dlq(batch_id: str):
    """List dead letter queue items for a batch."""

@router.post("/api/batches/{batch_id}/dlq/{item_id}/retry")
async def retry_dlq_item(batch_id: str, item_id: str):
    """Retry a DLQ item by pushing it back into the pipeline."""

@router.post("/api/batches/{batch_id}/dlq/{item_id}/resolve")
async def resolve_dlq_item(batch_id: str, item_id: str):
    """Manually resolve a DLQ item with provided metadata."""

@router.delete("/api/batches/{batch_id}/dlq/{item_id}")
async def discard_dlq_item(batch_id: str, item_id: str):
    """Discard a DLQ item (user decided these pages aren't needed)."""
```

Each endpoint loads `PipelineState` from the batch's `state.json`, performs the action, saves state, and returns the updated state. The resume/retry/advance endpoints also trigger `_run_processing` as a background task.

Implementation pattern for each:
1. Look up batch, verify state allows the operation
2. Load `PipelineState` from `batch_dir / "state.json"`
3. Perform the state transition
4. Save updated state
5. For resume/retry/advance: `asyncio.create_task(_run_processing(...))`
6. Return updated state as JSON

- [ ] **Step 4: Run tests**

Run: `pytest tests/integration/test_pipeline_api.py -v`
Expected: All tests PASS

- [ ] **Step 5: Format and lint**

Run: `ruff format scanbox/api/batches.py tests/integration/test_pipeline_api.py && ruff check scanbox/api/batches.py tests/integration/test_pipeline_api.py`

- [ ] **Step 6: Commit**

```bash
git add scanbox/api/batches.py tests/integration/test_pipeline_api.py
git commit -m "feat: add pipeline control API endpoints (resume, retry, skip, DLQ)"
```

---

## Task 5: Update batch GET endpoint and SSE events

**Files:**
- Modify: `scanbox/api/batches.py`
- Modify: `scanbox/api/scanning.py`

- [ ] **Step 1: Enhance GET /api/batches/{batch_id} response**

Add `pipeline_status` and `current_stage` fields to the batch GET response. Load `PipelineState` from state.json and include a summary:

```python
@router.get("/api/batches/{batch_id}")
async def get_batch(batch_id: str):
    # ... existing code ...
    batch["document_count"] = len(docs)

    # Add pipeline status if processing/paused
    if batch["state"] in ("processing", "paused", "review", "error"):
        batch_dir = _get_batch_dir(batch_id)
        state = PipelineState.load(batch_dir / "state.json")
        batch["pipeline_status"] = state.status
        batch["current_stage"] = state.current_stage.value if state.current_stage else None
        batch["dlq_count"] = len(state.dlq)

    return batch
```

- [ ] **Step 2: Add SSE events for stage results and DLQ**

In `_run_processing` (scanning.py), emit new SSE event types when stages complete:

```python
# After each stage completes in the pipeline runner, emit:
await event_bus.publish(batch_id, {
    "type": "stage_result",
    "stage": stage_name,
    "result": stage_result_summary,
})

# When pipeline pauses:
await event_bus.publish(batch_id, {
    "type": "pipeline_paused",
    "stage": paused_stage,
    "reason": pause_reason,
})

# When DLQ item added:
await event_bus.publish(batch_id, {
    "type": "dlq_item_added",
    "item_id": item_id,
    "stage": stage,
    "reason": reason,
})
```

These events are emitted from the `on_progress` callback in `_run_processing`, which already has access to the event bus.

- [ ] **Step 3: Run full test suite**

Run: `pytest -v 2>&1 | tail -20`
Expected: All tests pass

- [ ] **Step 4: Format, lint, commit**

```bash
ruff format scanbox/api/batches.py scanbox/api/scanning.py
ruff check scanbox/api/batches.py scanbox/api/scanning.py
git add scanbox/api/batches.py scanbox/api/scanning.py
git commit -m "feat: enhance batch endpoint with pipeline status and add SSE stage events"
```

---

## Task 6: Final verification and full test suite

- [ ] **Step 1: Format all modified files**

Run: `ruff format scanbox/ tests/ && ruff check scanbox/ tests/`

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`
Expected: All existing tests pass + all new tests pass

- [ ] **Step 3: Verify backward compatibility**

Test that old-style usage still works:

```python
# Old: run_pipeline returns list[SplitDocument]
# New: run_pipeline returns PipelineResult
# Callers that did `docs = await run_pipeline(ctx)` need `result.documents`
```

Verify no callers outside of scanning.py use `run_pipeline` directly. If any exist in MCP server or tests, update them.

Run: `grep -r "run_pipeline" scanbox/ tests/ --include="*.py" | grep -v __pycache__`

- [ ] **Step 4: Commit if any fixes needed**

```bash
git add -A
git commit -m "chore: final formatting and backward compatibility fixes"
```
