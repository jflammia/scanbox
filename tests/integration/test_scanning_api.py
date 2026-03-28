"""Integration tests for batch and scanning API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app


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
async def session_with_batch(client: AsyncClient):
    """Create a person, session, and batch for testing."""
    person = (await client.post("/api/persons", json={"display_name": "John Doe"})).json()
    session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
    batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
    return {"person": person, "session": session, "batch": batch}


class TestBatchCRUD:
    async def test_create_batch(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        resp = await client.post(f"/api/sessions/{session['id']}/batches")
        assert resp.status_code == 201
        data = resp.json()
        assert data["session_id"] == session["id"]
        assert data["state"] == "scanning_fronts"
        assert data["batch_num"] == 1

    async def test_get_batch(self, session_with_batch, client: AsyncClient):
        batch_id = session_with_batch["batch"]["id"]
        resp = await client.get(f"/api/batches/{batch_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == batch_id

    async def test_get_nonexistent_batch(self, client: AsyncClient):
        resp = await client.get("/api/batches/nonexistent")
        assert resp.status_code == 404

    async def test_list_batches(self, session_with_batch, client: AsyncClient):
        session_id = session_with_batch["session"]["id"]
        # Create a second batch
        await client.post(f"/api/sessions/{session_id}/batches")
        resp = await client.get(f"/api/sessions/{session_id}/batches")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    async def test_batch_num_increments(self, session_with_batch, client: AsyncClient):
        session_id = session_with_batch["session"]["id"]
        resp = await client.post(f"/api/sessions/{session_id}/batches")
        assert resp.json()["batch_num"] == 2


class TestSkipBacks:
    async def test_skip_backs(self, session_with_batch, client: AsyncClient):
        batch_id = session_with_batch["batch"]["id"]
        # First transition to fronts_done
        from scanbox.main import get_db

        db = get_db()
        await db.update_batch_state(batch_id, "fronts_done")

        resp = await client.post(f"/api/batches/{batch_id}/skip-backs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "backs_skipped"

    async def test_skip_backs_wrong_state(self, session_with_batch, client: AsyncClient):
        batch_id = session_with_batch["batch"]["id"]
        # Batch is in scanning_fronts, can't skip backs
        resp = await client.post(f"/api/batches/{batch_id}/skip-backs")
        assert resp.status_code == 409


class TestScanTrigger:
    async def test_scan_fronts_no_scanner(self, session_with_batch, client: AsyncClient):
        """Without a scanner configured, scan-fronts returns 503."""
        batch_id = session_with_batch["batch"]["id"]
        resp = await client.post(f"/api/batches/{batch_id}/scan/fronts")
        assert resp.status_code == 503

    async def test_scan_backs_no_scanner(self, session_with_batch, client: AsyncClient):
        """Without a scanner configured, scan-backs returns 503."""
        batch_id = session_with_batch["batch"]["id"]
        from scanbox.main import get_db

        db = get_db()
        await db.update_batch_state(batch_id, "fronts_done")
        resp = await client.post(f"/api/batches/{batch_id}/scan/backs")
        assert resp.status_code == 503
