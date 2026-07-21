import io
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from core.db import db, now_iso, logger
from core.config import APP_NAME, EXT_CONTENT_TYPES
from core.security import require_roles
from core.audit import log_audit
from core.storage import put_object, get_object, delete_object
from routers.settings import get_settings_doc
from core.pdf_utils import new_pdf, pdf_bytes, FONT

router = APIRouter()


def _invoice_pdf(inv: dict, clinic: str) -> bytes:
    pdf = new_pdf()
    pdf.set_font(FONT, "B", 18)
    pdf.cell(0, 12, (clinic or "")[:60], ln=True)
    pdf.set_font(FONT, "B", 13)
    pdf.cell(0, 9, f"Invoice {inv.get('invoice_number', '')}", ln=True)
    pdf.ln(2)
    pdf.set_font(FONT, "", 11)

    def row(label, val):
        if val:
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
        pdf.set_font(FONT, "", 10)
        pdf.multi_cell(0, 6, f"Notes: {inv['notes']}")
    return pdf_bytes(pdf)

CLAIM_STATUSES = {"draft", "submitted", "complete"}
UPLOAD_EXTS = {"pdf", "png", "jpg", "jpeg", "webp", "doc", "docx", "txt", "xls", "xlsx"}
EXTRA_CT = {"xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


class ClaimInput(BaseModel):
    name: str
    patient_id: Optional[str] = None
    claim_number: Optional[str] = None
    status: str = "draft"
    notes: Optional[str] = None
    va_claim_number: Optional[str] = None
    veteran_physical_address: Optional[str] = None
    veteran_mailing_address: Optional[str] = None
    diagnosis_narrative: Optional[str] = None
    payment_to: Optional[str] = "provider"


_COVER_FIELDS = ("va_claim_number", "veteran_physical_address",
                 "veteran_mailing_address", "diagnosis_narrative", "payment_to")


async def _patient_name(pid):
    if not pid:
        return None
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    return f"{p['first_name']} {p['last_name']}" if p else None


def _merge_items_pdf(items) -> bytes:
    from pypdf import PdfWriter, PdfReader
    from PIL import Image
    writer = PdfWriter()
    added = 0
    for item in items:
        try:
            data, _ = get_object(item["storage_path"])
            fn = item["filename"].lower()
            if fn.endswith(".pdf"):
                for page in PdfReader(io.BytesIO(data)).pages:
                    writer.add_page(page)
                added += 1
            elif fn.rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp"):
                img = Image.open(io.BytesIO(data)).convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="PDF")
                for page in PdfReader(io.BytesIO(buf.getvalue())).pages:
                    writer.add_page(page)
                added += 1
        except Exception as e:
            logger.error(f"merge skip {item.get('filename')}: {e}")
    if added == 0:
        raise HTTPException(status_code=400, detail="No PDF/image documents to merge in this packet")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


FMP_CHECKLIST = [
    ("cover_sheet", "FMP Claim Cover Sheet (VA Form 10-7959f-2)"),
    ("invoice", "Itemized Invoice"),
    ("progress_note", "Signed Clinical Progress Note / Initial Evaluation"),
    ("va_disability_letter", "VA Disability Verification Letter"),
    ("fmp_registration", "FMP Registration Form (VA Form 10-7959f-1)"),
    ("provider_exequatur", "Provider Exequatur"),
    ("provider_diploma", "Provider Diploma"),
]


async def _build_packet_pdf(c) -> bytes:
    """Build the full FMP packet PDF: auto-generated Summary cover + Checklist pages,
    followed by every attached document (merged)."""
    from pypdf import PdfWriter, PdfReader
    from PIL import Image
    from core.pdf_utils import new_pdf, pdf_bytes, FONT
    from core.folder_filing import fmt_date, disp_date

    settings = await get_settings_doc()
    clinic = settings.get("clinic_name", "Veterans of Puerto Plata")
    clinic_addr = settings.get("address", "")
    items = c.get("items", [])

    p = await db.patients.find_one({"id": c.get("patient_id")}, {"_id": 0}) if c.get("patient_id") else None
    vet_name = c.get("patient_name") or (f"{p['first_name']} {p['last_name']}" if p else "")
    dob = (p or {}).get("dob", "")
    ssn = (p or {}).get("ssn", "")

    inv = None
    inv_item = next((i for i in items if i.get("source") == "invoice" and i.get("invoice_id")), None)
    if inv_item:
        inv = await db.invoices.find_one({"id": inv_item["invoice_id"]}, {"_id": 0})
    note = None
    note_item = next((i for i in items if i.get("source") == "note" and i.get("note_id")), None)
    if note_item:
        note = await db.notes.find_one({"id": note_item["note_id"]}, {"_id": 0})

    provider = (inv or {}).get("attending_provider") or (note or {}).get("attending_provider") or ""
    icd = (inv or {}).get("icd10") or (note or {}).get("icd10") or ""
    diagnosis = c.get("diagnosis_narrative") or icd
    cpt_desc = ""
    if inv and inv.get("items"):
        it0 = inv["items"][0]
        cpt_desc = f"{it0.get('cpt_code', '')} - {it0.get('description', '')}".strip(" -")
    elif note:
        cpt_desc = note.get("cpt_code", "") or ""
    inv_no = (inv or {}).get("invoice_number", "")
    amount = (inv or {}).get("total")
    svc_date = disp_date(c.get("claim_number")) or disp_date((inv or {}).get("service_date")) or ""
    pay = "Provider payment requested - Provider box on VA Form 10-7959f-2" \
        if (c.get("payment_to") or "provider") == "provider" else "Veteran payment requested"

    pdf = new_pdf()
    pdf.set_font(FONT, "B", 15)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 8, "Foreign Medical Program (FMP) Fully Developed Claim Packet")
    pdf.ln(2)

    def row(label, val):
        pdf.set_x(pdf.l_margin)
        y0 = pdf.get_y()
        pdf.set_font(FONT, "B", 10)
        pdf.multi_cell(54, 7, label)
        pdf.set_xy(pdf.l_margin + 54, y0)
        pdf.set_font(FONT, "", 10)
        pdf.multi_cell(0, 7, str(val or "-"))

    row("Veteran:", vet_name)
    row("Date of Birth:", disp_date(dob) if dob else "")
    row("SSN / VA Claim File No.:", f"{ssn or '-'} / {c.get('va_claim_number') or '-'}")
    row("Claim / Service Date:", svc_date)
    row("Provider:", f"{provider}, {clinic}" if provider else clinic)
    row("Clinic Address:", clinic_addr)
    row("Diagnosis Treated:", diagnosis)
    row("CPT Code / Service:", cpt_desc)
    row("Invoice:", inv_no)
    row("Amount Billed:", f"${amount:.2f}" if amount is not None else "-")
    row("Payment Direction:", pay)
    if c.get("veteran_physical_address"):
        row("Veteran Physical Address:", c.get("veteran_physical_address"))
    if c.get("veteran_mailing_address"):
        row("Veteran Mailing Address:", c.get("veteran_mailing_address"))

    # ---- Checklist page ----
    pdf.add_page()
    pdf.set_font(FONT, "B", 14)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 8, "FMP Fully Developed Claim Checklist")
    pdf.ln(2)
    cats = set()
    for it in items:
        if it.get("source") == "invoice":
            cats.add("invoice")
        elif it.get("source") == "note":
            cats.add("progress_note")
        if it.get("category"):
            cats.add(it["category"])
    for cat, label in FMP_CHECKLIST:
        pdf.set_x(pdf.l_margin)
        y0 = pdf.get_y()
        pdf.set_font(FONT, "B", 11)
        pdf.multi_cell(12, 7, "[X]" if cat in cats else "[  ]")
        pdf.set_xy(pdf.l_margin + 12, y0)
        pdf.set_font(FONT, "", 10)
        pdf.multi_cell(0, 7, label)
    pdf.ln(3)
    pdf.set_font(FONT, "", 9)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5, "Suggested packet order for submission: 1) Claim summary & checklist; "
                         "2) FMP Claim Cover Sheet; 3) Invoice; 4) Clinical progress note; "
                         "5) VA disability verification; 6) FMP registration; 7) Provider credentials.")

    cover_bytes = pdf_bytes(pdf)

    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(cover_bytes)).pages:
        writer.add_page(page)
    for item in items:
        try:
            data, _ = get_object(item["storage_path"])
            fn = item["filename"].lower()
            if fn.endswith(".pdf"):
                for page in PdfReader(io.BytesIO(data)).pages:
                    writer.add_page(page)
            elif fn.rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp"):
                img = Image.open(io.BytesIO(data)).convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="PDF")
                for page in PdfReader(io.BytesIO(buf.getvalue())).pages:
                    writer.add_page(page)
        except Exception as e:
            logger.error(f"packet merge skip {item.get('filename')}: {e}")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@router.get("/claims")
async def list_claims(user: dict = Depends(require_roles("admin"))):
    packets = await db.claim_packets.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    await log_audit("view", "claim", actor=user, detail=f"list ({len(packets)})")
    return packets


@router.post("/claims")
async def create_claim(data: ClaimInput, user: dict = Depends(require_roles("admin"))):
    if data.status not in CLAIM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    doc = {"id": str(uuid.uuid4()), "name": data.name, "patient_id": data.patient_id,
           "patient_name": await _patient_name(data.patient_id), "claim_number": data.claim_number,
           "status": data.status, "notes": data.notes, "items": [],
           **{f: getattr(data, f) for f in _COVER_FIELDS},
           "created_at": now_iso(), "created_by": user["name"]}
    await db.claim_packets.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "claim", actor=user, resource_id=doc["id"], detail=data.name)
    return doc


class ClaimFromDateInput(BaseModel):
    patient_id: str
    date: str


def _same_day(val, date_str) -> bool:
    return bool(val) and str(val)[:10] == str(date_str)[:10]


@router.post("/claims/from-date")
async def claim_from_date(data: ClaimFromDateInput, user: dict = Depends(require_roles("admin"))):
    from core.folder_filing import note_pdf
    p = await db.patients.find_one({"id": data.patient_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    pname = f"{p['first_name']} {p['last_name']}"
    d = data.date[:10]

    invs = await db.invoices.find({"patient_id": data.patient_id}, {"_id": 0}).to_list(500)
    invs = [i for i in invs if _same_day(i.get("service_date"), d)]
    notes = await db.notes.find({"patient_id": data.patient_id}, {"_id": 0}).to_list(500)
    notes = [n for n in notes if _same_day(n.get("visit_date"), d)]

    if not invs and not notes:
        raise HTTPException(status_code=404, detail="No invoice or progress note found for that patient on that date")

    clinic = (await get_settings_doc()).get("clinic_name", "Veterans of Puerto Plata")
    m = d.split("-")
    disp = f"{m[1]}/{m[2]}/{m[0]}" if len(m) == 3 else d
    packet_name = f"{pname} {disp} FMP Claim"

    items = []
    for inv in invs:
        try:
            pdf = _invoice_pdf(inv, clinic)
        except Exception as e:
            logger.error(f"from-date invoice pdf failed: {e}")
            continue
        fname = f"Invoice_{inv.get('invoice_number', inv['id'][:8])}.pdf"
        path = f"{APP_NAME}/claims/from-date/{uuid.uuid4()}.pdf"
        try:
            result = put_object(path, pdf, "application/pdf")
        except Exception as e:
            logger.error(f"from-date invoice storage failed: {e}")
            continue
        items.append({"id": str(uuid.uuid4()), "source": "invoice", "form_id": None,
                      "invoice_id": inv["id"], "storage_path": result["path"], "filename": fname,
                      "content_type": "application/pdf", "size": result.get("size")})

    for n in notes:
        note = {**n, "patient_name": pname, "dob": p.get("dob"), "ssn": p.get("ssn")}
        try:
            pdf = note_pdf(note, clinic)
        except Exception as e:
            logger.error(f"from-date note pdf failed: {e}")
            continue
        fname = f"Progress_Note_{disp.replace('/', '-')}.pdf"
        path = f"{APP_NAME}/claims/from-date/{uuid.uuid4()}.pdf"
        try:
            result = put_object(path, pdf, "application/pdf")
        except Exception as e:
            logger.error(f"from-date note storage failed: {e}")
            continue
        items.append({"id": str(uuid.uuid4()), "source": "note", "form_id": None, "note_id": n["id"],
                      "storage_path": result["path"], "filename": fname,
                      "content_type": "application/pdf", "size": result.get("size")})

    doc = {"id": str(uuid.uuid4()), "name": packet_name, "patient_id": data.patient_id,
           "patient_name": pname, "claim_number": d, "status": "draft", "notes": None,
           "items": items, "created_at": now_iso(), "created_by": user["name"]}
    await db.claim_packets.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "claim", actor=user, resource_id=doc["id"],
                    detail=f"from-date {pname} {d} ({len(items)} items)")
    return doc


@router.get("/claims/{cid}")
async def get_claim(cid: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    return c


@router.put("/claims/{cid}")
async def update_claim(cid: str, data: ClaimInput, user: dict = Depends(require_roles("admin"))):
    if data.status not in CLAIM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    updates = {"name": data.name, "patient_id": data.patient_id,
               "patient_name": await _patient_name(data.patient_id), "claim_number": data.claim_number,
               "status": data.status, "notes": data.notes,
               **{f: getattr(data, f) for f in _COVER_FIELDS},
               "updated_at": now_iso()}
    res = await db.claim_packets.update_one({"id": cid}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=data.name)
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.delete("/claims/{cid}")
async def delete_claim(cid: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if c:
        for it in c.get("items", []):
            if it.get("source") in ("upload", "invoice", "note") and it.get("storage_path"):
                delete_object(it["storage_path"])
    await db.claim_packets.delete_one({"id": cid})
    await log_audit("delete", "claim", actor=user, resource_id=cid)
    return {"ok": True}


@router.post("/claims/{cid}/attach-form")
async def attach_form(cid: str, payload: dict, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    form = await db.forms.find_one({"id": payload.get("form_id")})
    if not form or not form.get("attachment"):
        raise HTTPException(status_code=400, detail="Form has no attached document")
    att = form["attachment"]
    item = {"id": str(uuid.uuid4()), "source": "form", "form_id": form["id"],
            "storage_path": att["storage_path"], "filename": att["filename"],
            "content_type": att.get("content_type", "application/octet-stream"), "size": att.get("size")}
    await db.claim_packets.update_one({"id": cid}, {"$push": {"items": item}, "$set": {"updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"attach form {att['filename']}")
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.post("/claims/{cid}/upload")
async def upload_to_claim(cid: str, file: UploadFile = File(...), user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    if ext not in UPLOAD_EXTS:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    safe_ct = EXT_CONTENT_TYPES.get(ext) or EXTRA_CT.get(ext, "application/octet-stream")
    payload = await file.read()
    if len(payload) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 15MB)")
    path = f"{APP_NAME}/claims/{cid}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, payload, safe_ct)
    except Exception as e:
        logger.error(f"claim upload failed: {e}")
        raise HTTPException(status_code=502, detail="File storage failed")
    item = {"id": str(uuid.uuid4()), "source": "upload", "form_id": None,
            "storage_path": result["path"], "filename": file.filename, "content_type": safe_ct,
            "size": result.get("size")}
    await db.claim_packets.update_one({"id": cid}, {"$push": {"items": item}, "$set": {"updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"upload {file.filename}")
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.get("/claims/options/forms")
async def attachable_forms(user: dict = Depends(require_roles("admin"))):
    forms = await db.forms.find({"attachment": {"$ne": None}}, {"_id": 0}).sort("created_at", -1).to_list(500)
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}" async for p in db.patients.find({}, {"_id": 0})}
    return [{"id": f["id"], "title": f.get("title"), "form_type": f.get("form_type"),
             "filename": f["attachment"].get("filename"),
             "patient_name": patients.get(f.get("patient_id"), "-")} for f in forms]


@router.get("/claims/options/invoices")
async def attachable_invoices(user: dict = Depends(require_roles("admin"))):
    invoices = await db.invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [{"id": i["id"], "invoice_number": i.get("invoice_number"),
             "patient_name": i.get("patient_name") or "-", "total": i.get("total", 0),
             "status": i.get("status"), "service_date": i.get("service_date")} for i in invoices]


@router.get("/claims/options/patients")
async def attachable_patients(user: dict = Depends(require_roles("admin"))):
    pts = await db.patients.find({}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).to_list(1000)
    return [{"id": p["id"], "name": f"{p['first_name']} {p['last_name']}"} for p in pts]


@router.post("/claims/{cid}/attach-invoice")
async def attach_invoice(cid: str, payload: dict, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    inv = await db.invoices.find_one({"id": payload.get("invoice_id")}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    clinic = (await get_settings_doc()).get("clinic_name", "Veterans of Puerto Plata")
    try:
        pdf_bytes = _invoice_pdf(inv, clinic)
    except Exception as e:
        logger.error(f"invoice pdf failed: {e}")
        raise HTTPException(status_code=500, detail="Could not render invoice PDF")
    fname = f"Invoice_{inv.get('invoice_number', inv['id'][:8])}.pdf"
    path = f"{APP_NAME}/claims/{cid}/{uuid.uuid4()}.pdf"
    try:
        result = put_object(path, pdf_bytes, "application/pdf")
    except Exception as e:
        logger.error(f"invoice storage failed: {e}")
        raise HTTPException(status_code=502, detail="File storage failed")
    item = {"id": str(uuid.uuid4()), "source": "invoice", "form_id": None, "invoice_id": inv["id"],
            "storage_path": result["path"], "filename": fname, "content_type": "application/pdf",
            "size": result.get("size")}
    await db.claim_packets.update_one({"id": cid}, {"$push": {"items": item}, "$set": {"updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"attach invoice {inv.get('invoice_number')}")
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.delete("/claims/{cid}/items/{item_id}")
async def remove_item(cid: str, item_id: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if c:
        it = next((i for i in c.get("items", []) if i["id"] == item_id), None)
        if it and it.get("source") in ("upload", "invoice", "note") and it.get("storage_path"):
            delete_object(it["storage_path"])
    await db.claim_packets.update_one({"id": cid}, {"$pull": {"items": {"id": item_id}}, "$set": {"updated_at": now_iso()}})
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.get("/claims/{cid}/items/{item_id}/download")
async def download_item(cid: str, item_id: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    item = next((i for i in c.get("items", []) if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    data, _ = get_object(item["storage_path"])
    fname = item["filename"].replace('"', "").replace("\n", "").replace("\r", "")
    return Response(content=data, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-Content-Type-Options": "nosniff"})


@router.get("/claims/{cid}/merged")
async def merged_pdf(cid: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    pdf = await _build_packet_pdf(c)
    await db.claim_packets.update_one({"id": cid}, {"$set": {"status": "complete", "updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail="merged PDF · marked complete")
    fname = (c.get("name") or "claim_packet").replace('"', "").replace(" ", "_")[:60]
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'})


class ItemRename(BaseModel):
    filename: Optional[str] = None
    category: Optional[str] = None


@router.put("/claims/{cid}/items/{item_id}")
async def rename_item(cid: str, item_id: str, data: ItemRename, user: dict = Depends(require_roles("admin"))):
    sets = {"updated_at": now_iso()}
    if data.filename is not None:
        name = data.filename.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name is required")
        sets["items.$.filename"] = name[:120]
    if data.category is not None:
        sets["items.$.category"] = data.category.strip()[:40]
    res = await db.claim_packets.update_one(
        {"id": cid, "items.id": item_id}, {"$set": sets})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    await log_audit("update", "claim", actor=user, resource_id=cid, detail="edit item")
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


class ItemOrder(BaseModel):
    ids: list


@router.put("/claims/{cid}/items-order")
async def reorder_items(cid: str, data: ItemOrder, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    items = c.get("items", [])
    by_id = {i["id"]: i for i in items}
    ordered = [by_id[i] for i in data.ids if i in by_id]
    ordered += [i for i in items if i["id"] not in set(data.ids)]
    await db.claim_packets.update_one({"id": cid}, {"$set": {"items": ordered, "updated_at": now_iso()}})
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.post("/claims/{cid}/items/{item_id}/to-folder")
async def item_to_folder(cid: str, item_id: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    pid = c.get("patient_id")
    if not pid:
        raise HTTPException(status_code=400, detail="Claim packet has no linked patient")
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    item = next((i for i in c.get("items", []) if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    try:
        data, _ = get_object(item["storage_path"])
    except Exception as e:
        logger.error(f"item to-folder read failed: {e}")
        raise HTTPException(status_code=502, detail="Could not read document")
    from core.folder_filing import _ensure_subfolder, fmt_date
    ds = fmt_date(c.get("claim_number")) if c.get("claim_number") else None
    from datetime import datetime, timezone
    ds = ds or datetime.now(timezone.utc).strftime("%m-%d-%Y")
    sub_name = f"{p['first_name']} {ds} FMP Claim"
    sid = await _ensure_subfolder(pid, sub_name, user)
    ext = item["filename"].rsplit(".", 1)[-1].lower() if "." in item["filename"] else "pdf"
    path = f"{APP_NAME}/folders/{pid}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, data, item.get("content_type", "application/pdf"))
    except Exception as e:
        logger.error(f"item to-folder store failed: {e}")
        raise HTTPException(status_code=502, detail="File storage failed")
    doc = {"id": str(uuid.uuid4()), "patient_id": pid, "subfolder_id": sid,
           "source": "upload", "form_id": None, "storage_path": result["path"],
           "filename": item["filename"][:120], "label": item["filename"][:120],
           "description": "Moved from FMP Claim", "content_type": item.get("content_type", "application/pdf"),
           "size": result.get("size"), "created_at": now_iso(),
           "created_by": user.get("name"), "created_by_id": user.get("id")}
    await db.folder_items.insert_one(doc)
    await log_audit("create", "folder", actor=user, resource_id=pid, detail=f"moved claim item to folder")
    return {"ok": True, "patient_name": f"{p['first_name']} {p['last_name']}", "subfolder": sub_name}


class SendPacket(BaseModel):
    to: str


@router.post("/claims/{cid}/send-email")
async def send_packet_email(cid: str, data: SendPacket, user: dict = Depends(require_roles("admin"))):
    from core.email_utils import send_email, email_configured
    to = (data.to or "").strip()
    if not to:
        raise HTTPException(status_code=400, detail="Recipient email is required")
    if not email_configured():
        raise HTTPException(status_code=400, detail="Email is not configured on the server")
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    pdf = await _build_packet_pdf(c)
    fname = (c.get("name") or "FMP_Claim").replace('"', "").replace(" ", "_")[:60] + ".pdf"
    ok = send_email(to, f"{c.get('name') or 'FMP Claim'}",
                    f"Attached is the merged claim packet: {c.get('name') or 'FMP Claim'}.",
                    attachments=[{"filename": fname, "content": pdf, "content_type": "application/pdf"}])
    if not ok:
        raise HTTPException(status_code=502, detail="Send failed — check the sender domain and recipient address")
    await db.claim_packets.update_one({"id": cid}, {"$set": {"status": "complete", "updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"emailed packet to {to} · marked complete")
    return {"ok": True, "to": to}


@router.post("/claims/{cid}/to-folder")
async def claim_to_folder(cid: str, user: dict = Depends(require_roles("admin"))):
    from datetime import datetime, timezone
    from core.folder_filing import file_pdf_into_folder
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    pid = c.get("patient_id")
    if not pid:
        raise HTTPException(status_code=400, detail="Claim packet has no linked patient")
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    pdf = await _build_packet_pdf(c)
    ds = datetime.now(timezone.utc).strftime("%m-%d-%Y")
    name = (c.get("name") or "Claim Packet")[:40]
    item = await file_pdf_into_folder(pid, p["first_name"], pdf,
                                      f"{name} {ds}", f"Claim_Packet_{ds}.pdf", user)
    if not item:
        raise HTTPException(status_code=502, detail="Could not file PDF")
    await log_audit("create", "folder", actor=user, resource_id=pid, detail=f"auto-filed claim {cid}")
    return {"ok": True, "patient_name": f"{p['first_name']} {p['last_name']}"}
