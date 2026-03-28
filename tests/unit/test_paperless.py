"""Unit tests for PaperlessNGX API client."""

import httpx
import pytest
import respx

from scanbox.api.paperless import PaperlessClient


@pytest.fixture
def client():
    return PaperlessClient(
        base_url="http://paperless.local:8000",
        api_token="test-token-123",
    )


class TestPaperlessUpload:
    """Test document upload to PaperlessNGX."""

    @respx.mock
    async def test_upload_document(self, client, tmp_path):
        """Upload a PDF with metadata."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake content")

        route = respx.post("http://paperless.local:8000/api/documents/post_document/").mock(
            return_value=httpx.Response(200, text="OK")
        )

        result = await client.upload_document(
            pdf_path=pdf_path,
            title="Radiology Report - CT Abdomen",
            document_type="Radiology Report",
            correspondent="Memorial Hospital",
            tags=["medical-records", "person:john-doe"],
            created="2025-06-15",
        )

        assert route.called
        assert result is True

    @respx.mock
    async def test_upload_sets_auth_header(self, client, tmp_path):
        """Upload should use bearer token auth."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake content")

        route = respx.post("http://paperless.local:8000/api/documents/post_document/").mock(
            return_value=httpx.Response(200, text="OK")
        )

        await client.upload_document(pdf_path=pdf_path, title="Test Doc")

        request = route.calls[0].request
        assert request.headers["Authorization"] == "Token test-token-123"

    @respx.mock
    async def test_upload_failure_returns_false(self, client, tmp_path):
        """Upload failure should return False, not raise."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake content")

        respx.post("http://paperless.local:8000/api/documents/post_document/").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        result = await client.upload_document(pdf_path=pdf_path, title="Test Doc")
        assert result is False


class TestPaperlessConnectivity:
    """Test connectivity check."""

    @respx.mock
    async def test_check_connection_success(self, client):
        respx.get("http://paperless.local:8000/api/").mock(
            return_value=httpx.Response(200, json={"version": "2.0"})
        )

        result = await client.check_connection()
        assert result is True

    @respx.mock
    async def test_check_connection_failure(self, client):
        respx.get("http://paperless.local:8000/api/").mock(
            return_value=httpx.Response(401, json={"detail": "Unauthorized"})
        )

        result = await client.check_connection()
        assert result is False

    @respx.mock
    async def test_check_connection_network_error(self, client):
        respx.get("http://paperless.local:8000/api/").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await client.check_connection()
        assert result is False
