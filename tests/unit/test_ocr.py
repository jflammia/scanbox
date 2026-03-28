"""Tests for OCR text extraction."""

import shutil
from pathlib import Path

import pytest

from scanbox.pipeline.ocr import extract_text_by_page, run_ocr

pytestmark = pytest.mark.skipif(
    not shutil.which("tesseract"),
    reason="tesseract not installed",
)


class TestExtractTextByPage:
    def test_extracts_text_from_content_page(self, page_fixtures_dir: Path):
        pdf_path = page_fixtures_dir / "radiology_report_p1.pdf"
        if not pdf_path.exists():
            pytest.skip("Run generate_fixtures first")
        texts = extract_text_by_page(pdf_path)
        assert 1 in texts
        assert len(texts[1]) > 50  # Should have substantial text
        assert "RADIOLOGY" in texts[1].upper() or "MEMORIAL" in texts[1].upper()

    def test_blank_page_has_minimal_text(self, page_fixtures_dir: Path):
        pdf_path = page_fixtures_dir / "blank_page.pdf"
        if not pdf_path.exists():
            pytest.skip("Run generate_fixtures first")
        texts = extract_text_by_page(pdf_path)
        assert 1 in texts
        assert len(texts[1].strip()) < 10  # Blank or nearly blank

    def test_multi_page_returns_all_pages(self, batch_fixtures_dir: Path):
        pdf_path = batch_fixtures_dir / "fronts_all_single_sided.pdf"
        if not pdf_path.exists():
            pytest.skip("Run generate_fixtures first")
        texts = extract_text_by_page(pdf_path)
        assert len(texts) == 3  # 3-page fixture


class TestRunOcr:
    def test_creates_searchable_pdf(self, tmp_path: Path, page_fixtures_dir: Path):
        input_path = page_fixtures_dir / "radiology_report_p1.pdf"
        if not input_path.exists():
            pytest.skip("Run generate_fixtures first")
        output_path = tmp_path / "ocr.pdf"
        text_path = tmp_path / "text_by_page.json"

        run_ocr(input_path, output_path, text_path)

        assert output_path.exists()
        assert text_path.exists()
