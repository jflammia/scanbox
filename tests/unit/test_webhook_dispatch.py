"""Unit tests for webhook dispatch — verifies events are actually sent."""

from unittest.mock import AsyncMock, patch

import pytest

from scanbox.api.webhooks import _write_webhooks, dispatch_webhook_event


@pytest.fixture
def webhook_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data" / "config").mkdir(parents=True)
    return tmp_path / "data" / "config"


class TestDispatchWebhookEvent:
    @patch("scanbox.api.webhooks.httpx.AsyncClient")
    async def test_dispatches_to_matching_url(self, mock_cls, webhook_dir):
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post.return_value = AsyncMock(status_code=200)

        _write_webhooks(
            [
                {"id": "wh1", "url": "https://example.com/hook", "events": ["scan.completed"]},
            ]
        )

        await dispatch_webhook_event("scan.completed", {"batch_id": "b1"})

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "https://example.com/hook" in str(call_kwargs)
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["event"] == "scan.completed"
        assert payload["data"]["batch_id"] == "b1"

    @patch("scanbox.api.webhooks.httpx.AsyncClient")
    async def test_skips_non_matching_events(self, mock_cls, webhook_dir):
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        _write_webhooks(
            [
                {"id": "wh1", "url": "https://example.com/hook", "events": ["save.completed"]},
            ]
        )

        await dispatch_webhook_event("scan.completed", {"batch_id": "b1"})
        mock_client.post.assert_not_called()

    @patch("scanbox.api.webhooks.httpx.AsyncClient")
    async def test_dispatches_to_multiple_webhooks(self, mock_cls, webhook_dir):
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post.return_value = AsyncMock(status_code=200)

        _write_webhooks(
            [
                {"id": "wh1", "url": "https://a.com/hook", "events": ["scan.completed"]},
                {"id": "wh2", "url": "https://b.com/hook", "events": ["scan.completed"]},
            ]
        )

        await dispatch_webhook_event("scan.completed", {"batch_id": "b1"})
        assert mock_client.post.call_count == 2

    @patch("scanbox.api.webhooks.httpx.AsyncClient")
    async def test_hmac_signature_when_secret_set(self, mock_cls, webhook_dir):
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post.return_value = AsyncMock(status_code=200)

        _write_webhooks(
            [
                {
                    "id": "wh1",
                    "url": "https://example.com/hook",
                    "events": ["scan.completed"],
                    "secret": "my-secret",
                },
            ]
        )

        await dispatch_webhook_event("scan.completed", {"batch_id": "b1"})

        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert "X-Webhook-Signature" in headers

    @patch("scanbox.api.webhooks.httpx.AsyncClient")
    async def test_no_error_on_delivery_failure(self, mock_cls, webhook_dir):
        """Webhook delivery failures should be logged, not raised."""
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post.side_effect = Exception("Connection refused")

        _write_webhooks(
            [
                {"id": "wh1", "url": "https://example.com/hook", "events": ["scan.completed"]},
            ]
        )

        # Should not raise
        await dispatch_webhook_event("scan.completed", {"batch_id": "b1"})

    @patch("scanbox.api.webhooks.httpx.AsyncClient")
    async def test_no_webhooks_registered(self, mock_cls, webhook_dir):
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        _write_webhooks([])
        await dispatch_webhook_event("scan.completed", {"batch_id": "b1"})
        mock_client.post.assert_not_called()

    @patch("scanbox.api.webhooks.httpx.AsyncClient")
    async def test_payload_includes_timestamp(self, mock_cls, webhook_dir):
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post.return_value = AsyncMock(status_code=200)

        _write_webhooks(
            [
                {"id": "wh1", "url": "https://example.com/hook", "events": ["scan.completed"]},
            ]
        )

        await dispatch_webhook_event("scan.completed", {"batch_id": "b1"})

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "timestamp" in payload
