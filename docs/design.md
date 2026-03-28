# ScanBox: Self-Contained Medical Document Scanning Pipeline

**Date:** 2026-03-28
**Status:** Design
**Repository:** New standalone repo (`scanbox`)

---

## Problem

Hundreds of mixed medical documents (radiology reports, letters, discharge papers, care plans) need to be scanned, split into individual documents, named professionally, and archived for both long-term searchability (PaperlessNGX) and sharing with medical providers (Epic-compatible PDFs). The documents are mixed single/double-sided with unclear boundaries between documents.

## Solution

A self-contained Docker application with a web UI that:
1. Controls the HP M283cdw scanner directly via eSCL protocol (no Mac or drivers needed)
2. Guides the user through two-pass duplex scanning via the web UI
3. Automatically interleaves pages, removes blanks, OCRs, and AI-splits into individual documents
4. Names and organizes documents using medical-professional conventions
5. Archives originals and ingests split documents into PaperlessNGX via API

## Core Design Principle: Human Authority

**The human is always right. Automation is a suggestion.**

Every automated decision in ScanBox — AI document splitting, blank page detection, metadata extraction, document classification — is a **proposal** that the user can accept, modify, or completely override. The software never assumes it knows better than the person looking at the documents.

This is not a feature bolted onto an automated pipeline. It is the fundamental architecture:

### The Authority Model

```
┌────────────────────────────────────────────────────────┐
│                    Human Authority                      │
│                                                        │
│  The user can ALWAYS:                                  │
│  1. Override any automated decision                    │
│  2. Do the work manually instead of using automation   │
│  3. Mix automated + manual within the same batch       │
│  4. Change their mind after accepting a suggestion     │
│                                                        │
│  Automation exists to save time, not to make decisions.│
└────────────────────────────────────────────────────────┘
```

### How This Works In Practice

| What Happened | What The User Does |
|---------------|-------------------|
| AI split two documents as one | Tap between pages in the thumbnail strip to add a divider |
| AI split one document as two | Tap the divider between them to remove it |
| Wrong document type | Tap the card, pick the right type from the dropdown |
| Wrong date, facility, or provider | Tap the card, type the correct value |
| A real page was removed as "blank" | Tap "Bring back a removed page" — see thumbnails of removed pages, tap to restore |
| A blank page snuck through | Tap the page in the viewer, tap "Remove this page" |
| Interleaving is wrong (pages out of order) | Re-scan the backs. The system re-processes automatically. |

**No modes, no toggles, no settings.** Automation always runs. Corrections are always available. The user never has to choose an approach up front.

### Override Persistence

When a user corrects something:
1. **The correction sticks.** Re-processing the batch won't undo manual corrections.
2. **Corrections are visible.** Edited fields show a small "edited" indicator so you know what you've touched.
3. **You can undo corrections.** Every edited field has a "Reset to original" option if you change your mind.

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│                     Docker Container                       │
│                                                           │
│  ┌─────────────┐         ┌──────────────────────────┐     │
│  │  Web UI      │────────▶│  FastAPI Backend          │     │
│  │  (browser)   │◀────────│                          │     │
│  └─────────────┘   SSE   │  - Scanner control        │     │
│                          │  - Session management     │     │
│                          │  - Processing pipeline    │     │
│                          └─────┬──────────┬──────────┘     │
│                                │          │                │
│  ┌─────────────────────────────┼──────────┼──────────────┐ │
│  │          Processing Pipeline│          │              │ │
│  │                             │          │              │ │
│  │  Interleave → Blank Removal → OCR      │              │ │
│  │      → AI Split/Classify → Name → Save │              │ │
│  └─────────────────────────────────────────┼──────────────┘ │
│                                            │                │
│  ┌────────────────────┐  ┌────────────────────────────┐    │
│  │  Internal Storage   │  │  scanbox.db (SQLite)       │    │
│  │  /app/data          │  │  Sessions, batches, state  │    │
│  │  (Docker volume)    │  │                            │    │
│  └────────────────────┘  └────────────────────────────┘    │
└──────┬────────────────────────┬──────────────┬─────────────┘
       │ eSCL (HTTP)            │ Volume mount  │ REST API (HTTPS)
       ▼                        ▼               ▼
┌──────────────┐    ┌────────────────┐   ┌──────────────────┐
│ HP M283cdw   │    │ Output Storage │   │ PaperlessNGX     │
│ Scanner      │    │ (any folder,   │   │ (optional)       │
│              │    │  NAS mount,    │   │                  │
└──────────────┘    │  USB drive)    │   │ Upload via API:  │
                    └────────────────┘   │ - PDF + metadata │
       │                                 │ - Tags           │
       ▼                                 │ - Document type  │
┌──────────────┐                         │ - Created date   │
│ LLM Provider │                         └──────────────────┘
│ (Anthropic,  │
│ Ollama, etc) │
└──────────────┘
```

## Scanner Communication

### You Never Touch the Printer

ScanBox **fully controls the scanner remotely**. The only physical actions are loading and flipping paper. Everything else — starting scans, receiving pages, checking status — happens through the web UI.

| Human Action (Physical) | ScanBox Action (Automatic) |
|------------------------|---------------------------|
| Load paper in ADF tray | — |
| Click "Scan" in browser | Sends HTTP command to printer → ADF starts feeding pages |
| — | Receives each page as it's scanned, saves to disk in real time |
| — | Detects when ADF is empty (last page fed), stops automatically |
| Flip stack, reload ADF | — |
| Click "Scan Backs" in browser | Sends another HTTP command → ADF feeds again |
| — | Receives back pages, processes everything in background |

**The printer's touchscreen is never used.** You could tape over it.

### How It Works (eSCL Protocol)

The HP M283cdw supports eSCL (Apple AirScan) — a REST API over HTTP. ScanBox speaks this protocol natively. No HP drivers, no SANE, no host software.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/eSCL/ScannerCapabilities` | What the scanner can do (resolutions, formats, ADF support) |
| GET | `/eSCL/ScannerStatus` | Is it on? Idle or busy? Paper loaded? Cover open? |
| POST | `/eSCL/ScanJobs` | **Start scanning** — the printer's ADF begins feeding immediately |
| GET | `/eSCL/ScanJobs/{id}/NextDocument` | Retrieve each scanned page (loop until ADF is empty) |
| DELETE | `/eSCL/ScanJobs/{id}` | Cancel a scan in progress |

### Live Scanner Health

The web UI continuously monitors the printer and shows its status:

| Printer State | What the User Sees |
|---------------|-------------------|
| Online, idle, ADF loaded | Green indicator: "Scanner ready" |
| Online, idle, ADF empty | "Scanner ready — load pages to start" |
| Online, busy (scanning) | "Scanning... 23 pages so far" with animated progress |
| Offline / unreachable | Yellow warning: "Can't reach the scanner. Is it turned on?" |
| Error (paper jam, cover open) | "The scanner has a problem — check for a paper jam or open cover" |

Status is polled every few seconds via `GET /eSCL/ScannerStatus`. During an active scan, the poll rate increases for real-time page count updates.

### First-Run Scanner Setup

On first launch, ScanBox:
1. Connects to the printer at `SCANNER_IP`.
2. Reads its capabilities (`/eSCL/ScannerCapabilities`) — confirms ADF support, 300 DPI, PDF output.
3. Enables WebScan if needed (some HP printers require this in EWS settings — the setup guide explains how with a screenshot).
4. Verifies it can start and cancel a test job.

If anything fails, the setup screen shows exactly what to check with plain-English troubleshooting.

### Scan Settings (Fixed)

Every scan uses the same settings. No user configuration needed.

```xml
<scan:ScanSettings>
  <pwg:InputSource>Feeder</pwg:InputSource>
  <scan:ColorMode>RGB24</scan:ColorMode>
  <scan:XResolution>300</scan:XResolution>
  <scan:YResolution>300</scan:YResolution>
  <pwg:DocumentFormat>application/pdf</pwg:DocumentFormat>
</scan:ScanSettings>
```

- **300 DPI**: Best balance of OCR accuracy and file size.
- **Color**: Medical docs have colored letterheads, charts, highlights.
- **PDF**: eSCL returns a multi-page PDF from one ADF job.

### ADF Limitation: Simplex Only

The M283cdw ADF does not support duplex scanning (duplex is print-only on this model). The web UI guides the user through a two-pass workflow:

1. **Pass 1**: Load stack face-up → click "Scan" → ADF feeds all pages automatically.
2. **Pass 2**: Flip stack face-down, reload → click "Scan Backs" → ADF feeds again.
3. **Software**: Interleaves fronts and backs in correct order.

When flipping a face-up stack to face-down, the backs come out in reverse order. The interleaving algorithm accounts for this:
- Front pages: [F1, F2, F3, ..., Fn]
- Back pages (as scanned, reversed): [Bn, Bn-1, ..., B1]
- Interleaved: [F1, B1, F2, B2, F3, B3, ..., Fn, Bn]

## Web UI

### Session-Based Workflow

The UI organizes work into **scanning sessions**. A session represents one sitting where the user scans multiple batches.

#### Session Setup Screen

```
┌─────────────────────────────────────────┐
│  New Scanning Session                   │
│                                         │
│  Person: [John Doe          ▼]          │
│          + Add new person               │
│                                         │
│  Scanner: HP M283cdw (192.168.10.11)    │
│           ✓ Online, ADF ready           │
│                                         │
│  [Start Session]                        │
└─────────────────────────────────────────┘
```

- Person selector populated from previous sessions (stored in config).
- Scanner connectivity and ADF status checked via eSCL on load.

#### Batch Scanning Screen

```
┌─────────────────────────────────────────┐
│  Session: John Doe — Batch 3            │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │  Step 1: Scan Front Sides       │    │
│  │                                 │    │
│  │  Load documents FACE UP in ADF  │    │
│  │                                 │    │
│  │  [Scan Fronts]                  │    │
│  │                                 │    │
│  │  ✓ 47 pages scanned            │    │
│  └─────────────────────────────────┘    │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │  Step 2: Scan Back Sides        │    │
│  │                                 │    │
│  │  Flip stack FACE DOWN, reload   │    │
│  │                                 │    │
│  │  [Scan Backs]   [Skip — all     │    │
│  │                  single-sided]  │    │
│  │                                 │    │
│  │  ⏳ Scanning... 23/47           │    │
│  └─────────────────────────────────┘    │
│                                         │
│  [Next Batch]  [Finish Session]         │
│                                         │
│  ── Processing Queue ──                 │
│  Batch 1: ✓ 12 documents extracted      │
│  Batch 2: ⏳ AI splitting...            │
└─────────────────────────────────────────┘
```

Key UI elements:
- **Clear physical instructions** at each step (face up, face down).
- **"Skip Backs"** button for batches known to be all single-sided.
- **Live page count** during ADF scanning (eSCL NextDocument loop).
- **Background processing** — previous batches process while user scans the next.
- **Processing queue** at the bottom shows pipeline progress.

#### Results Browser

See the card layout in the "Results Browsing" section below. The results screen shows document cards with thumbnails, not a data table — visual recognition is faster than reading rows.

### UX Design Principles

**The target user is non-technical.** A family member helping scan medical records, not a sysadmin. Every screen must be immediately understandable without training or documentation.

#### Language Rules

| Never Say | Instead Say |
|-----------|-------------|
| "eSCL protocol error" | "Can't reach the scanner. Is it turned on and connected to WiFi?" |
| "ADF feeder empty" | "The scanner ran out of pages" |
| "OCR confidence below threshold" | "Some text on this page was hard to read" |
| "Pipeline stage failed" | "Something went wrong while processing batch 3. You can try again." |
| "Interleave mismatch" | "The front and back page counts don't match — did a page get stuck?" |
| "NAS mount unavailable" | "Can't save files right now. The storage drive may be disconnected." |
| "API rate limit exceeded" | "The document analyzer is busy. It will try again in a moment." |
| "Batch processing queued" | "Working on it — you can keep scanning while this finishes" |

#### Visual Design Rules

- **Large click targets.** Minimum 48px tap target for all interactive elements. Buttons are full-width on mobile.
- **One primary action per screen.** The most important button is large, colored, and obvious. Secondary actions are smaller and muted.
- **Progress is always visible.** Never leave the user wondering "is it doing something?" Every long operation shows a progress indicator with human-readable status.
- **No modals for critical actions.** Modals are easily missed. Use inline expansion or dedicated pages.
- **Icons + text together.** Never rely on icons alone — always pair with a label.
- **Color coding is supplemental.** Green/yellow/red status indicators are always accompanied by text labels for accessibility.
- **Breadcrumb navigation.** User always knows where they are: Home → Session → Batch → Document.

#### Guided Workflow

The scanning screen uses a **wizard pattern** — numbered steps that highlight the current step and dim completed/upcoming steps:

```
┌─────────────────────────────────────────────┐
│                                             │
│  ① Load Pages                               │
│  ┌───────────────────────────────────────┐  │
│  │                                       │  │
│  │  Place your documents FACE UP         │  │
│  │  in the top tray of the scanner.      │  │
│  │                                       │  │
│  │  ┌─────────────────────────────────┐  │  │
│  │  │  [diagram: paper going          │  │  │
│  │  │   into ADF, face up arrow]      │  │  │
│  │  └─────────────────────────────────┘  │  │
│  │                                       │  │
│  │  You can load up to 50 pages at once. │  │
│  │                                       │  │
│  │         [ ✓ Ready, Scan Fronts ]      │  │
│  │                                       │  │
│  └───────────────────────────────────────┘  │
│                                             │
│  ② Flip & Scan Backs             (dimmed)   │
│  ③ Review Results                (dimmed)   │
│                                             │
└─────────────────────────────────────────────┘
```

Each step includes:
- A **simple illustration** showing the physical action (paper orientation, flip direction).
- **Plain English instructions** in 1-2 sentences.
- **One big action button** per step.
- **Automatic progression** — completing step 1 expands step 2 and collapses step 1 (with a "done" checkmark).

After backs are scanned (or skipped), step 3 shows a thumbnail strip of all pages so the user can visually confirm the stack was scanned correctly before processing begins.

#### Results Browsing: Card Layout

The results browser uses **document cards** rather than a data table — more visual, more approachable:

```
┌─────────────────────────────────────────────────────────┐
│  ✓ Done — 12 documents found in Batch 3                 │
│                                                         │
│  ┌─────────────────────┐  ┌─────────────────────┐      │
│  │ ┌──────┐            │  │ ┌──────┐            │      │
│  │ │ PDF  │ Radiology  │  │ │ PDF  │ Discharge  │      │
│  │ │ thumb│ Report     │  │ │ thumb│ Summary    │      │
│  │ └──────┘            │  │ └──────┘            │      │
│  │ June 15, 2025       │  │ June 14, 2025       │      │
│  │ Memorial Hospital   │  │ Memorial Hospital   │      │
│  │ CT Abdomen          │  │ Post-Appendectomy   │      │
│  │                     │  │                     │      │
│  │ [View] [Edit Info]  │  │ [View] [Edit Info]  │      │
│  └─────────────────────┘  └─────────────────────┘      │
│                                                         │
│  ┌─────────────────────┐  ┌─────────────────────┐      │
│  │ ┌──────┐            │  │ ┌──────┐            │      │
│  │ │ PDF  │ Lab        │  │ │ PDF  │ ⚠ Needs    │      │
│  │ │ thumb│ Results    │  │ │ thumb│ Review     │      │
│  │ └──────┘            │  │ └──────┘            │      │
│  │ May 22, 2025        │  │ Date unknown        │      │
│  │ Quest Diagnostics   │  │ Couldn't determine  │      │
│  │ Metabolic Panel     │  │ document type        │      │
│  │                     │  │                     │      │
│  │ [View] [Edit Info]  │  │ [View] [Fix This ➜] │      │
│  └─────────────────────┘  └─────────────────────┘      │
│                                                         │
│  ────────────────────────────────────────────           │
│  All documents look correct?                            │
│  [ ✓ Yes, Save Everything ]    [ ✎ I need to fix some ] │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Key UX details:
- **PDF thumbnails** — first page rendered as a small preview so users can visually identify documents without opening them.
- **Yellow "Needs Review" cards** for low-confidence splits or missing metadata. These have a "Fix This" button instead of the normal "Edit Info".
- **Confirmation gate** — "Save Everything" only appears after the user has seen all cards. Nothing is written to the NAS or PaperlessNGX until the user explicitly confirms.
- **"I need to fix some"** expands inline editing tools (not a separate page).

### Re-Run & Manual Correction

**Every stage of the pipeline can be re-run independently**, at the batch level or individual document level. All intermediate artifacts are preserved — nothing is discarded after processing.

All intermediate files are preserved in internal storage (see Storage Architecture section). Any stage can be re-run without re-scanning.

#### What You Can Fix After Processing

**Per document (from its card):**
- **Wrong split** — adjust boundaries in the thumbnail strip editor
- **Wrong info** — tap "Edit" and correct the date, type, facility, or description

**Per batch:**
- **Re-scan backs** — if pages jammed or you loaded them wrong, scan backs again without re-scanning fronts
- **Start over** — "Reprocess Batch" re-runs the full pipeline from the saved raw scans. Nothing needs to be re-scanned.

**Per page:**
- **Remove a page** — tap it, tap "Remove"
- **Bring back a removed page** — "Bring back a removed page" shows thumbnails of everything that was removed, tap to restore

#### Manual Document Splitting UI

When the AI gets a boundary wrong, the user needs a simple way to fix it. The split editor shows a **thumbnail strip** of all pages with draggable dividers:

```
┌─────────────────────────────────────────────────────────┐
│  Adjust Document Boundaries — Batch 3                   │
│                                                         │
│  Drag the dividers to mark where documents start/end.   │
│  Each section becomes a separate document.               │
│                                                         │
│  ┌───┐ ┌───┐ ┌───┐ ║ ┌───┐ ┌───┐ ║ ┌───┐ ┌───┐ ┌───┐ │
│  │ 1 │ │ 2 │ │ 3 │ ║ │ 4 │ │ 5 │ ║ │ 6 │ │ 7 │ │ 8 │ │
│  │   │ │   │ │   │ ║ │   │ │   │ ║ │   │ │   │ │   │ │
│  └───┘ └───┘ └───┘ ║ └───┘ └───┘ ║ └───┘ └───┘ └───┘ │
│  ← Doc 1 ────────→ ║ ← Doc 2 ──→ ║ ← Doc 3 ────────→ │
│                     ║              ║                     │
│  Click any page to see it full-size.                    │
│  Click between pages to add or remove a divider.        │
│                                                         │
│  [ Cancel ]                [ ✓ Apply Changes ]          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

- **Dividers** (║) mark document boundaries. Click between any two pages to add/remove a divider.
- **Click a thumbnail** to see the full page in a preview pane (for reading content to determine where documents actually split).
- **Apply Changes** re-splits the PDFs, re-runs naming (with AI metadata extraction for any new documents), and returns to the card view.

#### Saving

One button: **"Save."** It writes to all three destinations (archive, medical records folder, PaperlessNGX) in one action. No choices, no routing, no separate export steps. If corrections are made later, "Save Again" overwrites the previous output cleanly.

#### Past Sessions

The home screen shows all past sessions. Tap any session to review what was scanned and make corrections. You can't add new scans to a past session — start a new one instead. This keeps things simple: sessions only move forward.

### Error Handling in UI

Errors are presented as **friendly inline messages** with clear next actions, not technical dialogs:

| Situation | What the User Sees |
|-----------|-------------------|
| Scanner offline | Yellow banner at top: "Can't reach the scanner. Make sure it's turned on and connected to WiFi." [Try Again] |
| ADF ran out mid-scan | "The scanner ran out of pages after scanning 23. That's fine! Click below when you're ready for the next step." |
| Front/back mismatch | "You scanned 47 front pages but only 45 back pages. A couple of pages might have gotten stuck, or some documents might be single-sided. You can continue — we'll handle it." [Continue Anyway] [Re-Scan Backs] |
| AI splitting uncertain | Yellow-highlighted card: "We're not sure where this document starts. Take a quick look and adjust if needed." [Fix This] |
| OCR quality poor | Small note on card: "Some text on this page was hard to read. The document is still saved, but search may not find everything." |
| Processing failed | "Something went wrong while processing Batch 3. Your scans are safe — nothing is lost. You can try again." [Reprocess Batch] |
| NAS unreachable | "Can't save files right now — the storage drive may be disconnected. Your scans are safe in ScanBox. You can save them once the drive is back." [Retry] |
| AI API unreachable | "The document analyzer isn't available right now. We'll keep trying in the background. You can keep scanning." |

## Persistence & Progress

### Batch State Machine

Every batch moves through a defined sequence of states. Each transition is written to `state.json` on disk **before** the transition happens. If the app crashes at any point, it knows exactly where to resume.

```
scanning_fronts → fronts_done → scanning_backs → backs_done → processing → review → saved
                                      ↓
                                 backs_skipped
```

| State | What's Happening | If App Crashes Here | What User Sees |
|-------|-----------------|--------------------|----|
| `scanning_fronts` | eSCL job active, receiving pages one by one | Pages already received are saved. User re-scans fronts (only the remaining pages were lost). | "Scanning... 23 pages so far" |
| `fronts_done` | All front pages saved to disk as `fronts.pdf` | Nothing lost. Resume from here. | Checkmark on step 1, step 2 active |
| `scanning_backs` | eSCL job active, receiving back pages | Same as fronts — partial pages saved. | "Scanning backs... 18 pages so far" |
| `backs_done` | Back pages saved as `backs.pdf` | Nothing lost. Processing starts automatically on restart. | "Processing your documents..." |
| `backs_skipped` | User clicked "No back sides" | Nothing lost. Processing starts automatically. | "Processing your documents..." |
| `processing` | Pipeline running (with sub-stage tracking — see below) | Resumes from last completed sub-stage. No re-scanning. | Progress bar with stage name |
| `review` | Processing complete, cards displayed | Nothing lost. Review screen shown on return. | Document cards with "Save" button |
| `saved` | Output written to all destinations | If save was partial, user can "Save Again." | "Done!" with checkmark |

### Scan Persistence (The Critical Part)

During an eSCL ADF scan, pages arrive one at a time via HTTP (`GET .../NextDocument` in a loop). **Each page is written to disk immediately as it arrives** — appended to a growing PDF file. If the app crashes after receiving 23 of 50 pages:

- 23 pages are safely on disk.
- The eSCL job on the printer has ended (the printer doesn't hold state).
- On return, the UI shows: "Last time, we got 23 pages before something went wrong. You can use those 23 pages or re-scan."

**The printer's ADF has already fed those 23 sheets.** They're in the output tray. The user would need to separate the remaining ~27 unscanned sheets from the scanned ones. The UI makes this clear: "The scanner fed 23 pages. Those pages are in the scanner's output tray. Put the remaining pages back in the top tray and scan again."

### Processing Sub-Stages

The processing state has internal sub-stages, each checkpointed:

| Sub-Stage | Produces | If Crash Here |
|-----------|----------|---------------|
| `interleaving` | `combined.pdf` | Restart interleaving from saved fronts + backs |
| `blank_removal` | `cleaned.pdf` | Restart from `combined.pdf` |
| `ocr` | `ocr.pdf` + `text_by_page.json` | Restart from `cleaned.pdf` |
| `splitting` | `splits.json` | Restart from `text_by_page.json` (one AI call) |
| `naming` | `documents/*.pdf` | Restart from `ocr.pdf` + `splits.json` |

Each sub-stage reads its input from the previous stage's output file. No in-memory-only state. Everything is on disk.

### Progress Communication

The backend pushes progress updates to the frontend via **Server-Sent Events (SSE)** — a simple one-way stream over HTTP. No WebSocket complexity.

**What the user sees during scanning:**
```
Scanning... 23 pages so far
[animated scanner icon]
```
The page count increments in real time as each page arrives from the eSCL endpoint. We don't know the total (the ADF doesn't report how many pages are loaded), so it's an open-ended counter.

**What the user sees during processing:**
```
Processing Batch 3...
━━━━━━━━━━━━━━━━━━░░░░
Removing blank pages (4 of 47)
```

Progress stages shown in plain English:

| Internal Stage | User Sees |
|---------------|-----------|
| `interleaving` | "Combining front and back pages..." |
| `blank_removal` | "Removing blank pages..." (with count) |
| `ocr` | "Reading text from your documents..." (with page count) |
| `splitting` | "Figuring out where each document starts and ends..." |
| `naming` | "Organizing and naming your documents..." |

### What Happens On App Restart

When ScanBox starts up, it checks for incomplete work:

1. **Unfinished scans** (`scanning_fronts` or `scanning_backs`): Shows a recovery screen: "We were interrupted while scanning. 23 pages were saved. [Use these pages] or [Start over]"
2. **Unfinished processing** (`processing` state): Automatically resumes from the last completed sub-stage. Shows: "Picking up where we left off..."
3. **Unsaved review** (`review` state): Shows the review screen with document cards, ready for the user to save.
4. **Everything complete** (`saved`): Normal home screen.

The user never has to understand what happened technically. The app explains what it has and what it needs.

## Processing Pipeline

Each batch goes through this pipeline automatically after both passes complete (or after fronts-only if backs were skipped).

### Stage 1: Interleave (if duplex)

**Input:** `fronts.pdf` (N pages) + `backs.pdf` (M pages)
**Output:** `combined.pdf` (up to 2N pages)

- If M < N: last (N-M) sheets treated as single-sided (no back page).
- If M > N: error, prompt user.
- Backs are reversed before interleaving (flip-stack correction).
- Library: `pikepdf`

### Stage 2: Blank Page Removal

**Input:** `combined.pdf`
**Output:** `cleaned.pdf`

Detect blank pages using pixel variance analysis:
1. Render each page to image (150 DPI — lower res is fine for blank detection).
2. Calculate ink coverage: percentage of non-white pixels.
3. Remove pages below threshold (default: 1% ink coverage).
4. Library: `Pillow` + `pikepdf` (avoids Ghostscript dependency).

### Stage 3: OCR

**Input:** `cleaned.pdf`
**Output:** `ocr.pdf` (searchable PDF) + `text_by_page.json`

- Uses `ocrmypdf` (wraps Tesseract) — the industry standard for creating searchable PDFs. Handles deskew, image optimization, and text layer insertion in one step.
- Also extracts per-page text to JSON for the AI splitting stage.
- Language: English (`eng`).
- PaperlessNGX will skip re-OCR on PDFs that already have a text layer.

### Stage 4: AI Document Splitting & Classification

**Input:** `text_by_page.json` (OCR text per page)
**Output:** `splits.json` (document boundaries + metadata)

Single LLM call per batch. The prompt is the same regardless of provider — only the API transport differs.

**Prompt structure:**
```
You are analyzing OCR text from a batch of scanned medical documents.
The pages were scanned sequentially from a mixed stack. Multiple
documents are concatenated. Identify where each document starts and
ends, classify the document type, and extract metadata.

For each document found, return:
- start_page (1-indexed)
- end_page (1-indexed)
- document_type (one of: Radiology Report, Discharge Summary,
  Care Plan, Lab Results, Letter, Operative Report, Progress Note,
  Pathology Report, Prescription, Insurance, Billing, Other)
- date_of_service (YYYY-MM-DD or "unknown")
- facility (hospital/clinic name or "unknown")
- provider (doctor name or "unknown")
- description (brief description, 3-8 words)
- confidence (0.0-1.0, how confident in the boundary detection)

Patient name: {person_name}

Page texts:
---PAGE 1---
{ocr_text_page_1}
---PAGE 2---
{ocr_text_page_2}
...
```

**Response format:** JSON array of document objects.

**Cost estimate (cloud providers):** ~25K tokens per 50-page batch. With a fast, cheap model (Claude Haiku, GPT-4o-mini, etc.) this is ~$0.02/batch. Hundreds of pages for under $1. With local Ollama, cost is zero (just time).

**Low-confidence boundaries** (< 0.7) are flagged in the UI for human review.

### Stage 5: Split, Embed Metadata & Name PDFs

**Input:** `ocr.pdf` + `splits.json`
**Output:** Individual named PDFs with embedded metadata

For each document in `splits.json`:
1. Extract pages from `ocr.pdf` using `pikepdf`.
2. **Embed PDF metadata** into the file itself (via pikepdf's `docinfo`):
   - `Title`: Document type + description (e.g., "Radiology Report — CT Abdomen with Contrast")
   - `Author`: Facility name (e.g., "Memorial Hospital")
   - `Subject`: Person name
   - `CreationDate`: Date of service extracted by AI (e.g., `2025-06-15`)
   - `Producer`: "ScanBox"
3. Name file: `YYYY-MM-DD_{PersonName}_{DocumentType}_{Facility}_{Description}.pdf`
4. Sanitize filename (remove special chars, truncate to 200 chars).

The embedded metadata means the document date, title, and author are visible in any PDF viewer's "Properties" dialog — not just in ScanBox or PaperlessNGX. This is important for doctors or medical staff who receive the PDF directly.

### Stage 6: Output

Triggered by the user clicking **"Save"** on the review screen. Writes to three destinations:

| Destination | Where | Purpose |
|-------------|-------|---------|
| Archive | `/output/archive/{person}/{date}/` | Raw combined PDF (safety copy) |
| Medical Records | `/output/medical-records/{Person}/{Type}/` | Organized named PDFs for sharing |
| PaperlessNGX | API upload with tags + metadata | Searchable archive (optional) |
| Index | `/output/medical-records/{Person}/Index.csv` | Spreadsheet for doctor's offices |

### Index.csv Format

```csv
Filename,Date,Type,Facility,Provider,Description,Scanned
2025-06-15_John-Doe_Radiology-Report_Memorial-Hospital_CT-Abdomen.pdf,2025-06-15,Radiology Report,Memorial Hospital,Dr. Smith,CT Abdomen with Contrast,2026-03-28
```

Clean, human-readable. No internal metadata (batch IDs, confidence scores) in the shared output.

## Storage Architecture

ScanBox uses **two types of storage**, clearly separated by purpose:

### Internal Storage (Docker Volume)

Everything ScanBox needs to operate: session data, intermediate files, processing state. Lives inside the container. No external dependencies.

```
/app/data/                          # Docker volume: scanbox-data
├── config/
│   └── persons.json                # Person profiles
├── sessions/
│   └── {session_id}/
│       └── batches/{batch_id}/
│           ├── fronts.pdf          # Raw scan
│           ├── backs.pdf           # Raw scan
│           ├── combined.pdf        # Interleaved
│           ├── cleaned.pdf         # Blanks removed
│           ├── ocr.pdf             # OCR'd searchable PDF
│           ├── text_by_page.json   # Extracted text
│           ├── splits.json         # Document boundaries + metadata
│           ├── documents/          # Individual split PDFs
│           └── state.json          # Pipeline checkpoint
└── scanbox.db                      # SQLite (sessions, batches, documents)
```

**This is the safety net.** Even if PaperlessNGX is down, the NAS is offline, or an export fails, all scans and processing results are preserved here. The user can always come back and re-export.

### Export Storage (User-Configured Output Directory)

A single mounted volume where ScanBox writes final output. This is where the user points ScanBox at whatever storage they have — a NAS mount, a local folder, an external drive, anything.

```
/output/                            # Docker volume: user-mounted
├── archive/                        # Raw batch PDFs (safety copy)
│   └── john-doe/
│       └── 2026-03-28/
│           └── batch-001-combined.pdf
└── medical-records/                # Organized for sharing with doctors
    ├── README.txt
    ├── John_Doe/
    │   ├── Index.csv
    │   ├── Radiology Reports/
    │   ├── Discharge Summaries/
    │   └── ...
    └── Jane_Flammia/               # Future
```

**This is the shareable output.** Copy the `medical-records/John_Doe/` folder to a USB drive and hand it to a doctor.

### PaperlessNGX Integration (API, Not Filesystem)

ScanBox sends documents to PaperlessNGX via its **REST API**, not by dropping files in a consumption folder. This is cleaner and more reliable:

- No shared filesystem mount needed between ScanBox and PaperlessNGX
- ScanBox can set tags, document type, and correspondent directly via the API
- Upload confirmation — ScanBox knows the document was accepted, not just "file was written and hopefully something picks it up"
- Works regardless of where PaperlessNGX runs (same host, different host, cloud)

**API operations used:**

| Operation | Endpoint | Purpose |
|-----------|----------|---------|
| Upload document | `POST /api/documents/post_document/` | Upload PDF with metadata |
| Set tags | Tag name in upload payload | `medical-records`, `person:john-doe` |
| Set document type | Document type name in upload payload | `Radiology Report`, etc. |
| Set correspondent | Correspondent name in upload payload | Facility name |
| Set created date | `created` field in upload payload | Date of service |
| Check upload status | `GET /api/documents/?query=...` | Verify document was ingested |

**Configuration:** ScanBox needs only two values to talk to PaperlessNGX:
- `PAPERLESS_URL`: e.g., `https://paperless.blueshift.xyz`
- `PAPERLESS_API_TOKEN`: Generated in PaperlessNGX settings (Settings > API tokens)

**First-run setup guides the user through this** with step-by-step instructions showing exactly where to find the API token in PaperlessNGX.

## Configuration

### Docker Compose

```yaml
services:
  scanbox:
    build: .
    ports:
      - "8090:8090"
    env_file: .env
    volumes:
      - scanbox-data:/app/data        # Internal: sessions, config, processing
      - ${OUTPUT_DIR:-./output}:/output  # External: defaults to ./output
    restart: unless-stopped

volumes:
  scanbox-data:
```

### .env.example

```bash
# Required
SCANNER_IP=192.168.10.11

# LLM Provider — pick one (required for AI document splitting)
LLM_PROVIDER=anthropic          # Options: anthropic, openai, ollama

# Provider-specific keys (set the one matching your LLM_PROVIDER)
ANTHROPIC_API_KEY=sk-ant-...    # For LLM_PROVIDER=anthropic
# OPENAI_API_KEY=sk-...         # For LLM_PROVIDER=openai
# OLLAMA_URL=http://localhost:11434  # For LLM_PROVIDER=ollama
# LLM_MODEL=                    # Optional: override default model per provider

# Optional — PaperlessNGX integration (can also configure via web UI)
# PAPERLESS_URL=https://paperless.example.com
# PAPERLESS_API_TOKEN=

# Optional — override output directory (default: ./output next to compose file)
# OUTPUT_DIR=/mnt/nas/medical-scanning
```

**Minimal config:** Copy `.env.example` to `.env`, set `SCANNER_IP` and one LLM provider. PaperlessNGX and output directory are optional — defaults work out of the box.

**LLM provider can also be configured in the web UI** during first-run setup. The `.env` is just for pre-configuration or headless deployment.

### First-Run Setup

On first launch, the web UI walks through setup as a friendly checklist:

1. **Scanner check** — "Looking for your scanner..." Tests eSCL connectivity. Shows a green checkmark or a troubleshooting message.
2. **Storage check** — "Checking if we can save files..." Verifies the output volume is writable.
3. **AI setup** — "Which AI service would you like to use for document analysis?" Pick Anthropic, OpenAI, or Ollama. Enter the API key (or Ollama URL). Tests the connection.
4. **PaperlessNGX (optional)** — "Do you use PaperlessNGX?" If yes, walks through entering the URL and API token with screenshots showing where to find the token. If no, skips it.
5. **Add a person** — "Who are these documents for?" Type a name.
6. **Done** — "You're ready to scan!" Big green button to start first session.

### Person Profiles

Stored in `scanbox-data` volume as `config/persons.json`:

```json
[
  {
    "id": "john-doe",
    "display_name": "John Doe",
    "slug": "john-doe",
    "folder_name": "John_Doe",
    "created": "2026-03-28T08:00:00-0400"
  }
]
```

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Backend | Python 3.12 + FastAPI | Strong PDF/OCR ecosystem, async, lightweight |
| Frontend | HTML + Alpine.js + Tailwind CSS | No build step, fast to develop, reactive enough for this UI |
| Scanner comm | `httpx` (async HTTP) | Direct eSCL calls, no SANE dependency |
| PDF manipulation | `pikepdf` | Fast, reliable, handles merge/split/page extraction |
| OCR | `ocrmypdf` (wraps Tesseract 5) | Searchable PDF creation, deskew, image optimization |
| Blank detection | `Pillow` | Render PDF pages, analyze pixel coverage |
| AI splitting | `litellm` | Unified API for any LLM provider (Anthropic, OpenAI, Ollama, etc.) |
| PDF rendering | `pdf2image` + `poppler-utils` | Render PDF pages to images for blank detection and OCR |
| Database | SQLite | Session state, scan history, batch/document tracking |
| Container base | `python:3.12-slim` + Tesseract apt packages | Minimal image size |

### Container Dependencies (apt)

```
tesseract-ocr
tesseract-ocr-eng
poppler-utils
libgl1-mesa-glx     # For Pillow image processing
```

### Python Dependencies

```
fastapi
uvicorn
httpx
pikepdf
ocrmypdf
Pillow
pdf2image
litellm              # Unified LLM API (Anthropic, OpenAI, Ollama, etc.)
python-multipart
aiosqlite
jinja2               # Server-side template rendering
```

## Directory Structure (New Repo)

```
scanbox/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── README.md
├── CLAUDE.md
│
├── scanbox/                    # Python package
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Environment variable loading
│   ├── database.py             # SQLite session/person storage
│   │
│   ├── scanner/                # eSCL scanner communication
│   │   ├── __init__.py
│   │   ├── escl.py             # eSCL HTTP client
│   │   ├── models.py           # ScannerCapabilities, ScanJob, etc.
│   │   └── health.py           # Connectivity and status checks
│   │
│   ├── pipeline/               # Document processing pipeline
│   │   ├── __init__.py
│   │   ├── interleave.py       # Two-pass duplex page interleaving
│   │   ├── blank_detect.py     # Blank page detection and removal
│   │   ├── ocr.py              # Tesseract OCR wrapper
│   │   ├── splitter.py         # AI document boundary detection (provider-agnostic via litellm)
│   │   ├── namer.py            # Medical document naming logic
│   │   └── output.py           # Archive, medical-records, PaperlessNGX output
│   │
│   ├── api/                    # FastAPI route handlers
│   │   ├── __init__.py
│   │   ├── sessions.py         # Session CRUD
│   │   ├── scanning.py         # Scan initiation, status polling
│   │   ├── processing.py       # Pipeline status, results
│   │   ├── persons.py          # Person profile management
│   │   └── documents.py        # Result browsing, metadata editing, export
│   │
│   └── templates/              # Jinja2 HTML templates
│       ├── base.html
│       ├── index.html          # Session list / new session
│       ├── scan.html           # Batch scanning workflow
│       ├── results.html        # Document browser / editor
│       └── settings.html       # Person management, scanner config
│
├── static/                     # CSS, JS, icons
│   ├── css/
│   │   └── tailwind.min.css
│   ├── js/
│   │   └── alpine.min.js
│   └── icons/
│
└── tests/
    ├── generate_fixtures.py          # Builds synthetic test PDFs from templates
    ├── conftest.py                   # Shared fixtures, mock eSCL server
    │
    ├── unit/
    │   ├── test_interleave.py
    │   ├── test_blank_detect.py
    │   ├── test_ocr.py
    │   ├── test_splitter.py
    │   ├── test_namer.py
    │   ├── test_output.py
    │   └── test_escl.py
    │
    ├── integration/
    │   ├── test_pipeline_integration.py
    │   ├── test_escl_integration.py
    │   └── test_sessions_integration.py
    │
    ├── e2e/
    │   └── test_e2e_synthetic.py
    │
    └── fixtures/
        ├── pages/                    # Synthetic single-page PDFs
        ├── batches/                  # Pre-assembled multi-page test batches
        ├── expected/                 # Expected outputs for comparison
        └── escl/                     # Mock eSCL XML responses
```

## PaperlessNGX Integration

### How It Works

ScanBox uploads documents to PaperlessNGX via its REST API. Each document is uploaded with full metadata:

- **Tags:** `medical-records` + `person:john-doe` (auto-created by PaperlessNGX if they don't exist)
- **Document type:** `Radiology Report`, `Discharge Summary`, etc. (auto-created)
- **Correspondent:** Facility name (auto-created)
- **Created date:** Date of service from the document (see Date Handling below)
- **Title:** Document type + description

No PaperlessNGX configuration changes are needed. The API handles tag/type/correspondent creation automatically on first use.

### Date Handling

Document dates flow through every layer of the system:

| Source | How Date Is Found | Where It Goes |
|--------|------------------|---------------|
| OCR text | AI extracts date from document content (e.g., "Date of Service: 06/15/2025", report headers, letterhead dates) | `splits.json` → `date_of_service` field |
| AI extraction | Normalized to `YYYY-MM-DD` format | Used everywhere below |
| PDF metadata | Embedded as `CreationDate` in the PDF file | Visible in any PDF viewer's Properties |
| Filename | Date prefix: `2025-06-15_John-Doe_...pdf` | Visible in file explorer, sortable |
| PaperlessNGX | Sent as `created` field in the upload API call | PaperlessNGX shows this as the document date, enables date-range filtering |
| Index.csv | `Date` column | Visible in spreadsheet |

**Why this matters:** Without explicit date handling, PaperlessNGX defaults to the *scan date* (today) as the document date. A radiology report from June 2025 would show as "March 2026" in PaperlessNGX. By extracting the actual date of service from the document content and passing it through the API, the document appears in PaperlessNGX with the correct original date.

**When the AI can't find a date:** The field is set to `"unknown"`. The filename uses `Unknown-Date` prefix. PaperlessNGX receives no `created` field and falls back to upload date. The user can correct the date via the "Edit" button on the document card — this updates the PDF metadata, filename, PaperlessNGX, and Index.csv all at once.

### Required PaperlessNGX Setup (One-Time)

1. **Generate an API token:** PaperlessNGX Settings > click your username > generate token
2. **Enter in ScanBox:** Paste the URL and token during first-run setup (or in Settings later)

That's it. ScanBox handles everything else.

### Saved Views (Optional, Recommended)

After the first batch is processed, set up these views in PaperlessNGX for clean separation:

| View Name | Filter | Purpose |
|-----------|--------|---------|
| My Documents | Exclude tag `medical-records` | Your existing workflow, unchanged |
| John's Medical Records | Tag `medical-records` + tag `person:john-doe` | Per-person view |
| All Medical Records | Tag `medical-records` | Overview |

### No PaperlessNGX? No Problem.

PaperlessNGX is optional. Without it, ScanBox still scans, processes, splits, names, and writes organized PDFs to the output volume. You just won't get the search/tagging features. PaperlessNGX can be connected later without re-scanning — ScanBox can re-export any past session.

## Deployment

### Runs Anywhere Docker Runs

ScanBox is a single Docker image with zero external dependencies beyond the printer and (optionally) PaperlessNGX. It runs identically on a laptop and on infrastructure.

| Environment | How to Run | Output Volume |
|-------------|-----------|---------------|
| **Laptop (macOS/Linux/Windows)** | `docker compose up` | A local folder (e.g., `~/Medical-Records`) |
| **Homelab server** | Komodo stack, systemd, or `docker compose up` | NFS mount, local disk, whatever |
| **Any cloud VM** | `docker compose up` | Attached volume |

Requirements (same everywhere):
1. Docker (or Podman).
2. Network access to the printer's IP (same LAN or routed — e.g., VPN from a remote machine).
3. Outbound HTTPS to your LLM provider (or network access to local Ollama).

### Multi-Architecture

The Docker image builds for both **linux/amd64** (Intel/AMD servers) and **linux/arm64** (Apple Silicon Macs, ARM servers). All dependencies — Python, Tesseract, poppler — are available on both architectures from the standard Debian repos. No architecture-specific hacks needed.

```dockerfile
# Dockerfile uses multi-stage build, works on both architectures
FROM python:3.12-slim AS base
# tesseract-ocr, poppler-utils are multi-arch in Debian
```

### Laptop Quick Start

```bash
git clone <repo>
cd scanbox

# Set your printer IP and LLM provider
cp .env.example .env
# Edit .env: SCANNER_IP, LLM_PROVIDER, and provider API key

# Start (output goes to ./output/ by default)
docker compose up

# Open http://localhost:8090
```

The default `docker-compose.yml` maps `./output` as the output volume — a plain folder next to the repo. No NAS, no special mounts. On a homelab server, swap that path for an NFS mount or wherever you want the files.

### No Lock-In

Nothing in ScanBox depends on:
- A specific host or hostname
- NFS or any particular filesystem
- Komodo or any particular orchestrator
- A specific network subnet
- A specific LLM provider (swap Anthropic for Ollama or OpenAI anytime)
- PaperlessNGX (optional integration)

## Security Considerations

- **LLM API keys**: Injected via environment variables. Store securely (1Password, vault, etc.).
- **No authentication on web UI**: Intended for local network use only. Traefik can add auth if exposed externally.
- **Medical data**: All processing happens locally. Only OCR text (not images/PDFs) is sent to the LLM provider for splitting. No PHI leaves the network in image form.
- **eSCL has no auth**: The printer's eSCL endpoint is unauthenticated. Anyone on the LAN can initiate scans. This is an HP limitation, not a ScanBox issue.

## Privacy Note on AI Splitting

The AI splitting step sends OCR-extracted **text only** to the configured LLM provider. This text will contain PHI (patient names, dates, diagnoses). No images or PDFs leave the network.

**Choose your privacy level:**

| Provider | Data Leaves Network? | Notes |
|----------|---------------------|-------|
| **Ollama** (local) | No | Runs on your own hardware. Fully offline. Slower but maximum privacy. |
| **Anthropic** (cloud) | Yes (text only) | API data policy: inputs not used for training. |
| **OpenAI** (cloud) | Yes (text only) | Check current data policy for API usage. |

For maximum privacy with medical records, use **Ollama with a capable local model** (e.g., Llama 3, Mistral). ScanBox works identically regardless of provider — only the speed and accuracy may differ.

## Testing Strategy

The testing strategy is designed around one principle: **you must have full confidence in every stage of the pipeline before scanning a single real document.** Each stage is tested independently, then the full pipeline is tested end-to-end with synthetic data that mirrors real-world conditions. Only after all automated tests pass do you do a small live validation scan before committing to the full batch.

### Test Fixtures

A `tests/fixtures/` directory contains synthetic test data that exercises every edge case:

```
tests/fixtures/
├── pages/                          # Individual page images (PNG/PDF)
│   ├── radiology_report_p1.pdf     # Typical radiology header + body
│   ├── radiology_report_p2.pdf     # Continuation page
│   ├── discharge_summary_p1.pdf    # Different letterhead
│   ├── lab_results_single.pdf      # Single-page lab result
│   ├── care_plan_p1.pdf            # Multi-page care plan
│   ├── care_plan_p2.pdf
│   ├── care_plan_p3.pdf
│   ├── blank_page.pdf              # Completely blank
│   ├── near_blank_page.pdf         # Small smudge/artifact (<1% ink)
│   ├── low_quality_scan.pdf        # Skewed, faded text
│   └── handwritten_note.pdf        # Handwritten content (hard OCR)
│
├── batches/                        # Pre-assembled multi-page PDFs
│   ├── fronts_5docs.pdf            # 12 front pages, 5 documents
│   ├── backs_5docs.pdf             # 12 back pages (reversed order)
│   ├── fronts_all_single_sided.pdf # 8 pages, no backs
│   ├── fronts_mixed_sided.pdf      # 10 pages, some with backs
│   ├── backs_mixed_sided.pdf       # 7 pages (3 sheets single-sided)
│   └── fronts_single_doc.pdf       # 4 pages, all one document
│
├── expected/                       # Expected outputs for comparison
│   ├── interleaved_5docs.pdf       # Correct interleave of fronts+backs
│   ├── cleaned_5docs.pdf           # After blank removal
│   ├── splits_5docs.json           # Expected AI split boundaries
│   └── filenames_5docs.txt         # Expected output filenames
│
└── escl/                           # Mock eSCL responses
    ├── capabilities.xml            # ScannerCapabilities response
    ├── status_idle.xml             # ScannerStatus when idle
    ├── status_busy.xml             # ScannerStatus during scan
    └── status_adf_empty.xml        # ScannerStatus when ADF runs out
```

These fixtures are created during the build phase by a `tests/generate_fixtures.py` script that assembles synthetic medical documents from templates. The templates use realistic formatting (letterheads, dates, report structures) but contain no real PHI.

### Layer 1: Unit Tests

Each pipeline module has isolated unit tests. No network, no filesystem side effects, no AI calls.

#### 1a. Interleave (`test_interleave.py`)

| Test Case | Input | Expected |
|-----------|-------|----------|
| Equal fronts/backs | 5F + 5B | [F1,B1,F2,B2,F3,B3,F4,B4,F5,B5] |
| More fronts than backs | 5F + 3B | [F1,B1,F2,B2,F3,B3,F4,F5] (last 2 single-sided) |
| No backs (skip) | 5F + 0B | [F1,F2,F3,F4,F5] (passthrough) |
| Single page each | 1F + 1B | [F1,B1] |
| More backs than fronts | 3F + 5B | Error raised |
| Back reversal correctness | 3F + 3B(reversed) | Verify B pages are re-reversed before interleaving |
| Page content integrity | Known PDFs | Verify no page corruption, metadata preserved |

#### 1b. Blank Page Detection (`test_blank_detect.py`)

| Test Case | Input | Expected |
|-----------|-------|----------|
| Completely blank page | White PDF | Detected as blank (removed) |
| Near-blank (smudge) | <1% ink PDF | Detected as blank at default threshold |
| Light text page | ~3% ink PDF | NOT detected as blank |
| Full content page | Normal document | NOT detected as blank |
| Threshold edge cases | Pages at 0.5%, 1.0%, 1.5% | Correct classification per threshold |
| Color page handling | Colored letterhead | NOT detected as blank |
| All pages blank | 5 blank pages | All removed, warning logged |
| No blank pages | 5 content pages | All preserved |
| Mixed batch | 10 pages, 3 blank | Exactly 3 removed, 7 preserved |
| Page order preservation | Known sequence | Non-blank pages maintain original order |

#### 1c. OCR (`test_ocr.py`)

| Test Case | Input | Expected |
|-----------|-------|----------|
| Clean typed text | 300 DPI typed page | >95% character accuracy vs known text |
| Faded text | Low contrast page | Produces output (may be lower quality) |
| Skewed page | 5-degree rotation | ocrmypdf deskews, text extracted |
| Already-OCR'd PDF | PDF with text layer | Detects existing text, skips re-OCR |
| Multi-page batch | 5-page PDF | Per-page text JSON has all 5 entries |
| Empty page after blank removal | 0-page PDF | Graceful error, not crash |
| Special characters | Medical symbols (±, µ, ®) | Characters preserved or gracefully handled |

#### 1d. AI Splitter (`test_splitter.py`)

Uses recorded LLM responses (cassette/fixture pattern) — no live API calls in CI.

| Test Case | Input | Expected |
|-----------|-------|----------|
| Clear boundaries | 5 docs with distinct headers | 5 splits with correct page ranges |
| Single document | All pages one doc | 1 split covering all pages |
| Single-page documents | 5 one-page docs | 5 splits, each 1 page |
| Ambiguous boundary | Similar headers adjacent | Low confidence flag on boundary |
| Missing date | Doc without clear date | `date: "unknown"` in output |
| Missing facility | Personal letter, no letterhead | `facility: "unknown"` in output |
| All doc types | One of each known type | Correct classification for each |
| Large batch | 50 pages, ~15 docs | All boundaries detected, no gaps/overlaps |
| Overlapping pages | AI returns overlap | Validation catches and rejects |
| Gap in pages | AI skips pages | Validation catches and rejects |

The validation layer (separate from AI) enforces:
- Page ranges are contiguous (no gaps).
- Page ranges don't overlap.
- All pages in the batch are accounted for.
- start_page <= end_page for every document.
- Confidence values are between 0.0 and 1.0.

#### 1e. Namer (`test_namer.py`)

| Test Case | Input | Expected |
|-----------|-------|----------|
| Normal metadata | Full metadata dict | `2025-06-15_John-Doe_Radiology-Report_Memorial-Hospital_CT-Abdomen.pdf` |
| Unknown date | `date: "unknown"` | `Unknown-Date_John-Doe_Radiology-Report_...pdf` |
| Unknown facility | `facility: "unknown"` | Date and type present, facility omitted |
| Long description | 200+ char description | Truncated to limit, no mid-word cut |
| Special characters | `Dr. O'Brien & Associates` | `Dr-OBrien-Associates` (sanitized) |
| Unicode characters | Accented names | Transliterated or preserved safely |
| Duplicate filenames | Two identical metadata sets | Second gets `-2` suffix |
| All unknowns | Everything unknown | `Unknown-Date_John-Doe_Other_Unknown_Document.pdf` |

#### 1f. Output (`test_output.py`)

| Test Case | Input | Expected |
|-----------|-------|----------|
| Archive write | Combined PDF + metadata | Files exist at correct archive path |
| Medical records write | Split PDFs + metadata | Files in correct type subdirectories |
| PaperlessNGX write | Split PDFs + person slug | Files in correct consume subdirectory |
| Index.csv append | New documents | CSV rows appended, headers preserved |
| Index.csv create | First documents for person | CSV created with headers + rows |
| Directory creation | New person, new types | All directories created on demand |
| Permission errors | Read-only mount | Graceful error with clear message |
| Concurrent writes | Two batches finishing simultaneously | No file corruption, no race conditions |

#### 1g. eSCL Client (`test_escl.py`)

| Test Case | Input | Expected |
|-----------|-------|----------|
| Capabilities parsing | XML fixture | Correct resolution, format, ADF support extracted |
| Status parsing (idle) | XML fixture | `status=idle, adf_loaded=true` |
| Status parsing (busy) | XML fixture | `status=busy` |
| Scan job XML generation | Settings dict | Valid XML matching eSCL schema |
| Job creation response | HTTP 201 + Location header | Job URL extracted correctly |
| NextDocument loop | Multi-page mock responses | All pages collected, loop ends on 404 |
| ADF empty mid-scan | 404 after 3 pages | 3 pages returned, no error |
| Scanner offline | Connection refused | Clear error, not crash |
| Scanner busy | Status=busy | Retry with backoff, clear UI feedback |

### Layer 2: Integration Tests

Test multi-stage interactions with real filesystem I/O but mocked external services.

#### 2a. Pipeline Integration (`test_pipeline_integration.py`)

Tests the full pipeline from combined PDF to output files, using fixture PDFs and recorded AI responses.

| Test Case | Description |
|-----------|-------------|
| **Happy path: 5-doc duplex batch** | fronts + backs → interleave → blank removal → OCR → split → name → output. Verify all 5 documents exist at all 3 output destinations with correct names. |
| **Happy path: single-sided batch** | fronts only (no backs) → skip interleave → blank removal → OCR → split → name → output. |
| **Single document batch** | One multi-page document, no splitting needed. Verify it passes through correctly as a single output. |
| **All blank backs** | fronts + all-blank backs → interleave → blank removal removes all backs → output is fronts-only. |
| **Low-confidence split** | AI returns a boundary with confidence 0.4. Verify it's flagged in results JSON but still produces output. |
| **OCR failure recovery** | One page has 0% OCR confidence. Pipeline continues, page marked as low-quality in output metadata. |
| **Large batch** | 50-page fixture. Verify memory doesn't spike, processing completes in reasonable time (<60s). |
| **Output idempotency** | Run same batch twice. Second run doesn't create duplicates (or handles them with `-2` suffix). |

#### 2b. eSCL Integration (`test_escl_integration.py`)

A mock HTTP server (using `pytest-httpserver` or `respx`) that mimics the M283cdw's eSCL behavior:

| Test Case | Description |
|-----------|-------------|
| **Full ADF scan cycle** | POST job → loop NextDocument until 404 → verify all pages received as PDF. |
| **Scanner goes offline mid-scan** | Connection drops after page 3 of 10. Verify partial results saved, error reported. |
| **Concurrent scan rejection** | Second scan job while first is running. Verify graceful handling (eSCL returns 503). |
| **Slow scanner** | NextDocument takes 5s per page. Verify timeout handling and progress reporting. |

#### 2c. Session Management Integration (`test_sessions_integration.py`)

| Test Case | Description |
|-----------|-------------|
| **Session lifecycle** | Create session → add 3 batches → finish session. Verify SQLite state at each step. |
| **Resume interrupted session** | Create session, add 1 batch, simulate crash. Reopen — session is recoverable. |
| **Multi-person sessions** | Two sessions for different people. Verify output isolation (no cross-contamination). |

### Layer 3: End-to-End Tests

#### 3a. Synthetic E2E (`test_e2e_synthetic.py`)

The full app running in a test container, with a mock eSCL server replacing the real printer.

```
Test Container                    Mock eSCL Server
┌──────────────┐                 ┌──────────────┐
│  ScanBox App │ ──── HTTP ────▶ │  Serves       │
│  (FastAPI)   │ ◀────────────── │  fixture PDFs │
└──────┬───────┘                 └──────────────┘
       │
       ▼
  /tmp/test-output/
  ├── consume/
  ├── archive/
  └── medical-records/
```

**Test procedure:**
1. Start ScanBox container with `SCANNER_IP` pointing to mock eSCL server.
2. Via API: create person "Test Patient".
3. Via API: create session for "Test Patient".
4. Via API: trigger fronts scan (mock returns 12-page PDF).
5. Via API: trigger backs scan (mock returns 12-page PDF, reversed).
6. Wait for processing to complete (poll status endpoint).
7. **Verify:**
   - Archive contains `batch-001-fronts.pdf`, `batch-001-backs.pdf`, `batch-001-combined.pdf`.
   - Medical records folder has correct subdirectories and named PDFs.
   - PaperlessNGX consume folder has files in `medical-records/person:test-patient/`.
   - Index.csv has entries for all split documents.
   - All PDFs are valid (parseable by pikepdf).
   - All PDFs have OCR text layer (searchable).
   - No blank pages remain in output PDFs.
   - Filenames match expected pattern.
   - Web UI results endpoint returns all documents with metadata.

#### 3b. In-App Guided Walkthrough

The beta validation is **built into ScanBox itself** as a guided walkthrough. After first-run setup, the app offers (but does not require) a 4-step practice run that teaches the user how the software works while simultaneously validating that the hardware and pipeline are working correctly.

**This is not a test suite — it's onboarding.** The user learns by doing, with real paper and real results, while the app quietly validates everything behind the scenes.

##### How It Appears in the App

After first-run setup completes, the home screen shows:

```
┌──────────────────────────────────────────────────┐
│                                                  │
│  ✓ Setup complete! Your scanner is connected.    │
│                                                  │
│  Before scanning your full stack, we recommend   │
│  a quick practice run. It takes about 10 minutes │
│  and uses just a few pages from your stack.      │
│                                                  │
│  You'll learn how everything works and we'll     │
│  make sure the scanner, AI, and saving all       │
│  work correctly with your actual documents.      │
│                                                  │
│  [ Start Practice Run ]                          │
│                                                  │
│  or  Skip and start scanning →                   │
│                                                  │
└──────────────────────────────────────────────────┘
```

##### Practice Run Steps (In-App)

The practice run is a wizard inside the app. Each step has instructions, does the real thing, and shows the user what to look for.

**Step 1 — "Let's scan one page"**
- App says: "Grab one page from your stack — any page. Put it face-up in the scanner tray."
- User clicks "Scan" — the page scans.
- App says: "Skip back sides for now."
- Processing runs. App shows the result: a document card with a PDF preview.
- App asks: "Does this look right? Can you read the text?" [Yes] [No, something's wrong]
- **What's validated behind the scenes:** Scanner connectivity, eSCL scan-receive loop, OCR, basic pipeline, output writing.

**Step 2 — "Now let's try double-sided pages"**
- App says: "Grab 3-5 pages. Try to include at least one that has printing on both sides."
- Walks the user through fronts → flip → backs with the same guided wizard as normal scanning.
- App shows results. Asks: "Check a double-sided page — is the front page followed by its back?"  [Yes] [No, the pages are mixed up]
- **What's validated:** Interleaving, blank page removal, two-pass workflow.

**Step 3 — "Let's see if the AI can sort your documents"**
- App says: "Grab 10-15 pages that contain a few different documents — maybe a lab report, a letter, and a radiology report. Don't worry about sorting them."
- Scan and process.
- App shows document cards. Asks: "Did we find the right number of documents? Are the boundaries correct?"
- If wrong, the app walks the user through making a correction (moving a boundary in the thumbnail strip) — **teaching corrections as part of the practice.**
- **What's validated:** AI splitting accuracy on real medical documents, metadata extraction, correction workflow.

**Step 4 — "Let's save and check the results"**
- App says: "Everything look good? Let's save these for real."
- User clicks Save.
- App shows where files were saved: "Your documents are in the output folder, organized by type."
- If PaperlessNGX is configured: "We also sent them to PaperlessNGX. Open it and search for [word from a document] to make sure it worked."
- **What's validated:** Full save pipeline, output folder structure, PaperlessNGX upload, tagging.

##### Completion

```
┌──────────────────────────────────────────────────┐
│                                                  │
│  ✓ Practice run complete!                        │
│                                                  │
│  Everything is working:                          │
│  ✓ Scanner connected and scanning               │
│  ✓ Double-sided pages handled correctly          │
│  ✓ AI document detection working                 │
│  ✓ Files saving to the right places              │
│  ✓ PaperlessNGX receiving documents              │
│                                                  │
│  You're ready to scan your full stack.           │
│  Start with a batch of ~50 pages and review      │
│  the results before continuing with the rest.    │
│                                                  │
│  [ Start Scanning ]                              │
│                                                  │
└──────────────────────────────────────────────────┘
```

The practice run can be re-run at any time from Settings. The documents scanned during practice are real — they're saved like any other session and don't need to be re-scanned.

##### Practice Run State

The practice run tracks which steps have been completed in `config/practice.json`. If the user quits mid-practice (e.g., to fix a printer issue), they resume where they left off. Steps 1-4 are sequential — can't skip ahead, because each builds on the previous.

### Layer 4: Resilience Tests

These verify the system handles failures gracefully and doesn't lose data.

| Scenario | Test Method | Expected Behavior |
|----------|-------------|-------------------|
| **Container restart mid-processing** | Kill container during pipeline execution | On restart: incomplete batch is detected, re-processable from last checkpoint |
| **NAS disconnects during output** | Unmount NAS volume mid-write | Error logged, batch stays in processing queue, retryable when NAS returns |
| **LLM API unreachable** | Block LLM endpoint | Pipeline pauses at split stage, batch queued for retry, clear error in UI |
| **AI returns garbage** | Mock returns invalid JSON | Validation catches, batch flagged for manual review, no data loss |
| **Disk full** | Fill tmpfs | Error before corruption, clear message, no partial files |
| **Duplicate batch submission** | Click "Scan Fronts" twice rapidly | Second click disabled during scan, or idempotent handling |

### Test Infrastructure

| Tool | Purpose |
|------|---------|
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support (FastAPI is async) |
| `respx` | Mock HTTP responses for eSCL and AI API |
| `pytest-tmpdir` | Isolated temp directories for output verification |
| `httpx` test client | FastAPI TestClient for API endpoint tests |

### CI Pipeline

```
pytest tests/unit/           # Layer 1: Fast, no I/O (<10s)
pytest tests/integration/    # Layer 2: Filesystem I/O, mocked services (<30s)
pytest tests/e2e/            # Layer 3a: Full container test (<120s)
```

Layer 3b (live printer) is manual, run once before each real scanning session.

### Test Coverage Target

| Module | Target | Rationale |
|--------|--------|-----------|
| `pipeline/interleave.py` | 100% | Core data integrity — wrong interleaving = corrupted documents |
| `pipeline/blank_detect.py` | 100% | Wrong detection = lost pages or noisy output |
| `pipeline/namer.py` | 100% | Pure logic, easy to test fully |
| `pipeline/splitter.py` | 95% | AI response validation must be bulletproof |
| `pipeline/output.py` | 95% | File I/O paths all exercised |
| `pipeline/ocr.py` | 90% | Some edge cases depend on Tesseract internals |
| `scanner/escl.py` | 90% | Network edge cases covered by integration tests |
| `api/*.py` | 80% | Route handlers, tested via integration/E2E |
| Overall | 90%+ | High confidence before touching real documents |

## Future Enhancements (Out of Scope for V1)

- **Barcode separator sheets**: Print barcode sheets from the app, insert between known document boundaries for higher accuracy.
- **Multi-scanner support**: Configure multiple printers.
- **Batch merge**: Combine results from multiple sessions.
- **Mobile-friendly UI**: Responsive design for tablet use at the scanner.
- **Progress notifications**: ntfy push when a session finishes processing.
- **Direct EHR upload**: MyChart/Epic patient portal API integration (if available).
- **Document deduplication**: Detect if a re-scanned document already exists.
