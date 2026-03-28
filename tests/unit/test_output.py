"""Tests for output file writing (archive, medical records, Index.csv)."""

import csv
from pathlib import Path

import pikepdf
import pytest

from scanbox.models import SplitDocument
from scanbox.pipeline.output import append_index_csv, write_archive, write_medical_records


@pytest.fixture
def sample_doc() -> SplitDocument:
    return SplitDocument(
        start_page=1,
        end_page=2,
        document_type="Radiology Report",
        date_of_service="2025-06-15",
        facility="Memorial Hospital",
        provider="Dr. Chen",
        description="CT Abdomen",
        confidence=0.95,
    )


def _make_dummy_pdf(path: Path) -> None:
    pdf = pikepdf.Pdf.new()
    pdf.pages.append(
        pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, 612, 792]))
    )
    pdf.save(path)


class TestWriteArchive:
    def test_copies_combined_pdf(self, tmp_path: Path):
        src = tmp_path / "combined.pdf"
        _make_dummy_pdf(src)

        archive_dir = tmp_path / "archive"
        result = write_archive(
            src, archive_dir, person_slug="john-doe", scan_date="2026-03-28", batch_num=1
        )

        assert result.exists()
        assert "john-doe" in str(result)
        assert "2026-03-28" in str(result)


class TestWriteMedicalRecords:
    def test_creates_type_subdirectory(self, tmp_path: Path, sample_doc: SplitDocument):
        records_dir = tmp_path / "medical-records"
        doc_pdf = tmp_path / "doc.pdf"
        _make_dummy_pdf(doc_pdf)

        result = write_medical_records(
            doc_pdf,
            records_dir,
            person_folder="John_Doe",
            document_type="Radiology Report",
            filename="test.pdf",
        )

        assert result.exists()
        assert "Radiology Reports" in str(result) or "Radiology Report" in str(result)


class TestAppendIndexCsv:
    def test_creates_csv_with_headers(self, tmp_path: Path, sample_doc: SplitDocument):
        csv_path = tmp_path / "Index.csv"
        append_index_csv(csv_path, "test.pdf", sample_doc, scan_date="2026-03-28")

        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["Filename"] == "test.pdf"
        assert rows[0]["Date"] == "2025-06-15"
        assert rows[0]["Type"] == "Radiology Report"

    def test_appends_to_existing_csv(self, tmp_path: Path, sample_doc: SplitDocument):
        csv_path = tmp_path / "Index.csv"
        append_index_csv(csv_path, "doc1.pdf", sample_doc, scan_date="2026-03-28")
        append_index_csv(csv_path, "doc2.pdf", sample_doc, scan_date="2026-03-28")

        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
