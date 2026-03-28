# Implementation Context

This file captures decisions, constraints, and context from the design session that a fresh implementation agent needs to know. These are things that aren't obvious from reading the code or design spec alone.

## Project Origin

ScanBox was designed in a brainstorming session on 2026-03-28 between the project owner (Justin) and Claude. The design went through multiple rounds of feedback. Key decisions that were debated and settled:

### Scanner Hardware

- **HP Color LaserJet MFP M283cdw** — the specific scanner this was designed for
- The ADF is **simplex only** for scanning (duplex is print-only). This was confirmed via HP support docs and community forums. The two-pass workflow is not a design choice — it's a hardware limitation.
- The scanner supports **eSCL (Apple AirScan)** protocol — HTTP REST with XML payloads. This was verified via community reports and protocol documentation. No HP drivers needed.
- ADF max resolution is **300 DPI** (flatbed goes to 1200). 300 DPI is sufficient for OCR.
- eSCL has **no authentication**. Anyone on the LAN can start a scan. This is an HP limitation.
- WebScan may need to be enabled in the printer's EWS (Embedded Web Server) settings. The setup wizard should mention this.

### AI Splitting

- The AI prompt asks for JSON with specific fields. Different LLM providers may handle the `response_format={"type": "json_object"}` parameter differently. Test with your chosen provider.
- Claude Haiku and GPT-4o-mini are both good choices for speed/cost (~$0.02/batch of 50 pages).
- Ollama with Llama 3.1 or Mistral works for local/offline use but may be slower and less accurate.
- The **validation layer** is more important than the LLM call itself. If the LLM returns garbage, validation catches it. Build validation before worrying about prompt engineering.
- The LLM is called once per batch (all pages), not per document. This is a deliberate design choice for efficiency.

### Storage Design

- **Two separate volumes** was a deliberate choice. Internal storage (Docker volume) is the safety net — it persists even if the output drive is disconnected. Output storage (user-mounted) is the shareable result.
- PaperlessNGX is accessed via **REST API** (`POST /api/documents/post_document/`), not by dropping files in a consumption folder. This was a late design pivot — earlier versions used filesystem consumption. The API approach is cleaner (no shared filesystem mount needed, upload confirmation, direct metadata setting).
- The `created` field in the PaperlessNGX upload is critical — without it, all documents show as "today" instead of their actual date of service.

### UX Decisions

- **No modes, no toggles.** Automation always runs. The user corrects after. This was a deliberate simplification — earlier versions had a "Manual-First Mode" toggle that was cut.
- **One "Save" button.** Writes to all three destinations (archive, medical records, PaperlessNGX) at once. Earlier versions had separate export buttons — cut for simplicity.
- **Card layout, not data table** for results. Cards with PDF thumbnails are more approachable for non-technical users.
- **Wizard pattern** for scanning — numbered steps with illustrations. Not a dashboard.
- **Error messages must be plain English.** Never say "eSCL protocol error." Say "Can't reach the scanner. Is it turned on?"
- **In-app practice run** (not a separate test checklist) — the user learns the software by doing a real scan of 1-15 pages, with the app validating everything behind the scenes.

### Things That Were Explicitly Scoped Out (V1)

- Barcode separator sheets
- Multi-scanner support
- Mobile-responsive UI
- ntfy push notifications
- Direct EHR/Epic upload
- Document deduplication
- Heuristic-only splitting (without LLM)
- Per-field `*_source` tracking (simplified to boolean `user_edited`)
- Custom output routing per document (fixed paths)
- Manual page reorder for interleaving (re-scan backs instead)
- Reopening past sessions for new scans (view + correct only)

## Technical Gotchas

### eSCL Protocol

- eSCL endpoints are at `http://{ip}/eSCL/...` — note the capital S, C, L
- ScannerCapabilities XML has namespaces: `scan:` and `pwg:`
- When starting a scan job, the printer returns HTTP 201 with a `Location` header containing the job URL
- NextDocument returns the scanned page content. Loop until 404 (ADF empty).
- The ADF doesn't report how many pages are loaded — you only know when it's empty (404)
- Pages arrive one at a time. Each must be written to disk immediately for crash safety.

### pikepdf

- pikepdf uses 0-indexed pages internally, but the design spec uses 1-indexed page numbers (matching physical page numbering). Convert at the boundary.
- `pdf.docinfo` uses PDF-style date format: `D:YYYYMMDDHHMMSS`
- XMP metadata (via `pdf.open_metadata()`) uses Dublin Core namespace

### ocrmypdf

- `--skip-text` flag is important — don't re-OCR pages that already have a text layer
- `--deskew` corrects slightly rotated pages from the ADF
- ocrmypdf is a command-line tool, called via `subprocess.run`
- It requires `tesseract-ocr`, `ghostscript` (since v17), and `poppler-utils` as system packages

### litellm

- Model IDs differ by provider: `claude-haiku-4-5-20251001` (Anthropic), `gpt-4o-mini` (OpenAI), `ollama/llama3.1` (Ollama)
- `response_format={"type": "json_object"}` may not work with all Ollama models — add error handling
- Use `litellm.acompletion()` for async calls in the FastAPI context

### Pillow/pdf2image

- `convert_from_path` requires `poppler-utils` (the `pdftoppm` command)
- For blank detection, 150 DPI is sufficient (saves memory vs 300 DPI)
- Blank threshold of 0.01 (1% ink coverage) works well for scanner artifacts

## System Dependencies

These must be installed in the Docker image AND on the development machine:

| Package | apt Name | brew Name | Purpose |
|---------|----------|-----------|---------|
| Tesseract | `tesseract-ocr tesseract-ocr-eng` | `tesseract` | OCR engine |
| Ghostscript | `ghostscript` | `ghostscript` | Required by ocrmypdf >= 17 |
| Poppler | `poppler-utils` | `poppler` | PDF-to-image rendering |
| libgl1 | `libgl1-mesa-glx` | (included in macOS) | Pillow image processing |
