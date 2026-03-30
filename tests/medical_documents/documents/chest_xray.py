"""Chest X-Ray radiology report -- hospital style."""

from __future__ import annotations

from fpdf import FPDF

from tests.medical_documents import DocumentDef, PatientContext
from tests.medical_documents.helpers import (
    LETTER_W,
    body,
    heading,
    label_value,
    page_footer_text,
    separator,
    subheading,
)


def render(pdf: FPDF, patient: PatientContext, config: None = None) -> None:
    pdf.add_page()
    pdf.set_left_margin(25)
    pdf.set_right_margin(25)

    # Formal hospital header
    pdf.set_font("Times", "B", 18)
    pdf.cell(0, 9, "MEMORIAL REGIONAL MEDICAL CENTER", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Times", "", 9)
    pdf.cell(0, 4, "Department of Diagnostic Radiology", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        4,
        "3501 Johnson Street, Hollywood, FL 33021",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    # Double line separator
    y = pdf.get_y()
    pdf.line(25, y, LETTER_W - 25, y)
    pdf.line(25, y + 1, LETTER_W - 25, y + 1)
    pdf.ln(5)

    heading(pdf, "RADIOLOGY REPORT", "Times", 14)
    pdf.ln(1)

    label_value(pdf, "Patient Name", patient.name, "Times", 10)
    label_value(pdf, "MRN", patient.mrn, "Times", 10)
    label_value(pdf, "Date of Birth", patient.dob, "Times", 10)
    label_value(pdf, "Exam Date", "03/18/2026", "Times", 10)
    label_value(pdf, "Ordering Physician", patient.pcp, "Times", 10)
    label_value(pdf, "Examination", "XR CHEST PA AND LATERAL", "Times", 10)
    pdf.ln(3)
    separator(pdf)

    subheading(pdf, "CLINICAL INDICATION:", "Times", 11)
    body(pdf, "Cough and low-grade fever x 3 days. Rule out pneumonia.", "Times", 10)

    subheading(pdf, "COMPARISON:", "Times", 11)
    body(pdf, "Chest radiograph dated 01/05/2026.", "Times", 10)

    subheading(pdf, "TECHNIQUE:", "Times", 11)
    body(pdf, "PA and lateral views of the chest were obtained.", "Times", 10)

    subheading(pdf, "FINDINGS:", "Times", 11)
    body(
        pdf,
        "The heart size is within normal limits. The mediastinal contours are unremarkable. "
        "There is no pleural effusion or pneumothorax. The lungs are clear bilaterally without "
        "focal consolidation, mass, or nodule. There is mild peribronchial thickening in the "
        "right lower lobe, which may represent early bronchitis. The osseous structures are "
        "intact. No acute bony abnormality.",
        "Times",
        10,
    )

    subheading(pdf, "IMPRESSION:", "Times", 11)
    body(
        pdf,
        "1. No acute cardiopulmonary disease.\n"
        "2. Mild peribronchial thickening in the right lower lobe, possibly representing "
        "early bronchitis. Clinical correlation recommended.",
        "Times",
        10,
    )
    pdf.ln(5)

    separator(pdf)
    pdf.set_font("Times", "I", 9)
    pdf.multi_cell(
        0,
        4,
        "Electronically signed by: James T. Whitfield, MD\n"
        "Board Certified, Diagnostic Radiology\n"
        "03/18/2026 11:42 AM",
    )

    page_footer_text(
        pdf,
        f"Memorial Regional Medical Center  |  Confidential Patient Information  |  {patient.mrn}",
        "Times",
    )


DOCUMENT = DocumentDef(
    name="chest_xray",
    description="Chest X-Ray radiology report -- hospital style",
    render=render,
    single_sided=True,
    back_artifact="blank",
)
