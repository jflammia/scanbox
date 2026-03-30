"""Surgical pathology report -- dense small font."""

from __future__ import annotations

from fpdf import FPDF

from tests.medical_documents import DocumentDef, PatientContext
from tests.medical_documents.helpers import (
    body,
    label_value,
    page_footer_text,
    separator,
    subheading,
)


def render(pdf: FPDF, patient: PatientContext, config: None = None) -> None:
    pdf.add_page()
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)

    pdf.set_font("Times", "B", 14)
    pdf.cell(0, 7, "JOHNS HOPKINS HOSPITAL", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Times", "", 8)
    pdf.cell(
        0,
        3.5,
        "Department of Pathology  |  600 N. Wolfe Street  |  Baltimore, MD 21287",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)
    separator(pdf)

    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 6, "SURGICAL PATHOLOGY REPORT", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Times", "", 8)
    label_value(pdf, "Patient", patient.name, "Times", 8)
    label_value(pdf, "MRN", patient.mrn, "Times", 8)
    label_value(pdf, "DOB", patient.dob, "Times", 8)
    label_value(pdf, "Accession", "SP-26-04472", "Times", 8)
    label_value(pdf, "Collected", "03/12/2026", "Times", 8)
    label_value(pdf, "Received", "03/12/2026", "Times", 8)
    label_value(pdf, "Reported", "03/16/2026", "Times", 8)
    label_value(pdf, "Surgeon", "Dr. Kathleen Reyes, MD", "Times", 8)
    pdf.ln(2)
    separator(pdf)

    subheading(pdf, "SPECIMEN", "Times", 10)
    body(pdf, "A. Appendix, appendectomy", "Times", 9)

    subheading(pdf, "CLINICAL HISTORY", "Times", 10)
    body(
        pdf,
        f"{patient.age}-year-old female with acute right lower quadrant pain. CT showing "
        "peri-appendiceal inflammation. Laparoscopic appendectomy performed.",
        "Times",
        9,
    )

    subheading(pdf, "GROSS DESCRIPTION", "Times", 10)
    body(
        pdf,
        "Received in formalin is an appendix measuring 7.2 x 1.1 cm. The serosal surface "
        "is congested and covered with a fibrinopurulent exudate. The lumen is dilated and "
        "contains tan-yellow purulent material. The wall thickness ranges from 0.2 to 0.4 cm. "
        "A fecalith measuring 0.6 cm is identified at the base. Representative sections are "
        "submitted in cassettes A1-A4. A1: base margin; A2-A3: mid-appendix cross sections; "
        "A4: tip.",
        "Times",
        8,
    )

    subheading(pdf, "MICROSCOPIC DESCRIPTION", "Times", 10)
    body(
        pdf,
        "Sections show transmural acute inflammation of the appendiceal wall with extensive "
        "neutrophilic infiltration of the mucosa, submucosa, muscularis propria, and serosa. "
        "There is mucosal ulceration with luminal abscess formation. The serosal surface "
        "demonstrates fibrinopurulent exudate. Periappendiceal fat shows acute inflammation. "
        "No evidence of perforation, granulomatous inflammation, or neoplasia. The resection "
        "margin is free of acute inflammation.",
        "Times",
        8,
    )

    subheading(pdf, "DIAGNOSIS", "Times", 10)
    pdf.set_font("Times", "B", 9)
    pdf.multi_cell(
        0,
        4.5,
        "A. APPENDIX, APPENDECTOMY:\n"
        "   - ACUTE SUPPURATIVE APPENDICITIS WITH PERIAPPENDICITIS\n"
        "   - FECALITH IDENTIFIED\n"
        "   - NO EVIDENCE OF PERFORATION\n"
        "   - MARGINS NEGATIVE FOR ACUTE INFLAMMATION",
    )
    pdf.ln(3)

    separator(pdf)
    pdf.set_font("Times", "I", 8)
    pdf.multi_cell(
        0,
        3.5,
        "Pathologist: Margaret A. Collins, MD, FCAP\n"
        "Electronically signed: 03/16/2026 09:15\n"
        "Resident: David Park, MD (PGY-3)",
    )

    page_footer_text(
        pdf,
        f"SP-26-04472  |  JHH Pathology  |  {patient.name}  |  CONFIDENTIAL",
        "Times",
    )


DOCUMENT = DocumentDef(
    name="pathology_report",
    description="Surgical pathology report -- dense small font",
    render=render,
    single_sided=True,
    back_artifact="blank",
)
