# ScanBox UI Specification

**Audience for this document:** Implementing agents building the web UI.
**Design source of truth:** This file defines the visual design, component library, and screen layouts. `docs/design.md` defines behavior and data flow.

---

## Design Direction

**Aesthetic:** Clinical warmth. Think of the best-designed medical device software — calm, trustworthy, precise, but not cold. Clean surfaces with purposeful depth. A hospital reception desk, not a hospital room.

**Tone:** Confident and guiding. The interface leads the user through each step without ever making them feel lost or confused. It tells you exactly what to do next.

**Target user:** A non-technical person (elderly family member, spouse) scanning medical documents for the first time. They may not know what "ADF" means. They need to feel confident, not intimidated.

**What makes it memorable:** The wizard flow. Loading documents, clicking "Scan," and watching pages appear in real-time feels like magic. The progress from raw paper to organized, named documents should feel effortless and satisfying.

---

## Tech Stack

| Tool | Version | Role | CDN/Vendor |
|------|---------|------|------------|
| htmx | 2.0.8 | Server communication, SSE progress, DOM swapping | Vendor `static/js/htmx.min.js` (~14KB) |
| Alpine.js | 3.15.x | Client-side UI state (dropdowns, modals, transitions) | Vendor `static/js/alpine.min.js` (~15KB) |
| Tailwind CSS | 4.2.x | Styling | Standalone CLI at Docker build time → `static/css/app.css` |
| Jinja2 | 3.1+ | Server-side HTML rendering | Python package |
| jinja2-fragments | 1.5+ | Render individual template blocks for htmx partials | Python package |
| Idiomorph | 0.3+ | Morph-based DOM swapping (preserves focus/scroll) | Vendor `static/js/idiomorph-ext.min.js` (~4KB) |

**No JavaScript build step.** All JS is vendored as static files. CSS is built once during Docker image construction.

---

## Typography

**Display font:** `DM Sans` — geometric, modern, highly legible at all sizes. Available on Google Fonts. Distinctive without being distracting. Works for medical/professional contexts.

**Body font:** `DM Sans` at regular weight. One font family keeps things simple and loads fast.

**Monospace (filenames, paths):** `JetBrains Mono` — clear distinction between similar characters (0/O, 1/l). Used only for filenames in the results view.

```css
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=JetBrains+Mono:wght@400&display=swap');
```

**Scale:**

| Use | Size | Weight | Line Height |
|-----|------|--------|-------------|
| Page heading (h1) | text-3xl (30px) | 700 | 1.2 |
| Section heading (h2) | text-2xl (24px) | 600 | 1.3 |
| Card title | text-lg (18px) | 600 | 1.4 |
| Body text | text-base (16px) | 400 | 1.5 |
| Instructions (scanning) | text-lg (18px) | 400 | 1.6 |
| Small label | text-sm (14px) | 500 | 1.4 |
| Filename (mono) | text-sm (14px) | 400 (JetBrains Mono) | 1.5 |

**All text at least 16px for body content.** No 12px text anywhere in the UI. Elderly users need larger text.

---

## Color System

```css
/* Tailwind CSS v4 @theme */
@theme {
  /* Primary — trustworthy blue */
  --color-brand-50: #eff6ff;
  --color-brand-100: #dbeafe;
  --color-brand-500: #3b82f6;
  --color-brand-600: #2563eb;
  --color-brand-700: #1d4ed8;

  /* Surface */
  --color-surface: #f8fafc;
  --color-surface-raised: #ffffff;
  --color-surface-active: #eff6ff;

  /* Text */
  --color-text-primary: #0f172a;
  --color-text-secondary: #475569;
  --color-text-muted: #94a3b8;

  /* Status — colorblind-safe (always paired with icon + text) */
  --color-status-success: #16a34a;
  --color-status-warning: #d97706;
  --color-status-error: #dc2626;
  --color-status-info: #2563eb;
  --color-status-processing: #7c3aed;

  /* Border */
  --color-border: #e2e8f0;
  --color-border-focus: #2563eb;

  /* Radius */
  --radius-sm: 0.5rem;
  --radius-md: 0.75rem;
  --radius-lg: 1rem;
  --radius-xl: 1.25rem;
}
```

**Rules:**
- **Never use color alone to convey meaning.** Every status has an icon + text label.
- **No dark mode.** Adds cognitive overhead for elderly users and doubles testing surface.
- **Background is `surface` (#f8fafc), not pure white.** Cards and modals use `surface-raised` (#ffffff) for elevation.
- **AAA contrast (7:1) for all body text.** Primary text (#0f172a) on surface (#f8fafc) = 15.7:1.

---

## Component Library

All components are Jinja2 macros in `scanbox/templates/components/`. htmx attributes are on the consuming template, not inside the macro — macros are presentation-only.

### Buttons

```jinja2
{# components/button.html #}
{% macro button(text, variant="primary", size="lg", type="button", attrs="") %}
<button type="{{ type }}"
        class="inline-flex items-center justify-center gap-2 font-semibold
               rounded-lg transition-all duration-150
               focus-visible:outline-3 focus-visible:outline-offset-2
               focus-visible:outline-brand-600
               disabled:opacity-50 disabled:cursor-not-allowed
               {% if variant == 'primary' %}
                 bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-800
               {% elif variant == 'secondary' %}
                 bg-white text-brand-600 border-2 border-brand-200
                 hover:border-brand-400 hover:bg-brand-50 active:bg-brand-100
               {% elif variant == 'danger' %}
                 bg-status-error text-white hover:bg-red-700 active:bg-red-800
               {% elif variant == 'ghost' %}
                 bg-transparent text-text-secondary hover:bg-gray-100 active:bg-gray-200
               {% endif %}
               {% if size == 'xl' %}
                 text-lg px-8 py-4 min-h-14
               {% elif size == 'lg' %}
                 text-base px-6 py-3 min-h-12
               {% elif size == 'md' %}
                 text-sm px-4 py-2 min-h-10
               {% endif %}"
        {{ attrs }}>
  {{ caller() if caller else text }}
</button>
{% endmacro %}
```

**Primary action buttons are always `size="xl"` on scanning screens.** The main "Scan" button must be impossible to miss.

### Status Badge

```jinja2
{# components/status.html #}
{% macro status_badge(status, text=None) %}
{% set display = text or status | title %}
{% set configs = {
  'ready': {'bg': 'bg-green-100', 'text': 'text-green-800', 'icon': 'check-circle'},
  'scanning': {'bg': 'bg-blue-100', 'text': 'text-blue-800', 'icon': 'loader'},
  'processing': {'bg': 'bg-violet-100', 'text': 'text-violet-800', 'icon': 'cog'},
  'review': {'bg': 'bg-amber-100', 'text': 'text-amber-800', 'icon': 'eye'},
  'saved': {'bg': 'bg-green-100', 'text': 'text-green-800', 'icon': 'check'},
  'error': {'bg': 'bg-red-100', 'text': 'text-red-800', 'icon': 'alert-triangle'},
  'offline': {'bg': 'bg-gray-100', 'text': 'text-gray-800', 'icon': 'wifi-off'},
} %}
{% set cfg = configs.get(status, configs.error) %}
<span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full
             text-sm font-medium {{ cfg.bg }} {{ cfg.text }}">
  {% include "icons/" ~ cfg.icon ~ ".svg" %}
  {{ display }}
</span>
{% endmacro %}
```

### Document Card

```jinja2
{# components/document_card.html #}
{% macro document_card(doc, editable=true) %}
<article class="group relative rounded-xl border-2 bg-surface-raised overflow-hidden
                transition-all duration-150
                {% if doc.confidence < 0.7 %}
                  border-status-warning shadow-amber-100
                {% else %}
                  border-border hover:border-brand-500 hover:shadow-lg
                {% endif %}"
         id="doc-{{ doc.id }}">

  {# Thumbnail #}
  <div class="aspect-[3/4] bg-gray-100 relative overflow-hidden">
    <img src="/api/documents/{{ doc.id }}/thumbnail"
         alt="Preview of {{ doc.description }}"
         class="w-full h-full object-cover"
         loading="lazy"
         onerror="this.src='/static/img/pdf-placeholder.svg'">
    {% if doc.confidence < 0.7 %}
    <div class="absolute top-3 right-3">
      {{ status_badge('review', 'Needs review') }}
    </div>
    {% endif %}
  </div>

  {# Card body #}
  <div class="p-4">
    <h3 class="font-semibold text-text-primary truncate text-lg">
      {{ doc.document_type }}
    </h3>
    <p class="text-text-secondary mt-1">
      {% if doc.date_of_service != 'unknown' %}
        {{ doc.date_of_service | format_date }}
      {% else %}
        <span class="text-status-warning">Date unknown</span>
      {% endif %}
    </p>
    <p class="text-text-secondary text-sm mt-0.5 truncate">
      {% if doc.facility != 'unknown' %}{{ doc.facility }}{% endif %}
    </p>
    <p class="text-text-muted text-sm mt-1 truncate">
      {{ doc.description }}
    </p>
    {% if doc.user_edited %}
    <p class="text-xs text-brand-600 mt-2 flex items-center gap-1">
      {% include "icons/pencil.svg" %} Edited by you
    </p>
    {% endif %}
  </div>

  {# Actions #}
  {% if editable %}
  <div class="px-4 pb-4 flex gap-2">
    <button hx-get="/api/documents/{{ doc.id }}/preview"
            hx-target="#preview-panel" hx-swap="innerHTML"
            class="flex-1 py-2.5 text-sm font-medium rounded-lg border-2
                   border-border hover:border-brand-400 hover:bg-brand-50
                   min-h-11 transition-colors">
      View
    </button>
    <button hx-get="/api/documents/{{ doc.id }}/edit"
            hx-target="#doc-{{ doc.id }}" hx-swap="outerHTML"
            class="flex-1 py-2.5 text-sm font-medium rounded-lg
                   bg-brand-600 text-white hover:bg-brand-700
                   min-h-11 transition-colors">
      {% if doc.confidence < 0.7 %}Fix This{% else %}Edit{% endif %}
    </button>
  </div>
  {% endif %}
</article>
{% endmacro %}
```

### Progress Bar

```jinja2
{# components/progress.html #}
{% macro progress_bar(label, detail="", percent=None) %}
<div class="space-y-2" role="region" aria-label="{{ label }}">
  <div class="flex items-center justify-between">
    <span class="text-lg font-medium text-text-primary">{{ label }}</span>
    <span class="text-sm text-text-secondary">{{ detail }}</span>
  </div>
  {% if percent is not none %}
  <div class="h-3 bg-gray-200 rounded-full overflow-hidden"
       role="progressbar" aria-valuenow="{{ percent }}"
       aria-valuemin="0" aria-valuemax="100"
       aria-label="{{ label }}: {{ percent }}%">
    <div class="h-full bg-brand-600 rounded-full transition-all duration-300
                ease-out"
         style="width: {{ percent }}%"></div>
  </div>
  {% else %}
  {# Indeterminate — animated pulse #}
  <div class="h-3 bg-gray-200 rounded-full overflow-hidden">
    <div class="h-full w-1/3 bg-brand-600 rounded-full animate-pulse"></div>
  </div>
  {% endif %}
</div>
{% endmacro %}
```

### Toast Notifications

Driven by htmx `HX-Trigger` response header + Alpine.js toast stack.

**Server sends:**
```python
response.headers["HX-Trigger"] = json.dumps({
    "showToast": {"message": "Document saved", "type": "success"}
})
```

**Client receives:** Alpine.js `toastManager` component in `base.html` catches the event, shows a slide-up toast with auto-dismiss after 5 seconds. Toast types: `success` (green), `error` (red), `warning` (amber), `info` (blue).

---

## Screen Layouts

### Layout Shell (`base.html`)

```
┌──────────────────────────────────────────────────┐
│  ┌─────┐                                         │
│  │ Logo│  ScanBox            [Settings]           │
│  └─────┘                                         │
├──────────────────────────────────────────────────┤
│                                                  │
│  ← Back     Breadcrumb > Trail > Here            │
│                                                  │
│  ┌──────────────────────────────────────────┐    │
│  │                                          │    │
│  │              Page Content                │    │
│  │              (block: content)             │    │
│  │                                          │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  ── Scanner Status ──────────────────────────    │
│  ● Online — Scanner ready                        │
│                                                  │
└──────────────────────────────────────────────────┘
```

- **Max width:** `max-w-4xl` (896px) centered. Wider screens get generous margins.
- **Scanner status bar** at the bottom, always visible. Polls via htmx every 5 seconds. Shows green/amber/red dot + plain English status.
- **Breadcrumb** shows navigation path. Back button for one-level up.
- **No sidebar.** Linear flow. Users navigate forward and back, not across.

### Home Screen (`index.html`)

```
┌──────────────────────────────────────────────────┐
│                                                  │
│  ┌──────────────────────────────────────────┐    │
│  │                                          │    │
│  │  Ready to scan?                          │    │
│  │                                          │    │
│  │  Person: [ John Doe            ▼ ]       │    │
│  │          + Add someone new               │    │
│  │                                          │    │
│  │  [ ─────── Start Scanning ─────── ]      │    │
│  │            (primary, size=xl)             │    │
│  │                                          │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  ── Past Sessions ───────────────────────────    │
│                                                  │
│  ┌──────────────┐  ┌──────────────┐              │
│  │ Mar 28, 2026 │  │ Mar 15, 2026 │              │
│  │ John Doe     │  │ Jane Doe     │              │
│  │ 48 documents │  │ 12 documents │              │
│  │ ✓ Saved      │  │ ✓ Saved      │              │
│  └──────────────┘  └──────────────┘              │
│                                                  │
└──────────────────────────────────────────────────┘
```

- **One primary action** dominates the screen: "Start Scanning."
- Past sessions are below, de-emphasized. Cards, not a table.
- Person selector is a dropdown with "Add someone new" at the bottom.

### Scan Wizard (`scan.html`)

Three numbered steps. Only the active step is expanded. Completed steps show a green checkmark and collapse. Future steps are dimmed.

**Step 1 — Load & Scan Fronts:**

```
┌──────────────────────────────────────────────────┐
│  Scanning — John Doe — Batch 1                   │
│                                                  │
│  ① Scan Front Sides                              │
│  ┌──────────────────────────────────────────┐    │
│  │                                          │    │
│  │  ┌───────────────────────────────┐       │    │
│  │  │                               │       │    │
│  │  │  [Illustration: paper going   │       │    │
│  │  │   into ADF tray, face up,     │       │    │
│  │  │   with arrow showing          │       │    │
│  │  │   direction]                  │       │    │
│  │  │                               │       │    │
│  │  └───────────────────────────────┘       │    │
│  │                                          │    │
│  │  Place your documents face-up in the     │    │
│  │  scanner's top tray. Up to 50 pages.     │    │
│  │                                          │    │
│  │  [ ────── Scan Front Sides ────── ]      │    │
│  │           (primary, size=xl)              │    │
│  │                                          │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  ② Flip & Scan Back Sides           (dimmed)     │
│  ③ Review                           (dimmed)     │
│                                                  │
└──────────────────────────────────────────────────┘
```

**During scanning (replaces button via htmx SSE):**

```
│  │  Scanning...                             │    │
│  │                                          │    │
│  │  ┌────────────────────────────────┐      │    │
│  │  │  ████████████░░░░░░░░░░░░░░░░  │      │    │
│  │  │  23 pages scanned              │      │    │
│  │  └────────────────────────────────┘      │    │
│  │                                          │    │
│  │  The scanner is feeding pages...         │    │
│  │  This will finish when the tray          │    │
│  │  is empty.                               │    │
```

Progress is indeterminate (we don't know total pages). The count increments in real-time via SSE. The progress bar pulses.

**Step 2 — Flip & Scan Backs:**

After fronts complete, step 1 collapses with a checkmark, step 2 expands:

```
│  ✓ 47 front pages scanned                       │
│                                                  │
│  ② Flip & Scan Back Sides                        │
│  ┌──────────────────────────────────────────┐    │
│  │                                          │    │
│  │  ┌───────────────────────────────┐       │    │
│  │  │  [Illustration: stack being   │       │    │
│  │  │   flipped upside down, with   │       │    │
│  │  │   arrows showing the flip     │       │    │
│  │  │   motion]                     │       │    │
│  │  └───────────────────────────────┘       │    │
│  │                                          │    │
│  │  Take the stack from the output tray,    │    │
│  │  flip it face-down, and put it back in   │    │
│  │  the top tray.                           │    │
│  │                                          │    │
│  │  [ ────── Scan Back Sides ─────── ]      │    │
│  │                                          │    │
│  │  or  No back sides — skip this →         │    │
│  │                                          │    │
│  └──────────────────────────────────────────┘    │
```

"Skip" is a text link, not a button. The primary action (scan backs) is dominant.

**Step 3 — Processing + Review:**

After backs (or skip), step 3 shows processing progress via SSE:

```
│  ✓ 47 front pages scanned                       │
│  ✓ 47 back pages scanned                        │
│                                                  │
│  ③ Review                                        │
│  ┌──────────────────────────────────────────┐    │
│  │                                          │    │
│  │  Processing your documents...            │    │
│  │                                          │    │
│  │  ┌────────────────────────────────┐      │    │
│  │  │  ████████████████░░░░░░░░░░░░  │      │    │
│  │  │  Reading text... (page 31/47)  │      │    │
│  │  └────────────────────────────────┘      │    │
│  │                                          │    │
│  │  You can start a new batch while this    │    │
│  │  finishes.                               │    │
│  │                                          │    │
│  │  [ Start Next Batch ]   (secondary)      │    │
│  │                                          │    │
│  └──────────────────────────────────────────┘    │
```

When processing completes, the step transitions to showing document cards (redirects to results page).

### Results Screen (`results.html`)

```
┌──────────────────────────────────────────────────┐
│                                                  │
│  12 documents found in Batch 1                   │
│                                                  │
│  ┌────────┐  ┌────────┐  ┌────────┐             │
│  │  PDF   │  │  PDF   │  │  PDF   │             │
│  │ thumb  │  │ thumb  │  │ thumb  │             │
│  │        │  │        │  │   ⚠    │             │
│  │Radiol. │  │Disch.  │  │Needs   │             │
│  │Report  │  │Summary │  │Review  │             │
│  │Jun 15  │  │Jun 14  │  │Date ?  │             │
│  │Memorial│  │Memorial│  │        │             │
│  │        │  │        │  │        │             │
│  │[View]  │  │[View]  │  │[Fix    │             │
│  │[Edit]  │  │[Edit]  │  │ This]  │             │
│  └────────┘  └────────┘  └────────┘             │
│                                                  │
│  ... more cards ...                              │
│                                                  │
│  ────────────────────────────────────────────    │
│                                                  │
│  Everything look right?                          │
│                                                  │
│  [ ─────────── Save ────────────── ]             │
│            (primary, size=xl)                    │
│                                                  │
│  Need to fix something? Tap "Edit" or "Fix       │
│  This" on any document above.                    │
│                                                  │
└──────────────────────────────────────────────────┘
```

- Cards with amber border = low confidence, need review.
- "Save" is the single dominant action at the bottom.
- No separate "Fix" mode — editing is always available via the card buttons.
- Responsive grid: 1 column on mobile, 2 on medium, 3 on large.

### Document Boundary Editor

When the user needs to adjust where documents start/end. Shown as a horizontal scrollable thumbnail strip with clickable gaps:

```
┌──────────────────────────────────────────────────┐
│  Adjust Document Boundaries                      │
│                                                  │
│  Tap between pages to mark where one document    │
│  ends and the next begins.                       │
│                                                  │
│  ┌──┐ ┌──┐ ┌──┐ │ ┌──┐ ┌──┐ │ ┌──┐ ┌──┐ ┌──┐  │
│  │1 │ │2 │ │3 │ │ │4 │ │5 │ │ │6 │ │7 │ │8 │  │
│  └──┘ └──┘ └──┘ │ └──┘ └──┘ │ └──┘ └──┘ └──┘  │
│  ← Document 1 → │ ← Doc 2 → │ ← Document 3 →   │
│                                                  │
│  ← scroll horizontally →                        │
│                                                  │
│  Tap a page to see it full size.                 │
│                                                  │
│  ┌──────────────────────────────────────────┐    │
│  │                                          │    │
│  │  [Full-size preview of selected page]    │    │
│  │                                          │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  [ Cancel ]              [ Apply Changes ]       │
│                                                  │
└──────────────────────────────────────────────────┘
```

- Dividers (│) are clickable gaps between thumbnails. Tap to add/remove.
- Tapping a thumbnail shows it full-size below for reading content.
- "Apply Changes" sends the new boundary positions to the server via htmx.
- Entire interaction is one htmx swap — no page navigation.

### Setup Wizard (`setup.html`)

Full-screen, centered, no chrome. One step at a time. Each step has a large illustration, 1-2 sentences, and one action.

```
┌──────────────────────────────────────────────────┐
│                                                  │
│            ┌──────────────────────┐              │
│            │  [Scanner icon]      │              │
│            └──────────────────────┘              │
│                                                  │
│         Looking for your scanner...              │
│                                                  │
│            ┌──────────────────────┐              │
│            │  ✓ Found!            │              │
│            │  HP M283cdw          │              │
│            │  192.168.10.11       │              │
│            └──────────────────────┘              │
│                                                  │
│         [ ────── Continue ─────── ]              │
│                                                  │
│         Step 1 of 5   ● ○ ○ ○ ○                 │
│                                                  │
└──────────────────────────────────────────────────┘
```

Steps are server-driven via htmx. Each "Continue" swaps in the next step.

---

## Interaction Patterns

### htmx + Jinja2 Fragment Pattern

Every page has a full-page template and named blocks. Direct navigation renders the full page. htmx requests render just the block:

```python
# FastAPI route
@app.get("/batches/{batch_id}/results")
async def batch_results(request: Request, batch_id: str):
    batch = await get_batch(batch_id)
    block = "cards" if request.headers.get("HX-Request") else None
    return templates.TemplateResponse(
        "results.html", {"batch": batch}, block_name=block
    )
```

```jinja2
{# results.html #}
{% extends "base.html" %}
{% block content %}
  <h1>{{ batch.document_count }} documents found</h1>
  {% block cards %}
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {% for doc in batch.documents %}
        {{ document_card(doc) }}
      {% endfor %}
    </div>
  {% endblock %}
  {% block actions %}
    {{ button("Save", variant="primary", size="xl",
              attrs='hx-post="/api/sessions/' ~ batch.session_id ~ '/save"
                     hx-target="#save-result"') }}
  {% endblock %}
{% endblock %}
```

### SSE Progress (Scanning + Processing)

```html
{# Scanning progress — updates via SSE #}
<div hx-ext="sse" sse-connect="/api/batches/{{ batch_id }}/progress"
     sse-swap="progress" hx-swap="morph:innerHTML"
     id="progress-container">
  <div class="text-center py-8">
    <div class="animate-pulse text-lg text-text-secondary">
      Starting scanner...
    </div>
  </div>
</div>
```

Server sends named SSE events (`event: progress`) with HTML fragments that replace the progress container content. The `morph:innerHTML` swap preserves focus state.

### Inline Edit via htmx

When the user clicks "Edit" on a document card:
1. htmx `GET /api/documents/{id}/edit` returns an edit-mode card (form)
2. The form replaces the card via `outerHTML` swap
3. On save: `PUT /api/documents/{id}` returns the updated display-mode card
4. On cancel: `GET /api/documents/{id}/card` returns the original display-mode card

No page navigation. No modals. The card transforms in place.

### Toast Notifications

All save/error/success feedback uses the toast system (see Component Library above). Server sends `HX-Trigger: {"showToast": {...}}` response header. Alpine.js toast manager in `base.html` catches the event.

---

## Accessibility

- **WCAG 2.2 AA minimum, AAA target for text contrast**
- **48px minimum touch targets** for all interactive elements
- **`aria-live="polite"`** on all dynamic update regions (progress, results, toasts)
- **`aria-busy`** toggled during htmx requests on swap targets
- **Focus management:** `autofocus` on the first input of newly swapped forms. Idiomorph extension preserves focus during morph swaps.
- **`role="progressbar"`** with `aria-valuenow` on all progress bars
- **Keyboard navigation:** All interactive elements reachable via Tab. Escape closes edit forms.
- **No color-only indicators:** Every status badge has icon + text
- **Skip-to-content link** in `base.html` for screen reader users

---

## Responsive Behavior

| Breakpoint | Layout |
|-----------|--------|
| < 640px (mobile) | Single column. Full-width buttons. Stack vertically. |
| 640-1023px (tablet) | 2-column card grid. Side-by-side buttons. |
| 1024px+ (desktop) | 3-column card grid. Max-width container (896px). |

The primary use case is desktop/laptop (user is at a desk near the scanner). Tablet is secondary. Full mobile is not a V1 target, but the layout should degrade gracefully.

---

## PDF Thumbnails

Rendered server-side during processing (Stage 5). Stored as JPEG files in the batch directory. Served via a FastAPI endpoint:

```
GET /api/documents/{id}/thumbnail → JPEG (300px wide, aspect 3:4)
```

Use `pikepdf` + `pdf2image` (or PyMuPDF if license permits for internal use) to render page 1 at 150 DPI, scale to 300px wide, save as JPEG quality 85.

Lazy-loaded with `loading="lazy"` and a CSS `aspect-[3/4]` placeholder to prevent layout shift.

---

## Illustrations

The scanning wizard needs 2-3 simple illustrations:
1. **Paper going into ADF tray** (face up, with arrow)
2. **Stack being flipped** (face down, with rotation arrow)
3. **Scanner feeding pages** (animated, optional)

These should be simple SVG line drawings — clean, minimal, not clip art. Think IKEA instruction manual style. Create them as inline SVG in the templates for easy theming with Tailwind colors.

---

## File Organization

```
scanbox/templates/
├── base.html                   # Layout shell, nav, toast container, scanner status
├── components/
│   ├── button.html             # Button macro (primary, secondary, danger, ghost)
│   ├── status.html             # Status badge macro
│   ├── document_card.html      # Document card macro (display + edit states)
│   ├── progress.html           # Progress bar macro (determinate + indeterminate)
│   └── toast.html              # Toast notification Alpine component
├── icons/                      # Inline SVG icon files
│   ├── check-circle.svg
│   ├── loader.svg
│   ├── alert-triangle.svg
│   └── ...
├── index.html                  # Home: new session + past sessions
├── scan.html                   # Scan wizard: 3-step flow
├── results.html                # Results: document card grid + save
├── setup.html                  # First-run setup wizard
├── practice.html               # Guided practice run
└── settings.html               # Person management, integrations

static/
├── css/
│   ├── input.css               # Tailwind v4 input (imports, @theme, @utility)
│   └── app.css                 # Generated by Tailwind CLI at build time
├── js/
│   ├── htmx.min.js             # Vendored htmx 2.0.8
│   ├── idiomorph-ext.min.js    # Vendored Idiomorph extension
│   └── alpine.min.js           # Vendored Alpine.js 3.15.x
└── img/
    ├── logo.svg                # ScanBox logo
    ├── pdf-placeholder.svg     # Fallback when thumbnail fails to load
    ├── scan-face-up.svg        # Wizard illustration: paper face up
    └── scan-flip.svg           # Wizard illustration: flip stack
```
