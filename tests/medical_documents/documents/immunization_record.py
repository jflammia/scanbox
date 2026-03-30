"""Immunization history -- government style."""

from __future__ import annotations

from fpdf import FPDF

from tests.medical_documents import DocumentDef, PatientContext
from tests.medical_documents.helpers import (
    heading,
    label_value,
    page_footer_text,
    separator,
    subheading,
)


def render(pdf: FPDF, patient: PatientContext, config: None = None) -> None:
    pdf.add_page()
    pdf.set_left_margin(12)
    pdf.set_right_margin(12)

    pdf.set_font("Courier", "B", 14)
    pdf.cell(0, 7, "MARYLAND DEPARTMENT OF HEALTH", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Courier", "", 7)
    pdf.cell(
        0,
        3.5,
        "IMMUNIZATION INFORMATION SYSTEM (ImmuNet)",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        3.5,
        "201 W. Preston Street, Baltimore, MD 21201  |  1-800-867-4017",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)
    separator(pdf)

    heading(pdf, "OFFICIAL IMMUNIZATION RECORD", "Courier", 12)

    pdf.set_font("Courier", "", 8)
    label_value(pdf, "Name", patient.name_last_first, "Courier", 8)
    label_value(pdf, "DOB", patient.dob, "Courier", 8)
    label_value(pdf, "Gender", patient.gender, "Courier", 8)
    label_value(pdf, "State ID", "MD-IMM-4472891", "Courier", 8)
    label_value(pdf, "Report Date", "03/21/2026", "Courier", 8)
    pdf.ln(3)

    # Immunization table
    pdf.set_font("Courier", "B", 7)
    cols = [42, 22, 28, 28, 30, 32]
    hdrs = ["Vaccine", "Date", "Mfr/Lot", "Site", "Provider", "Status"]
    for i, h in enumerate(hdrs):
        pdf.cell(cols[i], 4.5, h, border="B")
    pdf.ln()

    records = [
        ("Influenza (IIV4)", "10/15/2025", "Sanofi/UL482", "L Deltoid", "CVS #4127", "Complete"),
        ("Tdap (Boostrix)", "06/20/2024", "GSK/AC3B7", "R Deltoid", "Patel IM", "Complete"),
        (
            "COVID-19 (Updated)",
            "09/28/2025",
            "Pfizer/GH129",
            "L Deltoid",
            "Walgreens",
            "Complete",
        ),
        (
            "Pneumococcal (PCV20)",
            "01/10/2025",
            "Pfizer/PV882",
            "L Deltoid",
            "Patel IM",
            "Complete",
        ),
        ("Shingrix Dose 1", "08/05/2024", "GSK/7DR22", "R Deltoid", "Patel IM", "Complete"),
        ("Shingrix Dose 2", "10/12/2024", "GSK/7DR54", "R Deltoid", "Patel IM", "Complete"),
        ("Hepatitis B #1", "03/15/1998", "Merck/--", "R Deltoid", "City HD", "Complete"),
        ("Hepatitis B #2", "04/15/1998", "Merck/--", "R Deltoid", "City HD", "Complete"),
        ("Hepatitis B #3", "09/15/1998", "Merck/--", "R Deltoid", "City HD", "Complete"),
        ("MMR #1", "05/12/1969", "--/--", "L Thigh", "Pediatric", "Complete"),
        ("MMR #2", "09/01/1973", "--/--", "L Deltoid", "School", "Complete"),
        ("Polio (OPV) #1", "06/12/1968", "--/--", "Oral", "Pediatric", "Complete"),
        ("Polio (OPV) #2", "08/12/1968", "--/--", "Oral", "Pediatric", "Complete"),
        ("Polio (OPV) #3", "12/12/1968", "--/--", "Oral", "Pediatric", "Complete"),
        ("Polio (OPV) #4", "04/12/1973", "--/--", "Oral", "School", "Complete"),
    ]

    pdf.set_font("Courier", "", 6.5)
    for vaccine, date, lot, site, provider, status in records:
        pdf.cell(cols[0], 3.8, vaccine)
        pdf.cell(cols[1], 3.8, date, align="C")
        pdf.cell(cols[2], 3.8, lot, align="C")
        pdf.cell(cols[3], 3.8, site, align="C")
        pdf.cell(cols[4], 3.8, provider, align="C")
        pdf.cell(cols[5], 3.8, status, align="C")
        pdf.ln()

    pdf.ln(3)
    separator(pdf)

    subheading(pdf, "VACCINES DUE / OVERDUE", "Courier", 9)
    pdf.set_font("Courier", "", 8)
    pdf.cell(0, 4, "- Influenza (2026-2027): Due October 2026", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4, "- COVID-19 (Updated): Due September 2026", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        4,
        "- Tdap: Next due 2034 (10-year interval)",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    pdf.set_font("Courier", "", 6)
    pdf.multi_cell(
        0,
        2.8,
        "This record reflects immunizations reported to the Maryland ImmuNet system. "
        "It may not include all immunizations received. Providers: report via HL7 feed "
        "or direct entry at phpa.health.maryland.gov/immunet. For records corrections, "
        "contact your immunization provider or ImmuNet at 1-800-867-4017.",
    )

    page_footer_text(
        pdf,
        f"MD Department of Health  |  ImmuNet  |  {patient.name_last_first}  |  Printed 03/21/2026",
        "Courier",
        6,
    )


DOCUMENT = DocumentDef(
    name="immunization_record",
    description="Immunization history -- government style",
    render=render,
    single_sided=True,
    back_artifact="blank",
)
