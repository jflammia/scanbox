"""Integration tests for practice run wizard."""

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


class TestPracticeStatus:
    async def test_practice_not_completed_initially(self, client: AsyncClient):
        resp = await client.get("/api/practice/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is False
        assert data["current_step"] == 1
        assert data["total_steps"] == 4

    async def test_advance_step(self, client: AsyncClient):
        resp = await client.post("/api/practice/step/1/complete")
        assert resp.status_code == 200
        assert resp.json()["current_step"] == 2

        resp = await client.get("/api/practice/status")
        assert resp.json()["current_step"] == 2

    async def test_cannot_skip_steps(self, client: AsyncClient):
        resp = await client.post("/api/practice/step/3/complete")
        assert resp.status_code == 409

    async def test_complete_all_steps(self, client: AsyncClient):
        for step in range(1, 5):
            resp = await client.post(f"/api/practice/step/{step}/complete")
            assert resp.status_code == 200

        resp = await client.get("/api/practice/status")
        assert resp.json()["completed"] is True

    async def test_state_persisted(self, client: AsyncClient, tmp_path):
        await client.post("/api/practice/step/1/complete")
        config_path = tmp_path / "data" / "config" / "practice.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["current_step"] == 2


class TestPracticePage:
    async def test_practice_page_returns_html(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_practice_page_contains_content(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert "Practice" in resp.text

    async def test_practice_page_shows_step_1(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert "scan one page" in resp.text.lower() or "one page" in resp.text.lower()


class TestPracticeReset:
    async def test_reset_practice(self, client: AsyncClient):
        await client.post("/api/practice/step/1/complete")
        await client.post("/api/practice/step/2/complete")

        resp = await client.post("/api/practice/reset")
        assert resp.status_code == 200

        resp = await client.get("/api/practice/status")
        assert resp.json()["current_step"] == 1
        assert resp.json()["completed"] is False
