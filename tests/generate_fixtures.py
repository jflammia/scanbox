"""Generate synthetic medical document PDFs for testing.

Creates realistic-looking pages with letterheads, dates, and report structures
but containing no real PHI. These are used by unit and integration tests.
"""

from pathlib import Path

import pikepdf
from PIL import Image, ImageDraw

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def create_text_page_pdf(text: str, output_path: Path, dpi: int = 300) -> None:
    """Create a single-page PDF with the given text content."""
    # US Letter at specified DPI
    width = int(8.5 * dpi)
    height = int(11 * dpi)

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # Use default font, draw text starting near top-left
    y_offset = int(0.5 * dpi)
    x_offset = int(0.75 * dpi)
    for line in text.split("\n"):
        draw.text((x_offset, y_offset), line, fill="black")
        y_offset += int(0.18 * dpi)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PDF", resolution=dpi)


def create_blank_page_pdf(output_path: Path, dpi: int = 300) -> None:
    """Create a blank white page PDF."""
    width = int(8.5 * dpi)
    height = int(11 * dpi)
    img = Image.new("RGB", (width, height), "white")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PDF", resolution=dpi)


def create_near_blank_page_pdf(output_path: Path, dpi: int = 300) -> None:
    """Create a nearly blank page with a small smudge (<1% ink coverage)."""
    width = int(8.5 * dpi)
    height = int(11 * dpi)
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    # Small smudge in corner
    draw.ellipse([10, 10, 30, 30], fill="gray")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PDF", resolution=dpi)


def merge_pdfs(input_paths: list[Path], output_path: Path) -> None:
    """Merge multiple single-page PDFs into one multi-page PDF."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged = pikepdf.Pdf.new()
    for path in input_paths:
        src = pikepdf.Pdf.open(path)
        merged.pages.extend(src.pages)
    merged.save(output_path)


RADIOLOGY_REPORT_P1 = """MEMORIAL HOSPITAL
Department of Radiology

RADIOLOGY REPORT

Patient: John Doe
DOB: 01/15/1955
Date of Service: 06/15/2025
Ordering Physician: Dr. Sarah Johnson
Exam: CT Abdomen and Pelvis with Contrast

CLINICAL HISTORY: Abdominal pain, rule out appendicitis.

TECHNIQUE: CT of the abdomen and pelvis was performed with IV contrast.

FINDINGS:
The liver, spleen, pancreas, and adrenal glands are unremarkable.
No evidence of appendicitis. The appendix measures 5mm in diameter.
No free fluid or free air. No lymphadenopathy.
"""

RADIOLOGY_REPORT_P2 = """MEMORIAL HOSPITAL — Page 2

IMPRESSION:
1. No evidence of acute appendicitis.
2. Normal CT of the abdomen and pelvis.

Electronically signed by:
Dr. Michael Chen, MD
Board Certified Radiologist
06/15/2025 14:30
"""

DISCHARGE_SUMMARY_P1 = """JOHNS HOPKINS HOSPITAL
Baltimore, MD 21287

DISCHARGE SUMMARY

Patient: John Doe
MRN: 1234567
Admission Date: 03/20/2025
Discharge Date: 03/22/2025
Attending: Dr. Robert Patel

PRINCIPAL DIAGNOSIS: Acute appendicitis, status post laparoscopic appendectomy

HOSPITAL COURSE:
Patient presented to the ED with acute right lower quadrant pain.
CT confirmed acute appendicitis. Taken to OR for laparoscopic appendectomy.
Procedure was uncomplicated. Post-operative course was unremarkable.
"""

LAB_RESULTS = """QUEST DIAGNOSTICS
Order Number: QD-2025-789456

COMPREHENSIVE METABOLIC PANEL

Patient: John Doe
Collected: 05/22/2025 08:15
Reported: 05/22/2025 14:30

Test                Result    Reference Range    Flag
Glucose             95 mg/dL  70-100
BUN                 18 mg/dL  7-20
Creatinine          1.1 mg/dL 0.7-1.3
Sodium              140 mEq/L 136-145
Potassium           4.2 mEq/L 3.5-5.0
"""

CARE_PLAN_P1 = """DR. PATEL INTERNAL MEDICINE
1234 Medical Center Drive

CARE PLAN

Patient: John Doe
Date: 01/10/2025
Provider: Dr. Anish Patel, MD

DIABETES MANAGEMENT PLAN

Current A1C: 7.2% (Goal: <7.0%)

Medications:
- Metformin 1000mg twice daily
- Lisinopril 10mg daily
"""


def generate_all_fixtures() -> None:
    """Generate all test fixture PDFs."""
    pages_dir = FIXTURES_DIR / "pages"
    batches_dir = FIXTURES_DIR / "batches"

    # Individual pages
    page_files = {
        "radiology_report_p1.pdf": RADIOLOGY_REPORT_P1,
        "radiology_report_p2.pdf": RADIOLOGY_REPORT_P2,
        "discharge_summary_p1.pdf": DISCHARGE_SUMMARY_P1,
        "lab_results_single.pdf": LAB_RESULTS,
        "care_plan_p1.pdf": CARE_PLAN_P1,
    }

    for filename, text in page_files.items():
        create_text_page_pdf(text, pages_dir / filename)

    create_blank_page_pdf(pages_dir / "blank_page.pdf")
    create_near_blank_page_pdf(pages_dir / "near_blank_page.pdf")

    # Multi-page batches: 5 docs as fronts
    front_pages = [
        pages_dir / "radiology_report_p1.pdf",
        pages_dir / "radiology_report_p2.pdf",
        pages_dir / "discharge_summary_p1.pdf",
        pages_dir / "lab_results_single.pdf",
        pages_dir / "care_plan_p1.pdf",
    ]
    merge_pdfs(front_pages, batches_dir / "fronts_5docs.pdf")

    # Backs: reversed order (simulating physical flip), with blanks for single-sided
    back_pages = [
        pages_dir / "blank_page.pdf",  # back of care_plan (single-sided)
        pages_dir / "blank_page.pdf",  # back of lab_results (single-sided)
        pages_dir / "blank_page.pdf",  # back of discharge (single-sided)
        pages_dir / "blank_page.pdf",  # back of radiology p2 (single-sided)
        pages_dir / "blank_page.pdf",  # back of radiology p1 (single-sided)
    ]
    merge_pdfs(back_pages, batches_dir / "backs_5docs.pdf")

    # All single-sided (no backs)
    merge_pdfs(front_pages[:3], batches_dir / "fronts_all_single_sided.pdf")

    # Single document (4 pages)
    merge_pdfs(
        [
            pages_dir / "radiology_report_p1.pdf",
            pages_dir / "radiology_report_p2.pdf",
            pages_dir / "radiology_report_p1.pdf",
            pages_dir / "radiology_report_p2.pdf",
        ],
        batches_dir / "fronts_single_doc.pdf",
    )

    print(f"Generated fixtures in {FIXTURES_DIR}")


if __name__ == "__main__":
    generate_all_fixtures()
