"""CBC with Differential -- Quest Diagnostics style."""

from __future__ import annotations

from dataclasses import dataclass, field

from fpdf import FPDF

from tests.medical_documents import DocumentDef, PatientContext
from tests.medical_documents.helpers import body, label_value, page_footer_text, separator


@dataclass
class CBCLabConfig:
    wbc: float = field(default=11.2, metadata={"description": "White blood cell count (x10E3/uL)"})
    glucose: int = field(default=142, metadata={"description": "Fasting glucose (mg/dL)"})
    a1c: float = field(default=7.2, metadata={"description": "Hemoglobin A1C (%)"})
    date_collected: str = field(
        default="03/15/2026", metadata={"description": "Specimen collection date"}
    )
    ordering_md: str = field(
        default="Dr. Anish Patel, MD", metadata={"description": "Ordering physician"}
    )


def render(pdf: FPDF, patient: PatientContext, config: CBCLabConfig | None = None) -> None:
    config = config or CBCLabConfig()

    # --- Page 1 ---
    pdf.add_page()
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)

    # Letterhead
    pdf.set_font("Courier", "B", 16)
    pdf.cell(0, 8, "QUEST DIAGNOSTICS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Courier", "", 8)
    pdf.cell(0, 4, "500 Plaza Drive, Secaucus, NJ 07094", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4, "CLIA No: 31D0714264  |  Dir: Dr. F. Morales, MD", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    separator(pdf)

    # Patient info
    pdf.set_font("Courier", "B", 11)
    pdf.cell(0, 5, "PATIENT REPORT", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Courier", "", 9)
    label_value(pdf, "Patient", patient.name_last_first, "Courier", 9)
    label_value(pdf, "DOB", f"{patient.dob}  (Age {patient.age})", "Courier", 9)
    label_value(pdf, "Gender", patient.gender, "Courier", 9)
    label_value(pdf, "Patient ID", patient.mrn, "Courier", 9)
    label_value(pdf, "Specimen", "Blood, Venipuncture", "Courier", 9)
    label_value(pdf, "Collected", f"{config.date_collected} 07:45 AM", "Courier", 9)
    label_value(pdf, "Received", "03/15/2026 10:12 AM", "Courier", 9)
    label_value(pdf, "Reported", "03/15/2026 16:30 PM", "Courier", 9)
    label_value(pdf, "Ordering MD", config.ordering_md, "Courier", 9)
    label_value(pdf, "Account", "Patel Internal Medicine", "Courier", 9)
    pdf.ln(3)
    separator(pdf)

    # CBC table header
    pdf.set_font("Courier", "B", 9)
    pdf.cell(55, 5, "TEST", border="B")
    pdf.cell(25, 5, "RESULT", border="B", align="R")
    pdf.cell(10, 5, "FLAG", border="B", align="C")
    pdf.cell(40, 5, "REFERENCE", border="B", align="R")
    pdf.cell(30, 5, "UNITS", border="B", align="R")
    pdf.ln()

    rows = [
        ("WBC", str(config.wbc), "H", "4.0-10.5", "x10E3/uL"),
        ("RBC", "4.35", "", "3.77-5.28", "x10E6/uL"),
        ("Hemoglobin", "13.1", "", "11.1-15.9", "g/dL"),
        ("Hematocrit", "39.2", "", "34.0-46.6", "%"),
        ("MCV", "90.1", "", "79.0-97.0", "fL"),
        ("MCH", "30.1", "", "26.6-33.0", "pg"),
        ("MCHC", "33.4", "", "31.5-35.7", "g/dL"),
        ("RDW", "13.8", "", "11.6-15.4", "%"),
        ("Platelets", "245", "", "150-379", "x10E3/uL"),
        ("MPV", "10.2", "", "7.4-10.4", "fL"),
        ("Neutrophils", "72", "H", "40-60", "%"),
        ("Lymphocytes", "18", "L", "20-40", "%"),
        ("Monocytes", "7", "", "2-8", "%"),
        ("Eosinophils", "2", "", "1-4", "%"),
        ("Basophils", "1", "", "0-2", "%"),
        ("Abs Neutrophils", "8.06", "H", "1.4-7.0", "x10E3/uL"),
        ("Abs Lymphocytes", "2.02", "", "0.7-3.1", "x10E3/uL"),
        ("Abs Monocytes", "0.78", "", "0.1-0.9", "x10E3/uL"),
        ("Abs Eosinophils", "0.22", "", "0.0-0.4", "x10E3/uL"),
        ("Abs Basophils", "0.11", "", "0.0-0.2", "x10E3/uL"),
    ]

    pdf.set_font("Courier", "", 8)
    for test, result, flag, ref, units in rows:
        pdf.cell(55, 4, test)
        pdf.cell(25, 4, result, align="R")
        if flag:
            pdf.set_text_color(180, 0, 0)
            pdf.set_font("Courier", "B", 8)
        pdf.cell(10, 4, flag, align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Courier", "", 8)
        pdf.cell(40, 4, ref, align="R")
        pdf.cell(30, 4, units, align="R")
        pdf.ln()

    pdf.ln(3)
    pdf.set_font("Courier", "", 7)
    pdf.cell(0, 3, "H = Above normal   L = Below normal", new_x="LMARGIN", new_y="NEXT")
    page_footer_text(pdf, f"Page 1 of 2  |  {patient.mrn}  |  {patient.name_last_first}", "Courier")

    # --- Page 2 ---
    pdf.add_page()
    pdf.set_font("Courier", "B", 11)
    pdf.cell(0, 5, "COMPREHENSIVE METABOLIC PANEL", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    separator(pdf)

    pdf.set_font("Courier", "B", 9)
    pdf.cell(55, 5, "TEST", border="B")
    pdf.cell(25, 5, "RESULT", border="B", align="R")
    pdf.cell(10, 5, "FLAG", border="B", align="C")
    pdf.cell(40, 5, "REFERENCE", border="B", align="R")
    pdf.cell(30, 5, "UNITS", border="B", align="R")
    pdf.ln()

    cmp_rows = [
        ("Glucose", str(config.glucose), "H", "74-106", "mg/dL"),
        ("BUN", "18", "", "6-24", "mg/dL"),
        ("Creatinine", "0.91", "", "0.57-1.00", "mg/dL"),
        ("eGFR", ">60", "", ">59", "mL/min/1.73"),
        ("BUN/Creatinine", "20", "", "8-27", "ratio"),
        ("Sodium", "140", "", "134-144", "mEq/L"),
        ("Potassium", "4.3", "", "3.5-5.2", "mEq/L"),
        ("Chloride", "101", "", "96-106", "mEq/L"),
        ("Carbon Dioxide", "24", "", "18-29", "mEq/L"),
        ("Calcium", "9.6", "", "8.7-10.2", "mg/dL"),
        ("Protein, Total", "7.1", "", "6.0-8.5", "g/dL"),
        ("Albumin", "4.2", "", "3.5-5.5", "g/dL"),
        ("Bilirubin, Total", "0.8", "", "0.0-1.2", "mg/dL"),
        ("Alk Phosphatase", "72", "", "44-121", "IU/L"),
        ("AST (SGOT)", "24", "", "0-40", "IU/L"),
        ("ALT (SGPT)", "31", "", "0-44", "IU/L"),
        ("A1C", str(config.a1c), "H", "4.8-5.6", "%"),
    ]

    pdf.set_font("Courier", "", 8)
    for test, result, flag, ref, units in cmp_rows:
        pdf.cell(55, 4, test)
        pdf.cell(25, 4, result, align="R")
        if flag:
            pdf.set_text_color(180, 0, 0)
            pdf.set_font("Courier", "B", 8)
        pdf.cell(10, 4, flag, align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Courier", "", 8)
        pdf.cell(40, 4, ref, align="R")
        pdf.cell(30, 4, units, align="R")
        pdf.ln()

    pdf.ln(5)
    separator(pdf)
    pdf.set_font("Courier", "", 8)
    body(
        pdf,
        "NOTES: Elevated glucose and A1C consistent with diabetes mellitus. "
        "Elevated WBC and neutrophils may indicate acute infection or stress response. "
        "Clinical correlation recommended. Fasting specimen confirmed.",
        "Courier",
        8,
    )
    pdf.ln(2)
    pdf.set_font("Courier", "B", 8)
    pdf.cell(
        0,
        4,
        "Electronically verified by: Frances K. Morales, MD",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_font("Courier", "", 7)
    pdf.cell(0, 3, "03/15/2026 16:30  |  Final Report", new_x="LMARGIN", new_y="NEXT")
    page_footer_text(pdf, f"Page 2 of 2  |  {patient.mrn}  |  {patient.name_last_first}", "Courier")


DOCUMENT = DocumentDef(
    name="cbc_lab_report",
    description="CBC with Differential + CMP -- Quest Diagnostics style",
    render=render,
    default_config_cls=CBCLabConfig,
    single_sided=False,
    back_artifact="blank",
)
