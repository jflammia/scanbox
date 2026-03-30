"""Tests for medical document generator core types."""


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
            WrongPatientDocument(document_name="test", patient=PatientContext(), position=0),
            BlankSheetInserted(position=0),
            RotatedPage(doc_index=0, page=1),
        ]
        for a in artifacts:
            assert isinstance(a, PileArtifact)
