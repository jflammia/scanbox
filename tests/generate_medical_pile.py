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
