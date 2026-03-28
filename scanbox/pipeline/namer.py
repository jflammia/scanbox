"""Medical document filename generation.

Pattern: YYYY-MM-DD_PersonName_DocumentType_Facility_Description.pdf
"""

import re
import unicodedata


def sanitize_filename(text: str, max_length: int = 60) -> str:
    """Sanitize text for use in a filename."""
    # Normalize unicode
    text = unicodedata.normalize("NFKD", text)
    # Remove non-ASCII
    text = text.encode("ascii", "ignore").decode("ascii")
    # Strip apostrophes (O'Brien -> OBrien) before general replacement
    text = text.replace("'", "")
    # Replace spaces and special chars with hyphens
    text = re.sub(r"[^a-zA-Z0-9-]", "-", text)
    # Collapse multiple hyphens
    text = re.sub(r"-+", "-", text)
    # Strip leading/trailing hyphens
    text = text.strip("-")
    # Truncate without cutting mid-word
    if len(text) > max_length:
        text = text[:max_length].rsplit("-", 1)[0]
    return text


def generate_filename(
    person_name: str,
    document_type: str,
    date_of_service: str = "unknown",
    facility: str = "unknown",
    description: str = "Document",
    duplicate_index: int = 0,
) -> str:
    """Generate a medical-professional filename from metadata."""
    date_part = "Unknown-Date" if date_of_service == "unknown" else date_of_service
    person_part = sanitize_filename(person_name, max_length=30)
    type_part = sanitize_filename(document_type, max_length=30)
    desc_part = sanitize_filename(description, max_length=50)

    parts = [date_part, person_part, type_part]

    if facility and facility != "unknown":
        parts.append(sanitize_filename(facility, max_length=30))

    parts.append(desc_part)

    base = "_".join(parts)

    if duplicate_index > 0:
        return f"{base}-{duplicate_index}.pdf"
    return f"{base}.pdf"
