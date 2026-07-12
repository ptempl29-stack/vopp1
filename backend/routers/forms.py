import uuid

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import Response

from core.db import db, now_iso, logger
from core.config import FORMS_ROLES, FORM_STATUSES, EXT_CONTENT_TYPES, APP_NAME, PUBLIC_BASE_URL
from core.security import get_current_user, require_roles
from core.storage import put_object, get_object
from core.email_utils import send_email
from models.schemas import FormInput, FormSubmission
from data.seed import FORM_TEMPLATES

router = APIRouter()


@router.get("/forms")
async def list_forms(user: dict = Depends(get_current_user)):
    forms = await db.forms.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}" async for p in db.patients.find({}, {"_id": 0})}
    for f in forms:
        f["patient_name"] = patients.get(f.get("patient_id"), "-")
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
    return doc


@router.get("/forms/{fid}/download")
async def download_form(fid: str, user: dict = Depends(require_roles(*FORMS_ROLES))):
    f = await db.forms.find_one({"id": fid})
    if not f or not f.get("attachment"):
        raise HTTPException(status_code=404, detail="Attachment not found")
    data, ctype = get_object(f["attachment"]["storage_path"])
    fname = f["attachment"]["filename"].replace('"', "").replace("\n", "").replace("\r", "")
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
