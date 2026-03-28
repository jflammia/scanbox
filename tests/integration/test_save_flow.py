"""Integration tests for the complete save flow.

Verifies that saving a batch writes archive, medical records,
Index.csv, and optionally uploads to PaperlessNGX.
"""

import csv

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
async def review_batch(client, tmp_path):
    """Create a batch in 'review' state with a fake document on disk."""
    from scanbox.main import get_db

    db = get_db()
    person = await db.create_person("Jane Doe")
    session = await db.create_session(person["id"])
    batch = await db.create_batch(session["id"])

    # Create batch directory with a fake combined PDF and document
    data_dir = tmp_path / "data"
    batch_dir = data_dir / "sessions" / session["id"] / "batches" / batch["id"]
    docs_dir = batch_dir / "documents"
    docs_dir.mkdir(parents=True)

    # Create minimal valid PDFs using pikepdf
    import pikepdf

    combined_pdf = batch_dir / "combined.pdf"
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page()
    pdf.save(combined_pdf)

    doc_filename = "2025-06-15_Jane-Doe_Lab-Results.pdf"
    doc_pdf = docs_dir / doc_filename
    pdf.save(doc_pdf)

    # Create document record in DB
    await db.create_document(
        batch_id=batch["id"],
        start_page=1,
        end_page=1,
        document_type="Lab Results",
        date_of_service="2025-06-15",
        facility="Memorial Hospital",
        provider="Dr. Smith",
        description="Blood Work Panel",
        filename=doc_filename,
    )

    # Transition to review state
    await db.update_batch_state(batch["id"], "review")

    return {
        "batch_id": batch["id"],
        "session_id": session["id"],
        "person": person,
        "batch_dir": batch_dir,
    }


class TestSaveWritesAllOutputs:
    """Save should write archive, medical records, and Index.csv."""

    async def test_save_creates_archive(self, client, review_batch, tmp_path):
        resp = await client.post(f"/api/batches/{review_batch['batch_id']}/save")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "saved"
        assert "archive_path" in data
        # Archive file should exist
        from pathlib import Path

        assert Path(data["archive_path"]).exists()

    async def test_save_creates_medical_records(self, client, review_batch, tmp_path):
        resp = await client.post(f"/api/batches/{review_batch['batch_id']}/save")
        data = resp.json()
        assert len(data["medical_records"]) == 1
        from pathlib import Path

        assert Path(data["medical_records"][0]).exists()

    async def test_save_writes_index_csv(self, client, review_batch, tmp_path):
        resp = await client.post(f"/api/batches/{review_batch['batch_id']}/save")
        assert resp.status_code == 200

        # Index.csv should exist in person's medical records folder
        output_dir = tmp_path / "output"
        person_folder = review_batch["person"]["folder_name"]
        index_csv = output_dir / "medical-records" / person_folder / "Index.csv"
        assert index_csv.exists()

        with open(index_csv) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["Type"] == "Lab Results"
        assert rows[0]["Date"] == "2025-06-15"
        assert rows[0]["Facility"] == "Memorial Hospital"

    async def test_save_transitions_to_saved(self, client, review_batch):
        await client.post(f"/api/batches/{review_batch['batch_id']}/save")

        resp = await client.get(f"/api/batches/{review_batch['batch_id']}")
        assert resp.json()["state"] == "saved"


class TestSaveHtmlRoute:
    """HTML save route returns template response."""

    async def test_html_save_returns_success(self, client, review_batch):
        resp = await client.post(f"/batches/{review_batch['batch_id']}/save")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "saved" in resp.text.lower() or "1" in resp.text


class TestSkipBacksTriggersProcessing:
    """HTML skip-backs route should trigger pipeline processing."""

    async def test_html_skip_backs_returns_html(self, client, tmp_path):
        from scanbox.main import get_db

        db = get_db()
        person = await db.create_person("Test")
        session = await db.create_session(person["id"])
        batch = await db.create_batch(session["id"])
        await db.update_batch_state(batch["id"], "fronts_done")

        resp = await client.post(f"/batches/{batch['id']}/skip-backs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
