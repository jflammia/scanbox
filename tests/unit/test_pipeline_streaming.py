"""Tests for live SSE streaming on the pipeline progress page."""

import json
from pathlib import Path

import pikepdf

from scanbox.pipeline.state import PipelineConfig, PipelineState, StageStatus


def _make_pdf(path: Path, num_pages: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.add_blank_page(page_size=(612, 792))
    pdf.save(path)


class TestPipelineViewContext:
    """Verify the pipeline page view passes stages_json and dlq_json."""

    def test_stages_json_is_valid(self):
        """Stages dict serializes to valid JSON that Alpine can consume."""
        state = PipelineState.new(PipelineConfig())
        state.stages["interleaving"].status = StageStatus.COMPLETED
        state.stages["interleaving"].result = {"total_pages": 5}

        stages_dict = {k: v.to_dict() for k, v in state.stages.items()}
        stages_json = json.dumps(stages_dict)

        parsed = json.loads(stages_json)
        assert "interleaving" in parsed
        assert parsed["interleaving"]["status"] == "completed"
        assert parsed["interleaving"]["result"]["total_pages"] == 5

    def test_dlq_json_is_valid(self):
        """DLQ list serializes to valid JSON that Alpine can consume."""
        from scanbox.pipeline.state import DLQItem

        state = PipelineState.new(PipelineConfig())
        state.add_to_dlq(
            DLQItem(stage="splitting", document={"doc_type": "Lab"}, reason="Low confidence")
        )

        dlq_list = [item.to_dict() for item in state.dlq]
        dlq_json = json.dumps(dlq_list)

        parsed = json.loads(dlq_json)
        assert len(parsed) == 1
        assert parsed[0]["stage"] == "splitting"
        assert parsed[0]["reason"] == "Low confidence"


class TestPipelineTemplateContent:
    """Verify the pipeline template contains the expected Alpine.js setup."""

    def test_template_has_pipeline_view_function(self):
        """pipeline.html defines pipelineView() with connectSSE and handleEvent."""
        template_path = (
            Path(__file__).parent.parent.parent / "scanbox" / "templates" / "pipeline.html"
        )
        content = template_path.read_text()

        assert "function pipelineView()" in content
        assert "connectSSE()" in content
        assert "handleEvent(event)" in content
        assert "stages_json" in content
        assert "dlq_json" in content

    def test_template_uses_json_sse_endpoint(self):
        """SSE connects to the JSON endpoint, not the HTML fragment endpoint."""
        template_path = (
            Path(__file__).parent.parent.parent / "scanbox" / "templates" / "pipeline.html"
        )
        content = template_path.read_text()

        assert "/api/batches/" in content
        assert "/progress/stream" in content

    def test_template_uses_alpine_reactive_bindings(self):
        """Template uses Alpine x-show/x-text instead of Jinja for stage status."""
        template_path = (
            Path(__file__).parent.parent.parent / "scanbox" / "templates" / "pipeline.html"
        )
        content = template_path.read_text()

        # Alpine reactive bindings
        assert "x-show=" in content
        assert "x-text=" in content
        assert "stageSummary(" in content

    def test_template_handles_all_event_types(self):
        """handleEvent processes all expected event types."""
        template_path = (
            Path(__file__).parent.parent.parent / "scanbox" / "templates" / "pipeline.html"
        )
        content = template_path.read_text()

        for event_type in [
            "stage_complete",
            "stage_result",
            "pipeline_paused",
            "done",
            "error",
            "progress",
            "dlq_item_added",
        ]:
            assert f"event.type === '{event_type}'" in content


class TestSSEEndpointEvents:
    """Verify the SSE endpoint emits the right event types."""

    async def test_sse_endpoint_exists(self):
        """The /api/batches/{batch_id}/progress/stream endpoint is registered."""
        from scanbox.main import app

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/batches/{batch_id}/progress/stream" in routes

    async def test_event_bus_delivers_events(self):
        """EventBus correctly delivers events to subscribers."""
        from scanbox.api.sse import EventBus

        bus = EventBus()
        received = []

        async def collect():
            async for event in bus.subscribe("test-batch"):
                received.append(event)
                if event.get("type") == "done":
                    break

        import asyncio

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.01)

        await bus.publish("test-batch", {"type": "progress", "stage": "ocr"})
        await bus.publish("test-batch", {"type": "stage_complete", "stage": "ocr"})
        await bus.publish(
            "test-batch",
            {"type": "stage_result", "stage": "ocr", "result": {"ocr_complete": True}},
        )
        await bus.publish("test-batch", {"type": "done", "document_count": 3})

        await task

        assert len(received) == 4
        assert received[0]["type"] == "progress"
        assert received[1]["type"] == "stage_complete"
        assert received[2]["type"] == "stage_result"
        assert received[3]["type"] == "done"
