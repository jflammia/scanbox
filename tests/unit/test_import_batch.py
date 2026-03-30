"""Tests for the shared import_batch function."""

from io import BytesIO

import pikepdf
import pytest

from scanbox.api.import_batch import ImportResult, import_batch
from scanbox.database import Database


def _make_pdf_bytes(num_pages: int = 3) -> bytes:
    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.add_blank_page(page_size=(612, 792))
    buf = BytesIO()
    pdf.save(buf)
    return buf.getvalue()


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.init()
    yield database
    await database.close()


class TestImportBatch:
    async def test_returns_import_result(self, db, tmp_path):
        fronts = _make_pdf_bytes(3)
        result = await import_batch(db, tmp_path, fronts)
        assert isinstance(result, ImportResult)
        assert result.batch_id.startswith("batch-")
        assert result.session_id.startswith("sess-")
        assert result.fronts_page_count == 3
        assert result.backs_page_count is None
        assert result.has_backs is False

    async def test_creates_person_session_batch(self, db, tmp_path):
        fronts = _make_pdf_bytes(2)
        result = await import_batch(db, tmp_path, fronts, person_name="Elena Martinez")
        person = await db.get_person(result.person_id)
        assert person is not None
        assert person["display_name"] == "Elena Martinez"
        session = await db.get_session(result.session_id)
        assert session is not None
        batch = await db.get_batch(result.batch_id)
        assert batch is not None
        assert batch["state"] == "backs_skipped"

    async def test_with_backs(self, db, tmp_path):
        fronts = _make_pdf_bytes(5)
        backs = _make_pdf_bytes(5)
        result = await import_batch(db, tmp_path, fronts, backs_bytes=backs)
        assert result.has_backs is True
        assert result.fronts_page_count == 5
        assert result.backs_page_count == 5
        batch = await db.get_batch(result.batch_id)
        assert batch["state"] == "backs_done"

    async def test_writes_pdfs_to_batch_dir(self, db, tmp_path):
        fronts = _make_pdf_bytes(3)
        backs = _make_pdf_bytes(3)
        result = await import_batch(db, tmp_path, fronts, backs_bytes=backs)
        assert (result.batch_dir / "fronts.pdf").exists()
        assert (result.batch_dir / "backs.pdf").exists()

    async def test_fronts_only_no_backs_file(self, db, tmp_path):
        fronts = _make_pdf_bytes(2)
        result = await import_batch(db, tmp_path, fronts)
        assert (result.batch_dir / "fronts.pdf").exists()
        assert not (result.batch_dir / "backs.pdf").exists()

    async def test_default_person_name(self, db, tmp_path):
        fronts = _make_pdf_bytes(1)
        result = await import_batch(db, tmp_path, fronts)
        person = await db.get_person(result.person_id)
        assert person["display_name"] == "Test Patient"

    async def test_reuses_existing_person(self, db, tmp_path):
        fronts = _make_pdf_bytes(1)
        r1 = await import_batch(db, tmp_path, fronts, person_name="John Doe")
        r2 = await import_batch(db, tmp_path, fronts, person_name="John Doe")
        assert r1.person_id == r2.person_id
        assert r1.session_id != r2.session_id

    async def test_page_counts_in_db(self, db, tmp_path):
        fronts = _make_pdf_bytes(7)
        backs = _make_pdf_bytes(7)
        result = await import_batch(db, tmp_path, fronts, backs_bytes=backs)
        batch = await db.get_batch(result.batch_id)
        assert batch["fronts_page_count"] == 7
        assert batch["backs_page_count"] == 7
