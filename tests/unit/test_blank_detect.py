"""Tests for blank page detection and removal."""

from pathlib import Path

import pikepdf
import pytest

from scanbox.pipeline.blank_detect import detect_blank_pages, remove_blank_pages


class TestDetectBlankPages:
    def test_blank_page_detected(self, page_fixtures_dir: Path):
        pdf_path = page_fixtures_dir / "blank_page.pdf"
        if not pdf_path.exists():
            pytest.skip("Run generate_fixtures first")
        blanks = detect_blank_pages(pdf_path, threshold=0.01)
        assert blanks == [0]  # 0-indexed, only page is blank

    def test_content_page_not_detected(self, page_fixtures_dir: Path):
        pdf_path = page_fixtures_dir / "radiology_report_p1.pdf"
        if not pdf_path.exists():
            pytest.skip("Run generate_fixtures first")
        blanks = detect_blank_pages(pdf_path, threshold=0.01)
        assert blanks == []

    def test_near_blank_detected(self, page_fixtures_dir: Path):
        pdf_path = page_fixtures_dir / "near_blank_page.pdf"
        if not pdf_path.exists():
            pytest.skip("Run generate_fixtures first")
        blanks = detect_blank_pages(pdf_path, threshold=0.01)
        assert blanks == [0]

    def test_multi_page_mixed(self, tmp_path: Path, page_fixtures_dir: Path):
        """Detect blanks in a multi-page PDF with mixed content."""
        blank = page_fixtures_dir / "blank_page.pdf"
        content = page_fixtures_dir / "radiology_report_p1.pdf"
        if not blank.exists() or not content.exists():
            pytest.skip("Run generate_fixtures first")

        merged = pikepdf.Pdf.new()
        for path in [content, blank, content, blank]:
            src = pikepdf.Pdf.open(path)
            merged.pages.extend(src.pages)
        input_path = tmp_path / "mixed.pdf"
        merged.save(input_path)

        blanks = detect_blank_pages(input_path, threshold=0.01)
        assert blanks == [1, 3]


class TestRemoveBlankPages:
    def test_removes_blanks_preserves_content(self, tmp_path: Path, page_fixtures_dir: Path):
        blank = page_fixtures_dir / "blank_page.pdf"
        content = page_fixtures_dir / "radiology_report_p1.pdf"
        if not blank.exists() or not content.exists():
            pytest.skip("Run generate_fixtures first")

        # Build a 3-page PDF: content, blank, content
        merged = pikepdf.Pdf.new()
        for path in [content, blank, content]:
            src = pikepdf.Pdf.open(path)
            merged.pages.extend(src.pages)
        input_path = tmp_path / "input.pdf"
        merged.save(input_path)

        output_path = tmp_path / "cleaned.pdf"
        result = remove_blank_pages(input_path, output_path, threshold=0.01)

        pdf = pikepdf.Pdf.open(result.cleaned_path)
        assert len(pdf.pages) == 2
        assert result.removed_indices == [1]

    def test_no_blanks_passthrough(self, tmp_path: Path, page_fixtures_dir: Path):
        content = page_fixtures_dir / "radiology_report_p1.pdf"
        if not content.exists():
            pytest.skip("Run generate_fixtures first")

        output_path = tmp_path / "cleaned.pdf"
        result = remove_blank_pages(content, output_path, threshold=0.01)

        pdf = pikepdf.Pdf.open(result.cleaned_path)
        assert len(pdf.pages) == 1
        assert result.removed_indices == []

    def test_all_blank_pages(self, tmp_path: Path, page_fixtures_dir: Path):
        """All pages blank — output should be empty."""
        blank = page_fixtures_dir / "blank_page.pdf"
        if not blank.exists():
            pytest.skip("Run generate_fixtures first")

        merged = pikepdf.Pdf.new()
        for _ in range(3):
            src = pikepdf.Pdf.open(blank)
            merged.pages.extend(src.pages)
        input_path = tmp_path / "all_blank.pdf"
        merged.save(input_path)

        output_path = tmp_path / "cleaned.pdf"
        result = remove_blank_pages(input_path, output_path, threshold=0.01)

        pdf = pikepdf.Pdf.open(result.cleaned_path)
        assert len(pdf.pages) == 0
        assert result.removed_indices == [0, 1, 2]
        assert result.total_pages == 3

    def test_result_total_pages_correct(self, tmp_path: Path, page_fixtures_dir: Path):
        content = page_fixtures_dir / "radiology_report_p1.pdf"
        blank = page_fixtures_dir / "blank_page.pdf"
        if not content.exists() or not blank.exists():
            pytest.skip("Run generate_fixtures first")

        merged = pikepdf.Pdf.new()
        for path in [content, blank, content]:
            src = pikepdf.Pdf.open(path)
            merged.pages.extend(src.pages)
        input_path = tmp_path / "input.pdf"
        merged.save(input_path)

        output_path = tmp_path / "cleaned.pdf"
        result = remove_blank_pages(input_path, output_path, threshold=0.01)

        assert result.total_pages == 3
