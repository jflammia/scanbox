# ScanBox MCP Server Specification

ScanBox exposes a **Model Context Protocol (MCP)** server that enables AI agents to interact with every scanning capability through native tool calls.

---

## Overview

The MCP server makes ScanBox a first-class tool in any MCP-compatible AI workflow. An AI agent can:

- Create sessions and trigger scans
- Monitor scanning and processing progress
- Review extracted documents and correct metadata
- Adjust document split boundaries
- Save results to all output destinations
- Query past sessions and documents
- Check system health and scanner status

This is the same business logic as the REST API — the MCP server delegates to the API layer, not duplicate implementations.

---

## Configuration

### Enable

Set the environment variable:

```bash
MCP_ENABLED=true
```

The MCP server starts alongside the REST API when the application launches.

### Transport

| Transport | Use Case | Configuration |
|-----------|----------|---------------|
| **stdio** | Local use via `docker exec` or Claude Desktop | Default when invoked via `python -m scanbox.mcp` |
| **SSE** | Remote AI agents over HTTP | Available at `/mcp` when `MCP_ENABLED=true` |

---

## Integration Examples

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "scanbox": {
      "command": "docker",
      "args": ["exec", "-i", "scanbox", "python", "-m", "scanbox.mcp"]
    }
  }
}
```

Then you can ask Claude:

> "Scan the documents in the feeder and save them for John Doe."

Claude will use the MCP tools to create a session, trigger the scan, monitor progress, review results, and save.

### Claude Code

From a Claude Code session with access to the ScanBox host:

```bash
# The MCP server is available as a tool when configured
claude --mcp-server "docker exec -i scanbox python -m scanbox.mcp"
```

### Any MCP Client

Connect to the SSE transport:

```
MCP SSE endpoint: http://localhost:8090/mcp
```

---

## Tools

Tools are the actions an AI agent can perform. Each tool maps to one or more REST API endpoints.

### `scanbox_health_check`

Check system health — scanner connectivity, LLM availability, storage status.

**Input:** none

**Output:**

```json
{
  "status": "ok",
  "scanner": "idle",
  "llm": "ok",
  "storage": "ok"
}
```

---

### `scanbox_get_scanner_status`

Get the current scanner status with a human-readable message.

**Input:** none

**Output:**

```json
{
  "status": "idle",
  "adf_loaded": true,
  "message": "Scanner ready — paper loaded in ADF"
}
```

---

### `scanbox_manage_persons`

Create, list, or get person profiles.

**Input:**

```json
{
  "action": "create",
  "display_name": "John Doe"
}
```

Actions: `list`, `create`, `get`, `delete`

**Output:** Person object or list of persons.

---

### `scanbox_create_session`

Create a new scanning session for a person.

**Input:**

```json
{
  "person_id": "john-doe"
}
```

**Output:**

```json
{
  "session_id": "sess-abc123",
  "batch_id": "batch-001",
  "message": "Session created. Ready to scan front pages."
}
```

---

### `scanbox_list_sessions`

List all scanning sessions, optionally filtered by person.

**Input:**

```json
{
  "person_id": "john-doe"
}
```

All fields optional.

**Output:** List of session summaries.

---

### `scanbox_scan_fronts`

Start scanning front pages. The scanner's ADF begins feeding immediately.

**Input:**

```json
{
  "batch_id": "batch-001"
}
```

**Output:**

```json
{
  "status": "scanning",
  "message": "Scanning front pages. The scanner is feeding paper from the ADF."
}
```

---

### `scanbox_scan_backs`

Start scanning back pages (after the stack has been flipped).

**Input:**

```json
{
  "batch_id": "batch-001"
}
```

**Output:**

```json
{
  "status": "scanning",
  "message": "Scanning back pages."
}
```

---

### `scanbox_skip_backs`

Skip back-side scanning (single-sided documents). Triggers processing immediately.

**Input:**

```json
{
  "batch_id": "batch-001"
}
```

**Output:**

```json
{
  "status": "processing",
  "message": "Skipped backs. Processing your documents now."
}
```

---

### `scanbox_get_batch_status`

Get the current status and processing stage of a batch.

**Input:**

```json
{
  "batch_id": "batch-001"
}
```

**Output:**

```json
{
  "batch_id": "batch-001",
  "state": "processing",
  "processing_stage": "ocr",
  "fronts_page_count": 47,
  "backs_page_count": 47,
  "message": "Reading text from your documents (page 31 of 47)..."
}
```

---

### `scanbox_get_pipeline_status`

Get detailed pipeline progress for a batch being processed.

**Input:**

```json
{
  "batch_id": "batch-001"
}
```

**Output:**

```json
{
  "batch_id": "batch-001",
  "stage": "ocr",
  "progress": {
    "current_page": 31,
    "total_pages": 47,
    "percent": 66
  },
  "completed_stages": ["interleaving", "blank_removal"],
  "remaining_stages": ["splitting", "naming"]
}
```

---

### `scanbox_list_documents`

List all documents extracted from a batch.

**Input:**

```json
{
  "batch_id": "batch-001"
}
```

**Output:**

```json
{
  "documents": [
    {
      "id": "doc-001",
      "document_type": "Radiology Report",
      "date_of_service": "2025-06-15",
      "facility": "Memorial Hospital",
      "provider": "Dr. Michael Chen",
      "description": "CT Abdomen with Contrast",
      "pages": "1-3",
      "confidence": 0.95,
      "needs_review": false
    },
    {
      "id": "doc-004",
      "document_type": "Other",
      "date_of_service": "unknown",
      "facility": "unknown",
      "description": "Document",
      "pages": "10-12",
      "confidence": 0.4,
      "needs_review": true
    }
  ],
  "total": 12,
  "needs_review": 1
}
```

---

### `scanbox_get_document`

Get full details for a single document, including OCR text.

**Input:**

```json
{
  "document_id": "doc-001"
}
```

**Output:** Document metadata + first 500 characters of OCR text for context.

---

### `scanbox_update_document`

Update a document's metadata (type, date, facility, provider, description).

**Input:**

```json
{
  "document_id": "doc-004",
  "document_type": "Lab Results",
  "date_of_service": "2025-05-22",
  "facility": "Quest Diagnostics",
  "description": "Comprehensive Metabolic Panel"
}
```

Only provided fields are updated. Sets `user_edited = true`.

**Output:**

```json
{
  "status": "updated",
  "document_id": "doc-004",
  "message": "Updated document type, date, facility, and description."
}
```

---

### `scanbox_adjust_boundaries`

Adjust document split boundaries for a batch. Re-runs naming for affected documents.

**Input:**

```json
{
  "batch_id": "batch-001",
  "boundaries": [
    {"start_page": 1, "end_page": 4},
    {"start_page": 5, "end_page": 5},
    {"start_page": 6, "end_page": 12}
  ]
}
```

Boundaries must be contiguous, non-overlapping, and cover all pages.

**Output:**

```json
{
  "status": "updated",
  "document_count": 3,
  "message": "Split into 3 documents. Re-running naming."
}
```

---

### `scanbox_save_batch`

Save all documents to output destinations (archive, medical-records, PaperlessNGX).

**Input:**

```json
{
  "batch_id": "batch-001"
}
```

**Output:**

```json
{
  "status": "saved",
  "documents_saved": 12,
  "destinations": {
    "archive": "/output/archive/john-doe/2026-03-28/",
    "medical_records": "/output/medical-records/John_Doe/",
    "paperless": true,
    "index_csv": "/output/medical-records/John_Doe/Index.csv"
  },
  "message": "Saved 12 documents to archive, medical records, and PaperlessNGX."
}
```

---

### `scanbox_reprocess_batch`

Reprocess a batch from raw scans without re-scanning.

**Input:**

```json
{
  "batch_id": "batch-001"
}
```

**Output:**

```json
{
  "status": "processing",
  "message": "Reprocessing batch from saved scans."
}
```

---

## Resources

Resources are read-only data that agents can access for context.

### `scanbox://status`

Current system status (scanner, LLM, storage).

### `scanbox://sessions`

List of all scanning sessions with summary info.

### `scanbox://batches/{batch_id}`

Full batch details including state, page counts, and document list.

### `scanbox://documents/{document_id}`

Document metadata including type, date, facility, provider, description.

### `scanbox://documents/{document_id}/text`

Full OCR-extracted text for a document (all pages).

---

## Prompts

Prompts are pre-built workflows that agents can invoke for common tasks.

### `review_batch`

Review all documents in a batch and suggest corrections for any that need attention.

**Arguments:**

```json
{
  "batch_id": "batch-001"
}
```

**Generated prompt:** Lists all documents with their metadata and confidence scores, highlights any that need review (low confidence, missing dates, unknown types), and asks the agent to review each flagged document's OCR text and suggest corrections.

### `classify_document`

Help classify a document that the AI splitting stage couldn't confidently identify.

**Arguments:**

```json
{
  "document_id": "doc-004"
}
```

**Generated prompt:** Provides the document's OCR text and asks the agent to determine the document type, date of service, facility, provider, and description.

---

## Example Agent Workflow

A complete scan-review-save workflow using MCP tools:

```
Agent: Let me check if the scanner is ready.
→ scanbox_get_scanner_status
← Scanner idle, paper loaded

Agent: Creating a session for John Doe.
→ scanbox_create_session {"person_id": "john-doe"}
← Session created, batch_id: batch-001

Agent: Starting the front-side scan.
→ scanbox_scan_fronts {"batch_id": "batch-001"}
← Scanning started

Agent: Checking progress...
→ scanbox_get_batch_status {"batch_id": "batch-001"}
← scanning_fronts: 47 pages scanned

Agent: Fronts done. The user should flip the stack and reload.
→ scanbox_scan_backs {"batch_id": "batch-001"}
← Scanning backs

[... processing completes ...]

Agent: Let me review the extracted documents.
→ scanbox_list_documents {"batch_id": "batch-001"}
← 12 documents, 1 needs review

Agent: Document doc-004 has low confidence. Let me read its text.
→ scanbox_get_document {"document_id": "doc-004"}
← OCR text shows it's a lab result from Quest Diagnostics

Agent: Updating the metadata.
→ scanbox_update_document {"document_id": "doc-004", "document_type": "Lab Results", ...}
← Updated

Agent: Everything looks good. Saving all documents.
→ scanbox_save_batch {"batch_id": "batch-001"}
← Saved 12 documents to all destinations
```

---

## Implementation Notes

- Built on the `mcp` Python SDK
- MCP tools delegate to the same service layer as the REST API — no duplicate business logic
- The MCP server runs in the same process as FastAPI (shared database, pipeline, config)
- stdio transport is used when invoked via `python -m scanbox.mcp` (for Claude Desktop / docker exec)
- SSE transport is available at `/mcp` when running as part of the web server
- Tool responses include human-readable `message` fields so agents can relay status naturally
