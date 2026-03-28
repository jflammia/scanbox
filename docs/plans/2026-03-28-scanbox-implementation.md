# ScanBox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained Docker app that controls an HP scanner via eSCL, processes scans through an automated pipeline (interleave, blank removal, OCR, AI split), and outputs organized medical records.

**Architecture:** FastAPI backend with Jinja2+htmx+Alpine.js frontend. Pipeline stages are independent pure functions with checkpointed state. eSCL scanner communication via direct HTTP. LLM integration via litellm. SQLite for session state.

**Tech Stack:** Python 3.13, FastAPI 0.135+, pikepdf, ocrmypdf 17+, litellm==1.82.6 (pinned — see `.claude/rules/tech-stack-2026.md`), httpx, htmx 2.0, Alpine.js 3.15, Tailwind CSS 4.2, jinja2-fragments

**Design spec:** `docs/design.md` — the authoritative reference for all behavior.

---

## Phased Delivery

This project is too large for a single implementation pass. It's broken into three phases, each producing working, testable software:

| Phase | What It Delivers | Testable Without |
|-------|-----------------|-----------------|
| **Phase 1: Pipeline Core** | All processing logic (interleave, blank detect, OCR, AI split, name, output) + test fixtures + unit/integration tests | Web UI, scanner, API |
| **Phase 2: API + Scanner + Web UI** | FastAPI API, eSCL scanner client, web UI for scanning + review + save, SSE progress, session state machine | PaperlessNGX, setup wizard, practice run |
| **Phase 3: Polish & Integrations** | First-run setup wizard, practice run, PaperlessNGX API integration, document boundary editor, metadata editing | Nothing — this is the complete app |

**Each phase has its own commit checkpoints.** Phase 1 can be reviewed and tested before Phase 2 begins.

---

## File Map

Every file that will be created or modified, grouped by responsibility:

### Core

| File | Responsibility |
|------|---------------|
| `scanbox/config.py` | Load all env vars with defaults, paths for internal/output storage |
| `scanbox/database.py` | SQLite schema, CRUD for sessions/batches/documents/persons |
| `scanbox/models.py` | Pydantic models shared across modules (BatchState, Document, Person, SplitResult) |

### Scanner

| File | Responsibility |
|------|---------------|
| `scanbox/scanner/escl.py` | eSCL HTTP client: capabilities, status, start job, get pages, cancel |
| `scanbox/scanner/models.py` | Scanner data models (ScannerCapabilities, ScannerStatus, ScanJob) |

### Pipeline

| File | Responsibility |
|------|---------------|
| `scanbox/pipeline/interleave.py` | Merge fronts + reversed backs into correct page order |
| `scanbox/pipeline/blank_detect.py` | Detect and remove blank pages by ink coverage |
| `scanbox/pipeline/ocr.py` | OCR via ocrmypdf, extract per-page text to JSON |
| `scanbox/pipeline/splitter.py` | LLM-based document boundary detection + validation |
| `scanbox/pipeline/namer.py` | Generate sanitized medical-professional filenames |
| `scanbox/pipeline/output.py` | Write to archive, medical-records, Index.csv |
| `scanbox/pipeline/runner.py` | Orchestrate stages with checkpoint state machine |

### API

| File | Responsibility |
|------|---------------|
| `scanbox/main.py` | FastAPI app, mount routers, static files, templates, startup |
| `scanbox/api/persons.py` | CRUD person profiles |
| `scanbox/api/sessions.py` | Create/list/get sessions |
| `scanbox/api/scanning.py` | Trigger scans, SSE progress stream |
| `scanbox/api/batches.py` | Batch status, reprocess, replace backs |
| `scanbox/api/documents.py` | List/edit/save documents, thumbnail serving |
| `scanbox/api/setup.py` | First-run setup and practice run endpoints |
| `scanbox/api/sse.py` | SSE event bus for progress communication |
| `scanbox/api/paperless.py` | PaperlessNGX API client (upload, tags, types) |

### Frontend

| File | Responsibility |
|------|---------------|
| `scanbox/templates/base.html` | Layout shell, nav, Alpine.js + Tailwind |
| `scanbox/templates/index.html` | Home: session list, new session, past sessions |
| `scanbox/templates/scan.html` | Wizard: scan fronts → flip → scan backs → process |
| `scanbox/templates/results.html` | Card layout: document cards, edit, save |
| `scanbox/templates/setup.html` | First-run setup wizard |
| `scanbox/templates/practice.html` | Guided practice run |
| `scanbox/templates/settings.html` | Person management, scanner/LLM/PaperlessNGX config |
| `static/css/app.css` | Custom styles beyond Tailwind defaults |

### Tests

| File | Responsibility |
|------|---------------|
| `tests/conftest.py` | Shared fixtures, tmp dirs, mock eSCL server factory |
| `tests/generate_fixtures.py` | Build synthetic medical PDFs for testing |
| `tests/unit/test_interleave.py` | Interleave algorithm correctness |
| `tests/unit/test_blank_detect.py` | Blank page detection accuracy |
| `tests/unit/test_ocr.py` | OCR text extraction |
| `tests/unit/test_splitter.py` | AI split validation logic |
| `tests/unit/test_namer.py` | Filename generation/sanitization |
| `tests/unit/test_output.py` | Output file writing |
| `tests/unit/test_escl.py` | eSCL XML parsing, job creation |
| `tests/integration/test_pipeline.py` | Full pipeline: PDF in → named docs out |
| `tests/integration/test_escl_integration.py` | Mock eSCL server scan cycle |
| `tests/integration/test_sessions.py` | Session lifecycle in SQLite |

---

## Phase 1: Pipeline Core

All processing logic, tested independently of the web UI and scanner.

### Task 1: Config and Models

**Files:**
- Create: `scanbox/config.py`
- Create: `scanbox/models.py`

- [ ] **Step 1: Write config.py**

```python
"""Configuration loaded from environment variables with sensible defaults."""

import os
from pathlib import Path


class Config:
    # Scanner
    SCANNER_IP: str = os.getenv("SCANNER_IP", "")

    # LLM
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")

    # PaperlessNGX (optional)
    PAPERLESS_URL: str = os.getenv("PAPERLESS_URL", "")
    PAPERLESS_API_TOKEN: str = os.getenv("PAPERLESS_API_TOKEN", "")

    # Storage
    INTERNAL_DATA_DIR: Path = Path(os.getenv("INTERNAL_DATA_DIR", "/app/data"))
    OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", "/output"))

    # Pipeline
    BLANK_PAGE_THRESHOLD: float = float(os.getenv("BLANK_PAGE_THRESHOLD", "0.01"))
    OCR_LANGUAGE: str = os.getenv("OCR_LANGUAGE", "eng")
    DEFAULT_DPI: int = int(os.getenv("DEFAULT_DPI", "300"))

    @property
    def sessions_dir(self) -> Path:
        return self.INTERNAL_DATA_DIR / "sessions"

    @property
    def config_dir(self) -> Path:
        return self.INTERNAL_DATA_DIR / "config"

    @property
    def db_path(self) -> Path:
        return self.INTERNAL_DATA_DIR / "scanbox.db"

    @property
    def archive_dir(self) -> Path:
        return self.OUTPUT_DIR / "archive"

    @property
    def medical_records_dir(self) -> Path:
        return self.OUTPUT_DIR / "medical-records"

    def llm_model_id(self) -> str:
        """Return the litellm model identifier based on provider + model."""
        if self.LLM_MODEL:
            return self.LLM_MODEL
        defaults = {
            "anthropic": "claude-haiku-4-5-20251001",
            "openai": "gpt-4o-mini",
            "ollama": "ollama/llama3.1",
        }
        return defaults.get(self.LLM_PROVIDER, "claude-haiku-4-5-20251001")


config = Config()
```

- [ ] **Step 2: Write models.py**

```python
"""Shared Pydantic models used across pipeline, API, and database."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class BatchState(str, Enum):
    SCANNING_FRONTS = "scanning_fronts"
    FRONTS_DONE = "fronts_done"
    SCANNING_BACKS = "scanning_backs"
    BACKS_DONE = "backs_done"
    BACKS_SKIPPED = "backs_skipped"
    PROCESSING = "processing"
    REVIEW = "review"
    SAVED = "saved"
    ERROR = "error"


class ProcessingStage(str, Enum):
    INTERLEAVING = "interleaving"
    BLANK_REMOVAL = "blank_removal"
    OCR = "ocr"
    SPLITTING = "splitting"
    NAMING = "naming"
    DONE = "done"


class Person(BaseModel):
    id: str
    display_name: str
    slug: str
    folder_name: str
    created: datetime


class SplitDocument(BaseModel):
    start_page: int
    end_page: int
    document_type: str = "Other"
    date_of_service: str = "unknown"
    facility: str = "unknown"
    provider: str = "unknown"
    description: str = "Document"
    confidence: float = 1.0
    user_edited: bool = False


class BatchInfo(BaseModel):
    id: str
    session_id: str
    state: BatchState
    processing_stage: ProcessingStage | None = None
    fronts_page_count: int = 0
    backs_page_count: int = 0
    documents: list[SplitDocument] = Field(default_factory=list)
    created: datetime
    error_message: str | None = None


DOCUMENT_TYPES = [
    "Radiology Report",
    "Discharge Summary",
    "Care Plan",
    "Lab Results",
    "Letter",
    "Operative Report",
    "Progress Note",
    "Pathology Report",
    "Prescription",
    "Insurance",
    "Billing",
    "Other",
]
```

- [ ] **Step 3: Verify imports work**

Run: `cd /Users/justin/Code/scanbox && python -c "from scanbox.config import config; from scanbox.models import BatchState, SplitDocument; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add scanbox/config.py scanbox/models.py
git commit -m "feat: add config and shared Pydantic models"
```

---

### Task 2: Test Fixture Generator

**Files:**
- Create: `tests/generate_fixtures.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/escl/capabilities.xml`
- Create: `tests/fixtures/escl/status_idle.xml`

- [ ] **Step 1: Write eSCL XML fixtures**

```xml
<!-- tests/fixtures/escl/capabilities.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<scan:ScannerCapabilities xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                          xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
  <pwg:Version>2.63</pwg:Version>
  <pwg:MakeAndModel>HP Color LaserJet MFP M283cdw</pwg:MakeAndModel>
  <scan:Platen>
    <scan:PlatenInputCaps>
      <scan:MinWidth>0</scan:MinWidth>
      <scan:MaxWidth>2550</scan:MaxWidth>
      <scan:MinHeight>0</scan:MinHeight>
      <scan:MaxHeight>3508</scan:MaxHeight>
      <scan:SettingProfiles>
        <scan:SettingProfile>
          <scan:ColorModes><scan:ColorMode>RGB24</scan:ColorMode></scan:ColorModes>
          <scan:SupportedResolutions>
            <scan:DiscreteResolutions>
              <scan:DiscreteResolution><scan:XResolution>300</scan:XResolution><scan:YResolution>300</scan:YResolution></scan:DiscreteResolution>
            </scan:DiscreteResolutions>
          </scan:SupportedResolutions>
          <scan:DocumentFormats>
            <pwg:DocumentFormat>application/pdf</pwg:DocumentFormat>
            <pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>
          </scan:DocumentFormats>
        </scan:SettingProfile>
      </scan:SettingProfiles>
    </scan:PlatenInputCaps>
  </scan:Platen>
  <scan:Adf>
    <scan:AdfSimplexInputCaps>
      <scan:MinWidth>0</scan:MinWidth>
      <scan:MaxWidth>2550</scan:MaxWidth>
      <scan:MinHeight>0</scan:MinHeight>
      <scan:MaxHeight>3300</scan:MaxHeight>
      <scan:SettingProfiles>
        <scan:SettingProfile>
          <scan:ColorModes><scan:ColorMode>RGB24</scan:ColorMode></scan:ColorModes>
          <scan:SupportedResolutions>
            <scan:DiscreteResolutions>
              <scan:DiscreteResolution><scan:XResolution>300</scan:XResolution><scan:YResolution>300</scan:YResolution></scan:DiscreteResolution>
            </scan:DiscreteResolutions>
          </scan:SupportedResolutions>
          <scan:DocumentFormats>
            <pwg:DocumentFormat>application/pdf</pwg:DocumentFormat>
            <pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>
          </scan:DocumentFormats>
        </scan:SettingProfile>
      </scan:SettingProfiles>
    </scan:AdfSimplexInputCaps>
  </scan:Adf>
</scan:ScannerCapabilities>
```

```xml
<!-- tests/fixtures/escl/status_idle.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<scan:ScannerStatus xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                    xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
  <pwg:Version>2.63</pwg:Version>
  <pwg:State>Idle</pwg:State>
  <scan:AdfState>ScannerAdfLoaded</scan:AdfState>
</scan:ScannerStatus>
```

- [ ] **Step 2: Write fixture generator**

```python
"""Generate synthetic medical document PDFs for testing.

Creates realistic-looking pages with letterheads, dates, and report structures
but containing no real PHI. These are used by unit and integration tests.
"""

from pathlib import Path

import pikepdf
from PIL import Image, ImageDraw, ImageFont


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def create_text_page_pdf(text: str, output_path: Path, dpi: int = 300) -> None:
    """Create a single-page PDF with the given text content."""
    # US Letter at specified DPI
    width = int(8.5 * dpi)
    height = int(11 * dpi)

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # Use default font, draw text starting near top-left
    y_offset = int(0.5 * dpi)
    x_offset = int(0.75 * dpi)
    for line in text.split("\n"):
        draw.text((x_offset, y_offset), line, fill="black")
        y_offset += int(0.18 * dpi)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PDF", resolution=dpi)


def create_blank_page_pdf(output_path: Path, dpi: int = 300) -> None:
    """Create a blank white page PDF."""
    width = int(8.5 * dpi)
    height = int(11 * dpi)
    img = Image.new("RGB", (width, height), "white")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PDF", resolution=dpi)


def create_near_blank_page_pdf(output_path: Path, dpi: int = 300) -> None:
    """Create a nearly blank page with a small smudge (<1% ink coverage)."""
    width = int(8.5 * dpi)
    height = int(11 * dpi)
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    # Small smudge in corner
    draw.ellipse([10, 10, 30, 30], fill="gray")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PDF", resolution=dpi)


def merge_pdfs(input_paths: list[Path], output_path: Path) -> None:
    """Merge multiple single-page PDFs into one multi-page PDF."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged = pikepdf.Pdf.new()
    for path in input_paths:
        src = pikepdf.Pdf.open(path)
        merged.pages.extend(src.pages)
    merged.save(output_path)


RADIOLOGY_REPORT_P1 = """MEMORIAL HOSPITAL
Department of Radiology

RADIOLOGY REPORT

Patient: John Doe
DOB: 01/15/1955
Date of Service: 06/15/2025
Ordering Physician: Dr. Sarah Johnson
Exam: CT Abdomen and Pelvis with Contrast

CLINICAL HISTORY: Abdominal pain, rule out appendicitis.

TECHNIQUE: CT of the abdomen and pelvis was performed with IV contrast.

FINDINGS:
The liver, spleen, pancreas, and adrenal glands are unremarkable.
No evidence of appendicitis. The appendix measures 5mm in diameter.
No free fluid or free air. No lymphadenopathy.
"""

RADIOLOGY_REPORT_P2 = """MEMORIAL HOSPITAL — Page 2

IMPRESSION:
1. No evidence of acute appendicitis.
2. Normal CT of the abdomen and pelvis.

Electronically signed by:
Dr. Michael Chen, MD
Board Certified Radiologist
06/15/2025 14:30
"""

DISCHARGE_SUMMARY_P1 = """JOHNS HOPKINS HOSPITAL
Baltimore, MD 21287

DISCHARGE SUMMARY

Patient: John Doe
MRN: 1234567
Admission Date: 03/20/2025
Discharge Date: 03/22/2025
Attending: Dr. Robert Patel

PRINCIPAL DIAGNOSIS: Acute appendicitis, status post laparoscopic appendectomy

HOSPITAL COURSE:
Patient presented to the ED with acute right lower quadrant pain.
CT confirmed acute appendicitis. Taken to OR for laparoscopic appendectomy.
Procedure was uncomplicated. Post-operative course was unremarkable.
"""

LAB_RESULTS = """QUEST DIAGNOSTICS
Order Number: QD-2025-789456

COMPREHENSIVE METABOLIC PANEL

Patient: John Doe
Collected: 05/22/2025 08:15
Reported: 05/22/2025 14:30

Test                Result    Reference Range    Flag
Glucose             95 mg/dL  70-100
BUN                 18 mg/dL  7-20
Creatinine          1.1 mg/dL 0.7-1.3
Sodium              140 mEq/L 136-145
Potassium           4.2 mEq/L 3.5-5.0
"""

CARE_PLAN_P1 = """DR. PATEL INTERNAL MEDICINE
1234 Medical Center Drive

CARE PLAN

Patient: John Doe
Date: 01/10/2025
Provider: Dr. Anish Patel, MD

DIABETES MANAGEMENT PLAN

Current A1C: 7.2% (Goal: <7.0%)

Medications:
- Metformin 1000mg twice daily
- Lisinopril 10mg daily
"""


def generate_all_fixtures() -> None:
    """Generate all test fixture PDFs."""
    pages_dir = FIXTURES_DIR / "pages"
    batches_dir = FIXTURES_DIR / "batches"

    # Individual pages
    page_files = {
        "radiology_report_p1.pdf": RADIOLOGY_REPORT_P1,
        "radiology_report_p2.pdf": RADIOLOGY_REPORT_P2,
        "discharge_summary_p1.pdf": DISCHARGE_SUMMARY_P1,
        "lab_results_single.pdf": LAB_RESULTS,
        "care_plan_p1.pdf": CARE_PLAN_P1,
    }

    for filename, text in page_files.items():
        create_text_page_pdf(text, pages_dir / filename)

    create_blank_page_pdf(pages_dir / "blank_page.pdf")
    create_near_blank_page_pdf(pages_dir / "near_blank_page.pdf")

    # Multi-page batches: 5 docs as fronts
    front_pages = [
        pages_dir / "radiology_report_p1.pdf",
        pages_dir / "radiology_report_p2.pdf",
        pages_dir / "discharge_summary_p1.pdf",
        pages_dir / "lab_results_single.pdf",
        pages_dir / "care_plan_p1.pdf",
    ]
    merge_pdfs(front_pages, batches_dir / "fronts_5docs.pdf")

    # Backs: reversed order (simulating physical flip), with blanks for single-sided
    back_pages = [
        pages_dir / "blank_page.pdf",  # back of care_plan (single-sided)
        pages_dir / "blank_page.pdf",  # back of lab_results (single-sided)
        pages_dir / "blank_page.pdf",  # back of discharge (single-sided)
        pages_dir / "blank_page.pdf",  # back of radiology p2 (single-sided)
        pages_dir / "blank_page.pdf",  # back of radiology p1 (single-sided)
    ]
    merge_pdfs(back_pages, batches_dir / "backs_5docs.pdf")

    # All single-sided (no backs)
    merge_pdfs(front_pages[:3], batches_dir / "fronts_all_single_sided.pdf")

    # Single document (4 pages)
    merge_pdfs(
        [
            pages_dir / "radiology_report_p1.pdf",
            pages_dir / "radiology_report_p2.pdf",
            pages_dir / "radiology_report_p1.pdf",
            pages_dir / "radiology_report_p2.pdf",
        ],
        batches_dir / "fronts_single_doc.pdf",
    )

    print(f"Generated fixtures in {FIXTURES_DIR}")


if __name__ == "__main__":
    generate_all_fixtures()
```

- [ ] **Step 3: Write conftest.py**

```python
"""Shared test fixtures."""

import json
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
```

- [ ] **Step 4: Generate fixtures**

Run: `cd /Users/justin/Code/scanbox && python -m tests.generate_fixtures`
Expected: `Generated fixtures in tests/fixtures`

- [ ] **Step 5: Verify fixture files exist**

Run: `ls tests/fixtures/pages/ tests/fixtures/batches/`
Expected: PDF files listed in both directories

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "feat: add test fixtures and conftest for pipeline testing"
```

---

### Task 3: Interleave Module

**Files:**
- Create: `scanbox/pipeline/__init__.py`
- Create: `scanbox/pipeline/interleave.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/test_interleave.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for two-pass duplex page interleaving."""

import pikepdf
import pytest
from pathlib import Path

from scanbox.pipeline.interleave import interleave_pages


def _make_pdf(tmp_path: Path, name: str, num_pages: int) -> Path:
    """Create a PDF with N pages, each containing its page number as text."""
    pdf = pikepdf.Pdf.new()
    for i in range(num_pages):
        # Create a minimal page with identifiable content in metadata
        page = pikepdf.Page(pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=[0, 0, 612, 792],
        ))
        pdf.pages.append(page)
    path = tmp_path / name
    pdf.save(path)
    return path


class TestInterleave:
    def test_equal_fronts_backs(self, tmp_path: Path):
        fronts = _make_pdf(tmp_path, "fronts.pdf", 3)
        backs = _make_pdf(tmp_path, "backs.pdf", 3)
        output = tmp_path / "combined.pdf"

        result = interleave_pages(fronts, backs, output)

        pdf = pikepdf.Pdf.open(result)
        assert len(pdf.pages) == 6  # F1,B3,F2,B2,F3,B1 -> interleaved

    def test_no_backs(self, tmp_path: Path):
        fronts = _make_pdf(tmp_path, "fronts.pdf", 5)
        output = tmp_path / "combined.pdf"

        result = interleave_pages(fronts, None, output)

        pdf = pikepdf.Pdf.open(result)
        assert len(pdf.pages) == 5  # passthrough

    def test_more_fronts_than_backs(self, tmp_path: Path):
        fronts = _make_pdf(tmp_path, "fronts.pdf", 5)
        backs = _make_pdf(tmp_path, "backs.pdf", 3)
        output = tmp_path / "combined.pdf"

        result = interleave_pages(fronts, backs, output)

        pdf = pikepdf.Pdf.open(result)
        # 3 pairs + 2 single-sided = 8 pages
        assert len(pdf.pages) == 8

    def test_more_backs_than_fronts_raises(self, tmp_path: Path):
        fronts = _make_pdf(tmp_path, "fronts.pdf", 3)
        backs = _make_pdf(tmp_path, "backs.pdf", 5)
        output = tmp_path / "combined.pdf"

        with pytest.raises(ValueError, match="more back pages than front"):
            interleave_pages(fronts, backs, output)

    def test_single_page_each(self, tmp_path: Path):
        fronts = _make_pdf(tmp_path, "fronts.pdf", 1)
        backs = _make_pdf(tmp_path, "backs.pdf", 1)
        output = tmp_path / "combined.pdf"

        result = interleave_pages(fronts, backs, output)

        pdf = pikepdf.Pdf.open(result)
        assert len(pdf.pages) == 2

    def test_output_file_created(self, tmp_path: Path):
        fronts = _make_pdf(tmp_path, "fronts.pdf", 2)
        output = tmp_path / "combined.pdf"

        result = interleave_pages(fronts, None, output)

        assert result.exists()
        assert result == output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_interleave.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scanbox.pipeline.interleave'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Two-pass duplex page interleaving.

When scanning duplex on a simplex-only ADF:
  Pass 1 (fronts): [F1, F2, F3, ..., Fn] — face up
  Pass 2 (backs):  [Bn, Bn-1, ..., B1]   — flipped stack, so reversed

This module interleaves them into correct order:
  [F1, B1, F2, B2, ..., Fn, Bn]
"""

from pathlib import Path

import pikepdf


def interleave_pages(
    fronts_path: Path,
    backs_path: Path | None,
    output_path: Path,
) -> Path:
    """Interleave front and back page scans into a single PDF.

    Args:
        fronts_path: PDF of front-side pages in scan order.
        backs_path: PDF of back-side pages in scan order (reversed from physical).
                    None if single-sided batch (fronts copied as-is).
        output_path: Where to write the interleaved PDF.

    Returns:
        output_path after writing.

    Raises:
        ValueError: If there are more back pages than front pages.
    """
    fronts_pdf = pikepdf.Pdf.open(fronts_path)
    n_fronts = len(fronts_pdf.pages)

    if backs_path is None:
        # Single-sided: just copy fronts
        fronts_pdf.save(output_path)
        return output_path

    backs_pdf = pikepdf.Pdf.open(backs_path)
    n_backs = len(backs_pdf.pages)

    if n_backs > n_fronts:
        raise ValueError(
            f"Got more back pages ({n_backs}) than front pages ({n_fronts}). "
            f"Did a page get stuck in the scanner?"
        )

    # Reverse the backs to undo the physical flip
    back_pages = list(reversed(range(n_backs)))

    # Interleave: F1, B1, F2, B2, ...
    result = pikepdf.Pdf.new()
    for i in range(n_fronts):
        result.pages.append(fronts_pdf.pages[i])
        if i < n_backs:
            result.pages.append(backs_pdf.pages[back_pages[i]])

    result.save(output_path)
    return output_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_interleave.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scanbox/pipeline/ tests/unit/
git commit -m "feat: add page interleaving for two-pass duplex scanning"
```

---

### Task 4: Blank Page Detection Module

**Files:**
- Create: `scanbox/pipeline/blank_detect.py`
- Create: `tests/unit/test_blank_detect.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for blank page detection and removal."""

from pathlib import Path

import pikepdf
import pytest

from scanbox.pipeline.blank_detect import detect_blank_pages, remove_blank_pages


class TestDetectBlankPages:
    def test_blank_page_detected(self, page_fixtures_dir: Path):
        pdf_path = page_fixtures_dir / "blank_page.pdf"
        if not pdf_path.exists():
            pytest.skip("Run generate_fixtures first")
        blanks = detect_blank_pages(pdf_path, threshold=0.01)
        assert blanks == [0]  # 0-indexed, only page is blank

    def test_content_page_not_detected(self, page_fixtures_dir: Path):
        pdf_path = page_fixtures_dir / "radiology_report_p1.pdf"
        if not pdf_path.exists():
            pytest.skip("Run generate_fixtures first")
        blanks = detect_blank_pages(pdf_path, threshold=0.01)
        assert blanks == []

    def test_near_blank_detected(self, page_fixtures_dir: Path):
        pdf_path = page_fixtures_dir / "near_blank_page.pdf"
        if not pdf_path.exists():
            pytest.skip("Run generate_fixtures first")
        blanks = detect_blank_pages(pdf_path, threshold=0.01)
        assert blanks == [0]


class TestRemoveBlankPages:
    def test_removes_blanks_preserves_content(self, tmp_path: Path, page_fixtures_dir: Path):
        blank = page_fixtures_dir / "blank_page.pdf"
        content = page_fixtures_dir / "radiology_report_p1.pdf"
        if not blank.exists() or not content.exists():
            pytest.skip("Run generate_fixtures first")

        # Build a 3-page PDF: content, blank, content
        merged = pikepdf.Pdf.new()
        for path in [content, blank, content]:
            src = pikepdf.Pdf.open(path)
            merged.pages.extend(src.pages)
        input_path = tmp_path / "input.pdf"
        merged.save(input_path)

        output_path = tmp_path / "cleaned.pdf"
        result = remove_blank_pages(input_path, output_path, threshold=0.01)

        pdf = pikepdf.Pdf.open(result.cleaned_path)
        assert len(pdf.pages) == 2
        assert result.removed_indices == [1]

    def test_no_blanks_passthrough(self, tmp_path: Path, page_fixtures_dir: Path):
        content = page_fixtures_dir / "radiology_report_p1.pdf"
        if not content.exists():
            pytest.skip("Run generate_fixtures first")

        output_path = tmp_path / "cleaned.pdf"
        result = remove_blank_pages(content, output_path, threshold=0.01)

        pdf = pikepdf.Pdf.open(result.cleaned_path)
        assert len(pdf.pages) == 1
        assert result.removed_indices == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_blank_detect.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
"""Blank page detection and removal.

Renders each PDF page to a low-res image and measures ink coverage
(percentage of non-white pixels). Pages below the threshold are blank.
"""

from dataclasses import dataclass, field
from pathlib import Path

import pikepdf
from pdf2image import convert_from_path
from PIL import Image
import numpy as np


@dataclass
class BlankRemovalResult:
    cleaned_path: Path
    removed_indices: list[int] = field(default_factory=list)
    total_pages: int = 0


def ink_coverage(image: Image.Image) -> float:
    """Calculate the fraction of non-white pixels in an image."""
    arr = np.array(image.convert("L"))  # grayscale
    # Count pixels darker than near-white (threshold 250 out of 255)
    non_white = np.sum(arr < 250)
    return non_white / arr.size


def detect_blank_pages(pdf_path: Path, threshold: float = 0.01) -> list[int]:
    """Return 0-indexed list of page numbers that are blank."""
    images = convert_from_path(str(pdf_path), dpi=150)
    blanks = []
    for i, img in enumerate(images):
        if ink_coverage(img) < threshold:
            blanks.append(i)
    return blanks


def remove_blank_pages(
    input_path: Path,
    output_path: Path,
    threshold: float = 0.01,
) -> BlankRemovalResult:
    """Remove blank pages from a PDF, preserving page order.

    Returns a result with the cleaned PDF path and which pages were removed.
    The removed pages are available for "bring back" functionality.
    """
    pdf = pikepdf.Pdf.open(input_path)
    total = len(pdf.pages)
    blanks = detect_blank_pages(input_path, threshold)

    if not blanks:
        # No blanks — copy as-is
        pdf.save(output_path)
        return BlankRemovalResult(
            cleaned_path=output_path, removed_indices=[], total_pages=total
        )

    result_pdf = pikepdf.Pdf.new()
    for i in range(total):
        if i not in blanks:
            result_pdf.pages.append(pdf.pages[i])

    result_pdf.save(output_path)
    return BlankRemovalResult(
        cleaned_path=output_path, removed_indices=blanks, total_pages=total
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_blank_detect.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scanbox/pipeline/blank_detect.py tests/unit/test_blank_detect.py
git commit -m "feat: add blank page detection and removal"
```

---

### Task 5: Namer Module

**Files:**
- Create: `scanbox/pipeline/namer.py`
- Create: `tests/unit/test_namer.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for medical document filename generation."""

import pytest

from scanbox.pipeline.namer import generate_filename, sanitize_filename


class TestSanitizeFilename:
    def test_removes_special_chars(self):
        assert sanitize_filename("Dr. O'Brien & Associates") == "Dr-OBrien-Associates"

    def test_replaces_spaces_with_hyphens(self):
        assert sanitize_filename("CT Abdomen with Contrast") == "CT-Abdomen-with-Contrast"

    def test_truncates_long_names(self):
        long = "A" * 250
        result = sanitize_filename(long, max_length=100)
        assert len(result) <= 100

    def test_no_trailing_hyphens(self):
        assert sanitize_filename("test - ") == "test"


class TestGenerateFilename:
    def test_full_metadata(self):
        result = generate_filename(
            person_name="John Doe",
            document_type="Radiology Report",
            date_of_service="2025-06-15",
            facility="Memorial Hospital",
            description="CT Abdomen with Contrast",
        )
        assert result == "2025-06-15_John-Doe_Radiology-Report_Memorial-Hospital_CT-Abdomen-with-Contrast.pdf"

    def test_unknown_date(self):
        result = generate_filename(
            person_name="John Doe",
            document_type="Lab Results",
            date_of_service="unknown",
            facility="Quest Diagnostics",
            description="Blood Work",
        )
        assert result.startswith("Unknown-Date_")

    def test_unknown_facility(self):
        result = generate_filename(
            person_name="John Doe",
            document_type="Letter",
            date_of_service="2025-01-01",
            facility="unknown",
            description="Referral",
        )
        # Facility omitted, not "unknown" in filename
        assert "unknown" not in result.lower()
        assert "Letter" in result

    def test_duplicate_suffix(self):
        base = generate_filename(
            person_name="John Doe",
            document_type="Other",
            date_of_service="unknown",
            facility="unknown",
            description="Document",
        )
        suffixed = generate_filename(
            person_name="John Doe",
            document_type="Other",
            date_of_service="unknown",
            facility="unknown",
            description="Document",
            duplicate_index=2,
        )
        assert suffixed.endswith("-2.pdf")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_namer.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
"""Medical document filename generation.

Pattern: YYYY-MM-DD_PersonName_DocumentType_Facility_Description.pdf
"""

import re
import unicodedata


def sanitize_filename(text: str, max_length: int = 60) -> str:
    """Sanitize text for use in a filename."""
    # Normalize unicode
    text = unicodedata.normalize("NFKD", text)
    # Remove non-ASCII
    text = text.encode("ascii", "ignore").decode("ascii")
    # Replace spaces and special chars with hyphens
    text = re.sub(r"[^a-zA-Z0-9-]", "-", text)
    # Collapse multiple hyphens
    text = re.sub(r"-+", "-", text)
    # Strip leading/trailing hyphens
    text = text.strip("-")
    # Truncate without cutting mid-word
    if len(text) > max_length:
        text = text[:max_length].rsplit("-", 1)[0]
    return text


def generate_filename(
    person_name: str,
    document_type: str,
    date_of_service: str = "unknown",
    facility: str = "unknown",
    description: str = "Document",
    duplicate_index: int = 0,
) -> str:
    """Generate a medical-professional filename from metadata."""
    date_part = "Unknown-Date" if date_of_service == "unknown" else date_of_service
    person_part = sanitize_filename(person_name, max_length=30)
    type_part = sanitize_filename(document_type, max_length=30)
    desc_part = sanitize_filename(description, max_length=50)

    parts = [date_part, person_part, type_part]

    if facility and facility != "unknown":
        parts.append(sanitize_filename(facility, max_length=30))

    parts.append(desc_part)

    base = "_".join(parts)

    if duplicate_index > 0:
        return f"{base}-{duplicate_index}.pdf"
    return f"{base}.pdf"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_namer.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scanbox/pipeline/namer.py tests/unit/test_namer.py
git commit -m "feat: add medical document filename generation"
```

---

### Task 6: AI Splitter Module

**Files:**
- Create: `scanbox/pipeline/splitter.py`
- Create: `tests/unit/test_splitter.py`

- [ ] **Step 1: Write the failing tests**

Focus on the **validation layer** — the part that validates LLM output. LLM calls are mocked.

```python
"""Tests for AI document splitting — validation logic, not LLM calls."""

import pytest

from scanbox.pipeline.splitter import validate_splits, build_prompt, SplitValidationError
from scanbox.models import SplitDocument


class TestValidateSplits:
    def test_valid_contiguous_splits(self):
        splits = [
            {"start_page": 1, "end_page": 2, "document_type": "Radiology Report",
             "date_of_service": "2025-06-15", "facility": "Hospital", "provider": "Dr. X",
             "description": "CT scan", "confidence": 0.9},
            {"start_page": 3, "end_page": 5, "document_type": "Lab Results",
             "date_of_service": "2025-05-22", "facility": "Quest", "provider": "unknown",
             "description": "Blood work", "confidence": 0.85},
        ]
        result = validate_splits(splits, total_pages=5)
        assert len(result) == 2
        assert isinstance(result[0], SplitDocument)

    def test_gap_in_pages_raises(self):
        splits = [
            {"start_page": 1, "end_page": 2, "document_type": "Report",
             "date_of_service": "unknown", "facility": "unknown", "provider": "unknown",
             "description": "Doc", "confidence": 0.9},
            {"start_page": 4, "end_page": 5, "document_type": "Report",
             "date_of_service": "unknown", "facility": "unknown", "provider": "unknown",
             "description": "Doc", "confidence": 0.9},
        ]
        with pytest.raises(SplitValidationError, match="gap"):
            validate_splits(splits, total_pages=5)

    def test_overlap_raises(self):
        splits = [
            {"start_page": 1, "end_page": 3, "document_type": "Report",
             "date_of_service": "unknown", "facility": "unknown", "provider": "unknown",
             "description": "Doc", "confidence": 0.9},
            {"start_page": 2, "end_page": 5, "document_type": "Report",
             "date_of_service": "unknown", "facility": "unknown", "provider": "unknown",
             "description": "Doc", "confidence": 0.9},
        ]
        with pytest.raises(SplitValidationError, match="overlap"):
            validate_splits(splits, total_pages=5)

    def test_pages_not_covered_raises(self):
        splits = [
            {"start_page": 1, "end_page": 3, "document_type": "Report",
             "date_of_service": "unknown", "facility": "unknown", "provider": "unknown",
             "description": "Doc", "confidence": 0.9},
        ]
        with pytest.raises(SplitValidationError, match="not covered"):
            validate_splits(splits, total_pages=5)

    def test_single_page_single_doc(self):
        splits = [
            {"start_page": 1, "end_page": 1, "document_type": "Letter",
             "date_of_service": "2025-01-01", "facility": "Clinic", "provider": "Dr. Y",
             "description": "Referral", "confidence": 0.95},
        ]
        result = validate_splits(splits, total_pages=1)
        assert len(result) == 1
        assert result[0].start_page == 1

    def test_start_after_end_raises(self):
        splits = [
            {"start_page": 3, "end_page": 1, "document_type": "Report",
             "date_of_service": "unknown", "facility": "unknown", "provider": "unknown",
             "description": "Doc", "confidence": 0.9},
        ]
        with pytest.raises(SplitValidationError, match="start_page.*end_page"):
            validate_splits(splits, total_pages=3)


class TestBuildPrompt:
    def test_prompt_includes_person_name(self):
        prompt = build_prompt(
            page_texts={1: "Some text", 2: "More text"},
            person_name="John Doe",
        )
        assert "John Doe" in prompt

    def test_prompt_includes_page_markers(self):
        prompt = build_prompt(
            page_texts={1: "Page one text", 2: "Page two text"},
            person_name="Test",
        )
        assert "---PAGE 1---" in prompt
        assert "---PAGE 2---" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_splitter.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
"""AI-powered document boundary detection and classification.

Uses litellm==1.82.6 (PINNED — versions 1.82.7/1.82.8 were compromised in a
supply chain attack, March 2026. See .claude/rules/tech-stack-2026.md) to call
any LLM provider (Anthropic, OpenAI, Ollama) with the same prompt. The
validation layer ensures the LLM output is structurally correct before use.
"""

import json

import litellm

from scanbox.config import config
from scanbox.models import SplitDocument, DOCUMENT_TYPES


class SplitValidationError(ValueError):
    """Raised when LLM split output fails structural validation."""


SYSTEM_PROMPT = """You are a document analysis assistant. You analyze OCR text from scanned medical documents and identify document boundaries.

Return ONLY a JSON array. No markdown, no explanation. Each element:
{
  "start_page": <int, 1-indexed>,
  "end_page": <int, 1-indexed>,
  "document_type": "<one of: Radiology Report, Discharge Summary, Care Plan, Lab Results, Letter, Operative Report, Progress Note, Pathology Report, Prescription, Insurance, Billing, Other>",
  "date_of_service": "<YYYY-MM-DD or 'unknown'>",
  "facility": "<name or 'unknown'>",
  "provider": "<doctor name or 'unknown'>",
  "description": "<3-8 word description>",
  "confidence": <0.0-1.0>
}"""


def build_prompt(page_texts: dict[int, str], person_name: str) -> str:
    """Build the user prompt with OCR text for all pages."""
    lines = [
        f"Analyze these {len(page_texts)} scanned pages. "
        f"They are medical documents for patient: {person_name}.",
        "",
    ]
    for page_num in sorted(page_texts.keys()):
        lines.append(f"---PAGE {page_num}---")
        lines.append(page_texts[page_num])
        lines.append("")
    return "\n".join(lines)


def validate_splits(
    raw_splits: list[dict], total_pages: int
) -> list[SplitDocument]:
    """Validate that split boundaries are contiguous, non-overlapping, and cover all pages."""
    if not raw_splits:
        raise SplitValidationError("LLM returned empty splits list")

    # Sort by start_page
    sorted_splits = sorted(raw_splits, key=lambda s: s["start_page"])

    docs = []
    for s in sorted_splits:
        start = s.get("start_page", 0)
        end = s.get("end_page", 0)

        if start > end:
            raise SplitValidationError(
                f"start_page ({start}) > end_page ({end}) — invalid range"
            )

        docs.append(SplitDocument(
            start_page=start,
            end_page=end,
            document_type=s.get("document_type", "Other"),
            date_of_service=s.get("date_of_service", "unknown"),
            facility=s.get("facility", "unknown"),
            provider=s.get("provider", "unknown"),
            description=s.get("description", "Document"),
            confidence=max(0.0, min(1.0, float(s.get("confidence", 0.5)))),
        ))

    # Check contiguous coverage
    for i in range(len(docs) - 1):
        current_end = docs[i].end_page
        next_start = docs[i + 1].start_page
        if next_start > current_end + 1:
            raise SplitValidationError(
                f"gap between pages {current_end} and {next_start} — "
                f"pages {current_end + 1}-{next_start - 1} not covered"
            )
        if next_start <= current_end:
            raise SplitValidationError(
                f"overlap: document ending at page {current_end} "
                f"overlaps with document starting at page {next_start}"
            )

    # Check first and last page coverage
    if docs[0].start_page != 1:
        raise SplitValidationError(
            f"Pages 1-{docs[0].start_page - 1} not covered by any document"
        )
    if docs[-1].end_page != total_pages:
        raise SplitValidationError(
            f"Pages {docs[-1].end_page + 1}-{total_pages} not covered by any document"
        )

    return docs


async def split_documents(
    page_texts: dict[int, str],
    person_name: str,
) -> list[SplitDocument]:
    """Call the LLM to split and classify documents, then validate."""
    prompt = build_prompt(page_texts, person_name)
    total_pages = len(page_texts)

    response = await litellm.acompletion(
        model=config.llm_model_id(),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    content = response.choices[0].message.content
    parsed = json.loads(content)

    # Handle both {"documents": [...]} and [...] formats
    if isinstance(parsed, dict) and "documents" in parsed:
        raw_splits = parsed["documents"]
    elif isinstance(parsed, list):
        raw_splits = parsed
    else:
        raise SplitValidationError(f"Unexpected response format: {type(parsed)}")

    return validate_splits(raw_splits, total_pages)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_splitter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scanbox/pipeline/splitter.py tests/unit/test_splitter.py
git commit -m "feat: add AI document splitting with validation layer"
```

---

### Task 7: OCR Module

**Files:**
- Create: `scanbox/pipeline/ocr.py`
- Create: `tests/unit/test_ocr.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for OCR text extraction."""

from pathlib import Path

import pytest

from scanbox.pipeline.ocr import extract_text_by_page, run_ocr


class TestExtractTextByPage:
    def test_extracts_text_from_content_page(self, page_fixtures_dir: Path):
        pdf_path = page_fixtures_dir / "radiology_report_p1.pdf"
        if not pdf_path.exists():
            pytest.skip("Run generate_fixtures first")
        texts = extract_text_by_page(pdf_path)
        assert 1 in texts
        assert len(texts[1]) > 50  # Should have substantial text
        assert "RADIOLOGY" in texts[1].upper() or "MEMORIAL" in texts[1].upper()

    def test_blank_page_has_minimal_text(self, page_fixtures_dir: Path):
        pdf_path = page_fixtures_dir / "blank_page.pdf"
        if not pdf_path.exists():
            pytest.skip("Run generate_fixtures first")
        texts = extract_text_by_page(pdf_path)
        assert 1 in texts
        assert len(texts[1].strip()) < 10  # Blank or nearly blank

    def test_multi_page_returns_all_pages(self, batch_fixtures_dir: Path):
        pdf_path = batch_fixtures_dir / "fronts_all_single_sided.pdf"
        if not pdf_path.exists():
            pytest.skip("Run generate_fixtures first")
        texts = extract_text_by_page(pdf_path)
        assert len(texts) == 3  # 3-page fixture


class TestRunOcr:
    def test_creates_searchable_pdf(self, tmp_path: Path, page_fixtures_dir: Path):
        input_path = page_fixtures_dir / "radiology_report_p1.pdf"
        if not input_path.exists():
            pytest.skip("Run generate_fixtures first")
        output_path = tmp_path / "ocr.pdf"
        text_path = tmp_path / "text_by_page.json"

        run_ocr(input_path, output_path, text_path)

        assert output_path.exists()
        assert text_path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_ocr.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
"""OCR processing via ocrmypdf with per-page text extraction."""

import json
import subprocess
from pathlib import Path

import pikepdf
from pdf2image import convert_from_path

try:
    import pytesseract
except ImportError:
    pytesseract = None


def extract_text_by_page(pdf_path: Path) -> dict[int, str]:
    """Extract OCR text from each page, returning {page_num: text} (1-indexed)."""
    images = convert_from_path(str(pdf_path), dpi=300)
    page_texts = {}
    for i, img in enumerate(images):
        if pytesseract:
            text = pytesseract.image_to_string(img)
        else:
            text = ""
        page_texts[i + 1] = text
    return page_texts


def run_ocr(
    input_path: Path,
    output_path: Path,
    text_json_path: Path,
    language: str = "eng",
) -> None:
    """Run OCR on a PDF: create searchable PDF and extract per-page text.

    Args:
        input_path: Input PDF (may or may not have text layer).
        output_path: Output searchable PDF.
        text_json_path: Path to write {page_num: text} JSON.
        language: Tesseract language code.
    """
    # Create searchable PDF with ocrmypdf
    subprocess.run(
        [
            "ocrmypdf",
            "--language", language,
            "--deskew",
            "--skip-text",  # Don't re-OCR pages that already have text
            "--output-type", "pdf",
            str(input_path),
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )

    # Extract text per page from the OCR'd PDF
    page_texts = extract_text_by_page(output_path)

    text_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(text_json_path, "w") as f:
        json.dump(page_texts, f, indent=2)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_ocr.py -v`
Expected: PASS (requires tesseract-ocr installed: `brew install tesseract`)

- [ ] **Step 5: Commit**

```bash
git add scanbox/pipeline/ocr.py tests/unit/test_ocr.py
git commit -m "feat: add OCR processing with per-page text extraction"
```

---

### Task 8: Output Module

**Files:**
- Create: `scanbox/pipeline/output.py`
- Create: `tests/unit/test_output.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for output file writing (archive, medical records, Index.csv)."""

import csv
from pathlib import Path

import pikepdf
import pytest

from scanbox.pipeline.output import write_archive, write_medical_records, append_index_csv
from scanbox.models import SplitDocument


@pytest.fixture
def sample_doc() -> SplitDocument:
    return SplitDocument(
        start_page=1,
        end_page=2,
        document_type="Radiology Report",
        date_of_service="2025-06-15",
        facility="Memorial Hospital",
        provider="Dr. Chen",
        description="CT Abdomen",
        confidence=0.95,
    )


class TestWriteArchive:
    def test_copies_combined_pdf(self, tmp_path: Path):
        # Create a dummy PDF
        pdf = pikepdf.Pdf.new()
        pdf.pages.append(pikepdf.Page(pikepdf.Dictionary(
            Type=pikepdf.Name.Page, MediaBox=[0, 0, 612, 792]
        )))
        src = tmp_path / "combined.pdf"
        pdf.save(src)

        archive_dir = tmp_path / "archive"
        result = write_archive(src, archive_dir, person_slug="john-doe", scan_date="2026-03-28", batch_num=1)

        assert result.exists()
        assert "john-doe" in str(result)
        assert "2026-03-28" in str(result)


class TestWriteMedicalRecords:
    def test_creates_type_subdirectory(self, tmp_path: Path, sample_doc: SplitDocument):
        records_dir = tmp_path / "medical-records"
        doc_pdf = tmp_path / "doc.pdf"
        pdf = pikepdf.Pdf.new()
        pdf.pages.append(pikepdf.Page(pikepdf.Dictionary(
            Type=pikepdf.Name.Page, MediaBox=[0, 0, 612, 792]
        )))
        pdf.save(doc_pdf)

        result = write_medical_records(
            doc_pdf, records_dir, person_folder="John_Doe",
            document_type="Radiology Report", filename="test.pdf"
        )

        assert result.exists()
        assert "Radiology Reports" in str(result) or "Radiology Report" in str(result)


class TestAppendIndexCsv:
    def test_creates_csv_with_headers(self, tmp_path: Path, sample_doc: SplitDocument):
        csv_path = tmp_path / "Index.csv"
        append_index_csv(csv_path, "test.pdf", sample_doc, scan_date="2026-03-28")

        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["Filename"] == "test.pdf"
        assert rows[0]["Date"] == "2025-06-15"
        assert rows[0]["Type"] == "Radiology Report"

    def test_appends_to_existing_csv(self, tmp_path: Path, sample_doc: SplitDocument):
        csv_path = tmp_path / "Index.csv"
        append_index_csv(csv_path, "doc1.pdf", sample_doc, scan_date="2026-03-28")
        append_index_csv(csv_path, "doc2.pdf", sample_doc, scan_date="2026-03-28")

        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_output.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
"""Output writing: archive, medical records, Index.csv."""

import csv
import shutil
from pathlib import Path

import pikepdf

from scanbox.models import SplitDocument


# Pluralized folder names for medical record categories
TYPE_FOLDER_NAMES = {
    "Radiology Report": "Radiology Reports",
    "Discharge Summary": "Discharge Summaries",
    "Care Plan": "Care Plans",
    "Lab Results": "Lab Results",
    "Letter": "Letters & Referrals",
    "Operative Report": "Operative Reports",
    "Progress Note": "Progress Notes",
    "Pathology Report": "Pathology Reports",
    "Prescription": "Prescriptions",
    "Insurance": "Insurance",
    "Billing": "Billing",
    "Other": "Other",
}

INDEX_HEADERS = ["Filename", "Date", "Type", "Facility", "Provider", "Description", "Scanned"]


def write_archive(
    combined_pdf: Path,
    archive_dir: Path,
    person_slug: str,
    scan_date: str,
    batch_num: int,
) -> Path:
    """Copy the raw combined PDF to the archive directory."""
    dest_dir = archive_dir / person_slug / scan_date
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"batch-{batch_num:03d}-combined.pdf"
    shutil.copy2(combined_pdf, dest)
    return dest


def write_medical_records(
    doc_pdf: Path,
    records_dir: Path,
    person_folder: str,
    document_type: str,
    filename: str,
) -> Path:
    """Write a split document PDF to the organized medical records folder."""
    type_folder = TYPE_FOLDER_NAMES.get(document_type, "Other")
    dest_dir = records_dir / person_folder / type_folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    shutil.copy2(doc_pdf, dest)
    return dest


def embed_pdf_metadata(
    pdf_path: Path,
    title: str,
    author: str,
    subject: str,
    creation_date: str,
) -> None:
    """Embed metadata into a PDF file's docinfo."""
    pdf = pikepdf.Pdf.open(pdf_path)
    with pdf.open_metadata() as meta:
        meta["dc:title"] = title
        meta["dc:creator"] = [author]
        meta["dc:subject"] = [subject]
        meta["xmp:CreatorTool"] = "ScanBox"
    if creation_date and creation_date != "unknown":
        pdf.docinfo["/CreationDate"] = f"D:{creation_date.replace('-', '')}000000"
        pdf.docinfo["/Producer"] = "ScanBox"
    pdf.save(pdf_path)


def append_index_csv(
    csv_path: Path,
    filename: str,
    doc: SplitDocument,
    scan_date: str,
) -> None:
    """Append a row to the Index.csv file, creating it if it doesn't exist."""
    write_header = not csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "Filename": filename,
            "Date": doc.date_of_service,
            "Type": doc.document_type,
            "Facility": doc.facility if doc.facility != "unknown" else "",
            "Provider": doc.provider if doc.provider != "unknown" else "",
            "Description": doc.description,
            "Scanned": scan_date,
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_output.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scanbox/pipeline/output.py tests/unit/test_output.py
git commit -m "feat: add output module for archive, medical records, and Index.csv"
```

---

### Task 9: Pipeline Runner (Orchestrator)

**Files:**
- Create: `scanbox/pipeline/runner.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_pipeline.py`

- [ ] **Step 1: Write the integration test**

```python
"""Integration test: full pipeline from fronts+backs to named output documents."""

import json
from pathlib import Path

import pikepdf
import pytest

from scanbox.pipeline.runner import run_pipeline, PipelineContext
from scanbox.models import BatchState, ProcessingStage


@pytest.fixture
def pipeline_ctx(tmp_path: Path, batch_fixtures_dir: Path) -> PipelineContext:
    """Create a pipeline context with fixture data."""
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    fronts = batch_fixtures_dir / "fronts_all_single_sided.pdf"
    if not fronts.exists():
        pytest.skip("Run generate_fixtures first")

    import shutil
    shutil.copy(fronts, batch_dir / "fronts.pdf")

    return PipelineContext(
        batch_dir=batch_dir,
        output_dir=output_dir,
        person_name="John Doe",
        person_slug="john-doe",
        person_folder="John_Doe",
        batch_num=1,
        scan_date="2026-03-28",
        has_backs=False,
    )


class TestPipelineRunner:
    def test_single_sided_produces_output(self, pipeline_ctx: PipelineContext):
        """Smoke test: pipeline completes without errors on single-sided batch."""
        # This test requires tesseract + a real or mocked LLM
        # For unit testing, we mock the LLM call — see conftest
        pytest.skip("Requires LLM mock — implement in task 10")

    def test_state_file_tracks_progress(self, pipeline_ctx: PipelineContext):
        state_path = pipeline_ctx.batch_dir / "state.json"
        # State file should be created at pipeline start
        assert not state_path.exists()  # Not yet started
```

- [ ] **Step 2: Write the pipeline runner**

```python
"""Pipeline orchestrator with checkpoint state machine.

Runs stages in sequence, checkpointing after each. If interrupted,
resumes from the last completed stage.
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from scanbox.models import BatchState, ProcessingStage, SplitDocument
from scanbox.pipeline.interleave import interleave_pages
from scanbox.pipeline.blank_detect import remove_blank_pages
from scanbox.pipeline.ocr import run_ocr, extract_text_by_page
from scanbox.pipeline.splitter import split_documents, validate_splits
from scanbox.pipeline.namer import generate_filename
from scanbox.pipeline.output import (
    write_archive,
    write_medical_records,
    embed_pdf_metadata,
    append_index_csv,
)
from scanbox.config import config

import pikepdf


@dataclass
class PipelineContext:
    batch_dir: Path
    output_dir: Path
    person_name: str
    person_slug: str
    person_folder: str
    batch_num: int
    scan_date: str
    has_backs: bool


def _state_path(ctx: PipelineContext) -> Path:
    return ctx.batch_dir / "state.json"


def _read_state(ctx: PipelineContext) -> dict:
    path = _state_path(ctx)
    if path.exists():
        return json.loads(path.read_text())
    return {"stage": ProcessingStage.INTERLEAVING.value}


def _write_state(ctx: PipelineContext, stage: ProcessingStage, **extra) -> None:
    state = {"stage": stage.value, **extra}
    _state_path(ctx).write_text(json.dumps(state, indent=2))


async def run_pipeline(
    ctx: PipelineContext,
    on_progress: callable = None,
) -> list[SplitDocument]:
    """Run the full processing pipeline with checkpointing.

    Args:
        ctx: Pipeline context with paths and metadata.
        on_progress: Optional callback(stage_name, detail) for SSE updates.
    """
    state = _read_state(ctx)
    current_stage = ProcessingStage(state["stage"])

    def progress(stage: ProcessingStage, detail: str = ""):
        _write_state(ctx, stage)
        if on_progress:
            on_progress(stage.value, detail)

    # Stage 1: Interleave
    combined_path = ctx.batch_dir / "combined.pdf"
    if current_stage == ProcessingStage.INTERLEAVING:
        progress(ProcessingStage.INTERLEAVING, "Combining front and back pages...")
        fronts_path = ctx.batch_dir / "fronts.pdf"
        backs_path = ctx.batch_dir / "backs.pdf" if ctx.has_backs else None
        interleave_pages(fronts_path, backs_path, combined_path)
        current_stage = ProcessingStage.BLANK_REMOVAL

    # Stage 2: Blank removal
    cleaned_path = ctx.batch_dir / "cleaned.pdf"
    if current_stage == ProcessingStage.BLANK_REMOVAL:
        progress(ProcessingStage.BLANK_REMOVAL, "Removing blank pages...")
        result = remove_blank_pages(combined_path, cleaned_path, config.BLANK_PAGE_THRESHOLD)
        # Save removed page info for "bring back" feature
        removed_info = {"removed_indices": result.removed_indices, "total_pages": result.total_pages}
        (ctx.batch_dir / "blank_removal.json").write_text(json.dumps(removed_info))
        current_stage = ProcessingStage.OCR

    # Stage 3: OCR
    ocr_path = ctx.batch_dir / "ocr.pdf"
    text_json_path = ctx.batch_dir / "text_by_page.json"
    if current_stage == ProcessingStage.OCR:
        progress(ProcessingStage.OCR, "Reading text from your documents...")
        run_ocr(cleaned_path, ocr_path, text_json_path)
        current_stage = ProcessingStage.SPLITTING

    # Stage 4: AI Splitting
    splits_path = ctx.batch_dir / "splits.json"
    if current_stage == ProcessingStage.SPLITTING:
        progress(ProcessingStage.SPLITTING, "Figuring out where each document starts and ends...")
        page_texts_raw = json.loads(text_json_path.read_text())
        page_texts = {int(k): v for k, v in page_texts_raw.items()}
        documents = await split_documents(page_texts, ctx.person_name)
        splits_data = [doc.model_dump() for doc in documents]
        splits_path.write_text(json.dumps(splits_data, indent=2))
        current_stage = ProcessingStage.NAMING

    # Stage 5: Split, embed metadata, name
    docs_dir = ctx.batch_dir / "documents"
    if current_stage == ProcessingStage.NAMING:
        progress(ProcessingStage.NAMING, "Organizing and naming your documents...")
        docs_dir.mkdir(exist_ok=True)
        splits_data = json.loads(splits_path.read_text())
        documents = [SplitDocument(**d) for d in splits_data]
        ocr_pdf = pikepdf.Pdf.open(ocr_path)

        seen_names: dict[str, int] = {}
        for doc in documents:
            # Extract pages
            doc_pdf = pikepdf.Pdf.new()
            for page_num in range(doc.start_page, doc.end_page + 1):
                doc_pdf.pages.append(ocr_pdf.pages[page_num - 1])

            # Generate filename (handle duplicates)
            base_name = generate_filename(
                person_name=ctx.person_name,
                document_type=doc.document_type,
                date_of_service=doc.date_of_service,
                facility=doc.facility,
                description=doc.description,
            )
            if base_name in seen_names:
                seen_names[base_name] += 1
                filename = generate_filename(
                    person_name=ctx.person_name,
                    document_type=doc.document_type,
                    date_of_service=doc.date_of_service,
                    facility=doc.facility,
                    description=doc.description,
                    duplicate_index=seen_names[base_name],
                )
            else:
                seen_names[base_name] = 1
                filename = base_name

            doc_path = docs_dir / filename
            doc_pdf.save(doc_path)

            # Embed PDF metadata
            title = f"{doc.document_type} — {doc.description}"
            embed_pdf_metadata(
                doc_path,
                title=title,
                author=doc.facility if doc.facility != "unknown" else "Unknown",
                subject=ctx.person_name,
                creation_date=doc.date_of_service,
            )

        _write_state(ctx, ProcessingStage.DONE)

    # Read back final documents list
    splits_data = json.loads(splits_path.read_text())
    return [SplitDocument(**d) for d in splits_data]
```

- [ ] **Step 3: Run integration tests**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/integration/test_pipeline.py -v`
Expected: 1 skipped (LLM mock needed), 1 pass (state file test)

- [ ] **Step 4: Commit**

```bash
git add scanbox/pipeline/runner.py tests/integration/
git commit -m "feat: add pipeline orchestrator with checkpoint state machine"
```

---

### Task 10: eSCL Scanner Client

**Files:**
- Create: `scanbox/scanner/__init__.py`
- Create: `scanbox/scanner/escl.py`
- Create: `scanbox/scanner/models.py`
- Create: `tests/unit/test_escl.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for eSCL scanner client — XML parsing and job creation."""

from pathlib import Path

import pytest

from scanbox.scanner.escl import parse_capabilities, parse_status, build_scan_settings_xml
from scanbox.scanner.models import ScannerCapabilities, ScannerStatus


class TestParseCapabilities:
    def test_parses_adf_support(self, escl_fixtures_dir: Path):
        xml = (escl_fixtures_dir / "capabilities.xml").read_text()
        caps = parse_capabilities(xml)
        assert caps.has_adf is True
        assert 300 in caps.supported_resolutions
        assert "application/pdf" in caps.supported_formats
        assert "HP" in caps.make_and_model


class TestParseStatus:
    def test_parses_idle_with_adf_loaded(self, escl_fixtures_dir: Path):
        xml = (escl_fixtures_dir / "status_idle.xml").read_text()
        status = parse_status(xml)
        assert status.state == "Idle"
        assert status.adf_loaded is True


class TestBuildScanSettings:
    def test_generates_valid_xml(self):
        xml = build_scan_settings_xml(dpi=300, color_mode="RGB24", source="Feeder")
        assert "Feeder" in xml
        assert "300" in xml
        assert "RGB24" in xml
        assert "application/pdf" in xml
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_escl.py -v`
Expected: FAIL

- [ ] **Step 3: Write scanner models**

```python
"""Scanner data models."""

from dataclasses import dataclass, field


@dataclass
class ScannerCapabilities:
    make_and_model: str = ""
    has_adf: bool = False
    has_duplex_adf: bool = False
    supported_resolutions: list[int] = field(default_factory=list)
    supported_formats: list[str] = field(default_factory=list)
    max_width: int = 2550   # US Letter at 300 DPI
    max_height: int = 3300


@dataclass
class ScannerStatus:
    state: str = "Unknown"  # Idle, Processing, Testing, Stopped, Down
    adf_loaded: bool = False
    adf_state: str = ""
```

- [ ] **Step 4: Write eSCL client**

```python
"""eSCL (Apple AirScan) HTTP client for HP scanner communication."""

import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from scanbox.scanner.models import ScannerCapabilities, ScannerStatus


ESCL_NS = {
    "scan": "http://schemas.hp.com/imaging/escl/2011/05/03",
    "pwg": "http://www.pwg.org/schemas/2010/12/sm",
}


def parse_capabilities(xml_text: str) -> ScannerCapabilities:
    """Parse eSCL ScannerCapabilities XML."""
    root = ET.fromstring(xml_text)
    caps = ScannerCapabilities()

    model_el = root.find(".//pwg:MakeAndModel", ESCL_NS)
    if model_el is not None and model_el.text:
        caps.make_and_model = model_el.text

    # Check for ADF
    adf = root.find(".//scan:Adf", ESCL_NS)
    if adf is not None:
        caps.has_adf = True
        if adf.find(".//scan:AdfDuplexInputCaps", ESCL_NS) is not None:
            caps.has_duplex_adf = True

    # Resolutions (from ADF or Platen)
    for res_el in root.findall(".//scan:DiscreteResolution", ESCL_NS):
        x_res = res_el.find("scan:XResolution", ESCL_NS)
        if x_res is not None and x_res.text:
            caps.supported_resolutions.append(int(x_res.text))

    # Formats
    for fmt_el in root.findall(".//pwg:DocumentFormat", ESCL_NS):
        if fmt_el.text:
            caps.supported_formats.append(fmt_el.text)

    # Deduplicate
    caps.supported_resolutions = sorted(set(caps.supported_resolutions))
    caps.supported_formats = sorted(set(caps.supported_formats))

    return caps


def parse_status(xml_text: str) -> ScannerStatus:
    """Parse eSCL ScannerStatus XML."""
    root = ET.fromstring(xml_text)
    status = ScannerStatus()

    state_el = root.find(".//pwg:State", ESCL_NS)
    if state_el is not None and state_el.text:
        status.state = state_el.text

    adf_el = root.find(".//scan:AdfState", ESCL_NS)
    if adf_el is not None and adf_el.text:
        status.adf_state = adf_el.text
        status.adf_loaded = "Loaded" in adf_el.text

    return status


def build_scan_settings_xml(
    dpi: int = 300,
    color_mode: str = "RGB24",
    source: str = "Feeder",
) -> str:
    """Build eSCL ScanSettings XML for an ADF scan job."""
    # US Letter at given DPI
    width = int(8.5 * dpi)
    height = int(11 * dpi)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<scan:ScanSettings xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                   xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
  <pwg:Version>2.0</pwg:Version>
  <pwg:InputSource>{source}</pwg:InputSource>
  <pwg:ScanRegions>
    <pwg:ScanRegion>
      <pwg:XOffset>0</pwg:XOffset>
      <pwg:YOffset>0</pwg:YOffset>
      <pwg:Width>{width}</pwg:Width>
      <pwg:Height>{height}</pwg:Height>
      <pwg:ContentRegionUnits>escl:ThreeHundredthsOfInches</pwg:ContentRegionUnits>
    </pwg:ScanRegion>
  </pwg:ScanRegions>
  <scan:ColorMode>{color_mode}</scan:ColorMode>
  <scan:XResolution>{dpi}</scan:XResolution>
  <scan:YResolution>{dpi}</scan:YResolution>
  <pwg:DocumentFormat>application/pdf</pwg:DocumentFormat>
</scan:ScanSettings>"""


class ESCLClient:
    """Async client for eSCL scanner communication."""

    def __init__(self, scanner_ip: str):
        self.base_url = f"http://{scanner_ip}/eSCL"
        self._client = httpx.AsyncClient(timeout=30.0)

    async def get_capabilities(self) -> ScannerCapabilities:
        resp = await self._client.get(f"{self.base_url}/ScannerCapabilities")
        resp.raise_for_status()
        return parse_capabilities(resp.text)

    async def get_status(self) -> ScannerStatus:
        resp = await self._client.get(f"{self.base_url}/ScannerStatus")
        resp.raise_for_status()
        return parse_status(resp.text)

    async def start_scan(self, dpi: int = 300) -> str:
        """Start an ADF scan job. Returns the job URL."""
        xml = build_scan_settings_xml(dpi=dpi)
        resp = await self._client.post(
            f"{self.base_url}/ScanJobs",
            content=xml,
            headers={"Content-Type": "text/xml"},
        )
        resp.raise_for_status()
        return resp.headers.get("Location", "")

    async def get_next_page(self, job_url: str) -> bytes | None:
        """Get the next scanned page. Returns None when ADF is empty (404)."""
        url = f"{job_url}/NextDocument"
        if not url.startswith("http"):
            url = f"http://{self.base_url.split('//')[1].split('/')[0]}{url}"
        try:
            resp = await self._client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def cancel_job(self, job_url: str) -> None:
        """Cancel an active scan job."""
        try:
            await self._client.delete(job_url)
        except httpx.HTTPError:
            pass  # Best effort

    async def close(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/justin/Code/scanbox && python -m pytest tests/unit/test_escl.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add scanbox/scanner/ tests/unit/test_escl.py
git commit -m "feat: add eSCL scanner client with XML parsing"
```

---

### Phase 1 Checkpoint

At this point, the entire processing pipeline is implemented and unit tested:
- Interleave (duplex page merging)
- Blank page detection/removal
- OCR (via ocrmypdf)
- AI document splitting (via litellm, with validation)
- Medical filename generation
- Output writing (archive, medical records, Index.csv)
- Pipeline orchestrator with state machine checkpoints
- eSCL scanner client

**Run all unit tests:**
```bash
cd /Users/justin/Code/scanbox
ruff format scanbox/ tests/
ruff check scanbox/ tests/
python -m pytest tests/unit/ -v
```

**Commit Phase 1 completion:**
```bash
git add -A
git commit -m "milestone: complete Phase 1 — pipeline core with unit tests"
```

---

## Phase 2: API + Web UI

> **Note to implementing agent:** Phase 2 builds the FastAPI API layer, web UI templates, SSE progress, and session management. The tasks below define the API routes, database schema, and template structure. Frontend uses Jinja2 server-side rendering with htmx for server communication (including SSE progress), Alpine.js for client-side UI state, Tailwind CSS 4 for styling, and jinja2-fragments for partial template rendering. See `.claude/rules/tech-stack-2026.md` for patterns. Phase 2 tasks should follow the same TDD pattern — write the test, make it fail, implement, make it pass, commit.

### Task 11: Database Schema

**Files:**
- Create: `scanbox/database.py`
- Create: `tests/integration/test_sessions.py`

Define SQLite tables for sessions, batches, documents, and persons. Use aiosqlite for async access. See `docs/design.md` "Storage Architecture" section for the schema.

Key tables: `persons`, `sessions` (linked to person), `batches` (linked to session, with state field), `documents` (linked to batch, with all metadata fields).

---

### Task 12: FastAPI App Shell

**Files:**
- Create: `scanbox/main.py`
- Create: `scanbox/api/persons.py`
- Create: `scanbox/api/sessions.py`
- Create: `scanbox/api/sse.py`

Mount all routers, static files, Jinja2 templates. Set up startup/shutdown lifecycle (init DB, check scanner). Implement person CRUD and session create/list/get endpoints.

---

### Task 13: Scanning API

**Files:**
- Create: `scanbox/api/scanning.py`
- Create: `scanbox/api/batches.py`
- Create: `tests/integration/test_escl_integration.py`

Implement scan trigger endpoints (`POST /api/batches/{id}/scan-fronts`, `POST /api/batches/{id}/scan-backs`, `POST /api/batches/{id}/skip-backs`). Each endpoint starts the eSCL scan, writes pages to disk as they arrive, and updates batch state. SSE endpoint streams progress.

---

### Task 14: Processing API

**Files:**
- Modify: `scanbox/api/batches.py`
- Create: `scanbox/api/documents.py`

Batch processing trigger (auto-starts after scan completes), document listing, metadata editing (`PATCH /api/documents/{id}`), thumbnail generation (`GET /api/documents/{id}/thumbnail`).

---

### Task 15: Save (Output) API

**Files:**
- Modify: `scanbox/api/sessions.py`
- Create: `scanbox/api/paperless.py`

`POST /api/sessions/{id}/save` — writes to all three destinations (archive, medical records, PaperlessNGX if configured). PaperlessNGX client: upload PDF with tags, document type, correspondent, created date via REST API.

---

### Task 16: Web UI Templates

**Files:**
- Create: all `scanbox/templates/*.html`
- Create: `static/css/app.css`
- Download: `static/css/tailwind.min.css`, `static/js/alpine.min.js`

Build all 6 pages following the wireframes in `docs/design.md`:
1. Home (session list)
2. Scanning (wizard: fronts → flip → backs → process)
3. Results (card layout with thumbnails)
4. Settings
5. Setup wizard (first-run)
6. Practice run

---

### Task 17: Phase 2 Integration Test

**Files:**
- Create: `tests/e2e/test_e2e_synthetic.py`

Full E2E: start app with mock eSCL server → create person → create session → scan (mock) → process → verify output files + API responses.

---

## Phase 3: Polish & Integrations

### Task 18: First-Run Setup Wizard

Implement the 6-step setup flow described in `docs/design.md` "First-Run Setup" section. Stores completion state in config. Redirects to setup if not completed.

### Task 19: Practice Run

Implement the 4-step in-app practice run described in `docs/design.md` "In-App Guided Walkthrough" section. Sequential steps with validation questions. Tracks completion in `config/practice.json`.

### Task 20: Document Boundary Editor

Implement the thumbnail strip editor for manual split correction. `GET /api/batches/{id}/thumbnails` returns page thumbnail images. `POST /api/batches/{id}/splits` accepts user-defined boundary positions. Re-runs naming stage from the new splits.

### Task 21: Docker Build Verification

Build and test the Docker image locally:
```bash
docker build -t scanbox:test .
docker compose up
```
Verify all functionality works in containerized mode. Fix any path/permission issues.

---

## Dependency Install Note

Before starting implementation, install dev dependencies:

```bash
cd /Users/justin/Code/scanbox
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# System deps (macOS)
brew install tesseract poppler ghostscript

# Generate test fixtures
python -m tests.generate_fixtures
```

Also run the git setup:
```bash
bash .githooks/setup.sh
```
