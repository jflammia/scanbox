"""Shared batch import function -- creates DB records and writes PDFs.

Used by both the API import endpoint and pytest fixtures to inject
pre-made PDFs into the pipeline without a physical scanner.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pikepdf

from scanbox.database import Database


@dataclass
class ImportResult:
    """Result of importing PDFs into a new batch."""

    batch_id: str
    session_id: str
    person_id: str
    batch_dir: Path
    has_backs: bool
    fronts_page_count: int
    backs_page_count: int | None


async def import_batch(
    db: Database,
    data_dir: Path,
    fronts_bytes: bytes,
    backs_bytes: bytes | None = None,
    person_name: str = "Test Patient",
) -> ImportResult:
    """Import PDFs into a new session and batch.

    Creates person (if needed), session, and batch records in the database.
    Writes fronts.pdf and optionally backs.pdf to the batch directory.
    Sets batch state to 'backs_done' (if backs provided) or 'backs_skipped'.
    """
    # Find or create person
    person = await _find_or_create_person(db, person_name)

    # Create session and batch
    session = await db.create_session(person["id"])
    batch = await db.create_batch(session["id"])

    # Write PDFs to batch directory
    batch_dir = data_dir / "sessions" / session["id"] / "batches" / batch["id"]
    batch_dir.mkdir(parents=True, exist_ok=True)

    fronts_path = batch_dir / "fronts.pdf"
    fronts_path.write_bytes(fronts_bytes)
    fronts_page_count = _count_pages(fronts_bytes)

    backs_page_count = None
    has_backs = backs_bytes is not None
    if has_backs:
        backs_path = batch_dir / "backs.pdf"
        backs_path.write_bytes(backs_bytes)
        backs_page_count = _count_pages(backs_bytes)

    # Update batch state and page counts
    state = "backs_done" if has_backs else "backs_skipped"
    await db.update_batch_state(
        batch["id"],
        state,
        fronts_page_count=fronts_page_count,
        backs_page_count=backs_page_count or 0,
    )

    return ImportResult(
        batch_id=batch["id"],
        session_id=session["id"],
        person_id=person["id"],
        batch_dir=batch_dir,
        has_backs=has_backs,
        fronts_page_count=fronts_page_count,
        backs_page_count=backs_page_count,
    )


async def _find_or_create_person(db: Database, display_name: str) -> dict:
    """Look up a person by name, or create if not found."""
    persons = await db.list_persons()
    for p in persons:
        if p["display_name"] == display_name:
            return p
    return await db.create_person(display_name)


def _count_pages(pdf_bytes: bytes) -> int:
    """Count pages in a PDF from raw bytes."""
    pdf = pikepdf.Pdf.open(BytesIO(pdf_bytes))
    return len(pdf.pages)
