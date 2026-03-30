"""Document registry -- auto-discovers all document modules in this directory."""

import importlib
import pkgutil

from tests.medical_documents import DocumentDef

REGISTRY: dict[str, DocumentDef] = {}


def _discover_documents() -> None:
    """Import all sibling modules and register their DOCUMENT exports."""
    package_path = __path__
    for _importer, module_name, _is_pkg in pkgutil.iter_modules(package_path):
        if module_name.startswith("_"):
            continue
        module = importlib.import_module(f".{module_name}", package=__name__)
        doc_def = getattr(module, "DOCUMENT", None)
        if isinstance(doc_def, DocumentDef):
            REGISTRY[doc_def.name] = doc_def


_discover_documents()
