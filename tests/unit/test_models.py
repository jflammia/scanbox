"""Tests for scanbox.models — Pydantic models and enums."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from scanbox.models import (
    DOCUMENT_TYPES,
    BatchInfo,
    BatchState,
    Person,
    ProcessingStage,
    SplitDocument,
)


class TestBatchState:
    """Batch state machine values."""

    def test_all_states_defined(self):
        expected = {
            "scanning_fronts",
            "fronts_done",
            "scanning_backs",
            "backs_done",
            "backs_skipped",
            "processing",
            "review",
            "saved",
            "error",
        }
        assert {s.value for s in BatchState} == expected

    def test_state_is_string(self):
        assert BatchState.SCANNING_FRONTS == "scanning_fronts"
        assert isinstance(BatchState.REVIEW, str)


class TestProcessingStage:
    """Pipeline processing stages."""

    def test_all_stages_defined(self):
        expected = {
            "interleaving",
            "blank_removal",
            "ocr",
            "splitting",
            "naming",
            "done",
        }
        assert {s.value for s in ProcessingStage} == expected

    def test_stage_ordering_is_logical(self):
        stages = list(ProcessingStage)
        stage_names = [s.value for s in stages]
        assert stage_names.index("interleaving") < stage_names.index("blank_removal")
        assert stage_names.index("blank_removal") < stage_names.index("ocr")
        assert stage_names.index("ocr") < stage_names.index("splitting")
        assert stage_names.index("splitting") < stage_names.index("naming")
        assert stage_names.index("naming") < stage_names.index("done")


class TestPerson:
    """Person model for patient/person profiles."""

    def test_create_person(self):
        p = Person(
            id="p1",
            display_name="Jane Doe",
            slug="jane-doe",
            folder_name="Doe, Jane",
            created=datetime(2026, 3, 28, 12, 0, 0),
        )
        assert p.display_name == "Jane Doe"
        assert p.slug == "jane-doe"
        assert p.folder_name == "Doe, Jane"

    def test_person_requires_all_fields(self):
        with pytest.raises(ValidationError):
            Person(id="p1", display_name="Jane")  # missing slug, folder_name, created


class TestSplitDocument:
    """SplitDocument model for AI-detected document boundaries."""

    def test_minimal_split_document(self):
        doc = SplitDocument(start_page=1, end_page=3)
        assert doc.start_page == 1
        assert doc.end_page == 3
        assert doc.document_type == "Other"
        assert doc.date_of_service == "unknown"
        assert doc.facility == "unknown"
        assert doc.provider == "unknown"
        assert doc.description == "Document"
        assert doc.confidence == 1.0
        assert doc.user_edited is False

    def test_fully_populated_split_document(self):
        doc = SplitDocument(
            start_page=1,
            end_page=5,
            document_type="Lab Results",
            date_of_service="2026-01-15",
            facility="Mayo Clinic",
            provider="Dr. Smith",
            description="CBC and metabolic panel",
            confidence=0.92,
            user_edited=True,
        )
        assert doc.document_type == "Lab Results"
        assert doc.date_of_service == "2026-01-15"
        assert doc.facility == "Mayo Clinic"
        assert doc.confidence == 0.92
        assert doc.user_edited is True

    def test_split_document_requires_page_range(self):
        with pytest.raises(ValidationError):
            SplitDocument()  # missing start_page and end_page

    def test_split_document_serialization_roundtrip(self):
        doc = SplitDocument(start_page=1, end_page=3, document_type="Letter")
        data = doc.model_dump()
        restored = SplitDocument(**data)
        assert restored == doc


class TestBatchInfo:
    """BatchInfo model for batch status tracking."""

    def test_minimal_batch(self):
        batch = BatchInfo(
            id="b1",
            session_id="s1",
            state=BatchState.SCANNING_FRONTS,
            created=datetime(2026, 3, 28, 12, 0, 0),
        )
        assert batch.state == BatchState.SCANNING_FRONTS
        assert batch.processing_stage is None
        assert batch.fronts_page_count == 0
        assert batch.backs_page_count == 0
        assert batch.documents == []
        assert batch.error_message is None

    def test_batch_with_documents(self):
        docs = [
            SplitDocument(start_page=1, end_page=3),
            SplitDocument(start_page=4, end_page=7),
        ]
        batch = BatchInfo(
            id="b2",
            session_id="s1",
            state=BatchState.REVIEW,
            processing_stage=ProcessingStage.DONE,
            fronts_page_count=7,
            backs_page_count=7,
            documents=docs,
            created=datetime(2026, 3, 28, 12, 0, 0),
        )
        assert len(batch.documents) == 2
        assert batch.documents[0].end_page == 3

    def test_batch_error_state(self):
        batch = BatchInfo(
            id="b3",
            session_id="s1",
            state=BatchState.ERROR,
            error_message="Scanner disconnected during scan",
            created=datetime(2026, 3, 28, 12, 0, 0),
        )
        assert batch.state == BatchState.ERROR
        assert "Scanner disconnected" in batch.error_message

    def test_batch_serialization_roundtrip(self):
        batch = BatchInfo(
            id="b4",
            session_id="s1",
            state=BatchState.PROCESSING,
            processing_stage=ProcessingStage.OCR,
            fronts_page_count=10,
            created=datetime(2026, 3, 28, 12, 0, 0),
        )
        data = batch.model_dump()
        restored = BatchInfo(**data)
        assert restored == batch


class TestDocumentTypes:
    """The DOCUMENT_TYPES constant should cover expected medical record types."""

    def test_document_types_is_nonempty_list(self):
        assert isinstance(DOCUMENT_TYPES, list)
        assert len(DOCUMENT_TYPES) > 0

    def test_other_is_included(self):
        assert "Other" in DOCUMENT_TYPES

    def test_common_medical_types_present(self):
        for doc_type in ["Lab Results", "Discharge Summary", "Radiology Report", "Progress Note"]:
            assert doc_type in DOCUMENT_TYPES, f"Missing expected type: {doc_type}"

    def test_no_duplicates(self):
        assert len(DOCUMENT_TYPES) == len(set(DOCUMENT_TYPES))
