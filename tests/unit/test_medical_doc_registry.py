"""Tests for the document auto-discovery registry."""

from tests.medical_documents import DocumentDef
from tests.medical_documents.documents import REGISTRY


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
