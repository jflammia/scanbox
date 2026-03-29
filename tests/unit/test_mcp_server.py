"""Unit tests for MCP server tools with mocked HTTP calls."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scanbox.mcp.server import (
    scanbox_adjust_boundaries,
    scanbox_create_session,
    scanbox_get_batch_status,
    scanbox_get_document,
    scanbox_get_pipeline_status,
    scanbox_get_scanner_status,
    scanbox_health_check,
    scanbox_list_documents,
    scanbox_list_sessions,
    scanbox_manage_persons,
    scanbox_reprocess_batch,
    scanbox_save_batch,
    scanbox_scan_backs,
    scanbox_scan_fronts,
    scanbox_skip_backs,
    scanbox_update_document,
)


def _mock_response(json_data: dict, status_code: int = 200):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    return resp


@pytest.fixture
def mock_client():
    """Patch httpx.AsyncClient for all MCP tool tests."""
    with patch("scanbox.mcp.server.httpx.AsyncClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        yield client


class TestHealthCheck:
    async def test_health_check(self, mock_client):
        mock_client.get.return_value = _mock_response({"status": "ok", "api": "ok"})
        result = await scanbox_health_check()
        assert result["status"] == "ok"
        mock_client.get.assert_called_once()


class TestScannerStatus:
    async def test_get_scanner_status_configured(self, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "192.168.1.100")
        result = await scanbox_get_scanner_status()
        assert result["scanner_ip"] == "192.168.1.100"
        assert result["message"] == "Scanner configured"

    async def test_get_scanner_status_not_configured(self, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "")
        result = await scanbox_get_scanner_status()
        assert result["scanner_ip"] == "not configured"


class TestPersons:
    async def test_list_persons(self, mock_client):
        mock_client.get.return_value = _mock_response({"items": [{"id": "john", "name": "John"}]})
        result = await scanbox_manage_persons(action="list")
        assert "items" in result

    async def test_create_person(self, mock_client):
        mock_client.post.return_value = _mock_response({"id": "jane", "display_name": "Jane"})
        result = await scanbox_manage_persons(action="create", display_name="Jane")
        assert result["display_name"] == "Jane"

    async def test_get_person(self, mock_client):
        mock_client.get.return_value = _mock_response({"id": "jane", "display_name": "Jane"})
        result = await scanbox_manage_persons(action="get", person_id="jane")
        assert result["id"] == "jane"

    async def test_delete_person(self, mock_client):
        mock_client.delete.return_value = MagicMock(status_code=204)
        result = await scanbox_manage_persons(action="delete", person_id="jane")
        assert result["deleted"] is True

    async def test_unknown_action(self, mock_client):
        result = await scanbox_manage_persons(action="invalid")
        assert "error" in result


class TestSessions:
    async def test_create_session(self, mock_client):
        mock_client.post.side_effect = [
            _mock_response({"id": "sess-1"}),
            _mock_response({"id": "batch-1"}),
        ]
        result = await scanbox_create_session(person_id="jane")
        assert result["session_id"] == "sess-1"
        assert result["batch_id"] == "batch-1"

    async def test_list_sessions(self, mock_client):
        mock_client.get.return_value = _mock_response({"items": []})
        result = await scanbox_list_sessions()
        assert "items" in result

    async def test_list_sessions_filtered(self, mock_client):
        mock_client.get.return_value = _mock_response({"items": []})
        await scanbox_list_sessions(person_id="jane")
        mock_client.get.assert_called_once()


class TestScanning:
    async def test_scan_fronts(self, mock_client):
        mock_client.post.return_value = _mock_response({"status": "scanning"})
        result = await scanbox_scan_fronts(batch_id="b1")
        assert result["status"] == "scanning"

    async def test_scan_backs(self, mock_client):
        mock_client.post.return_value = _mock_response({"status": "scanning"})
        result = await scanbox_scan_backs(batch_id="b1")
        assert result["status"] == "scanning"

    async def test_skip_backs(self, mock_client):
        mock_client.post.return_value = _mock_response({"state": "backs_skipped"})
        result = await scanbox_skip_backs(batch_id="b1")
        assert result["state"] == "backs_skipped"


class TestBatches:
    async def test_get_batch_status(self, mock_client):
        mock_client.get.return_value = _mock_response({"state": "review"})
        result = await scanbox_get_batch_status(batch_id="b1")
        assert result["state"] == "review"

    async def test_get_pipeline_status(self, mock_client):
        mock_client.get.return_value = _mock_response({"state": "processing", "stage": "ocr"})
        result = await scanbox_get_pipeline_status(batch_id="b1")
        assert result["state"] == "processing"

    async def test_reprocess_batch(self, mock_client):
        mock_client.post.return_value = _mock_response({"status": "reprocessing"})
        result = await scanbox_reprocess_batch(batch_id="b1")
        assert result["status"] == "reprocessing"


class TestDocuments:
    async def test_list_documents(self, mock_client):
        mock_client.get.return_value = _mock_response({"items": [{"id": "d1"}]})
        result = await scanbox_list_documents(batch_id="b1")
        assert len(result["items"]) == 1

    async def test_get_document(self, mock_client):
        mock_client.get.return_value = _mock_response({"id": "d1", "document_type": "Lab Results"})
        result = await scanbox_get_document(document_id="d1")
        assert result["document_type"] == "Lab Results"

    async def test_update_document(self, mock_client):
        mock_client.put.return_value = _mock_response(
            {"id": "d1", "document_type": "Radiology Report"}
        )
        result = await scanbox_update_document(document_id="d1", document_type="Radiology Report")
        assert result["document_type"] == "Radiology Report"

    async def test_update_document_partial(self, mock_client):
        mock_client.put.return_value = _mock_response({"id": "d1", "facility": "General"})
        await scanbox_update_document(document_id="d1", facility="General")
        # Verify only non-empty fields are sent
        call_args = mock_client.put.call_args
        sent_json = call_args.kwargs.get("json", call_args[1].get("json", {}))
        assert "facility" in sent_json


class TestBoundaries:
    async def test_adjust_boundaries(self, mock_client):
        mock_client.put.return_value = _mock_response({"boundaries": []})
        result = await scanbox_adjust_boundaries(
            batch_id="b1", boundaries=[{"start_page": 1, "end_page": 3}]
        )
        assert "boundaries" in result
        # Verify PUT (not POST) and /boundaries (not /splits)
        call_args = mock_client.put.call_args
        assert "/boundaries" in str(call_args)


class TestSave:
    async def test_save_batch(self, mock_client):
        mock_client.post.return_value = _mock_response({"status": "saved"})
        result = await scanbox_save_batch(batch_id="b1")
        assert result["status"] == "saved"
