"""Unit tests for MCP resources with mocked HTTP calls."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scanbox.mcp.server import get_batch_resource, get_document_resource, get_document_text


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    return resp


@pytest.fixture
def mock_client():
    with patch("scanbox.mcp.server.httpx.AsyncClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        yield client


class TestBatchResource:
    async def test_get_batch_resource(self, mock_client):
        mock_client.get.side_effect = [
            _mock_response({"id": "b1", "state": "review", "session_id": "s1"}),
            _mock_response({"items": [{"id": "d1"}, {"id": "d2"}], "total": 2}),
        ]
        result = await get_batch_resource("b1")
        assert "b1" in result
        assert "review" in result


class TestDocumentResource:
    async def test_get_document_resource(self, mock_client):
        mock_client.get.return_value = _mock_response(
            {
                "id": "d1",
                "document_type": "Lab Results",
                "date_of_service": "2026-01-15",
                "facility": "City Hospital",
            }
        )
        result = await get_document_resource("d1")
        assert "Lab Results" in result
        assert "City Hospital" in result


class TestDocumentTextResource:
    async def test_get_document_text(self, mock_client):
        mock_client.get.return_value = _mock_response(
            {
                "pages": [
                    {"page": 1, "text": "Blood test results"},
                    {"page": 2, "text": "continued..."},
                ]
            }
        )
        result = await get_document_text("d1")
        assert "Blood test results" in result
