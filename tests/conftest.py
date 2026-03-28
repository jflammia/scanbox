"""Shared test fixtures."""

from pathlib import Path

import pytest

from scanbox.config import Config

FIXTURES_DIR = Path(__file__).parent / "fixtures"


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
