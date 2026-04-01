"""Tests for session and batch deletion — database, API, and filesystem cleanup."""

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.database import Database
from scanbox.main import app


@pytest.fixture
async def db(tmp_path):
    """Create a fresh database for each test."""
    database = Database(tmp_path / "test.db")
    await database.init()
    yield database
    await database.close()


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


class TestDeleteBatchDB:
    async def test_delete_batch_removes_batch_and_documents(self, db: Database):
        person = await db.create_person("John Doe")
        session = await db.create_session(person["id"])
        batch = await db.create_batch(session["id"])
        await db.create_document(batch_id=batch["id"], start_page=1, end_page=2, filename="a.pdf")
        await db.create_document(batch_id=batch["id"], start_page=3, end_page=4, filename="b.pdf")

        result = await db.delete_batch(batch["id"])
        assert result is True
        assert await db.get_batch(batch["id"]) is None
        assert await db.list_documents(batch["id"]) == []

    async def test_delete_nonexistent_batch_returns_false(self, db: Database):
        result = await db.delete_batch("nonexistent")
        assert result is False

    async def test_delete_batch_leaves_other_batches(self, db: Database):
        person = await db.create_person("John Doe")
        session = await db.create_session(person["id"])
        batch1 = await db.create_batch(session["id"])
        batch2 = await db.create_batch(session["id"])

        await db.delete_batch(batch1["id"])
        assert await db.get_batch(batch1["id"]) is None
        assert await db.get_batch(batch2["id"]) is not None


class TestDeleteSessionDB:
    async def test_delete_session_removes_session_batches_and_documents(self, db: Database):
        person = await db.create_person("John Doe")
        session = await db.create_session(person["id"])
        batch = await db.create_batch(session["id"])
        await db.create_document(batch_id=batch["id"], start_page=1, end_page=1, filename="a.pdf")

        result = await db.delete_session(session["id"])
        assert result is True
        assert await db.get_session(session["id"]) is None
        assert await db.get_batch(batch["id"]) is None
        assert await db.list_documents(batch["id"]) == []

    async def test_delete_session_with_multiple_batches(self, db: Database):
        person = await db.create_person("John Doe")
        session = await db.create_session(person["id"])
        b1 = await db.create_batch(session["id"])
        b2 = await db.create_batch(session["id"])
        await db.create_document(batch_id=b1["id"], start_page=1, end_page=1, filename="a.pdf")
        await db.create_document(batch_id=b2["id"], start_page=1, end_page=1, filename="b.pdf")

        result = await db.delete_session(session["id"])
        assert result is True
        assert await db.get_batch(b1["id"]) is None
        assert await db.get_batch(b2["id"]) is None

    async def test_delete_nonexistent_session_returns_false(self, db: Database):
        result = await db.delete_session("nonexistent")
        assert result is False

    async def test_delete_session_leaves_other_sessions(self, db: Database):
        person = await db.create_person("John Doe")
        s1 = await db.create_session(person["id"])
        s2 = await db.create_session(person["id"])

        await db.delete_session(s1["id"])
        assert await db.get_session(s1["id"]) is None
        assert await db.get_session(s2["id"]) is not None


class TestDeleteSessionAPI:
    async def test_delete_session(self, client: AsyncClient):
        person = await client.post("/api/persons", json={"display_name": "John"})
        person_id = person.json()["id"]
        session = await client.post("/api/sessions", json={"person_id": person_id})
        session_id = session.json()["id"]

        resp = await client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 204

        # Verify session is gone
        resp = await client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 404

    async def test_delete_session_not_found(self, client: AsyncClient):
        resp = await client.delete("/api/sessions/nonexistent")
        assert resp.status_code == 404

    async def test_delete_session_cleans_up_files(self, client: AsyncClient, tmp_path):
        person = await client.post("/api/persons", json={"display_name": "John"})
        person_id = person.json()["id"]
        session = await client.post("/api/sessions", json={"person_id": person_id})
        session_id = session.json()["id"]

        # Create session directory with some files
        session_dir = tmp_path / "data" / "sessions" / session_id
        session_dir.mkdir(parents=True)
        (session_dir / "dummy.txt").write_text("test")

        resp = await client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 204
        assert not session_dir.exists()


class TestDeleteBatchAPI:
    async def test_delete_batch(self, client: AsyncClient):
        person = await client.post("/api/persons", json={"display_name": "John"})
        person_id = person.json()["id"]
        session = await client.post("/api/sessions", json={"person_id": person_id})
        session_id = session.json()["id"]
        batch = await client.post(f"/api/sessions/{session_id}/batches")
        batch_id = batch.json()["id"]

        resp = await client.delete(f"/api/batches/{batch_id}")
        assert resp.status_code == 204

        # Verify batch is gone
        resp = await client.get(f"/api/batches/{batch_id}")
        assert resp.status_code == 404

    async def test_delete_batch_not_found(self, client: AsyncClient):
        resp = await client.delete("/api/batches/nonexistent")
        assert resp.status_code == 404

    async def test_delete_batch_cleans_up_files(self, client: AsyncClient, tmp_path):
        person = await client.post("/api/persons", json={"display_name": "John"})
        person_id = person.json()["id"]
        session = await client.post("/api/sessions", json={"person_id": person_id})
        session_id = session.json()["id"]
        batch = await client.post(f"/api/sessions/{session_id}/batches")
        batch_id = batch.json()["id"]

        # Create batch directory with some files
        batch_dir = tmp_path / "data" / "sessions" / session_id / "batches" / batch_id
        batch_dir.mkdir(parents=True)
        (batch_dir / "state.json").write_text("{}")
        (batch_dir / "fronts.pdf").write_bytes(b"fake pdf")

        resp = await client.delete(f"/api/batches/{batch_id}")
        assert resp.status_code == 204
        assert not batch_dir.exists()
