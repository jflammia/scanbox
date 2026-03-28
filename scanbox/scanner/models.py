"""Scanner data models."""

from dataclasses import dataclass, field


@dataclass
class ScannerCapabilities:
    make_and_model: str = ""
    has_adf: bool = False
    has_duplex_adf: bool = False
    supported_resolutions: list[int] = field(default_factory=list)
    supported_formats: list[str] = field(default_factory=list)
    max_width: int = 2550  # US Letter at 300 DPI
    max_height: int = 3300


@dataclass
class ScannerStatus:
    state: str = "Unknown"  # Idle, Processing, Testing, Stopped, Down
    adf_loaded: bool = False
    adf_state: str = ""
