"""Tests for page and document exclusion."""

from scanbox.pipeline.state import PipelineState


class TestPageExclusion:
    def test_exclude_page(self):
        state = PipelineState.new()
        state.exclude_page(3)
        assert 3 in state.excluded_pages

    def test_exclude_page_sorted(self):
        state = PipelineState.new()
        state.exclude_page(5)
        state.exclude_page(2)
        assert state.excluded_pages == [2, 5]

    def test_exclude_page_idempotent(self):
        state = PipelineState.new()
        state.exclude_page(3)
        state.exclude_page(3)
        assert state.excluded_pages == [3]

    def test_include_page(self):
        state = PipelineState.new()
        state.exclude_page(3)
        state.include_page(3)
        assert state.excluded_pages == []

    def test_include_page_not_excluded(self):
        state = PipelineState.new()
        state.include_page(3)  # no-op, doesn't raise
        assert state.excluded_pages == []


class TestDocumentExclusion:
    def test_exclude_document(self):
        state = PipelineState.new()
        state.exclude_document(0)
        assert 0 in state.excluded_documents

    def test_exclude_document_sorted(self):
        state = PipelineState.new()
        state.exclude_document(2)
        state.exclude_document(0)
        assert state.excluded_documents == [0, 2]

    def test_exclude_document_idempotent(self):
        state = PipelineState.new()
        state.exclude_document(1)
        state.exclude_document(1)
        assert state.excluded_documents == [1]

    def test_include_document(self):
        state = PipelineState.new()
        state.exclude_document(1)
        state.include_document(1)
        assert state.excluded_documents == []

    def test_include_document_not_excluded(self):
        state = PipelineState.new()
        state.include_document(1)  # no-op, doesn't raise
        assert state.excluded_documents == []


class TestExclusionPersistence:
    def test_roundtrip(self, tmp_path):
        state = PipelineState.new()
        state.exclude_page(3)
        state.exclude_page(7)
        state.exclude_document(1)
        state.save(tmp_path / "state.json")

        loaded = PipelineState.load(tmp_path / "state.json")
        assert loaded.excluded_pages == [3, 7]
        assert loaded.excluded_documents == [1]

    def test_load_without_exclusion_fields(self, tmp_path):
        """Loading state.json from before exclusions were added should default to empty lists."""
        import json

        data = {
            "stages": {},
            "dlq": [],
            "config": {"auto_advance_on_error": False, "confidence_threshold": 0.7},
        }
        path = tmp_path / "state.json"
        path.write_text(json.dumps(data))
        loaded = PipelineState.load(path)
        assert loaded.excluded_pages == []
        assert loaded.excluded_documents == []

    def test_new_state_has_empty_exclusions(self):
        state = PipelineState.new()
        assert state.excluded_pages == []
        assert state.excluded_documents == []
