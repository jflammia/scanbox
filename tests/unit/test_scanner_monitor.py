"""Unit tests for scanner monitor background service."""

import asyncio
from unittest.mock import AsyncMock, patch

from scanbox.scanner.models import ScannerCapabilities, ScannerStatus
from scanbox.scanner.monitor import ScannerMonitor, ScannerState


class TestScannerState:
    def test_defaults(self):
        state = ScannerState()
        assert state.connected is False
        assert state.status is None
        assert state.capabilities is None
        assert state.last_seen is None
        assert state.last_error is None
        assert state.ip == ""


class TestScannerMonitor:
    async def test_state_defaults_to_disconnected(self):
        m = ScannerMonitor()
        assert m.state.connected is False
        assert m.state.ip == ""

    async def test_start_sets_ip(self):
        m = ScannerMonitor(poll_interval=100)
        with patch("scanbox.scanner.monitor.ESCLClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_status = AsyncMock(return_value=ScannerStatus(state="Idle"))
            mock_client.get_capabilities = AsyncMock(
                return_value=ScannerCapabilities(make_and_model="HP Test")
            )
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            await m.start("192.168.1.100")
            assert m.state.ip == "192.168.1.100"
            await m.stop()

    async def test_refresh_now_updates_state(self):
        m = ScannerMonitor(poll_interval=100)
        m._state.ip = "192.168.1.50"

        with patch("scanbox.scanner.monitor.ESCLClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_status = AsyncMock(
                return_value=ScannerStatus(state="Idle", adf_loaded=True)
            )
            mock_client.get_capabilities = AsyncMock(
                return_value=ScannerCapabilities(make_and_model="HP LaserJet")
            )
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            state = await m.refresh_now()

        assert state.connected is True
        assert state.status.state == "Idle"
        assert state.capabilities.make_and_model == "HP LaserJet"
        assert state.last_seen is not None
        assert state.last_error is None

    async def test_refresh_now_handles_error(self):
        m = ScannerMonitor(poll_interval=100)
        m._state.ip = "192.168.1.50"

        with patch("scanbox.scanner.monitor.ESCLClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_status = AsyncMock(side_effect=ConnectionError("refused"))
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            state = await m.refresh_now()

        assert state.connected is False
        assert state.status is None
        assert state.last_error == "refused"

    async def test_caches_capabilities(self):
        """Capabilities should be fetched on first poll but cached on subsequent polls."""
        m = ScannerMonitor(poll_interval=100, caps_interval=60.0)
        m._state.ip = "192.168.1.50"

        caps = ScannerCapabilities(make_and_model="HP Test")
        status = ScannerStatus(state="Idle")

        with patch("scanbox.scanner.monitor.ESCLClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_status = AsyncMock(return_value=status)
            mock_client.get_capabilities = AsyncMock(return_value=caps)
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            # First poll — capabilities should be fetched
            await m._poll_once()
            assert mock_client.get_capabilities.await_count == 1
            assert m.state.capabilities.make_and_model == "HP Test"

            # Second poll — capabilities should be cached (within 60s interval)
            await m._poll_once()
            assert mock_client.get_capabilities.await_count == 1  # still 1
            assert mock_client.get_status.await_count == 2  # status polled again

    async def test_capabilities_refreshed_after_interval(self):
        """Capabilities should be re-fetched after the caps_interval expires."""
        m = ScannerMonitor(poll_interval=100, caps_interval=0.0)  # 0 = always refresh
        m._state.ip = "192.168.1.50"

        with patch("scanbox.scanner.monitor.ESCLClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_status = AsyncMock(return_value=ScannerStatus(state="Idle"))
            mock_client.get_capabilities = AsyncMock(
                return_value=ScannerCapabilities(make_and_model="HP Test")
            )
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            await m._poll_once()
            await m._poll_once()
            # Both polls should fetch capabilities since interval is 0
            assert mock_client.get_capabilities.await_count == 2

    async def test_state_change_callback_fires_on_connect(self):
        m = ScannerMonitor(poll_interval=100)
        m._state.ip = "192.168.1.50"
        callback = AsyncMock()
        m.on_state_change(callback)

        with patch("scanbox.scanner.monitor.ESCLClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_status = AsyncMock(return_value=ScannerStatus(state="Idle"))
            mock_client.get_capabilities = AsyncMock(
                return_value=ScannerCapabilities(make_and_model="HP Test")
            )
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            # State goes from disconnected to connected
            await m._poll_once()

        callback.assert_awaited_once()
        args = callback.await_args[0]
        assert args[0].connected is True

    async def test_state_change_callback_fires_on_disconnect(self):
        m = ScannerMonitor(poll_interval=100)
        m._state.ip = "192.168.1.50"
        m._state.connected = True  # Start as connected
        callback = AsyncMock()
        m.on_state_change(callback)

        with patch("scanbox.scanner.monitor.ESCLClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_status = AsyncMock(side_effect=ConnectionError("down"))
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            await m._poll_once()

        callback.assert_awaited_once()
        args = callback.await_args[0]
        assert args[0].connected is False

    async def test_no_callback_when_state_unchanged(self):
        m = ScannerMonitor(poll_interval=100)
        m._state.ip = "192.168.1.50"
        m._state.connected = True  # Already connected
        callback = AsyncMock()
        m.on_state_change(callback)

        with patch("scanbox.scanner.monitor.ESCLClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_status = AsyncMock(return_value=ScannerStatus(state="Idle"))
            mock_client.get_capabilities = AsyncMock(
                return_value=ScannerCapabilities(make_and_model="HP Test")
            )
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            await m._poll_once()

        callback.assert_not_awaited()

    async def test_callback_error_does_not_break_monitor(self):
        m = ScannerMonitor(poll_interval=100)
        m._state.ip = "192.168.1.50"

        bad_callback = AsyncMock(side_effect=RuntimeError("callback broke"))
        good_callback = AsyncMock()
        m.on_state_change(bad_callback)
        m.on_state_change(good_callback)

        with patch("scanbox.scanner.monitor.ESCLClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_status = AsyncMock(return_value=ScannerStatus(state="Idle"))
            mock_client.get_capabilities = AsyncMock(
                return_value=ScannerCapabilities(make_and_model="HP Test")
            )
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            # Should not raise despite bad callback
            await m._poll_once()

        # Both callbacks were called despite the first one failing
        bad_callback.assert_awaited_once()
        good_callback.assert_awaited_once()

    async def test_poll_once_skips_when_no_ip(self):
        m = ScannerMonitor(poll_interval=100)
        # ip is empty by default
        with patch("scanbox.scanner.monitor.ESCLClient") as mock_cls:
            await m._poll_once()
            mock_cls.assert_not_called()

    async def test_start_cancels_previous_task(self):
        m = ScannerMonitor(poll_interval=100)
        with patch("scanbox.scanner.monitor.ESCLClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_status = AsyncMock(return_value=ScannerStatus(state="Idle"))
            mock_client.get_capabilities = AsyncMock(
                return_value=ScannerCapabilities(make_and_model="HP Test")
            )
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            await m.start("192.168.1.1")
            first_task = m._task

            await m.start("192.168.1.2")

            assert first_task.cancelled() or first_task.done()
            assert m.state.ip == "192.168.1.2"

            await m.stop()

    async def test_start_resets_capabilities_cache(self):
        m = ScannerMonitor(poll_interval=100, caps_interval=60.0)
        m._state.capabilities = ScannerCapabilities(make_and_model="Old Scanner")
        m._caps_last_fetched = 999999

        with patch("scanbox.scanner.monitor.ESCLClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_status = AsyncMock(return_value=ScannerStatus(state="Idle"))
            mock_client.get_capabilities = AsyncMock(
                return_value=ScannerCapabilities(make_and_model="New Scanner")
            )
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            await m.start("192.168.1.99")
            # Wait briefly for the poll loop to run once
            await asyncio.sleep(0.05)

            assert m.state.capabilities.make_and_model == "New Scanner"
            await m.stop()

    async def test_stop_when_not_started(self):
        m = ScannerMonitor()
        # Should not raise
        await m.stop()

    async def test_poll_loop_runs_and_stops(self):
        m = ScannerMonitor(poll_interval=0.01)
        m._state.ip = "192.168.1.50"

        call_count = 0

        with patch("scanbox.scanner.monitor.ESCLClient") as mock_cls:
            mock_client = AsyncMock()

            async def count_status():
                nonlocal call_count
                call_count += 1
                return ScannerStatus(state="Idle")

            mock_client.get_status = count_status
            mock_client.get_capabilities = AsyncMock(
                return_value=ScannerCapabilities(make_and_model="HP Test")
            )
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            m._task = asyncio.create_task(m._poll_loop())
            await asyncio.sleep(0.1)
            await m.stop()

        # Should have polled multiple times
        assert call_count >= 2


class TestScannerMonitorSSECallback:
    async def test_publish_scanner_change(self):
        from scanbox.scanner.monitor import _publish_scanner_change

        state = ScannerState(
            connected=True,
            capabilities=ScannerCapabilities(make_and_model="HP LaserJet"),
            status=ScannerStatus(state="Idle", adf_loaded=True),
            ip="192.168.1.50",
        )

        with patch("scanbox.api.sse.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            await _publish_scanner_change(state)

            mock_bus.publish.assert_awaited_once_with(
                "scanner",
                {
                    "type": "scanner_status_changed",
                    "connected": True,
                    "model": "HP LaserJet",
                    "adf_loaded": True,
                },
            )

    async def test_publish_scanner_change_disconnected(self):
        from scanbox.scanner.monitor import _publish_scanner_change

        state = ScannerState(connected=False, ip="192.168.1.50")

        with patch("scanbox.api.sse.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            await _publish_scanner_change(state)

            mock_bus.publish.assert_awaited_once_with(
                "scanner",
                {
                    "type": "scanner_status_changed",
                    "connected": False,
                    "model": None,
                    "adf_loaded": False,
                },
            )

    async def test_singleton_has_sse_callback_registered(self):
        from scanbox.scanner.monitor import _publish_scanner_change, scanner_monitor

        assert _publish_scanner_change in scanner_monitor._on_change
