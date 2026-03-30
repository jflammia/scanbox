"""Insurance explanation of benefits -- dense columnar."""

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
    pdf.set_left_margin(12)
    pdf.set_right_margin(12)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, "BlueCross BlueShield", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 7)
    pdf.cell(
        0,
        3.5,
        "P.O. Box 14079, Lexington, KY 40512-4079  |  Member Services: 1-800-810-2583",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)

    pdf.set_fill_color(0, 82, 156)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "  EXPLANATION OF BENEFITS", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(0, 4, "THIS IS NOT A BILL", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 8)
    label_value(pdf, "Member Name", patient.name, "Helvetica", 8)
    label_value(pdf, "Member ID", patient.mrn, "Helvetica", 8)
    label_value(pdf, "Group", "State of Maryland Employees (GRP-40821)", "Helvetica", 8)
    label_value(pdf, "Plan", "PPO Blue Standard", "Helvetica", 8)
    label_value(pdf, "Claim Number", "2026-0318-44729-01", "Helvetica", 8)
    label_value(pdf, "Statement Date", "03/25/2026", "Helvetica", 8)
    label_value(pdf, "Provider", "Memorial Regional Medical Center", "Helvetica", 8)
    label_value(pdf, "Service Dates", "03/10/2026 - 03/14/2026", "Helvetica", 8)
    pdf.ln(2)
    separator(pdf)

    subheading(pdf, "CLAIM DETAILS", "Helvetica", 10)

    # Dense claims table
    pdf.set_font("Helvetica", "B", 6.5)
    col_widths = [55, 20, 22, 22, 22, 22, 22]
    headers = [
        "Service Description",
        "Code",
        "Charged",
        "Allowed",
        "Plan Paid",
        "Adj/Disc",
        "You Owe",
    ]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 4, h, border="B", align="C" if i > 0 else "L")
    pdf.ln()

    claims = [
        (
            "Hospital Room & Board (4 days)",
            "0120",
            "$8,400.00",
            "$4,200.00",
            "$3,360.00",
            "$4,200.00",
            "$840.00",
        ),
        (
            "Emergency Room Visit",
            "0450",
            "$1,850.00",
            "$925.00",
            "$740.00",
            "$925.00",
            "$185.00",
        ),
        (
            "CT Chest w/Contrast",
            "71260",
            "$3,200.00",
            "$1,120.00",
            "$896.00",
            "$2,080.00",
            "$224.00",
        ),
        (
            "Chest X-Ray PA/LAT x2",
            "71046",
            "$640.00",
            "$256.00",
            "$204.80",
            "$384.00",
            "$51.20",
        ),
        (
            "CBC w/Differential x3",
            "85025",
            "$135.00",
            "$67.50",
            "$54.00",
            "$67.50",
            "$13.50",
        ),
        (
            "Comprehensive Metabolic x3",
            "80053",
            "$195.00",
            "$97.50",
            "$78.00",
            "$97.50",
            "$19.50",
        ),
        (
            "Blood Culture x2",
            "87040",
            "$240.00",
            "$120.00",
            "$96.00",
            "$120.00",
            "$24.00",
        ),
        (
            "Procalcitonin",
            "84145",
            "$185.00",
            "$92.50",
            "$74.00",
            "$92.50",
            "$18.50",
        ),
        (
            "IV Ceftriaxone x4",
            "J0696",
            "$480.00",
            "$240.00",
            "$192.00",
            "$240.00",
            "$48.00",
        ),
        (
            "Pharmacy - Misc",
            "0250",
            "$312.00",
            "$156.00",
            "$124.80",
            "$156.00",
            "$31.20",
        ),
        (
            "Endocrinology Consult",
            "99243",
            "$425.00",
            "$212.50",
            "$170.00",
            "$212.50",
            "$42.50",
        ),
        (
            "Pathology - Appendix",
            "88305",
            "$350.00",
            "$175.00",
            "$140.00",
            "$175.00",
            "$35.00",
        ),
        (
            "OR - Lap Appendectomy",
            "44970",
            "$12,500.00",
            "$5,000.00",
            "$4,000.00",
            "$7,500.00",
            "$1,000.00",
        ),
        (
            "Anesthesia",
            "00840",
            "$2,800.00",
            "$1,120.00",
            "$896.00",
            "$1,680.00",
            "$224.00",
        ),
    ]

    pdf.set_font("Courier", "", 6)
    for desc, code, charged, allowed, paid, adj, owe in claims:
        pdf.cell(col_widths[0], 3.8, desc)
        pdf.cell(col_widths[1], 3.8, code, align="C")
        pdf.cell(col_widths[2], 3.8, charged, align="R")
        pdf.cell(col_widths[3], 3.8, allowed, align="R")
        pdf.cell(col_widths[4], 3.8, paid, align="R")
        pdf.cell(col_widths[5], 3.8, adj, align="R")
        pdf.cell(col_widths[6], 3.8, owe, align="R")
        pdf.ln()

    # Totals row
    pdf.set_font("Courier", "B", 6.5)
    pdf.cell(col_widths[0] + col_widths[1], 5, "TOTALS", border="T")
    pdf.cell(col_widths[2], 5, "$31,712.00", border="T", align="R")
    pdf.cell(col_widths[3], 5, "$13,782.00", border="T", align="R")
    pdf.cell(col_widths[4], 5, "$11,025.60", border="T", align="R")
    pdf.cell(col_widths[5], 5, "$17,930.00", border="T", align="R")
    pdf.cell(col_widths[6], 5, "$2,756.40", border="T", align="R")
    pdf.ln(4)

    separator(pdf)

    subheading(pdf, "BENEFIT SUMMARY", "Helvetica", 9)
    pdf.set_font("Helvetica", "", 7.5)
    label_value(pdf, "Individual Deductible", "$500.00 (Met: $500.00)", "Helvetica", 7.5)
    label_value(pdf, "Family Deductible", "$1,500.00 (Met: $1,240.00)", "Helvetica", 7.5)
    label_value(
        pdf,
        "Out-of-Pocket Maximum",
        "$6,000.00 (Accumulated: $3,456.40)",
        "Helvetica",
        7.5,
    )
    label_value(pdf, "Coinsurance", "80/20 after deductible (in-network)", "Helvetica", 7.5)

    page_footer_text(
        pdf,
        f"Page 1 of 2  |  {patient.mrn}  |  Claim 2026-0318-44729-01  |  THIS IS NOT A BILL",
        "Helvetica",
        6,
    )

    # --- Page 2 ---
    pdf.add_page()
    pdf.set_left_margin(12)
    pdf.set_right_margin(12)

    subheading(pdf, "HOW WE CALCULATED YOUR SHARE", "Helvetica", 10)
    body(
        pdf,
        "Total charges from your provider: $31,712.00\n"
        "Our allowed amount (contracted rate): $13,782.00\n"
        "Network savings (you don't owe this): $17,930.00\n\n"
        "From the allowed amount:\n"
        "  Plan paid (80% coinsurance): $11,025.60\n"
        "  Your coinsurance (20%): $2,756.40\n\n"
        "Your deductible was already met for the year, so no additional "
        "deductible was applied to this claim.",
        "Helvetica",
        8.5,
    )

    subheading(pdf, "IMPORTANT NOTES", "Helvetica", 10)
    body(
        pdf,
        "- This is an Explanation of Benefits (EOB), not a bill\n"
        "- Your provider may send you a separate bill for $2,756.40\n"
        "- If you have questions about charges, contact your provider first\n"
        "- To appeal this claim, write to us within 180 days of this statement\n"
        "- Keep this document for your tax records",
        "Helvetica",
        8.5,
    )

    subheading(pdf, "APPEAL RIGHTS", "Helvetica", 10)
    pdf.set_font("Helvetica", "", 7)
    pdf.multi_cell(
        0,
        3.2,
        "If you disagree with this decision, you have the right to appeal. You may file an "
        "internal appeal by writing to: BlueCross BlueShield Appeals Department, P.O. Box "
        "14088, Lexington, KY 40512. Include your member ID, claim number, and a detailed "
        "explanation of why you believe the claim should be reconsidered. You may also "
        "request an external review by an independent organization. Maryland residents may "
        "contact the Maryland Insurance Administration at 1-800-492-6116.",
    )

    pdf.ln(5)
    separator(pdf)
    pdf.set_font("Helvetica", "I", 6.5)
    pdf.multi_cell(
        0,
        3,
        "BlueCross BlueShield of Maryland is an independent licensee of the Blue Cross and "
        "Blue Shield Association. This document contains confidential health information. "
        "Unauthorized use or disclosure is prohibited by law.",
    )

    page_footer_text(
        pdf,
        f"Page 2 of 2  |  {patient.mrn}  |  Claim 2026-0318-44729-01  |  THIS IS NOT A BILL",
        "Helvetica",
        6,
    )


DOCUMENT = DocumentDef(
    name="insurance_eob",
    description="Insurance explanation of benefits -- dense columnar",
    render=render,
    single_sided=False,
    back_artifact="blank",
)
