"""Physical therapy progress note -- SOAP format."""

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
    # --- Page 1 ---
    pdf.add_page()
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 7, "CHESAPEAKE PHYSICAL THERAPY", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 7)
    pdf.cell(
        0,
        3.5,
        "890 Linden Ave, Suite 110, Baltimore, MD 21201  |  (410) 555-0177  |  Fax: (410) 555-0178",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)
    separator(pdf)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "PHYSICAL THERAPY PROGRESS NOTE", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    label_value(pdf, "Patient", patient.name)
    label_value(pdf, "DOB", patient.dob)
    label_value(pdf, "Date of Service", "03/22/2026")
    label_value(pdf, "Visit Number", "4 of 12 authorized")
    label_value(pdf, "Referring MD", patient.pcp)
    label_value(pdf, "Diagnosis", "Deconditioning following hospitalization (R53.81)")
    label_value(pdf, "Therapist", "Michael Torres, DPT, OCS")
    pdf.ln(2)
    separator(pdf)

    # SOAP Note
    subheading(pdf, "SUBJECTIVE")
    body(
        pdf,
        "Patient reports gradual improvement in energy level since discharge from Johns Hopkins "
        'on 03/14/2026. States she is "still getting winded going up the stairs" but notices '
        '"I can walk further before needing to rest." Reports compliance with home exercise '
        "program 5/7 days. Denies chest pain, dizziness, or new symptoms. Pain level 2/10 "
        "(generalized fatigue, not focal pain). Sleep remains poor due to cough (improving).",
    )

    subheading(pdf, "OBJECTIVE")
    body(pdf, "Vital signs at start of session:", "Helvetica", 9)

    pdf.set_font("Helvetica", "", 9)
    vitals = [
        ("HR", "78 bpm (resting)", "82 bpm (post-exercise)"),
        ("BP", "132/82 mmHg", "138/84 mmHg"),
        ("SpO2", "97%", "95%"),
        ("RR", "16", "20"),
        ("RPE (Borg)", "--", "13/20 (somewhat hard)"),
    ]
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(35, 4.5, "Measure", border="B")
    pdf.cell(45, 4.5, "Resting", border="B", align="C")
    pdf.cell(45, 4.5, "Post-Exercise", border="B", align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for measure, rest, post in vitals:
        pdf.cell(35, 4, measure)
        pdf.cell(45, 4, rest, align="C")
        pdf.cell(45, 4, post, align="C")
        pdf.ln()
    pdf.ln(2)

    body(pdf, "Functional testing:", "Helvetica", 9)
    pdf.set_font("Helvetica", "", 8)
    tests = [
        ("6-Minute Walk Test", "380 meters", "320 meters (03/15)", "Normal >400m"),
        ("Timed Up and Go", "9.2 sec", "11.4 sec (03/15)", "Normal <12 sec"),
        ("30-sec Chair Stand", "11 reps", "8 reps (03/15)", "Normal >12 reps"),
        (
            "Single Leg Stance",
            "18 sec (R), 16 sec (L)",
            "12 sec (R), 10 sec (L)",
            "Normal >20 sec",
        ),
    ]
    pdf.set_font("Helvetica", "B", 7)
    pdf.cell(35, 4.5, "Test", border="B")
    pdf.cell(45, 4.5, "Today", border="B", align="C")
    pdf.cell(45, 4.5, "Previous", border="B", align="C")
    pdf.cell(35, 4.5, "Norm", border="B", align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 7)
    for test, today, prev, norm in tests:
        pdf.cell(35, 4, test)
        pdf.cell(45, 4, today, align="C")
        pdf.cell(45, 4, prev, align="C")
        pdf.cell(35, 4, norm, align="C")
        pdf.ln()

    page_footer_text(pdf, f"Page 1 of 2  |  Chesapeake PT  |  {patient.name}  |  03/22/2026")

    # --- Page 2 ---
    pdf.add_page()
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)

    subheading(pdf, "TREATMENT PROVIDED")
    body(
        pdf,
        "1. Warm-up: 10 min recumbent bike at light resistance (RPE 10-11)\n"
        "2. Strengthening circuit (2 sets x 12 reps each):\n"
        "   - Sit-to-stand (no arms)\n"
        "   - Standing hip abduction with yellow band\n"
        "   - Wall push-ups\n"
        "   - Seated row with green band\n"
        "   - Step-ups (6-inch step)\n"
        "3. Walking program: 12 min treadmill at 2.4 mph, 0% incline\n"
        "4. Balance training: tandem stance 3x30 sec, single leg stance 3x15 sec\n"
        "5. Cool-down: stretching and breathing exercises (5 min)\n"
        "Total treatment time: 55 minutes",
    )

    subheading(pdf, "ASSESSMENT")
    body(
        pdf,
        "Patient is making good progress toward functional recovery following hospitalization "
        "for pneumonia. 6MWT improved 19% from initial evaluation. Timed Up and Go now within "
        "normal limits. Aerobic endurance remains primary limitation. SpO2 maintained >94% "
        "throughout session with no desaturation events. Patient motivated and compliant with "
        "HEP. Blood glucose checked pre-session: 128 mg/dL (within target).",
    )

    subheading(pdf, "PLAN")
    body(
        pdf,
        "1. Continue PT 2x/week for remaining 8 authorized visits\n"
        "2. Progress treadmill to 15 min at 2.6 mph next session\n"
        "3. Advance resistance band to green for hip abduction\n"
        "4. Add stair climbing to next session if SpO2 tolerates\n"
        "5. Updated HEP provided (see attached)\n"
        "6. Goals for next visit: 6MWT >400m, 30-sec chair stand >12\n"
        "7. Will reassess for discharge readiness at visit 8",
    )

    subheading(pdf, "HOME EXERCISE PROGRAM")
    body(
        pdf,
        "Perform daily:\n"
        "- Walk 15-20 minutes (level surface, moderate pace)\n"
        "- Sit-to-stand x 10 reps, 2 sets\n"
        "- Wall push-ups x 10 reps, 2 sets\n"
        "- Standing balance: tandem stance 30 sec x 3\n"
        "- Deep breathing: 10 breaths x 3 times/day",
    )

    pdf.ln(3)
    separator(pdf)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, "Treating Therapist:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Michael Torres, DPT, OCS", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "License #: PT-14892-MD", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 7)
    pdf.cell(0, 3, "Electronically signed: 03/22/2026 15:45", new_x="LMARGIN", new_y="NEXT")

    page_footer_text(pdf, f"Page 2 of 2  |  Chesapeake PT  |  {patient.name}  |  03/22/2026")


DOCUMENT = DocumentDef(
    name="pt_progress_note",
    description="Physical therapy progress note -- SOAP format",
    render=render,
    single_sided=False,
    back_artifact="blank",
)
