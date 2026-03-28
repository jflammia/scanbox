"""Blank page detection and removal.

Renders each PDF page to a low-res image and measures ink coverage
(percentage of non-white pixels). Pages below the threshold are blank.
"""

from dataclasses import dataclass, field
from pathlib import Path

import pikepdf
from pdf2image import convert_from_path


@dataclass
class BlankRemovalResult:
    cleaned_path: Path
    removed_indices: list[int] = field(default_factory=list)
    total_pages: int = 0


def ink_coverage(image) -> float:
    """Calculate the fraction of non-white pixels in an image."""
    gray = image.convert("L")  # grayscale: 0=black, 255=white
    pixels = gray.tobytes()
    non_white = sum(1 for p in pixels if p < 250)
    return non_white / len(pixels)


def detect_blank_pages(pdf_path: Path, threshold: float = 0.01) -> list[int]:
    """Return 0-indexed list of page numbers that are blank."""
    images = convert_from_path(str(pdf_path), dpi=150)
    blanks = []
    for i, img in enumerate(images):
        if ink_coverage(img) < threshold:
            blanks.append(i)
    return blanks


def remove_blank_pages(
    input_path: Path,
    output_path: Path,
    threshold: float = 0.01,
) -> BlankRemovalResult:
    """Remove blank pages from a PDF, preserving page order.

    Returns a result with the cleaned PDF path and which pages were removed.
    """
    pdf = pikepdf.Pdf.open(input_path)
    total = len(pdf.pages)
    blanks = detect_blank_pages(input_path, threshold)

    if not blanks:
        pdf.save(output_path)
        return BlankRemovalResult(cleaned_path=output_path, removed_indices=[], total_pages=total)

    result_pdf = pikepdf.Pdf.new()
    for i in range(total):
        if i not in blanks:
            result_pdf.pages.append(pdf.pages[i])

    result_pdf.save(output_path)
    return BlankRemovalResult(cleaned_path=output_path, removed_indices=blanks, total_pages=total)
