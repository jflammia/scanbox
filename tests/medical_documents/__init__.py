"""Medical document generator framework for test fixture generation."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fpdf import FPDF


@dataclass
class PatientContext:
    """Patient identity shared across all documents in a pile."""

    name: str = "Elena R. Martinez"
    name_last_first: str = "MARTINEZ, ELENA R"
    dob: str = "04/12/1968"
    age: int = 57
    gender: str = "Female"
    mrn: str = "JHH-22847391"
    pcp: str = "Anish Patel, MD"
    insurance: str = "BlueCross PPO"


@dataclass
class DocumentDef:
    """Definition of a document type in the registry."""

    name: str
    description: str
    render: Callable[[FPDF, PatientContext, Any], None]
    default_config_cls: type | None = None
    single_sided: bool = False
    back_artifact: str = "blank"


@dataclass
class DocumentEntry:
    """One document in a pile configuration."""

    name: str
    config: Any = None
    patient: PatientContext | None = None
    single_sided: bool | None = None


@dataclass
class PileConfig:
    """Configuration for generating a pile of scanned documents."""

    patient: PatientContext
    documents: list[DocumentEntry | str]
    artifacts: list = field(default_factory=list)
    output_dir: Path = Path("tests/fixtures/medical_pile")


def generate_pile(config: PileConfig) -> tuple[Path, Path]:
    """Generate fronts.pdf and backs.pdf from a pile configuration."""
    from tests.medical_documents.assembler import PileAssembler

    assembler = PileAssembler()
    return assembler.generate(config)


def list_documents() -> list[dict]:
    """List all registered document types with metadata for discoverability."""
    from tests.medical_documents.documents import REGISTRY

    result = []
    for name, doc_def in sorted(REGISTRY.items()):
        config_fields = []
        if doc_def.default_config_cls:
            config_fields = [f.name for f in dataclasses.fields(doc_def.default_config_cls)]
        result.append(
            {
                "name": name,
                "description": doc_def.description,
                "single_sided": doc_def.single_sided,
                "config_fields": config_fields,
            }
        )
    return result


def describe_document(name: str) -> dict | None:
    """Describe a document type in detail, including config field metadata."""
    from tests.medical_documents.documents import REGISTRY

    doc_def = REGISTRY.get(name)
    if doc_def is None:
        return None

    config_fields = {}
    if doc_def.default_config_cls:
        for f in dataclasses.fields(doc_def.default_config_cls):
            field_info = {
                "type": f.type if isinstance(f.type, str) else f.type.__name__,
                "default": f.default if f.default is not dataclasses.MISSING else None,
            }
            if f.metadata and "description" in f.metadata:
                field_info["description"] = f.metadata["description"]
            config_fields[f.name] = field_info

    return {
        "name": doc_def.name,
        "description": doc_def.description,
        "single_sided": doc_def.single_sided,
        "back_artifact": doc_def.back_artifact,
        "config_cls": doc_def.default_config_cls.__name__ if doc_def.default_config_cls else None,
        "config_fields": config_fields,
    }


def list_artifacts() -> list[dict]:
    """List all available pile artifact types."""
    from tests.medical_documents import assembler

    result = []
    for name in dir(assembler):
        obj = getattr(assembler, name)
        if (
            isinstance(obj, type)
            and issubclass(obj, assembler.PileArtifact)
            and obj is not assembler.PileArtifact
        ):
            fields_list = (
                [f.name for f in dataclasses.fields(obj)] if dataclasses.is_dataclass(obj) else []
            )
            result.append(
                {
                    "name": name,
                    "description": obj.__doc__ or "",
                    "fields": fields_list,
                }
            )
    return sorted(result, key=lambda x: x["name"])
