"""Integration tests for scanner status and capabilities API endpoints."""

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


class TestScannerStatus:
    async def test_no_scanner_configured(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "")
        resp = await client.get("/api/scanner/status")
        assert resp.status_code == 503

    async def test_scanner_unreachable(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "192.168.255.255")
        resp = await client.get("/api/scanner/status")
        assert resp.status_code == 503
        assert "reach" in resp.json()["detail"].lower()


class TestScannerCapabilities:
    async def test_no_scanner_configured(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "")
        resp = await client.get("/api/scanner/capabilities")
        assert resp.status_code == 503


class TestSetupTestEndpoints:
    async def test_test_scanner_no_ip(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "")
        resp = await client.post("/api/setup/test-scanner")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    async def test_test_llm_no_key(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        monkeypatch.setenv("OPENAI_API_KEY", "")
        resp = await client.post("/api/setup/test-llm")
        assert resp.status_code == 200
        data = resp.json()
        # Without valid keys, LLM call will fail
        assert data["success"] is False
        assert "provider" in data

    async def test_test_paperless_not_configured(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("PAPERLESS_URL", "")
        monkeypatch.setenv("PAPERLESS_API_TOKEN", "")
        resp = await client.post("/api/setup/test-paperless")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
