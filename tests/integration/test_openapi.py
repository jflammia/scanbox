"""Integration tests for OpenAPI documentation and API key auth."""

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


class TestOpenAPIDocs:
    async def test_openapi_json_accessible(self, client: AsyncClient):
        resp = await client.get("/api/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["info"]["title"] == "ScanBox"
        assert "paths" in data

    async def test_swagger_ui_accessible(self, client: AsyncClient):
        resp = await client.get("/api/docs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_redoc_accessible(self, client: AsyncClient):
        resp = await client.get("/api/redoc")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_openapi_includes_all_api_paths(self, client: AsyncClient):
        resp = await client.get("/api/openapi.json")
        paths = resp.json()["paths"]
        assert "/api/health" in paths
        assert "/api/persons" in paths
        assert "/api/sessions" in paths
        assert "/api/webhooks" in paths
        assert "/api/setup/status" in paths
        assert "/api/practice/status" in paths
