"""Integration tests for practice run and scan wizard htmx flows."""

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestPracticeRunTemplate:
    """Practice run buttons must use hx-swap='none' so JSON isn't rendered."""

    async def test_practice_buttons_use_swap_none(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert resp.status_code == 200
        html = resp.text
        # Each step button should have hx-swap="none" to prevent JSON rendering
        assert 'hx-swap="none"' in html

    async def test_practice_step_complete_from_htmx(self, client: AsyncClient):
        """Completing a practice step via htmx should work without error."""
        resp = await client.post(
            "/api/practice/step/1/complete",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200


class TestScanWizardHtmlResponses:
    """Scan wizard endpoints must return HTML when called via htmx."""

    async def test_scan_page_renders(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
        resp = await client.get(f"/scan/{session['id']}/{batch['id']}")
        assert resp.status_code == 200
        assert "Scan Front Sides" in resp.text

    async def test_scan_buttons_target_progress(self, client: AsyncClient):
        """Scan front/back buttons should target progress divs for feedback."""
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
        resp = await client.get(f"/scan/{session['id']}/{batch['id']}")
        html = resp.text
        assert "scan-fronts" in html
        assert "scan-backs" in html
        assert 'hx-target="#step1-progress"' in html
        assert 'hx-target="#step2-progress"' in html


class TestScannerStatusBar:
    """Base template should include a scanner status indicator."""

    async def test_base_has_scanner_status(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "scanner-status" in resp.text

    async def test_scanner_status_endpoint_returns_html(self, client: AsyncClient):
        resp = await client.get("/scanner/status")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
