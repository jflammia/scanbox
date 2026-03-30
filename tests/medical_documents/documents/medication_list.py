"""Pharmacy medication list -- CVS style."""

from __future__ import annotations

from fpdf import FPDF

from tests.medical_documents import DocumentDef, PatientContext
from tests.medical_documents.helpers import heading, label_value, page_footer_text, separator


def render(pdf: FPDF, patient: PatientContext, config: None = None) -> None:
    pdf.add_page()
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 7, "CVS PHARMACY #4127", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 3.5, "2200 Boston Street, Baltimore, MD 21231", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        3.5,
        "Pharmacist: Linda Chen, PharmD  |  (410) 555-0199",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)
    separator(pdf)

    heading(pdf, "MEDICATION LIST", "Helvetica", 12)

    label_value(pdf, "Patient", patient.name)
    label_value(pdf, "DOB", patient.dob)
    label_value(pdf, "Allergies", "SULFA (rash), CODEINE (nausea)")
    label_value(pdf, "Printed", "03/21/2026")
    pdf.ln(3)

    # Medication table
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(40, 5, "Medication", border="B")
    pdf.cell(22, 5, "Strength", border="B", align="C")
    pdf.cell(28, 5, "Directions", border="B", align="C")
    pdf.cell(22, 5, "Qty", border="B", align="C")
    pdf.cell(22, 5, "Refills", border="B", align="C")
    pdf.cell(25, 5, "Prescriber", border="B", align="C")
    pdf.cell(20, 5, "Last Fill", border="B", align="C")
    pdf.ln()

    meds = [
        ("Metformin HCl", "1000mg", "BID w/meals", "60", "5", "A. Patel", "03/08"),
        ("Insulin Glargine", "100u/mL", "10u SC QHS", "1 pen", "2", "R. Patel", "03/14"),
        ("Lisinopril", "10mg", "QD", "30", "5", "A. Patel", "03/08"),
        ("Atorvastatin", "40mg", "QHS", "30", "5", "A. Patel", "03/08"),
        ("Amlodipine", "5mg", "QD", "30", "5", "A. Patel", "03/08"),
        ("Amox-Clav", "875-125mg", "BID x5d", "10", "0", "R. Patel", "03/14"),
        ("Acetaminophen", "500mg", "q6h PRN", "100", "OTC", "--", "03/01"),
        ("Guaifenesin ER", "600mg", "q12h PRN", "40", "OTC", "--", "03/14"),
    ]

    pdf.set_font("Helvetica", "", 7)
    for med, strength, dirs, qty, refills, prescriber, last_fill in meds:
        pdf.cell(40, 4.5, med)
        pdf.cell(22, 4.5, strength, align="C")
        pdf.cell(28, 4.5, dirs, align="C")
        pdf.cell(22, 4.5, qty, align="C")
        pdf.cell(22, 4.5, refills, align="C")
        pdf.cell(25, 4.5, prescriber, align="C")
        pdf.cell(20, 4.5, last_fill, align="C")
        pdf.ln()

    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, "NOTES:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.multi_cell(
        0,
        4,
        "- Amoxicillin-clavulanate: complete full course, do not stop early\n"
        "- Insulin glargine: store opened pen at room temp up to 28 days\n"
        "- Sulfa allergy on file - flagged for all new prescriptions\n"
        "- Next refill eligible: Metformin, Lisinopril, Atorvastatin, Amlodipine on 04/08/2026",
    )

    pdf.ln(3)
    separator(pdf)
    pdf.set_font("Helvetica", "I", 7)
    pdf.multi_cell(
        0,
        3,
        "This medication list is provided for informational purposes. Always consult "
        "your physician before making changes to your medication regimen. Bring this "
        "list to all medical appointments.",
    )

    page_footer_text(pdf, f"CVS Pharmacy #4127  |  {patient.name}  |  Printed 03/21/2026")


DOCUMENT = DocumentDef(
    name="medication_list",
    description="Pharmacy medication list -- CVS style",
    render=render,
    single_sided=True,
    back_artifact="near_blank_smudge",
)
