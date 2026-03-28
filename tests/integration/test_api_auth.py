"""Integration tests for optional API key authentication."""

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


@pytest.fixture
async def authed_client(tmp_path, monkeypatch):
    """Client with API key authentication enabled."""
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("SCANBOX_API_KEY", "test-secret-key-123")

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestNoAuthByDefault:
    """When SCANBOX_API_KEY is not set, all endpoints are open."""

    async def test_api_accessible_without_key(self, client: AsyncClient):
        resp = await client.get("/api/health")
        assert resp.status_code == 200

    async def test_api_persons_accessible_without_key(self, client: AsyncClient):
        resp = await client.get("/api/persons")
        assert resp.status_code == 200


class TestApiKeyAuth:
    """When SCANBOX_API_KEY is set, API endpoints require bearer token."""

    async def test_api_rejects_without_key(self, authed_client: AsyncClient):
        resp = await authed_client.get("/api/persons")
        assert resp.status_code == 401

    async def test_api_rejects_wrong_key(self, authed_client: AsyncClient):
        resp = await authed_client.get(
            "/api/persons", headers={"Authorization": "Bearer wrong-key"}
        )
        assert resp.status_code == 401

    async def test_api_accepts_correct_key(self, authed_client: AsyncClient):
        resp = await authed_client.get(
            "/api/persons", headers={"Authorization": "Bearer test-secret-key-123"}
        )
        assert resp.status_code == 200

    async def test_health_always_accessible(self, authed_client: AsyncClient):
        """Health endpoint should work without auth for monitoring tools."""
        resp = await authed_client.get("/api/health")
        assert resp.status_code == 200

    async def test_web_ui_accessible_without_key(self, authed_client: AsyncClient):
        """Web UI routes (non-/api/) should not require auth."""
        resp = await authed_client.get("/")
        assert resp.status_code == 200

    async def test_openapi_accessible_without_key(self, authed_client: AsyncClient):
        """OpenAPI docs should be accessible without auth."""
        resp = await authed_client.get("/api/openapi.json")
        assert resp.status_code == 200
