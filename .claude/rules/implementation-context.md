# Implementation Context

Decisions, constraints, and gotchas that aren't obvious from reading the code or specs. This file supplements `CLAUDE.md` with deeper technical context.

## Project Origin

Designed on 2026-03-28 by the project owner (Justin) and Claude. All three implementation phases are complete. The design went through multiple rounds of feedback — key decisions below were debated and settled.

## Hardware Constraints

- **HP Color LaserJet MFP M283cdw** — the target scanner
- ADF is **simplex only** for scanning (duplex is print-only). The two-pass workflow is a hardware limitation, not a design choice.
- eSCL (Apple AirScan) protocol — HTTP REST with XML. No drivers needed.
- ADF max resolution: **300 DPI** (sufficient for OCR)
- eSCL has **no authentication** — anyone on the LAN can start a scan
- WebScan may need enabling in the printer's EWS settings

## Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| **API-first** | REST API is primary. Web UI and MCP consume it. Enables AI agents, scripts, and external tools. |
| **MCP server** | Native tool calls for Claude and other MCP clients. 17 tools covering full workflow. |
| **Webhooks** | `scan.completed`, `processing.completed`, `save.completed` events for automation. |
| **Optional API auth** | `SCANBOX_API_KEY` bearer token. Off by default for local use. |
| **Two storage volumes** | Internal (Docker volume) persists even if output drive disconnects. Output (user-mounted) is the shareable result. |
| **PaperlessNGX via REST API** | Not filesystem consumption. Cleaner — no shared mount, direct metadata setting, upload confirmation. |
| **SQLite** | Single-user app. No concurrency concerns. aiosqlite is sufficient. |
| **Server-rendered** | htmx + Jinja2 is simpler than a SPA. No JS build step. |
| **Self-hosted assets** | htmx and Alpine.js vendored locally. No CDN dependencies. |

## UX Decisions

- **No modes or toggles.** Automation always runs. User corrects after.
- **One Save button.** Writes to all destinations at once.
- **Card layout** for results (not data table). Cards with thumbnails are more approachable.
- **Wizard pattern** for scanning — numbered steps with illustrations.
- **Plain English errors.** Never "eSCL protocol error." Say "Can't reach the scanner."
- **Practice run** — user learns by doing a real 1-15 page scan with behind-the-scenes validation.

## Technical Gotchas

### eSCL Protocol
- Endpoints at `http://{ip}/eSCL/...` — capital S, C, L
- ScannerCapabilities XML uses `scan:` and `pwg:` namespaces
- POST to ScanJobs → 201 with `Location` header containing job URL
- Loop GET on NextDocument until 404 (ADF empty)
- ADF doesn't report page count — you only know when it's empty
- Pages arrive one at a time — write to disk immediately for crash safety

### pikepdf
- 0-indexed pages internally; design spec uses 1-indexed. Convert at boundaries.
- `pdf.docinfo` uses PDF date format: `D:YYYYMMDDHHMMSS`
- XMP metadata via `pdf.open_metadata()` uses Dublin Core namespace
- **Must use `allow_overwriting_input=True`** when opening and saving to same file path (real bug found during testing)
- **Use `io.BytesIO`**, not `pikepdf.BytesIO` (doesn't exist — real bug found during testing)

### ocrmypdf
- `--skip-text` — don't re-OCR pages that already have text layers
- `--deskew` — corrects ADF rotation
- Command-line tool called via `subprocess.run`
- Requires `tesseract-ocr`, `ghostscript` (since v17), `poppler-utils` as system packages

### litellm
- `==1.82.6` exact pin — 1.82.7/1.82.8 were compromised (supply chain attack, March 24 2026)
- Model IDs differ by provider: `claude-haiku-4-5-20251001`, `gpt-4o-mini`, `ollama/llama3.1`
- `response_format={"type": "json_object"}` may not work with all Ollama models
- Use `litellm.acompletion()` for async in FastAPI context
- Module-level `config` import in `splitter.py` — must patch config object, not env vars

### Pillow/pdf2image
- `convert_from_path` requires `poppler-utils` (`pdftoppm`)
- 150 DPI sufficient for blank detection (saves memory vs 300)
- Blank threshold: 0.01 (1% ink coverage) handles scanner artifacts

### JSON Keys
- `text_by_page.json` uses string keys (`"1"`, `"2"`) since JSON doesn't support integer keys

### Lazy Imports
- Setup endpoints import ESCLClient, litellm, PaperlessClient inside function bodies
- Mock patches must target the **source module**, not the endpoint module

## System Dependencies

| Package | apt | brew | Purpose |
|---------|-----|------|---------|
| Tesseract | `tesseract-ocr tesseract-ocr-eng` | `tesseract` | OCR engine |
| Ghostscript | `ghostscript` | `ghostscript` | ocrmypdf >= 17 |
| Poppler | `poppler-utils` | `poppler` | PDF-to-image |
| libgl1 | `libgl1` | (macOS built-in) | Pillow |

## V1 Scope Boundaries

Explicitly out of scope:
- Barcode separators, multi-scanner, mobile UI, ntfy, EHR/Epic upload
- Document deduplication, heuristic splitting, custom routing
- Manual page reorder, reopening past sessions for new scans
- Per-field `*_source` tracking (simplified to boolean `user_edited`)
