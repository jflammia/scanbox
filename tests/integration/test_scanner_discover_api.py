"""Integration tests for POST /api/scanner/discover endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app
from scanbox.scanner.discovery import DiscoveredScanner


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestScannerDiscover:
    async def test_returns_found_scanners(self, client: AsyncClient):
        scanner = DiscoveredScanner(
            ip="192.168.1.100",
            port=80,
            name="HP LaserJet._uscan._tcp.local.",
            model="HP Color LaserJet MFP M283cdw",
            base_path="eSCL",
            uuid="abc-123",
            icon_url="http://192.168.1.100/icon.png",
            secure=False,
        )
        with patch(
            "scanbox.api.scanner.discover_scanners",
            new=AsyncMock(return_value=[scanner]),
        ):
            resp = await client.post("/api/scanner/discover")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["hint"] is None
        assert len(data["scanners"]) == 1
        s = data["scanners"][0]
        assert s["ip"] == "192.168.1.100"
        assert s["port"] == 80
        assert s["model"] == "HP Color LaserJet MFP M283cdw"
        assert s["name"] == "HP LaserJet._uscan._tcp.local."
        assert s["uuid"] == "abc-123"
        assert s["icon_url"] == "http://192.168.1.100/icon.png"
        assert s["secure"] is False

    async def test_returns_hint_when_empty(self, client: AsyncClient):
        with patch(
            "scanbox.api.scanner.discover_scanners",
            new=AsyncMock(return_value=[]),
        ):
            resp = await client.post("/api/scanner/discover")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["scanners"] == []
        assert data["hint"] is not None
        assert "mDNS" in data["hint"]

    async def test_timeout_clamped_to_max(self, client: AsyncClient):
        mock = AsyncMock(return_value=[])
        with patch("scanbox.api.scanner.discover_scanners", new=mock):
            resp = await client.post("/api/scanner/discover?timeout=60")

        assert resp.status_code == 200
        mock.assert_called_once_with(timeout=30.0)

    async def test_default_timeout(self, client: AsyncClient):
        mock = AsyncMock(return_value=[])
        with patch("scanbox.api.scanner.discover_scanners", new=mock):
            resp = await client.post("/api/scanner/discover")

        assert resp.status_code == 200
        mock.assert_called_once_with(timeout=5.0)
