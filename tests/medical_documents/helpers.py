from fpdf import FPDF

LETTER_W = 215.9  # mm
LETTER_H = 279.4  # mm


def new_pdf() -> FPDF:
    pdf = FPDF(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=20)
    return pdf


def add_blank_page(pdf: FPDF) -> None:
    pdf.add_page()
    # Truly blank  -- white page


def add_near_blank_page(pdf: FPDF, artifact: str = "smudge") -> None:
    """Page with minimal marks  -- simulates bleedthrough or faint back-of-form printing."""
    pdf.add_page()
    if artifact == "smudge":
        # Faint gray smudge in corner (scanner artifact / bleedthrough)
        pdf.set_fill_color(230, 230, 230)
        pdf.ellipse(15, 250, 8, 4, style="F")
        pdf.ellipse(22, 255, 5, 3, style="F")
    elif artifact == "footer":
        # Faint form footer that bled through
        pdf.set_font("Helvetica", "", 6)
        pdf.set_text_color(210, 210, 210)
        pdf.set_xy(20, 265)
        pdf.cell(0, 3, "Form MED-2847 Rev. 03/2024")
        pdf.set_text_color(0, 0, 0)


def heading(pdf: FPDF, text: str, font: str = "Helvetica", size: int = 14) -> None:
    pdf.set_font(font, "B", size)
    pdf.cell(0, size * 0.5, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


def subheading(pdf: FPDF, text: str, font: str = "Helvetica", size: int = 11) -> None:
    pdf.set_font(font, "B", size)
    pdf.cell(0, size * 0.45, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def body(pdf: FPDF, text: str, font: str = "Helvetica", size: int = 10) -> None:
    pdf.set_font(font, "", size)
    pdf.multi_cell(0, size * 0.45, text)
    pdf.ln(1)


def label_value(pdf: FPDF, label: str, value: str, font: str = "Helvetica", size: int = 10):
    pdf.set_font(font, "B", size)
    pdf.cell(45, size * 0.5, f"{label}:", new_x="RIGHT")
    pdf.set_font(font, "", size)
    pdf.cell(0, size * 0.5, value, new_x="LMARGIN", new_y="NEXT")


def separator(pdf: FPDF) -> None:
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, LETTER_W - pdf.r_margin, y)
    pdf.ln(3)


def page_footer_text(pdf: FPDF, text: str, font: str = "Helvetica", size: int = 7):
    # Temporarily disable auto page break so writing in the bottom margin
    # doesn't trigger a new page
    pdf.set_auto_page_break(auto=False)
    pdf.set_font(font, "", size)
    pdf.set_xy(pdf.l_margin, LETTER_H - 15)
    pdf.cell(0, 3, text, align="C")
    pdf.set_auto_page_break(auto=True, margin=20)
