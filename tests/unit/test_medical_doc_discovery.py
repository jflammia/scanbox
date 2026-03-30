"""Tests for the discoverability API."""

from tests.medical_documents import describe_document, list_artifacts, list_documents


class TestListDocuments:
    def test_returns_list(self):
        result = list_documents()
        assert isinstance(result, list)
        assert len(result) == 11

    def test_entry_shape(self):
        result = list_documents()
        entry = result[0]
        assert "name" in entry
        assert "description" in entry
        assert "single_sided" in entry
        assert isinstance(entry["description"], str)


class TestDescribeDocument:
    def test_known_document(self):
        result = describe_document("cbc_lab_report")
        assert result["name"] == "cbc_lab_report"
        assert "config_fields" in result
        assert "wbc" in result["config_fields"]
        assert "description" in result["config_fields"]["wbc"]

    def test_unknown_document(self):
        result = describe_document("nonexistent")
        assert result is None

    def test_doc_without_config(self):
        result = describe_document("chest_xray")
        assert result is not None
        assert result["config_fields"] == {}


class TestListArtifacts:
    def test_returns_list(self):
        result = list_artifacts()
        assert isinstance(result, list)
        assert len(result) == 8

    def test_entry_shape(self):
        result = list_artifacts()
        entry = result[0]
        assert "name" in entry
        assert "description" in entry
        assert "fields" in entry
