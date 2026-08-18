import io
import uuid
import re
from datetime import datetime, timezone
from typing import Optional

import fitz  # PyMuPDF
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel

from core.db import db, now_iso, logger
from core.config import APP_NAME
from core.security import require_roles
from core.audit import log_audit
from core.storage import put_object, get_object, delete_object
from core.folder_filing import disp_date, fmt_date
from core.claim_invoices import payment_recipient_from_fields, progress_note_codes
from routers.settings import get_settings_doc
from routers.claims import (_invoice_pdf, _guess_category, _auto_attach_credentials,
                            _claim_response, FMP_CHECKLIST)

_DOC_CATEGORY_LABELS = dict(FMP_CHECKLIST)
from routers.billing import _compute_next_number

router = APIRouter()

FMP_ROLES = ("admin", "biller")


# ---------------- date helpers ----------------
def _norm(d):
    return str(d or "").strip()[:10]


def _fmt_service_date(iso: str, fmt: str) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", _norm(iso))
    if not m:
        return _norm(iso)
    y, mo, da = m.group(1), m.group(2), m.group(3)
    fmt = (fmt or "MM/DD/YYYY").upper()
    if fmt.startswith("DD"):
        return f"{da}/{mo}/{y}"
    if fmt.startswith("YYYY"):
        return f"{y}-{mo}-{da}"
    return f"{mo}/{da}/{y}"


# ---------------- template models ----------------
class DateField(BaseModel):
    page: int = 0
    fx: float
    fy: float
    fw: float
    fh: float
    date_format: str = "MM/DD/YYYY"
    font_size: int = 12


async def _active_template(patient_id: str):
    return await db.fmp_templates.find_one(
        {"patient_id": patient_id, "active": True}, {"_id": 0})


def _read_payment_recipient(data: bytes) -> Optional[str]:
    """Read one marked payment recipient without assigning a default."""
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        fields = []
        marked_words = []
        label_words = []
        for page in doc:
            widgets = page.widgets()
            if widgets:
                fields.extend((widget.field_name, widget.field_value) for widget in widgets)
            for word in page.get_text("words"):
                value = str(word[4] or "").strip().lower().strip("[]()")
                if value in {"x", "☒", "✓", "✔"}:
                    marked_words.append((page.number, *word[:4]))
                if "veteran" in value or "provider" in value:
                    label_words.append(("veteran" if "veteran" in value else "provider",
                                        page.number, *word[:4]))

        selected = payment_recipient_from_fields(fields)
        if selected:
            return selected

        # Flattened PDFs have no form fields. Accept only an unambiguous mark
        # very near one label; all other layouts require user confirmation.
        nearby = set()
        for page_no, x0, y0, x1, y1 in marked_words:
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            distances = []
            for recipient, label_page, lx0, ly0, lx1, ly1 in label_words:
                if label_page != page_no:
                    continue
                lcx, lcy = (lx0 + lx1) / 2, (ly0 + ly1) / 2
                if abs(cy - lcy) <= 18 and abs(cx - lcx) <= 180:
                    distances.append((abs(cx - lcx) + abs(cy - lcy), recipient))
            if distances:
                distances.sort()
                if len(distances) == 1 or distances[0][0] + 8 < distances[1][0]:
                    nearby.add(distances[0][1])
        return nearby.pop() if len(nearby) == 1 else None
    finally:
        doc.close()


@router.get("/fmp/templates/{patient_id}")
async def get_template(patient_id: str, user: dict = Depends(require_roles(*FMP_ROLES))):
    tpl = await _active_template(patient_id)
    versions = await db.fmp_templates.count_documents({"patient_id": patient_id})
    return {"template": tpl, "versions": versions}


@router.post("/fmp/templates/{patient_id}")
async def upload_template(patient_id: str, file: UploadFile = File(...),
                          user: dict = Depends(require_roles(*FMP_ROLES))):
    p = await db.patients.find_one({"id": patient_id}, {"_id": 0, "first_name": 1, "last_name": 1})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Cover-sheet template must be a PDF")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 20MB)")
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        if doc.needs_pass:
            raise HTTPException(status_code=400, detail="Password-protected PDFs are not supported")
        page_count = doc.page_count
        pr = doc[0].rect
        doc.close()
        payment_to = _read_payment_recipient(data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"fmp template open failed: {e}")
        raise HTTPException(status_code=400, detail="Unsupported or corrupt PDF")

    path = f"{APP_NAME}/fmp/{patient_id}/{uuid.uuid4()}.pdf"
    try:
        result = put_object(path, data, "application/pdf")
    except Exception as e:
        logger.error(f"fmp template store failed: {e}")
        raise HTTPException(status_code=502, detail="File storage failed")

    prev = await db.fmp_templates.count_documents({"patient_id": patient_id})
    # archive previous active
    await db.fmp_templates.update_many(
        {"patient_id": patient_id, "active": True}, {"$set": {"active": False}})
    doc_rec = {"id": str(uuid.uuid4()), "patient_id": patient_id,
               "storage_path": result["path"], "filename": file.filename[:160],
               "page_count": page_count, "page_w": pr.width, "page_h": pr.height,
               "date_field": None, "version": prev + 1, "active": True,
               "payment_to": payment_to,
               "payment_to_source": "cover_sheet" if payment_to else None,
               "uploaded_by": user["name"], "uploaded_by_id": user["id"],
               "uploaded_at": now_iso()}
    await db.fmp_templates.insert_one(doc_rec)
    doc_rec.pop("_id", None)
    await log_audit("create", "fmp_template", actor=user, resource_id=patient_id,
                    detail=f"upload v{doc_rec['version']} {file.filename}")
    return doc_rec


@router.get("/fmp/templates/{patient_id}/preview.png")
async def template_preview(patient_id: str, page: int = 0,
                           user: dict = Depends(require_roles(*FMP_ROLES))):
    tpl = await _active_template(patient_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="No active template")
    data, _ = get_object(tpl["storage_path"])
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        pg = doc[max(0, min(page, doc.page_count - 1))]
        pix = pg.get_pixmap(dpi=110)
        png = pix.tobytes("png")
        doc.close()
    except Exception as e:
        logger.error(f"fmp preview failed: {e}")
        raise HTTPException(status_code=500, detail="Could not render preview")
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.put("/fmp/templates/{tid}/date-field")
async def set_date_field(tid: str, data: DateField, user: dict = Depends(require_roles(*FMP_ROLES))):
    res = await db.fmp_templates.update_one(
        {"id": tid}, {"$set": {"date_field": data.model_dump(), "updated_at": now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    await log_audit("update", "fmp_template", actor=user, resource_id=tid, detail="date field set")
    return await db.fmp_templates.find_one({"id": tid}, {"_id": 0})


@router.post("/fmp/templates/{tid}/archive")
async def archive_template(tid: str, user: dict = Depends(require_roles(*FMP_ROLES))):
    res = await db.fmp_templates.update_one({"id": tid}, {"$set": {"active": False}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    await log_audit("update", "fmp_template", actor=user, resource_id=tid, detail="archived")
    return {"ok": True}


def _stamp_date(original: bytes, field: dict, date_str: str) -> bytes:
    """Return a NEW pdf (bytes) with only the date stamped in the mapped box.
    Original is never modified."""
    doc = fitz.open(stream=original, filetype="pdf")
    page = doc[max(0, min(int(field.get("page", 0)), doc.page_count - 1))]
    W, H = page.rect.width, page.rect.height
    x0 = field["fx"] * W
    y0 = field["fy"] * H
    x1 = (field["fx"] + field["fw"]) * W
    y1 = (field["fy"] + field["fh"]) * H
    rect = fitz.Rect(x0, y0, x1, y1)
    fs = int(field.get("font_size", 12) or 12)
    try:
        page.insert_textbox(rect, date_str, fontsize=fs, fontname="helv",
                            color=(0, 0, 0), align=fitz.TEXT_ALIGN_LEFT)
    except Exception:
        page.insert_text((x0, y1), date_str, fontsize=fs, fontname="helv", color=(0, 0, 0))
    out = doc.tobytes()
    doc.close()
    return out


# ---------------- generate ----------------
class GenerateInput(BaseModel):
    patient_id: str
    note_id: str
    invoice_id: Optional[str] = None
    manual_date: Optional[str] = None
    attachment_item_ids: Optional[list] = None
    payment_to: Optional[str] = None


def _validate(patient, note, invoice, dos):
    """Return (issues, status). status in ready/review/blocked."""
    issues = []

    def add(level, msg):
        issues.append({"level": level, "message": msg})

    pname = f"{patient['first_name']} {patient['last_name']}".strip().lower()
    # date consistency
    note_d = _norm(note.get("visit_date"))
    inv_d = _norm(invoice.get("service_date")) if invoice else ""
    if not dos:
        add("blocked", "No verified date of service was found.")
    if note_d and dos and note_d != dos:
        add("blocked", f"Date mismatch: progress note {disp_date(note_d)} vs selected {disp_date(dos)}.")
    if inv_d and dos and inv_d != dos:
        add("blocked", f"Date mismatch: invoice {disp_date(inv_d)} vs selected {disp_date(dos)}.")
    # patient name match
    if invoice and invoice.get("patient_name") and invoice["patient_name"].strip().lower() != pname:
        add("blocked", "Patient name on the invoice does not match the selected patient.")
    npn = (note.get("patient_name") or "").strip().lower()
    if npn and npn != pname:
        add("warning", "Patient name on the progress note differs from the patient record.")
    # note completeness
    if not (note.get("signature") or "").startswith("data:image"):
        add("warning", "Progress note is not signed.")
    if not note.get("icd10"):
        add("warning", "No diagnosis (ICD-10) code on the progress note.")
    if invoice:
        if not invoice.get("items"):
            add("blocked", "Invoice has no service line items.")
        if not any(it.get("cpt_code") for it in invoice.get("items", [])):
            add("warning", "No procedure (CPT) code on the invoice.")
    else:
        add("warning", "No invoice attached to this claim.")

    if any(i["level"] == "blocked" for i in issues):
        return issues, "blocked"
    if any(i["level"] == "warning" for i in issues):
        return issues, "review"
    return issues, "ready"


@router.post("/fmp/generate")
async def generate_packet(data: GenerateInput, user: dict = Depends(require_roles(*FMP_ROLES))):
    from core.folder_filing import note_pdf
    p = await db.patients.find_one({"id": data.patient_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    note = await db.notes.find_one({"id": data.note_id}, {"_id": 0})
    if not note:
        raise HTTPException(status_code=404, detail="Progress note not found")
    invoice = await db.invoices.find_one({"id": data.invoice_id}, {"_id": 0}) if data.invoice_id else None

    pname = f"{p['first_name']} {p['last_name']}"
    # date of service priority: manual override -> invoice -> signed note
    dos = _norm(data.manual_date) if data.manual_date else ""
    date_source = "manually confirmed" if dos else ""
    if not dos and invoice:
        dos = _norm(invoice.get("service_date"))
        date_source = "invoice service date"
    if not dos:
        dos = _norm(note.get("visit_date"))
        date_source = "signed progress note" if dos else ""

    # Auto-create an invoice from the progress-note header when none is linked
    if invoice is None and note.get("cpt_code"):
        cpt = await db.cpt_codes.find_one({"code": note["cpt_code"]}, {"_id": 0})
        unit = float((cpt or {}).get("amount") or 0)
        item = {"cpt_code": note["cpt_code"], "description": (cpt or {}).get("description", ""),
                "quantity": 4, "minutes": 60, "amount": unit}
        number = await _compute_next_number()
        invoice = {"id": str(uuid.uuid4()), "invoice_number": number, "patient_id": data.patient_id,
                   "patient_name": pname, "dob": p.get("dob"), "ssn": p.get("ssn"),
                   "service_date": dos, "icd10": note.get("icd10"), "provider": note.get("attending_provider"),
                   "items": [item], "total": round(unit * 4, 2), "status": "in_transit", "notes": None,
                   "completed_at": None, "created_at": now_iso(), "created_by": user["name"],
                   "auto_generated": True, "source_note_id": data.note_id}
        await db.invoices.insert_one(dict(invoice))
        invoice.pop("_id", None)

    tpl = await _active_template(data.patient_id)
    if data.payment_to not in (None, "provider", "veteran"):
        raise HTTPException(status_code=400, detail="Payment recipient must be Provider or Veteran")
    payment_to = data.payment_to or (tpl or {}).get("payment_to")
    payment_to_source = "user_confirmed" if data.payment_to else (
        "cover_sheet" if payment_to else None)
    issues, status = _validate(p, note, invoice, dos)
    if not tpl:
        issues.insert(0, {"level": "blocked", "message": "No FMP cover-sheet template uploaded for this patient."})
        status = "blocked"
    elif not tpl.get("date_field"):
        issues.insert(0, {"level": "blocked", "message": "The date-of-service field has not been configured on the cover sheet."})
        status = "blocked"
    if not payment_to:
        issues.insert(0, {"level": "blocked", "message":
                          "Select the payment recipient shown on the completed cover sheet."})
        status = "blocked"

    # duplicate check
    dup = await db.claim_packets.find_one(
        {"patient_id": data.patient_id, "claim_number": dos, "source_note_id": data.note_id})
    duplicate_of = dup["id"] if dup else None
    if dup:
        issues.append({"level": "warning", "message": "A packet already exists for this patient, date and note."})
        if status == "ready":
            status = "review"

    clinic = (await get_settings_doc()).get("clinic_name", "Veterans of Puerto Plata")
    items = []
    cover_review = None

    # 1) cover sheet (stamped copy) — only if template + date field + a date
    if tpl and tpl.get("date_field") and dos:
        try:
            original, _ = get_object(tpl["storage_path"])
            stamped = _stamp_date(original, tpl["date_field"], _fmt_service_date(dos, tpl["date_field"].get("date_format")))
            path = f"{APP_NAME}/fmp/{data.patient_id}/generated/{uuid.uuid4()}.pdf"
            result = put_object(path, stamped, "application/pdf")
            items.append({"id": str(uuid.uuid4()), "source": "upload", "form_id": None,
                          "storage_path": result["path"], "filename": f"FMP_Cover_Sheet_{fmt_date(dos)}.pdf",
                          "content_type": "application/pdf", "size": result.get("size"),
                          "category": "cover_sheet"})
            cover_review = {"original_date": None, "new_date": _fmt_service_date(dos, tpl["date_field"].get("date_format")),
                            "date_source": date_source, "template_version": tpl.get("version"),
                            "only_date_changed": True, "payment_to": payment_to,
                            "payment_to_source": payment_to_source}
        except Exception as e:
            logger.error(f"cover sheet stamp failed: {e}")
            issues.append({"level": "blocked", "message": "Cover-sheet generation failed."})
            status = "blocked"

    # 2) invoice
    if invoice:
        try:
            inv = {**invoice, "patient_name": pname, "dob": p.get("dob")}
            pdf = _invoice_pdf(inv, clinic)
            path = f"{APP_NAME}/fmp/{data.patient_id}/generated/{uuid.uuid4()}.pdf"
            result = put_object(path, pdf, "application/pdf")
            items.append({"id": str(uuid.uuid4()), "source": "invoice", "form_id": None,
                          "invoice_id": invoice["id"], "storage_path": result["path"],
                          "filename": f"Invoice_{invoice.get('invoice_number', invoice['id'][:8])}.pdf",
                          "content_type": "application/pdf", "size": result.get("size"),
                          "category": "invoice",
                          "invoice_number": invoice.get("invoice_number"),
                          "amount": invoice.get("total")})
        except Exception as e:
            logger.error(f"fmp invoice pdf failed: {e}")

    # 3) progress note
    try:
        n = {**note, "patient_name": pname, "dob": p.get("dob"), "ssn": p.get("ssn")}
        pdf = note_pdf(n, clinic)
        path = f"{APP_NAME}/fmp/{data.patient_id}/generated/{uuid.uuid4()}.pdf"
        result = put_object(path, pdf, "application/pdf")
        items.append({"id": str(uuid.uuid4()), "source": "note", "form_id": None, "note_id": note["id"],
                      "storage_path": result["path"], "filename": f"Progress_Note_{fmt_date(dos) if dos else 'note'}.pdf",
                      "content_type": "application/pdf", "size": result.get("size"),
                      "category": "progress_note", **progress_note_codes(note)})
    except Exception as e:
        logger.error(f"fmp note pdf failed: {e}")

    # 4) supporting documents already filed for this patient/day (user-selected)
    for fid in (data.attachment_item_ids or []):
        fi = await db.folder_items.find_one({"id": fid, "patient_id": data.patient_id}, {"_id": 0})
        if fi and fi.get("storage_path"):
            items.append({"id": str(uuid.uuid4()), "source": "upload", "form_id": None,
                          "storage_path": fi["storage_path"],
                          "filename": fi.get("filename") or fi.get("label") or "Document.pdf",
                          "content_type": fi.get("content_type", "application/pdf"),
                          "size": fi.get("size"), "category": _guess_category(fi.get("filename") or fi.get("label") or "")})

    items = await _auto_attach_credentials(items, data.patient_id, note.get("attending_provider"))

    packet = {"id": str(uuid.uuid4()), "name": f"{pname} {disp_date(dos) or ''} FMP Claim".strip(),
              "patient_id": data.patient_id, "patient_name": pname, "claim_number": dos,
              "status": "draft", "notes": None, "items": items,
              "source_note_id": data.note_id, "source_invoice_id": (invoice or {}).get("id"),
              "date_source": date_source, "validation": {"status": status, "issues": issues},
              "cover_review": cover_review, "payment_to": payment_to,
              "payment_to_source": payment_to_source, "approved": False,
              "created_at": now_iso(), "created_by": user["name"], "generated": True}
    await db.claim_packets.insert_one(packet)
    packet.pop("_id", None)
    await log_audit("create", "claim", actor=user, resource_id=packet["id"],
                    detail=f"generated FMP packet {pname} {dos} [{status}]")
    result = await _claim_response(packet["id"])
    result["duplicate_of"] = duplicate_of
    return result


class ApproveInput(BaseModel):
    confirm_cover_date: bool = False


@router.post("/fmp/claims/{cid}/approve")
async def approve_packet(cid: str, data: ApproveInput, user: dict = Depends(require_roles(*FMP_ROLES))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    val = c.get("validation") or {}
    if val.get("status") == "blocked":
        raise HTTPException(status_code=400, detail="Cannot approve a packet with blocked issues. Resolve them first.")
    if c.get("cover_review") and not data.confirm_cover_date:
        raise HTTPException(status_code=400, detail="Please confirm the cover-sheet date of service before approving.")
    await db.claim_packets.update_one({"id": cid}, {"$set": {
        "approved": True, "approved_by": user["name"], "approved_at": now_iso(),
        "status": "complete", "updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail="approved FMP packet")
    return await _claim_response(cid)


# ---------------- cover-sheet corrections ----------------
# Only the date of service may be changed freely (it re-runs the existing
# date-only overlay, which never touches anything else on the signed page).
# Any of these fields being changed means the veteran is certifying a
# different set of facts than what the original signature covers, so a
# fresh e-signature is required before the change is accepted.
SUBSTANTIVE_COVER_FIELDS = (
    "va_claim_number", "veteran_physical_address", "veteran_mailing_address",
    "diagnosis_narrative", "payment_to",
)
COVER_FIELD_LABELS = {
    "va_claim_number": "VA Claim File Number",
    "veteran_physical_address": "Physical Address",
    "veteran_mailing_address": "Mailing Address",
    "diagnosis_narrative": "Diagnosis / Nature of Illness or Injury",
    "payment_to": "Payment To",
}


class CoverAmendmentInput(BaseModel):
    date_of_service: Optional[str] = None
    va_claim_number: Optional[str] = None
    veteran_physical_address: Optional[str] = None
    veteran_mailing_address: Optional[str] = None
    diagnosis_narrative: Optional[str] = None
    payment_to: Optional[str] = None
    veteran_signature: Optional[str] = None  # data:image/png;base64,... — fresh capture, required for substantive changes
    veteran_signed_at: Optional[str] = None


def _build_amendment_page(changes: list, signer_name: str, signature_b64: str,
                          signed_at: str, clinic: str) -> bytes:
    """A new, separately-signed page certifying corrected cover-sheet fields.
    This never edits or replaces the original signed VA form."""
    import base64
    from core.pdf_utils import new_pdf, pdf_bytes, FONT
    pdf = new_pdf()
    pdf.set_font(FONT, "B", 14)
    pdf.cell(0, 10, (clinic or "")[:70], ln=True)
    pdf.set_font(FONT, "B", 12)
    pdf.cell(0, 8, "Veteran Certification of Corrected Information", ln=True)
    pdf.ln(2)
    pdf.set_font(FONT, "", 9.5)
    pdf.multi_cell(0, 5,
        "This page amends specific fields on VA Form 10-7959f-2 for the claim below. "
        "The original signed cover sheet is retained unchanged; this certification covers "
        "only the corrected fields listed here. Federal law provides criminal penalties, "
        "including a fine and/or imprisonment, for any materially false, fictitious, or "
        "fraudulent statement or representation (18 U.S.C. 287 and 1001).")
    pdf.ln(4)
    for label, old_val, new_val in changes:
        pdf.set_font(FONT, "B", 10)
        pdf.cell(0, 6, label, ln=True)
        pdf.set_font(FONT, "", 9.5)
        pdf.multi_cell(0, 5, f"Previously stated: {old_val or '(blank)'}")
        pdf.multi_cell(0, 5, f"Corrected to: {new_val or '(blank)'}")
        pdf.ln(2)
    pdf.ln(4)
    if (signature_b64 or "").startswith("data:image"):
        try:
            b64 = signature_b64.split(",", 1)[1]
            img = io.BytesIO(base64.b64decode(b64))
            pdf.image(img, w=45)
        except Exception:
            pass
    pdf.set_font(FONT, "B", 9)
    pdf.cell(0, 5, "Veteran Signature", ln=True)
    pdf.set_font(FONT, "", 9)
    pdf.cell(0, 5, signer_name or "", ln=True)
    if signed_at:
        pdf.cell(0, 5, disp_date(signed_at[:10]) if len(signed_at) >= 10 else signed_at, ln=True)
    return pdf_bytes(pdf)


@router.post("/fmp/claims/{cid}/amend-cover")
async def amend_cover_sheet(cid: str, data: CoverAmendmentInput,
                            user: dict = Depends(require_roles(*FMP_ROLES))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")

    changed_substantive = []
    for f in SUBSTANTIVE_COVER_FIELDS:
        new_val = getattr(data, f)
        if new_val is not None and _norm(new_val) != _norm(c.get(f, "")):
            changed_substantive.append((f, c.get(f, ""), new_val))

    date_changed = data.date_of_service is not None and _norm(data.date_of_service) != _norm(c.get("claim_number", ""))

    if changed_substantive and not (data.veteran_signature or "").startswith("data:image"):
        fields = ", ".join(COVER_FIELD_LABELS.get(f, f) for f, _, _ in changed_substantive)
        raise HTTPException(status_code=400,
            detail=f"A fresh veteran signature is required to change: {fields}. "
                   f"The date of service alone can be corrected without re-signing.")

    updates = {"updated_at": now_iso()}

    # date-only path: reuse the existing date overlay, original page untouched
    if date_changed:
        tpl = await _active_template(c["patient_id"])
        if tpl and tpl.get("date_field"):
            try:
                original, _ = get_object(tpl["storage_path"])
                stamped = _stamp_date(original, tpl["date_field"],
                                      _fmt_service_date(data.date_of_service, tpl["date_field"].get("date_format")))
                path = f"{APP_NAME}/fmp/{c['patient_id']}/generated/{uuid.uuid4()}.pdf"
                result = put_object(path, stamped, "application/pdf")
                items = c.get("items", [])
                items = [it for it in items if it.get("category") != "cover_sheet"]
                items.insert(0, {"id": str(uuid.uuid4()), "source": "upload", "form_id": None,
                                 "storage_path": result["path"],
                                 "filename": f"FMP_Cover_Sheet_{fmt_date(data.date_of_service)}.pdf",
                                 "content_type": "application/pdf", "size": result.get("size"),
                                 "category": "cover_sheet"})
                updates["items"] = items
            except Exception as e:
                logger.error(f"cover sheet re-stamp failed: {e}")
                raise HTTPException(status_code=500, detail="Could not regenerate the cover sheet with the new date.")
        updates["claim_number"] = _norm(data.date_of_service)

    # substantive changes: never touch the original signed page — attach a
    # separately signed certification page instead
    if changed_substantive:
        clinic = (await get_settings_doc()).get("clinic_name", "Veterans of Puerto Plata")
        display_changes = [(COVER_FIELD_LABELS.get(f, f), old, new) for f, old, new in changed_substantive]
        amendment_pdf = _build_amendment_page(
            display_changes, c.get("patient_name", ""), data.veteran_signature,
            data.veteran_signed_at or now_iso(), clinic)
        path = f"{APP_NAME}/fmp/{c['patient_id']}/generated/{uuid.uuid4()}.pdf"
        result = put_object(path, amendment_pdf, "application/pdf")
        items = updates.get("items", c.get("items", []))
        items = list(items)
        items.append({"id": str(uuid.uuid4()), "source": "upload", "form_id": None,
                      "storage_path": result["path"],
                      "filename": f"Certification_Amendment_{now_iso()[:10]}.pdf",
                      "content_type": "application/pdf", "size": result.get("size"),
                      "category": "certification_amendment"})
        updates["items"] = items
        for f, _old, new in changed_substantive:
            updates[f] = new
        amendments = list(c.get("amendments") or [])
        amendments.append({
            "id": str(uuid.uuid4()), "at": now_iso(), "by": user["name"],
            "changed_fields": [{"field": f, "label": COVER_FIELD_LABELS.get(f, f),
                                "old": old, "new": new} for f, old, new in changed_substantive],
            "veteran_signed_at": data.veteran_signed_at or now_iso(),
        })
        updates["amendments"] = amendments
        # a substantive change invalidates any prior approval — force re-review
        if c.get("approved"):
            updates["approved"] = False
            updates["status"] = "review"

    if not date_changed and not changed_substantive:
        raise HTTPException(status_code=400, detail="No changes were submitted.")

    await db.claim_packets.update_one({"id": cid}, {"$set": updates})
    await log_audit("update", "claim", actor=user, resource_id=cid,
                    detail=f"cover sheet amended (date_changed={date_changed}, "
                           f"substantive_fields={[f for f, _, _ in changed_substantive]})")
    return await _claim_response(cid)


@router.get("/fmp/visits/{patient_id}")
async def patient_visits(patient_id: str, user: dict = Depends(require_roles(*FMP_ROLES))):
    """Signed/available progress notes for a patient, each with a matching invoice (by date) if any."""
    notes = await db.notes.find({"patient_id": patient_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    invoices = await db.invoices.find({"patient_id": patient_id}, {"_id": 0}).to_list(500)
    out = []
    for n in notes:
        vd = _norm(n.get("visit_date")) or _norm((n.get("created_at") or ""))
        inv = next((i for i in invoices if _norm(i.get("service_date")) == vd), None)
        out.append({
            "note_id": n["id"], "date": vd,
            "provider": n.get("attending_provider") or n.get("author") or "",
            "reason": n.get("reason_for_visit") or "",
            "icd10": n.get("icd10") or "", "cpt_code": n.get("cpt_code") or "",
            "signed": bool((n.get("signature") or "").startswith("data:image")),
            "invoice_id": inv["id"] if inv else None,
            "invoice_number": inv.get("invoice_number") if inv else None,
            "invoice_total": inv.get("total") if inv else None,
        })
    return out


@router.get("/fmp/day-files/{patient_id}")
async def day_files(patient_id: str, date: str = "", user: dict = Depends(require_roles(*FMP_ROLES))):
    """Documents already filed in the patient's folder for the given date of service."""
    d = fmt_date(_norm(date)) if date else ""
    subs = await db.folder_subfolders.find({"patient_id": patient_id}, {"_id": 0}).to_list(500)
    sub_ids = [s["id"] for s in subs if (not d or (s.get("name") or "").endswith(d))]
    items = await db.folder_items.find(
        {"patient_id": patient_id, "subfolder_id": {"$in": sub_ids}}, {"_id": 0}).to_list(500)
    out = []
    for it in items:
        fname = it.get("filename") or it.get("label") or "Document"
        cat = _guess_category(fname)
        out.append({"id": it["id"], "filename": fname,
                    "label": it.get("label"), "content_type": it.get("content_type"),
                    "category": cat, "category_label": _DOC_CATEGORY_LABELS.get(cat) if cat else None})
    return out
