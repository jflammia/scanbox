"""Physician referral letter -- traditional letter format."""

from __future__ import annotations

from fpdf import FPDF

from tests.medical_documents import DocumentDef, PatientContext
from tests.medical_documents.helpers import body, separator


def render(pdf: FPDF, patient: PatientContext, config: None = None) -> None:
    pdf.add_page()
    pdf.set_left_margin(25)
    pdf.set_right_margin(25)

    # Letterhead
    pdf.set_font("Times", "B", 14)
    pdf.cell(0, 7, f"{patient.pcp}, FACP", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Times", "", 9)
    pdf.cell(0, 4, "Internal Medicine", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        4,
        "1234 Medical Center Drive, Suite 200  |  Baltimore, MD 21201",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        4,
        "Tel: (410) 555-0142  |  Fax: (410) 555-0143",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)
    separator(pdf)
    pdf.ln(5)

    # Date
    pdf.set_font("Times", "", 11)
    pdf.cell(0, 5, "March 21, 2026", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Addressee
    pdf.cell(0, 5, "Sarah Kim, MD", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Division of Endocrinology", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Johns Hopkins Diabetes Center", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "601 N. Caroline Street, Suite 2008", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Baltimore, MD 21287", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    pdf.set_font("Times", "B", 11)
    pdf.cell(
        0,
        5,
        f"Re: {patient.name} (DOB: {patient.dob})",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(5)

    pdf.set_font("Times", "", 11)
    pdf.cell(0, 5, "Dear Dr. Kim,", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    last_name = patient.name.split()[-1]
    body(
        pdf,
        f"I am referring Ms. {last_name} to your care for management of her type 2 diabetes "
        f"mellitus. She is a {patient.age}-year-old woman who was recently hospitalized at "
        "Johns Hopkins for community-acquired pneumonia, during which her diabetes was found "
        "to be suboptimally controlled on metformin monotherapy (A1C 7.2%, fasting glucose "
        "142 mg/dL).",
        "Times",
        11,
    )

    body(
        pdf,
        "During her hospitalization, basal insulin (Lantus 10 units at bedtime) was initiated "
        "per your inpatient consultation. She was discharged on 03/14/2026 and is tolerating "
        "the insulin without hypoglycemia. I would appreciate your guidance on insulin "
        "titration and long-term diabetes management.",
        "Times",
        11,
    )

    body(
        pdf,
        "Her relevant history includes hypertension (controlled on lisinopril/amlodipine), "
        "hyperlipidemia (on atorvastatin), and a sulfa allergy. She has no history of diabetic "
        "complications. Most recent labs (03/15/2026) are enclosed.",
        "Times",
        11,
    )

    body(
        pdf,
        f"Thank you for seeing Ms. {last_name}. Please do not hesitate to contact my office "
        "if you need additional information.",
        "Times",
        11,
    )

    pdf.ln(5)
    pdf.set_font("Times", "", 11)
    pdf.cell(0, 5, "Sincerely,", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_font("Times", "I", 11)
    pdf.cell(0, 5, f"{patient.pcp}, FACP", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Times", "", 9)
    pdf.cell(0, 4, "Encl: Lab results (03/15/2026)", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4, "CC: Patient", new_x="LMARGIN", new_y="NEXT")


DOCUMENT = DocumentDef(
    name="referral_letter",
    description="Physician referral letter -- traditional letter format",
    render=render,
    single_sided=True,
    back_artifact="blank",
)
