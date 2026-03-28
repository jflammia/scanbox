<div align="center">

# ScanBox

**Scan, split, and organize stacks of documents from your browser.**

[![CI](https://github.com/jflammia/scanbox/actions/workflows/ci.yml/badge.svg)](https://github.com/jflammia/scanbox/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

---

ScanBox is a self-hosted web app that turns a network scanner into a hands-free document digitization station. Load paper, click scan, and ScanBox handles the rest — interleaving duplex pages, removing blanks, OCR, AI-powered document splitting, professional naming, and organized filing.

Built for scanning hundreds of medical records, tax documents, or any mixed stack where you don't know where one document ends and the next begins.

> **Status:** Under active development. Not yet ready for production use.

## How It Works

1. **Load paper** in your scanner's document feeder
2. **Click "Scan"** in your browser — the scanner starts automatically
3. **Flip the stack** if pages are double-sided, click "Scan Backs"
4. **ScanBox processes everything** in the background:
   - Interleaves front and back pages
   - Removes blank pages
   - Reads all text (OCR)
   - Uses AI to figure out where each document starts and ends
   - Names each document with the date, type, and source
5. **Review the results** — fix anything the AI got wrong
6. **Save** — organized PDFs land in your output folder, ready to share

Your scanner's touchscreen is never used. Everything is controlled from the web UI.

## Features

- **Remote scanner control** via eSCL protocol (no drivers needed)
- **Two-pass duplex** workflow for simplex-only ADF scanners
- **AI document splitting** — detects boundaries between different documents in a mixed stack
- **Medical-professional naming** — `2025-06-15_John-Doe_Radiology-Report_Memorial-Hospital.pdf`
- **Multi-person support** — scan records for different people, kept separate
- **Human authority** — every AI decision is a suggestion you can override
- **Crash-safe** — every stage checkpoints to disk; nothing is lost if the app restarts
- **PaperlessNGX integration** (optional) — upload via API with tags, types, and dates
- **Any LLM provider** — Anthropic, OpenAI, or Ollama (local, fully offline)
- **Runs anywhere** — laptop, homelab server, or cloud VM

## Quick Start

```bash
git clone https://github.com/jflammia/scanbox.git
cd scanbox

# Configure (only 2 required settings)
cp .env.example .env
# Edit .env: set SCANNER_IP and your LLM provider

# Start
docker compose up

# Open http://localhost:8090
```

The first-run setup wizard walks you through connecting your scanner and (optionally) PaperlessNGX.

## Requirements

- **Docker** (or Podman)
- A **network scanner** that supports eSCL/AirScan (most modern HP, Canon, Epson, Brother)
- An **LLM provider** for document splitting:
  - Anthropic API key, or
  - OpenAI API key, or
  - Local [Ollama](https://ollama.com) instance (fully offline, no data leaves your network)

## Configuration

All configuration is via environment variables in `.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `SCANNER_IP` | Yes | IP address of your network scanner |
| `LLM_PROVIDER` | Yes | `anthropic`, `openai`, or `ollama` |
| `ANTHROPIC_API_KEY` | If provider=anthropic | Anthropic API key |
| `OPENAI_API_KEY` | If provider=openai | OpenAI API key |
| `OLLAMA_URL` | If provider=ollama | Ollama server URL (default: `http://localhost:11434`) |
| `PAPERLESS_URL` | No | PaperlessNGX instance URL |
| `PAPERLESS_API_TOKEN` | No | PaperlessNGX API token |
| `OUTPUT_DIR` | No | Output folder (default: `./output`) |

## Output Structure

```
output/
├── archive/                          # Raw scans (safety backup)
│   └── john-doe/2026-03-28/
│       └── batch-001-combined.pdf
└── medical-records/                  # Organized for sharing
    └── John_Doe/
        ├── Index.csv                 # Spreadsheet of all documents
        ├── Radiology Reports/
        │   └── 2025-06-15_John-Doe_Radiology-Report_Memorial-Hospital_CT-Abdomen.pdf
        ├── Discharge Summaries/
        ├── Lab Results/
        └── ...
```

Copy the `medical-records/John_Doe/` folder to a USB drive and hand it to a doctor's office.

## Privacy

ScanBox processes everything locally. The only data that leaves your network is OCR text sent to the LLM provider for document splitting (no images or PDFs are sent). Choose Ollama for fully offline operation.

| Provider | Data Leaves Network? |
|----------|---------------------|
| Ollama (local) | No |
| Anthropic | Text only |
| OpenAI | Text only |

## Scanner Compatibility

ScanBox communicates via the **eSCL** (Apple AirScan) protocol — an industry standard supported by most modern network scanners. If your scanner works with Apple's AirScan or Mopria, it works with ScanBox.

**Tested with:** HP Color LaserJet MFP M283cdw

## Development

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
brew install tesseract poppler   # macOS system deps
bash .githooks/setup.sh          # Git hooks

# Test
pytest                            # All tests
pytest tests/unit/ -v             # Unit tests

# Lint
ruff format scanbox/ tests/
ruff check scanbox/ tests/
```

Built with Python 3.13, FastAPI, htmx, Alpine.js, Tailwind CSS, pikepdf, ocrmypdf, and litellm.

See [CLAUDE.md](CLAUDE.md) for architecture details and contributing guidelines.

## License

[MIT](LICENSE)
