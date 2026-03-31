"""Generate comprehensive test pile suite for ScanBox pipeline testing.

Creates 13 piles covering every combination of document types, sidedness,
artifacts, and edge cases an end-user might feed through the scanner.

Usage:
    python -m tests.generate_test_suite          # generate all piles
    python -m tests.generate_test_suite verify    # verify all piles against manifests
"""

import sys
from pathlib import Path

from tests.medical_documents import (
    PatientContext,
    PileConfig,
    generate_pile,
)
from tests.medical_documents.assembler import (
    BlankSheetInserted,
    DuplicateDocument,
    DuplicatePage,
    InterleaveDocuments,
    RotatedPage,
    ShufflePages,
    WrongPatientDocument,
)

SUITE_DIR = Path("tests/fixtures/test_suite")

# -- Patients --

DEFAULT_PATIENT = PatientContext()

ALT_PATIENT = PatientContext(
    name="John A. Doe",
    name_last_first="DOE, JOHN A",
    dob="11/03/1982",
    age=43,
    gender="Male",
    mrn="MRN-5529184",
    pcp="Dr. Karen Liu, MD",
    insurance="Aetna HMO",
)

WRONG_PATIENT = PatientContext(
    name="Robert J. Thompson",
    name_last_first="THOMPSON, ROBERT J",
    dob="09/22/1945",
    age=80,
    gender="Male",
    mrn="QD-1192847",
    pcp="Dr. William Harris, MD",
    insurance="Medicare Part B",
)

# -- Document lists --

ALL_DOCS = [
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

SINGLE_SIDED_DOCS = [
    "chest_xray",
    "pathology_report",
    "medication_list",
    "referral_letter",
    "immunization_record",
]

DOUBLE_SIDED_DOCS = [
    "cbc_lab_report",
    "discharge_summary",
    "diabetes_care_plan",
    "insurance_eob",
    "pt_progress_note",
]

SINGLE_PAGE_DOCS = [
    "chest_xray",
    "pathology_report",
    "medication_list",
    "referral_letter",
    "immunization_record",
]


# -- Pile definitions --


def pile_01_standard_clean() -> PileConfig:
    """Baseline: all 11 documents, clean scan, no artifacts.
    Tests the happy path through the entire pipeline.
    """
    return PileConfig(
        patient=DEFAULT_PATIENT,
        documents=ALL_DOCS,
        output_dir=SUITE_DIR / "01-standard-clean",
    )


def pile_02_single_sided_only() -> PileConfig:
    """All single-sided documents. Every back page should be blank.
    Tests blank removal -- pipeline should remove all back pages.
    """
    return PileConfig(
        patient=DEFAULT_PATIENT,
        documents=SINGLE_SIDED_DOCS,
        output_dir=SUITE_DIR / "02-single-sided-only",
    )


def pile_03_double_sided_only() -> PileConfig:
    """All double-sided documents. No blank backs (except odd-page docs).
    Tests that content backs are preserved through interleaving.
    """
    return PileConfig(
        patient=DEFAULT_PATIENT,
        documents=DOUBLE_SIDED_DOCS,
        output_dir=SUITE_DIR / "03-double-sided-only",
    )


def pile_04_single_document() -> PileConfig:
    """Just one multi-page document (operative report, 3 pages).
    Edge case for the AI splitter -- nothing to split.
    """
    return PileConfig(
        patient=DEFAULT_PATIENT,
        documents=["operative_report"],
        output_dir=SUITE_DIR / "04-single-document",
    )


def pile_05_single_page_docs() -> PileConfig:
    """Five single-page documents. Every boundary is between sheets.
    Tests the splitter's ability to detect boundaries with minimal content per doc.
    """
    return PileConfig(
        patient=DEFAULT_PATIENT,
        documents=SINGLE_PAGE_DOCS,
        output_dir=SUITE_DIR / "05-single-page-docs",
    )


def pile_06_minimal_quick() -> PileConfig:
    """Three documents for fast iteration during development.
    One double-sided, one single-sided, one letter.
    """
    return PileConfig(
        patient=DEFAULT_PATIENT,
        documents=["cbc_lab_report", "chest_xray", "referral_letter"],
        output_dir=SUITE_DIR / "06-minimal-quick",
    )


def pile_07_duplicate_pages() -> PileConfig:
    """Duplicate pages from ADF double-feed.
    Page 1 of the CBC scanned twice, page 1 of the discharge scanned twice.
    Splitter must handle seeing the same content repeated.
    """
    return PileConfig(
        patient=DEFAULT_PATIENT,
        documents=ALL_DOCS,
        artifacts=[
            DuplicatePage(doc_index=0, page=1),  # CBC page 1 duplicated
            DuplicatePage(doc_index=2, page=1),  # Discharge page 1 duplicated
        ],
        output_dir=SUITE_DIR / "07-duplicate-pages",
    )


def pile_08_shuffled_pages() -> PileConfig:
    """Pages within documents are out of order.
    Discharge summary pages fed as [3, 1, 2] and operative report as [2, 3, 1].
    Tests splitter's handling of non-sequential page content.
    """
    return PileConfig(
        patient=DEFAULT_PATIENT,
        documents=ALL_DOCS,
        artifacts=[
            ShufflePages(doc_index=2, order=[3, 1, 2]),  # Discharge: p3, p1, p2
            ShufflePages(doc_index=10, order=[2, 3, 1]),  # Op report: p2, p3, p1
        ],
        output_dir=SUITE_DIR / "08-shuffled-pages",
    )


def pile_09_wrong_patient() -> PileConfig:
    """Another patient's CBC lab report mixed into the pile.
    Inserted between the pathology report and medication list.
    Tests splitter's ability to detect patient identity changes.
    """
    return PileConfig(
        patient=DEFAULT_PATIENT,
        documents=ALL_DOCS,
        artifacts=[
            WrongPatientDocument(
                document_name="cbc_lab_report",
                patient=WRONG_PATIENT,
                position=6,  # after pathology (index 5), before medication (index 6)
            ),
        ],
        output_dir=SUITE_DIR / "09-wrong-patient",
    )


def pile_10_blank_sheets_mixed() -> PileConfig:
    """Random blank sheets mixed into the pile.
    Three blanks inserted at positions 0 (before first doc), 5 (middle), 11 (near end).
    Tests blank detection removes these without disrupting document boundaries.
    """
    return PileConfig(
        patient=DEFAULT_PATIENT,
        documents=ALL_DOCS,
        artifacts=[
            BlankSheetInserted(position=0),
            BlankSheetInserted(position=6),
            BlankSheetInserted(position=12),
        ],
        output_dir=SUITE_DIR / "10-blank-sheets-mixed",
    )


def pile_11_different_patient() -> PileConfig:
    """Same 11 documents but for a completely different patient (John Doe).
    Verifies patient parameterization works end-to-end and produces
    coherent documents with the alternate identity.
    """
    return PileConfig(
        patient=ALT_PATIENT,
        documents=ALL_DOCS,
        output_dir=SUITE_DIR / "11-different-patient",
    )


def pile_12_chaos_kitchen_sink() -> PileConfig:
    """Everything wrong at once: duplicated page, duplicated document,
    shuffled pages, wrong patient doc, blank sheets, rotated page.
    The worst-case scenario for the pipeline.
    """
    return PileConfig(
        patient=DEFAULT_PATIENT,
        documents=ALL_DOCS,
        artifacts=[
            DuplicatePage(doc_index=0, page=1),  # CBC page 1 scanned twice
            DuplicateDocument(doc_index=4),  # Pathology report scanned twice
            ShufflePages(doc_index=2, order=[1, 3, 2]),  # Discharge pages misordered
            WrongPatientDocument(
                document_name="insurance_eob",
                patient=WRONG_PATIENT,
                position=7,
            ),
            BlankSheetInserted(position=3),  # Random blank
            BlankSheetInserted(position=10),  # Another blank
            RotatedPage(doc_index=7, page=1),  # Referral letter upside-down
        ],
        output_dir=SUITE_DIR / "12-chaos-kitchen-sink",
    )


def pile_13_large_stress_test() -> PileConfig:
    """All 11 documents repeated twice (22 documents, ~26 sheets).
    Volume/stress test for the pipeline.
    """
    return PileConfig(
        patient=DEFAULT_PATIENT,
        documents=ALL_DOCS + ALL_DOCS,
        output_dir=SUITE_DIR / "13-large-stress-test",
    )


def pile_14_interleaved_docs() -> PileConfig:
    """Two documents with interleaved pages (papers got shuffled together).
    Tests that pages from two documents get mixed together correctly.
    """
    return PileConfig(
        patient=DEFAULT_PATIENT,
        documents=["cbc_lab_report", "discharge_summary"],
        artifacts=[
            InterleaveDocuments(doc_a_index=0, doc_b_index=1, pattern=[0, 1, 0, 1, 0]),
        ],
        output_dir=SUITE_DIR / "14-interleaved-docs",
    )


# -- Registry --

PILES = {
    "01-standard-clean": pile_01_standard_clean,
    "02-single-sided-only": pile_02_single_sided_only,
    "03-double-sided-only": pile_03_double_sided_only,
    "04-single-document": pile_04_single_document,
    "05-single-page-docs": pile_05_single_page_docs,
    "06-minimal-quick": pile_06_minimal_quick,
    "07-duplicate-pages": pile_07_duplicate_pages,
    "08-shuffled-pages": pile_08_shuffled_pages,
    "09-wrong-patient": pile_09_wrong_patient,
    "10-blank-sheets-mixed": pile_10_blank_sheets_mixed,
    "11-different-patient": pile_11_different_patient,
    "12-chaos-kitchen-sink": pile_12_chaos_kitchen_sink,
    "13-large-stress-test": pile_13_large_stress_test,
    "14-interleaved-docs": pile_14_interleaved_docs,
}


def generate_all() -> None:
    """Generate all 13 test piles."""
    print(f"Generating {len(PILES)} test piles into {SUITE_DIR}/\n")

    for name, pile_func in PILES.items():
        config = pile_func()
        print(f"--- {name} ---")
        print(f"  {pile_func.__doc__.strip().splitlines()[0]}")
        fronts, backs = generate_pile(config)
        print(f"  Output: {fronts.parent}/")
        print()

    print(f"Done. {len(PILES)} piles generated.")


def verify_all() -> None:
    """Verify all piles against their manifests."""
    import json

    print(f"Verifying {len(PILES)} test piles...\n")
    failures = []

    for name in PILES:
        pile_dir = SUITE_DIR / name
        fronts_path = pile_dir / "fronts.pdf"
        backs_path = pile_dir / "backs.pdf"
        manifest_path = pile_dir / "manifest.json"

        if not manifest_path.exists():
            failures.append((name, "manifest.json missing"))
            continue
        if not fronts_path.exists():
            failures.append((name, "fronts.pdf missing"))
            continue
        if not backs_path.exists():
            failures.append((name, "backs.pdf missing"))
            continue

        manifest = json.loads(manifest_path.read_text())

        import pikepdf

        fronts_pdf = pikepdf.Pdf.open(fronts_path)
        backs_pdf = pikepdf.Pdf.open(backs_path)

        errors = []

        # Check page counts match manifest
        num_sheets = manifest["num_sheets"]
        if len(fronts_pdf.pages) != num_sheets:
            errors.append(
                f"fronts has {len(fronts_pdf.pages)} pages, manifest says {num_sheets} sheets"
            )
        if len(backs_pdf.pages) != num_sheets:
            errors.append(
                f"backs has {len(backs_pdf.pages)} pages, manifest says {num_sheets} sheets"
            )

        # Check sheet count matches sheets list
        if len(manifest["sheets"]) != num_sheets:
            errors.append(
                f"manifest sheets list has {len(manifest['sheets'])} entries, "
                f"but num_sheets is {num_sheets}"
            )

        # Check document count
        num_docs = len(manifest["documents"])
        expected_docs = len(PILES[name]().documents)
        # Don't count artifact-inserted docs in expected count
        if num_docs < expected_docs:
            errors.append(f"manifest has {num_docs} documents, expected at least {expected_docs}")

        # Check backs_order indicates reversed
        backs_order = manifest["backs_order"]
        expected_list = list(range(num_sheets - 1, -1, -1))
        if backs_order != "reversed" and backs_order != expected_list:
            errors.append(f"backs_order is '{backs_order}', expected 'reversed' or {expected_list}")

        # Check fronts == backs page count
        if len(fronts_pdf.pages) != len(backs_pdf.pages):
            errors.append(
                f"fronts ({len(fronts_pdf.pages)} pages) != backs ({len(backs_pdf.pages)} pages)"
            )

        # Check each sheet has valid front doc reference
        for i, sheet in enumerate(manifest["sheets"]):
            if "front" not in sheet or "doc" not in sheet["front"]:
                errors.append(f"sheet {i} missing front.doc")
            if "back" not in sheet or "type" not in sheet["back"]:
                errors.append(f"sheet {i} missing back.type")

        # Check back types are valid
        valid_back_types = {"content", "blank", "near_blank_smudge", "near_blank_footer"}
        for i, sheet in enumerate(manifest["sheets"]):
            bt = sheet["back"]["type"]
            if bt not in valid_back_types:
                errors.append(f"sheet {i} has invalid back type: {bt}")

        # Check artifact count matches config
        config = PILES[name]()
        expected_artifacts = len(config.artifacts)
        actual_artifacts = len(manifest.get("artifacts_applied", []))
        if actual_artifacts != expected_artifacts:
            errors.append(
                f"manifest has {actual_artifacts} artifacts, expected {expected_artifacts}"
            )

        # Check all pages are US Letter size (612x792 pts, +/- 1 for rounding)
        for page_idx, page in enumerate(fronts_pdf.pages):
            box = page.mediabox
            w = float(box[2]) - float(box[0])
            h = float(box[3]) - float(box[1])
            if abs(w - 612) > 2 or abs(h - 792) > 2:
                errors.append(
                    f"fronts page {page_idx + 1} is {w:.0f}x{h:.0f} pts, "
                    f"expected 612x792 (US Letter)"
                )

        if errors:
            for e in errors:
                failures.append((name, e))
            print(f"  FAIL  {name}")
            for e in errors:
                print(f"        {e}")
        else:
            print(
                f"  OK    {name}: {num_sheets} sheets, "
                f"{num_docs} docs, "
                f"{actual_artifacts} artifacts"
            )

    print()
    if failures:
        print(f"FAILED: {len(failures)} issues in {len({f[0] for f in failures})} piles")
        for name, err in failures:
            print(f"  {name}: {err}")
        sys.exit(1)
    else:
        print(f"ALL {len(PILES)} PILES VERIFIED OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        verify_all()
    else:
        generate_all()
