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
from routers.settings import get_settings_doc
from routers.claims import _invoice_pdf, _guess_category
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

    # If a manual date was set on an existing invoice, sync it
    if invoice and data.manual_date and dos:
        await db.invoices.update_one({"id": invoice["id"]}, {"$set": {"service_date": dos}})
        invoice["service_date"] = dos

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
    issues, status = _validate(p, note, invoice, dos)
    if not tpl:
        issues.insert(0, {"level": "blocked", "message": "No FMP cover-sheet template uploaded for this patient."})
        status = "blocked"
    elif not tpl.get("date_field"):
        issues.insert(0, {"level": "blocked", "message": "The date-of-service field has not been configured on the cover sheet."})
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
                            "only_date_changed": True}
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
                          "category": "invoice"})
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
                      "category": "progress_note"})
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

    packet = {"id": str(uuid.uuid4()), "name": f"{pname} {disp_date(dos) or ''} FMP Claim".strip(),
              "patient_id": data.patient_id, "patient_name": pname, "claim_number": dos,
              "status": "draft", "notes": None, "items": items,
              "source_note_id": data.note_id, "source_invoice_id": (invoice or {}).get("id"),
              "date_source": date_source, "validation": {"status": status, "issues": issues},
              "cover_review": cover_review, "approved": False,
              "created_at": now_iso(), "created_by": user["name"], "generated": True}
    await db.claim_packets.insert_one(packet)
    packet.pop("_id", None)
    await log_audit("create", "claim", actor=user, resource_id=packet["id"],
                    detail=f"generated FMP packet {pname} {dos} [{status}]")
    packet["duplicate_of"] = duplicate_of
    return packet


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
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


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
    return [{"id": it["id"], "filename": it.get("filename") or it.get("label") or "Document",
             "label": it.get("label"), "content_type": it.get("content_type")} for it in items]
