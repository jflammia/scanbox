# Scanner Discovery Redesign

Replaces the unreliable HTTP subnet probe with proper mDNS/DNS-SD discovery using python-zeroconf. Adds verification checklist UX, container networking documentation, rescan capability, and MCP tool integration.

## Background

eSCL (AirScan) scanners advertise themselves via mDNS using service types `_uscan._tcp.local.` (HTTP) and `_uscans._tcp.local.` (HTTPS). The previous implementation probed 1500+ IPs across common subnets with short timeouts — slow, unreliable, and fundamentally the wrong approach.

### Container Networking Constraint

mDNS uses multicast UDP on port 5353 to group 224.0.0.251. Container networking handles this differently by platform:

| Platform | Network Mode | mDNS Works? | Why |
|----------|-------------|-------------|-----|
| **Linux** | `host` | Yes | Container shares host's physical interfaces |
| **Linux** | `macvlan` | Yes | Container gets its own MAC on the physical LAN |
| **Linux** | `bridge` (default) | No | Bridge filters multicast from the LAN |
| **macOS** | Any | No | Containers run in a Linux VM; multicast not forwarded from host into VM |
| **Windows** | Any | No | Same VM limitation as macOS |

**Recommendation:** Deploy on Linux with `network_mode: host` for automatic discovery. On macOS/Windows development setups, use manual IP entry.

## Discovery Service

### New Module: `scanbox/scanner/discovery.py`

```python
@dataclass
class DiscoveredScanner:
    ip: str
    port: int
    name: str           # mDNS service name
    model: str          # from TXT record "ty" field
    base_path: str      # from TXT record "rs" field (usually "eSCL")
    uuid: str           # from TXT record "UUID" field
    secure: bool        # True if discovered via _uscans._tcp

async def discover_scanners(timeout: float = 5.0) -> list[DiscoveredScanner]
```

Implementation:
- Creates `AsyncZeroconf(ip_version=IPVersion.V4Only)`
- Browses `_uscan._tcp.local.` and `_uscans._tcp.local.` with `AsyncServiceBrowser`
- Resolves each found service with `AsyncServiceInfo` to extract IP, port, and TXT record fields
- Waits for `timeout` seconds, then cancels browser and closes zeroconf
- Returns deduplicated list (by UUID) of found scanners
- Returns empty list if nothing found — no fallback, no subnet probe

### Dependency

Add to `pyproject.toml`:
```
"zeroconf>=0.140",
```

## API Endpoints

### New: `POST /api/scanner/discover`

Canonical discovery endpoint. Also serves as "rescan."

**Request:** Optional query param `timeout` (float, default 5.0, max 30.0)

**Response (200):**
```json
{
  "scanners": [
    {
      "ip": "192.168.10.11",
      "port": 80,
      "model": "HP Color LaserJet MFP M283cdw",
      "name": "HP Color LaserJet MFP M283cdw._uscan._tcp.local.",
      "uuid": "1c852a4d-b800-1f08-abcd-843497f7816c",
      "secure": false
    }
  ],
  "count": 1,
  "hint": null
}
```

**Response when empty (200):**
```json
{
  "scanners": [],
  "count": 0,
  "hint": "No scanners found. Automatic discovery uses mDNS, which requires the container to have direct LAN access (Linux with network_mode: host or macvlan). On macOS or standard Docker bridge networking, enter the scanner's IP address manually. You can find it in your scanner's network settings or your router's device list."
}
```

### New: `POST /setup/verify-scanner` (HTML)

Runs 4-step verification checklist on a scanner IP, returns HTML with results.

**Form param:** `scanner_ip`

**Verification checks (sequential):**
1. **Reaching scanner** — TCP connect to IP on port 80 (default eSCL port)
2. **eSCL protocol** — `GET /eSCL/ScannerStatus` returns 200
3. **Scanner capabilities** — `GET /eSCL/ScannerCapabilities` parses, has ADF
4. **Scanner ready** — Status is Idle

**HTML response — all pass:**
```html
<div class="space-y-2">
  <div class="flex items-center gap-2">
    <span class="text-status-success">✓</span> Reaching scanner
  </div>
  <div class="flex items-center gap-2">
    <span class="text-status-success">✓</span> eSCL protocol
  </div>
  <div class="flex items-center gap-2">
    <span class="text-status-success">✓</span> Scanner capabilities (ADF supported)
  </div>
  <div class="flex items-center gap-2">
    <span class="text-status-success">✓</span> Scanner ready
  </div>
  <p class="text-status-success font-semibold mt-3">
    Connected to HP Color LaserJet MFP M283cdw at 192.168.10.11
  </p>
</div>
<!-- Alpine.js auto-advance trigger -->
<div x-init="setTimeout(() => step = 2, 1500)"></div>
```

**HTML response — partial failure:**
```html
<div class="space-y-2">
  <div class="flex items-center gap-2">
    <span class="text-status-success">✓</span> Reaching scanner
  </div>
  <div class="flex items-center gap-2">
    <span class="text-status-success">✓</span> eSCL protocol
  </div>
  <div class="flex items-center gap-2">
    <span class="text-status-error">✗</span> Scanner capabilities
    <span class="text-sm text-text-muted">— No document feeder (ADF) detected</span>
  </div>
</div>
<div class="flex gap-3 mt-4">
  <button type="submit" class="...">Retry</button>
  <button type="button" @click="..." class="...">Try a different scanner</button>
</div>
```

On full success, saves `scanner_ip` to `runtime.json` before returning.

### Updated: `POST /setup/discover-scanners` (HTML)

Thin HTML wrapper around the discovery service. Returns scanner cards or the container networking hint. No longer does subnet probing.

### Kept Unchanged
- `POST /setup/test-scanner` (HTML) — saves IP, tests connectivity
- `POST /api/setup/test-scanner` (JSON) — tests configured scanner
- `GET /api/scanner/status` — scanner status
- `GET /api/scanner/capabilities` — scanner capabilities

## MCP Tools

### New: `scanbox_discover_scanners`

```
Tool: scanbox_discover_scanners
Description: Scan the local network for eSCL/AirScan compatible scanners using mDNS discovery.
Parameters:
  timeout (float, optional): How long to listen for scanner advertisements (default 5.0, max 30.0)
Returns:
  scanners: list of {ip, port, model, name, uuid, secure}
  count: number found
  hint: explanation if none found (container networking info)
```

### Updated Tools

**`scanbox_setup_guide`** — Step 1 text updated:
- Mentions `scanbox_discover_scanners` tool for automatic discovery
- Explains: mDNS works on Linux with `network_mode: host`; manual IP needed on macOS/bridge
- Recommends checking scanner's web admin page for its IP

**`scanbox_diagnose_system`** — When scanner is "not configured":
- Hint suggests running `scanbox_discover_scanners` or setting IP via Settings page

**`scanbox_get_scanner_status`** — When not configured:
- Adds actionable hint about discovery tool and manual IP entry

### Hint Text (shared constant)

Used across API JSON responses, MCP tool returns, and UI display:

> "Automatic scanner discovery uses mDNS, which requires the container to have direct LAN access (Linux with `network_mode: host` or macvlan). On macOS or standard Docker bridge networking, enter the scanner's IP address manually. You can find it in your scanner's network settings or your router's device list."

## UI Changes

### Setup Wizard Step 1

**Layout:**
1. Printer icon + "Find your scanner"
2. Discovery area: shows spinner during scan, then scanner cards or hint message
3. Manual IP entry field with "Verify" button
4. Verification checklist area (appears after verify)
5. "Skip for now" secondary action

**Behavior:**
- On page load: triggers `POST /setup/discover-scanners` (htmx `hx-trigger="load"`)
- Discovered scanners shown as clickable cards (name + model + IP)
- Clicking a card fills the IP field and submits the verify form
- Manual IP entry + "Verify" button submits to `POST /setup/verify-scanner`
- Verification checklist renders inline with pass/fail indicators
- On all checks pass: auto-advance to Step 2 after 1.5s
- On failure: show Retry and "Try a different scanner" buttons
- "Rescan Network" button re-triggers discovery

### Settings Page Scanner Section

**Layout:**
1. Scanner IP input field (pre-filled if configured)
2. "Save" button (existing)
3. "Rescan Network" button (new) — triggers discovery, shows results inline
4. Discovery results area (scanner cards, same as setup wizard)

Clicking a discovered scanner fills the IP field. Save button persists to runtime.json.

## Documentation Updates

### `docs/design.md`

Add "Scanner Discovery" subsection under Scanner Communication:
- mDNS/DNS-SD service types (`_uscan._tcp`, `_uscans._tcp`)
- TXT record fields used (ty, rs, UUID, is, duplex)
- Container networking constraint table (same as this spec)
- Recommended deployment: Linux + `network_mode: host`

### `docs/api-spec.md`

Add `POST /api/scanner/discover` endpoint:
- Request/response examples
- `hint` field documentation
- Note about container networking

### `docs/mcp-server.md`

Add `scanbox_discover_scanners` tool:
- Description, parameters, return format
- Example response with found scanner
- Example response with hint (nothing found)

## Testing

### New Tests

**`tests/unit/test_discovery.py`:**
- Mock `AsyncZeroconf` and `AsyncServiceBrowser`
- Test: found scanners → correct `DiscoveredScanner` list with parsed TXT fields
- Test: no scanners found → empty list
- Test: timeout respected
- Test: deduplication by UUID

**`tests/unit/test_verify_scanner.py`** (or in existing test files):
- Mock ESCLClient for each verification step
- Test: all 4 checks pass → success HTML + runtime.json saved
- Test: TCP unreachable → fail at step 1, steps 2-4 not attempted
- Test: eSCL not responding → pass step 1, fail step 2
- Test: no ADF → pass steps 1-2, fail step 3
- Test: scanner busy → pass steps 1-3, fail step 4

**`tests/integration/test_scanner_discover_api.py`:**
- Mock discovery service at the API layer
- Test: `POST /api/scanner/discover` → JSON response shape
- Test: empty results include `hint` field
- Test: `timeout` parameter clamped to max 30

### Updated Tests

- Setup wizard HTML tests — update assertions for new Step 1 structure (discovery area, verify form, checklist)
- MCP tool tests — add `scanbox_discover_scanners` if MCP tools have test coverage

### Unchanged

- ESCLClient unit tests
- Scanning pipeline tests
- Scanner status/capabilities API tests

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `scanbox/scanner/discovery.py` | **New** | mDNS discovery service |
| `scanbox/api/setup.py` | **Modify** | Replace subnet probe with zeroconf, add verify-scanner |
| `scanbox/api/scanner.py` | **Modify** | Add `POST /api/scanner/discover` |
| `scanbox/mcp/server.py` | **Modify** | Add discover tool, update hints in 3 tools |
| `scanbox/templates/setup.html` | **Modify** | Rewrite Step 1 with discovery + verification checklist |
| `scanbox/templates/settings.html` | **Modify** | Add Rescan Network button |
| `pyproject.toml` | **Modify** | Add `zeroconf>=0.140` |
| `docs/design.md` | **Modify** | Add Scanner Discovery section |
| `docs/api-spec.md` | **Modify** | Add discover endpoint docs |
| `docs/mcp-server.md` | **Modify** | Add discover tool docs |
| `tests/unit/test_discovery.py` | **New** | Discovery service tests |
| `tests/` (various) | **Modify** | Update setup wizard + verify tests |

## Out of Scope

- Scanning pipeline changes (fronts/backs acquisition is unaffected)
- ESCLClient protocol changes
- Scanner capabilities/status API changes
- Any UI changes outside Step 1 and Settings scanner section
