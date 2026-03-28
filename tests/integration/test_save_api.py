"""Integration tests for save (output) API endpoint."""

from pathlib import Path

import pikepdf
import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app, get_db


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


def _make_dummy_pdf(path: Path) -> None:
    """Create a minimal valid PDF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.Pdf.new()
    pdf.pages.append(
        pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, 612, 792]))
    )
    pdf.save(path)


@pytest.fixture
async def saveable_batch(client: AsyncClient, tmp_path):
    """Create a batch in review state with documents and files on disk."""
    person = (await client.post("/api/persons", json={"display_name": "John Doe"})).json()
    session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
    batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

    db = get_db()
    await db.update_batch_state(batch["id"], "review")

    # Create document records
    doc = await db.create_document(
        batch_id=batch["id"],
        start_page=1,
        end_page=2,
        document_type="Radiology Report",
        date_of_service="2025-06-15",
        facility="Memorial Hospital",
        provider="Dr. Chen",
        description="CT Abdomen",
        confidence=0.95,
        filename="2025-06-15_John-Doe_Radiology-Report.pdf",
    )

    # Create the batch directory and files on disk
    from scanbox.config import Config

    cfg = Config()
    batch_dir = cfg.INTERNAL_DATA_DIR / "sessions" / session["id"] / "batches" / batch["id"]
    docs_dir = batch_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    _make_dummy_pdf(batch_dir / "combined.pdf")
    _make_dummy_pdf(docs_dir / doc["filename"])

    return {"person": person, "session": session, "batch": batch, "doc": doc}


class TestSaveEndpoint:
    async def test_save_batch(self, saveable_batch, client: AsyncClient, tmp_path):
        batch_id = saveable_batch["batch"]["id"]
        resp = await client.post(f"/api/batches/{batch_id}/save")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "saved"
        assert "archive_path" in data
        assert "medical_records" in data
        assert isinstance(data["medical_records"], list)

    async def test_save_wrong_state(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
        resp = await client.post(f"/api/batches/{batch['id']}/save")
        assert resp.status_code == 409

    async def test_save_updates_state(self, saveable_batch, client: AsyncClient):
        batch_id = saveable_batch["batch"]["id"]
        await client.post(f"/api/batches/{batch_id}/save")
        resp = await client.get(f"/api/batches/{batch_id}")
        assert resp.json()["state"] == "saved"
