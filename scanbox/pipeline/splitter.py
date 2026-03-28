"""AI-powered document boundary detection and classification.

Uses litellm==1.82.6 (PINNED — versions 1.82.7/1.82.8 were compromised in a
supply chain attack, March 2026. See .claude/rules/tech-stack-2026.md) to call
any LLM provider (Anthropic, OpenAI, Ollama) with the same prompt. The
validation layer ensures the LLM output is structurally correct before use.
"""

import json

import litellm

from scanbox.config import config
from scanbox.models import SplitDocument


class SplitValidationError(ValueError):
    """Raised when LLM split output fails structural validation."""


SYSTEM_PROMPT = (
    "You are a document analysis assistant. You analyze OCR text from scanned "
    "medical documents and identify document boundaries.\n\n"
    "Return ONLY a JSON array. No markdown, no explanation. Each element:\n"
    "{\n"
    '  "start_page": <int, 1-indexed>,\n'
    '  "end_page": <int, 1-indexed>,\n'
    '  "document_type": "<one of: Radiology Report, Discharge Summary, Care Plan, '
    "Lab Results, Letter, Operative Report, Progress Note, Pathology Report, "
    'Prescription, Insurance, Billing, Other>",\n'
    '  "date_of_service": "<YYYY-MM-DD or \'unknown\'>",\n'
    '  "facility": "<name or \'unknown\'>",\n'
    '  "provider": "<doctor name or \'unknown\'>",\n'
    '  "description": "<3-8 word description>",\n'
    '  "confidence": <0.0-1.0>\n'
    "}"
)


def build_prompt(page_texts: dict[int, str], person_name: str) -> str:
    """Build the user prompt with OCR text for all pages."""
    lines = [
        f"Analyze these {len(page_texts)} scanned pages. "
        f"They are medical documents for patient: {person_name}.",
        "",
    ]
    for page_num in sorted(page_texts.keys()):
        lines.append(f"---PAGE {page_num}---")
        lines.append(page_texts[page_num])
        lines.append("")
    return "\n".join(lines)


def validate_splits(raw_splits: list[dict], total_pages: int) -> list[SplitDocument]:
    """Validate that split boundaries are contiguous, non-overlapping, and cover all pages."""
    if not raw_splits:
        raise SplitValidationError("LLM returned empty splits list")

    # Sort by start_page
    sorted_splits = sorted(raw_splits, key=lambda s: s["start_page"])

    docs = []
    for s in sorted_splits:
        start = s.get("start_page", 0)
        end = s.get("end_page", 0)

        if start > end:
            raise SplitValidationError(f"start_page ({start}) > end_page ({end}) — invalid range")

        docs.append(
            SplitDocument(
                start_page=start,
                end_page=end,
                document_type=s.get("document_type", "Other"),
                date_of_service=s.get("date_of_service", "unknown"),
                facility=s.get("facility", "unknown"),
                provider=s.get("provider", "unknown"),
                description=s.get("description", "Document"),
                confidence=max(0.0, min(1.0, float(s.get("confidence", 0.5)))),
            )
        )

    # Check contiguous coverage
    for i in range(len(docs) - 1):
        current_end = docs[i].end_page
        next_start = docs[i + 1].start_page
        if next_start > current_end + 1:
            raise SplitValidationError(
                f"gap between pages {current_end} and {next_start} — "
                f"pages {current_end + 1}-{next_start - 1} not covered"
            )
        if next_start <= current_end:
            raise SplitValidationError(
                f"overlap: document ending at page {current_end} "
                f"overlaps with document starting at page {next_start}"
            )

    # Check first and last page coverage
    if docs[0].start_page != 1:
        raise SplitValidationError(f"Pages 1-{docs[0].start_page - 1} not covered by any document")
    if docs[-1].end_page != total_pages:
        raise SplitValidationError(
            f"Pages {docs[-1].end_page + 1}-{total_pages} not covered by any document"
        )

    return docs


async def split_documents(
    page_texts: dict[int, str],
    person_name: str,
) -> list[SplitDocument]:
    """Call the LLM to split and classify documents, then validate."""
    prompt = build_prompt(page_texts, person_name)
    total_pages = len(page_texts)

    response = await litellm.acompletion(
        model=config.llm_model_id(),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    content = response.choices[0].message.content
    parsed = json.loads(content)

    # Handle both {"documents": [...]} and [...] formats
    if isinstance(parsed, dict) and "documents" in parsed:
        raw_splits = parsed["documents"]
    elif isinstance(parsed, list):
        raw_splits = parsed
    else:
        raise SplitValidationError(f"Unexpected response format: {type(parsed)}")

    return validate_splits(raw_splits, total_pages)
