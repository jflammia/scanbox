"""Unit tests for the AI splitter's LLM call with mocked litellm."""

import json
from unittest.mock import MagicMock, patch

import pytest

from scanbox.pipeline.splitter import SplitValidationError, split_documents


def _mock_llm_response(content: str):
    """Create a mock litellm response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestSplitDocuments:
    @patch("scanbox.pipeline.splitter.litellm.acompletion")
    async def test_successful_split(self, mock_llm):
        result_json = json.dumps(
            [
                {
                    "start_page": 1,
                    "end_page": 2,
                    "document_type": "Lab Results",
                    "date_of_service": "2026-01-15",
                    "facility": "City Hospital",
                    "provider": "Dr. Lee",
                    "description": "Blood Panel",
                    "confidence": 0.95,
                },
                {
                    "start_page": 3,
                    "end_page": 3,
                    "document_type": "Letter",
                    "date_of_service": "unknown",
                    "facility": "unknown",
                    "provider": "unknown",
                    "description": "Referral Letter",
                    "confidence": 0.88,
                },
            ]
        )
        mock_llm.return_value = _mock_llm_response(result_json)

        page_texts = {1: "Lab report page 1", 2: "Lab report page 2", 3: "Dear Dr. Smith"}
        docs = await split_documents(page_texts, "Jane Doe")

        assert len(docs) == 2
        assert docs[0].document_type == "Lab Results"
        assert docs[0].start_page == 1
        assert docs[0].end_page == 2
        assert docs[1].document_type == "Letter"

    @patch("scanbox.pipeline.splitter.litellm.acompletion")
    async def test_dict_wrapper_format(self, mock_llm):
        """LLM returns {"documents": [...]} instead of bare list."""
        result_json = json.dumps(
            {
                "documents": [
                    {
                        "start_page": 1,
                        "end_page": 1,
                        "document_type": "Other",
                        "description": "Test",
                        "confidence": 0.5,
                    }
                ]
            }
        )
        mock_llm.return_value = _mock_llm_response(result_json)

        docs = await split_documents({1: "text"}, "Test")
        assert len(docs) == 1
        assert docs[0].document_type == "Other"

    @patch("scanbox.pipeline.splitter.litellm.acompletion")
    async def test_unexpected_format_raises(self, mock_llm):
        mock_llm.return_value = _mock_llm_response(json.dumps({"result": "bad"}))

        with pytest.raises(SplitValidationError, match="Unexpected response format"):
            await split_documents({1: "text"}, "Test")

    @patch("scanbox.pipeline.splitter.litellm.acompletion")
    async def test_gap_in_pages_raises(self, mock_llm):
        result_json = json.dumps(
            [
                {"start_page": 1, "end_page": 1, "confidence": 0.9},
                {"start_page": 3, "end_page": 3, "confidence": 0.9},
            ]
        )
        mock_llm.return_value = _mock_llm_response(result_json)

        with pytest.raises(SplitValidationError, match="gap"):
            await split_documents({1: "a", 2: "b", 3: "c"}, "Test")

    @patch("scanbox.pipeline.splitter.config")
    @patch("scanbox.pipeline.splitter.litellm.acompletion")
    async def test_uses_configured_model(self, mock_llm, mock_config):
        mock_config.llm_model_id.return_value = "gpt-4o-mini"

        result_json = json.dumps(
            [{"start_page": 1, "end_page": 1, "document_type": "Other", "confidence": 0.8}]
        )
        mock_llm.return_value = _mock_llm_response(result_json)

        await split_documents({1: "text"}, "Test")

        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"
