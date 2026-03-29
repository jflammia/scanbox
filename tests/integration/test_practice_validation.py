"""Integration tests for practice run with actual subsystem validation."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestPracticeValidation:
    async def test_validate_scanner_step(self, client, monkeypatch):
        """Step 1 should validate scanner connectivity."""
        monkeypatch.setenv("SCANNER_IP", "192.168.1.100")

        with patch("scanbox.api.practice.ESCLClient") as mock_cls:
            mock_scanner = AsyncMock()
            mock_cls.return_value = mock_scanner
            from scanbox.scanner.models import ScannerCapabilities

            mock_scanner.get_capabilities.return_value = ScannerCapabilities(
                make_and_model="HP LaserJet"
            )

            resp = await client.post("/api/practice/step/1/validate")
            assert resp.status_code == 200
            data = resp.json()
            assert data["valid"] is True
            assert "scanner" in data["message"].lower()

    async def test_validate_scanner_step_fails(self, client, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "")

        resp = await client.post("/api/practice/step/1/validate")
        data = resp.json()
        assert data["valid"] is False

    @patch("litellm.acompletion")
    async def test_validate_llm_step(self, mock_llm, client, monkeypatch):
        """Step 2 should validate LLM connectivity."""
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        from unittest.mock import MagicMock

        mock_llm.return_value = MagicMock()

        resp = await client.post("/api/practice/step/2/validate")
        data = resp.json()
        assert data["valid"] is True

    @patch("litellm.acompletion")
    async def test_validate_llm_step_fails(self, mock_llm, client, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        mock_llm.side_effect = Exception("Invalid API key")

        resp = await client.post("/api/practice/step/2/validate")
        data = resp.json()
        assert data["valid"] is False
        assert "Invalid API key" in data["message"]

    async def test_validate_storage_step(self, client):
        """Step 3 should validate storage directories exist."""
        resp = await client.post("/api/practice/step/3/validate")
        data = resp.json()
        assert data["valid"] is True

    async def test_validate_storage_step_missing_output(self, client, monkeypatch, tmp_path):
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "nonexistent"))
        resp = await client.post("/api/practice/step/3/validate")
        data = resp.json()
        assert data["valid"] is False

    async def test_validate_complete_step(self, client):
        """Step 4 should verify a person exists."""
        from scanbox.main import get_db

        db = get_db()
        await db.create_person("Test User")

        resp = await client.post("/api/practice/step/4/validate")
        data = resp.json()
        assert data["valid"] is True

    async def test_validate_complete_step_no_person(self, client):
        resp = await client.post("/api/practice/step/4/validate")
        data = resp.json()
        assert data["valid"] is False

    async def test_validate_invalid_step(self, client):
        resp = await client.post("/api/practice/step/99/validate")
        assert resp.status_code == 400
