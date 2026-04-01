"""Stage-aware pipeline state with transitions, DLQ, and persistence."""

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

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "pause_reason": self.pause_reason,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: dict) -> StageState:
        return cls(
            status=StageStatus(data["status"]),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
            pause_reason=data.get("pause_reason"),
            result=data.get("result"),
        )


@dataclass
class DLQItem:
    stage: str
    document: dict
    reason: str
    id: str = ""
    added_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "stage": self.stage,
            "document": self.document,
            "reason": self.reason,
            "added_at": self.added_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DLQItem:
        return cls(
            id=data["id"],
            stage=data["stage"],
            document=data["document"],
            reason=data["reason"],
            added_at=data["added_at"],
        )


@dataclass
class PipelineConfig:
    auto_advance_on_error: bool = False
    confidence_threshold: float = 0.7

    def to_dict(self) -> dict:
        return {
            "auto_advance_on_error": self.auto_advance_on_error,
            "confidence_threshold": self.confidence_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PipelineConfig:
        return cls(
            auto_advance_on_error=data.get("auto_advance_on_error", False),
            confidence_threshold=data.get("confidence_threshold", 0.7),
        )


STAGE_ORDER: list[ProcessingStage] = [
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
    excluded_pages: list[int] = field(default_factory=list)
    excluded_documents: list[int] = field(default_factory=list)

    @classmethod
    def new(cls, config: PipelineConfig | None = None) -> PipelineState:
        stages = {stage.value: StageState() for stage in STAGE_ORDER}
        return cls(
            stages=stages,
            dlq=[],
            config=config or PipelineConfig(),
        )

    @classmethod
    def load(cls, path: Path) -> PipelineState:
        if not path.exists():
            return cls.new()
        raw = json.loads(path.read_text())
        # Detect legacy format: {"stage": "ocr", ...} without "stages" key
        if "stage" in raw and "stages" not in raw:
            return cls._migrate_legacy(raw)
        stages = {k: StageState.from_dict(v) for k, v in raw["stages"].items()}
        dlq = [DLQItem.from_dict(item) for item in raw.get("dlq", [])]
        cfg = PipelineConfig.from_dict(raw.get("config", {}))
        excluded_pages = raw.get("excluded_pages", [])
        excluded_documents = raw.get("excluded_documents", [])
        return cls(
            stages=stages,
            dlq=dlq,
            config=cfg,
            excluded_pages=excluded_pages,
            excluded_documents=excluded_documents,
        )

    @classmethod
    def _migrate_legacy(cls, raw: dict) -> PipelineState:
        legacy_stage = raw["stage"]
        state = cls.new()
        # Mark all stages before the legacy stage as COMPLETED
        found = False
        for stage in STAGE_ORDER:
            if stage.value == legacy_stage:
                found = True
                break
            state.stages[stage.value].status = StageStatus.COMPLETED
        # If legacy_stage is "done", mark everything as completed
        if not found and legacy_stage == "done":
            for stage in STAGE_ORDER:
                state.stages[stage.value].status = StageStatus.COMPLETED
        return state

    @property
    def current_stage(self) -> str | None:
        active = {StageStatus.PENDING, StageStatus.RUNNING, StageStatus.PAUSED, StageStatus.ERROR}
        for stage in STAGE_ORDER:
            if self.stages[stage.value].status in active:
                return stage.value
        return None

    @property
    def status(self) -> str:
        for stage in STAGE_ORDER:
            ss = self.stages[stage.value]
            if ss.status == StageStatus.RUNNING:
                return "running"
        for stage in STAGE_ORDER:
            ss = self.stages[stage.value]
            if ss.status == StageStatus.PAUSED:
                return "paused"
        for stage in STAGE_ORDER:
            ss = self.stages[stage.value]
            if ss.status == StageStatus.ERROR:
                return "error"
        terminal = {StageStatus.COMPLETED, StageStatus.SKIPPED}
        if all(self.stages[s.value].status in terminal for s in STAGE_ORDER):
            return "completed"
        # All PENDING or mix of PENDING/COMPLETED/SKIPPED with none running/paused/error
        return "running"

    def pending_stages(self) -> list[ProcessingStage]:
        return [s for s in STAGE_ORDER if self.stages[s.value].status == StageStatus.PENDING]

    def mark_running(self, stage: ProcessingStage) -> None:
        ss = self.stages[stage.value]
        ss.status = StageStatus.RUNNING
        ss.started_at = datetime.now(UTC).isoformat()

    def mark_completed(self, stage: ProcessingStage, result: dict | None = None) -> None:
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
        ss.error = None
        ss.pause_reason = None

    def add_to_dlq(self, item: DLQItem) -> None:
        item.id = f"dlq-{uuid.uuid4().hex[:8]}"
        item.added_at = datetime.now(UTC).isoformat()
        self.dlq.append(item)

    def remove_from_dlq(self, item_id: str) -> None:
        for i, item in enumerate(self.dlq):
            if item.id == item_id:
                self.dlq.pop(i)
                return
        msg = f"DLQ item {item_id!r} not found"
        raise ValueError(msg)

    def exclude_page(self, page_num: int) -> None:
        if page_num not in self.excluded_pages:
            self.excluded_pages.append(page_num)
            self.excluded_pages.sort()

    def include_page(self, page_num: int) -> None:
        if page_num in self.excluded_pages:
            self.excluded_pages.remove(page_num)

    def exclude_document(self, doc_index: int) -> None:
        if doc_index not in self.excluded_documents:
            self.excluded_documents.append(doc_index)
            self.excluded_documents.sort()

    def include_document(self, doc_index: int) -> None:
        if doc_index in self.excluded_documents:
            self.excluded_documents.remove(doc_index)

    def save(self, path: Path) -> None:
        data = {
            "stages": {k: v.to_dict() for k, v in self.stages.items()},
            "dlq": [item.to_dict() for item in self.dlq],
            "config": self.config.to_dict(),
            "excluded_pages": self.excluded_pages,
            "excluded_documents": self.excluded_documents,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
