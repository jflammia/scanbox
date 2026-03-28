"""Tests for two-pass duplex page interleaving."""

from pathlib import Path

import pikepdf
import pytest

from scanbox.pipeline.interleave import interleave_pages


def _make_pdf(tmp_path: Path, name: str, num_pages: int) -> Path:
    """Create a PDF with N pages, each containing its page number as text."""
    pdf = pikepdf.Pdf.new()
    for _i in range(num_pages):
        page = pikepdf.Page(
            pikepdf.Dictionary(
                Type=pikepdf.Name.Page,
                MediaBox=[0, 0, 612, 792],
            )
        )
        pdf.pages.append(page)
    path = tmp_path / name
    pdf.save(path)
    return path


class TestInterleave:
    def test_equal_fronts_backs(self, tmp_path: Path):
        fronts = _make_pdf(tmp_path, "fronts.pdf", 3)
        backs = _make_pdf(tmp_path, "backs.pdf", 3)
        output = tmp_path / "combined.pdf"

        result = interleave_pages(fronts, backs, output)

        pdf = pikepdf.Pdf.open(result)
        assert len(pdf.pages) == 6  # F1,B3,F2,B2,F3,B1 -> interleaved

    def test_no_backs(self, tmp_path: Path):
        fronts = _make_pdf(tmp_path, "fronts.pdf", 5)
        output = tmp_path / "combined.pdf"

        result = interleave_pages(fronts, None, output)

        pdf = pikepdf.Pdf.open(result)
        assert len(pdf.pages) == 5  # passthrough

    def test_more_fronts_than_backs(self, tmp_path: Path):
        fronts = _make_pdf(tmp_path, "fronts.pdf", 5)
        backs = _make_pdf(tmp_path, "backs.pdf", 3)
        output = tmp_path / "combined.pdf"

        result = interleave_pages(fronts, backs, output)

        pdf = pikepdf.Pdf.open(result)
        # 3 pairs + 2 single-sided = 8 pages
        assert len(pdf.pages) == 8

    def test_more_backs_than_fronts_raises(self, tmp_path: Path):
        fronts = _make_pdf(tmp_path, "fronts.pdf", 3)
        backs = _make_pdf(tmp_path, "backs.pdf", 5)
        output = tmp_path / "combined.pdf"

        with pytest.raises(ValueError, match="more back pages"):
            interleave_pages(fronts, backs, output)

    def test_single_page_each(self, tmp_path: Path):
        fronts = _make_pdf(tmp_path, "fronts.pdf", 1)
        backs = _make_pdf(tmp_path, "backs.pdf", 1)
        output = tmp_path / "combined.pdf"

        result = interleave_pages(fronts, backs, output)

        pdf = pikepdf.Pdf.open(result)
        assert len(pdf.pages) == 2

    def test_output_file_created(self, tmp_path: Path):
        fronts = _make_pdf(tmp_path, "fronts.pdf", 2)
        output = tmp_path / "combined.pdf"

        result = interleave_pages(fronts, None, output)

        assert result.exists()
        assert result == output

    def test_interleave_order_is_correct(self, tmp_path: Path):
        """Verify backs are reversed and interleaved in correct positions."""
        # Create fronts with labeled metadata per page
        fronts_pdf = pikepdf.Pdf.new()
        for i in range(3):
            page = pikepdf.Page(
                pikepdf.Dictionary(
                    Type=pikepdf.Name.Page,
                    MediaBox=[0, 0, 612, 792],
                    # Use unique MediaBox width to identify each page
                    CropBox=[0, 0, 100 + i, 792],
                )
            )
            fronts_pdf.pages.append(page)
        fronts_path = tmp_path / "fronts.pdf"
        fronts_pdf.save(fronts_path)

        # Create backs — scanned in reverse order (B3, B2, B1)
        backs_pdf = pikepdf.Pdf.new()
        for i in range(3):
            page = pikepdf.Page(
                pikepdf.Dictionary(
                    Type=pikepdf.Name.Page,
                    MediaBox=[0, 0, 612, 792],
                    CropBox=[0, 0, 200 + i, 792],
                )
            )
            backs_pdf.pages.append(page)
        backs_path = tmp_path / "backs.pdf"
        backs_pdf.save(backs_path)

        output = tmp_path / "combined.pdf"
        interleave_pages(fronts_path, backs_path, output)

        result = pikepdf.Pdf.open(output)
        assert len(result.pages) == 6

        # Expected order: F1(100), B1(202), F2(101), B2(201), F3(102), B3(200)
        # Backs reversed: index 2->0, 1->1, 0->2 => CropBox widths: 202, 201, 200
        crop_widths = [float(p.CropBox[2]) for p in result.pages]
        assert crop_widths == [100, 202, 101, 201, 102, 200]

    def test_empty_fronts(self, tmp_path: Path):
        """Edge case: empty fronts PDF should produce empty output."""
        fronts = _make_pdf(tmp_path, "fronts.pdf", 0)
        output = tmp_path / "combined.pdf"

        result = interleave_pages(fronts, None, output)

        pdf = pikepdf.Pdf.open(result)
        assert len(pdf.pages) == 0
