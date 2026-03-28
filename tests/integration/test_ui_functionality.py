"""Integration tests for UI functional routes and interactions."""

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app, get_db


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestScanStart:
    async def test_scan_start_creates_session_and_redirects(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        resp = await client.post(
            "/scan/start",
            data={"person_id": person["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/scan/" in resp.headers["location"]

    async def test_scan_start_with_new_person(self, client: AsyncClient):
        resp = await client.post(
            "/scan/start",
            data={"person_id": "__new__", "new_person_name": "Jane Smith"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/scan/" in resp.headers["location"]


class TestDocumentEditForm:
    async def test_edit_form_returns_html(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        db = get_db()
        doc = await db.create_document(
            batch_id=batch["id"],
            start_page=1,
            end_page=2,
            document_type="Radiology Report",
            date_of_service="2025-06-15",
            facility="Memorial Hospital",
            provider="Dr. Chen",
            description="CT Abdomen",
            confidence=0.95,
            filename="doc.pdf",
        )

        resp = await client.get(f"/documents/{doc['id']}/edit")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Radiology Report" in resp.text
        assert "<form" in resp.text or "<input" in resp.text

    async def test_edit_form_submit_updates_document(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        db = get_db()
        doc = await db.create_document(
            batch_id=batch["id"],
            start_page=1,
            end_page=2,
            document_type="Radiology Report",
            filename="doc.pdf",
        )

        resp = await client.post(
            f"/documents/{doc['id']}/edit",
            data={"document_type": "Lab Results", "description": "Blood Panel"},
        )
        assert resp.status_code == 200

        # Verify update persisted
        updated = await client.get(f"/api/documents/{doc['id']}")
        assert updated.json()["document_type"] == "Lab Results"
        assert updated.json()["description"] == "Blood Panel"


class TestDocumentCard:
    async def test_document_card_returns_html(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        db = get_db()
        doc = await db.create_document(
            batch_id=batch["id"],
            start_page=1,
            end_page=2,
            document_type="Radiology Report",
            filename="doc.pdf",
        )

        resp = await client.get(f"/documents/{doc['id']}/card")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Radiology Report" in resp.text


class TestSSEProgress:
    async def test_progress_endpoint_exists(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        resp = await client.get(f"/api/batches/{batch['id']}/progress")
        # SSE endpoint should return 200 with event-stream content type
        assert resp.status_code == 200


class TestStaticAssets:
    async def test_htmx_js_served(self, client: AsyncClient):
        resp = await client.get("/static/js/htmx.min.js")
        assert resp.status_code == 200

    async def test_alpine_js_served(self, client: AsyncClient):
        resp = await client.get("/static/js/alpine.min.js")
        assert resp.status_code == 200

    async def test_css_has_utility_classes(self, client: AsyncClient):
        resp = await client.get("/static/css/app.css")
        assert resp.status_code == 200
        # Should have real styles, not just variables
        assert "flex" in resp.text or "display" in resp.text
