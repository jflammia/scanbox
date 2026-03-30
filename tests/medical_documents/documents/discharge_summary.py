"""Hospital discharge summary -- Johns Hopkins style."""

from __future__ import annotations

from fpdf import FPDF

from tests.medical_documents import DocumentDef, PatientContext
from tests.medical_documents.helpers import (
    LETTER_W,
    body,
    page_footer_text,
    separator,
    subheading,
)


def render(pdf: FPDF, patient: PatientContext, config: None = None) -> None:
    # --- Page 1 ---
    pdf.add_page()
    pdf.set_left_margin(20)
    pdf.set_right_margin(20)

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, "JOHNS HOPKINS HOSPITAL", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(
        0,
        4,
        "1800 Orleans Street, Baltimore, MD 21287  |  (410) 955-5000",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)

    pdf.set_fill_color(0, 51, 102)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "  DISCHARGE SUMMARY", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # Two-column patient info
    pdf.set_font("Helvetica", "", 9)
    col_w = (LETTER_W - 40) / 2
    x_left = 20
    x_right = 20 + col_w + 5

    info_left = [
        ("Patient", patient.name),
        ("MRN", patient.mrn),
        ("DOB", patient.dob),
        ("Admission", "03/10/2026"),
        ("Discharge", "03/14/2026"),
    ]
    info_right = [
        ("Attending", "Robert K. Patel, MD"),
        ("Service", "Internal Medicine"),
        ("Room", "Nelson 4-218"),
        ("Insurance", patient.insurance),
        ("PCP", patient.pcp),
    ]
    y_start = pdf.get_y()
    for label, val in info_left:
        pdf.set_xy(x_left, pdf.get_y())
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(30, 4.5, f"{label}:")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_w - 30, 4.5, val, new_x="LMARGIN", new_y="NEXT")

    y_end_left = pdf.get_y()
    pdf.set_y(y_start)
    for label, val in info_right:
        pdf.set_xy(x_right, pdf.get_y())
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(30, 4.5, f"{label}:")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_w - 30, 4.5, val, new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(max(y_end_left, pdf.get_y()) + 3)
    separator(pdf)

    subheading(pdf, "PRINCIPAL DIAGNOSIS")
    body(
        pdf,
        "Community-acquired pneumonia, right lower lobe (ICD-10: J18.1)",
    )

    subheading(pdf, "SECONDARY DIAGNOSES")
    body(
        pdf,
        "1. Type 2 diabetes mellitus, uncontrolled (E11.65)\n"
        "2. Essential hypertension (I10)\n"
        "3. Hyperlipidemia (E78.5)\n"
        "4. Acute kidney injury, stage 1, resolved (N17.9)",
    )

    subheading(pdf, "HISTORY OF PRESENT ILLNESS")
    body(
        pdf,
        f"Ms. {patient.name.split()[-1]} is a {patient.age}-year-old woman with a history of "
        "type 2 diabetes, hypertension, "
        "and hyperlipidemia who presented to the emergency department on 03/10/2026 with a "
        "4-day history of productive cough, fever (Tmax 102.4F), chills, and progressive "
        "dyspnea on exertion. She reported yellow-green sputum production and right-sided "
        "pleuritic chest pain. She denied hemoptysis, recent travel, or sick contacts. Her "
        "symptoms had not improved with over-the-counter cold medications.",
    )

    subheading(pdf, "HOSPITAL COURSE")
    body(
        pdf,
        "The patient was admitted to the internal medicine service. Chest X-ray confirmed "
        "right lower lobe consolidation consistent with community-acquired pneumonia. Blood "
        "cultures were obtained (subsequently negative). She was started on IV ceftriaxone "
        "1g daily and oral azithromycin 500mg day 1, then 250mg days 2-5.\n\n"
        "On admission, her blood glucose was 287 mg/dL with A1C of 7.2%. Her home metformin "
        "was continued and sliding scale insulin was initiated. Endocrinology was consulted "
        "and recommended adding basal insulin (Lantus 10 units at bedtime) given suboptimal "
        "glycemic control.",
    )

    page_footer_text(
        pdf,
        f"Page 1 of 3  |  {patient.mrn}  |  {patient.name}  |  DISCHARGE SUMMARY",
    )

    # --- Page 2 ---
    pdf.add_page()
    pdf.set_left_margin(20)
    pdf.set_right_margin(20)

    body(
        pdf,
        "The patient's creatinine was mildly elevated at 1.3 mg/dL on admission (baseline "
        "0.91) consistent with prerenal AKI. IV fluids were administered and creatinine "
        "normalized to 0.95 by hospital day 3. ACE inhibitor was held during the AKI episode "
        "and restarted at discharge.\n\n"
        "By hospital day 3, the patient was afebrile with improving symptoms. She was "
        "transitioned to oral antibiotics and observed for 24 hours. She tolerated a regular "
        "diet and ambulated independently.",
    )

    subheading(pdf, "PERTINENT RESULTS")
    body(
        pdf,
        "CBC (03/10): WBC 14.2, Hgb 12.8, Plt 289\n"
        "CBC (03/13): WBC 8.7, Hgb 12.5, Plt 301\n"
        "BMP (03/10): Na 138, K 4.1, Cr 1.3, Glucose 287\n"
        "BMP (03/13): Na 140, K 4.3, Cr 0.95, Glucose 156\n"
        "Procalcitonin: 1.8 ng/mL (elevated)\n"
        "Blood cultures x2: No growth at 5 days\n"
        "Sputum culture: Normal respiratory flora\n"
        "CXR (03/10): RLL consolidation\n"
        "CXR (03/13): Improving RLL infiltrate",
    )

    subheading(pdf, "PROCEDURES")
    body(pdf, "None performed during this admission.")

    subheading(pdf, "CONSULTATIONS")
    body(
        pdf,
        "Endocrinology (Dr. Sarah Kim): Recommended initiation of basal insulin "
        "given suboptimal diabetes control with oral agents alone. Follow-up in 2 weeks.",
    )

    subheading(pdf, "DISCHARGE MEDICATIONS")
    pdf.set_font("Helvetica", "", 9)
    meds = [
        "1. Amoxicillin-clavulanate 875/125mg PO BID x 5 days (NEW)",
        "2. Metformin 1000mg PO BID (CONTINUED)",
        "3. Insulin glargine (Lantus) 10 units SC at bedtime (NEW)",
        "4. Lisinopril 10mg PO daily (RESTARTED)",
        "5. Atorvastatin 40mg PO at bedtime (CONTINUED)",
        "6. Amlodipine 5mg PO daily (CONTINUED)",
        "7. Acetaminophen 650mg PO q6h PRN fever/pain",
        "8. Guaifenesin 400mg PO q4h PRN cough",
    ]
    for med in meds:
        pdf.cell(0, 4.5, med, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    page_footer_text(
        pdf,
        f"Page 2 of 3  |  {patient.mrn}  |  {patient.name}  |  DISCHARGE SUMMARY",
    )

    # --- Page 3 ---
    pdf.add_page()
    pdf.set_left_margin(20)
    pdf.set_right_margin(20)

    subheading(pdf, "DISCHARGE CONDITION")
    body(pdf, "Stable. Ambulating independently. Afebrile x 48 hours. Tolerating PO.")

    subheading(pdf, "DISCHARGE INSTRUCTIONS")
    pdf.set_font("Helvetica", "", 9)
    instructions = [
        "- Complete the full course of antibiotics as prescribed",
        "- Check blood glucose before meals and at bedtime; record in log",
        "- Inject Lantus 10 units in abdomen or thigh at bedtime",
        "- Return to ED if fever >101.5F, worsening shortness of breath,",
        "  chest pain, blood in sputum, or inability to keep fluids down",
        "- Follow a diabetic diet; limit carbohydrates to 45-60g per meal",
        "- Avoid alcohol while on antibiotics",
        "- Use incentive spirometer 10 times per hour while awake",
    ]
    for inst in instructions:
        pdf.cell(0, 4.5, inst, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    subheading(pdf, "FOLLOW-UP APPOINTMENTS")
    body(
        pdf,
        f"1. {patient.pcp} (PCP)  -- March 21, 2026 at 2:00 PM\n"
        "   Patel Internal Medicine, 1234 Medical Center Dr, Suite 200\n"
        "   Purpose: Post-hospitalization check, repeat labs\n\n"
        "2. Dr. Sarah Kim (Endocrinology)  -- March 28, 2026 at 10:30 AM\n"
        "   Johns Hopkins Diabetes Center, 601 N. Caroline St, Suite 2008\n"
        "   Purpose: Insulin titration, diabetes management\n\n"
        "3. Repeat chest X-ray  -- April 7, 2026\n"
        "   Memorial Regional Radiology  -- call to schedule",
    )

    pdf.ln(5)
    separator(pdf)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, "Attending Physician:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, "Robert K. Patel, MD, FACP", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Department of Internal Medicine", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 4, "Electronically signed 03/14/2026 14:22", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 7)
    pdf.multi_cell(
        0,
        3,
        "This document contains confidential medical information protected by federal and "
        "state privacy laws. Unauthorized disclosure is prohibited.",
    )

    page_footer_text(
        pdf,
        f"Page 3 of 3  |  {patient.mrn}  |  {patient.name}  |  DISCHARGE SUMMARY",
    )


DOCUMENT = DocumentDef(
    name="discharge_summary",
    description="Hospital discharge summary -- Johns Hopkins style",
    render=render,
    single_sided=False,
    back_artifact="blank",
)
