"""Tests for the LLM splitting comparison feature."""

import json
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app
from scanbox.models import SplitDocument
from scanbox.pipeline.splitter import split_documents


@pytest.fixture
async def client(tmp_path, monkeypatch):
    """Create a test client with a temporary database."""
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def _create_batch_with_ocr(client: AsyncClient, tmp_path, monkeypatch) -> str:
    """Create a batch and write text_by_page.json so compare endpoint works."""
    # Create person + session + batch
    resp = await client.post("/api/persons", json={"display_name": "Test Patient"})
    person_id = resp.json()["id"]

    resp = await client.post("/api/sessions", json={"person_id": person_id})
    session_id = resp.json()["id"]

    resp = await client.post(f"/api/sessions/{session_id}/batches")
    batch_id = resp.json()["id"]

    # Write text_by_page.json in the batch directory
    data_dir = tmp_path / "data"
    batch_dir = data_dir / "sessions" / session_id / "batches" / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    text_data = {"1": "Lab results page one", "2": "Lab results page two", "3": "Dear Dr. Smith"}
    (batch_dir / "text_by_page.json").write_text(json.dumps(text_data))

    return batch_id


class TestCompareEndpoint:
    async def test_compare_requires_ocr_complete(self, client):
        """Batch without text_by_page.json should return 409."""
        resp = await client.post("/api/persons", json={"display_name": "Test Patient"})
        person_id = resp.json()["id"]
        resp = await client.post("/api/sessions", json={"person_id": person_id})
        session_id = resp.json()["id"]
        resp = await client.post(f"/api/sessions/{session_id}/batches")
        batch_id = resp.json()["id"]

        resp = await client.post(
            f"/api/batches/{batch_id}/compare",
            json={"models": ["model-a", "model-b"]},
        )
        assert resp.status_code == 409
        assert "OCR not complete" in resp.json()["detail"]

    @patch("scanbox.pipeline.splitter.split_documents")
    async def test_compare_returns_results_per_model(
        self, mock_split, client, tmp_path, monkeypatch
    ):
        """Each model should produce separate results in the response."""
        batch_id = await _create_batch_with_ocr(client, tmp_path, monkeypatch)

        mock_split.side_effect = [
            # Model A finds 2 documents
            [
                SplitDocument(
                    start_page=1, end_page=2, document_type="Lab Results", confidence=0.95
                ),
                SplitDocument(start_page=3, end_page=3, document_type="Letter", confidence=0.88),
            ],
            # Model B finds 1 document
            [
                SplitDocument(
                    start_page=1, end_page=3, document_type="Lab Results", confidence=0.7
                ),
            ],
        ]

        resp = await client.post(
            f"/api/batches/{batch_id}/compare",
            json={"models": ["model-a", "model-b"]},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["batch_id"] == batch_id
        assert data["total_pages"] == 3
        assert data["models_compared"] == 2
        assert "model-a" in data["results"]
        assert "model-b" in data["results"]

        # Model A
        assert data["results"]["model-a"]["document_count"] == 2
        assert data["results"]["model-a"]["status"] == "ok"

        # Model B
        assert data["results"]["model-b"]["document_count"] == 1
        assert data["results"]["model-b"]["status"] == "ok"

    @patch("scanbox.pipeline.splitter.split_documents")
    async def test_compare_handles_model_error(self, mock_split, client, tmp_path, monkeypatch):
        """If one model errors, the other should still succeed."""
        batch_id = await _create_batch_with_ocr(client, tmp_path, monkeypatch)

        mock_split.side_effect = [
            [SplitDocument(start_page=1, end_page=3, document_type="Other", confidence=0.8)],
            Exception("Model unavailable"),
        ]

        resp = await client.post(
            f"/api/batches/{batch_id}/compare",
            json={"models": ["good-model", "bad-model"]},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["results"]["good-model"]["status"] == "ok"
        assert data["results"]["good-model"]["document_count"] == 1

        assert data["results"]["bad-model"]["status"] == "error"
        assert "Model unavailable" in data["results"]["bad-model"]["error"]

    @patch("scanbox.pipeline.splitter.split_documents")
    async def test_compare_includes_avg_confidence(self, mock_split, client, tmp_path, monkeypatch):
        """Response should include average confidence per model."""
        batch_id = await _create_batch_with_ocr(client, tmp_path, monkeypatch)

        mock_split.return_value = [
            SplitDocument(start_page=1, end_page=2, document_type="Lab Results", confidence=0.9),
            SplitDocument(start_page=3, end_page=3, document_type="Letter", confidence=0.8),
        ]

        resp = await client.post(
            f"/api/batches/{batch_id}/compare",
            json={"models": ["test-model"]},
        )
        data = resp.json()
        assert data["results"]["test-model"]["avg_confidence"] == 0.85

    async def test_compare_batch_not_found(self, client):
        """Non-existent batch should return 404."""
        resp = await client.post(
            "/api/batches/nonexistent/compare",
            json={"models": ["model-a"]},
        )
        assert resp.status_code == 404


class TestSplitDocumentsModelOverride:
    @patch("scanbox.pipeline.splitter.litellm.acompletion")
    async def test_model_override_used(self, mock_llm):
        """When model_override is provided, it should be used instead of config."""
        result_json = json.dumps(
            [{"start_page": 1, "end_page": 1, "document_type": "Other", "confidence": 0.8}]
        )
        msg = MagicMock()
        msg.content = result_json
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        mock_llm.return_value = resp

        await split_documents({1: "text"}, "Test", model_override="custom/my-model")

        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["model"] == "custom/my-model"

    @patch("scanbox.pipeline.splitter.config")
    @patch("scanbox.pipeline.splitter.litellm.acompletion")
    async def test_no_override_uses_config(self, mock_llm, mock_config):
        """Without model_override, should use config.llm_model_id()."""
        mock_config.llm_model_id.return_value = "anthropic/claude-haiku-4-5-20251001"

        result_json = json.dumps(
            [{"start_page": 1, "end_page": 1, "document_type": "Other", "confidence": 0.8}]
        )
        msg = MagicMock()
        msg.content = result_json
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        mock_llm.return_value = resp

        await split_documents({1: "text"}, "Test")

        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["model"] == "anthropic/claude-haiku-4-5-20251001"
