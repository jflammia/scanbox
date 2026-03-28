"""Integration tests for document boundary editor API."""

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
async def batch_in_review(client: AsyncClient):
    """Create a batch in review state with documents."""
    person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
    session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
    batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

    db = get_db()
    await db.update_batch_state(batch["id"], "review")

    await db.create_document(
        batch_id=batch["id"],
        start_page=1,
        end_page=3,
        document_type="Radiology Report",
        filename="doc1.pdf",
    )
    await db.create_document(
        batch_id=batch["id"],
        start_page=4,
        end_page=5,
        document_type="Lab Results",
        filename="doc2.pdf",
    )
    return {"person": person, "session": session, "batch": batch}


class TestGetSplits:
    async def test_get_current_splits(self, batch_in_review, client: AsyncClient):
        batch_id = batch_in_review["batch"]["id"]
        resp = await client.get(f"/api/batches/{batch_id}/splits")
        assert resp.status_code == 200
        data = resp.json()
        assert "splits" in data
        assert len(data["splits"]) == 2
        assert data["splits"][0]["start_page"] == 1
        assert data["splits"][0]["end_page"] == 3
        assert data["splits"][1]["start_page"] == 4
        assert data["splits"][1]["end_page"] == 5
        assert data["total_pages"] == 5

    async def test_get_splits_nonexistent_batch(self, client: AsyncClient):
        resp = await client.get("/api/batches/nonexistent/splits")
        assert resp.status_code == 404


class TestUpdateSplits:
    async def test_update_splits(self, batch_in_review, client: AsyncClient):
        batch_id = batch_in_review["batch"]["id"]
        new_splits = [
            {"start_page": 1, "end_page": 2},
            {"start_page": 3, "end_page": 4},
            {"start_page": 5, "end_page": 5},
        ]
        resp = await client.post(f"/api/batches/{batch_id}/splits", json={"splits": new_splits})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["documents"]) == 3

    async def test_update_splits_wrong_state(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "X"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
        resp = await client.post(
            f"/api/batches/{batch['id']}/splits",
            json={"splits": [{"start_page": 1, "end_page": 1}]},
        )
        assert resp.status_code == 409

    async def test_update_splits_creates_new_documents(self, batch_in_review, client: AsyncClient):
        batch_id = batch_in_review["batch"]["id"]
        new_splits = [
            {"start_page": 1, "end_page": 1},
            {"start_page": 2, "end_page": 5},
        ]
        resp = await client.post(f"/api/batches/{batch_id}/splits", json={"splits": new_splits})
        assert resp.status_code == 200

        # Verify documents were recreated
        resp = await client.get(f"/api/batches/{batch_id}/documents")
        docs = resp.json()["items"]
        assert len(docs) == 2
        assert docs[0]["start_page"] == 1
        assert docs[0]["end_page"] == 1
        assert docs[1]["start_page"] == 2
        assert docs[1]["end_page"] == 5
