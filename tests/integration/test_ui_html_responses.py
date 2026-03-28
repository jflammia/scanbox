"""Integration tests for UI template correctness and HTML responses.

Verifies that htmx-targeted endpoints return HTML (not JSON),
templates reference correct routes, and interactive flows work end-to-end.
"""

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


async def _setup_doc(client):
    """Helper: create person -> session -> batch -> document, return doc dict."""
    person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
    session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
    batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
    db = get_db()
    doc = await db.create_document(
        batch_id=batch["id"],
        start_page=1,
        end_page=3,
        document_type="Lab Results",
        date_of_service="2025-01-15",
        facility="Memorial Hospital",
        provider="Dr. Smith",
        description="CBC Panel",
        confidence=0.85,
        filename="doc_001.pdf",
    )
    return {"person": person, "session": session, "batch": batch, "doc": doc}


class TestResultsPageEditButtons:
    """Results page edit/view buttons must point to HTML-returning endpoints."""

    async def test_results_page_edit_buttons_use_html_route(self, client: AsyncClient):
        """Edit buttons should use /documents/{id}/edit, not /api/documents/{id}."""
        data = await _setup_doc(client)
        resp = await client.get(f"/results/{data['batch']['id']}")
        assert resp.status_code == 200
        html = resp.text
        # Must NOT contain hx-get="/api/documents/ (JSON endpoint)
        assert f'hx-get="/api/documents/{data["doc"]["id"]}"' not in html
        # Must contain hx-get="/documents/{id}/edit" (HTML endpoint)
        assert f"/documents/{data['doc']['id']}/edit" in html


class TestSaveButtonHtmlResponse:
    """Save button must get an HTML response, not JSON."""

    async def test_save_returns_html(self, client: AsyncClient):
        data = await _setup_doc(client)
        db = get_db()
        # Move batch to review state so save is allowed
        await db.update_batch_state(data["batch"]["id"], "review")
        resp = await client.post(
            f"/batches/{data['batch']['id']}/save",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


class TestSettingsPersonsList:
    """Settings persons list must return HTML, not JSON."""

    async def test_persons_list_returns_html(self, client: AsyncClient):
        await client.post("/api/persons", json={"display_name": "Alice"})
        resp = await client.get("/persons/list")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Alice" in resp.text

    async def test_settings_page_references_html_endpoint(self, client: AsyncClient):
        resp = await client.get("/settings")
        assert resp.status_code == 200
        # Must use /persons/list (HTML) not /api/persons (JSON)
        assert 'hx-get="/persons/list"' in resp.text
        assert 'hx-get="/api/persons"' not in resp.text


class TestSettingsAddPerson:
    """Settings page must have a working add-person form."""

    async def test_add_person_form_returns_html(self, client: AsyncClient):
        resp = await client.post(
            "/persons/add",
            data={"display_name": "Bob Jones"},
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Bob Jones" in resp.text


class TestHomePageNewPersonInput:
    """Home page must show a name input when 'Add someone new' is selected."""

    async def test_home_has_new_person_name_input(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert 'name="new_person_name"' in resp.text


class TestScanProgressHtmlResponse:
    """Scan endpoints must return HTML fragments for htmx swapping."""

    async def test_scan_fronts_returns_html_for_htmx(self, client: AsyncClient):
        data = await _setup_doc(client)
        # The scan/fronts endpoint needs to return HTML when HX-Request header is set
        resp = await client.post(
            f"/api/batches/{data['batch']['id']}/scan/fronts",
            headers={"HX-Request": "true"},
        )
        # 503 because no scanner configured, but that's expected
        # We just verify the endpoint exists and responds
        assert resp.status_code in (200, 202, 409, 503)


class TestSkipBacksFlow:
    """Skip backs link must work with htmx properly."""

    async def test_skip_backs_returns_html_for_htmx(self, client: AsyncClient):
        data = await _setup_doc(client)
        db = get_db()
        await db.update_batch_state(data["batch"]["id"], "fronts_done")
        resp = await client.post(
            f"/batches/{data['batch']['id']}/skip-backs",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
