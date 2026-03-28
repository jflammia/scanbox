"""Integration tests for the scan-to-pipeline workflow.

Tests that scan endpoints trigger background tasks and state transitions,
and that the SSE progress stream endpoint works.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("SCANNER_IP", "192.168.1.100")

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
async def batch_id(client: AsyncClient):
    """Create a person, session, and batch for testing."""
    person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
    session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
    batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
    return batch["id"]


class TestScanEndpointValidation:
    """Scan endpoints enforce state machine rules."""

    async def test_scan_fronts_requires_scanner_ip(self, tmp_path, monkeypatch):
        """Scan fronts returns 503 when no scanner configured."""
        monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setenv("SCANNER_IP", "")

        from scanbox.main import lifespan

        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                person = (await ac.post("/api/persons", json={"display_name": "Test"})).json()
                session = (await ac.post("/api/sessions", json={"person_id": person["id"]})).json()
                batch = (await ac.post(f"/api/sessions/{session['id']}/batches")).json()
                resp = await ac.post(f"/api/batches/{batch['id']}/scan/fronts")
                assert resp.status_code == 503

    async def test_scan_fronts_wrong_state(self, client, batch_id):
        """Cannot scan fronts if batch is not in scanning_fronts state."""
        from scanbox.main import get_db

        db = get_db()
        await db.update_batch_state(batch_id, "fronts_done")
        resp = await client.post(f"/api/batches/{batch_id}/scan/fronts")
        assert resp.status_code == 409

    async def test_scan_backs_wrong_state(self, client, batch_id):
        """Cannot scan backs if batch is not in fronts_done state."""
        resp = await client.post(f"/api/batches/{batch_id}/scan/backs")
        assert resp.status_code == 409

    async def test_scan_fronts_returns_202(self, client, batch_id):
        """Scan fronts returns 202 and starts background task."""
        resp = await client.post(f"/api/batches/{batch_id}/scan/fronts")
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "scanning"
        assert "progress_url" in data

    async def test_scan_backs_returns_202(self, client, batch_id):
        """Scan backs returns 202 when in fronts_done state."""
        from scanbox.main import get_db

        db = get_db()
        await db.update_batch_state(batch_id, "fronts_done")
        resp = await client.post(f"/api/batches/{batch_id}/scan/backs")
        assert resp.status_code == 202


class TestSkipBacksTriggersProcessing:
    """Skip backs should transition state and trigger pipeline."""

    async def test_skip_backs_transitions_state(self, client, batch_id):
        """Skip backs transitions from fronts_done to backs_skipped."""
        from scanbox.main import get_db

        db = get_db()
        await db.update_batch_state(batch_id, "fronts_done")
        resp = await client.post(f"/api/batches/{batch_id}/skip-backs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "backs_skipped"


class TestProgressEndpoints:
    """Progress polling and SSE streaming endpoints."""

    async def test_progress_returns_state(self, client, batch_id):
        resp = await client.get(f"/api/batches/{batch_id}/progress")
        assert resp.status_code == 200
        data = resp.json()
        assert data["batch_id"] == batch_id
        assert data["state"] == "scanning_fronts"

    async def test_progress_stream_endpoint_exists(self, client, batch_id):
        """SSE stream endpoint should be reachable."""
        # We can't fully test SSE in a synchronous test, but we verify the endpoint exists
        # and returns the right content type
        import asyncio

        from scanbox.api.sse import event_bus

        # Publish a done event so the stream terminates
        async def send_done():
            await asyncio.sleep(0.1)
            await event_bus.publish(batch_id, {"type": "done"})

        asyncio.create_task(send_done())

        resp = await client.get(
            f"/api/batches/{batch_id}/progress/stream",
            timeout=2.0,
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    async def test_progress_404_for_missing_batch(self, client):
        resp = await client.get("/api/batches/nonexistent/progress")
        assert resp.status_code == 404
