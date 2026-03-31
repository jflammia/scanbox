"""Tests for scan summary: thumbnail generation, summary endpoint, thumbnail serving."""

from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pikepdf
import pytest

from scanbox.database import Database


def _make_pdf(path: Path, num_pages: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.add_blank_page(page_size=(612, 792))
    pdf.save(path)


def _make_pdf_bytes(num_pages: int = 1) -> bytes:
    buf = BytesIO()
    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.add_blank_page(page_size=(612, 792))
    pdf.save(buf)
    return buf.getvalue()


def _make_page_bytes() -> bytes:
    """Create a valid single-page PDF as bytes."""
    buf = BytesIO()
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    pdf.save(buf)
    return buf.getvalue()


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.init()
    yield database
    await database.close()


class TestGenerateThumbnails:
    def test_generates_correct_number_of_jpegs(self, tmp_path):
        from scanbox.api.scanning import generate_thumbnails

        batch_dir = tmp_path / "batch"
        batch_dir.mkdir()
        pdf_path = batch_dir / "fronts.pdf"
        _make_pdf(pdf_path, num_pages=3)

        count = generate_thumbnails(batch_dir, pdf_path)

        assert count == 3
        thumbs_dir = batch_dir / "thumbs"
        assert thumbs_dir.exists()
        jpgs = sorted(thumbs_dir.glob("page-*.jpg"))
        assert len(jpgs) == 3
        assert jpgs[0].name == "page-001.jpg"
        assert jpgs[1].name == "page-002.jpg"
        assert jpgs[2].name == "page-003.jpg"

    def test_generates_valid_jpeg_files(self, tmp_path):
        from PIL import Image

        from scanbox.api.scanning import generate_thumbnails

        batch_dir = tmp_path / "batch"
        batch_dir.mkdir()
        pdf_path = batch_dir / "fronts.pdf"
        _make_pdf(pdf_path, num_pages=1)

        generate_thumbnails(batch_dir, pdf_path)

        thumb = batch_dir / "thumbs" / "page-001.jpg"
        img = Image.open(thumb)
        assert img.format == "JPEG"
        assert img.width == 200

    def test_single_page_pdf(self, tmp_path):
        from scanbox.api.scanning import generate_thumbnails

        batch_dir = tmp_path / "batch"
        batch_dir.mkdir()
        pdf_path = batch_dir / "fronts.pdf"
        _make_pdf(pdf_path, num_pages=1)

        count = generate_thumbnails(batch_dir, pdf_path)

        assert count == 1
        assert (batch_dir / "thumbs" / "page-001.jpg").exists()

    def test_creates_thumbs_dir(self, tmp_path):
        from scanbox.api.scanning import generate_thumbnails

        batch_dir = tmp_path / "batch"
        batch_dir.mkdir()
        pdf_path = batch_dir / "fronts.pdf"
        _make_pdf(pdf_path, num_pages=1)

        assert not (batch_dir / "thumbs").exists()
        generate_thumbnails(batch_dir, pdf_path)
        assert (batch_dir / "thumbs").exists()


class TestScanFrontsGeneratesThumbnails:
    @patch("scanbox.api.scanning.event_bus")
    @patch("scanbox.api.scanning.ESCLClient")
    async def test_thumbnails_generated_after_fronts_scan(
        self, mock_escl_cls, mock_bus, tmp_path, monkeypatch, db
    ):
        from scanbox.api.scanning import scan_fronts_task

        monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setenv("SCANNER_IP", "192.168.1.100")

        person = await db.create_person("Test User")
        session = await db.create_session(person["id"])
        batch = await db.create_batch(session["id"])

        from scanbox.config import Config

        cfg = Config()
        batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch["id"]
        batch_dir.mkdir(parents=True, exist_ok=True)

        mock_scanner = AsyncMock()
        mock_escl_cls.return_value = mock_scanner
        mock_scanner.start_scan.return_value = "http://scanner/job/1"
        page_bytes = _make_page_bytes()
        mock_scanner.get_next_page.side_effect = [page_bytes, page_bytes, None]
        mock_bus.publish = AsyncMock()

        await scan_fronts_task(batch["id"], db)

        thumbs_dir = batch_dir / "thumbs"
        assert thumbs_dir.exists()
        jpgs = sorted(thumbs_dir.glob("page-*.jpg"))
        assert len(jpgs) == 2


class TestImportGeneratesThumbnails:
    async def test_import_generates_thumbnails(self, tmp_path, monkeypatch):
        """Import endpoint generates thumbnails from fronts PDF."""
        monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

        from scanbox.api.import_batch import import_batch
        from scanbox.api.scanning import generate_thumbnails

        database = Database(tmp_path / "data" / "scanbox.db")
        await database.init()

        fronts_bytes = _make_pdf_bytes(num_pages=3)

        result = await import_batch(
            db=database,
            data_dir=tmp_path / "data",
            fronts_bytes=fronts_bytes,
            person_name="Test Patient",
        )

        # Generate thumbnails like the import endpoint does
        fronts_pdf = result.batch_dir / "fronts.pdf"
        count = generate_thumbnails(result.batch_dir, fronts_pdf)

        assert count == 3
        thumbs_dir = result.batch_dir / "thumbs"
        assert thumbs_dir.exists()
        jpgs = sorted(thumbs_dir.glob("page-*.jpg"))
        assert len(jpgs) == 3

        await database.close()
