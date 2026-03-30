---
name: test-pdfs
description: Generate, regenerate, list, or verify medical document test PDFs. Use when the user says "generate test PDFs", "create a test pile", "regenerate the test suite", "make me a test pile with...", "what test piles do we have", or "verify test fixtures". Supports custom pile composition with specific documents, patients, and scanning artifacts.
---

# /test-pdfs — Medical Document Test Fixture Manager

Manage test PDF fixtures for the ScanBox pipeline. This command generates realistic
scanned medical document piles (fronts.pdf + backs.pdf + manifest.json).

## Determine Intent

Parse the user's request to determine which operation:

| User says | Operation |
|-----------|-----------|
| `/test-pdfs` (no args) | **List** available documents, artifacts, and existing piles |
| `/test-pdfs generate ...` | **Generate** a new custom pile from a description |
| `/test-pdfs regenerate` | **Regenerate** all 13 standard test suite piles |
| `/test-pdfs verify` | **Verify** all existing piles against their manifests |
| Natural language about creating test documents | **Generate** — interpret the request |

## Operation: List

Run this Python snippet to show the user what's available:

```python
.venv/bin/python -c "
from tests.medical_documents import list_documents, list_artifacts
import json
from pathlib import Path

print('=== Available Documents ===')
for d in list_documents():
    sided = 'single-sided' if d['single_sided'] else 'double-sided'
    config = f'  config: {d[\"config_fields\"]}' if d['config_fields'] else ''
    print(f'  {d[\"name\"]:30s} {sided:15s} {d[\"description\"]}{config}')

print()
print('=== Available Artifacts ===')
for a in list_artifacts():
    print(f'  {a[\"name\"]:30s} fields={a[\"fields\"]}')
    print(f'    {a[\"description\"].strip().splitlines()[0]}')

print()
print('=== Existing Test Piles ===')
suite_dir = Path('tests/fixtures/test_suite')
if suite_dir.exists():
    for d in sorted(suite_dir.iterdir()):
        if d.is_dir():
            manifest = d / 'manifest.json'
            if manifest.exists():
                m = json.loads(manifest.read_text())
                print(f'  {d.name:35s} {m[\"num_sheets\"]:2d} sheets, {len(m[\"documents\"]):2d} docs, {len(m.get(\"artifacts_applied\", [])):d} artifacts')
            else:
                print(f'  {d.name:35s} (no manifest)')
"
```

## Operation: Generate

When the user describes a pile they want, translate their description into a
`PileConfig` and generate it. Follow this process:

### Step 1: Translate the request

Map the user's natural language to framework concepts:

- "lab results" → `"cbc_lab_report"`
- "x-ray" / "radiology" → `"chest_xray"`
- "discharge papers" → `"discharge_summary"`
- "care plan" / "diabetes plan" → `"diabetes_care_plan"`
- "pathology" / "biopsy" → `"pathology_report"`
- "medication list" / "pharmacy" → `"medication_list"`
- "insurance" / "EOB" / "explanation of benefits" → `"insurance_eob"`
- "referral" / "referral letter" → `"referral_letter"`
- "physical therapy" / "PT notes" → `"pt_progress_note"`
- "immunizations" / "vaccines" → `"immunization_record"`
- "surgery" / "operative report" → `"operative_report"`
- "duplicate page" → `DuplicatePage(doc_index=N, page=N)`
- "duplicate document" / "scanned twice" → `DuplicateDocument(doc_index=N)`
- "pages out of order" / "shuffled" → `ShufflePages(doc_index=N, order=[...])`
- "wrong patient" / "someone else's document" → `WrongPatientDocument(...)`
- "blank sheet" / "extra blank" → `BlankSheetInserted(position=N)`
- "upside down" / "rotated" → `RotatedPage(doc_index=N, page=N)`

### Step 2: Choose an output directory

Place the pile in `tests/fixtures/test_suite/` with a descriptive name:

- Use kebab-case: `custom-lab-only`, `stress-50-docs`, `all-single-sided`
- Prefix with a number if adding to the numbered sequence: `14-custom-name`
- For one-off tests, use `tests/fixtures/custom/<name>/`

### Step 3: Write and execute the generation code

```python
from pathlib import Path
from tests.medical_documents import generate_pile, PatientContext, PileConfig, DocumentEntry
from tests.medical_documents.assembler import (
    DuplicatePage, DuplicateDocument, ShufflePages, InterleaveDocuments,
    StrayDocument, WrongPatientDocument, BlankSheetInserted, RotatedPage,
)

config = PileConfig(
    patient=PatientContext(...),  # customize or use defaults
    documents=[...],              # list of doc names or DocumentEntry objects
    artifacts=[...],              # list of artifact objects (optional)
    output_dir=Path("tests/fixtures/test_suite/<pile-name>"),
)
fronts, backs = generate_pile(config)
```

### Step 4: Verify the output

After generating, verify the pile:

```python
import json, pikepdf
fronts_pdf = pikepdf.Pdf.open(fronts)
backs_pdf = pikepdf.Pdf.open(backs)
manifest = json.loads((config.output_dir / "manifest.json").read_text())
print(f"Fronts: {len(fronts_pdf.pages)} pages")
print(f"Backs: {len(backs_pdf.pages)} pages")
print(f"Sheets: {manifest['num_sheets']}, Documents: {len(manifest['documents'])}")
print(f"Artifacts applied: {len(manifest.get('artifacts_applied', []))}")
assert len(fronts_pdf.pages) == manifest["num_sheets"]
assert len(backs_pdf.pages) == manifest["num_sheets"]
print("Verified OK")
```

### Step 5: Offer to commit

If the pile should be reusable, offer to commit it to the test suite.
Use `git add -f` for PDFs (they're gitignored but negated for `tests/fixtures/`).

## Operation: Regenerate

Regenerate all 13 standard piles and verify them:

```bash
.venv/bin/python -m tests.generate_test_suite
.venv/bin/python -m tests.generate_test_suite verify
```

Report results. If the user asked to regenerate a specific pile, run only that one
by calling `generate_pile()` with the matching config from `tests/generate_test_suite.py`.

## Operation: Verify

Run verification on all existing piles:

```bash
.venv/bin/python -m tests.generate_test_suite verify
```

Report results. If any fail, diagnose and offer to regenerate.

## Adding New Document Types

When the user asks to add a new document type (not just a pile):

1. Create `tests/medical_documents/documents/<name>.py`
2. Follow the pattern in any existing document module (read one first for reference)
3. Define `render(pdf, patient, config)` using helpers from `tests.medical_documents.helpers`
4. Export `DOCUMENT = DocumentDef(name="<name>", description="...", render=render)`
5. The registry auto-discovers it — no other files to edit
6. Generate a test pile using the new document to verify it renders correctly
