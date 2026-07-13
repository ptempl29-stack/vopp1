import uuid
import io

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import Response, StreamingResponse

from core.db import db, now_iso, logger
from core.config import FORMS_ROLES, FORM_STATUSES, EXT_CONTENT_TYPES, APP_NAME, PUBLIC_BASE_URL
from core.security import require_roles
from core.audit import log_audit
from core.storage import put_object, get_object
from core.email_utils import send_email
from models.schemas import FormInput, FormSubmission
from data.seed import FORM_TEMPLATES

router = APIRouter()

_TEMPLATE_META = {
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "blank_form.docx"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "blank_spreadsheet.xlsx"),
    "pdf": ("application/pdf", "blank_form.pdf"),
}


def _build_docx(clinic: str) -> bytes:
    from docx import Document
    doc = Document()
    doc.add_heading(clinic, level=0)
    doc.add_heading("Patient Form", level=1)
    for label in ["Patient Name:", "Date of Birth:", "Date:", "Notes:"]:
        doc.add_paragraph(label)
    for _ in range(12):
        doc.add_paragraph("")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _build_xlsx(clinic: str) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Form"
    ws["A1"] = clinic
    ws["A2"] = "Patient Form"
    ws.append([])
    ws.append(["Field", "Value"])
    for label in ["Patient Name", "Date of Birth", "Date", "Notes"]:
        ws.append([label, ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_pdf(clinic: str) -> bytes:
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, clinic, ln=True)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Patient Form", ln=True)
    pdf.ln(4)
    pdf.set_font("Helvetica", size=12)
    for label in ["Patient Name: ______________________________", "Date of Birth: _____________________________",
                  "Date: ______________________________________", "Notes:"]:
        pdf.cell(0, 10, label, ln=True)
    for _ in range(10):
        pdf.cell(0, 10, "_" * 70, ln=True)
    out = pdf.output(dest="S")
    return bytes(out) if isinstance(out, (bytes, bytearray)) else out.encode("latin-1")


@router.get("/forms/blank-template/{kind}")
async def blank_template(kind: str, user: dict = Depends(require_roles(*FORMS_ROLES))):
    if kind not in _TEMPLATE_META:
        raise HTTPException(status_code=400, detail="Unsupported template type")
    s = await db.settings.find_one({"key": "clinic"}, {"_id": 0})
    clinic = (s or {}).get("clinic_name", "Veterans of Puerto Plata")
    builders = {"docx": _build_docx, "xlsx": _build_xlsx, "pdf": _build_pdf}
    data = builders[kind](clinic)
    ctype, fname = _TEMPLATE_META[kind]
    return StreamingResponse(io.BytesIO(data), media_type=ctype,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/forms")
async def list_forms(user: dict = Depends(require_roles("doctor", "nurse", "receptionist"))):
    forms = await db.forms.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}" async for p in db.patients.find({}, {"_id": 0})}
    for f in forms:
        f["patient_name"] = patients.get(f.get("patient_id"), "-")
    await log_audit("view", "form", actor=user, detail=f"list ({len(forms)})")
    return forms


@router.post("/forms")
async def create_form(data: FormInput, user: dict = Depends(require_roles(*FORMS_ROLES))):
    doc = {"id": str(uuid.uuid4()), "public_token": uuid.uuid4().hex,
           "patient_id": data.patient_id, "title": data.title, "form_type": data.form_type,
           "fields": data.fields, "external_url": data.external_url, "status": data.status,
           "template": FORM_TEMPLATES.get(data.form_type, []), "responses": None,
           "attachment": None, "email_sent": False,
           "created_at": now_iso(), "created_by": user["name"]}
    recipient = data.recipient_email
    if not recipient and data.patient_id:
        p = await db.patients.find_one({"id": data.patient_id}, {"_id": 0})
        if p and p.get("email"):
            recipient = p["email"]
    if recipient:
        link = f"{PUBLIC_BASE_URL.rstrip('/')}/form/{doc['public_token']}"
        sent = send_email(recipient,
            f"Please complete your form: {data.title}",
            f"Hello,\n\nPlease complete the following form for Veterans of Puerto Plata:\n{data.title}\n\n{link}\n\nThank you.")
        doc["email_sent"] = sent
        doc["recipient_email"] = recipient
    await db.forms.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "form", actor=user, resource_id=doc["id"],
                    detail=f"{data.form_type}: {data.title}")
    return doc


@router.post("/forms/upload")
async def upload_form(file: UploadFile = File(...), title: str = Form(...),
                      form_type: str = Form("Uploaded"), patient_id: str = Form(""),
                      user: dict = Depends(require_roles(*FORMS_ROLES))):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    if ext not in EXT_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    safe_ct = EXT_CONTENT_TYPES[ext]
    path = f"{APP_NAME}/forms/{user['id']}/{uuid.uuid4()}.{ext}"
    payload = await file.read()
    if len(payload) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 15MB)")
    try:
        result = put_object(path, payload, safe_ct)
    except Exception as e:
        logger.error(f"upload failed: {e}")
        raise HTTPException(status_code=502, detail="File storage failed")
    doc = {"id": str(uuid.uuid4()), "public_token": uuid.uuid4().hex,
           "title": title, "form_type": form_type, "patient_id": patient_id or None,
           "template": [], "responses": None, "status": "received",
           "attachment": {"storage_path": result["path"], "filename": file.filename,
                          "content_type": safe_ct, "size": result.get("size")},
           "created_at": now_iso(), "created_by": user["name"]}
    await db.forms.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "form", actor=user, resource_id=doc["id"],
                    detail=f"upload: {file.filename}")
    return doc


@router.get("/forms/{fid}/download")
async def download_form(fid: str, user: dict = Depends(require_roles(*FORMS_ROLES))):
    f = await db.forms.find_one({"id": fid})
    if not f or not f.get("attachment"):
        raise HTTPException(status_code=404, detail="Attachment not found")
    data, ctype = get_object(f["attachment"]["storage_path"])
    fname = f["attachment"]["filename"].replace('"', "").replace("\n", "").replace("\r", "")
    await log_audit("view", "form", actor=user, resource_id=fid, detail=f"download: {fname}")
    return Response(content=data, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"',
                 "X-Content-Type-Options": "nosniff"})


@router.put("/forms/{fid}/status")
async def update_form_status(fid: str, status: str, user: dict = Depends(require_roles(*FORMS_ROLES))):
    if status not in FORM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    res = await db.forms.update_one({"id": fid}, {"$set": {"status": status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Form not found")
    await log_audit("update", "form", actor=user, resource_id=fid, detail=f"status={status}")
    return await db.forms.find_one({"id": fid}, {"_id": 0})


# ---------------- Public (unauthenticated) patient form ----------------
@router.get("/public/forms/{token}")
async def public_get_form(token: str):
    f = await db.forms.find_one({"public_token": token}, {"_id": 0, "created_by": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Form not found")
    patient = None
    if f.get("patient_id"):
        p = await db.patients.find_one({"id": f["patient_id"]}, {"_id": 0, "first_name": 1})
        patient = p["first_name"] if p else None
    return {"id": f["id"], "title": f["title"], "form_type": f["form_type"],
            "template": f.get("template", []), "status": f["status"],
            "has_template": bool(f.get("template")), "has_attachment": bool(f.get("attachment")),
            "patient_first_name": patient, "clinic": "Veterans of Puerto Plata"}


@router.post("/public/forms/{token}/submit")
async def public_submit_form(token: str, data: FormSubmission):
    import json as _json
    if len(_json.dumps(data.responses)) > 1_200_000:
        raise HTTPException(status_code=400, detail="Submission too large")
    f = await db.forms.find_one({"public_token": token})
    if not f:
        raise HTTPException(status_code=404, detail="Form not found")
    if f.get("status") == "received":
        raise HTTPException(status_code=400, detail="This form has already been submitted")
    missing = [fld["name"] for fld in f.get("template", [])
               if fld.get("required") and not data.responses.get(fld["name"])]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")
    await db.forms.update_one({"public_token": token},
        {"$set": {"responses": data.responses, "status": "received", "submitted_at": now_iso()}})
    return {"ok": True}


@router.post("/public/forms/{token}/upload")
async def public_upload_back(token: str, file: UploadFile = File(...)):
    f = await db.forms.find_one({"public_token": token})
    if not f:
        raise HTTPException(status_code=404, detail="Form not found")
    if f.get("status") == "received":
        raise HTTPException(status_code=400, detail="This form has already been submitted")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    allowed = {"pdf", "png", "jpg", "jpeg", "webp", "doc", "docx", "txt", "xls", "xlsx"}
    if ext not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    ct_map = {"xls": "application/vnd.ms-excel",
              "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    safe_ct = EXT_CONTENT_TYPES.get(ext) or ct_map.get(ext, "application/octet-stream")
    payload = await file.read()
    if len(payload) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 15MB)")
    path = f"{APP_NAME}/forms/patient-uploads/{token}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, payload, safe_ct)
    except Exception as e:
        logger.error(f"patient upload failed: {e}")
        raise HTTPException(status_code=502, detail="File storage failed")
    await db.forms.update_one({"public_token": token}, {"$set": {
        "attachment": {"storage_path": result["path"], "filename": file.filename,
                       "content_type": safe_ct, "size": result.get("size")},
        "status": "received", "submitted_at": now_iso()}})
    return {"ok": True}
