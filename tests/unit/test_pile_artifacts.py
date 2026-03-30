"""Tests for pile artifact application."""

import json
from pathlib import Path

import pikepdf

from tests.medical_documents import PatientContext, PileConfig, generate_pile
from tests.medical_documents.assembler import (
    BlankSheetInserted,
    DuplicateDocument,
    DuplicatePage,
    RotatedPage,
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
            documents=["discharge_summary"],
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
        # referral_letter = 1 sheet, cbc_lab_report = 1 sheet (2 pages double-sided)
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


class TestRotatedPage:
    def test_rotates_page(self, tmp_path: Path):
        config = PileConfig(
            patient=PatientContext(),
            documents=["referral_letter"],
            artifacts=[RotatedPage(doc_index=0, page=1)],
            output_dir=tmp_path,
        )
        generate_pile(config)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert len(manifest["artifacts_applied"]) == 1
        assert manifest["artifacts_applied"][0]["type"] == "RotatedPage"
