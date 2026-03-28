"""Configuration loaded from environment variables with sensible defaults."""

import os
from pathlib import Path


class Config:
    """Reads environment variables at instantiation time, not import time."""

    def __init__(self) -> None:
        # Scanner
        self.SCANNER_IP: str = os.getenv("SCANNER_IP", "")

        # LLM
        self.LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")
        self.LLM_MODEL: str = os.getenv("LLM_MODEL", "")
        self.ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
        self.OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")

        # PaperlessNGX (optional)
        self.PAPERLESS_URL: str = os.getenv("PAPERLESS_URL", "")
        self.PAPERLESS_API_TOKEN: str = os.getenv("PAPERLESS_API_TOKEN", "")

        # Storage
        self.INTERNAL_DATA_DIR: Path = Path(os.getenv("INTERNAL_DATA_DIR", "/app/data"))
        self.OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", "/output"))

        # Pipeline
        self.BLANK_PAGE_THRESHOLD: float = float(os.getenv("BLANK_PAGE_THRESHOLD", "0.01"))
        self.OCR_LANGUAGE: str = os.getenv("OCR_LANGUAGE", "eng")
        self.DEFAULT_DPI: int = int(os.getenv("DEFAULT_DPI", "300"))

        # API authentication (optional — off by default for local use)
        self.SCANBOX_API_KEY: str = os.getenv("SCANBOX_API_KEY", "")

        # MCP server (opt-in)
        self.MCP_ENABLED: bool = os.getenv("MCP_ENABLED", "").lower() in ("true", "1", "yes")

        # Webhooks (optional)
        self.WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
        self.WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")

    @property
    def sessions_dir(self) -> Path:
        return self.INTERNAL_DATA_DIR / "sessions"

    @property
    def config_dir(self) -> Path:
        return self.INTERNAL_DATA_DIR / "config"

    @property
    def db_path(self) -> Path:
        return self.INTERNAL_DATA_DIR / "scanbox.db"

    @property
    def archive_dir(self) -> Path:
        return self.OUTPUT_DIR / "archive"

    @property
    def medical_records_dir(self) -> Path:
        return self.OUTPUT_DIR / "medical-records"

    def llm_model_id(self) -> str:
        """Return the litellm model identifier based on provider + model."""
        if self.LLM_MODEL:
            return self.LLM_MODEL
        defaults = {
            "anthropic": "claude-haiku-4-5-20251001",
            "openai": "gpt-4o-mini",
            "ollama": "ollama/llama3.1",
        }
        return defaults.get(self.LLM_PROVIDER, "claude-haiku-4-5-20251001")


config = Config()
