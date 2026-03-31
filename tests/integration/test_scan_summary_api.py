"""Integration tests for scan summary and thumbnail API endpoints."""

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
async def batch_with_thumbs(client, tmp_path, monkeypatch):
    """Create a person, session, batch, and pre-generated thumbnails."""
    from scanbox.config import Config
    from scanbox.main import get_db

    db = get_db()

    person = (await client.post("/api/persons", json={"display_name": "Test User"})).json()
    session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
    batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

    await db.update_batch_state(batch["id"], "fronts_done", fronts_page_count=3)

    cfg = Config()
    batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch["id"]
    thumbs_dir = batch_dir / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    # Write minimal JPEG-like files
    for i in range(1, 4):
        (thumbs_dir / f"page-{i:03d}.jpg").write_bytes(b"\xff\xd8\xff\xe0JFIF")

    return {"person": person, "session": session, "batch": batch}


class TestScanSummaryEndpoint:
    async def test_returns_thumbnails(self, client, batch_with_thumbs):
        batch_id = batch_with_thumbs["batch"]["id"]
        resp = await client.get(f"/api/batches/{batch_id}/scan-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["batch_id"] == batch_id
        assert data["fronts_pages"] == 3
        assert len(data["thumbnails"]) == 3
        assert data["thumbnails"][0]["page"] == 1
        assert f"/api/batches/{batch_id}/thumbs/1" in data["thumbnails"][0]["url"]
        assert data["state"] == "fronts_done"

    async def test_no_thumbnails(self, client):
        """Batch without thumbnails returns empty list."""
        from scanbox.config import Config

        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        # Create batch dir but no thumbs
        cfg = Config()
        batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch["id"]
        batch_dir.mkdir(parents=True, exist_ok=True)

        resp = await client.get(f"/api/batches/{batch['id']}/scan-summary")
        assert resp.status_code == 200
        assert resp.json()["thumbnails"] == []

    async def test_not_found(self, client):
        resp = await client.get("/api/batches/nonexistent/scan-summary")
        assert resp.status_code == 404


class TestServeThumbnail:
    async def test_serves_jpeg(self, client, batch_with_thumbs):
        batch_id = batch_with_thumbs["batch"]["id"]
        resp = await client.get(f"/api/batches/{batch_id}/thumbs/1")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
        assert resp.content.startswith(b"\xff\xd8")

    async def test_page_not_found(self, client, batch_with_thumbs):
        batch_id = batch_with_thumbs["batch"]["id"]
        resp = await client.get(f"/api/batches/{batch_id}/thumbs/99")
        assert resp.status_code == 404

    async def test_batch_not_found(self, client):
        resp = await client.get("/api/batches/nonexistent/thumbs/1")
        assert resp.status_code == 404


class TestScanSummaryHTMLView:
    async def test_returns_html_with_thumbnails(self, client, batch_with_thumbs):
        batch_id = batch_with_thumbs["batch"]["id"]
        resp = await client.get(f"/batches/{batch_id}/scan-summary")
        assert resp.status_code == 200
        assert "3 pages scanned" in resp.text
        assert f"/api/batches/{batch_id}/thumbs/1" in resp.text
        assert f"/api/batches/{batch_id}/thumbs/2" in resp.text
        assert f"/api/batches/{batch_id}/thumbs/3" in resp.text

    async def test_batch_not_found(self, client):
        resp = await client.get("/batches/nonexistent/scan-summary")
        assert resp.status_code == 404
