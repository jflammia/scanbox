"""Diabetes management care plan -- doctor's office style."""

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
    # --- Page 1 ---
    pdf.add_page()
    pdf.set_left_margin(18)
    pdf.set_right_margin(18)

    # Office letterhead -- different style
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 7, "PATEL INTERNAL MEDICINE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 3.5, "1234 Medical Center Drive, Suite 200", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 3.5, "Baltimore, MD 21201", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 3.5, "Tel: (410) 555-0142  |  Fax: (410) 555-0143", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_draw_color(0, 102, 51)
    pdf.set_line_width(0.8)
    y = pdf.get_y()
    pdf.line(18, y, LETTER_W - 18, y)
    pdf.set_line_width(0.2)
    pdf.set_draw_color(0, 0, 0)
    pdf.ln(4)

    heading(pdf, "DIABETES MANAGEMENT CARE PLAN", "Helvetica", 13)
    pdf.ln(1)

    label_value(pdf, "Patient", patient.name)
    label_value(pdf, "DOB", patient.dob)
    label_value(pdf, "Date", "03/21/2026")
    label_value(pdf, "Provider", patient.pcp)
    label_value(pdf, "Diagnosis", "Type 2 Diabetes Mellitus (E11.65)")
    pdf.ln(3)

    subheading(pdf, "CURRENT METRICS")
    pdf.set_font("Helvetica", "", 9)

    # Simple table
    metrics = [
        ("A1C", "7.2%", "<7.0%", "03/15/2026"),
        ("Fasting Glucose", "142 mg/dL", "80-130 mg/dL", "03/15/2026"),
        ("Blood Pressure", "138/86 mmHg", "<130/80 mmHg", "03/21/2026"),
        ("BMI", "31.4", "<25", "03/21/2026"),
        ("Weight", "182 lbs", "Goal: 165 lbs", "03/21/2026"),
        ("LDL Cholesterol", "118 mg/dL", "<100 mg/dL", "03/15/2026"),
        ("eGFR", ">60 mL/min", ">60 mL/min", "03/15/2026"),
        ("Urine Albumin", "Pending", "<30 mg/g", "Ordered"),
    ]

    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(40, 5, "Metric", border="B")
    pdf.cell(35, 5, "Current", border="B", align="C")
    pdf.cell(35, 5, "Target", border="B", align="C")
    pdf.cell(30, 5, "Date", border="B", align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for metric, current, target, date in metrics:
        pdf.cell(40, 4.5, metric)
        pdf.cell(35, 4.5, current, align="C")
        pdf.cell(35, 4.5, target, align="C")
        pdf.cell(30, 4.5, date, align="C")
        pdf.ln()
    pdf.ln(3)

    subheading(pdf, "MEDICATIONS")
    meds = [
        ("Metformin", "1000mg", "Twice daily with meals", "Continue"),
        ("Lantus (insulin glargine)", "10 units", "SC at bedtime", "NEW - started 03/14"),
        ("Lisinopril", "10mg", "Once daily", "Continue"),
        ("Atorvastatin", "40mg", "At bedtime", "Continue"),
        ("Amlodipine", "5mg", "Once daily", "Continue"),
    ]
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(45, 5, "Medication", border="B")
    pdf.cell(25, 5, "Dose", border="B", align="C")
    pdf.cell(40, 5, "Frequency", border="B", align="C")
    pdf.cell(45, 5, "Status", border="B", align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for med, dose, freq, status in meds:
        pdf.cell(45, 4.5, med)
        pdf.cell(25, 4.5, dose, align="C")
        pdf.cell(40, 4.5, freq, align="C")
        pdf.cell(45, 4.5, status, align="C")
        pdf.ln()

    page_footer_text(pdf, f"Page 1 of 2  |  {patient.name}  |  Diabetes Care Plan  |  03/21/2026")

    # --- Page 2 ---
    pdf.add_page()
    pdf.set_left_margin(18)
    pdf.set_right_margin(18)

    subheading(pdf, "SELF-MANAGEMENT GOALS")
    goals = [
        "[ ] Check blood glucose 4x daily (before meals + bedtime) for 2 weeks",
        "[ ] Record glucose readings in logbook or app (MySugr recommended)",
        "[ ] Walk 30 minutes, 5 days per week",
        "[ ] Follow Mediterranean-style diet; limit carbs to 45-60g per meal",
        "[ ] Bring glucose log to all appointments",
        "[ ] Schedule eye exam with ophthalmology (annual diabetic screening)",
        "[ ] Schedule podiatry visit for foot examination",
    ]
    pdf.set_font("Helvetica", "", 9)
    for goal in goals:
        pdf.cell(0, 5.5, goal, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    subheading(pdf, "INSULIN INSTRUCTIONS")
    body(
        pdf,
        "Lantus (insulin glargine) 10 units subcutaneously at bedtime:\n"
        "- Inject in abdomen, thigh, or upper arm (rotate sites)\n"
        "- Do NOT mix with other insulins\n"
        "- Store opened pen at room temperature for up to 28 days\n"
        "- If fasting glucose remains >130 for 3 consecutive days, increase dose by 2 units\n"
        "- Call office if fasting glucose drops below 70 or exceeds 250\n"
        "- Always carry fast-acting glucose (juice, glucose tabs) for hypoglycemia",
    )

    subheading(pdf, "WHEN TO SEEK IMMEDIATE CARE")
    body(
        pdf,
        "- Blood glucose >400 mg/dL\n"
        "- Symptoms of DKA: nausea/vomiting, fruity breath, rapid breathing, confusion\n"
        "- Blood glucose <54 mg/dL unresponsive to treatment\n"
        "- Signs of infection at injection site (redness, warmth, swelling)",
    )

    subheading(pdf, "FOLLOW-UP SCHEDULE")
    body(
        pdf,
        "- Endocrinology (Dr. S. Kim): 03/28/2026  -- insulin titration\n"
        f"- PCP ({patient.pcp}): 04/21/2026  -- comprehensive review\n"
        "- Labs before next PCP visit: A1C, CMP, lipid panel, urine albumin\n"
        "- Annual: diabetic eye exam, podiatry, dental",
    )

    pdf.ln(5)
    separator(pdf)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(
        0, 5, "Provider Signature: ____________________________", new_x="LMARGIN", new_y="NEXT"
    )
    pdf.cell(0, 5, patient.pcp, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.cell(
        0, 5, "Patient Signature:  ____________________________", new_x="LMARGIN", new_y="NEXT"
    )
    pdf.cell(0, 5, patient.name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 7)
    pdf.cell(
        0,
        3,
        "I acknowledge that I have received and understand this care plan.",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    page_footer_text(pdf, f"Page 2 of 2  |  {patient.name}  |  Diabetes Care Plan  |  03/21/2026")


DOCUMENT = DocumentDef(
    name="diabetes_care_plan",
    description="Diabetes management care plan -- doctor's office style",
    render=render,
    single_sided=False,
    back_artifact="blank",
)
