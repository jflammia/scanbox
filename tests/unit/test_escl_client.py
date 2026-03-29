"""Unit tests for eSCL client with mocked HTTP calls."""

from unittest.mock import AsyncMock, MagicMock

import httpx

from scanbox.scanner.escl import ESCLClient, build_scan_settings_xml


class TestBuildScanSettingsXml:
    def test_default_settings(self):
        xml = build_scan_settings_xml()
        assert "300" in xml
        assert "RGB24" in xml
        assert "Feeder" in xml
        assert "application/pdf" in xml

    def test_custom_dpi(self):
        xml = build_scan_settings_xml(dpi=150)
        assert "<scan:XResolution>150</scan:XResolution>" in xml
        assert "<scan:YResolution>150</scan:YResolution>" in xml

    def test_custom_source(self):
        xml = build_scan_settings_xml(source="Platen")
        assert "<pwg:InputSource>Platen</pwg:InputSource>" in xml


class TestESCLClientGetCapabilities:
    async def test_get_capabilities(self):
        client = ESCLClient("192.168.1.1")
        mock_resp = MagicMock()
        mock_resp.text = """<?xml version="1.0" encoding="UTF-8"?>
        <scan:ScannerCapabilities xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                                   xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
          <pwg:MakeAndModel>HP LaserJet MFP M283</pwg:MakeAndModel>
          <scan:Adf>
            <scan:AdfSimplexInputCaps>
              <scan:DiscreteResolution><scan:XResolution>300</scan:XResolution></scan:DiscreteResolution>
            </scan:AdfSimplexInputCaps>
          </scan:Adf>
        </scan:ScannerCapabilities>"""
        mock_resp.raise_for_status = MagicMock()
        client._client.get = AsyncMock(return_value=mock_resp)

        caps = await client.get_capabilities()
        assert caps.make_and_model == "HP LaserJet MFP M283"
        assert caps.has_adf is True
        assert 300 in caps.supported_resolutions
        await client.close()


class TestESCLClientGetStatus:
    async def test_get_status_idle(self):
        client = ESCLClient("192.168.1.1")
        mock_resp = MagicMock()
        mock_resp.text = """<?xml version="1.0" encoding="UTF-8"?>
        <scan:ScannerStatus xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                            xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
          <pwg:State>Idle</pwg:State>
          <scan:AdfState>ScannerAdfLoaded</scan:AdfState>
        </scan:ScannerStatus>"""
        mock_resp.raise_for_status = MagicMock()
        client._client.get = AsyncMock(return_value=mock_resp)

        status = await client.get_status()
        assert status.state == "Idle"
        assert status.adf_loaded is True
        assert status.adf_state == "ScannerAdfLoaded"
        await client.close()


class TestESCLClientStartScan:
    async def test_start_scan(self):
        client = ESCLClient("192.168.1.1")
        mock_resp = MagicMock()
        mock_resp.headers = {"Location": "http://192.168.1.1/eSCL/ScanJobs/1234"}
        mock_resp.raise_for_status = MagicMock()
        client._client.post = AsyncMock(return_value=mock_resp)

        job_url = await client.start_scan(dpi=300)
        assert job_url == "http://192.168.1.1/eSCL/ScanJobs/1234"
        await client.close()


class TestESCLClientGetNextPage:
    async def test_get_next_page_success(self):
        client = ESCLClient("192.168.1.1")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"%PDF-1.4 page data"
        mock_resp.raise_for_status = MagicMock()
        client._client.get = AsyncMock(return_value=mock_resp)

        data = await client.get_next_page("http://scanner/eSCL/ScanJobs/1234")
        assert data == b"%PDF-1.4 page data"
        await client.close()

    async def test_get_next_page_404_returns_none(self):
        client = ESCLClient("192.168.1.1")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        client._client.get = AsyncMock(return_value=mock_resp)

        data = await client.get_next_page("http://scanner/eSCL/ScanJobs/1234")
        assert data is None
        await client.close()

    async def test_get_next_page_http_error_404(self):
        client = ESCLClient("192.168.1.1")
        error_resp = MagicMock()
        error_resp.status_code = 404
        error = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=error_resp)
        client._client.get = AsyncMock(side_effect=error)

        data = await client.get_next_page("http://scanner/eSCL/ScanJobs/1234")
        assert data is None
        await client.close()


class TestESCLClientCancelJob:
    async def test_cancel_job(self):
        client = ESCLClient("192.168.1.1")
        client._client.delete = AsyncMock()

        await client.cancel_job("http://scanner/eSCL/ScanJobs/1234")
        client._client.delete.assert_awaited_once()
        await client.close()

    async def test_cancel_job_error_suppressed(self):
        client = ESCLClient("192.168.1.1")
        client._client.delete = AsyncMock(side_effect=httpx.HTTPError("Connection lost"))

        # Should not raise
        await client.cancel_job("http://scanner/eSCL/ScanJobs/1234")
        await client.close()
