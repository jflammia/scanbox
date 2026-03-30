# Medical Document Generator Framework

A test fixture framework for generating realistic piles of medical documents as fronts/backs PDFs, simulating simplex ADF scanning. Supports configurable document content, multiple patients, and real-world scanning artifacts (duplicates, misordering, wrong-patient documents).

## Problem

The current `tests/generate_medical_pile.py` is an 1,856-line monolith. All 11 document generators, PDF helpers, and assembly logic live in one file. Adding a new document type means editing a massive file. There's no way to compose different piles, vary patient data, or simulate scanning mistakes. The existing `tests/generate_fixtures.py` is a separate simpler generator — it stays as-is since existing tests depend on it.

## Architecture

Three layers, each independently configurable:

```
Document Layer        Pile Layer              Artifact Layer
(what's on the page)  (which docs, which      (real-world chaos)
                       patient, sidedness)
       |                    |                       |
       v                    v                       v
  DocumentDef  --->   PileConfig    --->   PileArtifacts
  + PatientCtx        + doc list           + transforms
  + doc-specific      + patient(s)         applied to sheet list
    config            + sidedness
       |                    |                       |
       +--------------------+-----------------------+
                            |
                            v
                      PileAssembler
                   (fronts.pdf + backs.pdf)
```

## Package Structure

```
tests/
  medical_documents/
    __init__.py                 # Public API: generate_pile, REGISTRY, PatientContext, etc.
    helpers.py                  # PDF layout helpers (heading, body, label_value, separator, etc.)
    assembler.py                # PileAssembler: sheet building, artifact application, front/back split
    documents/
      __init__.py               # Document registry (auto-imports all modules in this dir)
      cbc_lab_report.py         # ~150 lines each
      chest_xray.py
      diabetes_care_plan.py
      discharge_summary.py
      immunization_record.py
      insurance_eob.py
      medication_list.py
      operative_report.py
      pathology_report.py
      pt_progress_note.py
      referral_letter.py
  generate_medical_pile.py      # CLI entry point with predefined pile recipes
```

## Document Layer

### PatientContext

Shared identity used by all documents in a pile for narrative coherence.

```python
@dataclass
class PatientContext:
    name: str = "Elena R. Martinez"
    name_last_first: str = "MARTINEZ, ELENA R"   # lab report format
    dob: str = "04/12/1968"
    age: int = 57
    gender: str = "Female"
    mrn: str = "JHH-22847391"
    pcp: str = "Anish Patel, MD"
    insurance: str = "BlueCross PPO"
```

Multiple `PatientContext` instances can exist in one pile (for wrong-patient artifacts).

### DocumentDef

Each document module exports a `DOCUMENT` constant:

```python
# In cbc_lab_report.py
@dataclass
class CBCLabConfig:
    """Knobs specific to this document type."""
    wbc: float = 11.2
    glucose: int = 142
    a1c: float = 7.2
    date_collected: str = "03/15/2026"
    ordering_md: str = "Dr. Anish Patel, MD"

def render(pdf: FPDF, patient: PatientContext, config: CBCLabConfig | None = None) -> None:
    config = config or CBCLabConfig()
    # ... adds pages to pdf using patient + config ...

DOCUMENT = DocumentDef(
    name="cbc_lab_report",
    render=render,
    default_config_cls=CBCLabConfig,
    single_sided=False,
    back_artifact="blank",
)
```

The `DocumentDef` dataclass (see Discoverability section for full definition with `description` field).

### Document Registry

`documents/__init__.py` auto-discovers all sibling modules that export a `DOCUMENT` attribute:

```python
REGISTRY: dict[str, DocumentDef] = {}
# Auto-import all .py files in this directory, register their DOCUMENT
```

Accessed via `from tests.medical_documents import REGISTRY`.

### Adding a New Document Type

1. Create `tests/medical_documents/documents/consent_form.py`
2. Define a `render(pdf, patient, config)` function
3. Export `DOCUMENT = DocumentDef(name="consent_form", render=render, ...)`
4. It's automatically available in `REGISTRY` — no other files to edit

## Pile Layer

### PileConfig

Describes which documents to include and how they're printed:

```python
@dataclass
class DocumentEntry:
    """One document in a pile."""
    name: str                           # Key into REGISTRY
    config: Any = None                  # Doc-specific config override, or None for defaults
    patient: PatientContext | None = None  # Override pile-level patient for this doc
    single_sided: bool | None = None    # Override document default

@dataclass
class PileConfig:
    patient: PatientContext             # Default patient for all documents
    documents: list[DocumentEntry | str]  # str is shorthand for DocumentEntry(name=str)
    artifacts: list[PileArtifact] = field(default_factory=list)
    output_dir: Path = Path("tests/fixtures/medical_pile")
```

String shorthand: `"cbc_lab_report"` expands to `DocumentEntry(name="cbc_lab_report")` with all defaults.

## Artifact Layer

Artifacts are transforms applied to the sheet list after documents are generated but before the front/back split. They operate on physical sheets, not logical pages.

### Artifact Types

```python
class PileArtifact:
    """Base for all artifacts."""
    pass

@dataclass
class DuplicatePage(PileArtifact):
    """Same page scanned twice (ADF double-feed or manual re-scan)."""
    doc_index: int          # Which document (0-based index into PileConfig.documents)
    page: int               # Which page of that document (1-based)

@dataclass
class DuplicateDocument(PileArtifact):
    """Entire document appears twice in the pile."""
    doc_index: int          # Which document to duplicate
    insert_at: int | None = None  # Sheet position to insert copy, None = immediately after original

@dataclass
class ShufflePages(PileArtifact):
    """Pages within a document are out of order."""
    doc_index: int
    order: list[int]        # 1-based page numbers in desired (wrong) order

@dataclass
class InterleaveDocuments(PileArtifact):
    """Pages from two documents got mixed together.
    Pattern is a list of doc indices (0 or 1) indicating which doc's next page goes at each position.
    """
    doc_a_index: int
    doc_b_index: int
    pattern: list[int]      # e.g., [0, 0, 1, 0, 1] means: A1, A2, B1, A3, B2

@dataclass
class StrayDocument(PileArtifact):
    """A document that doesn't belong — junk mail, utility bill, etc."""
    document_name: str      # Key into REGISTRY (could be a non-medical doc type)
    position: int           # Sheet position to insert (0-based)
    config: Any = None

@dataclass
class WrongPatientDocument(PileArtifact):
    """Someone else's document mixed into this patient's pile."""
    document_name: str      # Key into REGISTRY
    patient: PatientContext  # The wrong patient
    position: int           # Sheet position to insert
    config: Any = None

@dataclass
class BlankSheetInserted(PileArtifact):
    """Random blank sheet in the pile."""
    position: int           # Sheet position

@dataclass
class RotatedPage(PileArtifact):
    """Page fed upside-down through the ADF (180 degree rotation)."""
    doc_index: int
    page: int               # 1-based
```

### Artifact Application Order

Artifacts are applied in this order:
1. **ShufflePages** — reorder pages within documents (before sheet assignment)
2. **InterleaveDocuments** — merge documents' pages (before sheet assignment)
3. **DuplicatePage** — insert duplicate sheets
4. **DuplicateDocument** — insert duplicate document sheets
5. **StrayDocument / WrongPatientDocument / BlankSheetInserted** — insert foreign sheets at positions
6. **RotatedPage** — rotate specific pages in the final sheet list

This order matters: shuffling and interleaving happen at the page level, then sheets are assigned, then positional inserts happen on the sheet list.

## Assembly Logic

`PileAssembler.generate(config: PileConfig) -> tuple[Path, Path]`:

1. **Render** — for each `DocumentEntry`, look up `REGISTRY[name]`, call `render(pdf, patient, config)`, get PDF bytes
2. **Sheet assignment** — for each document's pages, assign to physical sheets based on `single_sided` flag (same logic as current code)
3. **Apply artifacts** — transform the sheet list per artifact rules
4. **Split** — extract front pages in sheet order → `fronts.pdf`; extract back pages in reversed sheet order → `backs.pdf`
5. **Summary** — print sheet count, content/blank/near-blank back breakdown

Returns `(fronts_path, backs_path)`.

## Predefined Pile Recipes

In `generate_medical_pile.py`:

```python
from tests.medical_documents import generate_pile, PatientContext, PileConfig
from tests.medical_documents.assembler import (
    DuplicatePage, ShufflePages, WrongPatientDocument, BlankSheetInserted,
)

def standard_pile() -> PileConfig:
    """The original 11-document pile. Clean scan, no artifacts."""
    return PileConfig(
        patient=PatientContext(),
        documents=[
            "cbc_lab_report", "chest_xray", "discharge_summary",
            "diabetes_care_plan", "pathology_report", "medication_list",
            "insurance_eob", "referral_letter", "pt_progress_note",
            "immunization_record", "operative_report",
        ],
    )

def chaos_pile() -> PileConfig:
    """Realistic mess: duplicates, wrong order, wrong patient mixed in."""
    return PileConfig(
        patient=PatientContext(),
        documents=[
            "cbc_lab_report", "chest_xray", "discharge_summary",
            "diabetes_care_plan", "pathology_report", "medication_list",
            "insurance_eob", "referral_letter", "pt_progress_note",
            "immunization_record", "operative_report",
        ],
        artifacts=[
            DuplicatePage(doc_index=0, page=1),
            ShufflePages(doc_index=2, order=[1, 3, 2]),
            WrongPatientDocument(
                document_name="cbc_lab_report",
                patient=PatientContext(
                    name="Robert J. Thompson",
                    name_last_first="THOMPSON, ROBERT J",
                    dob="09/22/1945", age=80, gender="Male",
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

# CLI
if __name__ == "__main__":
    import sys
    recipes = {"standard": standard_pile, "chaos": chaos_pile, "minimal": minimal_pile}
    recipe = sys.argv[1] if len(sys.argv) > 1 else "standard"
    config = recipes[recipe]()
    generate_pile(config)
```

## Discoverability API

Claude Code (or any agent) needs to understand the framework without reading every source file. The package exposes introspection functions:

```python
from tests.medical_documents import list_documents, describe_document, list_artifacts

list_documents()
# Returns:
# [
#   {"name": "cbc_lab_report", "description": "CBC with Differential + CMP — Quest Diagnostics style",
#    "pages": 2, "single_sided": False, "config_fields": ["wbc", "glucose", "a1c", "date_collected", "ordering_md"]},
#   {"name": "chest_xray", "description": "Chest X-Ray radiology report — hospital style",
#    "pages": 1, "single_sided": True, "config_fields": []},
#   ...
# ]

describe_document("cbc_lab_report")
# Returns:
# {"name": "cbc_lab_report",
#  "description": "CBC with Differential + CMP — Quest Diagnostics style",
#  "pages": 2, "single_sided": False,
#  "config_cls": "CBCLabConfig",
#  "config_fields": {
#    "wbc": {"type": "float", "default": 11.2, "description": "White blood cell count"},
#    "glucose": {"type": "int", "default": 142, "description": "Fasting glucose mg/dL"},
#    ...
#  }}

list_artifacts()
# Returns:
# [
#   {"name": "DuplicatePage", "description": "Same page scanned twice", "fields": ["doc_index", "page"]},
#   {"name": "DuplicateDocument", "description": "Entire document appears twice", "fields": ["doc_index", "insert_at"]},
#   ...
# ]
```

Each `DocumentDef` includes a `description` field (one-line summary) for this purpose. Each doc-specific config dataclass uses `field(metadata={"description": "..."})` for field-level docs.

### Updated DocumentDef

```python
@dataclass
class DocumentDef:
    name: str
    description: str                                  # One-line summary for discoverability
    render: Callable[[FPDF, PatientContext, Any | None], None]
    default_config_cls: type | None = None
    single_sided: bool = False
    back_artifact: str = "blank"
```

### Updated Config Fields

```python
from dataclasses import dataclass, field

@dataclass
class CBCLabConfig:
    wbc: float = field(default=11.2, metadata={"description": "White blood cell count (x10E3/uL)"})
    glucose: int = field(default=142, metadata={"description": "Fasting glucose (mg/dL)"})
    a1c: float = field(default=7.2, metadata={"description": "Hemoglobin A1C (%)"})
    date_collected: str = field(default="03/15/2026", metadata={"description": "Specimen collection date"})
    ordering_md: str = field(default="Dr. Anish Patel, MD", metadata={"description": "Ordering physician"})
```

The `describe_document()` function reads these metadata annotations to produce the field descriptions.

## Output Manifest

`generate_pile()` writes a `manifest.json` alongside `fronts.pdf` and `backs.pdf`. This gives Claude Code (and tests) a machine-readable record of exactly what was generated.

```json
{
  "generated_at": "2026-03-30T14:22:00",
  "patient": {"name": "Elena R. Martinez", "dob": "04/12/1968", "mrn": "JHH-22847391"},
  "num_sheets": 13,
  "num_logical_pages": 19,
  "documents": [
    {
      "index": 0,
      "name": "cbc_lab_report",
      "patient": "Elena R. Martinez",
      "pages": 2,
      "single_sided": false,
      "sheets": [0],
      "front_pages": [0],
      "back_pages": [1]
    },
    {
      "index": 1,
      "name": "chest_xray",
      "patient": "Elena R. Martinez",
      "pages": 1,
      "single_sided": true,
      "sheets": [1],
      "front_pages": [1],
      "back_pages": []
    }
  ],
  "sheets": [
    {"index": 0, "front": {"doc": "cbc_lab_report", "page": 1}, "back": {"type": "content", "doc": "cbc_lab_report", "page": 2}},
    {"index": 1, "front": {"doc": "chest_xray", "page": 1}, "back": {"type": "blank"}},
    {"index": 2, "front": {"doc": "discharge_summary", "page": 1}, "back": {"type": "content", "doc": "discharge_summary", "page": 2}}
  ],
  "backs_order": [12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
  "artifacts_applied": [],
  "content_backs": 6,
  "blank_backs": 5,
  "near_blank_backs": 2
}
```

For piles with artifacts, `artifacts_applied` records what was done:

```json
"artifacts_applied": [
  {"type": "DuplicatePage", "doc_index": 0, "page": 1, "result": "Inserted duplicate of cbc_lab_report page 1 at sheet 1"},
  {"type": "ShufflePages", "doc_index": 2, "order": [1, 3, 2], "result": "Reordered discharge_summary pages to [1, 3, 2]"},
  {"type": "WrongPatientDocument", "document": "cbc_lab_report", "patient": "Robert J. Thompson", "position": 7}
]
```

This manifest enables Claude Code to:
- Verify the pile was generated correctly
- Reference specific pages/sheets by index in follow-up conversations
- Understand the ground truth for testing the AI splitter against

## Claude Code Integration

### Project Rule

Add `.claude/rules/medical-document-generator.md`:

```markdown
# Medical Document Generator

Test fixture framework at `tests/medical_documents/` for generating realistic
scanned medical document piles (fronts.pdf + backs.pdf).

## Quick Reference

```python
from tests.medical_documents import generate_pile, list_documents, describe_document, PatientContext, PileConfig
from tests.medical_documents.assembler import DuplicatePage, ShufflePages, WrongPatientDocument, BlankSheetInserted, DuplicateDocument, InterleaveDocuments, StrayDocument, RotatedPage

# List available document types
list_documents()

# Generate the standard 11-document pile
generate_pile(PileConfig(patient=PatientContext(), documents=["cbc_lab_report", "chest_xray", ...]))

# Generate with artifacts (scanning mistakes)
generate_pile(PileConfig(
    patient=PatientContext(name="Jane Doe", dob="05/20/1990"),
    documents=["cbc_lab_report", "discharge_summary"],
    artifacts=[DuplicatePage(doc_index=0, page=1)],
    output_dir=Path("tests/fixtures/my_test_pile"),
))
```

## Adding a New Document Type

1. Create `tests/medical_documents/documents/<name>.py`
2. Implement `render(pdf, patient, config)` function
3. Export `DOCUMENT = DocumentDef(name="<name>", description="...", render=render)`
4. Auto-registered — no other files to edit

## Running from CLI

```bash
python -m tests.generate_medical_pile                    # standard pile
python -m tests.generate_medical_pile chaos              # pile with scanning artifacts
python -m tests.generate_medical_pile minimal            # quick 3-doc pile
```

Output goes to `tests/fixtures/medical_pile/` (fronts.pdf, backs.pdf, manifest.json).
```

This rule ensures Claude Code knows the framework exists and can use it without being told.

## What Stays the Same

- **`tests/generate_fixtures.py`** — untouched, existing tests depend on it
- **`tests/conftest.py` fixtures** — unchanged, point at `tests/fixtures/`
- **All existing document content** — same text, formatting, fonts; just reorganized into separate files
- **`fpdf2` as dev dependency** — already installed
- **The 11 document generators** — same render logic, wrapped in the new structure

## What Changes

- **`tests/generate_medical_pile.py`** — becomes a thin CLI that imports from the package and calls recipes
- **Document generators** — extracted from the monolith into individual files under `documents/`
- **PDF helpers** — extracted to `helpers.py`
- **Assembly logic** — extracted to `assembler.py` with artifact support
- **`pyproject.toml`** — add `fpdf2` to dev dependencies

## Migration

The generated output files (`tests/fixtures/medical_pile/fronts.pdf` and `backs.pdf`) should be identical before and after refactoring when using the `standard_pile()` recipe. Verify by comparing page counts and text content.
