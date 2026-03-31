"""Tests that static assets and templates exist and are served correctly."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()

    from scanbox.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestStaticAssets:
    async def test_logo_svg_exists(self):
        path = Path(__file__).resolve().parent.parent.parent / "static" / "img" / "logo.svg"
        assert path.exists()
        content = path.read_text()
        assert "Scan" in content and "Box" in content

    async def test_pdf_placeholder_exists(self):
        path = (
            Path(__file__).resolve().parent.parent.parent / "static" / "img" / "pdf-placeholder.svg"
        )
        assert path.exists()

    async def test_scan_face_up_exists(self):
        path = Path(__file__).resolve().parent.parent.parent / "static" / "img" / "scan-face-up.svg"
        assert path.exists()
        assert "Face up" in path.read_text()

    async def test_scan_flip_exists(self):
        path = Path(__file__).resolve().parent.parent.parent / "static" / "img" / "scan-flip.svg"
        assert path.exists()
        assert "Flip" in path.read_text()

    async def test_idiomorph_js_exists(self):
        path = (
            Path(__file__).resolve().parent.parent.parent / "static" / "js" / "idiomorph-ext.min.js"
        )
        assert path.exists()

    async def test_static_images_served(self, client):
        resp = await client.get("/static/img/logo.svg")
        assert resp.status_code == 200

    async def test_idiomorph_served(self, client):
        resp = await client.get("/static/js/idiomorph-ext.min.js")
        assert resp.status_code == 200


class TestIconSVGs:
    @pytest.fixture
    def icons_dir(self):
        return Path(__file__).resolve().parent.parent.parent / "scanbox" / "templates" / "icons"

    @pytest.mark.parametrize(
        "icon_name",
        [
            "check-circle",
            "loader",
            "alert-triangle",
            "pencil",
            "wifi-off",
            "cog",
            "check",
            "eye",
        ],
    )
    async def test_icon_exists(self, icons_dir, icon_name):
        path = icons_dir / f"{icon_name}.svg"
        assert path.exists(), f"Missing icon: {icon_name}.svg"
        content = path.read_text()
        assert "<svg" in content
        assert 'aria-hidden="true"' in content


class TestComponentMacros:
    @pytest.fixture
    def components_dir(self):
        return (
            Path(__file__).resolve().parent.parent.parent / "scanbox" / "templates" / "components"
        )

    @pytest.mark.parametrize(
        "component_name",
        ["button", "status", "progress", "toast", "document_card"],
    )
    async def test_component_exists(self, components_dir, component_name):
        path = components_dir / f"{component_name}.html"
        assert path.exists(), f"Missing component: {component_name}.html"

    async def test_button_macro(self, components_dir):
        content = (components_dir / "button.html").read_text()
        assert "{% macro button" in content
        assert "primary" in content
        assert "secondary" in content

    async def test_status_macro(self, components_dir):
        content = (components_dir / "status.html").read_text()
        assert "{% macro status_badge" in content
        assert "check-circle" in content
        assert "loader" in content

    async def test_progress_macro(self, components_dir):
        content = (components_dir / "progress.html").read_text()
        assert "{% macro progress_bar" in content
        assert "progressbar" in content

    async def test_toast_macro(self, components_dir):
        content = (components_dir / "toast.html").read_text()
        assert "toastManager" in content
        assert "showToast" in content


class TestBaseTemplate:
    async def test_idiomorph_loaded(self, client):
        resp = await client.get("/")
        assert "idiomorph-ext.min.js" in resp.text

    async def test_morph_extension_enabled(self, client):
        resp = await client.get("/")
        assert 'hx-ext="morph"' in resp.text

    async def test_logo_in_header(self, client):
        resp = await client.get("/")
        assert "logo.svg" in resp.text

    async def test_toast_system_present(self, client):
        resp = await client.get("/")
        assert "toastManager()" in resp.text
        assert "show-toast" in resp.text

    async def test_scanner_polls_every_5s(self, client):
        resp = await client.get("/")
        assert "every 5s" in resp.text


class TestBoundaryEditorRoute:
    async def test_boundary_editor_page(self, client):
        from scanbox.main import get_db

        db = get_db()
        person = await db.create_person("Test User")
        session = await db.create_session(person["id"])
        batch = await db.create_batch(session["id"])
        await db.create_document(
            batch_id=batch["id"],
            start_page=1,
            end_page=3,
            document_type="Lab Results",
            filename="test.pdf",
        )
        await db.create_document(
            batch_id=batch["id"],
            start_page=4,
            end_page=5,
            document_type="Other",
            filename="test2.pdf",
        )

        resp = await client.get(f"/batches/{batch['id']}/boundaries/edit")
        assert resp.status_code == 200
        assert "Adjust Document Boundaries" in resp.text
        assert "boundaryEditor" in resp.text
