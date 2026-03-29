"""Unit tests for PDF metadata embedding."""

import pikepdf

from scanbox.pipeline.output import embed_pdf_metadata


class TestEmbedPdfMetadata:
    def _make_pdf(self, path):
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        pdf.save(path)

    def test_embeds_title_and_author(self, tmp_path):
        pdf_path = tmp_path / "doc.pdf"
        self._make_pdf(pdf_path)

        embed_pdf_metadata(
            pdf_path,
            title="Lab Results — Blood Panel",
            author="City Hospital",
            subject="Jane Doe",
            creation_date="2026-01-15",
        )

        pdf = pikepdf.Pdf.open(pdf_path)
        with pdf.open_metadata() as meta:
            assert meta.get("dc:title") == "Lab Results — Blood Panel"
            assert "ScanBox" in meta.get("xmp:CreatorTool", "")

    def test_embeds_creation_date(self, tmp_path):
        pdf_path = tmp_path / "doc.pdf"
        self._make_pdf(pdf_path)

        embed_pdf_metadata(
            pdf_path,
            title="Test",
            author="Test Author",
            subject="Test Subject",
            creation_date="2026-03-29",
        )

        pdf = pikepdf.Pdf.open(pdf_path)
        assert "/CreationDate" in pdf.docinfo
        assert "20260329" in str(pdf.docinfo["/CreationDate"])

    def test_unknown_date_skips_docinfo(self, tmp_path):
        pdf_path = tmp_path / "doc.pdf"
        self._make_pdf(pdf_path)

        embed_pdf_metadata(
            pdf_path,
            title="Test",
            author="Test",
            subject="Test",
            creation_date="unknown",
        )

        pdf = pikepdf.Pdf.open(pdf_path)
        # Should not have creation date set
        assert "/CreationDate" not in pdf.docinfo

    def test_empty_date_skips_docinfo(self, tmp_path):
        pdf_path = tmp_path / "doc.pdf"
        self._make_pdf(pdf_path)

        embed_pdf_metadata(
            pdf_path,
            title="Test",
            author="Test",
            subject="Test",
            creation_date="",
        )

        pdf = pikepdf.Pdf.open(pdf_path)
        assert "/CreationDate" not in pdf.docinfo
