"""Integration tests for scanner and setup endpoints with mocked external services."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app
from scanbox.scanner.models import ScannerCapabilities, ScannerStatus


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


class TestScannerStatusMocked:
    @patch("scanbox.api.scanner.ESCLClient")
    async def test_scanner_status_idle(self, mock_cls, client, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "192.168.1.100")
        mock_scanner = AsyncMock()
        mock_cls.return_value = mock_scanner
        mock_scanner.get_status.return_value = ScannerStatus(
            state="Idle", adf_loaded=True, adf_state="ScannerAdfLoaded"
        )

        resp = await client.get("/api/scanner/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "idle"
        assert data["adf_loaded"] is True
        assert "ready" in data["message"].lower()

    @patch("scanbox.api.scanner.ESCLClient")
    async def test_scanner_status_processing(self, mock_cls, client, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "192.168.1.100")
        mock_scanner = AsyncMock()
        mock_cls.return_value = mock_scanner
        mock_scanner.get_status.return_value = ScannerStatus(state="Processing", adf_loaded=False)

        resp = await client.get("/api/scanner/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "processing"
        assert "busy" in resp.json()["message"].lower()


class TestScannerCapabilitiesMocked:
    @patch("scanbox.api.scanner.ESCLClient")
    async def test_capabilities_success(self, mock_cls, client, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "192.168.1.100")
        mock_scanner = AsyncMock()
        mock_cls.return_value = mock_scanner
        mock_scanner.get_capabilities.return_value = ScannerCapabilities(
            make_and_model="HP Color LaserJet MFP M283cdw",
            has_adf=True,
            has_duplex_adf=False,
            supported_resolutions=[150, 300],
            supported_formats=["application/pdf", "image/jpeg"],
        )

        resp = await client.get("/api/scanner/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["make_and_model"] == "HP Color LaserJet MFP M283cdw"
        assert data["has_adf"] is True
        assert 300 in data["supported_resolutions"]


class TestSetupTestScannerMocked:
    @patch("scanbox.scanner.escl.ESCLClient")
    async def test_scanner_test_success(self, mock_cls, client, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "192.168.1.100")
        mock_scanner = AsyncMock()
        mock_cls.return_value = mock_scanner
        mock_scanner.get_capabilities.return_value = ScannerCapabilities(
            make_and_model="HP LaserJet"
        )

        resp = await client.post("/api/setup/test-scanner")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["model"] == "HP LaserJet"

    @patch("scanbox.scanner.escl.ESCLClient")
    async def test_scanner_test_unreachable(self, mock_cls, client, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "192.168.1.100")
        mock_scanner = AsyncMock()
        mock_cls.return_value = mock_scanner
        mock_scanner.get_capabilities.side_effect = Exception("timeout")

        resp = await client.post("/api/setup/test-scanner")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "reach" in data["message"].lower()


class TestSetupTestLLMMocked:
    @patch("litellm.acompletion")
    async def test_llm_test_success(self, mock_acompletion, client, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        mock_acompletion.return_value = MagicMock()

        resp = await client.post("/api/setup/test-llm")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["provider"] == "anthropic"
        assert "connected" in data["message"].lower()

    @patch("litellm.acompletion")
    async def test_llm_test_failure(self, mock_acompletion, client, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        mock_acompletion.side_effect = Exception("Invalid API key")

        resp = await client.post("/api/setup/test-llm")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "Invalid API key" in data["message"]


class TestSetupTestPaperlessMocked:
    @patch("scanbox.api.paperless.PaperlessClient.check_connection")
    async def test_paperless_success(self, mock_check, client, monkeypatch):
        monkeypatch.setenv("PAPERLESS_URL", "http://paperless:8000")
        monkeypatch.setenv("PAPERLESS_API_TOKEN", "token123")
        mock_check.return_value = True

        resp = await client.post("/api/setup/test-paperless")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "paperless:8000" in data["paperless_url"]

    @patch("scanbox.api.paperless.PaperlessClient.check_connection")
    async def test_paperless_failure(self, mock_check, client, monkeypatch):
        monkeypatch.setenv("PAPERLESS_URL", "http://paperless:8000")
        monkeypatch.setenv("PAPERLESS_API_TOKEN", "token123")
        mock_check.return_value = False

        resp = await client.post("/api/setup/test-paperless")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


class TestHealthMocked:
    @patch("scanbox.scanner.escl.ESCLClient")
    async def test_health_scanner_ok(self, mock_cls, client, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "192.168.1.100")
        mock_scanner = AsyncMock()
        mock_cls.return_value = mock_scanner
        mock_scanner.get_status.return_value = ScannerStatus(state="Idle")

        resp = await client.get("/api/health")
        data = resp.json()
        assert data["scanner"] == "ok"

    @patch("scanbox.scanner.escl.ESCLClient")
    async def test_health_scanner_unreachable(self, mock_cls, client, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "192.168.1.100")
        mock_scanner = AsyncMock()
        mock_cls.return_value = mock_scanner
        mock_scanner.get_status.side_effect = Exception("timeout")

        resp = await client.get("/api/health")
        data = resp.json()
        assert data["scanner"] == "unreachable"
