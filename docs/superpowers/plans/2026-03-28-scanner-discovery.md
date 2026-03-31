# Scanner Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace the HTTP subnet probe with proper mDNS/DNS-SD scanner discovery, add a verification checklist UX, document container networking constraints, and expose discovery via API + MCP.

**Architecture:** New `scanbox/scanner/discovery.py` module uses python-zeroconf to browse for `_uscan._tcp.local.` and `_uscans._tcp.local.` services. A 4-step verification checklist validates scanner connectivity before saving. The discovery service is exposed through REST API, MCP tool, setup wizard HTML, and settings page.

**Tech Stack:** python-zeroconf (mDNS/DNS-SD), FastAPI, htmx, Alpine.js

**Spec:** `docs/superpowers/specs/2026-03-28-scanner-discovery-design.md`

---

### Task 1: Add zeroconf dependency and icon_url to ScannerCapabilities

**Files:**
- Modify: `pyproject.toml:11-26`
- Modify: `scanbox/scanner/models.py:7-15`
- Modify: `scanbox/scanner/escl.py:16-47`
- Test: `tests/unit/test_escl.py`

- [x] **Step 1: Add zeroconf to pyproject.toml**

In `pyproject.toml`, add `zeroconf` after `mcp`:

```toml
    "mcp>=1.0",
    "zeroconf>=0.140",
```

- [x] **Step 2: Write failing test for icon_url in parse_capabilities**

In `tests/unit/test_escl.py`, add a test for parsing `IconURI`:

```python
class TestParseCapabilitiesIconUrl:
    def test_icon_url_parsed(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <scan:ScannerCapabilities
            xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
            xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
          <pwg:MakeAndModel>Test Scanner</pwg:MakeAndModel>
          <scan:IconURI>http://192.168.10.11/images/printer.png</scan:IconURI>
        </scan:ScannerCapabilities>"""
        caps = parse_capabilities(xml)
        assert caps.icon_url == "http://192.168.10.11/images/printer.png"

    def test_icon_url_empty_when_missing(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <scan:ScannerCapabilities
            xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
            xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
          <pwg:MakeAndModel>Test Scanner</pwg:MakeAndModel>
        </scan:ScannerCapabilities>"""
        caps = parse_capabilities(xml)
        assert caps.icon_url == ""
```

- [x] **Step 3: Run test to verify it fails**

Run: `pytest tests/unit/test_escl.py::TestParseCapabilitiesIconUrl -v`
Expected: FAIL -- `ScannerCapabilities` has no `icon_url` attribute

- [x] **Step 4: Add icon_url field to ScannerCapabilities**

In `scanbox/scanner/models.py`, add `icon_url` to the dataclass:

```python
@dataclass
class ScannerCapabilities:
    make_and_model: str = ""
    has_adf: bool = False
    has_duplex_adf: bool = False
    supported_resolutions: list[int] = field(default_factory=list)
    supported_formats: list[str] = field(default_factory=list)
    max_width: int = 2550  # US Letter at 300 DPI
    max_height: int = 3300
    icon_url: str = ""
```

- [x] **Step 5: Parse IconURI in parse_capabilities**

In `scanbox/scanner/escl.py`, add after the `model_el` block (after line 22):

```python
    icon_el = root.find(".//scan:IconURI", ESCL_NS)
    if icon_el is not None and icon_el.text:
        caps.icon_url = icon_el.text.strip()
```

- [x] **Step 6: Run test to verify it passes**

Run: `pytest tests/unit/test_escl.py -v`
Expected: All PASS including new icon_url tests

- [x] **Step 7: Install zeroconf**

Run: `pip install -e ".[dev]"`
Expected: zeroconf installs successfully

- [x] **Step 8: Commit**

```bash
git add pyproject.toml scanbox/scanner/models.py scanbox/scanner/escl.py tests/unit/test_escl.py
git commit -m "feat: add zeroconf dependency and icon_url to ScannerCapabilities"
```

---

### Task 2: Create the mDNS discovery service

**Files:**
- Create: `scanbox/scanner/discovery.py`
- Test: `tests/unit/test_discovery.py`

- [x] **Step 1: Write failing tests for discover_scanners**

Create `tests/unit/test_discovery.py`:

```python
"""Tests for mDNS scanner discovery."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scanbox.scanner.discovery import DiscoveredScanner, discover_scanners


class TestDiscoverScanners:
    @patch("scanbox.scanner.discovery.AsyncZeroconf")
    @patch("scanbox.scanner.discovery.AsyncServiceBrowser")
    async def test_returns_empty_when_no_scanners(self, mock_browser_cls, mock_zc_cls):
        mock_zc = MagicMock()
        mock_zc.async_close = AsyncMock()
        mock_zc_cls.return_value = mock_zc
        mock_browser = MagicMock()
        mock_browser.async_cancel = AsyncMock()
        mock_browser_cls.return_value = mock_browser

        result = await discover_scanners(timeout=0.1)
        assert result == []
        mock_browser.async_cancel.assert_called_once()
        mock_zc.async_close.assert_called_once()

    def test_discovered_scanner_dataclass(self):
        scanner = DiscoveredScanner(
            ip="192.168.10.11",
            port=80,
            name="HP Printer._uscan._tcp.local.",
            model="HP Color LaserJet MFP M283cdw",
            base_path="eSCL",
            uuid="abc-123",
            icon_url="http://192.168.10.11/icon.png",
            secure=False,
        )
        assert scanner.ip == "192.168.10.11"
        assert scanner.model == "HP Color LaserJet MFP M283cdw"
        assert scanner.icon_url == "http://192.168.10.11/icon.png"
        assert not scanner.secure


class TestDiscoveredScannerDedup:
    def test_dedup_by_uuid(self):
        from scanbox.scanner.discovery import _dedup_scanners

        scanners = [
            DiscoveredScanner("10.0.0.1", 80, "A", "Model", "eSCL", "uuid-1", "", False),
            DiscoveredScanner("10.0.0.1", 443, "A", "Model", "eSCL", "uuid-1", "", True),
            DiscoveredScanner("10.0.0.2", 80, "B", "Model2", "eSCL", "uuid-2", "", False),
        ]
        result = _dedup_scanners(scanners)
        assert len(result) == 2
        uuids = {s.uuid for s in result}
        assert uuids == {"uuid-1", "uuid-2"}
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_discovery.py -v`
Expected: FAIL -- module `scanbox.scanner.discovery` not found

- [x] **Step 3: Implement the discovery module**

Create `scanbox/scanner/discovery.py`:

```python
"""mDNS/DNS-SD scanner discovery for eSCL/AirScan devices."""

import asyncio
from dataclasses import dataclass

from zeroconf import IPVersion, ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

ESCL_SERVICE_TYPES = ["_uscan._tcp.local.", "_uscans._tcp.local."]

DISCOVERY_HINT = (
    "Automatic scanner discovery uses mDNS, which requires the container to have "
    "direct LAN access (Linux with network_mode: host or macvlan). On macOS or "
    "standard Docker bridge networking, enter the scanner's IP address manually. "
    "You can find it in your scanner's network settings or your router's device list."
)


@dataclass
class DiscoveredScanner:
    ip: str
    port: int
    name: str
    model: str
    base_path: str
    uuid: str
    icon_url: str
    secure: bool


def _dedup_scanners(scanners: list[DiscoveredScanner]) -> list[DiscoveredScanner]:
    """Remove duplicates by UUID, preferring secure (HTTPS) entries."""
    seen: dict[str, DiscoveredScanner] = {}
    for s in scanners:
        key = s.uuid or f"{s.ip}:{s.port}"
        if key not in seen or (s.secure and not seen[key].secure):
            seen[key] = s
    return list(seen.values())


async def discover_scanners(timeout: float = 5.0) -> list[DiscoveredScanner]:
    """Discover eSCL scanners on the local network via mDNS."""
    found: list[DiscoveredScanner] = []
    lock = asyncio.Lock()

    def on_state_change(
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change is ServiceStateChange.Added:
            asyncio.ensure_future(_resolve(zeroconf, service_type, name))

    async def _resolve(zc: Zeroconf, stype: str, name: str) -> None:
        info = AsyncServiceInfo(stype, name)
        await info.async_request(zc, 3000)
        if not info:
            return
        addresses = info.parsed_addresses(IPVersion.V4Only)
        if not addresses:
            return
        port = info.port or 80
        props = {
            k.decode(): v.decode() if v else ""
            for k, v in (info.properties or {}).items()
        }
        scanner = DiscoveredScanner(
            ip=addresses[0],
            port=port,
            name=name,
            model=props.get("ty", "Unknown scanner"),
            base_path=props.get("rs", "eSCL"),
            uuid=props.get("UUID", ""),
            icon_url=props.get("representation", ""),
            secure=stype.startswith("_uscans"),
        )
        async with lock:
            found.append(scanner)

    aiozc = AsyncZeroconf(ip_version=IPVersion.V4Only)
    browser = AsyncServiceBrowser(
        aiozc.zeroconf, ESCL_SERVICE_TYPES, handlers=[on_state_change]
    )
    await asyncio.sleep(timeout)
    await browser.async_cancel()
    await aiozc.async_close()

    return _dedup_scanners(found)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_discovery.py -v`
Expected: All PASS

- [x] **Step 5: Run full test suite**

Run: `pytest tests/ --ignore=tests/unit/test_fixtures.py -q`
Expected: All pass, no regressions

- [x] **Step 6: Commit**

```bash
git add scanbox/scanner/discovery.py tests/unit/test_discovery.py
git commit -m "feat: add mDNS scanner discovery service"
```

---

### Task 3: Add JSON discovery API endpoint

**Files:**
- Modify: `scanbox/api/scanner.py`
- Test: `tests/integration/test_scanner_discover_api.py`

- [x] **Step 1: Write failing tests for the discover endpoint**

Create `tests/integration/test_scanner_discover_api.py`:

```python
"""Tests for scanner discovery API endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from scanbox.scanner.discovery import DiscoveredScanner


class TestScannerDiscoverAPI:
    @patch("scanbox.api.scanner.discover_scanners", new_callable=AsyncMock)
    async def test_returns_found_scanners(self, mock_discover, client: AsyncClient):
        mock_discover.return_value = [
            DiscoveredScanner(
                ip="192.168.10.11",
                port=80,
                name="HP._uscan._tcp.local.",
                model="HP MFP M283cdw",
                base_path="eSCL",
                uuid="abc-123",
                icon_url="http://192.168.10.11/icon.png",
                secure=False,
            )
        ]
        resp = await client.post("/api/scanner/discover")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["scanners"][0]["ip"] == "192.168.10.11"
        assert data["scanners"][0]["model"] == "HP MFP M283cdw"
        assert data["scanners"][0]["icon_url"] == "http://192.168.10.11/icon.png"
        assert data["hint"] is None

    @patch("scanbox.api.scanner.discover_scanners", new_callable=AsyncMock)
    async def test_returns_hint_when_empty(self, mock_discover, client: AsyncClient):
        mock_discover.return_value = []
        resp = await client.post("/api/scanner/discover")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["scanners"] == []
        assert "mDNS" in data["hint"]
        assert "network_mode" in data["hint"]

    @patch("scanbox.api.scanner.discover_scanners", new_callable=AsyncMock)
    async def test_timeout_clamped_to_max(self, mock_discover, client: AsyncClient):
        mock_discover.return_value = []
        await client.post("/api/scanner/discover?timeout=60")
        mock_discover.assert_called_once_with(timeout=30.0)

    @patch("scanbox.api.scanner.discover_scanners", new_callable=AsyncMock)
    async def test_default_timeout(self, mock_discover, client: AsyncClient):
        mock_discover.return_value = []
        await client.post("/api/scanner/discover")
        mock_discover.assert_called_once_with(timeout=5.0)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_scanner_discover_api.py -v`
Expected: FAIL -- no route for `/api/scanner/discover`

- [x] **Step 3: Implement the discover endpoint**

In `scanbox/api/scanner.py`, add at the end of the file:

```python
from scanbox.scanner.discovery import DISCOVERY_HINT, discover_scanners


@router.post("/api/scanner/discover")
async def discover(timeout: float = 5.0):
    """Discover eSCL scanners on the local network via mDNS.

    Also serves as the 'rescan' action -- call again to re-run discovery.
    """
    timeout = min(max(timeout, 1.0), 30.0)
    scanners = await discover_scanners(timeout=timeout)
    return {
        "scanners": [
            {
                "ip": s.ip,
                "port": s.port,
                "model": s.model,
                "name": s.name,
                "uuid": s.uuid,
                "icon_url": s.icon_url,
                "secure": s.secure,
            }
            for s in scanners
        ],
        "count": len(scanners),
        "hint": DISCOVERY_HINT if not scanners else None,
    }
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_scanner_discover_api.py -v`
Expected: All PASS

- [x] **Step 5: Commit**

```bash
git add scanbox/api/scanner.py tests/integration/test_scanner_discover_api.py
git commit -m "feat: add POST /api/scanner/discover endpoint"
```

---

### Task 4: Add verify-scanner endpoint and replace subnet probe

**Files:**
- Modify: `scanbox/api/setup.py`
- Test: `tests/integration/test_verify_scanner.py`

- [x] **Step 1: Write failing tests for verify-scanner**

Create `tests/integration/test_verify_scanner.py`:

```python
"""Tests for scanner verification checklist endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from scanbox.scanner.models import ScannerCapabilities, ScannerStatus


class TestVerifyScanner:
    @patch("scanbox.api.setup.ESCLClient")
    async def test_all_checks_pass(self, mock_client_cls, client: AsyncClient, tmp_path, monkeypatch):
        monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path))
        mock_client = AsyncMock()
        mock_client.get_status.return_value = ScannerStatus(state="Idle", adf_loaded=True)
        mock_client.get_capabilities.return_value = ScannerCapabilities(
            make_and_model="Test Scanner", has_adf=True, icon_url="http://1.2.3.4/icon.png"
        )
        mock_client_cls.return_value = mock_client

        with patch("scanbox.api.setup.socket") as mock_socket:
            mock_conn = mock_socket.create_connection.return_value
            resp = await client.post("/setup/verify-scanner", data={"scanner_ip": "1.2.3.4"})

        assert resp.status_code == 200
        html = resp.text
        assert "Reaching scanner" in html
        assert "eSCL protocol" in html
        assert "Scanner capabilities" in html
        assert "Scanner ready" in html
        assert "Test Scanner" in html
        assert "step = 2" in html

    @patch("scanbox.api.setup.socket")
    async def test_unreachable_scanner(self, mock_socket, client: AsyncClient):
        mock_socket.create_connection.side_effect = ConnectionError("timeout")

        resp = await client.post("/setup/verify-scanner", data={"scanner_ip": "1.2.3.4"})
        html = resp.text
        assert "Reaching scanner" in html
        assert "step = 2" not in html
        assert "Retry" in html

    @patch("scanbox.api.setup.ESCLClient")
    @patch("scanbox.api.setup.socket")
    async def test_no_adf(self, mock_socket, mock_client_cls, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.get_status.return_value = ScannerStatus(state="Idle")
        mock_client.get_capabilities.return_value = ScannerCapabilities(
            make_and_model="Test Scanner", has_adf=False
        )
        mock_client_cls.return_value = mock_client

        resp = await client.post("/setup/verify-scanner", data={"scanner_ip": "1.2.3.4"})
        html = resp.text
        assert "No document feeder" in html
        assert "Retry" in html

    async def test_empty_ip(self, client: AsyncClient):
        resp = await client.post("/setup/verify-scanner", data={"scanner_ip": ""})
        assert "Enter a scanner IP" in resp.text
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_verify_scanner.py -v`
Expected: FAIL -- no route for `/setup/verify-scanner`

- [x] **Step 3: Replace the subnet probe and add verify-scanner**

In `scanbox/api/setup.py`, replace the entire `discover_scanners` function (the one with subnet probing, starting with `@router.post("/setup/discover-scanners"...)`) with the new mDNS-based version, and add the verify-scanner endpoint.

The new `discover_scanners` HTML wrapper calls `scanbox.scanner.discovery.discover_scanners()` instead of doing subnet probes. The `verify_scanner` endpoint runs 4 sequential checks (TCP, eSCL status, capabilities/ADF, idle state) and returns a checklist HTML.

See the full implementation in the spec at `docs/superpowers/specs/2026-03-28-scanner-discovery-design.md`, sections "POST /setup/discover-scanners (HTML)" and "POST /setup/verify-scanner (HTML)".

Key details:
- `_render_checklist()` helper builds the HTML checklist with pass/fail icons
- On all pass: saves `scanner_ip` to `runtime.json`, returns auto-advance trigger `x-init="setTimeout(() => step = 2, 1500)"`
- On failure: returns Retry and "Try a different scanner" buttons
- Scanner cards from discovery include the device icon from `icon_url` (falls back to printer emoji)
- Uses `socket.create_connection` for TCP check, `ESCLClient` for eSCL checks

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_verify_scanner.py -v`
Expected: All PASS

- [x] **Step 5: Run full test suite, fix any broken setup wizard tests**

Run: `pytest tests/ --ignore=tests/unit/test_fixtures.py -q`

Update any tests that reference the old subnet probe response text. The key assertion changes:
- `"Find your scanner"` in Step 1 (unchanged)
- `"discover-scanners"` endpoint name (unchanged)
- `"verify-scanner"` is the new endpoint to check for
- Remove assertions about `"Connect your scanner"` if present

- [x] **Step 6: Commit**

```bash
git add scanbox/api/setup.py tests/integration/test_verify_scanner.py tests/
git commit -m "feat: add verify-scanner checklist, replace subnet probe with mDNS"
```

---

### Task 5: Rewrite setup wizard Step 1 template

**Files:**
- Modify: `scanbox/templates/setup.html`

- [x] **Step 1: Rewrite Step 1 in setup.html**

Replace the entire `{# Step 1: Scanner Check #}` div. The new version has:
1. "Find your scanner" heading
2. Discovery area with htmx `hx-trigger="load"` calling `/setup/discover-scanners`
3. Spinner while scanning
4. "Rescan Network" button
5. Manual IP entry form posting to `/setup/verify-scanner`
6. Verification result area (`#scanner-verify-result`)
7. "Skip for now" button

Key htmx attributes:
- Discovery: `hx-post="/setup/discover-scanners"` with `hx-trigger="load"` on the container div
- Verify form: `hx-post="/setup/verify-scanner"` targeting `#scanner-verify-result`
- Rescan button: `hx-post="/setup/discover-scanners"` targeting the discovery area
- Scanner cards use `x-ref="scannerIp"` to fill the IP field and trigger form submission

- [x] **Step 2: Run setup wizard tests**

Run: `pytest tests/e2e/test_ui_comprehensive.py::TestSetupPage -v`

Update `test_step1_scanner_check` assertions to match the new template content:
- Assert `"Find your scanner"` in response
- Assert `"verify-scanner"` in response
- Assert `"discover-scanners"` in response

- [x] **Step 3: Commit**

```bash
git add scanbox/templates/setup.html tests/
git commit -m "feat: rewrite setup Step 1 with discovery cards and verify checklist"
```

---

### Task 6: Add Rescan Network to Settings page

**Files:**
- Modify: `scanbox/templates/settings.html`

- [x] **Step 1: Update the Scanner section**

Add `x-data` wrapper and `x-ref="scannerIp"` to the scanner IP input. Add a "Rescan Network" button below the save form that calls `/setup/discover-scanners` and shows results in a `#settings-discover-result` div.

The discover-scanners HTML endpoint returns cards with `@click` handlers that reference `$refs.scannerIp` -- this works because the settings section is now wrapped in `x-data`.

- [x] **Step 2: Run settings page tests**

Run: `pytest tests/e2e/test_ui_comprehensive.py::TestSettingsPage -v`
Expected: All PASS

- [x] **Step 3: Commit**

```bash
git add scanbox/templates/settings.html
git commit -m "feat: add Rescan Network button to Settings page"
```

---

### Task 7: Add MCP discover tool and update hints

**Files:**
- Modify: `scanbox/mcp/server.py`

- [x] **Step 1: Add scanbox_discover_scanners tool**

Add a new `@mcp.tool()` function `scanbox_discover_scanners(timeout: float = 5.0)` that imports and calls `discover_scanners()` from `scanbox.scanner.discovery`, returns the same JSON shape as the REST API (`{scanners, count, hint}`).

- [x] **Step 2: Update scanbox_get_scanner_status hint**

Change the "not configured" message to: `"No scanner configured. Use scanbox_discover_scanners() to find scanners on your network, or set the IP manually via the Settings page."`

- [x] **Step 3: Update scanbox_setup_guide Step 1**

Update Step 1 description to mention `scanbox_discover_scanners()` for automatic discovery, explain the mDNS container networking constraint, and recommend manual IP for macOS/bridge setups.

- [x] **Step 4: Update scanbox_diagnose_system scanner hint**

Change the "not configured" issue text to mention `scanbox_discover_scanners()`.

- [x] **Step 5: Run full test suite**

Run: `pytest tests/ --ignore=tests/unit/test_fixtures.py -q`
Expected: All pass

- [x] **Step 6: Commit**

```bash
git add scanbox/mcp/server.py
git commit -m "feat: add MCP discover tool, update scanner hints"
```

---

### Task 8: Update documentation

**Files:**
- Modify: `docs/design.md`
- Modify: `docs/api-spec.md`
- Modify: `docs/mcp-server.md`

- [x] **Step 1: Add Scanner Discovery section to design.md**

Add a "Scanner Discovery" subsection explaining mDNS/DNS-SD service types, TXT record fields, and the container networking constraint table. Include the deployment recommendation (Linux + `network_mode: host`).

- [x] **Step 2: Add discover endpoint to api-spec.md**

Document `POST /api/scanner/discover` with query parameters, response examples (found and empty with hint), and container networking note.

- [x] **Step 3: Add discover tool to mcp-server.md**

Document `scanbox_discover_scanners` with parameters, return format, and examples (found and empty).

- [x] **Step 4: Commit**

```bash
git add docs/design.md docs/api-spec.md docs/mcp-server.md
git commit -m "docs: add scanner discovery, container networking, and mDNS documentation"
```

---

### Task 9: Final cleanup, full test suite, and lint

- [x] **Step 1: Run full test suite**

Run: `pytest tests/ --ignore=tests/unit/test_fixtures.py -q`
Expected: All pass, no regressions

- [x] **Step 2: Format and lint**

```bash
ruff format scanbox/ tests/
ruff check scanbox/ tests/
```

- [x] **Step 3: Commit any cleanup**

```bash
git add -A
git commit -m "chore: final cleanup and lint"
```

---

### Task 10: Integration test and PR

- [x] **Step 1: Rebuild Docker container**

```bash
podman compose down -v && podman compose up -d --build
```

- [x] **Step 2: Verify the setup wizard in browser**

Navigate to http://localhost:8090/setup and confirm:
- Spinner shows during mDNS scan
- Results or hint text appears after ~5 seconds
- Manual IP entry works with verification checklist
- All 4 checks show pass/fail with correct icons
- Auto-advance works on all pass
- Retry and "Try a different scanner" buttons work on failure

- [x] **Step 3: Verify Settings page**

Navigate to http://localhost:8090/settings and confirm:
- Rescan Network button triggers discovery
- Scanner cards appear (or hint if nothing found)
- Clicking a card fills the IP field

- [x] **Step 4: Verify API endpoint**

```bash
curl -X POST http://localhost:8090/api/scanner/discover | python3 -m json.tool
```

Expected: JSON with `scanners` array, `count`, and `hint` (null or the networking explanation).

- [x] **Step 5: Push and create PR**

```bash
git push -u origin <branch>
gh pr create --title "feat: mDNS scanner discovery with verification checklist" --body "..."
```

- [x] **Step 6: Squash merge and cleanup**

```bash
gh pr merge <number> --squash --delete-branch
git checkout main && git pull --rebase
```
