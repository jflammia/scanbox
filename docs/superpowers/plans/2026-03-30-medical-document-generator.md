# Medical Document Generator Framework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Refactor the monolithic `tests/generate_medical_pile.py` into a composable framework with a document registry, configurable pile assembly, artifact injection, manifest output, and Claude Code discoverability.

**Architecture:** Three-layer framework — document layer (individual renders with patient context + config knobs), pile layer (composition of documents into physical sheets), artifact layer (transforms for real-world scanning chaos). Auto-discovery registry, JSON manifest output, `.claude/rules/` integration.

**Tech Stack:** Python 3.13+, fpdf2 (PDF generation), pikepdf (PDF manipulation), dataclasses

**Spec:** `docs/superpowers/specs/2026-03-30-medical-document-generator-design.md`

---

## File Map

### New files to create

| File | Responsibility |
|------|---------------|
| `tests/medical_documents/__init__.py` | Public API: exports `generate_pile`, `list_documents`, `describe_document`, `list_artifacts`, `PatientContext`, `PileConfig`, `DocumentEntry`, `DocumentDef` |
| `tests/medical_documents/helpers.py` | PDF layout helpers extracted from monolith: `new_pdf`, `heading`, `body`, `subheading`, `label_value`, `separator`, `page_footer_text`, `add_blank_page`, `add_near_blank_page`, constants |
| `tests/medical_documents/assembler.py` | `PileAssembler`, all `PileArtifact` subclasses, sheet building, artifact application, front/back split, manifest writing |
| `tests/medical_documents/documents/__init__.py` | Auto-discovery registry: imports sibling modules, builds `REGISTRY` dict |
| `tests/medical_documents/documents/cbc_lab_report.py` | CBC + CMP lab report render + `CBCLabConfig` + `DOCUMENT` |
| `tests/medical_documents/documents/chest_xray.py` | Chest X-ray radiology report render + `DOCUMENT` |
| `tests/medical_documents/documents/discharge_summary.py` | Hospital discharge summary render + `DOCUMENT` |
| `tests/medical_documents/documents/diabetes_care_plan.py` | Diabetes management care plan render + `DOCUMENT` |
| `tests/medical_documents/documents/pathology_report.py` | Surgical pathology report render + `DOCUMENT` |
| `tests/medical_documents/documents/medication_list.py` | Pharmacy medication list render + `DOCUMENT` |
| `tests/medical_documents/documents/insurance_eob.py` | Insurance explanation of benefits render + `DOCUMENT` |
| `tests/medical_documents/documents/referral_letter.py` | Physician referral letter render + `DOCUMENT` |
| `tests/medical_documents/documents/pt_progress_note.py` | Physical therapy SOAP note render + `DOCUMENT` |
| `tests/medical_documents/documents/immunization_record.py` | Immunization history record render + `DOCUMENT` |
| `tests/medical_documents/documents/operative_report.py` | Operative/surgical report render + `DOCUMENT` |
| `.claude/rules/medical-document-generator.md` | Claude Code project rule for framework usage |

### Files to modify

| File | Change |
|------|--------|
| `tests/generate_medical_pile.py` | Replace monolith with thin CLI importing from `tests.medical_documents` |
| `pyproject.toml` | Add `fpdf2` to dev dependencies |

### Files unchanged

| File | Why |
|------|-----|
| `tests/generate_fixtures.py` | Existing tests depend on it |
| `tests/conftest.py` | Fixtures point at `tests/fixtures/` |
| All files under `scanbox/` | No production code changes |

---

## Task 1: Add fpdf2 to dev dependencies

**Files:**
- Modify: `pyproject.toml:30-36`

- [x] **Step 1: Add fpdf2 to pyproject.toml dev deps**

```python
# In pyproject.toml [project.optional-dependencies], add fpdf2:
dev = [
    "pytest>=8",
    "pytest-asyncio>=1.3",
    "respx>=0.22",
    "ruff>=0.15",
    "httpx[http2]>=0.28",
    "fpdf2>=2.8",
]
```

- [x] **Step 2: Verify install**

Run: `uv pip install -e ".[dev]" 2>&1 | tail -3`
Expected: fpdf2 installed successfully (already present from earlier manual install)

- [x] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add fpdf2 to dev dependencies for test PDF generation"
```

---

## Task 2: Create helpers.py — extract PDF layout utilities

**Files:**
- Create: `tests/medical_documents/__init__.py` (empty placeholder)
- Create: `tests/medical_documents/helpers.py`

- [x] **Step 1: Create package directory and empty init**

```bash
mkdir -p tests/medical_documents/documents
```

Create `tests/medical_documents/__init__.py`:
```python
"""Medical document generator framework for test fixture generation."""
```

- [x] **Step 2: Create helpers.py with all layout utilities**

Create `tests/medical_documents/helpers.py` by extracting lines 1-106 from `tests/generate_medical_pile.py`. These are the PDF helper functions that all document generators depend on.

```python
"""PDF layout helpers for medical document generation.

Provides common formatting functions used by all document renderers:
heading, subheading, body text, label-value pairs, separators, and page footers.
"""

from fpdf import FPDF

LETTER_W = 215.9  # mm
LETTER_H = 279.4  # mm


def new_pdf() -> FPDF:
    pdf = FPDF(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=20)
    return pdf


def add_blank_page(pdf: FPDF) -> None:
    pdf.add_page()


def add_near_blank_page(pdf: FPDF, artifact: str = "smudge") -> None:
    """Page with minimal marks -- simulates bleedthrough or faint back-of-form printing."""
    pdf.add_page()
    if artifact == "smudge":
        pdf.set_fill_color(230, 230, 230)
        pdf.ellipse(15, 250, 8, 4, style="F")
        pdf.ellipse(22, 255, 5, 3, style="F")
    elif artifact == "footer":
        pdf.set_font("Helvetica", "", 6)
        pdf.set_text_color(210, 210, 210)
        pdf.set_xy(20, 265)
        pdf.cell(0, 3, "Form MED-2847 Rev. 03/2024")
        pdf.set_text_color(0, 0, 0)


def heading(pdf: FPDF, text: str, font: str = "Helvetica", size: int = 14) -> None:
    pdf.set_font(font, "B", size)
    pdf.cell(0, size * 0.5, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


def subheading(pdf: FPDF, text: str, font: str = "Helvetica", size: int = 11) -> None:
    pdf.set_font(font, "B", size)
    pdf.cell(0, size * 0.45, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def body(pdf: FPDF, text: str, font: str = "Helvetica", size: int = 10) -> None:
    pdf.set_font(font, "", size)
    pdf.multi_cell(0, size * 0.45, text)
    pdf.ln(1)


def label_value(pdf: FPDF, label: str, value: str, font: str = "Helvetica", size: int = 10):
    pdf.set_font(font, "B", size)
    pdf.cell(45, size * 0.5, f"{label}:", new_x="RIGHT")
    pdf.set_font(font, "", size)
    pdf.cell(0, size * 0.5, value, new_x="LMARGIN", new_y="NEXT")


def separator(pdf: FPDF) -> None:
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, LETTER_W - pdf.r_margin, y)
    pdf.ln(3)


def page_footer_text(pdf: FPDF, text: str, font: str = "Helvetica", size: int = 7):
    pdf.set_auto_page_break(auto=False)
    pdf.set_font(font, "", size)
    pdf.set_xy(pdf.l_margin, LETTER_H - 15)
    pdf.cell(0, 3, text, align="C")
    pdf.set_auto_page_break(auto=True, margin=20)
```

- [x] **Step 3: Verify helpers import cleanly**

Run: `.venv/bin/python -c "from tests.medical_documents.helpers import new_pdf, heading, body; print('OK')"`
Expected: `OK`

- [x] **Step 4: Commit**

```bash
git add tests/medical_documents/__init__.py tests/medical_documents/helpers.py
git commit -m "refactor: extract PDF helpers into medical_documents.helpers"
```

---

## Task 3: Create core types — PatientContext, DocumentDef, PileConfig, artifacts

**Files:**
- Modify: `tests/medical_documents/__init__.py`
- Create: `tests/medical_documents/assembler.py`

- [x] **Step 1: Write tests for core types**

Create `tests/unit/test_medical_doc_types.py`:

```python
"""Tests for medical document generator core types."""

from dataclasses import fields

from tests.medical_documents import DocumentDef, DocumentEntry, PatientContext, PileConfig
from tests.medical_documents.assembler import (
    BlankSheetInserted,
    DuplicateDocument,
    DuplicatePage,
    InterleaveDocuments,
    PileArtifact,
    RotatedPage,
    ShufflePages,
    StrayDocument,
    WrongPatientDocument,
)


class TestPatientContext:
    def test_defaults(self):
        p = PatientContext()
        assert p.name == "Elena R. Martinez"
        assert p.name_last_first == "MARTINEZ, ELENA R"
        assert p.dob == "04/12/1968"
        assert p.age == 57
        assert p.gender == "Female"

    def test_custom_patient(self):
        p = PatientContext(name="John Doe", dob="01/01/1990", age=36, gender="Male")
        assert p.name == "John Doe"
        assert p.dob == "01/01/1990"


class TestDocumentDef:
    def test_required_fields(self):
        def noop(pdf, patient, config=None):
            pass

        d = DocumentDef(name="test", description="A test doc", render=noop)
        assert d.name == "test"
        assert d.description == "A test doc"
        assert d.single_sided is False
        assert d.back_artifact == "blank"
        assert d.default_config_cls is None


class TestPileConfig:
    def test_string_shorthand(self):
        cfg = PileConfig(
            patient=PatientContext(),
            documents=["cbc_lab_report", "chest_xray"],
        )
        assert cfg.documents == ["cbc_lab_report", "chest_xray"]

    def test_mixed_entries(self):
        cfg = PileConfig(
            patient=PatientContext(),
            documents=[
                "cbc_lab_report",
                DocumentEntry(name="chest_xray", single_sided=True),
            ],
        )
        assert len(cfg.documents) == 2

    def test_artifacts_default_empty(self):
        cfg = PileConfig(patient=PatientContext(), documents=[])
        assert cfg.artifacts == []


class TestArtifacts:
    def test_all_artifacts_are_pile_artifacts(self):
        artifacts = [
            DuplicatePage(doc_index=0, page=1),
            DuplicateDocument(doc_index=0),
            ShufflePages(doc_index=0, order=[1, 2]),
            InterleaveDocuments(doc_a_index=0, doc_b_index=1, pattern=[0, 1]),
            StrayDocument(document_name="test", position=0),
            WrongPatientDocument(
                document_name="test", patient=PatientContext(), position=0
            ),
            BlankSheetInserted(position=0),
            RotatedPage(doc_index=0, page=1),
        ]
        for a in artifacts:
            assert isinstance(a, PileArtifact)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_medical_doc_types.py -v 2>&1 | tail -5`
Expected: FAIL — `ImportError` because types don't exist yet

- [x] **Step 3: Define PatientContext, DocumentDef, DocumentEntry, PileConfig in __init__.py**

Update `tests/medical_documents/__init__.py`:

```python
"""Medical document generator framework for test fixture generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fpdf import FPDF


@dataclass
class PatientContext:
    """Patient identity shared across all documents in a pile."""

    name: str = "Elena R. Martinez"
    name_last_first: str = "MARTINEZ, ELENA R"
    dob: str = "04/12/1968"
    age: int = 57
    gender: str = "Female"
    mrn: str = "JHH-22847391"
    pcp: str = "Anish Patel, MD"
    insurance: str = "BlueCross PPO"


@dataclass
class DocumentDef:
    """Definition of a document type in the registry."""

    name: str
    description: str
    render: Callable[[FPDF, PatientContext, Any], None]
    default_config_cls: type | None = None
    single_sided: bool = False
    back_artifact: str = "blank"


@dataclass
class DocumentEntry:
    """One document in a pile configuration."""

    name: str
    config: Any = None
    patient: PatientContext | None = None
    single_sided: bool | None = None


@dataclass
class PileConfig:
    """Configuration for generating a pile of scanned documents."""

    patient: PatientContext
    documents: list[DocumentEntry | str]
    artifacts: list = field(default_factory=list)
    output_dir: Path = Path("tests/fixtures/medical_pile")
```

- [x] **Step 4: Create assembler.py with artifact types**

Create `tests/medical_documents/assembler.py`:

```python
"""Pile assembly: sheet building, artifact application, front/back splitting."""

from __future__ import annotations

from dataclasses import dataclass

from tests.medical_documents import PatientContext


class PileArtifact:
    """Base for all pile artifacts (scanning mistakes / organizational chaos)."""

    pass


@dataclass
class DuplicatePage(PileArtifact):
    """Same page scanned twice (ADF double-feed or manual re-scan)."""

    doc_index: int
    page: int  # 1-based


@dataclass
class DuplicateDocument(PileArtifact):
    """Entire document appears twice in the pile."""

    doc_index: int
    insert_at: int | None = None


@dataclass
class ShufflePages(PileArtifact):
    """Pages within a document are out of order."""

    doc_index: int
    order: list[int]  # 1-based page numbers


@dataclass
class InterleaveDocuments(PileArtifact):
    """Pages from two documents got mixed together."""

    doc_a_index: int
    doc_b_index: int
    pattern: list[int]  # 0 = next page from doc_a, 1 = next page from doc_b


@dataclass
class StrayDocument(PileArtifact):
    """A document that doesn't belong in the pile."""

    document_name: str
    position: int
    config: object = None


@dataclass
class WrongPatientDocument(PileArtifact):
    """Someone else's document mixed into this patient's pile."""

    document_name: str
    patient: PatientContext
    position: int
    config: object = None


@dataclass
class BlankSheetInserted(PileArtifact):
    """Random blank sheet in the pile."""

    position: int


@dataclass
class RotatedPage(PileArtifact):
    """Page fed upside-down through the ADF (180 degree rotation)."""

    doc_index: int
    page: int  # 1-based
```

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_medical_doc_types.py -v`
Expected: All tests PASS

- [x] **Step 6: Commit**

```bash
git add tests/medical_documents/__init__.py tests/medical_documents/assembler.py tests/unit/test_medical_doc_types.py
git commit -m "feat: add core types for medical document generator framework"
```

---

## Task 4: Create document registry with auto-discovery

**Files:**
- Create: `tests/medical_documents/documents/__init__.py`

- [x] **Step 1: Write test for registry**

Create `tests/unit/test_medical_doc_registry.py`:

```python
"""Tests for the document auto-discovery registry."""

from tests.medical_documents import DocumentDef
from tests.medical_documents.documents import REGISTRY


class TestRegistry:
    def test_registry_is_dict(self):
        assert isinstance(REGISTRY, dict)

    def test_registry_empty_initially(self):
        # No document modules exist yet, so registry should be empty
        # (This test will change once we add document modules)
        pass

    def test_registry_values_are_document_defs(self):
        for name, doc_def in REGISTRY.items():
            assert isinstance(doc_def, DocumentDef)
            assert doc_def.name == name
            assert isinstance(doc_def.description, str)
            assert len(doc_def.description) > 0
            assert callable(doc_def.render)
```

- [x] **Step 2: Create documents/__init__.py with auto-discovery**

Create `tests/medical_documents/documents/__init__.py`:

```python
"""Document registry — auto-discovers all document modules in this directory."""

import importlib
import pkgutil

from tests.medical_documents import DocumentDef

REGISTRY: dict[str, DocumentDef] = {}


def _discover_documents() -> None:
    """Import all sibling modules and register their DOCUMENT exports."""
    package_path = __path__
    for importer, module_name, is_pkg in pkgutil.iter_modules(package_path):
        if module_name.startswith("_"):
            continue
        module = importlib.import_module(f".{module_name}", package=__name__)
        doc_def = getattr(module, "DOCUMENT", None)
        if isinstance(doc_def, DocumentDef):
            REGISTRY[doc_def.name] = doc_def


_discover_documents()
```

- [x] **Step 3: Run tests to verify they pass**

Run: `pytest tests/unit/test_medical_doc_registry.py -v`
Expected: All tests PASS (registry is empty but valid)

- [x] **Step 4: Commit**

```bash
git add tests/medical_documents/documents/__init__.py tests/unit/test_medical_doc_registry.py
git commit -m "feat: add auto-discovery document registry"
```

---

## Task 5: Extract all 11 document generators into individual modules

This is the largest task — extracting each `doc_*` function from the monolith into its own module file. Each module follows the same pattern:

1. Import helpers from `tests.medical_documents.helpers`
2. Import `PatientContext` and `DocumentDef` from `tests.medical_documents`
3. Define an optional config dataclass with `field(metadata={"description": ...})`
4. Define `render(pdf, patient, config)` — same logic as the original `doc_*` function but using `patient` for identity fields
5. Export `DOCUMENT = DocumentDef(...)`

**Files:**
- Create: all 11 files under `tests/medical_documents/documents/`
- Source: `tests/generate_medical_pile.py` lines 113-1693

- [x] **Step 1: Write test that all 11 documents register**

Add to `tests/unit/test_medical_doc_registry.py`:

```python
EXPECTED_DOCUMENTS = [
    "cbc_lab_report",
    "chest_xray",
    "discharge_summary",
    "diabetes_care_plan",
    "pathology_report",
    "medication_list",
    "insurance_eob",
    "referral_letter",
    "pt_progress_note",
    "immunization_record",
    "operative_report",
]


class TestAllDocumentsRegistered:
    def test_all_expected_documents_present(self):
        for name in EXPECTED_DOCUMENTS:
            assert name in REGISTRY, f"Missing document: {name}"

    def test_no_unexpected_documents(self):
        for name in REGISTRY:
            assert name in EXPECTED_DOCUMENTS, f"Unexpected document: {name}"

    def test_count(self):
        assert len(REGISTRY) == 11
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_medical_doc_registry.py::TestAllDocumentsRegistered -v`
Expected: FAIL — documents not found in empty registry

- [x] **Step 3: Extract all 11 document modules**

For each document, extract from the monolith into its own file. The pattern for each file:

```python
"""<Document description> — <style description>."""

from __future__ import annotations

from dataclasses import dataclass, field

from fpdf import FPDF

from tests.medical_documents import DocumentDef, PatientContext
from tests.medical_documents.helpers import (
    body,
    heading,
    label_value,
    page_footer_text,
    separator,
    subheading,
    # ... only import what this document uses
)


@dataclass
class <DocName>Config:
    """Configuration knobs for <document type>."""
    # fields with metadata={"description": "..."} for discoverability
    pass  # or omit config class entirely for simple documents


def render(pdf: FPDF, patient: PatientContext, config: <DocName>Config | None = None) -> None:
    config = config or <DocName>Config()
    # ... paste the body of doc_<name>() here
    # ... replace hardcoded patient names with patient.name, patient.dob, etc.


DOCUMENT = DocumentDef(
    name="<name>",
    description="<one-line description>",
    render=render,
    default_config_cls=<DocName>Config,  # or None
    single_sided=<True|False>,
    back_artifact="<blank|near_blank_smudge|etc>",
)
```

Extract each document from `tests/generate_medical_pile.py`:

| Module file | Source lines | Description | Single-sided | Config class |
|-------------|-------------|-------------|-------------|-------------|
| `cbc_lab_report.py` | 113-266 | CBC + CMP — Quest Diagnostics style | No | `CBCLabConfig` (wbc, glucose, a1c, date_collected, ordering_md) |
| `chest_xray.py` | 268-353 | Chest X-Ray — hospital radiology style | Yes | None (simple) |
| `discharge_summary.py` | 355-581 | Discharge Summary — Johns Hopkins style | No | None (complex but no useful knobs yet) |
| `diabetes_care_plan.py` | 583-743 | Care Plan — doctor's office style | No | None |
| `pathology_report.py` | 745-849 | Surgical Pathology — dense small font | Yes | None |
| `medication_list.py` | 851-941 | Medication List — CVS pharmacy style | Yes (back_artifact="near_blank_smudge") | None |
| `insurance_eob.py` | 943-1115 | Insurance EOB — dense columnar | No | None |
| `referral_letter.py` | 1117-1219 | Referral Letter — traditional letter format | Yes | None |
| `pt_progress_note.py` | 1221-1386 | PT Progress Note — SOAP format | No | None |
| `immunization_record.py` | 1388-1493 | Immunization Record — government style | Yes | None |
| `operative_report.py` | 1495-1693 | Operative Report — formal surgical style | No (back_artifact on last sheet: "near_blank_footer") | None |

Key changes when extracting:
- Replace hardcoded `"MARTINEZ, ELENA R"` with `patient.name_last_first`
- Replace hardcoded `"Elena R. Martinez"` with `patient.name`
- Replace hardcoded `"04/12/1968"` with `patient.dob`
- Replace hardcoded `"57"` age references with `str(patient.age)`
- Replace hardcoded `"Female"` with `patient.gender`
- Replace hardcoded `"JHH-22847391"` with `patient.mrn`
- Replace hardcoded `"Anish Patel, MD"` / `"Dr. Anish Patel, MD"` with `patient.pcp`
- Replace hardcoded `"BlueCross PPO"` with `patient.insurance`
- For CBC lab report: use `config.wbc`, `config.glucose`, `config.a1c`, `config.date_collected`, `config.ordering_md`
- Leave non-patient content (facility names, provider names other than PCP, clinical text) hardcoded — these are document-specific

For the `operative_report.py`, the `back_artifact` on the `DocumentDef` should remain `"blank"` (the default). The near-blank footer on the last sheet of odd-page-count documents is handled by the assembler, not the document definition. Add a comment in the module noting this.

- [x] **Step 4: Run registry tests to verify all 11 register**

Run: `pytest tests/unit/test_medical_doc_registry.py -v`
Expected: All tests PASS, 11 documents registered

- [x] **Step 5: Write render smoke test for each document**

Add to `tests/unit/test_medical_doc_registry.py`:

```python
from tests.medical_documents.helpers import new_pdf


class TestDocumentRendering:
    """Smoke test: every registered document renders without error."""

    def test_each_document_renders(self):
        patient = PatientContext()
        for name, doc_def in REGISTRY.items():
            pdf = new_pdf()
            doc_def.render(pdf, patient, None)
            assert len(pdf.pages) >= 1, f"{name} produced no pages"

    def test_cbc_with_custom_config(self):
        from tests.medical_documents.documents.cbc_lab_report import CBCLabConfig

        patient = PatientContext(name="John Doe", name_last_first="DOE, JOHN")
        pdf = new_pdf()
        config = CBCLabConfig(wbc=6.5, glucose=95, a1c=5.4)
        REGISTRY["cbc_lab_report"].render(pdf, patient, config)
        assert len(pdf.pages) >= 1

    def test_custom_patient_renders_in_all_docs(self):
        patient = PatientContext(
            name="Jane Smith",
            name_last_first="SMITH, JANE",
            dob="11/03/1982",
            age=43,
            gender="Female",
            mrn="TEST-999",
            pcp="Dr. Test Provider",
            insurance="Aetna HMO",
        )
        for name, doc_def in REGISTRY.items():
            pdf = new_pdf()
            doc_def.render(pdf, patient, None)
            assert len(pdf.pages) >= 1, f"{name} failed with custom patient"
```

- [x] **Step 6: Run all tests**

Run: `pytest tests/unit/test_medical_doc_registry.py -v`
Expected: All tests PASS

- [x] **Step 7: Commit**

```bash
git add tests/medical_documents/documents/ tests/unit/test_medical_doc_registry.py
git commit -m "feat: extract 11 document generators into individual registry modules"
```

---

## Task 6: Build PileAssembler — sheet building and front/back split

**Files:**
- Modify: `tests/medical_documents/assembler.py`
- Modify: `tests/medical_documents/__init__.py`

- [x] **Step 1: Write tests for basic pile assembly (no artifacts)**

Create `tests/unit/test_pile_assembler.py`:

```python
"""Tests for pile assembly — sheet building, front/back splitting, manifest."""

import json
from pathlib import Path

from tests.medical_documents import PatientContext, PileConfig, generate_pile


class TestBasicAssembly:
    def test_minimal_pile(self, tmp_path: Path):
        config = PileConfig(
            patient=PatientContext(),
            documents=["referral_letter"],
            output_dir=tmp_path,
        )
        fronts, backs = generate_pile(config)
        assert fronts.exists()
        assert backs.exists()

    def test_page_counts_single_sided(self, tmp_path: Path):
        """Single-sided 1-page doc = 1 sheet."""
        import pikepdf

        config = PileConfig(
            patient=PatientContext(),
            documents=["referral_letter"],
            output_dir=tmp_path,
        )
        fronts, backs = generate_pile(config)
        f = pikepdf.Pdf.open(fronts)
        b = pikepdf.Pdf.open(backs)
        assert len(f.pages) == 1
        assert len(b.pages) == 1

    def test_page_counts_double_sided(self, tmp_path: Path):
        """Double-sided 2-page doc = 1 sheet."""
        import pikepdf

        config = PileConfig(
            patient=PatientContext(),
            documents=["cbc_lab_report"],
            output_dir=tmp_path,
        )
        fronts, backs = generate_pile(config)
        f = pikepdf.Pdf.open(fronts)
        b = pikepdf.Pdf.open(backs)
        assert len(f.pages) == 1
        assert len(b.pages) == 1

    def test_standard_pile_sheet_count(self, tmp_path: Path):
        """The full 11-doc standard pile should produce 13 sheets."""
        import pikepdf

        config = PileConfig(
            patient=PatientContext(),
            documents=[
                "cbc_lab_report", "chest_xray", "discharge_summary",
                "diabetes_care_plan", "pathology_report", "medication_list",
                "insurance_eob", "referral_letter", "pt_progress_note",
                "immunization_record", "operative_report",
            ],
            output_dir=tmp_path,
        )
        fronts, backs = generate_pile(config)
        f = pikepdf.Pdf.open(fronts)
        b = pikepdf.Pdf.open(backs)
        assert len(f.pages) == 13
        assert len(b.pages) == 13

    def test_manifest_written(self, tmp_path: Path):
        config = PileConfig(
            patient=PatientContext(),
            documents=["referral_letter"],
            output_dir=tmp_path,
        )
        generate_pile(config)
        manifest_path = tmp_path / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["num_sheets"] == 1
        assert len(manifest["documents"]) == 1
        assert manifest["documents"][0]["name"] == "referral_letter"

    def test_manifest_sheet_details(self, tmp_path: Path):
        config = PileConfig(
            patient=PatientContext(),
            documents=["cbc_lab_report"],
            output_dir=tmp_path,
        )
        generate_pile(config)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert len(manifest["sheets"]) == 1
        sheet = manifest["sheets"][0]
        assert sheet["front"]["doc"] == "cbc_lab_report"
        assert sheet["front"]["page"] == 1
        assert sheet["back"]["type"] == "content"
        assert sheet["back"]["page"] == 2

    def test_document_entry_overrides(self, tmp_path: Path):
        """DocumentEntry can override single_sided."""
        import pikepdf

        from tests.medical_documents import DocumentEntry

        config = PileConfig(
            patient=PatientContext(),
            documents=[
                DocumentEntry(name="cbc_lab_report", single_sided=True),
            ],
            output_dir=tmp_path,
        )
        fronts, backs = generate_pile(config)
        f = pikepdf.Pdf.open(fronts)
        # 2-page doc forced single-sided = 2 sheets
        assert len(f.pages) == 2

    def test_custom_patient_in_manifest(self, tmp_path: Path):
        patient = PatientContext(name="Test Patient", mrn="TEST-1")
        config = PileConfig(
            patient=patient,
            documents=["referral_letter"],
            output_dir=tmp_path,
        )
        generate_pile(config)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["patient"]["name"] == "Test Patient"
        assert manifest["patient"]["mrn"] == "TEST-1"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_pile_assembler.py -v 2>&1 | tail -5`
Expected: FAIL — `generate_pile` not yet implemented

- [x] **Step 3: Implement PileAssembler in assembler.py**

Add to `tests/medical_documents/assembler.py` (after the artifact class definitions):

```python
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pikepdf

from tests.medical_documents import DocumentDef, DocumentEntry, PatientContext, PileConfig
from tests.medical_documents.helpers import add_blank_page, add_near_blank_page, new_pdf


class PileAssembler:
    """Builds fronts.pdf + backs.pdf from a PileConfig."""

    def generate(self, config: PileConfig) -> tuple[Path, Path]:
        from tests.medical_documents.documents import REGISTRY

        config.output_dir.mkdir(parents=True, exist_ok=True)

        # Normalize document entries
        entries = []
        for doc in config.documents:
            if isinstance(doc, str):
                entries.append(DocumentEntry(name=doc))
            else:
                entries.append(doc)

        # Render each document into its own PDF
        doc_pdfs: list[pikepdf.Pdf] = []
        doc_metas: list[dict] = []
        for i, entry in enumerate(entries):
            doc_def = REGISTRY[entry.name]
            patient = entry.patient or config.patient
            single_sided = entry.single_sided if entry.single_sided is not None else doc_def.single_sided
            pdf_bytes = self._render_doc(doc_def, patient, entry.config)
            doc_pdf = pikepdf.Pdf.open(BytesIO(pdf_bytes))
            doc_pdfs.append(doc_pdf)
            doc_metas.append({
                "index": i,
                "name": entry.name,
                "patient": patient.name,
                "pages": len(doc_pdf.pages),
                "single_sided": single_sided,
                "back_artifact": doc_def.back_artifact,
            })

        # Build sheet list
        sheets = self._build_sheets(doc_pdfs, doc_metas)

        # TODO: Apply artifacts here (Task 7)

        # Split into fronts and backs
        fronts_path, backs_path = self._split_fronts_backs(sheets, config.output_dir)

        # Write manifest
        self._write_manifest(config, doc_metas, sheets)

        return fronts_path, backs_path

    def _render_doc(self, doc_def: DocumentDef, patient: PatientContext, config) -> bytes:
        pdf = new_pdf()
        doc_def.render(pdf, patient, config)
        buf = BytesIO()
        pdf.output(buf)
        return buf.getvalue()

    def _build_sheets(self, doc_pdfs, doc_metas):
        """Assign document pages to physical sheets.

        Returns list of dicts:
            {"front": pikepdf_page, "back": pikepdf_page | None,
             "back_type": "content" | "blank" | "near_blank_*",
             "front_doc": str, "front_page": int,
             "back_doc": str | None, "back_page": int | None}
        """
        sheets = []
        for doc_pdf, meta in zip(doc_pdfs, doc_metas):
            num_pages = meta["pages"]
            single_sided = meta["single_sided"]
            doc_name = meta["name"]
            back_artifact = meta["back_artifact"]

            if single_sided:
                for p in range(num_pages):
                    sheets.append({
                        "front": doc_pdf.pages[p],
                        "back": None,
                        "back_type": back_artifact,
                        "front_doc": doc_name,
                        "front_page": p + 1,
                        "back_doc": None,
                        "back_page": None,
                    })
            else:
                num_sheets = (num_pages + 1) // 2
                for s in range(num_sheets):
                    front_idx = s * 2
                    back_idx = s * 2 + 1
                    if back_idx < num_pages:
                        sheets.append({
                            "front": doc_pdf.pages[front_idx],
                            "back": doc_pdf.pages[back_idx],
                            "back_type": "content",
                            "front_doc": doc_name,
                            "front_page": front_idx + 1,
                            "back_doc": doc_name,
                            "back_page": back_idx + 1,
                        })
                    else:
                        sheets.append({
                            "front": doc_pdf.pages[front_idx],
                            "back": None,
                            "back_type": "blank",
                            "front_doc": doc_name,
                            "front_page": front_idx + 1,
                            "back_doc": None,
                            "back_page": None,
                        })

        return sheets

    def _split_fronts_backs(self, sheets, output_dir: Path) -> tuple[Path, Path]:
        fronts_pdf = pikepdf.Pdf.new()
        backs_pdf = pikepdf.Pdf.new()

        for sheet in sheets:
            fronts_pdf.pages.append(sheet["front"])

        blank_bytes = self._make_page_pdf("blank")
        smudge_bytes = self._make_page_pdf("near_blank_smudge")
        footer_bytes = self._make_page_pdf("near_blank_footer")

        page_cache = {
            "blank": blank_bytes,
            "near_blank_smudge": smudge_bytes,
            "near_blank_footer": footer_bytes,
        }

        for sheet in reversed(sheets):
            if sheet["back_type"] == "content" and sheet["back"] is not None:
                backs_pdf.pages.append(sheet["back"])
            else:
                bt = sheet["back_type"]
                pdf_bytes = page_cache.get(bt, blank_bytes)
                tmp = pikepdf.Pdf.open(pdf_bytes)
                backs_pdf.pages.append(tmp.pages[0])

        fronts_path = output_dir / "fronts.pdf"
        backs_path = output_dir / "backs.pdf"
        fronts_pdf.save(fronts_path)
        backs_pdf.save(backs_path)
        return fronts_path, backs_path

    def _make_page_pdf(self, page_type: str) -> BytesIO:
        pdf = new_pdf()
        if page_type == "blank":
            add_blank_page(pdf)
        elif page_type == "near_blank_smudge":
            add_near_blank_page(pdf, "smudge")
        elif page_type == "near_blank_footer":
            add_near_blank_page(pdf, "footer")
        else:
            add_blank_page(pdf)
        buf = BytesIO()
        pdf.output(buf)
        buf.seek(0)
        return buf

    def _write_manifest(self, config: PileConfig, doc_metas, sheets):
        # Build sheet details for manifest
        sheet_details = []
        for i, sheet in enumerate(sheets):
            back_info = {"type": sheet["back_type"]}
            if sheet["back_type"] == "content":
                back_info["doc"] = sheet["back_doc"]
                back_info["page"] = sheet["back_page"]
            sheet_details.append({
                "index": i,
                "front": {"doc": sheet["front_doc"], "page": sheet["front_page"]},
                "back": back_info,
            })

        # Build document details with sheet assignments
        doc_details = []
        for meta in doc_metas:
            doc_sheets = [
                i for i, s in enumerate(sheets) if s["front_doc"] == meta["name"]
            ]
            front_pages = [i for i, s in enumerate(sheets) if s["front_doc"] == meta["name"]]
            back_pages = [
                i for i, s in enumerate(sheets)
                if s["back_doc"] == meta["name"]
            ]
            doc_details.append({
                "index": meta["index"],
                "name": meta["name"],
                "patient": meta["patient"],
                "pages": meta["pages"],
                "single_sided": meta["single_sided"],
                "sheets": doc_sheets,
                "front_pages": front_pages,
                "back_pages": back_pages,
            })

        num_sheets = len(sheets)
        manifest = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "patient": {
                "name": config.patient.name,
                "dob": config.patient.dob,
                "mrn": config.patient.mrn,
            },
            "num_sheets": num_sheets,
            "num_logical_pages": sum(m["pages"] for m in doc_metas),
            "documents": doc_details,
            "sheets": sheet_details,
            "backs_order": list(range(num_sheets - 1, -1, -1)),
            "artifacts_applied": [],
            "content_backs": sum(1 for s in sheets if s["back_type"] == "content"),
            "blank_backs": sum(1 for s in sheets if s["back_type"] == "blank"),
            "near_blank_backs": sum(
                1 for s in sheets if s["back_type"].startswith("near_blank")
            ),
        }

        manifest_path = config.output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
```

- [x] **Step 4: Add generate_pile to __init__.py**

Append to `tests/medical_documents/__init__.py`:

```python
def generate_pile(config: PileConfig) -> tuple[Path, Path]:
    """Generate fronts.pdf and backs.pdf from a pile configuration."""
    from tests.medical_documents.assembler import PileAssembler

    assembler = PileAssembler()
    return assembler.generate(config)
```

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_pile_assembler.py -v`
Expected: All tests PASS

- [x] **Step 6: Commit**

```bash
git add tests/medical_documents/assembler.py tests/medical_documents/__init__.py tests/unit/test_pile_assembler.py
git commit -m "feat: implement PileAssembler with sheet building, front/back split, manifest"
```

---

## Task 7: Implement artifact application

**Files:**
- Modify: `tests/medical_documents/assembler.py`

- [x] **Step 1: Write tests for each artifact type**

Create `tests/unit/test_pile_artifacts.py`:

```python
"""Tests for pile artifact application."""

import json
from pathlib import Path

import pikepdf

from tests.medical_documents import DocumentEntry, PatientContext, PileConfig, generate_pile
from tests.medical_documents.assembler import (
    BlankSheetInserted,
    DuplicateDocument,
    DuplicatePage,
    ShufflePages,
    WrongPatientDocument,
)


class TestDuplicatePage:
    def test_adds_extra_sheet(self, tmp_path: Path):
        config = PileConfig(
            patient=PatientContext(),
            documents=["referral_letter"],
            artifacts=[DuplicatePage(doc_index=0, page=1)],
            output_dir=tmp_path,
        )
        fronts, _ = generate_pile(config)
        f = pikepdf.Pdf.open(fronts)
        # 1-page single-sided doc + 1 duplicate = 2 sheets
        assert len(f.pages) == 2

    def test_manifest_records_artifact(self, tmp_path: Path):
        config = PileConfig(
            patient=PatientContext(),
            documents=["referral_letter"],
            artifacts=[DuplicatePage(doc_index=0, page=1)],
            output_dir=tmp_path,
        )
        generate_pile(config)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert len(manifest["artifacts_applied"]) == 1
        assert manifest["artifacts_applied"][0]["type"] == "DuplicatePage"


class TestDuplicateDocument:
    def test_doubles_sheet_count(self, tmp_path: Path):
        config = PileConfig(
            patient=PatientContext(),
            documents=["referral_letter"],
            artifacts=[DuplicateDocument(doc_index=0)],
            output_dir=tmp_path,
        )
        fronts, _ = generate_pile(config)
        f = pikepdf.Pdf.open(fronts)
        assert len(f.pages) == 2


class TestShufflePages:
    def test_reorders_sheets(self, tmp_path: Path):
        config = PileConfig(
            patient=PatientContext(),
            documents=["discharge_summary"],  # 3 pages
            artifacts=[ShufflePages(doc_index=0, order=[3, 1, 2])],
            output_dir=tmp_path,
        )
        fronts, _ = generate_pile(config)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert len(manifest["artifacts_applied"]) == 1
        assert manifest["artifacts_applied"][0]["type"] == "ShufflePages"


class TestBlankSheetInserted:
    def test_inserts_blank(self, tmp_path: Path):
        config = PileConfig(
            patient=PatientContext(),
            documents=["referral_letter"],
            artifacts=[BlankSheetInserted(position=0)],
            output_dir=tmp_path,
        )
        fronts, _ = generate_pile(config)
        f = pikepdf.Pdf.open(fronts)
        assert len(f.pages) == 2


class TestWrongPatientDocument:
    def test_inserts_foreign_doc(self, tmp_path: Path):
        config = PileConfig(
            patient=PatientContext(),
            documents=["referral_letter"],
            artifacts=[
                WrongPatientDocument(
                    document_name="cbc_lab_report",
                    patient=PatientContext(name="Wrong Person", name_last_first="PERSON, WRONG"),
                    position=0,
                ),
            ],
            output_dir=tmp_path,
        )
        fronts, _ = generate_pile(config)
        f = pikepdf.Pdf.open(fronts)
        # CBC is 1 sheet (double-sided) + referral is 1 sheet = 2
        assert len(f.pages) == 2

    def test_manifest_records_wrong_patient(self, tmp_path: Path):
        config = PileConfig(
            patient=PatientContext(),
            documents=["referral_letter"],
            artifacts=[
                WrongPatientDocument(
                    document_name="cbc_lab_report",
                    patient=PatientContext(name="Wrong Person", name_last_first="PERSON, WRONG"),
                    position=0,
                ),
            ],
            output_dir=tmp_path,
        )
        generate_pile(config)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["artifacts_applied"][0]["patient"] == "Wrong Person"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_pile_artifacts.py -v 2>&1 | tail -5`
Expected: FAIL — artifacts not yet applied

- [x] **Step 3: Implement artifact application in PileAssembler**

Add method `_apply_artifacts` to `PileAssembler` in `assembler.py`, and call it from `generate()` where the TODO comment is. Replace the `# TODO: Apply artifacts here (Task 7)` line with `sheets, artifact_log = self._apply_artifacts(config, sheets, doc_pdfs, doc_metas)`. Then pass `artifact_log` to `_write_manifest`.

```python
def _apply_artifacts(self, config, sheets, doc_pdfs, doc_metas):
    """Apply artifacts to the sheet list. Returns (modified_sheets, artifact_log)."""
    from tests.medical_documents.documents import REGISTRY

    artifact_log = []

    for artifact in config.artifacts:
        if isinstance(artifact, ShufflePages):
            sheets, log = self._apply_shuffle(artifact, sheets, doc_metas)
            artifact_log.append(log)
        elif isinstance(artifact, DuplicatePage):
            sheets, log = self._apply_duplicate_page(artifact, sheets, doc_pdfs, doc_metas)
            artifact_log.append(log)
        elif isinstance(artifact, DuplicateDocument):
            sheets, log = self._apply_duplicate_doc(artifact, sheets, doc_pdfs, doc_metas)
            artifact_log.append(log)
        elif isinstance(artifact, BlankSheetInserted):
            sheets, log = self._apply_blank_insert(artifact, sheets)
            artifact_log.append(log)
        elif isinstance(artifact, (StrayDocument, WrongPatientDocument)):
            sheets, log = self._apply_foreign_doc(artifact, config, sheets, REGISTRY)
            artifact_log.append(log)
        elif isinstance(artifact, RotatedPage):
            sheets, log = self._apply_rotation(artifact, sheets)
            artifact_log.append(log)

    return sheets, artifact_log
```

Implement each `_apply_*` method. Key implementations:

**`_apply_duplicate_page`**: Find sheets belonging to `doc_index`, find the sheet containing the specified page as front, create a copy sheet (same front page, blank back), insert it after the original.

**`_apply_duplicate_doc`**: Re-render the document, build sheets from it, insert at `insert_at` or right after the original document's last sheet.

**`_apply_shuffle`**: Collect all sheets for the document, reorder their front pages according to `order`, rebuild sheet list.

**`_apply_blank_insert`**: Create a blank sheet dict and insert at `position`.

**`_apply_foreign_doc`**: For `WrongPatientDocument`, render the named document with the wrong patient, build sheets, insert at position. For `StrayDocument`, same but with the pile's patient.

**`_apply_rotation`**: Find the sheet, rotate the pikepdf page 180 degrees using `page.rotate(180, relative=True)`.

Each method returns `(modified_sheets, log_entry_dict)`.

- [x] **Step 4: Update _write_manifest to accept artifact_log**

Change `_write_manifest` signature to accept `artifact_log` and write it into `manifest["artifacts_applied"]`.

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_pile_artifacts.py -v`
Expected: All tests PASS

- [x] **Step 6: Commit**

```bash
git add tests/medical_documents/assembler.py tests/unit/test_pile_artifacts.py
git commit -m "feat: implement pile artifact application (duplicates, shuffle, inserts, rotation)"
```

---

## Task 8: Implement discoverability API

**Files:**
- Modify: `tests/medical_documents/__init__.py`

- [x] **Step 1: Write tests for discoverability functions**

Create `tests/unit/test_medical_doc_discovery.py`:

```python
"""Tests for the discoverability API."""

from tests.medical_documents import describe_document, list_artifacts, list_documents


class TestListDocuments:
    def test_returns_list(self):
        result = list_documents()
        assert isinstance(result, list)
        assert len(result) == 11

    def test_entry_shape(self):
        result = list_documents()
        entry = result[0]
        assert "name" in entry
        assert "description" in entry
        assert "single_sided" in entry
        assert isinstance(entry["description"], str)


class TestDescribeDocument:
    def test_known_document(self):
        result = describe_document("cbc_lab_report")
        assert result["name"] == "cbc_lab_report"
        assert "config_fields" in result
        assert "wbc" in result["config_fields"]
        assert "description" in result["config_fields"]["wbc"]

    def test_unknown_document(self):
        result = describe_document("nonexistent")
        assert result is None

    def test_doc_without_config(self):
        result = describe_document("chest_xray")
        assert result is not None
        assert result["config_fields"] == {}


class TestListArtifacts:
    def test_returns_list(self):
        result = list_artifacts()
        assert isinstance(result, list)
        assert len(result) == 8  # all artifact types

    def test_entry_shape(self):
        result = list_artifacts()
        entry = result[0]
        assert "name" in entry
        assert "description" in entry
        assert "fields" in entry
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_medical_doc_discovery.py -v 2>&1 | tail -5`
Expected: FAIL — functions not yet defined

- [x] **Step 3: Implement list_documents, describe_document, list_artifacts**

Add to `tests/medical_documents/__init__.py`:

```python
import dataclasses


def list_documents() -> list[dict]:
    """List all registered document types with metadata for discoverability."""
    from tests.medical_documents.documents import REGISTRY

    result = []
    for name, doc_def in sorted(REGISTRY.items()):
        config_fields = []
        if doc_def.default_config_cls:
            config_fields = [f.name for f in dataclasses.fields(doc_def.default_config_cls)]
        result.append({
            "name": name,
            "description": doc_def.description,
            "single_sided": doc_def.single_sided,
            "config_fields": config_fields,
        })
    return result


def describe_document(name: str) -> dict | None:
    """Describe a document type in detail, including config field metadata."""
    from tests.medical_documents.documents import REGISTRY

    doc_def = REGISTRY.get(name)
    if doc_def is None:
        return None

    config_fields = {}
    if doc_def.default_config_cls:
        for f in dataclasses.fields(doc_def.default_config_cls):
            field_info = {
                "type": f.type if isinstance(f.type, str) else f.type.__name__,
                "default": f.default if f.default is not dataclasses.MISSING else None,
            }
            if f.metadata and "description" in f.metadata:
                field_info["description"] = f.metadata["description"]
            config_fields[f.name] = field_info

    return {
        "name": doc_def.name,
        "description": doc_def.description,
        "single_sided": doc_def.single_sided,
        "back_artifact": doc_def.back_artifact,
        "config_cls": doc_def.default_config_cls.__name__ if doc_def.default_config_cls else None,
        "config_fields": config_fields,
    }


def list_artifacts() -> list[dict]:
    """List all available pile artifact types."""
    from tests.medical_documents import assembler

    result = []
    for name in dir(assembler):
        obj = getattr(assembler, name)
        if (
            isinstance(obj, type)
            and issubclass(obj, assembler.PileArtifact)
            and obj is not assembler.PileArtifact
        ):
            fields_list = [
                f.name for f in dataclasses.fields(obj)
            ] if dataclasses.is_dataclass(obj) else []
            result.append({
                "name": name,
                "description": obj.__doc__ or "",
                "fields": fields_list,
            })
    return sorted(result, key=lambda x: x["name"])
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_medical_doc_discovery.py -v`
Expected: All tests PASS

- [x] **Step 5: Commit**

```bash
git add tests/medical_documents/__init__.py tests/unit/test_medical_doc_discovery.py
git commit -m "feat: add discoverability API (list_documents, describe_document, list_artifacts)"
```

---

## Task 9: Replace monolith with thin CLI + predefined recipes

**Files:**
- Modify: `tests/generate_medical_pile.py`

- [x] **Step 1: Replace the monolith**

Overwrite `tests/generate_medical_pile.py` with the thin CLI:

```python
"""Generate medical document pile test fixtures.

Usage:
    python -m tests.generate_medical_pile                # standard pile (default)
    python -m tests.generate_medical_pile standard       # same as above
    python -m tests.generate_medical_pile chaos          # pile with scanning artifacts
    python -m tests.generate_medical_pile minimal        # quick 3-doc pile
"""

import sys
from pathlib import Path

from tests.medical_documents import PatientContext, PileConfig, generate_pile
from tests.medical_documents.assembler import (
    BlankSheetInserted,
    DuplicatePage,
    ShufflePages,
    WrongPatientDocument,
)


def standard_pile() -> PileConfig:
    """The original 11-document pile. Clean scan, no artifacts."""
    return PileConfig(
        patient=PatientContext(),
        documents=[
            "cbc_lab_report",
            "chest_xray",
            "discharge_summary",
            "diabetes_care_plan",
            "pathology_report",
            "medication_list",
            "insurance_eob",
            "referral_letter",
            "pt_progress_note",
            "immunization_record",
            "operative_report",
        ],
    )


def chaos_pile() -> PileConfig:
    """Realistic mess: duplicates, wrong order, wrong patient mixed in."""
    return PileConfig(
        patient=PatientContext(),
        documents=[
            "cbc_lab_report",
            "chest_xray",
            "discharge_summary",
            "diabetes_care_plan",
            "pathology_report",
            "medication_list",
            "insurance_eob",
            "referral_letter",
            "pt_progress_note",
            "immunization_record",
            "operative_report",
        ],
        artifacts=[
            DuplicatePage(doc_index=0, page=1),
            ShufflePages(doc_index=2, order=[1, 3, 2]),
            WrongPatientDocument(
                document_name="cbc_lab_report",
                patient=PatientContext(
                    name="Robert J. Thompson",
                    name_last_first="THOMPSON, ROBERT J",
                    dob="09/22/1945",
                    age=80,
                    gender="Male",
                    mrn="QD-1192847",
                ),
                position=7,
            ),
            BlankSheetInserted(position=4),
        ],
    )


def minimal_pile() -> PileConfig:
    """Quick 3-document pile for fast iteration."""
    return PileConfig(
        patient=PatientContext(),
        documents=["cbc_lab_report", "chest_xray", "referral_letter"],
    )


RECIPES = {
    "standard": standard_pile,
    "chaos": chaos_pile,
    "minimal": minimal_pile,
}

if __name__ == "__main__":
    recipe_name = sys.argv[1] if len(sys.argv) > 1 else "standard"
    if recipe_name not in RECIPES:
        print(f"Unknown recipe: {recipe_name}")
        print(f"Available: {', '.join(RECIPES)}")
        sys.exit(1)
    config = RECIPES[recipe_name]()
    fronts, backs = generate_pile(config)
    print(f"\nOutput: {fronts.parent}/")
```

- [x] **Step 2: Run the standard recipe and verify output matches original**

Run: `.venv/bin/python -m tests.generate_medical_pile standard`
Expected: 13 sheets, fronts.pdf + backs.pdf + manifest.json

Verify page count matches original:
```bash
.venv/bin/python -c "
import pikepdf
f = pikepdf.Pdf.open('tests/fixtures/medical_pile/fronts.pdf')
b = pikepdf.Pdf.open('tests/fixtures/medical_pile/backs.pdf')
assert len(f.pages) == 13, f'Expected 13 fronts, got {len(f.pages)}'
assert len(b.pages) == 13, f'Expected 13 backs, got {len(b.pages)}'
print('Page counts match: 13 fronts, 13 backs')
"
```

- [x] **Step 3: Run all tests to verify nothing broke**

Run: `pytest tests/unit/test_medical_doc_types.py tests/unit/test_medical_doc_registry.py tests/unit/test_pile_assembler.py tests/unit/test_pile_artifacts.py tests/unit/test_medical_doc_discovery.py -v`
Expected: All tests PASS

- [x] **Step 4: Commit**

```bash
git add tests/generate_medical_pile.py
git commit -m "refactor: replace monolith with thin CLI using medical_documents framework"
```

---

## Task 10: Add Claude Code project rule

**Files:**
- Create: `.claude/rules/medical-document-generator.md`

- [x] **Step 1: Create the rule file**

Create `.claude/rules/medical-document-generator.md`:

```markdown
# Medical Document Generator

Test fixture framework at `tests/medical_documents/` for generating realistic
scanned medical document piles (fronts.pdf + backs.pdf).

## Quick Reference

```python
from tests.medical_documents import (
    generate_pile, list_documents, describe_document, list_artifacts,
    PatientContext, PileConfig, DocumentEntry,
)
from tests.medical_documents.assembler import (
    DuplicatePage, DuplicateDocument, ShufflePages, InterleaveDocuments,
    StrayDocument, WrongPatientDocument, BlankSheetInserted, RotatedPage,
)

# Discover what's available
list_documents()                    # All document types with descriptions
describe_document("cbc_lab_report") # Detailed config fields for one type
list_artifacts()                    # All artifact types with fields

# Generate the standard 11-document pile
generate_pile(PileConfig(
    patient=PatientContext(),
    documents=["cbc_lab_report", "chest_xray", "discharge_summary", ...],
))

# Generate with a custom patient and artifacts
generate_pile(PileConfig(
    patient=PatientContext(name="Jane Doe", dob="05/20/1990", age=36),
    documents=["cbc_lab_report", "discharge_summary"],
    artifacts=[DuplicatePage(doc_index=0, page=1)],
    output_dir=Path("tests/fixtures/my_custom_pile"),
))
```

## Adding a New Document Type

1. Create `tests/medical_documents/documents/<name>.py`
2. Implement `render(pdf, patient, config)` function using helpers from `tests.medical_documents.helpers`
3. Export `DOCUMENT = DocumentDef(name="<name>", description="...", render=render)`
4. Auto-registered -- no other files to edit

## Running from CLI

```bash
python -m tests.generate_medical_pile                    # standard 11-doc pile
python -m tests.generate_medical_pile chaos              # pile with scanning artifacts
python -m tests.generate_medical_pile minimal            # quick 3-doc pile
```

Output: `tests/fixtures/medical_pile/` (fronts.pdf, backs.pdf, manifest.json)

## Artifacts (Scanning Mistakes)

| Artifact | What it simulates |
|----------|------------------|
| `DuplicatePage(doc_index, page)` | Same page scanned twice |
| `DuplicateDocument(doc_index)` | Entire document scanned twice |
| `ShufflePages(doc_index, order)` | Pages fed in wrong order |
| `InterleaveDocuments(doc_a_index, doc_b_index, pattern)` | Two docs' pages mixed together |
| `StrayDocument(document_name, position)` | Unrelated document in the pile |
| `WrongPatientDocument(document_name, patient, position)` | Another patient's document |
| `BlankSheetInserted(position)` | Random blank sheet |
| `RotatedPage(doc_index, page)` | Page fed upside-down (180 degrees) |
```

- [x] **Step 2: Commit**

```bash
git add .claude/rules/medical-document-generator.md
git commit -m "docs: add Claude Code rule for medical document generator framework"
```

---

## Task 11: Final verification — run full test suite + format

- [x] **Step 1: Format all new code**

Run: `ruff format tests/medical_documents/ tests/unit/test_medical_doc*.py tests/unit/test_pile*.py tests/generate_medical_pile.py`

- [x] **Step 2: Lint all new code**

Run: `ruff check tests/medical_documents/ tests/unit/test_medical_doc*.py tests/unit/test_pile*.py tests/generate_medical_pile.py`
Expected: No errors

- [x] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: All tests pass (existing 532 + new tests)

- [x] **Step 4: Generate standard pile and verify output**

Run: `.venv/bin/python -m tests.generate_medical_pile standard`

Verify:
```bash
.venv/bin/python -c "
import json, pikepdf
f = pikepdf.Pdf.open('tests/fixtures/medical_pile/fronts.pdf')
b = pikepdf.Pdf.open('tests/fixtures/medical_pile/backs.pdf')
m = json.loads(open('tests/fixtures/medical_pile/manifest.json').read())
print(f'Fronts: {len(f.pages)} pages')
print(f'Backs: {len(b.pages)} pages')
print(f'Manifest: {m[\"num_sheets\"]} sheets, {m[\"num_logical_pages\"]} pages, {len(m[\"documents\"])} documents')
assert len(f.pages) == 13
assert len(b.pages) == 13
assert m['num_sheets'] == 13
print('All checks passed')
"
```

- [x] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: final formatting and verification of medical document generator framework"
```
