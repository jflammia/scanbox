"""Tests for mDNS scanner discovery module."""

from unittest.mock import AsyncMock, MagicMock, patch

from scanbox.scanner.discovery import (
    DISCOVERY_HINT,
    ESCL_SERVICE_TYPES,
    DiscoveredScanner,
    _dedup_scanners,
    discover_scanners,
)


class TestConstants:
    def test_service_types(self):
        assert ESCL_SERVICE_TYPES == ["_uscan._tcp.local.", "_uscans._tcp.local."]

    def test_discovery_hint_contains_key_info(self):
        assert "mDNS" in DISCOVERY_HINT
        assert "network_mode: host" in DISCOVERY_HINT
        assert "IP address" in DISCOVERY_HINT


class TestDiscoveredScannerDataclass:
    def test_discovered_scanner_dataclass(self):
        scanner = DiscoveredScanner(
            ip="192.168.1.5",
            port=443,
            name="HP Color LaserJet MFP M283cdw._uscans._tcp.local.",
            model="HP Color LaserJet MFP M283cdw",
            base_path="eSCL",
            uuid="1234-5678",
            icon_url="http://192.168.1.5/scanner.png",
            secure=True,
        )
        assert scanner.ip == "192.168.1.5"
        assert scanner.port == 443
        assert scanner.name == "HP Color LaserJet MFP M283cdw._uscans._tcp.local."
        assert scanner.model == "HP Color LaserJet MFP M283cdw"
        assert scanner.base_path == "eSCL"
        assert scanner.uuid == "1234-5678"
        assert scanner.icon_url == "http://192.168.1.5/scanner.png"
        assert scanner.secure is True

    def test_discovered_scanner_defaults(self):
        scanner = DiscoveredScanner(
            ip="10.0.0.1",
            port=80,
            name="Scanner._uscan._tcp.local.",
            model="",
            base_path="",
            uuid="",
            icon_url="",
            secure=False,
        )
        assert scanner.secure is False
        assert scanner.model == ""


class TestDiscoveredScannerDedup:
    def test_dedup_by_uuid(self):
        scanners = [
            DiscoveredScanner(
                ip="192.168.1.5",
                port=80,
                name="Scanner._uscan._tcp.local.",
                model="HP",
                base_path="eSCL",
                uuid="uuid-abc",
                icon_url="",
                secure=False,
            ),
            DiscoveredScanner(
                ip="192.168.1.5",
                port=443,
                name="Scanner._uscans._tcp.local.",
                model="HP",
                base_path="eSCL",
                uuid="uuid-abc",
                icon_url="",
                secure=True,
            ),
            DiscoveredScanner(
                ip="192.168.1.10",
                port=80,
                name="Printer._uscan._tcp.local.",
                model="Canon",
                base_path="eSCL",
                uuid="uuid-xyz",
                icon_url="",
                secure=False,
            ),
        ]
        result = _dedup_scanners(scanners)
        assert len(result) == 2

    def test_dedup_prefers_secure(self):
        scanners = [
            DiscoveredScanner(
                ip="192.168.1.5",
                port=80,
                name="Scanner._uscan._tcp.local.",
                model="HP",
                base_path="eSCL",
                uuid="uuid-abc",
                icon_url="",
                secure=False,
            ),
            DiscoveredScanner(
                ip="192.168.1.5",
                port=443,
                name="Scanner._uscans._tcp.local.",
                model="HP",
                base_path="eSCL",
                uuid="uuid-abc",
                icon_url="",
                secure=True,
            ),
        ]
        result = _dedup_scanners(scanners)
        assert len(result) == 1
        assert result[0].secure is True
        assert result[0].port == 443

    def test_dedup_empty(self):
        assert _dedup_scanners([]) == []

    def test_dedup_no_duplicates(self):
        scanners = [
            DiscoveredScanner(
                ip="192.168.1.5",
                port=80,
                name="Scanner._uscan._tcp.local.",
                model="HP",
                base_path="eSCL",
                uuid="uuid-abc",
                icon_url="",
                secure=False,
            ),
            DiscoveredScanner(
                ip="192.168.1.10",
                port=80,
                name="Printer._uscan._tcp.local.",
                model="Canon",
                base_path="eSCL",
                uuid="uuid-xyz",
                icon_url="",
                secure=False,
            ),
        ]
        result = _dedup_scanners(scanners)
        assert len(result) == 2


class TestDiscoverScanners:
    async def test_returns_empty_when_no_scanners(self):
        mock_zeroconf = AsyncMock()
        mock_browser = MagicMock()
        mock_browser.async_cancel = AsyncMock()

        with (
            patch("scanbox.scanner.discovery.AsyncZeroconf", return_value=mock_zeroconf),
            patch("scanbox.scanner.discovery.AsyncServiceBrowser", return_value=mock_browser),
        ):
            result = await discover_scanners(timeout=0.01)

        assert result == []
        mock_zeroconf.async_close.assert_awaited_once()

    async def test_cleanup_called_on_completion(self):
        mock_zeroconf = AsyncMock()
        mock_browser = MagicMock()
        mock_browser.async_cancel = AsyncMock()

        with (
            patch("scanbox.scanner.discovery.AsyncZeroconf", return_value=mock_zeroconf),
            patch("scanbox.scanner.discovery.AsyncServiceBrowser", return_value=mock_browser),
        ):
            await discover_scanners(timeout=0.01)

        mock_zeroconf.async_close.assert_awaited_once()
