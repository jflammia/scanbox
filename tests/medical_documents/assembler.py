"""Pile assembly: sheet building, artifact application, front/back splitting."""

from __future__ import annotations

from dataclasses import dataclass

from tests.medical_documents import PatientContext


class PileArtifact:
    """Base for all pile artifacts (scanning mistakes / organizational chaos)."""

    pass


@dataclass
class DuplicatePage(PileArtifact):
    """Same page scanned twice (ADF double-feed or manual re-scan)."""

    doc_index: int
    page: int  # 1-based


@dataclass
class DuplicateDocument(PileArtifact):
    """Entire document appears twice in the pile."""

    doc_index: int
    insert_at: int | None = None


@dataclass
class ShufflePages(PileArtifact):
    """Pages within a document are out of order."""

    doc_index: int
    order: list[int]  # 1-based page numbers


@dataclass
class InterleaveDocuments(PileArtifact):
    """Pages from two documents got mixed together."""

    doc_a_index: int
    doc_b_index: int
    pattern: list[int]  # 0 = next page from doc_a, 1 = next page from doc_b


@dataclass
class StrayDocument(PileArtifact):
    """A document that doesn't belong in the pile."""

    document_name: str
    position: int
    config: object = None


@dataclass
class WrongPatientDocument(PileArtifact):
    """Someone else's document mixed into this patient's pile."""

    document_name: str
    patient: PatientContext
    position: int
    config: object = None


@dataclass
class BlankSheetInserted(PileArtifact):
    """Random blank sheet in the pile."""

    position: int


@dataclass
class RotatedPage(PileArtifact):
    """Page fed upside-down through the ADF (180 degree rotation)."""

    doc_index: int
    page: int  # 1-based
