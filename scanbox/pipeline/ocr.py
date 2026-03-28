"""OCR processing via ocrmypdf with per-page text extraction."""

import json
import subprocess
from pathlib import Path

import pytesseract
from pdf2image import convert_from_path


def extract_text_by_page(pdf_path: Path) -> dict[int, str]:
    """Extract OCR text from each page, returning {page_num: text} (1-indexed)."""
    images = convert_from_path(str(pdf_path), dpi=300)
    page_texts = {}
    for i, img in enumerate(images):
        text = pytesseract.image_to_string(img)
        page_texts[i + 1] = text
    return page_texts


def run_ocr(
    input_path: Path,
    output_path: Path,
    text_json_path: Path,
    language: str = "eng",
) -> None:
    """Run OCR on a PDF: create searchable PDF and extract per-page text.

    Args:
        input_path: Input PDF (may or may not have text layer).
        output_path: Output searchable PDF.
        text_json_path: Path to write {page_num: text} JSON.
        language: Tesseract language code.
    """
    # Create searchable PDF with ocrmypdf
    subprocess.run(
        [
            "ocrmypdf",
            "--language",
            language,
            "--deskew",
            "--skip-text",  # Don't re-OCR pages that already have text
            "--output-type",
            "pdf",
            str(input_path),
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )

    # Extract text per page from the OCR'd PDF
    page_texts = extract_text_by_page(output_path)

    text_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(text_json_path, "w") as f:
        json.dump(page_texts, f, indent=2)
