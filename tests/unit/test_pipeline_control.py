"""Tests for pipeline pause/resume/DLQ behavior."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pikepdf

from scanbox.models import PipelineResult, SplitDocument
from scanbox.pipeline.runner import PipelineContext, run_pipeline
from scanbox.pipeline.state import PipelineConfig, PipelineState, StageStatus


def _make_pdf(path: Path, num_pages: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.add_blank_page(page_size=(612, 792))
    pdf.save(path)


def _make_ctx(tmp_path: Path, has_backs: bool = False) -> PipelineContext:
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir(parents=True, exist_ok=True)
    return PipelineContext(
        batch_dir=batch_dir,
        output_dir=tmp_path / "output",
        person_name="Jane Doe",
        person_slug="jane-doe",
        person_folder="Jane_Doe",
        batch_num=1,
        scan_date="2026-03-29",
        has_backs=has_backs,
    )


class TestPipelineControl:
    @patch("scanbox.pipeline.runner.split_documents")
    @patch("scanbox.pipeline.runner.run_ocr")
    @patch("scanbox.pipeline.runner.remove_blank_pages")
    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_returns_pipeline_result(
        self, mock_interleave, mock_blank, mock_ocr, mock_split, tmp_path
    ):
        """Basic run returns PipelineResult with status='completed'."""
        ctx = _make_ctx(tmp_path)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 2)

        def fake_interleave(fronts, backs, output):
            _make_pdf(output, 2)

        mock_interleave.side_effect = fake_interleave

        mock_result = MagicMock()
        mock_result.removed_indices = []
        mock_result.total_pages = 2

        def fake_blank(inp, out, threshold):
            _make_pdf(out, 2)
            return mock_result

        mock_blank.side_effect = fake_blank

        def fake_ocr(inp, out, text_json):
            _make_pdf(out, 2)
            text_json.write_text(json.dumps({"1": "Page 1", "2": "Page 2"}))

        mock_ocr.side_effect = fake_ocr

        mock_split.return_value = [
            SplitDocument(
                start_page=1,
                end_page=2,
                document_type="Lab Results",
                description="Blood Panel",
                confidence=0.95,
            ),
        ]

        result = await run_pipeline(ctx)

        assert isinstance(result, PipelineResult)
        assert result.status == "completed"
        assert len(result.documents) == 1
        assert result.documents[0].document_type == "Lab Results"
        assert result.paused_stage is None
        assert result.error_stage is None

    @patch("scanbox.pipeline.runner.split_documents")
    @patch("scanbox.pipeline.runner.run_ocr")
    @patch("scanbox.pipeline.runner.remove_blank_pages")
    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_pauses_on_low_confidence(
        self, mock_interleave, mock_blank, mock_ocr, mock_split, tmp_path
    ):
        """Splitter returns doc with confidence 0.3, pipeline pauses."""
        ctx = _make_ctx(tmp_path)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 2)

        def fake_interleave(fronts, backs, output):
            _make_pdf(output, 2)

        mock_interleave.side_effect = fake_interleave

        mock_result = MagicMock()
        mock_result.removed_indices = []
        mock_result.total_pages = 2

        def fake_blank(inp, out, threshold):
            _make_pdf(out, 2)
            return mock_result

        mock_blank.side_effect = fake_blank

        def fake_ocr(inp, out, text_json):
            _make_pdf(out, 2)
            text_json.write_text(json.dumps({"1": "Page 1", "2": "Page 2"}))

        mock_ocr.side_effect = fake_ocr

        mock_split.return_value = [
            SplitDocument(
                start_page=1,
                end_page=2,
                document_type="Lab Results",
                description="Blood Panel",
                confidence=0.3,
            ),
        ]

        # Default config: auto_advance_on_error=False, confidence_threshold=0.7
        pipeline_config = PipelineConfig(auto_advance_on_error=False, confidence_threshold=0.7)
        result = await run_pipeline(ctx, pipeline_config=pipeline_config)

        assert result.status == "paused"
        assert result.paused_stage == "splitting"
        assert "below confidence threshold" in result.paused_reason
        # Low-confidence docs are still in the documents list
        assert len(result.documents) == 1
        assert result.documents[0].confidence == 0.3

        # State file should reflect paused status
        state = PipelineState.load(ctx.batch_dir / "state.json")
        assert state.stages["splitting"].status == StageStatus.PAUSED

    @patch("scanbox.pipeline.runner.split_documents")
    @patch("scanbox.pipeline.runner.run_ocr")
    @patch("scanbox.pipeline.runner.remove_blank_pages")
    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_dlq_mode_continues_past_low_confidence(
        self, mock_interleave, mock_blank, mock_ocr, mock_split, tmp_path
    ):
        """With auto_advance_on_error=True, pipeline completes and DLQ has the item."""
        ctx = _make_ctx(tmp_path)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 2)

        def fake_interleave(fronts, backs, output):
            _make_pdf(output, 2)

        mock_interleave.side_effect = fake_interleave

        mock_result = MagicMock()
        mock_result.removed_indices = []
        mock_result.total_pages = 2

        def fake_blank(inp, out, threshold):
            _make_pdf(out, 2)
            return mock_result

        mock_blank.side_effect = fake_blank

        def fake_ocr(inp, out, text_json):
            _make_pdf(out, 2)
            text_json.write_text(json.dumps({"1": "Page 1", "2": "Page 2"}))

        mock_ocr.side_effect = fake_ocr

        mock_split.return_value = [
            SplitDocument(
                start_page=1,
                end_page=2,
                document_type="Lab Results",
                description="Blood Panel",
                confidence=0.3,
            ),
        ]

        pipeline_config = PipelineConfig(auto_advance_on_error=True, confidence_threshold=0.7)
        result = await run_pipeline(ctx, pipeline_config=pipeline_config)

        assert result.status == "completed"
        assert len(result.documents) == 1

        # DLQ should have the low-confidence item
        state = PipelineState.load(ctx.batch_dir / "state.json")
        assert len(state.dlq) == 1
        assert "Confidence 0.30 below" in state.dlq[0].reason
        assert "threshold 0.7" in state.dlq[0].reason

    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_stage_error_returns_error_result(self, mock_interleave, tmp_path):
        """Interleave raises RuntimeError, result has status='error'."""
        ctx = _make_ctx(tmp_path)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 2)

        mock_interleave.side_effect = RuntimeError("Corrupt PDF")

        result = await run_pipeline(ctx)

        assert result.status == "error"
        assert result.error_stage == "interleaving"
        assert "Corrupt PDF" in result.error_message

        # State file should reflect error
        state = PipelineState.load(ctx.batch_dir / "state.json")
        assert state.stages["interleaving"].status == StageStatus.ERROR

    @patch("scanbox.pipeline.runner.split_documents")
    @patch("scanbox.pipeline.runner.run_ocr")
    @patch("scanbox.pipeline.runner.remove_blank_pages")
    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_state_json_has_stage_results(
        self, mock_interleave, mock_blank, mock_ocr, mock_split, tmp_path
    ):
        """After completion, state.json has result dicts for each stage."""
        ctx = _make_ctx(tmp_path)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 2)

        def fake_interleave(fronts, backs, output):
            _make_pdf(output, 2)

        mock_interleave.side_effect = fake_interleave

        mock_result = MagicMock()
        mock_result.removed_indices = []
        mock_result.total_pages = 2

        def fake_blank(inp, out, threshold):
            _make_pdf(out, 2)
            return mock_result

        mock_blank.side_effect = fake_blank

        def fake_ocr(inp, out, text_json):
            _make_pdf(out, 2)
            text_json.write_text(json.dumps({"1": "Page 1", "2": "Page 2"}))

        mock_ocr.side_effect = fake_ocr

        mock_split.return_value = [
            SplitDocument(
                start_page=1,
                end_page=2,
                document_type="Lab Results",
                description="Blood Panel",
                confidence=0.95,
            ),
        ]

        await run_pipeline(ctx)

        state = PipelineState.load(ctx.batch_dir / "state.json")
        for stage in ["interleaving", "blank_removal", "ocr", "splitting", "naming"]:
            assert state.stages[stage].status == StageStatus.COMPLETED
            assert state.stages[stage].result is not None
