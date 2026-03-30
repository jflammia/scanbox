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
