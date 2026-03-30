"""Tests for pile assembly -- sheet building, front/back splitting, manifest."""

import json
from pathlib import Path

import pikepdf

from tests.medical_documents import DocumentEntry, PatientContext, PileConfig, generate_pile


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
        config = PileConfig(
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
        config = PileConfig(
            patient=PatientContext(),
            documents=[DocumentEntry(name="cbc_lab_report", single_sided=True)],
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
