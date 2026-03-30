"""Operative/surgical report -- formal surgical style."""

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
    pdf.set_left_margin(20)
    pdf.set_right_margin(20)

    pdf.set_font("Times", "B", 16)
    pdf.cell(0, 8, "JOHNS HOPKINS HOSPITAL", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Times", "", 8)
    pdf.cell(0, 3.5, "Department of Surgery", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        3.5,
        "600 N. Wolfe Street, Blalock Building  |  Baltimore, MD 21287",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)

    pdf.set_fill_color(102, 0, 0)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 7, "  OPERATIVE REPORT", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    pdf.set_font("Times", "", 9)
    label_value(pdf, "Patient", patient.name, "Times", 9)
    label_value(pdf, "MRN", patient.mrn, "Times", 9)
    label_value(pdf, "DOB", patient.dob, "Times", 9)
    label_value(pdf, "Date of Procedure", "03/12/2026", "Times", 9)
    label_value(pdf, "Surgeon", "Kathleen M. Reyes, MD, FACS", "Times", 9)
    label_value(pdf, "First Assistant", "David Chen, MD (PGY-4)", "Times", 9)
    label_value(pdf, "Anesthesiologist", "James Whitaker, MD", "Times", 9)
    label_value(pdf, "Anesthesia Type", "General endotracheal", "Times", 9)
    pdf.ln(2)
    separator(pdf)

    subheading(pdf, "PREOPERATIVE DIAGNOSIS", "Times", 11)
    body(pdf, "Acute appendicitis", "Times", 10)

    subheading(pdf, "POSTOPERATIVE DIAGNOSIS", "Times", 11)
    body(pdf, "Acute suppurative appendicitis, non-perforated", "Times", 10)

    subheading(pdf, "PROCEDURE PERFORMED", "Times", 11)
    body(pdf, "Laparoscopic appendectomy", "Times", 10)

    subheading(pdf, "INDICATIONS", "Times", 11)
    body(
        pdf,
        f"The patient is a {patient.age}-year-old woman who presented with acute onset right "
        "lower quadrant pain, fever, and elevated white blood cell count. CT abdomen/pelvis "
        "demonstrated peri-appendiceal inflammation and an appendicolith consistent with "
        "acute appendicitis. After discussion of risks, benefits, and alternatives, the "
        "patient consented to laparoscopic appendectomy. Informed consent was obtained. "
        "The patient's diabetes was noted; blood glucose was 156 mg/dL preoperatively.",
        "Times",
        10,
    )

    subheading(pdf, "DESCRIPTION OF PROCEDURE", "Times", 11)
    body(
        pdf,
        "The patient was brought to the operating room and placed in supine position on the "
        "operating table. After induction of general endotracheal anesthesia, sequential "
        "compression devices were applied. A time-out was performed confirming patient "
        "identity, procedure, and surgical site. The abdomen was prepped and draped in "
        "standard sterile fashion.",
        "Times",
        10,
    )

    page_footer_text(
        pdf,
        f"Page 1 of 3  |  {patient.mrn}  |  {patient.name}  |  OPERATIVE REPORT",
        "Times",
    )

    # --- Page 2 ---
    pdf.add_page()
    pdf.set_left_margin(20)
    pdf.set_right_margin(20)

    body(
        pdf,
        "A 12mm trocar was placed at the umbilicus using the Hasson open technique. "
        "Pneumoperitoneum was established to 15 mmHg. A 10mm 30-degree laparoscope was "
        "inserted. Two additional 5mm trocars were placed: one in the suprapubic region "
        "and one in the left lower quadrant, both under direct visualization.\n\n"
        "Upon exploration, the appendix was identified in the right lower quadrant. It "
        "appeared erythematous, edematous, and inflamed, consistent with acute appendicitis. "
        "There was no evidence of perforation or abscess. A small amount of serous fluid "
        "was noted in the pelvis and was aspirated.\n\n"
        "The mesoappendix was divided using a LigaSure device, progressing from the tip "
        "toward the base. The appendiceal artery was sealed and divided within the "
        "mesoappendix. The base of the appendix was identified at its junction with the "
        "cecum. Two Endoloop ligatures (0-PDS) were placed at the base of the appendix, "
        "and a third was placed 5mm distal. The appendix was divided between the second "
        "and third Endoloops using laparoscopic scissors.\n\n"
        "The appendiceal stump was inspected and found to be secure with no evidence of "
        "bleeding or leak. The appendix was placed in an EndoCatch specimen retrieval bag "
        "and extracted through the umbilical port site. The operative field was irrigated "
        "with warm saline and aspirated. Hemostasis was confirmed throughout.\n\n"
        "The trocars were removed under direct visualization. Pneumoperitoneum was released. "
        "The fascia at the umbilical port was closed with a figure-of-eight 0-Vicryl suture. "
        "All skin incisions were closed with 4-0 Monocryl subcuticular sutures and dressed "
        "with Steri-Strips and sterile dressings.",
        "Times",
        10,
    )

    page_footer_text(
        pdf,
        f"Page 2 of 3  |  {patient.mrn}  |  {patient.name}  |  OPERATIVE REPORT",
        "Times",
    )

    # --- Page 3 ---
    pdf.add_page()
    pdf.set_left_margin(20)
    pdf.set_right_margin(20)

    subheading(pdf, "FINDINGS", "Times", 11)
    body(
        pdf,
        "1. Acutely inflamed, edematous appendix with suppurative changes\n"
        "2. Appendicolith at the base of the appendix\n"
        "3. No perforation or abscess\n"
        "4. Small amount of serous peritoneal fluid (aspirated, not sent for culture)\n"
        "5. Remainder of visualized bowel and pelvic organs unremarkable",
        "Times",
        10,
    )

    subheading(pdf, "SPECIMENS", "Times", 11)
    body(pdf, "Appendix  -- sent to surgical pathology", "Times", 10)

    subheading(pdf, "ESTIMATED BLOOD LOSS", "Times", 11)
    body(pdf, "Minimal (<25 mL)", "Times", 10)

    subheading(pdf, "FLUIDS", "Times", 11)
    body(pdf, "Crystalloid: 1200 mL Lactated Ringer's\nUrine output: 250 mL", "Times", 10)

    subheading(pdf, "DRAINS", "Times", 11)
    body(pdf, "None", "Times", 10)

    subheading(pdf, "COMPLICATIONS", "Times", 11)
    body(pdf, "None", "Times", 10)

    subheading(pdf, "DISPOSITION", "Times", 11)
    body(
        pdf,
        "The patient was extubated in the operating room and transferred to the PACU "
        "in stable condition. Vital signs were stable throughout. The patient was awake, "
        "alert, and comfortable on arrival to PACU.",
        "Times",
        10,
    )

    subheading(pdf, "POSTOPERATIVE PLAN", "Times", 11)
    body(
        pdf,
        "1. Admit to surgical floor (Nelson 4)\n"
        "2. IV ceftriaxone 1g daily x 24 hours (empiric)\n"
        "3. Clear liquid diet, advance as tolerated\n"
        "4. Activity: ambulate day of surgery\n"
        "5. DVT prophylaxis: SCDs + early ambulation\n"
        "6. Blood glucose monitoring per sliding scale insulin protocol\n"
        "7. Anticipate discharge POD 1-2 pending pain control and diet tolerance",
        "Times",
        10,
    )

    pdf.ln(5)
    separator(pdf)

    pdf.set_font("Times", "B", 10)
    pdf.cell(0, 5, "Attending Surgeon:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Times", "", 10)
    pdf.cell(0, 5, "Kathleen M. Reyes, MD, FACS", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Division of General Surgery", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Times", "", 8)
    pdf.cell(0, 4, "Dictated: 03/12/2026 16:30", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4, "Transcribed: 03/12/2026 18:15", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4, "Electronically signed: 03/12/2026 19:00", new_x="LMARGIN", new_y="NEXT")

    page_footer_text(
        pdf,
        f"Page 3 of 3  |  {patient.mrn}  |  {patient.name}  |  OPERATIVE REPORT",
        "Times",
    )


DOCUMENT = DocumentDef(
    name="operative_report",
    description="Operative/surgical report -- formal surgical style",
    render=render,
    single_sided=False,
    back_artifact="blank",
)
