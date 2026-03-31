"""Configuration loaded from environment variables with sensible defaults."""

import json
import os
from pathlib import Path


def _read_runtime_config() -> dict:
    """Read user-configured settings from runtime.json (set via the UI)."""
    path = Path(os.getenv("INTERNAL_DATA_DIR", "/app/data")) / "config" / "runtime.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


class Config:
    """Reads environment variables at instantiation time, not import time."""

    def __init__(self) -> None:
        runtime = _read_runtime_config()

        # Scanner — runtime config takes priority over env var
        self.SCANNER_IP: str = runtime.get("scanner_ip") or os.getenv("SCANNER_IP", "")

        # LLM — runtime config takes priority over env var
        self.LLM_PROVIDER: str = runtime.get("llm_provider") or os.getenv(
            "LLM_PROVIDER", "anthropic"
        )
        self.LLM_MODEL: str = runtime.get("llm_model") or os.getenv("LLM_MODEL", "")
        self.ANTHROPIC_API_KEY: str = (
            runtime.get("llm_api_key")
            if self.LLM_PROVIDER == "anthropic"
            else os.getenv("ANTHROPIC_API_KEY", "")
        ) or os.getenv("ANTHROPIC_API_KEY", "")
        self.OPENAI_API_KEY: str = (
            runtime.get("llm_api_key")
            if self.LLM_PROVIDER == "openai"
            else os.getenv("OPENAI_API_KEY", "")
        ) or os.getenv("OPENAI_API_KEY", "")
        self.OLLAMA_URL: str = runtime.get("llm_url") or os.getenv(
            "OLLAMA_URL", "http://localhost:11434"
        )

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

        # Pipeline — stage-aware settings
        self.PIPELINE_AUTO_ADVANCE_ON_ERROR: bool = os.getenv(
            "PIPELINE_AUTO_ADVANCE_ON_ERROR", ""
        ).lower() in ("true", "1", "yes")
        self.PIPELINE_CONFIDENCE_THRESHOLD: float = float(
            os.getenv("PIPELINE_CONFIDENCE_THRESHOLD", "0.7")
        )

        # Version: release tag when set, otherwise build info, otherwise "dev"
        app_version = os.getenv("APP_VERSION", "dev")
        git_commit = os.getenv("GIT_COMMIT", "unknown")
        build_time = os.getenv("BUILD_TIME", "")
        if app_version == "dev" and git_commit not in ("unknown", ""):
            app_version = f"g{git_commit[:7]}"
            if build_time:
                app_version = f"{build_time} ({app_version})"
        self.APP_VERSION: str = app_version

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

    def llm_api_base(self) -> str | None:
        """Return the api_base URL for litellm, or None for cloud providers."""
        if self.LLM_PROVIDER == "ollama":
            return self.OLLAMA_URL
        base = os.getenv("OPENAI_API_BASE", "")
        return base or None


config = Config()
