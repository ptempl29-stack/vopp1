import os
from fpdf import FPDF

_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
_REG = os.path.join(_FONT_DIR, "DejaVuSans.ttf")
_BOLD = os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")

FONT = "DejaVu"


def new_pdf() -> FPDF:
    pdf = FPDF()
    pdf.add_font(FONT, "", _REG)
    pdf.add_font(FONT, "B", _BOLD)
    pdf.add_page()
    pdf.set_font(FONT, "", 12)
    return pdf


def pdf_bytes(pdf: FPDF) -> bytes:
    out = pdf.output()
    return bytes(out) if isinstance(out, (bytes, bytearray)) else out.encode("latin-1")
