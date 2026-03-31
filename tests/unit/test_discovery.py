"""Tests for mDNS scanner discovery module."""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

from zeroconf import ServiceStateChange

from scanbox.scanner.discovery import (
    DISCOVERY_HINT,
    ESCL_SERVICE_TYPES,
    DiscoveredScanner,
    _dedup_scanners,
    discover_scanners,
    mdns_available,
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


class TestMdnsAvailable:
    def test_returns_true_on_lan_ip(self):
        """LAN IP (e.g. host networking or bare metal) means mDNS works."""
        mock_socket = MagicMock()
        mock_socket.getsockname.return_value = ("192.168.1.100", 0)
        with patch("scanbox.scanner.discovery.socket.socket", return_value=mock_socket):
            assert mdns_available() is True

    def test_returns_false_on_bridge_ip(self):
        """Docker bridge IP (172.17.x.x) means mDNS won't work."""
        mock_socket = MagicMock()
        mock_socket.getsockname.return_value = ("172.17.0.2", 0)
        with patch("scanbox.scanner.discovery.socket.socket", return_value=mock_socket):
            assert mdns_available() is False

    def test_returns_false_on_connect_failure(self):
        """No route to multicast = no network = no mDNS."""
        mock_socket = MagicMock()
        mock_socket.connect.side_effect = OSError("Network unreachable")
        with patch("scanbox.scanner.discovery.socket.socket", return_value=mock_socket):
            assert mdns_available() is False

    def test_returns_false_on_loopback(self):
        """Loopback only means no LAN access."""
        mock_socket = MagicMock()
        mock_socket.getsockname.return_value = ("127.0.0.1", 0)
        with patch("scanbox.scanner.discovery.socket.socket", return_value=mock_socket):
            assert mdns_available() is False

    def test_returns_true_on_non_bridge_private_ip(self):
        """10.x.x.x network (non-bridge private) means mDNS works."""
        mock_socket = MagicMock()
        mock_socket.getsockname.return_value = ("10.0.0.50", 0)
        with patch("scanbox.scanner.discovery.socket.socket", return_value=mock_socket):
            assert mdns_available() is True


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

    async def test_handler_called_from_background_thread_resolves_scanner(self):
        """Reproduce GH-82: zeroconf calls handlers from a background thread.

        asyncio.ensure_future raises RuntimeError in Python 3.10+ when called
        from a thread without a running event loop, so _resolve_and_add never
        runs and discover_scanners returns [].
        """
        mock_zeroconf = AsyncMock()
        mock_zeroconf.zeroconf = MagicMock()

        mock_info = MagicMock()
        mock_info.async_request = AsyncMock(return_value=True)
        mock_info.parsed_addresses.return_value = ["192.168.10.11"]
        mock_info.port = 8080
        mock_info.decoded_properties = {
            "ty": "HP Color LaserJet MFP M283cdw",
            "rs": "eSCL",
            "UUID": "abc-123",
            "representation": "http://192.168.10.11/icon.png",
        }

        captured_handlers = []

        def capture_browser(zc, types, handlers, **kwargs):
            captured_handlers.extend(handlers)
            browser = MagicMock()
            browser.async_cancel = AsyncMock()
            return browser

        real_sleep = asyncio.sleep

        with (
            patch("scanbox.scanner.discovery.AsyncZeroconf", return_value=mock_zeroconf),
            patch(
                "scanbox.scanner.discovery.AsyncServiceBrowser",
                side_effect=capture_browser,
            ),
            patch("scanbox.scanner.discovery.AsyncServiceInfo", return_value=mock_info),
            patch("scanbox.scanner.discovery.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):

            async def trigger_handler_from_thread(timeout):
                handler = captured_handlers[0]
                t = threading.Thread(
                    target=handler,
                    args=(
                        mock_zeroconf,
                        "_uscan._tcp.local.",
                        "HP Scanner._uscan._tcp.local.",
                        ServiceStateChange.Added,
                    ),
                )
                t.start()
                t.join()
                await real_sleep(0.1)  # Let scheduled coroutine run

            mock_sleep.side_effect = trigger_handler_from_thread

            result = await discover_scanners(timeout=0.01)

        assert len(result) == 1
        assert result[0].ip == "192.168.10.11"
        assert result[0].model == "HP Color LaserJet MFP M283cdw"
