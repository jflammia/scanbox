"""Unit tests for SSE event bus."""

import asyncio

from scanbox.api.sse import EventBus


class TestEventBus:
    """Test the SSE event bus for progress communication."""

    async def test_publish_and_subscribe(self):
        bus = EventBus()
        received = []

        async def listener():
            async for event in bus.subscribe("batch-123"):
                received.append(event)
                if event["type"] == "done":
                    break

        task = asyncio.create_task(listener())
        await asyncio.sleep(0.01)

        await bus.publish("batch-123", {"type": "progress", "stage": "ocr", "percent": 50})
        await bus.publish("batch-123", {"type": "done"})

        await asyncio.wait_for(task, timeout=1.0)

        assert len(received) == 2
        assert received[0]["stage"] == "ocr"
        assert received[1]["type"] == "done"

    async def test_multiple_subscribers(self):
        bus = EventBus()
        counts = [0, 0]

        async def listener(idx):
            async for event in bus.subscribe("batch-1"):
                counts[idx] += 1
                if event["type"] == "done":
                    break

        t1 = asyncio.create_task(listener(0))
        t2 = asyncio.create_task(listener(1))
        await asyncio.sleep(0.01)

        await bus.publish("batch-1", {"type": "progress"})
        await bus.publish("batch-1", {"type": "done"})

        await asyncio.wait_for(asyncio.gather(t1, t2), timeout=1.0)

        assert counts[0] == 2
        assert counts[1] == 2

    async def test_different_channels(self):
        bus = EventBus()
        received = []

        async def listener():
            async for event in bus.subscribe("batch-A"):
                received.append(event)
                if event["type"] == "done":
                    break

        task = asyncio.create_task(listener())
        await asyncio.sleep(0.01)

        # Publish to different channel — should not be received
        await bus.publish("batch-B", {"type": "progress"})
        # Publish to correct channel
        await bus.publish("batch-A", {"type": "done"})

        await asyncio.wait_for(task, timeout=1.0)

        assert len(received) == 1
        assert received[0]["type"] == "done"

    async def test_subscriber_receives_only_after_subscribe(self):
        bus = EventBus()
        received = []

        # Publish before any subscriber
        await bus.publish("ch", {"type": "missed"})

        async def listener():
            async for event in bus.subscribe("ch"):
                received.append(event)
                if event["type"] == "done":
                    break

        task = asyncio.create_task(listener())
        await asyncio.sleep(0.01)
        await bus.publish("ch", {"type": "done"})
        await asyncio.wait_for(task, timeout=1.0)

        # Should only have the event published after subscribing
        assert len(received) == 1
        assert received[0]["type"] == "done"
