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
    return item


def _mc(pdf, text, bold=False, size=11):
    pdf.set_font(FONT, "B" if bold else "", size)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 6, text)


def invoice_pdf(inv: dict, clinic: str) -> bytes:
    pdf = new_pdf()
    pdf.set_font(FONT, "B", 18)
    pdf.cell(0, 12, (clinic or "")[:60], ln=True)
    pdf.set_font(FONT, "B", 13)
    pdf.cell(0, 9, f"Invoice {inv.get('invoice_number', '')}", ln=True)
    pdf.ln(2)
    pdf.set_font(FONT, "", 11)

    def row(label, val):
        if val:
            pdf.set_x(pdf.l_margin)
            pdf.cell(45, 7, label, border=0)
            pdf.cell(0, 7, str(val), ln=True)

    row("Patient:", inv.get("patient_name"))
    row("DOB:", inv.get("dob"))
    row("Service Date:", inv.get("service_date"))
    row("Provider:", inv.get("provider"))
    row("Visit Reason:", inv.get("visit_reason"))
    row("ICD-10:", inv.get("icd10"))
    row("Status:", inv.get("status"))
    pdf.ln(3)
    pdf.set_font(FONT, "B", 10)
    pdf.cell(28, 8, "CPT", border=1)
    pdf.cell(90, 8, "Description", border=1)
    pdf.cell(20, 8, "Qty", border=1, align="R")
    pdf.cell(0, 8, "Amount", border=1, ln=True, align="R")
    pdf.set_font(FONT, "", 10)
    for it in inv.get("items", []):
        qty = it.get("quantity", 1)
        pdf.cell(28, 8, str(it.get("cpt_code", ""))[:12], border=1)
        pdf.cell(90, 8, str(it.get("description", ""))[:55], border=1)
        pdf.cell(20, 8, str(qty), border=1, align="R")
        pdf.cell(0, 8, f"${it.get('amount', 0) * qty:.2f}", border=1, ln=True, align="R")
    pdf.set_font(FONT, "B", 11)
    pdf.cell(138, 9, "Total", border=1)
    pdf.cell(0, 9, f"${inv.get('total', 0):.2f}", border=1, ln=True, align="R")
    if inv.get("notes"):
        pdf.ln(3)
        _mc(pdf, f"Notes: {inv['notes']}", size=10)
    return pdf_bytes(pdf)


def note_pdf(note: dict, clinic: str) -> bytes:
    pdf = new_pdf()
    pdf.set_font(FONT, "B", 18)
    pdf.cell(0, 12, (clinic or "")[:60], ln=True)
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
    row("DOB:", note.get("dob"))
    row("Date of Session:", vd)
    row("Provider:", note.get("attending_provider") or note.get("author"))
    row("ICD-10:", note.get("icd10"))
    row("CPT:", note.get("cpt_code"))
    row("Risk:", note.get("risk_level"))
    pdf.ln(3)
    _mc(pdf, note.get("content") or "", size=11)
    if (note.get("signature") or "").startswith("data:image"):
        pdf.ln(4)
        _mc(pdf, "Provider Signature", bold=True, size=9)
        try:
            import base64
            b64 = note["signature"].split(",", 1)[1]
            import io
            img = io.BytesIO(base64.b64decode(b64))
            pdf.image(img, w=45)
        except Exception:
            pass
        if vd:
            _mc(pdf, str(vd), size=9)
    return pdf_bytes(pdf)
