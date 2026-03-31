"""Integration tests for web UI template routes."""

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


class TestHomeScreen:
    async def test_home_returns_html(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_home_contains_scanbox_title(self, client: AsyncClient):
        resp = await client.get("/")
        assert "ScanBox" in resp.text

    async def test_home_contains_start_scanning(self, client: AsyncClient):
        resp = await client.get("/")
        assert "Start Scanning" in resp.text


class TestScanWizard:
    async def test_scan_page_returns_html(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
        resp = await client.get(f"/scan/{session['id']}/{batch['id']}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_scan_page_contains_steps(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
        resp = await client.get(f"/scan/{session['id']}/{batch['id']}")
        assert "Scan Front Sides" in resp.text


class TestResultsScreen:
    async def test_results_returns_html(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
        resp = await client.get(f"/results/{batch['id']}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_results_shows_documents(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        db = get_db()
        await db.create_document(
            batch_id=batch["id"],
            start_page=1,
            end_page=2,
            document_type="Radiology Report",
            date_of_service="2025-06-15",
            facility="Memorial Hospital",
            provider="Dr. Chen",
            description="CT Abdomen",
            confidence=0.95,
            filename="2025-06-15_John-Doe_Radiology-Report.pdf",
        )
        resp = await client.get(f"/results/{batch['id']}")
        assert "Radiology Report" in resp.text
        assert "CT Abdomen" in resp.text

    async def test_results_shows_dlq_banner(self, client: AsyncClient, tmp_path):
        from scanbox.config import Config
        from scanbox.pipeline.state import DLQItem, PipelineState

        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        cfg = Config()
        batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch["id"]
        batch_dir.mkdir(parents=True, exist_ok=True)

        state = PipelineState.new()
        state.add_to_dlq(
            DLQItem(stage="naming", document={"type": "Lab Report"}, reason="Low confidence")
        )
        state.save(batch_dir / "state.json")

        resp = await client.get(f"/results/{batch['id']}")
        assert "1 item needs attention" in resp.text
        assert "Documents the AI" in resp.text

    async def test_results_no_dlq_banner_when_empty(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
        resp = await client.get(f"/results/{batch['id']}")
        assert "needs attention" not in resp.text


class TestSettingsScreen:
    async def test_settings_returns_html(self, client: AsyncClient):
        resp = await client.get("/settings")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_settings_contains_heading(self, client: AsyncClient):
        resp = await client.get("/settings")
        assert "Settings" in resp.text


class TestStaticFiles:
    async def test_css_served(self, client: AsyncClient):
        resp = await client.get("/static/css/app.css")
        assert resp.status_code == 200
