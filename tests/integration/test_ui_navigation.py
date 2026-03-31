"""Integration tests for UI navigation flows and data enrichment."""

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


class TestHomePageSessions:
    """Past sessions on home page must link to valid results pages."""

    async def test_home_shows_person_name_on_sessions(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Jane Doe"})).json()
        await client.post("/api/sessions", json={"person_id": person["id"]})
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "Jane Doe" in resp.text

    async def test_session_link_resolves_to_valid_page(self, client: AsyncClient):
        """Clicking a past session link should reach a valid page for the batch state."""
        from scanbox.main import get_db

        person = (await client.post("/api/persons", json={"display_name": "Test"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        # Scanning state links to scan wizard
        resp = await client.get("/")
        assert resp.status_code == 200
        assert f"/scan/{session['id']}/{batch['id']}" in resp.text

        # Review state links to results
        db = get_db()
        await db.update_batch_state(batch["id"], "review")
        resp = await client.get("/")
        assert f"/results/{batch['id']}" in resp.text


class TestSetupWizardPersistence:
    """Setup wizard should capture and persist the first person's name."""

    async def test_setup_person_creation(self, client: AsyncClient):
        """Step 5 'Add person' in setup should persist via htmx POST."""
        resp = await client.post(
            "/setup/add-person",
            data={"person_name": "Alice Smith"},
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Alice Smith" in resp.text

        # Verify person was created in the database
        persons = (await client.get("/api/persons")).json()
        names = [p["display_name"] for p in persons["items"]]
        assert "Alice Smith" in names

    async def test_setup_html_has_person_form(self, client: AsyncClient):
        """Setup step 5 must have a form that posts to /setup/add-person."""
        resp = await client.get("/setup")
        assert resp.status_code == 200
        assert 'name="person_name"' in resp.text
        assert "/setup/add-person" in resp.text
