"""Tests for POST /api/batches/import endpoint."""

from io import BytesIO

import pikepdf
import pytest
from httpx import ASGITransport, AsyncClient

from scanbox.main import app


def _make_pdf_bytes(num_pages: int = 3) -> bytes:
    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.add_blank_page(page_size=(612, 792))
    buf = BytesIO()
    pdf.save(buf)
    return buf.getvalue()


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


class TestImportEndpoint:
    async def test_fronts_only(self, client):
        fronts = _make_pdf_bytes(3)
        resp = await client.post(
            "/api/batches/import",
            files={"fronts": ("fronts.pdf", fronts, "application/pdf")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "batch_id" in data
        assert data["has_backs"] is False
        assert data["fronts_pages"] == 3

    async def test_fronts_and_backs(self, client):
        fronts = _make_pdf_bytes(5)
        backs = _make_pdf_bytes(5)
        resp = await client.post(
            "/api/batches/import",
            files={
                "fronts": ("fronts.pdf", fronts, "application/pdf"),
                "backs": ("backs.pdf", backs, "application/pdf"),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["has_backs"] is True
        assert data["fronts_pages"] == 5
        assert data["backs_pages"] == 5

    async def test_custom_person_name(self, client):
        fronts = _make_pdf_bytes(1)
        resp = await client.post(
            "/api/batches/import",
            files={"fronts": ("fronts.pdf", fronts, "application/pdf")},
            data={"person_name": "Elena Martinez"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["person_id"] == "elena-martinez"

    async def test_invalid_pdf_returns_400(self, client):
        resp = await client.post(
            "/api/batches/import",
            files={"fronts": ("fronts.pdf", b"not a pdf", "application/pdf")},
        )
        assert resp.status_code == 400

    async def test_status_url_in_response(self, client):
        fronts = _make_pdf_bytes(1)
        resp = await client.post(
            "/api/batches/import",
            files={"fronts": ("fronts.pdf", fronts, "application/pdf")},
        )
        data = resp.json()
        assert "status_url" in data
        assert data["batch_id"] in data["status_url"]
