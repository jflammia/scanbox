"""End-to-end pipeline tests using committed test fixture PDFs.

Tests run the real pipeline (interleave → blank removal → OCR → splitting → naming)
against the test suite piles. The AI splitting stage uses the local LLM when available,
falling back to a mock when not.

Requirements:
- tesseract, ghostscript, poppler-utils (system deps for OCR)
- Local LLM at OPENAI_API_BASE (optional — tests skip or mock if unavailable)

Usage:
    # With local LLM (full E2E):
    OPENAI_API_BASE=http://192.168.10.95:11434/v1 \
    OPENAI_API_KEY=mlx-local \
    LLM_MODEL=openai/mlx-community/Qwen3.5-35B-A3B-4bit \
    pytest tests/integration/test_e2e_pipeline.py -v

    # Without LLM (mocked splitting):
    pytest tests/integration/test_e2e_pipeline.py -v
"""

import json
import os
import shutil
from pathlib import Path

import pikepdf
import pytest

from scanbox.models import PipelineResult, SplitDocument
from scanbox.pipeline.runner import PipelineContext, run_pipeline
from scanbox.pipeline.state import PipelineConfig, PipelineState, StageStatus

SUITE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "test_suite"

# Check if real OCR is available
HAS_OCRMYPDF = shutil.which("ocrmypdf") is not None
# Check if real LLM is available
HAS_LLM = bool(os.environ.get("OPENAI_API_BASE") or os.environ.get("ANTHROPIC_API_KEY"))

skip_no_ocr = pytest.mark.skipif(not HAS_OCRMYPDF, reason="ocrmypdf not installed")
skip_no_llm = pytest.mark.skipif(not HAS_LLM, reason="No LLM configured (set OPENAI_API_BASE)")


def _load_pile(pile_name: str, tmp_path: Path) -> PipelineContext:
    """Load a test pile into a PipelineContext for direct pipeline execution."""
    pile_dir = SUITE_DIR / pile_name
    manifest = json.loads((pile_dir / "manifest.json").read_text())

    batch_dir = tmp_path / "batch"
    batch_dir.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy PDFs
    shutil.copy(pile_dir / "fronts.pdf", batch_dir / "fronts.pdf")
    backs = pile_dir / "backs.pdf"
    has_backs = backs.exists()
    if has_backs:
        shutil.copy(backs, batch_dir / "backs.pdf")

    patient_name = manifest["patient"]["name"]

    return PipelineContext(
        batch_dir=batch_dir,
        output_dir=output_dir,
        person_name=patient_name,
        person_slug=patient_name.lower().replace(" ", "-").replace(".", ""),
        person_folder=patient_name.replace(" ", "_").replace(".", ""),
        batch_num=1,
        scan_date="2026-03-30",
        has_backs=has_backs,
    )


class TestInterleaveStage:
    """Test interleaving with real fixture PDFs."""

    def test_standard_pile_interleaves(self, tmp_path):
        ctx = _load_pile("01-standard-clean", tmp_path)
        from scanbox.pipeline.interleave import interleave_pages

        combined = ctx.batch_dir / "combined.pdf"
        interleave_pages(
            ctx.batch_dir / "fronts.pdf",
            ctx.batch_dir / "backs.pdf",
            combined,
        )
        pdf = pikepdf.Pdf.open(combined)
        # 13 fronts + 13 backs = 26 interleaved pages
        assert len(pdf.pages) == 26

    def test_single_sided_passes_through(self, tmp_path):
        ctx = _load_pile("02-single-sided-only", tmp_path)
        from scanbox.pipeline.interleave import interleave_pages

        combined = ctx.batch_dir / "combined.pdf"
        interleave_pages(
            ctx.batch_dir / "fronts.pdf",
            ctx.batch_dir / "backs.pdf",
            combined,
        )
        fronts = pikepdf.Pdf.open(ctx.batch_dir / "fronts.pdf")
        result = pikepdf.Pdf.open(combined)
        # Single-sided still interleaves fronts + backs (backs are blank pages)
        assert len(result.pages) == len(fronts.pages) * 2

    def test_minimal_pile(self, tmp_path):
        ctx = _load_pile("06-minimal-quick", tmp_path)
        from scanbox.pipeline.interleave import interleave_pages

        combined = ctx.batch_dir / "combined.pdf"
        interleave_pages(
            ctx.batch_dir / "fronts.pdf",
            ctx.batch_dir / "backs.pdf",
            combined,
        )
        assert combined.exists()
        pdf = pikepdf.Pdf.open(combined)
        assert len(pdf.pages) >= 3


class TestBlankRemovalStage:
    """Test blank page removal with real fixture PDFs."""

    def test_removes_blanks_from_standard(self, tmp_path):
        ctx = _load_pile("01-standard-clean", tmp_path)
        from scanbox.pipeline.blank_detect import remove_blank_pages
        from scanbox.pipeline.interleave import interleave_pages

        combined = ctx.batch_dir / "combined.pdf"
        interleave_pages(ctx.batch_dir / "fronts.pdf", ctx.batch_dir / "backs.pdf", combined)

        cleaned = ctx.batch_dir / "cleaned.pdf"
        result = remove_blank_pages(combined, cleaned, threshold=0.01)

        # Should remove some blank back pages
        assert len(result.removed_indices) > 0
        cleaned_pdf = pikepdf.Pdf.open(cleaned)
        assert len(cleaned_pdf.pages) < 26  # fewer than interleaved total

    def test_single_sided_removes_all_blanks(self, tmp_path):
        ctx = _load_pile("02-single-sided-only", tmp_path)
        from scanbox.pipeline.blank_detect import remove_blank_pages
        from scanbox.pipeline.interleave import interleave_pages

        combined = ctx.batch_dir / "combined.pdf"
        interleave_pages(ctx.batch_dir / "fronts.pdf", ctx.batch_dir / "backs.pdf", combined)

        cleaned = ctx.batch_dir / "cleaned.pdf"
        remove_blank_pages(combined, cleaned, threshold=0.01)

        # All back pages should be blank → removed
        # Original has 5 fronts, interleaved with 5 blank backs = 10 pages
        # After removal: should have ~5 content pages
        cleaned_pdf = pikepdf.Pdf.open(cleaned)
        assert len(cleaned_pdf.pages) <= 6  # some tolerance for near-blank detection


@skip_no_ocr
class TestOCRStage:
    """Test OCR with real fixture PDFs. Requires tesseract."""

    def test_ocr_produces_text(self, tmp_path):
        ctx = _load_pile("06-minimal-quick", tmp_path)
        from scanbox.pipeline.blank_detect import remove_blank_pages
        from scanbox.pipeline.interleave import interleave_pages
        from scanbox.pipeline.ocr import run_ocr

        combined = ctx.batch_dir / "combined.pdf"
        interleave_pages(ctx.batch_dir / "fronts.pdf", ctx.batch_dir / "backs.pdf", combined)

        cleaned = ctx.batch_dir / "cleaned.pdf"
        remove_blank_pages(combined, cleaned, threshold=0.01)

        ocr_pdf = ctx.batch_dir / "ocr.pdf"
        text_json = ctx.batch_dir / "text_by_page.json"
        run_ocr(cleaned, ocr_pdf, text_json)

        assert ocr_pdf.exists()
        assert text_json.exists()

        text_data = json.loads(text_json.read_text())
        assert len(text_data) >= 1

        # Check that OCR actually found text (our PDFs have real text content)
        all_text = " ".join(text_data.values())
        assert len(all_text) > 100  # should have substantial text


@skip_no_ocr
@skip_no_llm
class TestFullPipelineWithLLM:
    """Full end-to-end pipeline with real LLM. Requires ocrmypdf + LLM."""

    async def test_minimal_pile_produces_documents(self, tmp_path):
        ctx = _load_pile("06-minimal-quick", tmp_path)
        result = await run_pipeline(ctx)

        assert isinstance(result, PipelineResult)
        assert result.status == "completed"
        assert len(result.documents) >= 1

        # Check documents have real metadata
        for doc in result.documents:
            assert doc.document_type != ""
            assert doc.filename.endswith(".pdf")

        # Check document PDFs exist
        docs_dir = ctx.batch_dir / "documents"
        assert docs_dir.exists()
        pdf_files = list(docs_dir.glob("*.pdf"))
        assert len(pdf_files) == len(result.documents)

    async def test_minimal_pile_state_is_complete(self, tmp_path):
        ctx = _load_pile("06-minimal-quick", tmp_path)
        await run_pipeline(ctx)

        state = PipelineState.load(ctx.batch_dir / "state.json")
        assert state.status == "completed"
        for _stage_name, stage_state in state.stages.items():
            assert stage_state.status == StageStatus.COMPLETED
            assert stage_state.result is not None

    async def test_standard_pile_finds_multiple_documents(self, tmp_path):
        """The 11-document standard pile should produce multiple documents."""
        ctx = _load_pile("01-standard-clean", tmp_path)
        result = await run_pipeline(ctx)

        assert result.status == "completed"
        # Should find at least several documents (may not be exactly 11 due to LLM variance)
        assert len(result.documents) >= 3

        # All documents should have page ranges
        for doc in result.documents:
            assert doc.start_page >= 1
            assert doc.end_page >= doc.start_page

    async def test_single_document_pile(self, tmp_path):
        """Single document pile — splitter should find exactly 1 document."""
        ctx = _load_pile("04-single-document", tmp_path)
        result = await run_pipeline(ctx)

        assert result.status == "completed"
        # Should find 1 document (or close to it)
        assert len(result.documents) >= 1
        assert len(result.documents) <= 3  # tolerance for LLM variance


@skip_no_ocr
class TestFullPipelineWithMockedLLM:
    """Full pipeline with real OCR but mocked AI splitting."""

    async def test_pipeline_completes_with_mock(self, tmp_path):
        from unittest.mock import patch

        ctx = _load_pile("06-minimal-quick", tmp_path)

        # Run interleave + blank removal + OCR first to know page count
        from scanbox.pipeline.blank_detect import remove_blank_pages
        from scanbox.pipeline.interleave import interleave_pages
        from scanbox.pipeline.ocr import run_ocr

        combined = ctx.batch_dir / "combined.pdf"
        interleave_pages(ctx.batch_dir / "fronts.pdf", ctx.batch_dir / "backs.pdf", combined)
        br_result = remove_blank_pages(combined, ctx.batch_dir / "cleaned.pdf", threshold=0.01)
        run_ocr(
            ctx.batch_dir / "cleaned.pdf",
            ctx.batch_dir / "ocr.pdf",
            ctx.batch_dir / "text_by_page.json",
        )

        cleaned_pages = br_result.total_pages - len(br_result.removed_indices)

        # Mock the splitter to return a single document covering all pages
        mock_docs = [
            SplitDocument(
                start_page=1,
                end_page=cleaned_pages,
                document_type="Lab Results",
                date_of_service="2026-03-15",
                facility="Quest Diagnostics",
                description="CBC and Metabolic Panel",
                confidence=0.92,
            )
        ]

        with patch("scanbox.pipeline.runner.split_documents", return_value=mock_docs):
            result = await run_pipeline(ctx)

        assert result.status == "completed"
        assert len(result.documents) == 1
        assert result.documents[0].filename.endswith(".pdf")

        # Verify the document PDF was actually created with correct pages
        doc_pdf = pikepdf.Pdf.open(ctx.batch_dir / "documents" / result.documents[0].filename)
        assert len(doc_pdf.pages) == cleaned_pages


@skip_no_ocr
class TestPipelineWithLowConfidence:
    """Test pipeline pause behavior with low-confidence documents."""

    async def test_low_confidence_pauses(self, tmp_path):
        from unittest.mock import patch

        ctx = _load_pile("06-minimal-quick", tmp_path)

        mock_docs = [
            SplitDocument(start_page=1, end_page=2, confidence=0.95),
            SplitDocument(start_page=3, end_page=3, confidence=0.3),  # low
        ]

        config = PipelineConfig(confidence_threshold=0.7)

        with patch("scanbox.pipeline.runner.split_documents", return_value=mock_docs):
            result = await run_pipeline(ctx, pipeline_config=config)

        assert result.status == "paused"
        assert result.paused_stage == "splitting"

    async def test_low_confidence_dlq_mode(self, tmp_path):
        from unittest.mock import patch

        ctx = _load_pile("06-minimal-quick", tmp_path)

        mock_docs = [
            SplitDocument(start_page=1, end_page=2, confidence=0.95),
            SplitDocument(start_page=3, end_page=3, confidence=0.3),
        ]

        config = PipelineConfig(auto_advance_on_error=True, confidence_threshold=0.7)

        with patch("scanbox.pipeline.runner.split_documents", return_value=mock_docs):
            result = await run_pipeline(ctx, pipeline_config=config)

        assert result.status == "completed"

        state = PipelineState.load(ctx.batch_dir / "state.json")
        assert len(state.dlq) == 1
        assert state.dlq[0].stage == "splitting"
