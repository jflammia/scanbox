"""Shared Pydantic models used across pipeline, API, and database."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class BatchState(StrEnum):
    SCANNING_FRONTS = "scanning_fronts"
    FRONTS_DONE = "fronts_done"
    SCANNING_BACKS = "scanning_backs"
    BACKS_DONE = "backs_done"
    BACKS_SKIPPED = "backs_skipped"
    PROCESSING = "processing"
    REVIEW = "review"
    SAVED = "saved"
    ERROR = "error"


class ProcessingStage(StrEnum):
    INTERLEAVING = "interleaving"
    BLANK_REMOVAL = "blank_removal"
    OCR = "ocr"
    SPLITTING = "splitting"
    NAMING = "naming"
    DONE = "done"


class Person(BaseModel):
    id: str
    display_name: str
    slug: str
    folder_name: str
    created: datetime


class SplitDocument(BaseModel):
    start_page: int
    end_page: int
    document_type: str = "Other"
    date_of_service: str = "unknown"
    facility: str = "unknown"
    provider: str = "unknown"
    description: str = "Document"
    confidence: float = 1.0
    user_edited: bool = False
    filename: str = ""


class BatchInfo(BaseModel):
    id: str
    session_id: str
    state: BatchState
    processing_stage: ProcessingStage | None = None
    fronts_page_count: int = 0
    backs_page_count: int = 0
    documents: list[SplitDocument] = Field(default_factory=list)
    created: datetime
    error_message: str | None = None


DOCUMENT_TYPES = [
    "Radiology Report",
    "Discharge Summary",
    "Care Plan",
    "Lab Results",
    "Letter",
    "Operative Report",
    "Progress Note",
    "Pathology Report",
    "Prescription",
    "Insurance",
    "Billing",
    "Other",
]
