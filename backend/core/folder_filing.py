import uuid
import re
from datetime import datetime, timezone

from core.db import db, now_iso, logger
from core.config import APP_NAME
from core.storage import put_object
from core.pdf_utils import new_pdf, pdf_bytes, FONT


def fmt_date(d) -> str:
    """Return a date as MM-DD-YYYY. Accepts YYYY-MM-DD (or ISO) input; passes through otherwise."""
    s = str(d or "").strip()[:10]
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    return f"{m.group(2)}-{m.group(3)}-{m.group(1)}" if m else s


def disp_date(d) -> str:
    """Return a date as MM/DD/YYYY for document display. Passes through non-date strings."""
    s = str(d or "").strip()[:10]
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    return f"{m.group(2)}/{m.group(3)}/{m.group(1)}" if m else str(d or "")



async def _ensure_subfolder(patient_id: str, name: str, user: dict) -> str:
    sf = await db.folder_subfolders.find_one({"patient_id": patient_id, "name": name}, {"_id": 0})
    if sf:
        return sf["id"]
    doc = {"id": str(uuid.uuid4()), "patient_id": patient_id, "name": name[:80],
           "created_at": now_iso(), "created_by": user.get("name"), "created_by_id": user.get("id")}
    await db.folder_subfolders.insert_one(doc)
    return doc["id"]


async def file_pdf_into_folder(patient_id, first_name, pdf_data, label, filename, user, date_str=None):
    """Store a generated PDF into the patient's folder under a '{first_name} MM-DD-YYYY' subfolder.
    date_str (the document's date of service) drives the subfolder date; falls back to today.
    Creates the subfolder if missing. Returns the folder item, or None on failure."""
    if not patient_id:
        return None
    date_out = fmt_date(date_str) if date_str else datetime.now(timezone.utc).strftime("%m-%d-%Y")
    sub_name = f"{(first_name or 'Patient').strip()} {date_out}"
    sid = await _ensure_subfolder(patient_id, sub_name, user)
    path = f"{APP_NAME}/folders/{patient_id}/{uuid.uuid4()}.pdf"
    try:
        result = put_object(path, pdf_data, "application/pdf")
    except Exception as e:
        logger.error(f"folder auto-file failed: {e}")
        return None
    item = {"id": str(uuid.uuid4()), "patient_id": patient_id, "subfolder_id": sid,
            "source": "upload", "form_id": None, "storage_path": result["path"],
            "filename": filename[:120], "label": label[:120], "description": "Auto-saved PDF",
            "content_type": "application/pdf", "size": result.get("size"),
            "created_at": now_iso(), "created_by": user.get("name"), "created_by_id": user.get("id")}
    await db.folder_items.insert_one(item)
    item.pop("_id", None)
    try:
        from routers.claims import _sync_folder_item_claims
        await _sync_folder_item_claims(item)
    except Exception as e:
        logger.error(f"folder-item claim auto-sync failed: {e}")
    return item


def _mc(pdf, text, bold=False, size=11):
    pdf.set_font(FONT, "B" if bold else "", size)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 6, text)


_INV_STATUS_LABELS = {"paid": "Paid", "in_transit": "In Transit", "denied": "Denied",
                      "unpaid": "Unpaid", "void": "Draft", "outstanding": "Outstanding"}
_INV_STATUS_COLORS = {
    "paid": ((220, 252, 231), (21, 128, 61)),
    "in_transit": ((254, 243, 199), (180, 83, 9)),
    "unpaid": ((254, 243, 199), (180, 83, 9)),
    "outstanding": ((254, 243, 199), (180, 83, 9)),
    "denied": ((254, 226, 226), (185, 28, 28)),
    "void": ((243, 244, 246), (75, 85, 99)),
}


def invoice_pdf(inv: dict, settings: dict = None) -> bytes:
    """Render an invoice PDF styled to match the in-app invoice view: clinic
    letterhead (logo/tagline/RNC/contact), a status badge, a two-column
    Patient/Invoice information block, and a dark-green line-item table."""
    import io
    import base64

    settings = settings or {}
    clinic = settings.get("clinic_name") or "Veterans of Puerto Plata"
    tagline = settings.get("tagline") or ""
    rnc = settings.get("rnc") or ""
    address = settings.get("address") or ""
    phone = settings.get("phone") or ""
    whatsapp = settings.get("whatsapp") or ""
    email = settings.get("email") or ""
    mailing = settings.get("mailing_address") or ""
    insurance = settings.get("primary_insurance") or ""
    logo = settings.get("logo") or ""

    GREEN = (21, 94, 61)
    GREEN_MID = (34, 124, 82)
    GREEN_DARK = (23, 61, 44)
    TAN = (250, 246, 238)
    INK = (33, 33, 33)
    GREY = (115, 115, 115)
    GREY_LT = (222, 222, 222)

    pdf = new_pdf()
    content_w = pdf.w - pdf.l_margin - pdf.r_margin
    x0 = pdf.l_margin

    # ---- Letterhead ----
    logo_w = 20
    y0 = pdf.get_y()
    embedded = False
    if logo.startswith("data:image"):
        try:
            b64 = logo.split(",", 1)[1]
            img = io.BytesIO(base64.b64decode(b64))
            pdf.image(img, x=x0, y=y0, w=logo_w, h=logo_w)
            embedded = True
        except Exception:
            embedded = False
    if not embedded:
        pdf.set_fill_color(*GREEN_MID)
        pdf.rect(x0, y0, logo_w, logo_w, style="F")

    text_x = x0 + logo_w + 5
    text_w = content_w - logo_w - 5
    pdf.set_xy(text_x, y0)
    pdf.set_text_color(*GREEN)
    pdf.set_font(FONT, "B", 16)
    pdf.multi_cell(text_w, 7, clinic[:70])
    if tagline:
        pdf.set_x(text_x)
        pdf.set_text_color(*GREY)
        pdf.set_font(FONT, "", 9)
        pdf.cell(text_w, 5, tagline[:80], ln=True)
    if rnc:
        pdf.set_x(text_x)
        pdf.set_text_color(60, 60, 60)
        pdf.set_font(FONT, "B", 8)
        pdf.cell(text_w, 4.5, f"RNC: {rnc}", ln=True)

    pdf.set_y(max(pdf.get_y(), y0 + logo_w) + 2)

    contact_bits = [b for b in [address, phone, (f"WhatsApp: {whatsapp}" if whatsapp else ""), email] if b]
    if contact_bits:
        pdf.set_x(x0)
        pdf.set_font(FONT, "", 8)
        pdf.set_text_color(*GREY)
        pdf.multi_cell(content_w, 4.5, "   |   ".join(contact_bits))

    extra_bits = [b for b in [(f"Mailing Address: {mailing}" if mailing else ""),
                               (f"Primary Insurance: {insurance}" if insurance else "")] if b]
    if extra_bits:
        pdf.set_x(x0)
        pdf.set_font(FONT, "", 8)
        pdf.set_text_color(*GREY)
        pdf.multi_cell(content_w, 4.5, "   |   ".join(extra_bits))

    pdf.set_text_color(*INK)
    pdf.ln(1)
    pdf.set_draw_color(*GREEN_MID)
    pdf.set_line_width(0.6)
    yline = pdf.get_y()
    pdf.line(x0, yline, x0 + content_w, yline)
    pdf.ln(5)

    # ---- Invoice number / date (left) + status badge (right) ----
    y2 = pdf.get_y()
    pdf.set_xy(x0, y2)
    pdf.set_font(FONT, "B", 12)
    pdf.set_text_color(*GREEN)
    pdf.cell(content_w * 0.6, 6, str(inv.get("invoice_number") or ""), ln=True)
    pdf.set_x(x0)
    pdf.set_font(FONT, "", 9)
    pdf.set_text_color(*GREY)
    pdf.cell(content_w * 0.6, 5, disp_date(inv.get("service_date")) or "", ln=True)

    status = inv.get("status") or ""
    label = _INV_STATUS_LABELS.get(status, status.title() if status else "")
    bg, fg = _INV_STATUS_COLORS.get(status, ((243, 244, 246), (75, 85, 99)))
    if label:
        pdf.set_font(FONT, "B", 8.5)
        bw = pdf.get_string_width(label) + 8
        pdf.set_xy(x0 + content_w - bw, y2)
        pdf.set_fill_color(*bg)
        pdf.set_text_color(*fg)
        pdf.cell(bw, 7, label, align="C", fill=True)
    pdf.set_text_color(*INK)
    pdf.set_y(max(pdf.get_y(), y2 + 12))
    pdf.ln(4)

    # ---- Two-column Patient / Invoice information ----
    col_w = content_w / 2 - 4
    col1_x, col2_x = x0, x0 + content_w / 2 + 4
    top_y = pdf.get_y()

    def section(xcol, title_txt, rows):
        pdf.set_xy(xcol, top_y)
        pdf.set_font(FONT, "B", 8.5)
        pdf.set_text_color(*GREEN)
        pdf.cell(col_w, 5, title_txt.upper())
        liney = top_y + 5.5
        pdf.set_draw_color(*GREY_LT)
        pdf.set_line_width(0.2)
        pdf.line(xcol, liney, xcol + col_w, liney)
        yy = liney + 2
        for lbl, val in rows:
            val = str(val) if val not in (None, "") else "\u2014"
            pdf.set_xy(xcol, yy)
            pdf.set_font(FONT, "B", 7.5)
            pdf.set_text_color(*GREY)
            pdf.cell(col_w * 0.42, 5, lbl)
            pdf.set_xy(xcol + col_w * 0.42, yy)
            pdf.set_font(FONT, "", 8.5)
            pdf.set_text_color(*INK)
            pdf.multi_cell(col_w * 0.58, 5, val)
            yy = max(yy + 5, pdf.get_y())
        return yy

    completed = inv.get("completed_at")
    y_left = section(col1_x, "Patient Information", [
        ("Full Name:", inv.get("patient_name")),
        ("DOB:", disp_date(inv.get("dob")) if inv.get("dob") else ""),
        ("SSN:", (lambda d: f"***-**-{d[-4:]}" if len(d) >= 4 else "")("".join(ch for ch in str(inv.get("ssn") or "") if ch.isdigit()))),
        ("Gender:", inv.get("gender")),
        ("Policy #:", inv.get("policy_number")),
    ])
    y_right = section(col2_x, "Invoice Information", [
        ("Invoice #:", inv.get("invoice_number")),
        ("Date:", disp_date(inv.get("service_date"))),
        ("Completed:", disp_date(str(completed)[:10]) if completed else ""),
        ("Status:", label or status),
        ("Visit Reason:", inv.get("visit_reason")),
        ("ICD-10-CM:", inv.get("icd10")),
        ("Provider:", inv.get("provider")),
    ])
    pdf.set_text_color(*INK)
    pdf.set_y(max(y_left, y_right) + 4)

    # ---- Line-item table ----
    col_widths = [22, content_w - (22 + 16 + 20 + 26 + 26), 16, 20, 26, 26]
    labels = ["CPT CODE", "SERVICE DESCRIPTION", "UNITS", "MINUTES", "UNIT PRICE", "FEE"]
    pdf.set_x(x0)
    pdf.set_fill_color(*GREEN_DARK)
    pdf.set_text_color(*TAN)
    pdf.set_font(FONT, "B", 7.5)
    for w, lbl in zip(col_widths, labels):
        pdf.cell(w, 7, lbl, border=1, fill=True, align=("R" if lbl == "FEE" else "L"))
    pdf.ln(7)

    pdf.set_font(FONT, "", 8.5)
    pdf.set_draw_color(*GREY_LT)
    running_total = 0.0
    for it in inv.get("items", []):
        qty = float(it.get("quantity") or 0)
        amount = float(it.get("amount") or 0)
        fee = amount * qty
        running_total += fee
        qty_disp = str(int(qty)) if qty == int(qty) else str(qty)
        pdf.set_x(x0)
        pdf.set_text_color(*INK)
        pdf.set_font(FONT, "", 8.5)
        pdf.cell(col_widths[0], 7, str(it.get("cpt_code", ""))[:12], border=1)
        pdf.cell(col_widths[1], 7, str(it.get("description", ""))[:55], border=1)
        pdf.cell(col_widths[2], 7, qty_disp, border=1)
        pdf.cell(col_widths[3], 7, str(int(qty * 15)), border=1)
        pdf.cell(col_widths[4], 7, f"${amount:.2f}", border=1)
        pdf.set_font(FONT, "B", 8.5)
        pdf.set_text_color(*GREEN)
        pdf.cell(col_widths[5], 7, f"${fee:.2f}", border=1, align="R")
        pdf.ln(7)

    pdf.ln(3)
    total_val = inv.get("total")
    total_val = float(total_val) if total_val not in (None, "") else running_total
    pdf.set_x(x0)
    pdf.set_font(FONT, "B", 9)
    pdf.set_text_color(*GREY)
    pdf.cell(content_w - 40, 8, "TOTAL", align="R")
    pdf.set_font(FONT, "B", 16)
    pdf.set_text_color(*GREEN)
    pdf.cell(40, 8, f"${total_val:.2f}", align="R", ln=True)

    if inv.get("notes"):
        pdf.ln(3)
        pdf.set_text_color(*INK)
        _mc(pdf, f"Notes: {inv['notes']}", size=10)
    return pdf_bytes(pdf)


def note_pdf(note: dict, clinic: str, rnc: str = "") -> bytes:
    pdf = new_pdf()
    pdf.set_font(FONT, "B", 18)
    pdf.cell(0, 12, (clinic or "")[:60], ln=True)
    if rnc:
        pdf.set_font(FONT, "", 9)
        pdf.cell(0, 5, f"RNC: {rnc}", ln=True)
    pdf.set_font(FONT, "B", 13)
    pdf.cell(0, 9, "Progress Note", ln=True)
    pdf.ln(2)

    def row(label, val):
        if val:
            pdf.set_x(pdf.l_margin)
            pdf.set_font(FONT, "B", 10)
            pdf.cell(45, 7, label, border=0)
            pdf.set_font(FONT, "", 10)
            pdf.cell(0, 7, str(val), ln=True)

    vd = note.get("visit_date")
    row("Patient:", note.get("patient_name"))
    row("DOB:", disp_date(note.get("dob")))
    row("Date of Session:", disp_date(vd))
    row("Provider:", note.get("attending_provider") or note.get("author"))
    row("ICD-10:", note.get("icd10"))
    row("CPT:", note.get("cpt_code"))
    row("Risk:", note.get("risk_level"))
    pdf.ln(3)
    _mc(pdf, note.get("content") or "", size=11)
    if (note.get("signature") or "").startswith("data:image"):
        pdf.ln(4)
        try:
            import base64
            b64 = note["signature"].split(",", 1)[1]
            import io
            img = io.BytesIO(base64.b64decode(b64))
            pdf.image(img, w=45)
        except Exception:
            pass
        date_disp = fmt_date(vd).replace("-", "/") if vd else ""
        _mc(pdf, "Provider Signature", bold=True, size=9)
        if note.get("exequatur_number"):
            _mc(pdf, f"Exequatur Num: {note['exequatur_number']}", size=9)
        if date_disp:
            _mc(pdf, date_disp, size=9)
        signer = note.get("attending_provider") or "Saday Rodriguez Cabrera"
        pdf.ln(1)
        _mc(pdf, f"This Document has been electronically signed by {signer} on {disp_date(vd)}.", size=8)
    elif note.get("exequatur_number"):
        pdf.ln(4)
        prov = note.get("attending_provider") or note.get("author") or ""
        if prov:
            _mc(pdf, prov, bold=True, size=9)
        _mc(pdf, f"Exequatur Num: {note['exequatur_number']}", size=9)
    return pdf_bytes(pdf)
