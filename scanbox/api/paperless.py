"""PaperlessNGX API client for document upload and connectivity testing."""

from pathlib import Path

import httpx


class PaperlessClient:
    """Client for the PaperlessNGX REST API."""

    def __init__(self, base_url: str, api_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self.api_token}"}

    async def upload_document(
        self,
        pdf_path: Path,
        title: str,
        document_type: str | None = None,
        correspondent: str | None = None,
        tags: list[str] | None = None,
        created: str | None = None,
    ) -> bool:
        """Upload a PDF to PaperlessNGX. Returns True on success, False on failure."""
        data: dict[str, str] = {"title": title}
        if document_type:
            data["document_type"] = document_type
        if correspondent:
            data["correspondent"] = correspondent
        if created:
            data["created"] = created

        files = {"document": (pdf_path.name, pdf_path.read_bytes(), "application/pdf")}

        # Tags are sent as repeated form fields
        tag_entries: list[tuple[str, str]] = []
        if tags:
            for tag in tags:
                tag_entries.append(("tags", tag))

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/documents/post_document/",
                    headers=self._headers(),
                    data={**data, **dict(tag_entries)} if not tag_entries else data,
                    files={**files, **dict(tag_entries)} if tag_entries else files,
                )
                return resp.is_success
        except httpx.HTTPError:
            return False

    async def check_connection(self) -> bool:
        """Test connectivity to PaperlessNGX. Returns True if reachable and authenticated."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.base_url}/api/",
                    headers=self._headers(),
                )
                return resp.is_success
        except httpx.HTTPError:
            return False
