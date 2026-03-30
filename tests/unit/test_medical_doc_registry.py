"""Tests for the document auto-discovery registry."""

from tests.medical_documents import DocumentDef, PatientContext
from tests.medical_documents.documents import REGISTRY
from tests.medical_documents.helpers import new_pdf

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


class TestRegistry:
    def test_registry_is_dict(self):
        assert isinstance(REGISTRY, dict)

    def test_registry_values_are_document_defs(self):
        for name, doc_def in REGISTRY.items():
            assert isinstance(doc_def, DocumentDef)
            assert doc_def.name == name
            assert isinstance(doc_def.description, str)
            assert len(doc_def.description) > 0
            assert callable(doc_def.render)


class TestAllDocumentsRegistered:
    def test_all_expected_documents_present(self):
        for name in EXPECTED_DOCUMENTS:
            assert name in REGISTRY, f"Missing document: {name}"

    def test_no_unexpected_documents(self):
        for name in REGISTRY:
            assert name in EXPECTED_DOCUMENTS, f"Unexpected document: {name}"

    def test_count(self):
        assert len(REGISTRY) == 11


class TestDocumentRendering:
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
