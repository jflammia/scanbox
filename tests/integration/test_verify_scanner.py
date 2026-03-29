"""Tests for scanner verification checklist endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app
from scanbox.scanner.models import ScannerCapabilities, ScannerStatus


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestVerifyScanner:
    @patch("scanbox.scanner.escl.ESCLClient")
    @patch("scanbox.api.setup.socket")
    async def test_all_checks_pass(
        self, mock_socket, mock_client_cls, client: AsyncClient, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path))
        mock_client = AsyncMock()
        mock_client.get_status.return_value = ScannerStatus(state="Idle", adf_loaded=True)
        mock_client.get_capabilities.return_value = ScannerCapabilities(
            make_and_model="Test Scanner",
            has_adf=True,
            icon_url="http://1.2.3.4/icon.png",
        )
        mock_client_cls.return_value = mock_client

        resp = await client.post("/setup/verify-scanner", data={"scanner_ip": "1.2.3.4"})
        assert resp.status_code == 200
        html = resp.text
        assert "Reaching scanner" in html
        assert "eSCL protocol" in html
        assert "Scanner capabilities" in html
        assert "Scanner ready" in html
        assert "Test Scanner" in html
        assert "step = 2" in html

    @patch("scanbox.api.setup.socket")
    async def test_unreachable_scanner(self, mock_socket, client: AsyncClient):
        mock_socket.create_connection.side_effect = ConnectionError("timeout")
        resp = await client.post("/setup/verify-scanner", data={"scanner_ip": "1.2.3.4"})
        html = resp.text
        assert "Reaching scanner" in html
        assert "step = 2" not in html
        assert "Retry" in html

    @patch("scanbox.scanner.escl.ESCLClient")
    @patch("scanbox.api.setup.socket")
    async def test_no_adf(self, mock_socket, mock_client_cls, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.get_status.return_value = ScannerStatus(state="Idle")
        mock_client.get_capabilities.return_value = ScannerCapabilities(
            make_and_model="Test Scanner", has_adf=False
        )
        mock_client_cls.return_value = mock_client
        resp = await client.post("/setup/verify-scanner", data={"scanner_ip": "1.2.3.4"})
        html = resp.text
        assert "No document feeder" in html
        assert "Retry" in html

    async def test_empty_ip(self, client: AsyncClient):
        resp = await client.post("/setup/verify-scanner", data={"scanner_ip": ""})
        assert "Enter a scanner IP" in resp.text

    @patch("scanbox.scanner.escl.ESCLClient")
    @patch("scanbox.api.setup.socket")
    async def test_escl_protocol_failure(self, mock_socket, mock_client_cls, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.get_status.side_effect = Exception("connection refused")
        mock_client_cls.return_value = mock_client
        resp = await client.post("/setup/verify-scanner", data={"scanner_ip": "1.2.3.4"})
        html = resp.text
        assert "eSCL protocol" in html
        assert "doesn't support eSCL" in html
        assert "Retry" in html

    @patch("scanbox.scanner.escl.ESCLClient")
    @patch("scanbox.api.setup.socket")
    async def test_scanner_busy(self, mock_socket, mock_client_cls, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.get_status.return_value = ScannerStatus(state="Processing")
        mock_client.get_capabilities.return_value = ScannerCapabilities(
            make_and_model="Test Scanner", has_adf=True
        )
        mock_client_cls.return_value = mock_client
        resp = await client.post("/setup/verify-scanner", data={"scanner_ip": "1.2.3.4"})
        html = resp.text
        assert "Scanner ready" in html
        assert "busy" in html
        assert "Retry" in html
        assert "step = 2" not in html


class TestDiscoverScannersHtml:
    """Tests for the mDNS-based HTML discovery endpoint."""

    @patch("scanbox.scanner.discovery.discover_scanners", new_callable=AsyncMock)
    async def test_found_scanners(self, mock_discover, client: AsyncClient):
        from scanbox.scanner.discovery import DiscoveredScanner

        mock_discover.return_value = [
            DiscoveredScanner(
                ip="192.168.1.100",
                port=80,
                name="HP Scanner",
                model="HP LaserJet",
                base_path="eSCL",
                uuid="abc-123",
                icon_url="http://192.168.1.100/icon.png",
                secure=False,
            )
        ]
        resp = await client.post("/setup/discover-scanners")
        assert resp.status_code == 200
        html = resp.text
        assert "Found 1 scanner(s)" in html
        assert "HP LaserJet" in html
        assert "192.168.1.100" in html

    @patch("scanbox.scanner.discovery.discover_scanners", new_callable=AsyncMock)
    async def test_no_scanners_shows_hint(self, mock_discover, client: AsyncClient):
        mock_discover.return_value = []
        resp = await client.post("/setup/discover-scanners")
        assert resp.status_code == 200
        html = resp.text
        assert "mDNS" in html
