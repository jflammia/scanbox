"""End-to-end synthetic test: full workflow from person creation to save."""

from pathlib import Path

import pikepdf
import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app, get_db


def _make_dummy_pdf(path: Path, num_pages: int = 1) -> None:
    """Create a minimal valid PDF with the given number of pages."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.pages.append(
            pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, 612, 792]))
        )
    pdf.save(path)


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestFullWorkflow:
    """End-to-end test exercising the complete API workflow."""

    async def test_person_to_save_workflow(self, client: AsyncClient, tmp_path):
        # 1. Create a person
        resp = await client.post("/api/persons", json={"display_name": "Jane Smith"})
        assert resp.status_code == 201
        person = resp.json()
        assert person["display_name"] == "Jane Smith"
        assert person["id"] == "jane-smith"

        # 2. Verify person appears in list
        resp = await client.get("/api/persons")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

        # 3. Create a session
        resp = await client.post("/api/sessions", json={"person_id": person["id"]})
        assert resp.status_code == 201
        session = resp.json()
        assert session["person_id"] == person["id"]

        # 4. Create a batch
        resp = await client.post(f"/api/sessions/{session['id']}/batches")
        assert resp.status_code == 201
        batch = resp.json()
        assert batch["state"] == "scanning_fronts"
        assert batch["batch_num"] == 1

        # 5. Verify batch appears in session's batch list
        resp = await client.get(f"/api/sessions/{session['id']}/batches")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

        # 6. Simulate scanning + processing by advancing state and creating files
        db = get_db()
        await db.update_batch_state(batch["id"], "review")

        from scanbox.config import Config

        cfg = Config()
        batch_dir = cfg.INTERNAL_DATA_DIR / "sessions" / session["id"] / "batches" / batch["id"]
        docs_dir = batch_dir / "documents"
        _make_dummy_pdf(batch_dir / "combined.pdf", num_pages=5)

        # 7. Create document records (simulating AI splitting results)
        doc1 = await db.create_document(
            batch_id=batch["id"],
            start_page=1,
            end_page=3,
            document_type="Radiology Report",
            date_of_service="2025-08-10",
            facility="City Hospital",
            provider="Dr. Lee",
            description="MRI Brain",
            confidence=0.92,
            filename="2025-08-10_Jane-Smith_Radiology-Report.pdf",
        )
        doc2 = await db.create_document(
            batch_id=batch["id"],
            start_page=4,
            end_page=5,
            document_type="Lab Results",
            date_of_service="2025-07-22",
            facility="Quest Diagnostics",
            provider="unknown",
            description="Blood Panel",
            confidence=0.88,
            filename="2025-07-22_Jane-Smith_Lab-Results.pdf",
        )

        _make_dummy_pdf(docs_dir / doc1["filename"], num_pages=3)
        _make_dummy_pdf(docs_dir / doc2["filename"], num_pages=2)

        # 8. Verify documents via API
        resp = await client.get(f"/api/batches/{batch['id']}/documents")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        assert items[0]["document_type"] == "Radiology Report"
        assert items[1]["document_type"] == "Lab Results"

        # 9. Edit a document (user correction)
        resp = await client.put(
            f"/api/documents/{doc1['id']}",
            json={"description": "MRI Brain with Contrast"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "MRI Brain with Contrast"
        assert resp.json()["user_edited"] is True

        # 10. Verify batch state is review
        resp = await client.get(f"/api/batches/{batch['id']}")
        assert resp.status_code == 200
        assert resp.json()["state"] == "review"

        # 11. Save the batch
        resp = await client.post(f"/api/batches/{batch['id']}/save")
        assert resp.status_code == 200
        save_data = resp.json()
        assert save_data["status"] == "saved"
        assert "archive_path" in save_data
        assert len(save_data["medical_records"]) == 2

        # 12. Verify archive file exists on disk
        archive_path = Path(save_data["archive_path"])
        assert archive_path.exists()
        assert archive_path.suffix == ".pdf"

        # 13. Verify medical records files exist on disk
        for record_path_str in save_data["medical_records"]:
            record_path = Path(record_path_str)
            assert record_path.exists()
            assert record_path.suffix == ".pdf"

        # 14. Verify batch state is now saved
        resp = await client.get(f"/api/batches/{batch['id']}")
        assert resp.status_code == 200
        assert resp.json()["state"] == "saved"

        # 15. Verify output directory structure
        output_dir = tmp_path / "output"
        archive_dir = output_dir / "archive"
        records_dir = output_dir / "medical-records"
        assert archive_dir.exists()
        assert records_dir.exists()

        # Archive should have person-slug/date/ structure
        person_archive = list(archive_dir.glob("jane-smith/*/*.pdf"))
        assert len(person_archive) == 1

        # Medical records should have person/type/ structure
        person_records = list(records_dir.glob("Jane_Smith/**/*.pdf"))
        assert len(person_records) == 2

    async def test_save_wrong_state_rejected(self, client: AsyncClient):
        """Batch in scanning_fronts state cannot be saved."""
        person = (await client.post("/api/persons", json={"display_name": "Bob"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        resp = await client.post(f"/api/batches/{batch['id']}/save")
        assert resp.status_code == 409

    async def test_web_ui_accessible(self, client: AsyncClient):
        """Verify all UI pages return HTML."""
        # Home
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "ScanBox" in resp.text

        # Settings
        resp = await client.get("/settings")
        assert resp.status_code == 200
        assert "Settings" in resp.text

        # Static CSS
        resp = await client.get("/static/css/app.css")
        assert resp.status_code == 200

    async def test_multiple_batches_in_session(self, client: AsyncClient):
        """A session can have multiple batches with incrementing batch_num."""
        person = (await client.post("/api/persons", json={"display_name": "Multi"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()

        batch1 = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
        batch2 = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        assert batch1["batch_num"] == 1
        assert batch2["batch_num"] == 2

        resp = await client.get(f"/api/sessions/{session['id']}/batches")
        assert len(resp.json()["items"]) == 2

    async def test_health_endpoint(self, client: AsyncClient):
        """Health check returns ok."""
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert data["api"] == "ok"
        assert data["database"] == "ok"
