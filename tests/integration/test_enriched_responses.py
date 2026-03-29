"""Tests for enriched API responses — document counts, batch summaries, etc."""

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def _create_person_session_batch(client):
    """Helper: create person → session → batch, return IDs."""
    person = (await client.post("/api/persons", json={"display_name": "Test User"})).json()
    session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
    batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
    return person, session, batch


class TestBatchDocumentCount:
    async def test_batch_includes_document_count(self, client):
        _, _, batch = await _create_person_session_batch(client)

        resp = await client.get(f"/api/batches/{batch['id']}")
        data = resp.json()
        assert "document_count" in data
        assert data["document_count"] == 0

    async def test_batch_document_count_after_creating_docs(self, client):
        _, _, batch = await _create_person_session_batch(client)
        batch_id = batch["id"]

        # Create documents directly via the database
        from scanbox.main import get_db

        db = get_db()
        await db.create_document(batch_id, 1, 2, "doc1.pdf", document_type="Lab Results")
        await db.create_document(batch_id, 3, 3, "doc2.pdf", document_type="Letter")

        resp = await client.get(f"/api/batches/{batch_id}")
        assert resp.json()["document_count"] == 2


class TestDocumentListEnriched:
    async def test_list_documents_includes_total(self, client):
        _, _, batch = await _create_person_session_batch(client)
        batch_id = batch["id"]

        from scanbox.main import get_db

        db = get_db()
        await db.create_document(batch_id, 1, 2, "doc1.pdf", confidence=0.95)
        await db.create_document(batch_id, 3, 3, "doc2.pdf", confidence=0.3)
        await db.create_document(batch_id, 4, 5, "doc3.pdf", confidence=0.85)

        resp = await client.get(f"/api/batches/{batch_id}/documents")
        data = resp.json()
        assert data["total"] == 3

    async def test_list_documents_includes_needs_review(self, client):
        _, _, batch = await _create_person_session_batch(client)
        batch_id = batch["id"]

        from scanbox.main import get_db

        db = get_db()
        await db.create_document(batch_id, 1, 2, "doc1.pdf", confidence=0.95)
        await db.create_document(batch_id, 3, 3, "doc2.pdf", confidence=0.3)

        resp = await client.get(f"/api/batches/{batch_id}/documents")
        data = resp.json()
        # confidence < 0.7 counts as needs_review
        assert data["needs_review"] == 1

    async def test_list_documents_empty(self, client):
        _, _, batch = await _create_person_session_batch(client)
        resp = await client.get(f"/api/batches/{batch['id']}/documents")
        data = resp.json()
        assert data["total"] == 0
        assert data["needs_review"] == 0


class TestSessionEnriched:
    async def test_list_sessions_includes_person_name(self, client):
        person = (await client.post("/api/persons", json={"display_name": "Jane Doe"})).json()
        await client.post("/api/sessions", json={"person_id": person["id"]})

        resp = await client.get("/api/sessions")
        data = resp.json()
        assert data["items"][0]["person_name"] == "Jane Doe"

    async def test_list_sessions_includes_batch_count(self, client):
        person = (await client.post("/api/persons", json={"display_name": "Jane"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()

        await client.post(f"/api/sessions/{session['id']}/batches")
        await client.post(f"/api/sessions/{session['id']}/batches")

        resp = await client.get("/api/sessions")
        data = resp.json()
        assert data["items"][0]["batch_count"] == 2

    async def test_list_sessions_includes_document_count(self, client):
        person = (await client.post("/api/persons", json={"display_name": "Jane"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        from scanbox.main import get_db

        db = get_db()
        await db.create_document(batch["id"], 1, 2, "d1.pdf")
        await db.create_document(batch["id"], 3, 3, "d2.pdf")
        await db.create_document(batch["id"], 4, 5, "d3.pdf")

        resp = await client.get("/api/sessions")
        data = resp.json()
        assert data["items"][0]["document_count"] == 3

    async def test_get_session_includes_batches(self, client):
        person = (await client.post("/api/persons", json={"display_name": "Jane"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()

        await client.post(f"/api/sessions/{session['id']}/batches")
        await client.post(f"/api/sessions/{session['id']}/batches")

        resp = await client.get(f"/api/sessions/{session['id']}")
        data = resp.json()
        assert "batches" in data
        assert len(data["batches"]) == 2

    async def test_get_session_includes_person_name(self, client):
        person = (await client.post("/api/persons", json={"display_name": "Jane Doe"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()

        resp = await client.get(f"/api/sessions/{session['id']}")
        data = resp.json()
        assert data["person_name"] == "Jane Doe"
