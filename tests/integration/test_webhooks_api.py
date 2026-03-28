"""Integration tests for webhook registration and management."""

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestWebhookRegistration:
    async def test_register_webhook(self, client: AsyncClient):
        resp = await client.post(
            "/api/webhooks",
            json={
                "url": "https://example.com/hooks/scanbox",
                "events": ["scan.completed", "save.completed"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["url"] == "https://example.com/hooks/scanbox"
        assert data["events"] == ["scan.completed", "save.completed"]

    async def test_register_webhook_with_secret(self, client: AsyncClient):
        resp = await client.post(
            "/api/webhooks",
            json={
                "url": "https://example.com/hooks",
                "events": ["processing.completed"],
                "secret": "my-secret-key",
            },
        )
        assert resp.status_code == 201
        # Secret should not be returned in response
        assert "secret" not in resp.json() or resp.json().get("secret") is None

    async def test_register_requires_url(self, client: AsyncClient):
        resp = await client.post("/api/webhooks", json={"events": ["scan.completed"]})
        assert resp.status_code == 422


class TestWebhookList:
    async def test_list_empty(self, client: AsyncClient):
        resp = await client.get("/api/webhooks")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_list_after_register(self, client: AsyncClient):
        await client.post(
            "/api/webhooks",
            json={"url": "https://a.com/hook", "events": ["scan.completed"]},
        )
        await client.post(
            "/api/webhooks",
            json={"url": "https://b.com/hook", "events": ["save.completed"]},
        )
        resp = await client.get("/api/webhooks")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2


class TestWebhookDelete:
    async def test_delete_webhook(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/webhooks",
            json={"url": "https://example.com/hook", "events": ["scan.completed"]},
        )
        webhook_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/webhooks/{webhook_id}")
        assert resp.status_code == 204

        # Verify deleted
        resp = await client.get("/api/webhooks")
        assert len(resp.json()["items"]) == 0

    async def test_delete_nonexistent(self, client: AsyncClient):
        resp = await client.delete("/api/webhooks/nonexistent")
        assert resp.status_code == 404


class TestWebhookEvents:
    async def test_valid_event_types(self, client: AsyncClient):
        resp = await client.get("/api/webhooks/events")
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert "scan.completed" in events
        assert "processing.completed" in events
        assert "save.completed" in events
