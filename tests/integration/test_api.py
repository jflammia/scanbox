"""Integration tests for FastAPI app — persons and sessions endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    """Create a test client with a temporary database."""
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    # Re-import to pick up env changes
    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestHealth:
    async def test_health_endpoint(self, client: AsyncClient):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_health_includes_version(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("APP_VERSION", "20260331-abc1234")
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["version"] == "20260331-abc1234"

    async def test_health_version_defaults_to_dev(self, client: AsyncClient, monkeypatch):
        monkeypatch.delenv("APP_VERSION", raising=False)
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["version"] == "dev"


class TestPersonsAPI:
    async def test_create_person(self, client: AsyncClient):
        resp = await client.post("/api/persons", json={"display_name": "John Doe"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "john-doe"
        assert data["display_name"] == "John Doe"
        assert data["folder_name"] == "John_Doe"

    async def test_list_persons(self, client: AsyncClient):
        await client.post("/api/persons", json={"display_name": "Alice"})
        await client.post("/api/persons", json={"display_name": "Bob"})
        resp = await client.get("/api/persons")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    async def test_get_person(self, client: AsyncClient):
        create_resp = await client.post("/api/persons", json={"display_name": "Jane"})
        person_id = create_resp.json()["id"]
        resp = await client.get(f"/api/persons/{person_id}")
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Jane"

    async def test_get_nonexistent_person(self, client: AsyncClient):
        resp = await client.get("/api/persons/nonexistent")
        assert resp.status_code == 404

    async def test_update_person(self, client: AsyncClient):
        create_resp = await client.post("/api/persons", json={"display_name": "Old"})
        person_id = create_resp.json()["id"]
        resp = await client.put(f"/api/persons/{person_id}", json={"display_name": "New"})
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "New"

    async def test_delete_person(self, client: AsyncClient):
        create_resp = await client.post("/api/persons", json={"display_name": "Delete Me"})
        person_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/persons/{person_id}")
        assert resp.status_code == 204

    async def test_delete_person_with_sessions(self, client: AsyncClient):
        create_resp = await client.post("/api/persons", json={"display_name": "Has Sess"})
        person_id = create_resp.json()["id"]
        await client.post("/api/sessions", json={"person_id": person_id})
        resp = await client.delete(f"/api/persons/{person_id}")
        assert resp.status_code == 409


class TestSessionsAPI:
    async def test_create_session(self, client: AsyncClient):
        person_resp = await client.post("/api/persons", json={"display_name": "John"})
        person_id = person_resp.json()["id"]
        resp = await client.post("/api/sessions", json={"person_id": person_id})
        assert resp.status_code == 201
        data = resp.json()
        assert data["person_id"] == person_id

    async def test_list_sessions(self, client: AsyncClient):
        person_resp = await client.post("/api/persons", json={"display_name": "John"})
        person_id = person_resp.json()["id"]
        await client.post("/api/sessions", json={"person_id": person_id})
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

    async def test_list_sessions_filter_by_person(self, client: AsyncClient):
        p1 = (await client.post("/api/persons", json={"display_name": "A"})).json()["id"]
        p2 = (await client.post("/api/persons", json={"display_name": "B"})).json()["id"]
        await client.post("/api/sessions", json={"person_id": p1})
        await client.post("/api/sessions", json={"person_id": p2})
        resp = await client.get(f"/api/sessions?person_id={p1}")
        assert len(resp.json()["items"]) == 1

    async def test_get_session(self, client: AsyncClient):
        person_resp = await client.post("/api/persons", json={"display_name": "John"})
        person_id = person_resp.json()["id"]
        sess_resp = await client.post("/api/sessions", json={"person_id": person_id})
        session_id = sess_resp.json()["id"]
        resp = await client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200

    async def test_create_session_invalid_person(self, client: AsyncClient):
        resp = await client.post("/api/sessions", json={"person_id": "nonexistent"})
        assert resp.status_code == 404
