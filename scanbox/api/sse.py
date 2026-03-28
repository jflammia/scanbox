"""SSE event bus for real-time progress communication."""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator


class EventBus:
    """Pub/sub event bus for SSE progress streaming.

    Channels are keyed by batch_id. Multiple subscribers can listen
    to the same channel. Subscribers automatically unregister when
    the async generator is closed.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def publish(self, channel: str, event: dict) -> None:
        """Send an event to all subscribers of a channel."""
        for queue in self._subscribers.get(channel, []):
            await queue.put(event)

    async def subscribe(self, channel: str) -> AsyncIterator[dict]:
        """Subscribe to events on a channel. Yields events as they arrive."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[channel].append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self._subscribers[channel].remove(queue)
            if not self._subscribers[channel]:
                del self._subscribers[channel]


# Global event bus instance
event_bus = EventBus()
