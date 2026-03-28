"""Test that API routes have meaningful OpenAPI descriptions."""

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


async def test_openapi_routes_have_summaries(client: AsyncClient):
    """All /api/ routes should have an OpenAPI summary or description."""
    resp = await client.get("/api/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()

    missing = []
    for path, methods in spec["paths"].items():
        if not path.startswith("/api/"):
            continue
        for method, details in methods.items():
            if method in ("parameters",):
                continue
            has_summary = bool(details.get("summary"))
            has_desc = bool(details.get("description"))
            if not has_summary and not has_desc:
                missing.append(f"{method.upper()} {path}")

    if missing:
        raise AssertionError(
            "API routes missing OpenAPI summary/description:\n"
            + "\n".join(f"  {m}" for m in missing)
        )


async def test_openapi_tags_present(client: AsyncClient):
    """OpenAPI spec should define tag groups."""
    resp = await client.get("/api/openapi.json")
    spec = resp.json()
    # Routes should be tagged
    for path, methods in spec["paths"].items():
        if not path.startswith("/api/"):
            continue
        for method, details in methods.items():
            if method in ("parameters",):
                continue
            assert details.get("tags"), f"{method.upper()} {path} has no tags"
