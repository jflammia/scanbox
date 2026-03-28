"""Integration tests for document content endpoints (PDF, text, thumbnail)."""

import json

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


@pytest.fixture
async def doc_with_files(client: AsyncClient, tmp_path):
    """Create a batch with a document that has files on disk."""
    person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
    session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
    batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

    db = get_db()
    await db.update_batch_state(batch["id"], "review")

    # Create document record
    doc = await db.create_document(
        batch_id=batch["id"],
        start_page=1,
        end_page=2,
        document_type="Lab Results",
        filename="test-doc.pdf",
    )

    # Create the file on disk
    data_dir = tmp_path / "data"
    batch_dir = data_dir / "sessions" / session["id"] / "batches" / batch["id"]
    docs_dir = batch_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Create a minimal PDF
    import pikepdf

    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    pdf.add_blank_page(page_size=(612, 792))
    pdf.save(str(docs_dir / "test-doc.pdf"))

    # Also save as combined.pdf for page thumbnails
    pdf.save(str(batch_dir / "combined.pdf"))

    # Create text_by_page.json
    text_data = {"1": "Page one text", "2": "Page two text", "3": "Not in this doc"}
    (batch_dir / "text_by_page.json").write_text(json.dumps(text_data))

    return {"doc": doc, "batch": batch, "session": session, "batch_dir": batch_dir}


class TestDocumentPdf:
    async def test_get_pdf(self, doc_with_files, client: AsyncClient):
        doc_id = doc_with_files["doc"]["id"]
        resp = await client.get(f"/api/documents/{doc_id}/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert len(resp.content) > 0

    async def test_get_pdf_not_found(self, client: AsyncClient):
        resp = await client.get("/api/documents/nonexistent/pdf")
        assert resp.status_code == 404


class TestDocumentText:
    async def test_get_text(self, doc_with_files, client: AsyncClient):
        doc_id = doc_with_files["doc"]["id"]
        resp = await client.get(f"/api/documents/{doc_id}/text")
        assert resp.status_code == 200
        data = resp.json()
        assert "pages" in data
        assert len(data["pages"]) == 2
        assert data["pages"][0]["page"] == 1
        assert data["pages"][0]["text"] == "Page one text"
        assert data["pages"][1]["page"] == 2
        assert data["pages"][1]["text"] == "Page two text"

    async def test_get_text_not_found(self, client: AsyncClient):
        resp = await client.get("/api/documents/nonexistent/text")
        assert resp.status_code == 404


class TestDocumentThumbnail:
    async def test_get_thumbnail_not_found(self, client: AsyncClient):
        resp = await client.get("/api/documents/nonexistent/thumbnail")
        assert resp.status_code == 404


class TestPageThumbnail:
    async def test_page_thumbnail_batch_not_found(self, client: AsyncClient):
        resp = await client.get("/api/batches/nonexistent/pages/1/thumbnail")
        assert resp.status_code == 404


class TestReprocessBatch:
    async def test_reprocess_wrong_state(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "R"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
        # Batch is in scanning_fronts state
        resp = await client.post(f"/api/batches/{batch['id']}/reprocess")
        assert resp.status_code == 409

    async def test_reprocess_not_found(self, client: AsyncClient):
        resp = await client.post("/api/batches/nonexistent/reprocess")
        assert resp.status_code == 404


class TestHealthEndpoint:
    async def test_health_enriched(self, client: AsyncClient):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert data["api"] == "ok"
        assert data["database"] == "ok"
        assert "scanner" in data
        assert "storage" in data
        assert "llm" in data
        assert "paperless" in data
