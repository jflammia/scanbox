"""Comprehensive UI tests covering every page, template, form, and htmx endpoint.

Tests all HTML views, htmx fragment endpoints, form submissions, and template
rendering with various data states. Uses httpx ASGI transport for fast,
deterministic testing without a real browser.
"""

from pathlib import Path

import pikepdf
import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app, get_db


def _make_pdf(path: Path, num_pages: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.pages.append(
            pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, 612, 792]))
        )
    pdf.save(path)


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "output").mkdir()

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
async def seeded(client: AsyncClient, tmp_path):
    """Seed DB with a person, session, batch in review, and two documents with files."""
    person = (await client.post("/api/persons", json={"display_name": "Jane Smith"})).json()
    session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
    batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

    db = get_db()
    await db.update_batch_state(batch["id"], "review")

    from scanbox.config import Config

    cfg = Config()
    batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch["id"]
    docs_dir = batch_dir / "documents"

    doc1 = await db.create_document(
        batch_id=batch["id"],
        start_page=1,
        end_page=3,
        document_type="Radiology Report",
        date_of_service="2025-08-10",
        facility="City Hospital",
        provider="Dr. Lee",
        description="MRI Brain",
        confidence=0.92,
        filename="doc1.pdf",
    )
    doc2 = await db.create_document(
        batch_id=batch["id"],
        start_page=4,
        end_page=5,
        document_type="Lab Results",
        date_of_service="unknown",
        facility="unknown",
        description="Document",
        confidence=0.55,
        filename="doc2.pdf",
    )

    _make_pdf(docs_dir / "doc1.pdf", 3)
    _make_pdf(docs_dir / "doc2.pdf", 2)
    _make_pdf(batch_dir / "combined.pdf", 5)

    import json

    text_data = {"1": "Page 1 text", "2": "Page 2", "3": "Page 3", "4": "Lab", "5": "Results"}
    (batch_dir / "text_by_page.json").write_text(json.dumps(text_data))

    return {
        "person": person,
        "session": session,
        "batch": batch,
        "doc1": doc1,
        "doc2": doc2,
        "batch_dir": batch_dir,
    }


# ---------------------------------------------------------------------------
# Base template & layout
# ---------------------------------------------------------------------------
class TestBaseLayout:
    async def test_header_branding(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "ScanBox" in resp.text
        assert 'href="/"' in resp.text

    async def test_settings_nav_link(self, client: AsyncClient):
        resp = await client.get("/")
        assert 'href="/settings"' in resp.text
        assert "Settings" in resp.text

    async def test_skip_to_content_link(self, client: AsyncClient):
        resp = await client.get("/")
        assert 'href="#main"' in resp.text
        assert "Skip to content" in resp.text

    async def test_scanner_status_htmx_polling(self, client: AsyncClient):
        resp = await client.get("/")
        assert 'hx-get="/scanner/status"' in resp.text
        assert "every 5s" in resp.text

    async def test_toast_container(self, client: AsyncClient):
        resp = await client.get("/")
        assert 'id="toast-container"' in resp.text
        assert "toastManager()" in resp.text

    async def test_easter_egg_footer(self, client: AsyncClient):
        resp = await client.get("/")
        assert "Made with" in resp.text
        assert "For her" in resp.text

    async def test_static_css_loaded(self, client: AsyncClient):
        resp = await client.get("/")
        assert "/static/css/app.css" in resp.text

    async def test_alpine_and_htmx_loaded(self, client: AsyncClient):
        resp = await client.get("/")
        assert "/static/js/alpine.min.js" in resp.text
        assert "/static/js/htmx.min.js" in resp.text

    async def test_static_css_serves(self, client: AsyncClient):
        resp = await client.get("/static/css/app.css")
        assert resp.status_code == 200

    async def test_static_alpine_serves(self, client: AsyncClient):
        resp = await client.get("/static/js/alpine.min.js")
        assert resp.status_code == 200

    async def test_static_htmx_serves(self, client: AsyncClient):
        resp = await client.get("/static/js/htmx.min.js")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------
class TestHomePage:
    async def test_renders_html(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_title(self, client: AsyncClient):
        resp = await client.get("/")
        assert "<title>ScanBox — Home</title>" in resp.text

    async def test_heading(self, client: AsyncClient):
        resp = await client.get("/")
        assert "Ready to scan" in resp.text

    async def test_setup_banner_shown_when_not_completed(self, client: AsyncClient):
        resp = await client.get("/")
        assert "Run Setup" in resp.text
        assert 'href="/setup"' in resp.text

    async def test_setup_banner_hidden_after_completion(self, client: AsyncClient):
        await client.post("/api/setup/complete")
        resp = await client.get("/")
        assert "Run Setup" not in resp.text

    async def test_person_dropdown(self, client: AsyncClient):
        await client.post("/api/persons", json={"display_name": "Alice"})
        resp = await client.get("/")
        assert "Alice" in resp.text
        assert 'name="person_id"' in resp.text

    async def test_add_new_person_option(self, client: AsyncClient):
        resp = await client.get("/")
        assert "__new__" in resp.text
        assert "Add someone new" in resp.text

    async def test_alpine_person_selector(self, client: AsyncClient):
        resp = await client.get("/")
        assert "selectedPerson" in resp.text
        assert "x-model=" in resp.text

    async def test_new_person_input_conditional(self, client: AsyncClient):
        resp = await client.get("/")
        assert (
            "selectedPerson === &#39;__new__&#39;" in resp.text
            or "selectedPerson === '__new__'" in resp.text
        )
        assert 'name="new_person_name"' in resp.text

    async def test_start_scanning_button(self, client: AsyncClient):
        resp = await client.get("/")
        assert "Start Scanning" in resp.text
        assert 'action="/scan/start"' in resp.text

    async def test_past_sessions_shown(self, seeded, client: AsyncClient):
        resp = await client.get("/")
        assert "Past sessions" in resp.text
        assert "Jane Smith" in resp.text

    async def test_past_sessions_hidden_when_empty(self, client: AsyncClient):
        resp = await client.get("/")
        assert "Past sessions" not in resp.text

    async def test_session_links_to_results(self, seeded, client: AsyncClient):
        resp = await client.get("/")
        batch_id = seeded["batch"]["id"]
        assert f"/results/{batch_id}" in resp.text


# ---------------------------------------------------------------------------
# Scan start form submission
# ---------------------------------------------------------------------------
class TestScanStart:
    async def test_start_with_existing_person(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Bob"})).json()
        resp = await client.post(
            "/scan/start",
            data={"person_id": person["id"], "new_person_name": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 303 or resp.status_code == 302 or resp.status_code == 200
        # Should redirect to scan page
        if resp.status_code in (302, 303):
            assert "/scan/" in resp.headers["location"]

    async def test_start_with_new_person(self, client: AsyncClient):
        resp = await client.post(
            "/scan/start",
            data={"person_id": "__new__", "new_person_name": "Charlie"},
            follow_redirects=False,
        )
        if resp.status_code in (302, 303):
            assert "/scan/" in resp.headers["location"]
        # Verify person was created
        persons = (await client.get("/api/persons")).json()["items"]
        names = [p["display_name"] for p in persons]
        assert "Charlie" in names


# ---------------------------------------------------------------------------
# Scan wizard page
# ---------------------------------------------------------------------------
class TestScanPage:
    async def test_renders(self, seeded, client: AsyncClient):
        sid = seeded["session"]["id"]
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/scan/{sid}/{bid}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_title(self, seeded, client: AsyncClient):
        sid = seeded["session"]["id"]
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/scan/{sid}/{bid}")
        assert "Scanning" in resp.text

    async def test_breadcrumb_home_link(self, seeded, client: AsyncClient):
        sid = seeded["session"]["id"]
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/scan/{sid}/{bid}")
        assert "Home" in resp.text
        assert 'href="/"' in resp.text

    async def test_three_steps_present(self, seeded, client: AsyncClient):
        sid = seeded["session"]["id"]
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/scan/{sid}/{bid}")
        assert "Scan Front Sides" in resp.text
        assert "Scan Back Sides" in resp.text
        assert "Processing" in resp.text

    async def test_alpine_state(self, seeded, client: AsyncClient):
        sid = seeded["session"]["id"]
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/scan/{sid}/{bid}")
        assert "currentStep: 1" in resp.text
        assert "step1Done: false" in resp.text
        assert "step2Done: false" in resp.text

    async def test_scan_fronts_button(self, seeded, client: AsyncClient):
        sid = seeded["session"]["id"]
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/scan/{sid}/{bid}")
        assert f'hx-post="/batches/{bid}/scan-fronts"' in resp.text
        assert 'hx-target="#step1-progress"' in resp.text

    async def test_scan_backs_button(self, seeded, client: AsyncClient):
        sid = seeded["session"]["id"]
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/scan/{sid}/{bid}")
        assert f'hx-post="/batches/{bid}/scan-backs"' in resp.text

    async def test_skip_backs_link(self, seeded, client: AsyncClient):
        sid = seeded["session"]["id"]
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/scan/{sid}/{bid}")
        assert f'hx-post="/batches/{bid}/skip-backs"' in resp.text
        assert "skip this" in resp.text

    async def test_step_transition_events(self, seeded, client: AsyncClient):
        sid = seeded["session"]["id"]
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/scan/{sid}/{bid}")
        assert "step1Done" in resp.text
        assert "step2Done" in resp.text

    async def test_progress_areas(self, seeded, client: AsyncClient):
        sid = seeded["session"]["id"]
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/scan/{sid}/{bid}")
        assert 'id="step1-progress"' in resp.text
        assert 'id="step2-progress"' in resp.text
        assert 'id="step3-progress"' in resp.text
        assert 'aria-live="polite"' in resp.text


# ---------------------------------------------------------------------------
# Skip backs htmx endpoint
# ---------------------------------------------------------------------------
class TestSkipBacks:
    async def test_skip_backs_returns_html(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "X"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        db = get_db()
        await db.update_batch_state(batch["id"], "fronts_done")

        resp = await client.post(f"/batches/{batch['id']}/skip-backs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Backs skipped" in resp.text

    async def test_skip_backs_wrong_state(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "X"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
        # Still in scanning_fronts
        resp = await client.post(f"/batches/{batch['id']}/skip-backs")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Results page
# ---------------------------------------------------------------------------
class TestResultsPage:
    async def test_renders(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_title(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert "Results" in resp.text

    async def test_document_count_heading(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert "2 documents found" in resp.text

    async def test_document_cards_rendered(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert "Radiology Report" in resp.text
        assert "Lab Results" in resp.text

    async def test_high_confidence_doc_metadata(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert "2025-08-10" in resp.text
        assert "City Hospital" in resp.text
        assert "MRI Brain" in resp.text

    async def test_low_confidence_warning_badge(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert "Needs review" in resp.text
        assert "border-status-warning" in resp.text

    async def test_low_confidence_fix_button(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert "Fix This" in resp.text

    async def test_high_confidence_edit_button(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert "Edit" in resp.text

    async def test_unknown_date_shows_warning(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert "Date unknown" in resp.text

    async def test_edit_htmx_targets(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        doc_id = seeded["doc1"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert f'hx-get="/documents/{doc_id}/edit"' in resp.text
        assert f'hx-target="#doc-{doc_id}"' in resp.text

    async def test_save_button(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert f'hx-post="/batches/{bid}/save"' in resp.text
        assert 'hx-target="#save-result"' in resp.text
        assert "Save" in resp.text

    async def test_save_result_area(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert 'id="save-result"' in resp.text

    async def test_user_edited_label(self, seeded, client: AsyncClient):
        db = get_db()
        await db.update_document(seeded["doc1"]["id"], user_edited=True)
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert "Edited by you" in resp.text

    async def test_breadcrumb(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert "Home" in resp.text

    async def test_grid_layout_classes(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.get(f"/results/{bid}")
        assert "grid-cols-1" in resp.text
        assert "sm:grid-cols-2" in resp.text
        assert "lg:grid-cols-3" in resp.text


# ---------------------------------------------------------------------------
# Document card fragment (htmx)
# ---------------------------------------------------------------------------
class TestDocumentCardFragment:
    async def test_renders_card(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        resp = await client.get(f"/documents/{doc_id}/card")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Radiology Report" in resp.text

    async def test_card_contains_metadata(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        resp = await client.get(f"/documents/{doc_id}/card")
        assert "2025-08-10" in resp.text
        assert "City Hospital" in resp.text
        assert "MRI Brain" in resp.text

    async def test_card_page_range(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        resp = await client.get(f"/documents/{doc_id}/card")
        assert "pp." in resp.text

    async def test_card_has_thumbnail(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        resp = await client.get(f"/documents/{doc_id}/card")
        assert f"/api/documents/{doc_id}/thumbnail" in resp.text
        assert "pdf-placeholder.svg" in resp.text

    async def test_card_edit_button(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        resp = await client.get(f"/documents/{doc_id}/card")
        assert f'hx-get="/documents/{doc_id}/edit"' in resp.text
        assert "Edit" in resp.text

    async def test_card_htmx_target(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        resp = await client.get(f"/documents/{doc_id}/card")
        assert f'id="doc-{doc_id}"' in resp.text

    async def test_card_not_found(self, client: AsyncClient):
        resp = await client.get("/documents/nonexistent/card")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Document edit form fragment (htmx)
# ---------------------------------------------------------------------------
class TestDocumentEditFragment:
    async def test_renders_form(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        resp = await client.get(f"/documents/{doc_id}/edit")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Edit Document" in resp.text

    async def test_form_fields_prefilled(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        resp = await client.get(f"/documents/{doc_id}/edit")
        assert 'value="Radiology Report"' in resp.text
        assert 'value="2025-08-10"' in resp.text
        assert 'value="City Hospital"' in resp.text
        assert 'value="Dr. Lee"' in resp.text
        assert 'value="MRI Brain"' in resp.text

    async def test_form_all_fields_present(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        resp = await client.get(f"/documents/{doc_id}/edit")
        assert 'name="document_type"' in resp.text
        assert 'name="date_of_service"' in resp.text
        assert 'name="facility"' in resp.text
        assert 'name="provider"' in resp.text
        assert 'name="description"' in resp.text

    async def test_form_htmx_post(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        resp = await client.get(f"/documents/{doc_id}/edit")
        assert f'hx-post="/documents/{doc_id}/edit"' in resp.text
        assert f'hx-target="#doc-{doc_id}"' in resp.text
        assert 'hx-swap="outerHTML"' in resp.text

    async def test_cancel_button(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        resp = await client.get(f"/documents/{doc_id}/edit")
        assert f'hx-get="/documents/{doc_id}/card"' in resp.text
        assert "Cancel" in resp.text

    async def test_save_button(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        resp = await client.get(f"/documents/{doc_id}/edit")
        assert "Save" in resp.text

    async def test_submit_edit_returns_card(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        resp = await client.post(
            f"/documents/{doc_id}/edit",
            data={
                "document_type": "Discharge Summary",
                "date_of_service": "2025-09-01",
                "facility": "New Hospital",
                "provider": "Dr. X",
                "description": "Updated desc",
            },
        )
        assert resp.status_code == 200
        assert "Discharge Summary" in resp.text
        assert "2025-09-01" in resp.text
        assert "New Hospital" in resp.text

    async def test_submit_edit_marks_user_edited(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        await client.post(
            f"/documents/{doc_id}/edit",
            data={
                "document_type": "Letter",
                "date_of_service": "",
                "facility": "",
                "provider": "",
                "description": "",
            },
        )
        doc = await get_db().get_document(doc_id)
        assert doc["user_edited"] is True

    async def test_submit_empty_fields_no_overwrite(self, seeded, client: AsyncClient):
        doc_id = seeded["doc1"]["id"]
        await client.post(
            f"/documents/{doc_id}/edit",
            data={
                "document_type": "",
                "date_of_service": "",
                "facility": "",
                "provider": "",
                "description": "",
            },
        )
        doc = await get_db().get_document(doc_id)
        # Empty fields should not overwrite existing values
        assert doc["document_type"] == "Radiology Report"

    async def test_edit_not_found(self, client: AsyncClient):
        resp = await client.get("/documents/nonexistent/edit")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Save batch htmx endpoint
# ---------------------------------------------------------------------------
class TestSaveBatchHtml:
    async def test_save_returns_success_html(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.post(f"/batches/{bid}/save")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Saved successfully" in resp.text
        assert "2 documents" in resp.text

    async def test_save_includes_home_link(self, seeded, client: AsyncClient):
        bid = seeded["batch"]["id"]
        resp = await client.post(f"/batches/{bid}/save")
        assert 'href="/"' in resp.text
        assert "Back to Home" in resp.text

    async def test_save_wrong_state_returns_409(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Z"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()
        resp = await client.post(f"/batches/{batch['id']}/save")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Scanner status htmx fragment
# ---------------------------------------------------------------------------
class TestScannerStatusFragment:
    async def test_no_scanner_configured(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "")
        resp = await client.get("/scanner/status")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "No scanner configured" in resp.text

    async def test_scanner_unreachable(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "192.168.255.255")
        resp = await client.get("/scanner/status")
        assert resp.status_code == 200
        assert "reach" in resp.text.lower() or "scanner" in resp.text.lower()


# ---------------------------------------------------------------------------
# Settings page
# ---------------------------------------------------------------------------
class TestSettingsPage:
    async def test_renders(self, client: AsyncClient):
        resp = await client.get("/settings")
        assert resp.status_code == 200
        assert "Settings" in resp.text

    async def test_title(self, client: AsyncClient):
        resp = await client.get("/settings")
        assert "<title>ScanBox — Settings</title>" in resp.text

    async def test_breadcrumb(self, client: AsyncClient):
        resp = await client.get("/settings")
        assert "Home" in resp.text

    async def test_people_section(self, client: AsyncClient):
        resp = await client.get("/settings")
        assert "People" in resp.text
        assert 'id="persons-list"' in resp.text
        assert 'hx-get="/persons/list"' in resp.text

    async def test_add_person_form(self, client: AsyncClient):
        resp = await client.get("/settings")
        assert "+ Add person" in resp.text
        assert "showForm" in resp.text
        assert 'hx-post="/persons/add"' in resp.text
        assert 'name="display_name"' in resp.text

    async def test_scanner_section_no_ip(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "")
        resp = await client.get("/settings")
        assert "Scanner" in resp.text
        assert 'name="scanner_ip"' in resp.text
        assert 'hx-post="/settings/scanner"' in resp.text

    async def test_scanner_section_with_ip(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "10.0.0.5")
        resp = await client.get("/settings")
        assert "10.0.0.5" in resp.text

    async def test_integrations_section_no_paperless(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("PAPERLESS_URL", "")
        resp = await client.get("/settings")
        assert "Integrations" in resp.text
        assert "Not configured" in resp.text

    async def test_integrations_section_with_paperless(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("PAPERLESS_URL", "http://paperless:8000")
        resp = await client.get("/settings")
        assert "Connected" in resp.text
        assert "paperless:8000" in resp.text


# ---------------------------------------------------------------------------
# Persons list htmx fragment
# ---------------------------------------------------------------------------
class TestPersonsListFragment:
    async def test_empty_state(self, client: AsyncClient):
        resp = await client.get("/persons/list")
        assert resp.status_code == 200
        assert "No people added yet" in resp.text

    async def test_with_persons(self, client: AsyncClient):
        await client.post("/api/persons", json={"display_name": "Alice"})
        await client.post("/api/persons", json={"display_name": "Bob"})
        resp = await client.get("/persons/list")
        assert "Alice" in resp.text
        assert "Bob" in resp.text

    async def test_add_person_returns_updated_list(self, client: AsyncClient):
        await client.post("/api/persons", json={"display_name": "Eve"})
        resp = await client.post("/persons/add", data={"display_name": "Mallory"})
        assert resp.status_code == 200
        assert "Mallory" in resp.text
        assert "Eve" in resp.text


# ---------------------------------------------------------------------------
# Setup wizard page
# ---------------------------------------------------------------------------
class TestSetupPage:
    async def test_renders(self, client: AsyncClient):
        resp = await client.get("/setup")
        assert resp.status_code == 200
        assert "Setup" in resp.text

    async def test_title(self, client: AsyncClient):
        resp = await client.get("/setup")
        assert "<title>ScanBox — Setup</title>" in resp.text

    async def test_step_indicator_dots(self, client: AsyncClient):
        resp = await client.get("/setup")
        assert "rounded-full" in resp.text
        # 6 step dots
        assert resp.text.count("w-3 h-3 rounded-full") == 6

    async def test_step1_scanner_check(self, client: AsyncClient):
        resp = await client.get("/setup")
        assert "Find your scanner" in resp.text
        assert "verify-scanner" in resp.text
        assert "discover-scanners" in resp.text

    async def test_step2_storage_check(self, client: AsyncClient):
        resp = await client.get("/setup")
        assert "Checking storage" in resp.text

    async def test_step3_ai_setup(self, client: AsyncClient):
        resp = await client.get("/setup")
        assert "AI document analysis" in resp.text
        assert "Anthropic" in resp.text
        assert "OpenAI" in resp.text
        assert "Ollama" in resp.text

    async def test_step4_paperless(self, client: AsyncClient):
        resp = await client.get("/setup")
        assert "PaperlessNGX" in resp.text
        assert "skip this" in resp.text.lower() or "No, skip" in resp.text

    async def test_step5_add_person(self, client: AsyncClient):
        resp = await client.get("/setup")
        assert "Who are these documents for" in resp.text
        assert 'hx-post="/setup/add-person"' in resp.text
        assert 'name="person_name"' in resp.text
        assert 'id="person-result"' in resp.text

    async def test_step6_done(self, client: AsyncClient):
        resp = await client.get("/setup")
        assert "ready to scan" in resp.text.lower()
        assert 'hx-post="/api/setup/complete"' in resp.text

    async def test_alpine_step_state(self, client: AsyncClient):
        resp = await client.get("/setup")
        assert "x-data" in resp.text
        assert "step:" in resp.text

    async def test_add_person_endpoint(self, client: AsyncClient):
        resp = await client.post("/setup/add-person", data={"person_name": "John Doe"})
        assert resp.status_code == 200
        assert "Added" in resp.text
        assert "John Doe" in resp.text

    async def test_complete_setup_endpoint(self, client: AsyncClient):
        resp = await client.post("/api/setup/complete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is True


# ---------------------------------------------------------------------------
# Practice run page
# ---------------------------------------------------------------------------
class TestPracticePage:
    async def test_renders(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert resp.status_code == 200
        assert "Practice Run" in resp.text

    async def test_title(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert "<title>ScanBox — Practice Run</title>" in resp.text

    async def test_breadcrumb(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert "Home" in resp.text

    async def test_step_indicator_dots(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert resp.text.count("w-3 h-3 rounded-full") == 4

    async def test_step1_single_page(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert "scan one page" in resp.text.lower()
        assert 'hx-post="/api/practice/step/1/complete"' in resp.text

    async def test_step2_double_sided(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert "double-sided" in resp.text.lower()
        assert 'hx-post="/api/practice/step/2/complete"' in resp.text

    async def test_step3_ai_splitting(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert "AI can sort" in resp.text
        assert 'hx-post="/api/practice/step/3/complete"' in resp.text

    async def test_step4_save(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert "save and check" in resp.text.lower()
        assert 'hx-post="/api/practice/step/4/complete"' in resp.text

    async def test_completion_screen(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert "Practice run complete" in resp.text
        assert "Scanner connected" in resp.text
        assert "Double-sided pages" in resp.text
        assert "AI document detection" in resp.text
        assert "Files saving" in resp.text

    async def test_alpine_state(self, client: AsyncClient):
        resp = await client.get("/practice")
        assert "step:" in resp.text
        assert "completed:" in resp.text

    async def test_step_completion_api(self, client: AsyncClient):
        resp = await client.post("/api/practice/step/1/complete")
        assert resp.status_code == 200
        status = (await client.get("/api/practice/status")).json()
        assert status["current_step"] == 2

    async def test_full_practice_flow(self, client: AsyncClient):
        for step in range(1, 5):
            resp = await client.post(f"/api/practice/step/{step}/complete")
            assert resp.status_code == 200
        status = (await client.get("/api/practice/status")).json()
        assert status["completed"] is True

    async def test_practice_reset(self, client: AsyncClient):
        await client.post("/api/practice/step/1/complete")
        resp = await client.post("/api/practice/reset")
        assert resp.status_code == 200
        status = (await client.get("/api/practice/status")).json()
        assert status["current_step"] == 1
        assert status["completed"] is False


# ---------------------------------------------------------------------------
# Single document results (singular form)
# ---------------------------------------------------------------------------
class TestResultsSingular:
    async def test_singular_document_text(self, client: AsyncClient):
        person = (await client.post("/api/persons", json={"display_name": "Solo"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        db = get_db()
        await db.update_batch_state(batch["id"], "review")
        await db.create_document(
            batch_id=batch["id"],
            start_page=1,
            end_page=1,
            document_type="Letter",
            filename="letter.pdf",
        )
        resp = await client.get(f"/results/{batch['id']}")
        assert "1 document found" in resp.text


# ---------------------------------------------------------------------------
# Save result template (singular/plural)
# ---------------------------------------------------------------------------
class TestSaveResultTemplate:
    async def test_single_doc_singular(self, client: AsyncClient, tmp_path):
        person = (await client.post("/api/persons", json={"display_name": "One"})).json()
        session = (await client.post("/api/sessions", json={"person_id": person["id"]})).json()
        batch = (await client.post(f"/api/sessions/{session['id']}/batches")).json()

        db = get_db()
        await db.update_batch_state(batch["id"], "review")
        await db.create_document(
            batch_id=batch["id"],
            start_page=1,
            end_page=1,
            document_type="Letter",
            filename="letter.pdf",
        )

        from scanbox.config import Config

        cfg = Config()
        batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch["id"]
        _make_pdf(batch_dir / "combined.pdf", 1)
        _make_pdf(batch_dir / "documents" / "letter.pdf", 1)

        resp = await client.post(f"/batches/{batch['id']}/save")
        assert "1 document" in resp.text
        # Should NOT say "documents" (plural)
        assert "1 documents" not in resp.text


# ---------------------------------------------------------------------------
# Full UI workflow: home → scan → results → edit → save
# ---------------------------------------------------------------------------
class TestFullUIWorkflow:
    async def test_home_to_results_to_edit_to_save(self, seeded, client: AsyncClient):
        """Test the complete UI workflow via htmx fragment endpoints."""
        bid = seeded["batch"]["id"]
        doc_id = seeded["doc1"]["id"]

        # 1. Home page shows session
        home = await client.get("/")
        assert "Jane Smith" in home.text

        # 2. Results page shows documents
        results = await client.get(f"/results/{bid}")
        assert "2 documents found" in results.text

        # 3. Click edit (htmx GET)
        edit_form = await client.get(f"/documents/{doc_id}/edit")
        assert "Edit Document" in edit_form.text
        assert 'value="Radiology Report"' in edit_form.text

        # 4. Submit edit (htmx POST)
        updated = await client.post(
            f"/documents/{doc_id}/edit",
            data={
                "document_type": "Progress Note",
                "date_of_service": "2025-10-01",
                "facility": "Updated Clinic",
                "provider": "Dr. New",
                "description": "Updated description",
            },
        )
        assert "Progress Note" in updated.text

        # 5. Cancel edit (htmx GET card)
        card = await client.get(f"/documents/{doc_id}/card")
        assert "Progress Note" in card.text  # Shows updated data

        # 6. Save (htmx POST)
        save_result = await client.post(f"/batches/{bid}/save")
        assert "Saved successfully" in save_result.text

        # 7. Home page after save
        home2 = await client.get("/")
        assert "Jane Smith" in home2.text
