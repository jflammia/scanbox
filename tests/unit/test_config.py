"""Tests for scanbox.config — environment variable loading and derived paths."""

from pathlib import Path

from scanbox.config import Config


class TestConfigDefaults:
    """Config should have sensible defaults when no env vars are set."""

    def test_scanner_ip_defaults_empty(self):
        c = Config()
        assert c.SCANNER_IP == "" or isinstance(c.SCANNER_IP, str)

    def test_llm_provider_defaults_anthropic(self):
        c = Config()
        assert c.LLM_PROVIDER == "anthropic"

    def test_ollama_url_default(self):
        c = Config()
        assert c.OLLAMA_URL == "http://localhost:11434"

    def test_internal_data_dir_default(self):
        c = Config()
        assert Path("/app/data") == c.INTERNAL_DATA_DIR

    def test_output_dir_default(self):
        c = Config()
        assert Path("/output") == c.OUTPUT_DIR

    def test_blank_page_threshold_default(self):
        c = Config()
        assert c.BLANK_PAGE_THRESHOLD == 0.01

    def test_ocr_language_default(self):
        c = Config()
        assert c.OCR_LANGUAGE == "eng"

    def test_default_dpi(self):
        c = Config()
        assert c.DEFAULT_DPI == 300

    def test_api_key_off_by_default(self):
        c = Config()
        assert c.SCANBOX_API_KEY == ""

    def test_mcp_disabled_by_default(self):
        c = Config()
        assert c.MCP_ENABLED is False

    def test_webhook_url_empty_by_default(self):
        c = Config()
        assert c.WEBHOOK_URL == ""

    def test_webhook_secret_empty_by_default(self):
        c = Config()
        assert c.WEBHOOK_SECRET == ""


class TestConfigDerivedPaths:
    """Derived path properties should build on base dirs."""

    def test_sessions_dir(self):
        c = Config()
        assert c.sessions_dir == c.INTERNAL_DATA_DIR / "sessions"

    def test_config_dir(self):
        c = Config()
        assert c.config_dir == c.INTERNAL_DATA_DIR / "config"

    def test_db_path(self):
        c = Config()
        assert c.db_path == c.INTERNAL_DATA_DIR / "scanbox.db"
        assert c.db_path.name == "scanbox.db"

    def test_archive_dir(self):
        c = Config()
        assert c.archive_dir == c.OUTPUT_DIR / "archive"

    def test_medical_records_dir(self):
        c = Config()
        assert c.medical_records_dir == c.OUTPUT_DIR / "medical-records"


class TestConfigLlmModelId:
    """LLM model ID resolution based on provider and explicit model."""

    def test_anthropic_default_model(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.delenv("LLM_MODEL", raising=False)
        c = Config()
        c.LLM_PROVIDER = "anthropic"
        c.LLM_MODEL = ""
        assert c.llm_model_id() == "claude-haiku-4-5-20251001"

    def test_openai_default_model(self):
        c = Config()
        c.LLM_PROVIDER = "openai"
        c.LLM_MODEL = ""
        assert c.llm_model_id() == "gpt-4o-mini"

    def test_ollama_default_model(self):
        c = Config()
        c.LLM_PROVIDER = "ollama"
        c.LLM_MODEL = ""
        assert c.llm_model_id() == "ollama/llama3.1"

    def test_explicit_model_overrides_provider_default(self):
        c = Config()
        c.LLM_PROVIDER = "anthropic"
        c.LLM_MODEL = "claude-sonnet-4-20250514"
        assert c.llm_model_id() == "claude-sonnet-4-20250514"

    def test_unknown_provider_falls_back_to_anthropic(self):
        c = Config()
        c.LLM_PROVIDER = "unknown-provider"
        c.LLM_MODEL = ""
        assert c.llm_model_id() == "claude-haiku-4-5-20251001"


class TestConfigEnvOverrides:
    """Config should pick up environment variable overrides."""

    def test_scanner_ip_from_env(self, monkeypatch):
        monkeypatch.setenv("SCANNER_IP", "192.168.1.50")
        c = Config()
        assert c.SCANNER_IP == "192.168.1.50"

    def test_blank_threshold_from_env(self, monkeypatch):
        monkeypatch.setenv("BLANK_PAGE_THRESHOLD", "0.05")
        c = Config()
        assert c.BLANK_PAGE_THRESHOLD == 0.05

    def test_custom_data_dir(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_DATA_DIR", "/tmp/scanbox-data")
        c = Config()
        assert Path("/tmp/scanbox-data") == c.INTERNAL_DATA_DIR
        assert c.db_path == Path("/tmp/scanbox-data/scanbox.db")

    def test_mcp_enabled_true(self, monkeypatch):
        monkeypatch.setenv("MCP_ENABLED", "true")
        c = Config()
        assert c.MCP_ENABLED is True

    def test_mcp_enabled_yes(self, monkeypatch):
        monkeypatch.setenv("MCP_ENABLED", "yes")
        c = Config()
        assert c.MCP_ENABLED is True

    def test_mcp_enabled_1(self, monkeypatch):
        monkeypatch.setenv("MCP_ENABLED", "1")
        c = Config()
        assert c.MCP_ENABLED is True

    def test_mcp_disabled_false(self, monkeypatch):
        monkeypatch.setenv("MCP_ENABLED", "false")
        c = Config()
        assert c.MCP_ENABLED is False

    def test_version_defaults_to_dev(self, monkeypatch):
        monkeypatch.delenv("APP_VERSION", raising=False)
        monkeypatch.delenv("GIT_COMMIT", raising=False)
        c = Config()
        assert c.APP_VERSION == "dev"

    def test_version_uses_git_hash_when_dev(self, monkeypatch):
        monkeypatch.setenv("APP_VERSION", "dev")
        monkeypatch.setenv("GIT_COMMIT", "abc1234def5678")
        monkeypatch.delenv("BUILD_TIME", raising=False)
        c = Config()
        assert c.APP_VERSION == "gabc1234"

    def test_version_includes_build_time(self, monkeypatch):
        monkeypatch.setenv("APP_VERSION", "dev")
        monkeypatch.setenv("GIT_COMMIT", "abc1234def5678")
        monkeypatch.setenv("BUILD_TIME", "2026-03-31 17:00")
        c = Config()
        assert c.APP_VERSION == "2026-03-31 17:00 (gabc1234)"

    def test_version_preserves_explicit_release(self, monkeypatch):
        monkeypatch.setenv("APP_VERSION", "1.3.0")
        monkeypatch.setenv("GIT_COMMIT", "abc1234def5678")
        monkeypatch.setenv("BUILD_TIME", "2026-03-31 17:00")
        c = Config()
        assert c.APP_VERSION == "1.3.0"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("SCANBOX_API_KEY", "secret-key-123")
        c = Config()
        assert c.SCANBOX_API_KEY == "secret-key-123"
