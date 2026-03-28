"""Tests for medical document filename generation."""

from scanbox.pipeline.namer import generate_filename, sanitize_filename


class TestSanitizeFilename:
    def test_removes_special_chars(self):
        assert sanitize_filename("Dr. O'Brien & Associates") == "Dr-OBrien-Associates"

    def test_replaces_spaces_with_hyphens(self):
        assert sanitize_filename("CT Abdomen with Contrast") == "CT-Abdomen-with-Contrast"

    def test_truncates_long_names(self):
        long = "A" * 250
        result = sanitize_filename(long, max_length=100)
        assert len(result) <= 100

    def test_no_trailing_hyphens(self):
        assert sanitize_filename("test - ") == "test"


class TestGenerateFilename:
    def test_full_metadata(self):
        result = generate_filename(
            person_name="John Doe",
            document_type="Radiology Report",
            date_of_service="2025-06-15",
            facility="Memorial Hospital",
            description="CT Abdomen with Contrast",
        )
        assert (
            result
            == "2025-06-15_John-Doe_Radiology-Report_Memorial-Hospital_CT-Abdomen-with-Contrast.pdf"
        )

    def test_unknown_date(self):
        result = generate_filename(
            person_name="John Doe",
            document_type="Lab Results",
            date_of_service="unknown",
            facility="Quest Diagnostics",
            description="Blood Work",
        )
        assert result.startswith("Unknown-Date_")

    def test_unknown_facility(self):
        result = generate_filename(
            person_name="John Doe",
            document_type="Letter",
            date_of_service="2025-01-01",
            facility="unknown",
            description="Referral",
        )
        # Facility omitted, not "unknown" in filename
        assert "unknown" not in result.lower()
        assert "Letter" in result

    def test_duplicate_suffix(self):
        generate_filename(
            person_name="John Doe",
            document_type="Other",
            date_of_service="unknown",
            facility="unknown",
            description="Document",
        )
        suffixed = generate_filename(
            person_name="John Doe",
            document_type="Other",
            date_of_service="unknown",
            facility="unknown",
            description="Document",
            duplicate_index=2,
        )
        assert suffixed.endswith("-2.pdf")
