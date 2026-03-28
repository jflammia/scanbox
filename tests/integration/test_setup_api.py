"""Integration tests for first-run setup wizard."""

import json

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


class TestSetupStatus:
    async def test_setup_not_completed_initially(self, client: AsyncClient):
        resp = await client.get("/api/setup/status")
        assert resp.status_code == 200
        assert resp.json()["completed"] is False

    async def test_setup_status_returns_current_step(self, client: AsyncClient):
        resp = await client.get("/api/setup/status")
        data = resp.json()
        assert "current_step" in data
        assert data["current_step"] == 1
        assert data["total_steps"] == 6


class TestSetupPage:
    async def test_setup_page_returns_html(self, client: AsyncClient):
        resp = await client.get("/setup")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_setup_page_contains_wizard_content(self, client: AsyncClient):
        resp = await client.get("/setup")
        assert "Setup" in resp.text


class TestSetupComplete:
    async def test_complete_setup(self, client: AsyncClient, tmp_path):
        resp = await client.post("/api/setup/complete")
        assert resp.status_code == 200
        assert resp.json()["completed"] is True

        # Verify persisted
        resp = await client.get("/api/setup/status")
        assert resp.json()["completed"] is True

    async def test_setup_stores_config(self, client: AsyncClient, tmp_path):
        resp = await client.post(
            "/api/setup/complete",
            json={"scanner_ip": "192.168.1.100", "llm_provider": "anthropic"},
        )
        assert resp.status_code == 200

        # Config file should be written
        config_path = tmp_path / "data" / "config" / "setup.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["completed"] is True


class TestHomeRedirect:
    async def test_home_shows_setup_prompt_when_not_completed(self, client: AsyncClient):
        """Home page should mention setup when not completed."""
        resp = await client.get("/")
        assert resp.status_code == 200
        # Should have a link/prompt to run setup
        assert "setup" in resp.text.lower() or "Setup" in resp.text
