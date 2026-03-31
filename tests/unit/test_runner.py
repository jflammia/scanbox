"""Unit tests for pipeline runner with mocked pipeline stages."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pikepdf

from scanbox.models import ProcessingStage, SplitDocument
from scanbox.pipeline.runner import PipelineContext, _state_path, run_pipeline
from scanbox.pipeline.state import PipelineState, StageStatus


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


class TestPipelineState:
    def test_load_state_default(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        state = PipelineState.load(_state_path(ctx))
        assert state.current_stage == "interleaving"

    def test_load_state_existing(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        # Write a legacy format state.json
        (ctx.batch_dir / "state.json").write_text(json.dumps({"stage": "ocr"}))
        state = PipelineState.load(_state_path(ctx))
        # Interleaving and blank_removal should be completed (migrated from legacy)
        assert state.stages["interleaving"].status == StageStatus.COMPLETED
        assert state.stages["blank_removal"].status == StageStatus.COMPLETED
        assert state.current_stage == "ocr"

    def test_save_state(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.INTERLEAVING)
        state.save(_state_path(ctx))
        loaded = PipelineState.load(_state_path(ctx))
        assert loaded.stages["interleaving"].status == StageStatus.COMPLETED

    def test_save_state_with_result(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        state = PipelineState.new()
        state.mark_completed(ProcessingStage.SPLITTING, {"document_count": 5})
        state.save(_state_path(ctx))
        loaded = PipelineState.load(_state_path(ctx))
        assert loaded.stages["splitting"].result == {"document_count": 5}


class TestRunPipeline:
    @patch("scanbox.pipeline.runner.split_documents")
    @patch("scanbox.pipeline.runner.run_ocr")
    @patch("scanbox.pipeline.runner.remove_blank_pages")
    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_full_pipeline_run(
        self, mock_interleave, mock_blank, mock_ocr, mock_split, tmp_path
    ):
        ctx = _make_ctx(tmp_path)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 3)

        # Mock interleave: create combined.pdf
        def fake_interleave(fronts, backs, output):
            _make_pdf(output, 3)

        mock_interleave.side_effect = fake_interleave

        # Mock blank removal: create cleaned.pdf
        mock_result = MagicMock()
        mock_result.removed_indices = []
        mock_result.total_pages = 3

        def fake_blank(input_path, output_path, threshold):
            _make_pdf(output_path, 3)
            return mock_result

        mock_blank.side_effect = fake_blank

        # Mock OCR: create ocr.pdf and text_by_page.json
        def fake_ocr(input_path, output_path, text_json_path):
            _make_pdf(output_path, 3)
            text_json_path.write_text(json.dumps({"1": "Page 1", "2": "Page 2", "3": "Page 3"}))

        mock_ocr.side_effect = fake_ocr

        # Mock AI splitting
        mock_split.return_value = [
            SplitDocument(
                start_page=1,
                end_page=2,
                document_type="Lab Results",
                date_of_service="2026-01-15",
                facility="City Hospital",
                description="Blood Panel",
                confidence=0.95,
            ),
            SplitDocument(
                start_page=3,
                end_page=3,
                document_type="Letter",
                date_of_service="2026-01-20",
                facility="unknown",
                description="Referral Letter",
                confidence=0.88,
            ),
        ]

        progress_calls = []

        async def on_progress(stage: str, detail: str = "", complete: bool = False):
            progress_calls.append((stage, detail, complete))

        result = await run_pipeline(ctx, on_progress=on_progress)
        docs = result.documents

        assert result.status == "completed"
        assert len(docs) == 2
        assert docs[0].document_type == "Lab Results"
        assert docs[1].document_type == "Letter"
        assert docs[0].filename.endswith(".pdf")
        assert docs[1].filename.endswith(".pdf")

        # Verify progress was called for each stage (start events)
        stages = [c[0] for c in progress_calls if not c[2]]
        assert "interleaving" in stages
        assert "blank_removal" in stages
        assert "ocr" in stages
        assert "splitting" in stages
        assert "naming" in stages

        # Verify stage_done was called for each stage (complete events)
        done_stages = [c[0] for c in progress_calls if c[2]]
        assert "interleaving" in done_stages
        assert "blank_removal" in done_stages
        assert "ocr" in done_stages
        assert "splitting" in done_stages
        assert "naming" in done_stages

        # Verify document files were created
        docs_dir = ctx.batch_dir / "documents"
        assert docs_dir.exists()
        pdf_files = list(docs_dir.glob("*.pdf"))
        assert len(pdf_files) == 2

        # Verify state has all stages completed
        state = PipelineState.load(_state_path(ctx))
        for stage_name in ["interleaving", "blank_removal", "ocr", "splitting", "naming"]:
            assert state.stages[stage_name].status == StageStatus.COMPLETED

    @patch("scanbox.pipeline.runner.split_documents")
    @patch("scanbox.pipeline.runner.run_ocr")
    @patch("scanbox.pipeline.runner.remove_blank_pages")
    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_pipeline_with_backs(
        self, mock_interleave, mock_blank, mock_ocr, mock_split, tmp_path
    ):
        ctx = _make_ctx(tmp_path, has_backs=True)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 2)
        _make_pdf(ctx.batch_dir / "backs.pdf", 2)

        def fake_interleave(fronts, backs, output):
            assert backs is not None
            _make_pdf(output, 4)

        mock_interleave.side_effect = fake_interleave

        mock_result = MagicMock()
        mock_result.removed_indices = [3]
        mock_result.total_pages = 4

        def fake_blank(inp, out, threshold):
            _make_pdf(out, 3)
            return mock_result

        mock_blank.side_effect = fake_blank

        def fake_ocr(inp, out, text_json):
            _make_pdf(out, 3)
            text_json.write_text(json.dumps({"1": "A", "2": "B", "3": "C"}))

        mock_ocr.side_effect = fake_ocr

        mock_split.return_value = [
            SplitDocument(start_page=1, end_page=3, document_type="Other", description="Doc")
        ]

        result = await run_pipeline(ctx)
        docs = result.documents

        assert result.status == "completed"
        assert len(docs) == 1
        mock_interleave.assert_called_once()
        # Verify backs was passed
        call_args = mock_interleave.call_args
        assert call_args[0][1] is not None

    @patch("scanbox.pipeline.runner.split_documents")
    @patch("scanbox.pipeline.runner.run_ocr")
    async def test_pipeline_resumes_from_checkpoint(self, mock_ocr, mock_split, tmp_path):
        """Pipeline resumes from OCR stage if earlier stages completed."""
        ctx = _make_ctx(tmp_path)

        # Pre-create files from earlier stages
        _make_pdf(ctx.batch_dir / "combined.pdf", 2)
        _make_pdf(ctx.batch_dir / "cleaned.pdf", 2)
        # Set checkpoint to OCR stage (legacy format, will be migrated)
        (ctx.batch_dir / "state.json").write_text(json.dumps({"stage": "ocr"}))

        def fake_ocr(inp, out, text_json):
            _make_pdf(out, 2)
            text_json.write_text(json.dumps({"1": "Hello", "2": "World"}))

        mock_ocr.side_effect = fake_ocr
        mock_split.return_value = [
            SplitDocument(start_page=1, end_page=2, document_type="Lab Results")
        ]

        result = await run_pipeline(ctx)
        docs = result.documents

        assert result.status == "completed"
        assert len(docs) == 1
        mock_ocr.assert_called_once()
        mock_split.assert_called_once()

    async def test_pipeline_no_progress_callback(self, tmp_path):
        """Pipeline works without on_progress callback."""
        ctx = _make_ctx(tmp_path)

        # Set state to naming with pre-existing splits using new format
        _make_pdf(ctx.batch_dir / "ocr.pdf", 1)
        splits = [{"start_page": 1, "end_page": 1, "document_type": "Other", "description": "X"}]
        (ctx.batch_dir / "splits.json").write_text(json.dumps(splits))
        # Write new-format state with all stages before naming completed
        state = PipelineState.new()
        state.mark_completed(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.BLANK_REMOVAL)
        state.mark_completed(ProcessingStage.OCR)
        state.mark_completed(ProcessingStage.SPLITTING)
        state.save(_state_path(ctx))

        result = await run_pipeline(ctx, on_progress=None)
        assert result.status == "completed"
        assert len(result.documents) == 1

    @patch("scanbox.pipeline.runner.split_documents")
    @patch("scanbox.pipeline.runner.run_ocr")
    @patch("scanbox.pipeline.runner.remove_blank_pages")
    @patch("scanbox.pipeline.runner.interleave_pages")
    async def test_stage_done_detail_messages(
        self, mock_interleave, mock_blank, mock_ocr, mock_split, tmp_path
    ):
        """stage_done calls include correct detail strings."""
        ctx = _make_ctx(tmp_path)
        _make_pdf(ctx.batch_dir / "fronts.pdf", 2)

        def fake_interleave(fronts, backs, output):
            _make_pdf(output, 2)

        mock_interleave.side_effect = fake_interleave

        mock_result = MagicMock()
        mock_result.removed_indices = [1]
        mock_result.total_pages = 2

        def fake_blank(inp, out, threshold):
            _make_pdf(out, 1)
            return mock_result

        mock_blank.side_effect = fake_blank

        def fake_ocr(inp, out, text_json):
            _make_pdf(out, 1)
            text_json.write_text(json.dumps({"1": "Page 1"}))

        mock_ocr.side_effect = fake_ocr

        mock_split.return_value = [
            SplitDocument(start_page=1, end_page=1, document_type="Lab Results")
        ]

        done_calls = []

        async def on_progress(stage: str, detail: str = "", complete: bool = False):
            if complete:
                done_calls.append((stage, detail))

        result = await run_pipeline(ctx, on_progress=on_progress)
        assert result.status == "completed"

        done_map = dict(done_calls)
        assert "2 pages" in done_map["interleaving"]
        assert "1 pages" in done_map["blank_removal"]
        assert "1 blank removed" in done_map["blank_removal"]
        assert done_map["ocr"] == "OCR complete"
        assert "1 documents" in done_map["splitting"]
        assert "1 documents named" in done_map["naming"]
