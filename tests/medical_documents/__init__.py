"""Medical document generator framework for test fixture generation."""

from __future__ import annotations

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
