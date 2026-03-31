# Development Environments

ScanBox runs in three environments. Use the right one for the right task.

## Local (this machine)

**When:** Feature development, debugging, unit tests, integration tests, writing code.

```bash
# Start server
INTERNAL_DATA_DIR=/tmp/scanbox-dev OUTPUT_DIR=/tmp/scanbox-output \
  .venv/bin/uvicorn scanbox.main:app --port 8090

# Run tests
pytest                                    # 835 tests, mocked LLM
pytest tests/integration/test_e2e_pipeline.py  # with real OCR (needs ocrmypdf)

# E2E with local LLM
OPENAI_API_BASE=http://192.168.10.95:11434/v1 OPENAI_API_KEY=mlx-local \
  LLM_MODEL=openai/mlx-community/Qwen3.5-35B-A3B-4bit LLM_PROVIDER=openai \
  pytest tests/integration/test_e2e_pipeline.py -k "FullPipelineWithLLM"

# Import test fixture (no scanner needed)
curl -X POST -F fronts=@tests/fixtures/test_suite/06-minimal-quick/fronts.pdf \
  http://localhost:8090/api/batches/import
```

**Has:** Full source code, test fixtures, all dev dependencies, ocrmypdf, local LLM access.
**Doesn't have:** Physical scanner, DNS resolution for `scanbox.blueshift.xyz`.

## CI (GitHub Actions)

**When:** Automated on every push/PR. Lint, test, Docker build, coverage gate.

**What runs:**
- `ruff check + format` (Lint job)
- `pytest` with coverage >= 85% (Test job) — includes OCR tests (tesseract installed)
- Docker image build (Docker Build job)
- Conventional commit title validation (PR only)

**Has:** tesseract, ghostscript, poppler, full test suite, committed fixture PDFs.
**Doesn't have:** LLM (tests that need it skip), scanner, production data.

## Production (scanbox.blueshift.xyz)

**When:** Real-world validation, deployment smoke tests, real scanner integration, dogfooding.

**Access:**
- URL: `https://scanbox.blueshift.xyz`
- Host: bighead (Podman, Komodo-managed)
- API key required for all endpoints except `/api/health`
- Health check: `curl https://scanbox.blueshift.xyz/api/health` (no auth)
- Authenticated: `curl -H "Authorization: Bearer $SCANBOX_API_KEY" https://scanbox.blueshift.xyz/api/...`

**Deploy:**
```bash
# From homelab or Komodo:
komodo-api build-run scanbox          # Build from GitHub main
komodo-api stack-destroy scanbox      # Tear down
komodo-api stack-deploy scanbox       # Deploy
komodo-api stack-services scanbox     # Verify
```

**Has:** Real scanner (HP M283cdw), real LLM (Qwen3.5-35B on Mac Mini), PaperlessNGX, API key auth, MCP enabled.
**Doesn't have:** Dev dependencies, test fixtures, pytest.

## When to Use What

| Task | Environment |
|------|------------|
| Write code, run tests | Local |
| Verify CI passes | CI (automatic) |
| Test with real scanner | Production |
| Test with real LLM locally | Local + `OPENAI_API_BASE` env vars |
| Validate deployment after merge | Production (build + deploy + smoke test) |
| Compare LLM models | Local (comparison tool) or Production (if testing with scanner data) |
| Debug pipeline issues | Local (import production batch data via API) |
| Check production logs | Loki via Grafana on homelab |

## Cross-Environment Workflows

**After shipping a PR:**
1. CI verifies automatically (lint + test + Docker build)
2. Deploy to production: `komodo-api build-run scanbox && komodo-api stack-destroy scanbox && komodo-api stack-deploy scanbox`
3. Smoke test: `curl https://scanbox.blueshift.xyz/api/health`

**Debugging a production issue:**
1. Check production logs (Loki/Grafana)
2. Export the problematic batch's PDFs from production
3. Import into local dev: `curl -X POST -F fronts=@exported.pdf http://localhost:8090/api/batches/import`
4. Debug locally with full tooling
5. Fix, test, push, deploy

**Testing scanner integration:**
1. Develop feature locally with test fixtures
2. Push to main, deploy to production
3. Scan real documents on production
4. Verify pipeline results via production UI or API
