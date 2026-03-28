"""Integration tests for document API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app, get_db


@pytest.fixture
async def client(tmp_path, monkeypatch):
    """Create a test client with a temporary database."""
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
async def batch_with_docs(client: AsyncClient):
    """Create a person, session, batch, and documents for testing."""
    person = (await client.post("/api/persons", json={"display_name": "John Doe"})).json()
    session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
    batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

    db = get_db()
    doc1 = await db.create_document(
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
    doc2 = await db.create_document(
        batch_id=batch["id"],
        start_page=3,
        end_page=3,
        document_type="Lab Results",
        date_of_service="2025-05-22",
        facility="Quest",
        provider="unknown",
        description="Blood Work",
        confidence=0.85,
        filename="2025-05-22_John-Doe_Lab-Results.pdf",
    )
    return {"person": person, "session": session, "batch": batch, "docs": [doc1, doc2]}


class TestListDocuments:
    async def test_list_documents(self, batch_with_docs, client: AsyncClient):
        batch_id = batch_with_docs["batch"]["id"]
        resp = await client.get(f"/api/batches/{batch_id}/documents")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        assert items[0]["start_page"] == 1  # Ordered by start_page

    async def test_list_empty_batch(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
        resp = await client.get(f"/api/batches/{batch['id']}/documents")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 0


class TestGetDocument:
    async def test_get_document(self, batch_with_docs, client: AsyncClient):
        doc_id = batch_with_docs["docs"][0]["id"]
        resp = await client.get(f"/api/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["document_type"] == "Radiology Report"

    async def test_get_nonexistent(self, client: AsyncClient):
        resp = await client.get("/api/documents/nonexistent")
        assert resp.status_code == 404


class TestUpdateDocument:
    async def test_update_metadata(self, batch_with_docs, client: AsyncClient):
        doc_id = batch_with_docs["docs"][0]["id"]
        resp = await client.put(
            f"/api/documents/{doc_id}",
            json={
                "document_type": "Discharge Summary",
                "description": "Post-Surgery",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_type"] == "Discharge Summary"
        assert data["description"] == "Post-Surgery"
        assert data["user_edited"] is True

    async def test_partial_update(self, batch_with_docs, client: AsyncClient):
        doc_id = batch_with_docs["docs"][1]["id"]
        resp = await client.put(
            f"/api/documents/{doc_id}",
            json={"facility": "LabCorp"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["facility"] == "LabCorp"
        # Other fields unchanged
        assert data["document_type"] == "Lab Results"
