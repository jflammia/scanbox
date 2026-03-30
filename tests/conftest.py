"""Shared test fixtures."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scanbox.api.import_batch import import_batch
from scanbox.config import Config
from scanbox.database import Database
from scanbox.pipeline.runner import PipelineContext

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SUITE_DIR = FIXTURES_DIR / "test_suite"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def escl_fixtures_dir() -> Path:
    return FIXTURES_DIR / "escl"


@pytest.fixture
def batch_fixtures_dir() -> Path:
    return FIXTURES_DIR / "batches"


@pytest.fixture
def page_fixtures_dir() -> Path:
    return FIXTURES_DIR / "pages"


@pytest.fixture
def tmp_config(tmp_path: Path) -> Config:
    """Config pointing at temp directories for isolated testing."""
    cfg = Config()
    cfg.INTERNAL_DATA_DIR = tmp_path / "data"
    cfg.OUTPUT_DIR = tmp_path / "output"
    cfg.INTERNAL_DATA_DIR.mkdir(parents=True)
    cfg.OUTPUT_DIR.mkdir(parents=True)
    return cfg


@pytest.fixture
async def db(tmp_path):
    """Isolated database for testing."""
    database = Database(tmp_path / "data" / "scanbox.db")
    await database.init()
    yield database
    await database.close()


@pytest.fixture
def load_test_pile(tmp_path, db):
    """Factory fixture: load a test suite pile into a ready-to-process state.

    Usage:
        batch_id, ctx = await load_test_pile("01-standard-clean")
        docs = await run_pipeline(ctx)
    """

    async def _load(
        pile_name: str,
        person_name: str | None = None,
    ) -> tuple[str, PipelineContext]:
        pile_dir = SUITE_DIR / pile_name

        # Read manifest for patient name
        manifest_path = pile_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if person_name is None:
            person_name = manifest["patient"]["name"]

        # Read PDF files
        fronts_bytes = (pile_dir / "fronts.pdf").read_bytes()
        backs_path = pile_dir / "backs.pdf"
        backs_bytes = backs_path.read_bytes() if backs_path.exists() else None

        # Import into database
        data_dir = tmp_path / "data"
        result = await import_batch(
            db=db,
            data_dir=data_dir,
            fronts_bytes=fronts_bytes,
            backs_bytes=backs_bytes,
            person_name=person_name,
        )

        # Build PipelineContext
        person = await db.get_person(result.person_id)
        output_dir = tmp_path / "output"
        output_dir.mkdir(exist_ok=True)

        ctx = PipelineContext(
            batch_dir=result.batch_dir,
            output_dir=output_dir,
            person_name=person["display_name"],
            person_slug=person["slug"],
            person_folder=person["folder_name"],
            batch_num=1,
            scan_date=datetime.now(UTC).strftime("%Y-%m-%d"),
            has_backs=result.has_backs,
        )

        return result.batch_id, ctx

    return _load


@pytest.fixture
def sample_splits_json() -> list[dict]:
    """A typical AI split response for a 5-page, 3-document batch."""
    return [
        {
            "start_page": 1,
            "end_page": 2,
            "document_type": "Radiology Report",
            "date_of_service": "2025-06-15",
            "facility": "Memorial Hospital",
            "provider": "Dr. Michael Chen",
            "description": "CT Abdomen and Pelvis",
            "confidence": 0.95,
        },
        {
            "start_page": 3,
            "end_page": 3,
            "document_type": "Discharge Summary",
            "date_of_service": "2025-03-22",
            "facility": "Johns Hopkins Hospital",
            "provider": "Dr. Robert Patel",
            "description": "Post-Appendectomy Discharge",
            "confidence": 0.92,
        },
        {
            "start_page": 4,
            "end_page": 5,
            "document_type": "Lab Results",
            "date_of_service": "2025-05-22",
            "facility": "Quest Diagnostics",
            "provider": "unknown",
            "description": "Comprehensive Metabolic Panel",
            "confidence": 0.88,
        },
    ]
