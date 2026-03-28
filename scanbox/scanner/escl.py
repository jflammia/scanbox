"""eSCL (Apple AirScan) HTTP client for HP scanner communication."""

import contextlib
import xml.etree.ElementTree as ET

import httpx

from scanbox.scanner.models import ScannerCapabilities, ScannerStatus

ESCL_NS = {
    "scan": "http://schemas.hp.com/imaging/escl/2011/05/03",
    "pwg": "http://www.pwg.org/schemas/2010/12/sm",
}


def parse_capabilities(xml_text: str) -> ScannerCapabilities:
    """Parse eSCL ScannerCapabilities XML."""
    root = ET.fromstring(xml_text)
    caps = ScannerCapabilities()

    model_el = root.find(".//pwg:MakeAndModel", ESCL_NS)
    if model_el is not None and model_el.text:
        caps.make_and_model = model_el.text

    # Check for ADF
    adf = root.find(".//scan:Adf", ESCL_NS)
    if adf is not None:
        caps.has_adf = True
        if adf.find(".//scan:AdfDuplexInputCaps", ESCL_NS) is not None:
            caps.has_duplex_adf = True

    # Resolutions (from ADF or Platen)
    for res_el in root.findall(".//scan:DiscreteResolution", ESCL_NS):
        x_res = res_el.find("scan:XResolution", ESCL_NS)
        if x_res is not None and x_res.text:
            caps.supported_resolutions.append(int(x_res.text))

    # Formats
    for fmt_el in root.findall(".//pwg:DocumentFormat", ESCL_NS):
        if fmt_el.text:
            caps.supported_formats.append(fmt_el.text)

    # Deduplicate
    caps.supported_resolutions = sorted(set(caps.supported_resolutions))
    caps.supported_formats = sorted(set(caps.supported_formats))

    return caps


def parse_status(xml_text: str) -> ScannerStatus:
    """Parse eSCL ScannerStatus XML."""
    root = ET.fromstring(xml_text)
    status = ScannerStatus()

    state_el = root.find(".//pwg:State", ESCL_NS)
    if state_el is not None and state_el.text:
        status.state = state_el.text

    adf_el = root.find(".//scan:AdfState", ESCL_NS)
    if adf_el is not None and adf_el.text:
        status.adf_state = adf_el.text
        status.adf_loaded = "Loaded" in adf_el.text

    return status


def build_scan_settings_xml(
    dpi: int = 300,
    color_mode: str = "RGB24",
    source: str = "Feeder",
) -> str:
    """Build eSCL ScanSettings XML for an ADF scan job."""
    # US Letter at given DPI
    width = int(8.5 * dpi)
    height = int(11 * dpi)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<scan:ScanSettings xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                   xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
  <pwg:Version>2.0</pwg:Version>
  <pwg:InputSource>{source}</pwg:InputSource>
  <pwg:ScanRegions>
    <pwg:ScanRegion>
      <pwg:XOffset>0</pwg:XOffset>
      <pwg:YOffset>0</pwg:YOffset>
      <pwg:Width>{width}</pwg:Width>
      <pwg:Height>{height}</pwg:Height>
      <pwg:ContentRegionUnits>escl:ThreeHundredthsOfInches</pwg:ContentRegionUnits>
    </pwg:ScanRegion>
  </pwg:ScanRegions>
  <scan:ColorMode>{color_mode}</scan:ColorMode>
  <scan:XResolution>{dpi}</scan:XResolution>
  <scan:YResolution>{dpi}</scan:YResolution>
  <pwg:DocumentFormat>application/pdf</pwg:DocumentFormat>
</scan:ScanSettings>"""


class ESCLClient:
    """Async client for eSCL scanner communication."""

    def __init__(self, scanner_ip: str):
        self.base_url = f"http://{scanner_ip}/eSCL"
        self._client = httpx.AsyncClient(timeout=30.0)

    async def get_capabilities(self) -> ScannerCapabilities:
        resp = await self._client.get(f"{self.base_url}/ScannerCapabilities")
        resp.raise_for_status()
        return parse_capabilities(resp.text)

    async def get_status(self) -> ScannerStatus:
        resp = await self._client.get(f"{self.base_url}/ScannerStatus")
        resp.raise_for_status()
        return parse_status(resp.text)

    async def start_scan(self, dpi: int = 300) -> str:
        """Start an ADF scan job. Returns the job URL."""
        xml = build_scan_settings_xml(dpi=dpi)
        resp = await self._client.post(
            f"{self.base_url}/ScanJobs",
            content=xml,
            headers={"Content-Type": "text/xml"},
        )
        resp.raise_for_status()
        return resp.headers.get("Location", "")

    async def get_next_page(self, job_url: str) -> bytes | None:
        """Get the next scanned page. Returns None when ADF is empty (404)."""
        url = f"{job_url}/NextDocument"
        if not url.startswith("http"):
            url = f"http://{self.base_url.split('//')[1].split('/')[0]}{url}"
        try:
            resp = await self._client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def cancel_job(self, job_url: str) -> None:
        """Cancel an active scan job."""
        with contextlib.suppress(httpx.HTTPError):
            await self._client.delete(job_url)

    async def close(self) -> None:
        await self._client.aclose()
