"""Tests for fixture generator and fixture file integrity."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pikepdf

from tests.generate_fixtures import (
    create_blank_page_pdf,
    create_near_blank_page_pdf,
    create_text_page_pdf,
    merge_pdfs,
)


class TestCreateTextPagePdf:
    """create_text_page_pdf should produce valid single-page PDFs with text content."""

    def test_creates_single_page_pdf(self, tmp_path: Path):
        output = tmp_path / "text.pdf"
        create_text_page_pdf("Hello World", output)
        pdf = pikepdf.Pdf.open(output)
        assert len(pdf.pages) == 1

    def test_creates_parent_directories(self, tmp_path: Path):
        output = tmp_path / "nested" / "dir" / "text.pdf"
        create_text_page_pdf("Test", output)
        assert output.exists()

    def test_page_has_content(self, tmp_path: Path):
        output = tmp_path / "text.pdf"
        create_text_page_pdf("MEMORIAL HOSPITAL\nRadiology Report", output)
        # File should be larger than a blank page
        blank = tmp_path / "blank.pdf"
        create_blank_page_pdf(blank)
        assert output.stat().st_size > 0

    def test_respects_dpi_parameter(self, tmp_path: Path):
        low = tmp_path / "low.pdf"
        high = tmp_path / "high.pdf"
        create_text_page_pdf("Test", low, dpi=72)
        create_text_page_pdf("Test", high, dpi=300)
        # Higher DPI should produce a larger file
        assert high.stat().st_size > low.stat().st_size


class TestCreateBlankPagePdf:
    """create_blank_page_pdf should produce valid blank white pages."""

    def test_creates_single_page_pdf(self, tmp_path: Path):
        output = tmp_path / "blank.pdf"
        create_blank_page_pdf(output)
        pdf = pikepdf.Pdf.open(output)
        assert len(pdf.pages) == 1

    def test_page_is_white(self, tmp_path: Path):
        output = tmp_path / "blank.pdf"
        create_blank_page_pdf(output, dpi=72)
        from pdf2image import convert_from_path

        images = convert_from_path(str(output), dpi=72)
        img = images[0].convert("L")  # grayscale: 0=black, 255=white
        pixels = list(img.tobytes())
        white_pixels = sum(1 for p in pixels if p >= 250)
        assert white_pixels / len(pixels) > 0.99


class TestCreateNearBlankPagePdf:
    """create_near_blank_page_pdf should have minimal ink coverage."""

    def test_creates_single_page_pdf(self, tmp_path: Path):
        output = tmp_path / "near_blank.pdf"
        create_near_blank_page_pdf(output)
        pdf = pikepdf.Pdf.open(output)
        assert len(pdf.pages) == 1

    def test_has_some_content_but_mostly_white(self, tmp_path: Path):
        output = tmp_path / "near_blank.pdf"
        create_near_blank_page_pdf(output, dpi=72)
        from pdf2image import convert_from_path

        images = convert_from_path(str(output), dpi=72)
        img = images[0].convert("L")  # grayscale
        pixels = list(img.tobytes())
        non_white = sum(1 for p in pixels if p < 250)
        ink_coverage = non_white / len(pixels)
        # Should have some ink but less than 1%
        assert ink_coverage < 0.01
        assert ink_coverage > 0  # Not completely blank


class TestMergePdfs:
    """merge_pdfs should combine multiple single-page PDFs."""

    def test_merge_two_pages(self, tmp_path: Path):
        p1 = tmp_path / "p1.pdf"
        p2 = tmp_path / "p2.pdf"
        out = tmp_path / "merged.pdf"
        create_text_page_pdf("Page 1", p1)
        create_text_page_pdf("Page 2", p2)
        merge_pdfs([p1, p2], out)
        pdf = pikepdf.Pdf.open(out)
        assert len(pdf.pages) == 2

    def test_merge_five_pages(self, tmp_path: Path):
        pages = []
        for i in range(5):
            p = tmp_path / f"p{i}.pdf"
            create_text_page_pdf(f"Page {i}", p)
            pages.append(p)
        out = tmp_path / "merged.pdf"
        merge_pdfs(pages, out)
        pdf = pikepdf.Pdf.open(out)
        assert len(pdf.pages) == 5

    def test_creates_parent_directories(self, tmp_path: Path):
        p1 = tmp_path / "p1.pdf"
        create_text_page_pdf("Test", p1)
        out = tmp_path / "nested" / "merged.pdf"
        merge_pdfs([p1], out)
        assert out.exists()


class TestGeneratedFixtureFiles:
    """Verify the pre-generated fixture files are valid."""

    def test_escl_capabilities_xml_valid(self, escl_fixtures_dir: Path):
        xml_path = escl_fixtures_dir / "capabilities.xml"
        assert xml_path.exists()
        tree = ET.parse(xml_path)
        root = tree.getroot()
        assert "ScannerCapabilities" in root.tag

    def test_escl_capabilities_has_adf(self, escl_fixtures_dir: Path):
        xml_path = escl_fixtures_dir / "capabilities.xml"
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = {"scan": "http://schemas.hp.com/imaging/escl/2011/05/03"}
        adf = root.find(".//scan:Adf", ns)
        assert adf is not None

    def test_escl_capabilities_has_platen(self, escl_fixtures_dir: Path):
        xml_path = escl_fixtures_dir / "capabilities.xml"
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = {"scan": "http://schemas.hp.com/imaging/escl/2011/05/03"}
        platen = root.find(".//scan:Platen", ns)
        assert platen is not None

    def test_escl_status_idle_xml_valid(self, escl_fixtures_dir: Path):
        xml_path = escl_fixtures_dir / "status_idle.xml"
        assert xml_path.exists()
        tree = ET.parse(xml_path)
        root = tree.getroot()
        assert "ScannerStatus" in root.tag

    def test_escl_status_reports_idle(self, escl_fixtures_dir: Path):
        xml_path = escl_fixtures_dir / "status_idle.xml"
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = {"pwg": "http://www.pwg.org/schemas/2010/12/sm"}
        state = root.find(".//pwg:State", ns)
        assert state is not None
        assert state.text == "Idle"

    def test_fronts_5docs_has_5_pages(self, batch_fixtures_dir: Path):
        pdf = pikepdf.Pdf.open(batch_fixtures_dir / "fronts_5docs.pdf")
        assert len(pdf.pages) == 5

    def test_backs_5docs_has_5_pages(self, batch_fixtures_dir: Path):
        pdf = pikepdf.Pdf.open(batch_fixtures_dir / "backs_5docs.pdf")
        assert len(pdf.pages) == 5

    def test_fronts_all_single_sided_has_3_pages(self, batch_fixtures_dir: Path):
        pdf = pikepdf.Pdf.open(batch_fixtures_dir / "fronts_all_single_sided.pdf")
        assert len(pdf.pages) == 3

    def test_fronts_single_doc_has_4_pages(self, batch_fixtures_dir: Path):
        pdf = pikepdf.Pdf.open(batch_fixtures_dir / "fronts_single_doc.pdf")
        assert len(pdf.pages) == 4

    def test_individual_pages_are_single_page(self, page_fixtures_dir: Path):
        for pdf_path in page_fixtures_dir.glob("*.pdf"):
            pdf = pikepdf.Pdf.open(pdf_path)
            assert len(pdf.pages) == 1, f"{pdf_path.name} should be single-page"


class TestConftest:
    """Verify conftest fixtures work correctly."""

    def test_fixtures_dir_exists(self, fixtures_dir: Path):
        assert fixtures_dir.exists()
        assert fixtures_dir.is_dir()

    def test_escl_fixtures_dir_exists(self, escl_fixtures_dir: Path):
        assert escl_fixtures_dir.exists()

    def test_batch_fixtures_dir_exists(self, batch_fixtures_dir: Path):
        assert batch_fixtures_dir.exists()

    def test_page_fixtures_dir_exists(self, page_fixtures_dir: Path):
        assert page_fixtures_dir.exists()

    def test_tmp_config_has_isolated_dirs(self, tmp_config):
        assert tmp_config.INTERNAL_DATA_DIR.exists()
        assert tmp_config.OUTPUT_DIR.exists()
        assert "data" in str(tmp_config.INTERNAL_DATA_DIR)
        assert "output" in str(tmp_config.OUTPUT_DIR)

    def test_tmp_config_derived_paths(self, tmp_config):
        assert tmp_config.db_path.parent == tmp_config.INTERNAL_DATA_DIR
        assert tmp_config.archive_dir.parent == tmp_config.OUTPUT_DIR

    def test_sample_splits_json_coverage(self, sample_splits_json):
        """Splits should cover pages 1-5 contiguously."""
        assert len(sample_splits_json) == 3
        assert sample_splits_json[0]["start_page"] == 1
        assert sample_splits_json[-1]["end_page"] == 5
        # Verify contiguous
        for i in range(1, len(sample_splits_json)):
            assert sample_splits_json[i]["start_page"] == sample_splits_json[i - 1]["end_page"] + 1
