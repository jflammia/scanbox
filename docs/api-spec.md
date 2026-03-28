# ScanBox REST API Specification

**Base URL:** `http://localhost:8090/api`
**Auto-generated docs:** `/api/docs` (Swagger UI) | `/api/redoc` (ReDoc) | `/api/openapi.json`

---

## Design Principles

1. **API-first.** The REST API is the primary interface. The web UI is one consumer. AI agents, scripts, and external tools use the same endpoints.
2. **RESTful.** Standard HTTP methods, JSON request/response bodies, meaningful status codes.
3. **OpenAPI-documented.** FastAPI auto-generates the OpenAPI spec. Interactive docs at `/api/docs`.
4. **SSE for real-time.** Long-running operations (scanning, processing) emit Server-Sent Events. Poll endpoints are also available for clients that don't support SSE.
5. **Optional auth.** Set `SCANBOX_API_KEY` to require bearer token authentication. Off by default for local use.

---

## Authentication

By default, no authentication is required (intended for local network use).

To enable API key authentication, set `SCANBOX_API_KEY` in your environment:

```bash
SCANBOX_API_KEY=your-secret-key
```

Then include the key in all requests:

```bash
curl -H "Authorization: Bearer your-secret-key" http://localhost:8090/api/health
```

---

## Common Patterns

### Pagination

List endpoints support cursor-based pagination:

```
GET /api/sessions?limit=20&offset=0
```

Response includes pagination metadata:

```json
{
  "items": [...],
  "total": 45,
  "limit": 20,
  "offset": 0
}
```

### Error Responses

All errors return a consistent JSON structure:

```json
{
  "error": "not_found",
  "message": "Batch abc123 not found",
  "detail": null
}
```

| Status Code | Meaning |
|-------------|---------|
| 400 | Bad request (invalid input) |
| 401 | Unauthorized (missing/invalid API key) |
| 404 | Resource not found |
| 409 | Conflict (e.g., scan already in progress) |
| 422 | Validation error (Pydantic) |
| 500 | Internal server error |

---

## Endpoints

### Health

#### `GET /api/health`

System health check and version info.

**Response:**

```json
{
  "status": "ok",
  "version": "0.0.1",
  "scanner": {
    "status": "idle",
    "ip": "192.168.10.11",
    "model": "HP Color LaserJet MFP M283cdw",
    "adf_loaded": true
  },
  "llm": {
    "provider": "anthropic",
    "model": "claude-haiku-4-5-20251001",
    "status": "ok"
  },
  "storage": {
    "internal": {"status": "ok", "path": "/app/data"},
    "output": {"status": "ok", "path": "/output"}
  },
  "mcp_enabled": false,
  "paperless_configured": true
}
```

---

### Persons

Person profiles represent the individuals whose documents are being scanned.

#### `GET /api/persons`

List all person profiles.

**Response:**

```json
{
  "items": [
    {
      "id": "john-doe",
      "display_name": "John Doe",
      "slug": "john-doe",
      "folder_name": "John_Doe",
      "created": "2026-03-28T08:00:00-04:00"
    }
  ]
}
```

#### `POST /api/persons`

Create a new person profile.

**Request:**

```json
{
  "display_name": "John Doe"
}
```

**Response:** `201 Created` with the person object.

#### `GET /api/persons/{person_id}`

Get a specific person profile.

#### `PUT /api/persons/{person_id}`

Update a person's display name.

#### `DELETE /api/persons/{person_id}`

Delete a person profile (only if they have no sessions).

---

### Sessions

A session represents one sitting where the user scans multiple batches for a person.

#### `GET /api/sessions`

List all sessions. Filter by `person_id` query parameter.

```bash
curl "http://localhost:8090/api/sessions?person_id=john-doe"
```

**Response:**

```json
{
  "items": [
    {
      "id": "sess-abc123",
      "person_id": "john-doe",
      "person_name": "John Doe",
      "batch_count": 3,
      "document_count": 12,
      "state": "saved",
      "created": "2026-03-28T10:00:00-04:00"
    }
  ]
}
```

#### `POST /api/sessions`

Create a new scanning session.

**Request:**

```json
{
  "person_id": "john-doe"
}
```

**Response:** `201 Created` with session object including its first batch ID.

#### `GET /api/sessions/{session_id}`

Get session details with all batches.

---

### Batches

A batch represents one stack of documents fed through the scanner.

#### `GET /api/batches/{batch_id}`

Get batch status and details.

**Response:**

```json
{
  "id": "batch-001",
  "session_id": "sess-abc123",
  "state": "review",
  "processing_stage": "done",
  "fronts_page_count": 47,
  "backs_page_count": 47,
  "document_count": 12,
  "created": "2026-03-28T10:05:00-04:00",
  "error_message": null
}
```

#### `POST /api/batches/{batch_id}/scan/fronts`

Trigger front-side scanning. The scanner's ADF begins feeding immediately.

**Response:** `202 Accepted`

```json
{
  "status": "scanning",
  "message": "Scanning front pages...",
  "progress_url": "/api/batches/batch-001/progress"
}
```

#### `POST /api/batches/{batch_id}/scan/backs`

Trigger back-side scanning.

#### `POST /api/batches/{batch_id}/skip-backs`

Skip back scanning (single-sided batch). Triggers processing immediately.

#### `POST /api/batches/{batch_id}/reprocess`

Reprocess the batch from raw scans. Re-runs the full pipeline without re-scanning.

#### `POST /api/batches/{batch_id}/save`

Save all documents to output destinations (archive, medical-records, PaperlessNGX).

**Response:**

```json
{
  "status": "saved",
  "archive_path": "/output/archive/john-doe/2026-03-28/batch-001-combined.pdf",
  "medical_records": [
    "/output/medical-records/John_Doe/Radiology Reports/2025-06-15_John-Doe_Radiology-Report_Memorial-Hospital_CT-Abdomen.pdf"
  ],
  "paperless_ids": [42, 43, 44],
  "index_csv": "/output/medical-records/John_Doe/Index.csv"
}
```

---

### Scanning Progress (SSE)

#### `GET /api/batches/{batch_id}/progress`

Server-Sent Events stream for real-time scanning and processing progress.

**SSE Events:**

```
event: progress
data: {"stage": "scanning", "pages_scanned": 23, "side": "fronts"}

event: progress
data: {"stage": "blank_removal", "pages_processed": 4, "total_pages": 47}

event: progress
data: {"stage": "ocr", "pages_processed": 31, "total_pages": 47}

event: progress
data: {"stage": "splitting", "status": "calling_llm"}

event: progress
data: {"stage": "naming", "documents_named": 12}

event: complete
data: {"stage": "done", "document_count": 12}
```

**Usage with curl:**

```bash
curl -N http://localhost:8090/api/batches/batch-001/progress
```

**Usage with Python:**

```python
import httpx

with httpx.stream("GET", "http://localhost:8090/api/batches/batch-001/progress") as r:
    for line in r.iter_lines():
        if line.startswith("data: "):
            print(line[6:])
```

---

### Documents

Documents are the individual split PDFs extracted from a batch.

#### `GET /api/batches/{batch_id}/documents`

List all documents in a batch.

**Response:**

```json
{
  "items": [
    {
      "id": "doc-001",
      "batch_id": "batch-001",
      "start_page": 1,
      "end_page": 3,
      "document_type": "Radiology Report",
      "date_of_service": "2025-06-15",
      "facility": "Memorial Hospital",
      "provider": "Dr. Michael Chen",
      "description": "CT Abdomen with Contrast",
      "confidence": 0.95,
      "user_edited": false,
      "filename": "2025-06-15_John-Doe_Radiology-Report_Memorial-Hospital_CT-Abdomen.pdf"
    }
  ]
}
```

#### `GET /api/documents/{document_id}`

Get a single document's metadata.

#### `PUT /api/documents/{document_id}`

Update document metadata (type, date, facility, provider, description).

**Request:**

```json
{
  "document_type": "Discharge Summary",
  "date_of_service": "2025-06-14",
  "facility": "Johns Hopkins Hospital",
  "description": "Post-Appendectomy"
}
```

Changes are persisted immediately. The `user_edited` flag is set to `true`.

#### `GET /api/documents/{document_id}/pdf`

Download the document PDF.

#### `GET /api/documents/{document_id}/thumbnail`

Get the document thumbnail (JPEG, 300px wide).

#### `GET /api/documents/{document_id}/text`

Get the OCR-extracted text for a document.

**Response:**

```json
{
  "pages": [
    {"page": 1, "text": "MEMORIAL HOSPITAL\nDepartment of Radiology\n..."},
    {"page": 2, "text": "IMPRESSION:\n1. No evidence of acute appendicitis.\n..."}
  ]
}
```

---

### Document Boundaries

#### `GET /api/batches/{batch_id}/boundaries`

Get current document split boundaries.

**Response:**

```json
{
  "total_pages": 47,
  "boundaries": [
    {"document_id": "doc-001", "start_page": 1, "end_page": 3},
    {"document_id": "doc-002", "start_page": 4, "end_page": 5},
    {"document_id": "doc-003", "start_page": 6, "end_page": 12}
  ]
}
```

#### `PUT /api/batches/{batch_id}/boundaries`

Update document split boundaries. Re-runs naming for affected documents.

**Request:**

```json
{
  "boundaries": [
    {"start_page": 1, "end_page": 4},
    {"start_page": 5, "end_page": 5},
    {"start_page": 6, "end_page": 12}
  ]
}
```

---

### Page Thumbnails

#### `GET /api/batches/{batch_id}/pages/{page_num}/thumbnail`

Get a thumbnail for a specific page (used by the boundary editor).

---

### Scanner

#### `GET /api/scanner/status`

Get current scanner status.

**Response:**

```json
{
  "status": "idle",
  "ip": "192.168.10.11",
  "model": "HP Color LaserJet MFP M283cdw",
  "adf_loaded": true,
  "message": "Scanner ready"
}
```

#### `GET /api/scanner/capabilities`

Get scanner capabilities (resolution, formats, ADF support).

---

### Setup

#### `GET /api/setup/status`

Check if first-run setup is complete.

#### `POST /api/setup/test-scanner`

Test scanner connectivity.

#### `POST /api/setup/test-llm`

Test LLM provider connectivity.

#### `POST /api/setup/test-paperless`

Test PaperlessNGX connectivity.

#### `POST /api/setup/complete`

Mark setup as complete.

---

### Webhooks

Register URLs to receive event notifications.

#### `GET /api/webhooks`

List registered webhooks.

#### `POST /api/webhooks`

Register a new webhook.

**Request:**

```json
{
  "url": "https://example.com/hooks/scanbox",
  "events": ["processing.completed", "save.completed"],
  "secret": "optional-hmac-secret"
}
```

#### `DELETE /api/webhooks/{webhook_id}`

Remove a webhook.

#### Webhook Payload Format

All webhook deliveries use this envelope:

```json
{
  "event": "processing.completed",
  "timestamp": "2026-03-28T10:15:00Z",
  "data": {
    "batch_id": "batch-001",
    "session_id": "sess-abc123",
    "person_name": "John Doe",
    "document_count": 12,
    "documents": [
      {
        "id": "doc-001",
        "type": "Radiology Report",
        "date": "2025-06-15",
        "description": "CT Abdomen with Contrast",
        "confidence": 0.95
      }
    ]
  }
}
```

The `X-Webhook-Signature` header contains an HMAC-SHA256 signature if a secret was provided.

---

## Integration Examples

### Python (httpx)

```python
import httpx

base = "http://localhost:8090/api"

# Create a session and scan
person = httpx.post(f"{base}/persons", json={"display_name": "John Doe"}).json()
session = httpx.post(f"{base}/sessions", json={"person_id": person["id"]}).json()
batch_id = session["batches"][0]["id"]

# Trigger scan
httpx.post(f"{base}/batches/{batch_id}/scan/fronts")

# Wait for completion (poll)
import time
while True:
    batch = httpx.get(f"{base}/batches/{batch_id}").json()
    if batch["state"] in ("review", "error"):
        break
    time.sleep(2)

# Review documents
docs = httpx.get(f"{base}/batches/{batch_id}/documents").json()
for doc in docs["items"]:
    print(f"{doc['document_type']}: {doc['description']} ({doc['date_of_service']})")

# Save
httpx.post(f"{base}/batches/{batch_id}/save")
```

### Shell (curl)

```bash
BASE="http://localhost:8090/api"

# Create person and session
PERSON=$(curl -s -X POST "$BASE/persons" \
  -H "Content-Type: application/json" \
  -d '{"display_name": "John Doe"}')

PERSON_ID=$(echo "$PERSON" | jq -r '.id')

SESSION=$(curl -s -X POST "$BASE/sessions" \
  -H "Content-Type: application/json" \
  -d "{\"person_id\": \"$PERSON_ID\"}")

BATCH_ID=$(echo "$SESSION" | jq -r '.batches[0].id')

# Scan fronts
curl -X POST "$BASE/batches/$BATCH_ID/scan/fronts"

# Skip backs (single-sided)
curl -X POST "$BASE/batches/$BATCH_ID/skip-backs"

# Check documents
curl -s "$BASE/batches/$BATCH_ID/documents" | jq '.items[].document_type'

# Save
curl -X POST "$BASE/batches/$BATCH_ID/save"
```

---

## Document Types

The following document types are recognized by the AI splitting stage:

- Radiology Report
- Discharge Summary
- Care Plan
- Lab Results
- Letter
- Operative Report
- Progress Note
- Pathology Report
- Prescription
- Insurance
- Billing
- Other

See `docs/design.md` "Stage 4" for the full AI prompt and validation rules.
