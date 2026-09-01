"""One-off: convert simple markdown docs to PDF using fpdf2."""
import re
import sys

from fpdf import FPDF

REPLACEMENTS = {
    "\u20b9": "Rs. ", "\u2014": "-", "\u2013": "-", "\u2018": "'",
    "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00d7": "x",
    "\u2265": ">=", "\u2264": "<=", "\u2026": "...", "\u00b7": "-",
}


def clean(text: str) -> str:
    for k, v in REPLACEMENTS.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


class DocPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def render(md_path: str, pdf_path: str):
    pdf = DocPDF(format="A4")
    pdf.alias_nb_pages()
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    for raw in open(md_path, encoding="utf-8").read().splitlines():
        line = clean(raw.rstrip())
        stripped = line.strip()
        if stripped == "---":
            pdf.ln(2)
            pdf.set_draw_color(180, 180, 180)
            y = pdf.get_y()
            pdf.line(pdf.l_margin, y, pdf.l_margin + width, y)
            pdf.ln(4)
        elif stripped.startswith("# "):
            pdf.set_font("helvetica", "B", 17)
            pdf.set_text_color(20, 40, 80)
            pdf.multi_cell(width, 8, stripped[2:])
            pdf.ln(2)
        elif stripped.startswith("## "):
            pdf.ln(2)
            pdf.set_font("helvetica", "B", 13.5)
            pdf.set_text_color(20, 40, 80)
            pdf.multi_cell(width, 7, stripped[3:])
            pdf.ln(1)
        elif stripped.startswith("### "):
            pdf.ln(1)
            pdf.set_font("helvetica", "B", 11)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(width, 6, stripped[4:], markdown=True)
        elif stripped.startswith("- "):
            pdf.set_font("helvetica", "", 10)
            pdf.set_text_color(30, 30, 30)
            x = pdf.get_x()
            pdf.cell(6, 5.5, "-")
            pdf.multi_cell(width - 6, 5.5, stripped[2:], markdown=True)
            pdf.set_x(x)
        elif stripped:
            pdf.set_font("helvetica", "", 10)
            pdf.set_text_color(30, 30, 30)
            pdf.multi_cell(width, 5.5, stripped, markdown=True)
        else:
            pdf.ln(2)

    pdf.output(pdf_path)
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2])
