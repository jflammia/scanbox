"""Tests for AI document splitting — validation logic, not LLM calls."""

import pytest

from scanbox.models import SplitDocument
from scanbox.pipeline.splitter import SplitValidationError, build_prompt, validate_splits


class TestValidateSplits:
    def test_valid_contiguous_splits(self):
        splits = [
            {
                "start_page": 1,
                "end_page": 2,
                "document_type": "Radiology Report",
                "date_of_service": "2025-06-15",
                "facility": "Hospital",
                "provider": "Dr. X",
                "description": "CT scan",
                "confidence": 0.9,
            },
            {
                "start_page": 3,
                "end_page": 5,
                "document_type": "Lab Results",
                "date_of_service": "2025-05-22",
                "facility": "Quest",
                "provider": "unknown",
                "description": "Blood work",
                "confidence": 0.85,
            },
        ]
        result = validate_splits(splits, total_pages=5)
        assert len(result) == 2
        assert isinstance(result[0], SplitDocument)

    def test_gap_in_pages_raises(self):
        splits = [
            {
                "start_page": 1,
                "end_page": 2,
                "document_type": "Report",
                "date_of_service": "unknown",
                "facility": "unknown",
                "provider": "unknown",
                "description": "Doc",
                "confidence": 0.9,
            },
            {
                "start_page": 4,
                "end_page": 5,
                "document_type": "Report",
                "date_of_service": "unknown",
                "facility": "unknown",
                "provider": "unknown",
                "description": "Doc",
                "confidence": 0.9,
            },
        ]
        with pytest.raises(SplitValidationError, match="gap"):
            validate_splits(splits, total_pages=5)

    def test_overlap_raises(self):
        splits = [
            {
                "start_page": 1,
                "end_page": 3,
                "document_type": "Report",
                "date_of_service": "unknown",
                "facility": "unknown",
                "provider": "unknown",
                "description": "Doc",
                "confidence": 0.9,
            },
            {
                "start_page": 2,
                "end_page": 5,
                "document_type": "Report",
                "date_of_service": "unknown",
                "facility": "unknown",
                "provider": "unknown",
                "description": "Doc",
                "confidence": 0.9,
            },
        ]
        with pytest.raises(SplitValidationError, match="overlap"):
            validate_splits(splits, total_pages=5)

    def test_pages_not_covered_raises(self):
        splits = [
            {
                "start_page": 1,
                "end_page": 3,
                "document_type": "Report",
                "date_of_service": "unknown",
                "facility": "unknown",
                "provider": "unknown",
                "description": "Doc",
                "confidence": 0.9,
            },
        ]
        with pytest.raises(SplitValidationError, match="not covered"):
            validate_splits(splits, total_pages=5)

    def test_single_page_single_doc(self):
        splits = [
            {
                "start_page": 1,
                "end_page": 1,
                "document_type": "Letter",
                "date_of_service": "2025-01-01",
                "facility": "Clinic",
                "provider": "Dr. Y",
                "description": "Referral",
                "confidence": 0.95,
            },
        ]
        result = validate_splits(splits, total_pages=1)
        assert len(result) == 1
        assert result[0].start_page == 1

    def test_start_after_end_raises(self):
        splits = [
            {
                "start_page": 3,
                "end_page": 1,
                "document_type": "Report",
                "date_of_service": "unknown",
                "facility": "unknown",
                "provider": "unknown",
                "description": "Doc",
                "confidence": 0.9,
            },
        ]
        with pytest.raises(SplitValidationError, match="start_page.*end_page"):
            validate_splits(splits, total_pages=3)


class TestBuildPrompt:
    def test_prompt_includes_person_name(self):
        prompt = build_prompt(
            page_texts={1: "Some text", 2: "More text"},
            person_name="John Doe",
        )
        assert "John Doe" in prompt

    def test_prompt_includes_page_markers(self):
        prompt = build_prompt(
            page_texts={1: "Page one text", 2: "Page two text"},
            person_name="Test",
        )
        assert "---PAGE 1---" in prompt
        assert "---PAGE 2---" in prompt
