"""Tests for document classification used by boundary editor."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from scanbox.pipeline.splitter import classify_document_pages


class TestClassifyDocumentPages:
    @patch("scanbox.pipeline.splitter.Config")
    @patch("scanbox.pipeline.splitter.litellm")
    async def test_classifies_document(self, mock_litellm, MockConfig):
        mock_config = MockConfig.return_value
        mock_config.llm_model_id.return_value = "test-model"
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "document_type": "Lab Results",
                            "date_of_service": "2025-06-15",
                            "facility": "Quest Diagnostics",
                            "provider": "Dr. Smith",
                            "description": "Comprehensive Metabolic Panel",
                            "confidence": 0.92,
                        }
                    )
                )
            )
        ]
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)

        result = await classify_document_pages({1: "Blood test results", 2: "cont..."}, "John Doe")

        assert result["document_type"] == "Lab Results"
        assert result["date_of_service"] == "2025-06-15"
        assert result["facility"] == "Quest Diagnostics"
        assert result["confidence"] == 0.92

    @patch("scanbox.pipeline.splitter.Config")
    @patch("scanbox.pipeline.splitter.litellm")
    async def test_defaults_on_missing_fields(self, mock_litellm, MockConfig):
        mock_config = MockConfig.return_value
        mock_config.llm_model_id.return_value = "test-model"
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json.dumps({})))]
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)

        result = await classify_document_pages({1: "Some text"}, "Jane Doe")

        assert result["document_type"] == "Other"
        assert result["date_of_service"] == "unknown"
        assert result["confidence"] == 0.5

    @patch("scanbox.pipeline.splitter.Config")
    @patch("scanbox.pipeline.splitter.litellm")
    async def test_clamps_confidence(self, mock_litellm, MockConfig):
        mock_config = MockConfig.return_value
        mock_config.llm_model_id.return_value = "test-model"
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps({"confidence": 1.5})))
        ]
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)

        result = await classify_document_pages({1: "Text"}, "Test")

        assert result["confidence"] == 1.0
