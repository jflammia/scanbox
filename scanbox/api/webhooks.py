"""Webhook registration, listing, and deletion endpoints."""

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from scanbox.config import Config

router = APIRouter(tags=["webhooks"])

VALID_EVENTS = [
    "scan.completed",
    "processing.completed",
    "processing.stage_completed",
    "save.completed",
    "review.needed",
]


def _webhooks_path() -> Path:
    cfg = Config()
    return cfg.config_dir / "webhooks.json"


def _read_webhooks() -> list[dict]:
    path = _webhooks_path()
    if path.exists():
        return json.loads(path.read_text())
    return []


def _write_webhooks(webhooks: list[dict]) -> None:
    path = _webhooks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(webhooks))


class CreateWebhookRequest(BaseModel):
    url: str
    events: list[str]
    secret: str | None = None


@router.post("/api/webhooks", status_code=201)
async def create_webhook(req: CreateWebhookRequest):
    """Register a new webhook to receive event notifications."""
    webhooks = _read_webhooks()
    webhook_id = uuid.uuid4().hex[:12]
    webhook = {
        "id": webhook_id,
        "url": req.url,
        "events": req.events,
    }
    # Store secret internally but don't return it
    internal = {**webhook}
    if req.secret:
        internal["secret"] = req.secret
    webhooks.append(internal)
    _write_webhooks(webhooks)
    return webhook


@router.get("/api/webhooks")
async def list_webhooks():
    """List all registered webhooks."""
    webhooks = _read_webhooks()
    # Strip secrets from response
    items = [{"id": w["id"], "url": w["url"], "events": w["events"]} for w in webhooks]
    return {"items": items}


@router.delete("/api/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: str):
    """Remove a registered webhook."""
    webhooks = _read_webhooks()
    original_count = len(webhooks)
    webhooks = [w for w in webhooks if w["id"] != webhook_id]
    if len(webhooks) == original_count:
        raise HTTPException(status_code=404, detail="Webhook not found")
    _write_webhooks(webhooks)
    return Response(status_code=204)


@router.get("/api/webhooks/events")
async def list_event_types():
    """List available webhook event types."""
    return {"events": VALID_EVENTS}
