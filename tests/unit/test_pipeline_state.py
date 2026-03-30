"""Tests for scanbox.pipeline.state — PipelineState with stage transitions, DLQ, persistence."""

import json

import pytest

from scanbox.models import ProcessingStage
from scanbox.pipeline.state import (
    STAGE_ORDER,
    DLQItem,
    PipelineConfig,
    PipelineState,
    StageStatus,
)


class TestPipelineConfig:
    """PipelineConfig defaults and custom values."""

    def test_defaults(self):
        cfg = PipelineConfig()
        assert cfg.auto_advance_on_error is False
        assert cfg.confidence_threshold == 0.7

    def test_custom_values(self):
        cfg = PipelineConfig(auto_advance_on_error=True, confidence_threshold=0.85)
        assert cfg.auto_advance_on_error is True
        assert cfg.confidence_threshold == 0.85


class TestStageOrder:
    """STAGE_ORDER should list the 5 executable stages without DONE."""

    def test_contains_five_stages(self):
        assert len(STAGE_ORDER) == 5

    def test_does_not_include_done(self):
        assert ProcessingStage.DONE not in STAGE_ORDER

    def test_order_matches_pipeline(self):
        expected = [
            ProcessingStage.INTERLEAVING,
            ProcessingStage.BLANK_REMOVAL,
            ProcessingStage.OCR,
            ProcessingStage.SPLITTING,
            ProcessingStage.NAMING,
        ]
        assert expected == STAGE_ORDER


class TestPipelineStateNew:
    """PipelineState.new() creates fresh state with all stages PENDING."""

    def test_all_stages_pending(self):
        state = PipelineState.new()
        for stage in STAGE_ORDER:
            assert state.stages[stage.value].status == StageStatus.PENDING

    def test_status_is_running(self):
        # A fresh state with all PENDING stages has no RUNNING/PAUSED/ERROR,
        # but no stages are completed either. The spec says a fresh state
        # status should be "running" (pipeline is ready to proceed).
        state = PipelineState.new()
        assert state.status == "running"

    def test_empty_dlq(self):
        state = PipelineState.new()
        assert state.dlq == []

    def test_default_config(self):
        state = PipelineState.new()
        assert state.config.auto_advance_on_error is False
        assert state.config.confidence_threshold == 0.7

    def test_custom_config(self):
        cfg = PipelineConfig(auto_advance_on_error=True, confidence_threshold=0.9)
        state = PipelineState.new(config=cfg)
        assert state.config.auto_advance_on_error is True
        assert state.config.confidence_threshold == 0.9


class TestPendingStages:
    """pending_stages() returns stages not yet started."""

    def test_all_pending_initially(self):
        state = PipelineState.new()
        assert len(state.pending_stages()) == 5

    def test_fewer_pending_after_completion(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.INTERLEAVING)
        pending = state.pending_stages()
        assert len(pending) == 4
        assert ProcessingStage.INTERLEAVING not in pending


class TestStageTransitions:
    """Stage transition methods: mark_running, mark_completed, etc."""

    def test_mark_running(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        ss = state.stages[ProcessingStage.INTERLEAVING.value]
        assert ss.status == StageStatus.RUNNING
        assert ss.started_at is not None

    def test_mark_completed_with_result(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.INTERLEAVING, result={"pages": 10})
        ss = state.stages[ProcessingStage.INTERLEAVING.value]
        assert ss.status == StageStatus.COMPLETED
        assert ss.completed_at is not None
        assert ss.result == {"pages": 10}

    def test_mark_completed_without_result(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.OCR)
        state.mark_completed(ProcessingStage.OCR)
        ss = state.stages[ProcessingStage.OCR.value]
        assert ss.status == StageStatus.COMPLETED
        assert ss.result is None

    def test_mark_completed_sets_timestamps(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.INTERLEAVING)
        ss = state.stages[ProcessingStage.INTERLEAVING.value]
        assert ss.started_at is not None
        assert ss.completed_at is not None

    def test_mark_paused(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.SPLITTING)
        state.mark_paused(ProcessingStage.SPLITTING, reason="Low confidence on document 3")
        ss = state.stages[ProcessingStage.SPLITTING.value]
        assert ss.status == StageStatus.PAUSED
        assert ss.pause_reason == "Low confidence on document 3"

    def test_mark_error(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.OCR)
        state.mark_error(ProcessingStage.OCR, error="Tesseract not found")
        ss = state.stages[ProcessingStage.OCR.value]
        assert ss.status == StageStatus.ERROR
        assert ss.error == "Tesseract not found"

    def test_mark_skipped(self):
        state = PipelineState.new()
        state.mark_skipped(ProcessingStage.INTERLEAVING)
        ss = state.stages[ProcessingStage.INTERLEAVING.value]
        assert ss.status == StageStatus.SKIPPED


class TestResumeFrom:
    """resume_from() resets a paused/error stage back to PENDING."""

    def test_resume_paused_stage(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.SPLITTING)
        state.mark_paused(ProcessingStage.SPLITTING, reason="Review needed")
        state.resume_from(ProcessingStage.SPLITTING)
        ss = state.stages[ProcessingStage.SPLITTING.value]
        assert ss.status == StageStatus.PENDING

    def test_resume_error_stage(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.OCR)
        state.mark_error(ProcessingStage.OCR, error="crash")
        state.resume_from(ProcessingStage.OCR)
        ss = state.stages[ProcessingStage.OCR.value]
        assert ss.status == StageStatus.PENDING


class TestCurrentStage:
    """current_stage returns the first non-completed/non-skipped stage."""

    def test_first_stage_initially(self):
        state = PipelineState.new()
        assert state.current_stage == ProcessingStage.INTERLEAVING.value

    def test_advances_after_completion(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.INTERLEAVING)
        assert state.current_stage == ProcessingStage.BLANK_REMOVAL.value

    def test_none_when_all_done(self):
        state = PipelineState.new()
        for stage in STAGE_ORDER:
            state.mark_running(stage)
            state.mark_completed(stage)
        assert state.current_stage is None

    def test_stops_at_paused(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.INTERLEAVING)
        state.mark_running(ProcessingStage.BLANK_REMOVAL)
        state.mark_paused(ProcessingStage.BLANK_REMOVAL, reason="test")
        assert state.current_stage == ProcessingStage.BLANK_REMOVAL.value

    def test_stops_at_error(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_error(ProcessingStage.INTERLEAVING, error="fail")
        assert state.current_stage == ProcessingStage.INTERLEAVING.value


class TestDLQ:
    """Dead-letter queue for documents that fail or need review."""

    def test_add_to_dlq_generates_id(self):
        state = PipelineState.new()
        item = DLQItem(
            stage=ProcessingStage.SPLITTING.value,
            document={"start_page": 1, "end_page": 3},
            reason="Low confidence",
        )
        state.add_to_dlq(item)
        assert len(state.dlq) == 1
        assert state.dlq[0].id.startswith("dlq-")
        assert len(state.dlq[0].id) == 12  # "dlq-" + 8 hex chars

    def test_add_to_dlq_sets_added_at(self):
        state = PipelineState.new()
        item = DLQItem(
            stage=ProcessingStage.NAMING.value,
            document={"filename": "test.pdf"},
            reason="Naming failed",
        )
        state.add_to_dlq(item)
        assert state.dlq[0].added_at is not None

    def test_remove_from_dlq(self):
        state = PipelineState.new()
        item = DLQItem(
            stage=ProcessingStage.SPLITTING.value,
            document={"start_page": 1, "end_page": 3},
            reason="Low confidence",
        )
        state.add_to_dlq(item)
        item_id = state.dlq[0].id
        state.remove_from_dlq(item_id)
        assert len(state.dlq) == 0

    def test_remove_nonexistent_raises(self):
        state = PipelineState.new()
        with pytest.raises(ValueError, match="not found"):
            state.remove_from_dlq("dlq-nonexist")


class TestPersistence:
    """save() and load() roundtrip."""

    def test_save_load_roundtrip(self, tmp_path):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.INTERLEAVING, result={"pages": 5})
        state.mark_running(ProcessingStage.BLANK_REMOVAL)
        state.mark_paused(ProcessingStage.BLANK_REMOVAL, reason="review")

        item = DLQItem(
            stage=ProcessingStage.SPLITTING.value,
            document={"start_page": 1, "end_page": 3},
            reason="Low confidence",
        )
        state.add_to_dlq(item)

        path = tmp_path / "pipeline_state.json"
        state.save(path)

        loaded = PipelineState.load(path)
        assert loaded.stages["interleaving"].status == StageStatus.COMPLETED
        assert loaded.stages["interleaving"].result == {"pages": 5}
        assert loaded.stages["blank_removal"].status == StageStatus.PAUSED
        assert loaded.stages["blank_removal"].pause_reason == "review"
        assert len(loaded.dlq) == 1
        assert loaded.dlq[0].reason == "Low confidence"
        assert loaded.config.auto_advance_on_error is False

    def test_load_missing_file_returns_fresh(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        state = PipelineState.load(path)
        assert len(state.pending_stages()) == 5

    def test_save_creates_valid_json(self, tmp_path):
        state = PipelineState.new()
        path = tmp_path / "pipeline_state.json"
        state.save(path)
        data = json.loads(path.read_text())
        assert "stages" in data
        assert "dlq" in data
        assert "config" in data


class TestLegacyMigration:
    """Legacy state.json with {"stage": "ocr"} should be migrated."""

    def test_migrate_ocr_stage(self, tmp_path):
        legacy = {"stage": "ocr"}
        path = tmp_path / "pipeline_state.json"
        path.write_text(json.dumps(legacy))

        state = PipelineState.load(path)
        # interleaving and blank_removal completed, rest pending
        assert state.stages["interleaving"].status == StageStatus.COMPLETED
        assert state.stages["blank_removal"].status == StageStatus.COMPLETED
        assert state.stages["ocr"].status == StageStatus.PENDING
        assert state.stages["splitting"].status == StageStatus.PENDING
        assert state.stages["naming"].status == StageStatus.PENDING

    def test_migrate_splitting_stage(self, tmp_path):
        legacy = {"stage": "splitting"}
        path = tmp_path / "pipeline_state.json"
        path.write_text(json.dumps(legacy))

        state = PipelineState.load(path)
        assert state.stages["interleaving"].status == StageStatus.COMPLETED
        assert state.stages["blank_removal"].status == StageStatus.COMPLETED
        assert state.stages["ocr"].status == StageStatus.COMPLETED
        assert state.stages["splitting"].status == StageStatus.PENDING
        assert state.stages["naming"].status == StageStatus.PENDING

    def test_migrate_done_stage(self, tmp_path):
        legacy = {"stage": "done"}
        path = tmp_path / "pipeline_state.json"
        path.write_text(json.dumps(legacy))

        state = PipelineState.load(path)
        for stage in STAGE_ORDER:
            assert state.stages[stage.value].status == StageStatus.COMPLETED

    def test_migrate_interleaving_stage(self, tmp_path):
        """First stage — nothing is completed yet."""
        legacy = {"stage": "interleaving"}
        path = tmp_path / "pipeline_state.json"
        path.write_text(json.dumps(legacy))

        state = PipelineState.load(path)
        for stage in STAGE_ORDER:
            assert state.stages[stage.value].status == StageStatus.PENDING


class TestOverallStatus:
    """Derived status property based on stage states."""

    def test_running_when_has_running_stage(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        assert state.status == "running"

    def test_paused_when_has_paused_stage(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_paused(ProcessingStage.INTERLEAVING, reason="test")
        assert state.status == "paused"

    def test_error_when_has_error_stage(self):
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_error(ProcessingStage.INTERLEAVING, error="fail")
        assert state.status == "error"

    def test_completed_when_all_done(self):
        state = PipelineState.new()
        for stage in STAGE_ORDER:
            state.mark_running(stage)
            state.mark_completed(stage)
        assert state.status == "completed"

    def test_completed_with_skipped(self):
        state = PipelineState.new()
        state.mark_skipped(ProcessingStage.INTERLEAVING)
        for stage in STAGE_ORDER[1:]:
            state.mark_running(stage)
            state.mark_completed(stage)
        assert state.status == "completed"

    def test_running_status_for_all_pending(self):
        """Fresh state with no RUNNING stage is still 'running' (ready to proceed)."""
        state = PipelineState.new()
        assert state.status == "running"
