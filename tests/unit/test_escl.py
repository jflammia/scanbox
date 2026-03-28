"""Tests for eSCL scanner client — XML parsing and job creation."""

from pathlib import Path

from scanbox.scanner.escl import build_scan_settings_xml, parse_capabilities, parse_status


class TestParseCapabilities:
    def test_parses_adf_support(self, escl_fixtures_dir: Path):
        xml = (escl_fixtures_dir / "capabilities.xml").read_text()
        caps = parse_capabilities(xml)
        assert caps.has_adf is True
        assert 300 in caps.supported_resolutions
        assert "application/pdf" in caps.supported_formats
        assert "HP" in caps.make_and_model


class TestParseStatus:
    def test_parses_idle_with_adf_loaded(self, escl_fixtures_dir: Path):
        xml = (escl_fixtures_dir / "status_idle.xml").read_text()
        status = parse_status(xml)
        assert status.state == "Idle"
        assert status.adf_loaded is True


class TestBuildScanSettings:
    def test_generates_valid_xml(self):
        xml = build_scan_settings_xml(dpi=300, color_mode="RGB24", source="Feeder")
        assert "Feeder" in xml
        assert "300" in xml
        assert "RGB24" in xml
        assert "application/pdf" in xml
