"""Output writing: archive, medical records, Index.csv."""

import csv
import shutil
from pathlib import Path

from scanbox.models import SplitDocument

# Pluralized folder names for medical record categories
TYPE_FOLDER_NAMES = {
    "Radiology Report": "Radiology Reports",
    "Discharge Summary": "Discharge Summaries",
    "Care Plan": "Care Plans",
    "Lab Results": "Lab Results",
    "Letter": "Letters & Referrals",
    "Operative Report": "Operative Reports",
    "Progress Note": "Progress Notes",
    "Pathology Report": "Pathology Reports",
    "Prescription": "Prescriptions",
    "Insurance": "Insurance",
    "Billing": "Billing",
    "Other": "Other",
}

INDEX_HEADERS = ["Filename", "Date", "Type", "Facility", "Provider", "Description", "Scanned"]


def write_archive(
    combined_pdf: Path,
    archive_dir: Path,
    person_slug: str,
    scan_date: str,
    batch_num: int,
) -> Path:
    """Copy the raw combined PDF to the archive directory."""
    dest_dir = archive_dir / person_slug / scan_date
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"batch-{batch_num:03d}-combined.pdf"
    shutil.copy2(combined_pdf, dest)
    return dest


def write_medical_records(
    doc_pdf: Path,
    records_dir: Path,
    person_folder: str,
    document_type: str,
    filename: str,
) -> Path:
    """Write a split document PDF to the organized medical records folder."""
    type_folder = TYPE_FOLDER_NAMES.get(document_type, "Other")
    dest_dir = records_dir / person_folder / type_folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    shutil.copy2(doc_pdf, dest)
    return dest


def append_index_csv(
    csv_path: Path,
    filename: str,
    doc: SplitDocument,
    scan_date: str,
) -> None:
    """Append a row to the Index.csv file, creating it if it doesn't exist."""
    write_header = not csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "Filename": filename,
                "Date": doc.date_of_service,
                "Type": doc.document_type,
                "Facility": doc.facility if doc.facility != "unknown" else "",
                "Provider": doc.provider if doc.provider != "unknown" else "",
                "Description": doc.description,
                "Scanned": scan_date,
            }
        )
