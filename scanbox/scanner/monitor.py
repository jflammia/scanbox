"""Scanner connection monitor — background polling with cached state."""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from scanbox.scanner.escl import ESCLClient
from scanbox.scanner.models import ScannerCapabilities, ScannerStatus

logger = logging.getLogger(__name__)


@dataclass
class ScannerState:
    """Current cached scanner state."""

    connected: bool = False
    status: ScannerStatus | None = None
    capabilities: ScannerCapabilities | None = None
    last_seen: str | None = None
    last_error: str | None = None
    ip: str = ""


class ScannerMonitor:
    """Background scanner monitoring service.

    Polls the scanner every `poll_interval` seconds and caches the result.
    Capabilities are refreshed every `caps_interval` seconds (they rarely change).
    """

    def __init__(self, poll_interval: float = 5.0, caps_interval: float = 60.0):
        self._poll_interval = poll_interval
        self._caps_interval = caps_interval
        self._state = ScannerState()
        self._task: asyncio.Task | None = None
        self._caps_last_fetched: float = 0
        self._on_change: list[callable] = []

    @property
    def state(self) -> ScannerState:
        """Get the current cached scanner state. No HTTP call."""
        return self._state

    def on_state_change(self, callback):
        """Register a callback for state changes."""
        self._on_change.append(callback)

    async def start(self, scanner_ip: str) -> None:
        """Start monitoring the given scanner IP."""
        self._state.ip = scanner_ip
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._caps_last_fetched = 0
        self._state.capabilities = None
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop the monitoring background task."""
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def refresh_now(self) -> ScannerState:
        """Force an immediate refresh. Used after changing scanner IP."""
        await self._poll_once()
        return self._state

    async def _poll_loop(self) -> None:
        """Background polling loop."""
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Scanner poll error")
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        if not self._state.ip:
            return

        was_connected = self._state.connected
        client = ESCLClient(self._state.ip)
        try:
            status = await client.get_status()
            self._state.status = status
            self._state.connected = True
            self._state.last_seen = datetime.now(UTC).isoformat()
            self._state.last_error = None

            # Refresh capabilities less frequently
            now = asyncio.get_event_loop().time()
            if (
                now - self._caps_last_fetched > self._caps_interval
                or self._state.capabilities is None
            ):
                caps = await client.get_capabilities()
                self._state.capabilities = caps
                self._caps_last_fetched = now

        except Exception as e:
            self._state.connected = False
            self._state.status = None
            self._state.last_error = str(e)

        finally:
            await client.close()

        # Notify on state change
        if was_connected != self._state.connected:
            for cb in self._on_change:
                try:
                    await cb(self._state)
                except Exception:
                    logger.exception("State change callback error")


async def _publish_scanner_change(state: ScannerState) -> None:
    """Publish scanner state changes to the SSE event bus."""
    from scanbox.api.sse import event_bus

    await event_bus.publish(
        "scanner",
        {
            "type": "scanner_status_changed",
            "connected": state.connected,
            "model": state.capabilities.make_and_model if state.capabilities else None,
            "adf_loaded": state.status.adf_loaded if state.status else False,
        },
    )


# Global singleton
scanner_monitor = ScannerMonitor()
scanner_monitor.on_state_change(_publish_scanner_change)
