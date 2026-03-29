<div align="center">

# ScanBox

**Scan, split, and organize stacks of documents — from your browser, your AI agent, or a script.**

[![CI](https://github.com/jflammia/scanbox/actions/workflows/ci.yml/badge.svg)](https://github.com/jflammia/scanbox/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)](https://github.com/jflammia/scanbox/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)

</div>

---

ScanBox is a self-hosted web app that turns a network scanner into a hands-free document digitization station. Load paper, click scan (or tell your AI agent to), and ScanBox handles the rest — interleaving duplex pages, removing blanks, OCR, AI-powered document splitting, professional naming, and organized filing.

Built for scanning hundreds of medical records, tax documents, or any mixed stack where you don't know where one document ends and the next begins.

## Three Interfaces, One Engine

| Interface | For | How |
|-----------|-----|-----|
| **REST API** | Scripts, automation, external tools | Full CRUD at `/api/*`. OpenAPI docs at `/api/docs` |
| **MCP Server** | AI agents (Claude, etc.) | 17 native tools: `scanbox_scan_fronts`, `scanbox_list_documents`, etc. |
| **Web UI** | Humans | Wizard-guided scanning at `http://localhost:8090` |

All three share the same backend. Anything you can do in the browser, you can do from curl or Claude.

## How It Works

1. **Load paper** in your scanner's document feeder
2. **Scan** — from the web UI, an API call, or an AI agent
3. **Flip the stack** if double-sided, scan backs
4. ScanBox **processes everything** automatically:
   - Interleaves front and back pages into correct order
   - Removes blank pages
   - OCR — extracts all text
   - AI splits the stack into individual documents
   - Names each file: `2025-06-15_John-Doe_Radiology-Report_Memorial-Hospital.pdf`
5. **Review** — fix anything the AI got wrong
6. **Save** — organized PDFs in your output folder, optionally uploaded to PaperlessNGX

## Quick Start

```bash
git clone https://github.com/jflammia/scanbox.git
cd scanbox
cp .env.example .env    # set SCANNER_IP and LLM provider
docker compose up       # http://localhost:8090
```

The setup wizard walks you through connecting your scanner and LLM on first run.

## Configuration

All settings via environment variables in `.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `SCANNER_IP` | Yes | IP address of your eSCL/AirScan scanner |
| `LLM_PROVIDER` | Yes | `anthropic`, `openai`, or `ollama` |
| `ANTHROPIC_API_KEY` | If anthropic | API key |
| `OPENAI_API_KEY` | If openai | API key |
| `OLLAMA_URL` | If ollama | Server URL (default: `http://localhost:11434`) |
| `OUTPUT_DIR` | No | Output folder (default: `./output`) |
| `PAPERLESS_URL` | No | PaperlessNGX instance URL |
| `PAPERLESS_API_TOKEN` | No | PaperlessNGX API token |
| `SCANBOX_API_KEY` | No | Bearer token auth (off by default) |
| `MCP_ENABLED` | No | Enable MCP server at `/mcp` |
| `WEBHOOK_URL` | No | URL for event notifications |

## API

```bash
# Create a person and session
curl -X POST localhost:8090/api/persons -d '{"display_name": "John Doe"}'
curl -X POST localhost:8090/api/sessions -d '{"person_id": "john-doe"}'

# Scan
curl -X POST localhost:8090/api/batches/{id}/scan/fronts

# Review results
curl localhost:8090/api/batches/{id}/documents

# Save
curl -X POST localhost:8090/api/batches/{id}/save
```

Interactive docs: `http://localhost:8090/api/docs`

## MCP Integration

Add ScanBox to your AI agent config:

```json
{
  "mcpServers": {
    "scanbox": {
      "command": "docker",
      "args": ["exec", "-i", "scanbox", "python", "-m", "scanbox.mcp"],
      "env": { "MCP_ENABLED": "true" }
    }
  }
}
```

17 tools, 2 resources, 2 prompts. See [`docs/mcp-server.md`](docs/mcp-server.md).

## Output Structure

```
output/
├── archive/                     # Raw scan backup
│   └── john-doe/2026-03-28/
│       └── batch-001-combined.pdf
└── medical-records/             # Organized for sharing
    └── John_Doe/
        ├── Index.csv
        ├── Radiology Reports/
        │   └── 2025-06-15_John-Doe_Radiology-Report_Memorial-Hospital.pdf
        ├── Lab Results/
        └── ...
```

## Privacy

Everything runs locally. Only OCR text (not images or PDFs) is sent to the LLM for document splitting. Use Ollama for fully offline operation.

## Scanner Compatibility

ScanBox uses the **eSCL** (Apple AirScan) protocol — an industry standard. If your scanner works with AirScan or Mopria, it works with ScanBox. No drivers needed.

**Tested with:** HP Color LaserJet MFP M283cdw

## Architecture

```
┌──────────┬──────────┬──────────┐
│  Web UI  │ AI Agent │ Scripts  │
│ (htmx)   │ (MCP)    │ (curl)   │
└────┬─────┴────┬─────┴────┬─────┘
     ▼          ▼          ▼
┌─────────────────────────────────┐
│  FastAPI · REST · SSE · MCP     │
├─────────────────────────────────┤
│  Pipeline: Interleave → Blanks  │
│  → OCR → AI Split → Name → Save│
├─────────────────────────────────┤
│  SQLite · Checkpointing         │
└────┬──────────┬──────────┬──────┘
     ▼          ▼          ▼
  Scanner    Output     Paperless
  (eSCL)     (volume)   (optional)
```

**Tech stack:** Python 3.13, FastAPI, htmx, Alpine.js, Tailwind CSS, pikepdf, ocrmypdf, litellm, aiosqlite.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
bash .githooks/setup.sh                          # git hooks + rebase config
brew install tesseract poppler ghostscript        # macOS system deps
python -m tests.generate_fixtures                 # test PDFs

pytest                      # 532 tests, 94% coverage
pytest tests/unit/ -v       # unit tests
pytest tests/integration/   # integration tests
ruff format scanbox/ tests/ # format
ruff check scanbox/ tests/  # lint
```

CI enforces 85% minimum coverage, lint, format, and Docker build on every push.

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/design.md`](docs/design.md) | Authoritative design spec |
| [`docs/api-spec.md`](docs/api-spec.md) | REST API reference |
| [`docs/mcp-server.md`](docs/mcp-server.md) | MCP server tools and resources |
| [`docs/ui-spec.md`](docs/ui-spec.md) | UI components and layouts |
| [`CLAUDE.md`](CLAUDE.md) | AI agent development guide |

## License

[MIT](LICENSE)
