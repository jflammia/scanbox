"""Tests for pipeline control API endpoints."""

from io import BytesIO
from unittest.mock import AsyncMock, patch

import pikepdf
import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.config import Config
from scanbox.main import app, get_db
from scanbox.models import ProcessingStage
from scanbox.pipeline.state import DLQItem, PipelineState


def _make_pdf_bytes(num_pages: int = 3) -> bytes:
    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.add_blank_page(page_size=(612, 792))
    buf = BytesIO()
    pdf.save(buf)
    return buf.getvalue()


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "output").mkdir()
    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def _create_batch(client):
    """Create a batch via import (with processing mocked out) and return (batch_id, batch_dir)."""
    fronts = _make_pdf_bytes(3)
    with patch("scanbox.api.scanning._run_processing", new_callable=AsyncMock):
        resp = await client.post(
            "/api/batches/import",
            files={"fronts": ("fronts.pdf", fronts, "application/pdf")},
        )
    data = resp.json()
    batch_id = data["batch_id"]
    db = get_db()
    batch = await db.get_batch(batch_id)
    session = await db.get_session(batch["session_id"])
    cfg = Config()
    batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch_id
    return batch_id, batch_dir


class TestGetPipelineState:
    async def test_returns_pipeline_state(self, client):
        batch_id, batch_dir = await _create_batch(client)
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.INTERLEAVING, {"total_pages": 3})
        state.save(batch_dir / "state.json")

        resp = await client.get(f"/api/batches/{batch_id}/pipeline")
        assert resp.status_code == 200
        data = resp.json()
        assert "stages" in data
        assert "dlq" in data
        assert "config" in data
        assert "status" in data
        assert data["stages"]["interleaving"]["status"] == "completed"

    async def test_nonexistent_batch_returns_404(self, client):
        resp = await client.get("/api/batches/nonexistent/pipeline")
        assert resp.status_code == 404


class TestGetStageResult:
    async def test_returns_stage_data(self, client):
        batch_id, batch_dir = await _create_batch(client)
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.INTERLEAVING, {"total_pages": 5})
        state.save(batch_dir / "state.json")

        resp = await client.get(f"/api/batches/{batch_id}/pipeline/stage/interleaving")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"
        assert resp.json()["result"]["total_pages"] == 5

    async def test_unknown_stage_returns_404(self, client):
        batch_id, batch_dir = await _create_batch(client)
        PipelineState.new().save(batch_dir / "state.json")
        resp = await client.get(f"/api/batches/{batch_id}/pipeline/stage/nonexistent")
        assert resp.status_code == 404


class TestResumePipeline:
    async def test_resume_not_paused_returns_409(self, client):
        batch_id, _ = await _create_batch(client)
        resp = await client.post(f"/api/batches/{batch_id}/pipeline/resume")
        assert resp.status_code == 409

    async def test_resume_paused_batch(self, client):
        batch_id, batch_dir = await _create_batch(client)
        db = get_db()
        await db.update_batch_state(batch_id, "paused")
        state = PipelineState.new()
        # Mark earlier stages as completed so current_stage is OCR
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.INTERLEAVING, {})
        state.mark_running(ProcessingStage.BLANK_REMOVAL)
        state.mark_completed(ProcessingStage.BLANK_REMOVAL, {})
        state.mark_running(ProcessingStage.OCR)
        state.mark_paused(ProcessingStage.OCR, "test pause")
        state.save(batch_dir / "state.json")

        with patch("scanbox.api.batches._run_processing", new_callable=AsyncMock):
            resp = await client.post(f"/api/batches/{batch_id}/pipeline/resume")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "resuming"
        assert data["from_stage"] == "ocr"


class TestRetryPipeline:
    async def test_retry_not_error_returns_409(self, client):
        batch_id, _ = await _create_batch(client)
        resp = await client.post(f"/api/batches/{batch_id}/pipeline/retry")
        assert resp.status_code == 409

    async def test_retry_error_batch(self, client):
        batch_id, batch_dir = await _create_batch(client)
        db = get_db()
        await db.update_batch_state(batch_id, "error")
        state = PipelineState.new()
        # Mark earlier stages as completed so current_stage is SPLITTING
        for s in [ProcessingStage.INTERLEAVING, ProcessingStage.BLANK_REMOVAL, ProcessingStage.OCR]:
            state.mark_running(s)
            state.mark_completed(s, {})
        state.mark_running(ProcessingStage.SPLITTING)
        state.mark_error(ProcessingStage.SPLITTING, "LLM timeout")
        state.save(batch_dir / "state.json")

        with patch("scanbox.api.batches._run_processing", new_callable=AsyncMock):
            resp = await client.post(f"/api/batches/{batch_id}/pipeline/retry")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "retrying"
        assert data["stage"] == "splitting"


class TestSkipPipelineStage:
    async def test_skip_not_paused_returns_409(self, client):
        batch_id, _ = await _create_batch(client)
        resp = await client.post(f"/api/batches/{batch_id}/pipeline/skip")
        assert resp.status_code == 409

    async def test_skip_paused_stage(self, client):
        batch_id, batch_dir = await _create_batch(client)
        db = get_db()
        await db.update_batch_state(batch_id, "paused")
        state = PipelineState.new()
        state.mark_running(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.INTERLEAVING, {})
        state.mark_running(ProcessingStage.BLANK_REMOVAL)
        state.mark_paused(ProcessingStage.BLANK_REMOVAL, "test pause")
        state.save(batch_dir / "state.json")

        with patch("scanbox.api.batches._run_processing", new_callable=AsyncMock):
            resp = await client.post(f"/api/batches/{batch_id}/pipeline/skip")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "skipped"
        assert data["stage"] == "blank_removal"

    async def test_skip_last_stage_transitions_to_review(self, client):
        batch_id, batch_dir = await _create_batch(client)
        db = get_db()
        await db.update_batch_state(batch_id, "paused")
        state = PipelineState.new()
        # Mark all stages as completed except the last one (naming)
        for stage in [
            ProcessingStage.INTERLEAVING,
            ProcessingStage.BLANK_REMOVAL,
            ProcessingStage.OCR,
            ProcessingStage.SPLITTING,
        ]:
            state.mark_running(stage)
            state.mark_completed(stage, {})
        state.mark_running(ProcessingStage.NAMING)
        state.mark_paused(ProcessingStage.NAMING, "test pause")
        state.save(batch_dir / "state.json")

        resp = await client.post(f"/api/batches/{batch_id}/pipeline/skip")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "skipped"
        assert data["stage"] == "naming"
        assert data["next_stage"] is None


class TestAdvancePipeline:
    async def test_advance_not_paused_returns_409(self, client):
        batch_id, _ = await _create_batch(client)
        resp = await client.post(f"/api/batches/{batch_id}/pipeline/advance")
        assert resp.status_code == 409

    async def test_advance_paused_batch(self, client):
        batch_id, batch_dir = await _create_batch(client)
        db = get_db()
        await db.update_batch_state(batch_id, "paused")
        state = PipelineState.new()
        # Mark earlier stages as completed so current_stage is SPLITTING
        for s in [ProcessingStage.INTERLEAVING, ProcessingStage.BLANK_REMOVAL, ProcessingStage.OCR]:
            state.mark_running(s)
            state.mark_completed(s, {})
        state.mark_running(ProcessingStage.SPLITTING)
        state.mark_paused(ProcessingStage.SPLITTING, "low confidence")
        state.stages["splitting"].result = {"documents": []}
        state.save(batch_dir / "state.json")

        with patch("scanbox.api.batches._run_processing", new_callable=AsyncMock):
            resp = await client.post(f"/api/batches/{batch_id}/pipeline/advance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "advancing"
        assert data["from_stage"] == "splitting"


class TestDLQEndpoints:
    async def test_list_dlq_empty(self, client):
        batch_id, batch_dir = await _create_batch(client)
        PipelineState.new().save(batch_dir / "state.json")
        resp = await client.get(f"/api/batches/{batch_id}/dlq")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_list_dlq_with_items(self, client):
        batch_id, batch_dir = await _create_batch(client)
        state = PipelineState.new()
        state.add_to_dlq(DLQItem(stage="splitting", document={"start_page": 1}, reason="low conf"))
        state.save(batch_dir / "state.json")

        resp = await client.get(f"/api/batches/{batch_id}/dlq")
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["stage"] == "splitting"

    async def test_retry_dlq_item(self, client):
        batch_id, batch_dir = await _create_batch(client)
        state = PipelineState.new()
        state.add_to_dlq(DLQItem(stage="splitting", document={}, reason="test"))
        state.save(batch_dir / "state.json")

        resp = await client.get(f"/api/batches/{batch_id}/dlq")
        item_id = resp.json()["items"][0]["id"]

        resp = await client.post(f"/api/batches/{batch_id}/dlq/{item_id}/retry")
        assert resp.status_code == 200
        assert resp.json()["status"] == "removed"

        # Verify item is gone
        resp = await client.get(f"/api/batches/{batch_id}/dlq")
        assert len(resp.json()["items"]) == 0

    async def test_retry_nonexistent_dlq_item_returns_404(self, client):
        batch_id, batch_dir = await _create_batch(client)
        PipelineState.new().save(batch_dir / "state.json")
        resp = await client.post(f"/api/batches/{batch_id}/dlq/dlq-nonexistent/retry")
        assert resp.status_code == 404

    async def test_discard_dlq_item(self, client):
        batch_id, batch_dir = await _create_batch(client)
        state = PipelineState.new()
        state.add_to_dlq(DLQItem(stage="splitting", document={}, reason="test"))
        state.save(batch_dir / "state.json")

        resp = await client.get(f"/api/batches/{batch_id}/dlq")
        item_id = resp.json()["items"][0]["id"]

        resp = await client.delete(f"/api/batches/{batch_id}/dlq/{item_id}")
        assert resp.status_code == 200

        # Verify gone
        resp = await client.get(f"/api/batches/{batch_id}/dlq")
        assert len(resp.json()["items"]) == 0

    async def test_discard_nonexistent_returns_404(self, client):
        batch_id, batch_dir = await _create_batch(client)
        PipelineState.new().save(batch_dir / "state.json")
        resp = await client.delete(f"/api/batches/{batch_id}/dlq/dlq-nonexistent")
        assert resp.status_code == 404


class TestDLQResolve:
    async def test_resolve_updates_splits_json(self, client):
        import json

        batch_id, batch_dir = await _create_batch(client)
        state = PipelineState.new()
        state.mark_completed(ProcessingStage.INTERLEAVING)
        state.mark_completed(ProcessingStage.BLANK_REMOVAL)
        state.mark_completed(ProcessingStage.OCR)
        state.mark_completed(ProcessingStage.SPLITTING, {"document_count": 2})
        state.add_to_dlq(
            DLQItem(
                stage="splitting",
                document={
                    "start_page": 3,
                    "end_page": 4,
                    "document_type": "Other",
                    "confidence": 0.3,
                },
                reason="Low confidence",
            )
        )
        state.save(batch_dir / "state.json")

        splits = [
            {
                "start_page": 1,
                "end_page": 2,
                "document_type": "Lab Results",
                "confidence": 0.95,
            },
            {
                "start_page": 3,
                "end_page": 4,
                "document_type": "Other",
                "confidence": 0.3,
            },
        ]
        (batch_dir / "splits.json").write_text(json.dumps(splits))

        item_id = state.dlq[0].id

        resp = await client.post(
            f"/api/batches/{batch_id}/dlq/{item_id}/resolve",
            json={
                "document_type": "Discharge Summary",
                "date_of_service": "2026-03-15",
                "facility": "Johns Hopkins",
                "provider": "Dr. Patel",
                "description": "Post-surgery discharge",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document"]["document_type"] == "Discharge Summary"
        assert data["document"]["user_edited"] is True
        assert data["document"]["confidence"] == 1.0

        # DLQ should be empty now
        resp = await client.get(f"/api/batches/{batch_id}/dlq")
        assert len(resp.json()["items"]) == 0

        # splits.json should be updated
        updated_splits = json.loads((batch_dir / "splits.json").read_text())
        assert updated_splits[1]["document_type"] == "Discharge Summary"
        assert updated_splits[1]["user_edited"] is True
        assert updated_splits[1]["confidence"] == 1.0

    async def test_resolve_nonexistent_returns_404(self, client):
        batch_id, batch_dir = await _create_batch(client)
        PipelineState.new().save(batch_dir / "state.json")
        resp = await client.post(
            f"/api/batches/{batch_id}/dlq/dlq-nonexistent/resolve",
            json={"document_type": "Lab Results"},
        )
        assert resp.status_code == 404

    async def test_resolve_without_splits_json(self, client):
        batch_id, batch_dir = await _create_batch(client)
        state = PipelineState.new()
        state.add_to_dlq(
            DLQItem(
                stage="splitting",
                document={
                    "start_page": 1,
                    "end_page": 2,
                    "document_type": "Other",
                    "confidence": 0.3,
                },
                reason="Low confidence",
            )
        )
        state.save(batch_dir / "state.json")
        item_id = state.dlq[0].id

        resp = await client.post(
            f"/api/batches/{batch_id}/dlq/{item_id}/resolve",
            json={"document_type": "Lab Results", "facility": "Quest Diagnostics"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document"]["document_type"] == "Lab Results"
        assert data["document"]["facility"] == "Quest Diagnostics"
        assert data["document"]["user_edited"] is True

    async def test_resolve_with_custom_confidence(self, client):
        batch_id, batch_dir = await _create_batch(client)
        state = PipelineState.new()
        state.add_to_dlq(
            DLQItem(
                stage="splitting",
                document={"start_page": 1, "end_page": 1, "document_type": "Other"},
                reason="Low confidence",
            )
        )
        state.save(batch_dir / "state.json")
        item_id = state.dlq[0].id

        resp = await client.post(
            f"/api/batches/{batch_id}/dlq/{item_id}/resolve",
            json={"document_type": "Lab Results", "confidence": 0.9},
        )
        assert resp.status_code == 200
        assert resp.json()["document"]["confidence"] == 0.9


class TestReprocessWithStartStage:
    async def test_reprocess_from_stage(self, client):
        batch_id, batch_dir = await _create_batch(client)
        db = get_db()
        await db.update_batch_state(batch_id, "review")
        # Create completed state
        state = PipelineState.new()
        for stage in [
            ProcessingStage.INTERLEAVING,
            ProcessingStage.BLANK_REMOVAL,
            ProcessingStage.OCR,
            ProcessingStage.SPLITTING,
            ProcessingStage.NAMING,
        ]:
            state.mark_running(stage)
            state.mark_completed(stage, {})
        state.save(batch_dir / "state.json")
        # Create fronts.pdf so reprocess sees it
        fronts = _make_pdf_bytes(3)
        (batch_dir / "fronts.pdf").write_bytes(fronts)

        with patch("scanbox.api.batches._run_processing", new_callable=AsyncMock):
            resp = await client.post(f"/api/batches/{batch_id}/reprocess?start_stage=splitting")
        assert resp.status_code == 202

        # Verify splitting and naming are reset to pending
        updated = PipelineState.load(batch_dir / "state.json")
        assert updated.stages["interleaving"].status.value == "completed"
        assert updated.stages["blank_removal"].status.value == "completed"
        assert updated.stages["ocr"].status.value == "completed"
        assert updated.stages["splitting"].status.value == "pending"
        assert updated.stages["naming"].status.value == "pending"

    async def test_reprocess_unknown_stage_returns_400(self, client):
        batch_id, batch_dir = await _create_batch(client)
        db = get_db()
        await db.update_batch_state(batch_id, "review")
        state = PipelineState.new()
        state.save(batch_dir / "state.json")
        fronts = _make_pdf_bytes(3)
        (batch_dir / "fronts.pdf").write_bytes(fronts)

        resp = await client.post(f"/api/batches/{batch_id}/reprocess?start_stage=nonexistent")
        assert resp.status_code == 400

    async def test_full_reprocess_preserves_user_overrides(self, client):
        import json

        batch_id, batch_dir = await _create_batch(client)
        db = get_db()
        await db.update_batch_state(batch_id, "review")
        fronts = _make_pdf_bytes(3)
        (batch_dir / "fronts.pdf").write_bytes(fronts)

        # Create a user_edited document
        await db.create_document(
            batch_id=batch_id,
            start_page=1,
            end_page=2,
            document_type="Lab Results",
            date_of_service="2026-01-01",
            facility="Quest",
            provider="Dr. Smith",
            description="CBC",
            confidence=0.9,
            filename="lab.pdf",
        )
        docs = await db.list_documents(batch_id)
        await db.update_document(docs[0]["id"], user_edited=True)

        with patch("scanbox.api.batches._run_processing", new_callable=AsyncMock):
            resp = await client.post(f"/api/batches/{batch_id}/reprocess")
        assert resp.status_code == 202

        overrides_path = batch_dir / "user_overrides.json"
        assert overrides_path.exists()
        overrides = json.loads(overrides_path.read_text())
        assert len(overrides) == 1
        assert overrides[0]["document_type"] == "Lab Results"
        assert overrides[0]["start_page"] == 1


class TestExclusionEndpoints:
    async def test_exclude_page(self, client):
        batch_id, batch_dir = await _create_batch(client)
        PipelineState.new().save(batch_dir / "state.json")
        resp = await client.post(f"/api/batches/{batch_id}/exclude/page/3")
        assert resp.status_code == 200
        assert 3 in resp.json()["excluded_pages"]

    async def test_include_page(self, client):
        batch_id, batch_dir = await _create_batch(client)
        state = PipelineState.new()
        state.exclude_page(3)
        state.save(batch_dir / "state.json")
        resp = await client.delete(f"/api/batches/{batch_id}/exclude/page/3")
        assert resp.status_code == 200
        assert 3 not in resp.json()["excluded_pages"]

    async def test_exclude_document(self, client):
        batch_id, batch_dir = await _create_batch(client)
        PipelineState.new().save(batch_dir / "state.json")
        resp = await client.post(f"/api/batches/{batch_id}/exclude/document/0")
        assert resp.status_code == 200
        assert 0 in resp.json()["excluded_documents"]

    async def test_include_document(self, client):
        batch_id, batch_dir = await _create_batch(client)
        state = PipelineState.new()
        state.exclude_document(0)
        state.save(batch_dir / "state.json")
        resp = await client.delete(f"/api/batches/{batch_id}/exclude/document/0")
        assert resp.status_code == 200
        assert 0 not in resp.json()["excluded_documents"]

    async def test_get_exclusions(self, client):
        batch_id, batch_dir = await _create_batch(client)
        state = PipelineState.new()
        state.exclude_page(1)
        state.exclude_document(0)
        state.save(batch_dir / "state.json")
        resp = await client.get(f"/api/batches/{batch_id}/exclusions")
        assert resp.status_code == 200
        assert resp.json()["excluded_pages"] == [1]
        assert resp.json()["excluded_documents"] == [0]

    async def test_get_exclusions_empty(self, client):
        batch_id, batch_dir = await _create_batch(client)
        PipelineState.new().save(batch_dir / "state.json")
        resp = await client.get(f"/api/batches/{batch_id}/exclusions")
        assert resp.status_code == 200
        assert resp.json()["excluded_pages"] == []
        assert resp.json()["excluded_documents"] == []

    async def test_exclude_page_idempotent(self, client):
        batch_id, batch_dir = await _create_batch(client)
        PipelineState.new().save(batch_dir / "state.json")
        await client.post(f"/api/batches/{batch_id}/exclude/page/3")
        resp = await client.post(f"/api/batches/{batch_id}/exclude/page/3")
        assert resp.status_code == 200
        assert resp.json()["excluded_pages"] == [3]

    async def test_nonexistent_batch_returns_404(self, client):
        resp = await client.get("/api/batches/nonexistent/exclusions")
        assert resp.status_code == 404
