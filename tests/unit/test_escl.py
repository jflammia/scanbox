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


class TestParseCapabilitiesIconUrl:
    def test_icon_url_parsed(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<scan:ScannerCapabilities xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                          xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
  <pwg:Version>2.63</pwg:Version>
  <pwg:MakeAndModel>HP Color LaserJet MFP M283cdw</pwg:MakeAndModel>
  <scan:IconURI>http://192.168.1.5/hp/device/scanner.png</scan:IconURI>
</scan:ScannerCapabilities>"""
        caps = parse_capabilities(xml)
        assert caps.icon_url == "http://192.168.1.5/hp/device/scanner.png"

    def test_icon_url_empty_when_missing(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<scan:ScannerCapabilities xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                          xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
  <pwg:Version>2.63</pwg:Version>
  <pwg:MakeAndModel>HP Color LaserJet MFP M283cdw</pwg:MakeAndModel>
</scan:ScannerCapabilities>"""
        caps = parse_capabilities(xml)
        assert caps.icon_url == ""


class TestBuildScanSettings:
    def test_generates_valid_xml(self):
        xml = build_scan_settings_xml(dpi=300, color_mode="RGB24", source="Feeder")
        assert "Feeder" in xml
        assert "300" in xml
        assert "RGB24" in xml
        assert "application/pdf" in xml
