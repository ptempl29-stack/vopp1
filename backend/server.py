from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import re
import io
import csv
import uuid
import logging
import bcrypt
import jwt
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import FastAPI, APIRouter, Request, HTTPException, Depends, UploadFile, File, Form, Header, Query
from fastapi.responses import Response, StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr

from emergentintegrations.llm.chat import LlmChat, UserMessage

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

JWT_ALGORITHM = "HS256"
TOKEN_TTL_HOURS = int(os.environ.get("TOKEN_TTL_HOURS", "8"))
ROLES = ["doctor", "nurse", "psychologist", "receptionist", "biller", "admin"]
CLINICAL_ROLES = ("doctor", "nurse", "psychologist")
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
INVOICE_STATUSES = {"unpaid", "paid", "void"}
FORM_STATUSES = {"sent", "pending", "received"}

ALL_TABS = ["dashboard", "patients", "appointments", "telehealth", "notes",
            "invoices", "cpt", "reports", "forms", "messages", "team"]
DEFAULT_TABS = {
    "admin": ALL_TABS,
    "doctor": ["dashboard", "patients", "appointments", "telehealth", "notes", "forms", "messages"],
    "nurse": ["dashboard", "patients", "appointments", "telehealth", "notes", "forms", "messages"],
    "psychologist": ["dashboard", "appointments", "telehealth", "notes", "messages"],
    "receptionist": ["dashboard", "patients", "appointments", "invoices", "forms", "messages"],
    "biller": ["dashboard", "invoices", "cpt", "reports", "messages"],
}

# ---------------- Object storage ----------------
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = "vpp-clinic"
storage_key = None

def init_storage():
    global storage_key
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ["EMERGENT_LLM_KEY"]}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()

def get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

def effective_tabs(user: dict) -> List[str]:
    return user.get("allowed_tabs") or DEFAULT_TABS.get(user.get("role"), ["dashboard"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------- Auth helpers ----------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {"sub": user_id, "email": email, "role": role,
               "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS), "type": "access"}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request) -> dict:
    token = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def require_roles(*roles):
    async def checker(user: dict = Depends(get_current_user)):
        if roles and user["role"] not in roles and user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker


# ---------------- Models ----------------
class LoginInput(BaseModel):
    email: EmailStr
    password: str

class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "receptionist"
    allowed_tabs: Optional[List[str]] = None

class PatientInput(BaseModel):
    first_name: str
    last_name: str
    dob: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    status: str = "active"

class AppointmentInput(BaseModel):
    patient_id: str
    provider: Optional[str] = None
    date: str
    time: Optional[str] = None
    reason: Optional[str] = None
    status: str = "scheduled"

class NoteInput(BaseModel):
    patient_id: str
    title: str
    content: str
    summary: Optional[str] = None

class SummarizeInput(BaseModel):
    content: str

class InvoiceItem(BaseModel):
    cpt_code: str
    description: str
    amount: float
    quantity: int = 1

class CptInput(BaseModel):
    code: str
    description: str
    amount: float

class InvoiceInput(BaseModel):
    patient_id: str
    items: List[InvoiceItem]
    status: str = "unpaid"
    notes: Optional[str] = None

class MessageInput(BaseModel):
    to_user_id: str
    subject: Optional[str] = None
    body: str

class FormInput(BaseModel):
    patient_id: Optional[str] = None
    title: str
    form_type: str
    fields: Optional[dict] = None
    external_url: Optional[str] = None
    status: str = "sent"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------- Auth routes ----------------
@api_router.post("/auth/login")
async def login(data: LoginInput, request: Request):
    email = data.email.lower()
    xff = request.headers.get("x-forwarded-for", "")
    ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
    identifier = f"{ip}:{email}"
    now = datetime.now(timezone.utc)

    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if attempt and attempt.get("count", 0) >= MAX_LOGIN_ATTEMPTS:
        locked_until = attempt.get("locked_until")
        if locked_until and datetime.fromisoformat(locked_until) > now:
            raise HTTPException(status_code=429,
                detail="Too many failed attempts. Please try again later.")

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        new_count = (attempt.get("count", 0) if attempt else 0) + 1
        update = {"count": new_count, "updated_at": now.isoformat(),
                  "expires_at": now + timedelta(minutes=LOCKOUT_MINUTES)}
        if new_count >= MAX_LOGIN_ATTEMPTS:
            update["locked_until"] = (now + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
        await db.login_attempts.update_one({"identifier": identifier}, {"$set": update}, upsert=True)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await db.login_attempts.delete_one({"identifier": identifier})
    token = create_access_token(user["id"], user["email"], user["role"])
    return {"token": token, "user": {"id": user["id"], "email": user["email"],
            "name": user["name"], "role": user["role"], "allowed_tabs": effective_tabs(user)}}

@api_router.post("/auth/register")
async def register(data: RegisterInput, current: dict = Depends(require_roles("admin"))):
    if data.role not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if await db.users.find_one({"email": data.email.lower()}):
        raise HTTPException(status_code=400, detail="Email already registered")
    tabs = data.allowed_tabs if data.allowed_tabs is not None else DEFAULT_TABS.get(data.role, ["dashboard"])
    tabs = [tt for tt in tabs if tt in ALL_TABS]
    user = {"id": str(uuid.uuid4()), "email": data.email.lower(),
            "password_hash": hash_password(data.password), "name": data.name,
            "role": data.role, "allowed_tabs": tabs, "created_at": now_iso()}
    await db.users.insert_one(user)
    return {"id": user["id"], "email": user["email"], "name": user["name"],
            "role": user["role"], "allowed_tabs": tabs}

@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    user["allowed_tabs"] = effective_tabs(user)
    return user

@api_router.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(200)
    for u in users:
        u["allowed_tabs"] = effective_tabs(u)
    return users

@api_router.put("/users/{uid}/tabs")
async def update_user_tabs(uid: str, payload: dict, current: dict = Depends(require_roles("admin"))):
    tabs = [tt for tt in payload.get("allowed_tabs", []) if tt in ALL_TABS]
    res = await db.users.update_one({"id": uid}, {"$set": {"allowed_tabs": tabs}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    u = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})
    return u

@api_router.delete("/users/{uid}")
async def delete_user(uid: str, current: dict = Depends(require_roles("admin"))):
    if uid == current["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    await db.users.delete_one({"id": uid})
    return {"ok": True}

@api_router.get("/meta/tabs")
async def meta_tabs(current: dict = Depends(require_roles("admin"))):
    return {"tabs": ALL_TABS, "roles": ROLES, "defaults": DEFAULT_TABS}


# ---------------- Patients ----------------
@api_router.get("/patients")
async def list_patients(search: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {}
    if search:
        safe = re.escape(search.strip()[:80])
        q = {"$or": [{"first_name": {"$regex": safe, "$options": "i"}},
                     {"last_name": {"$regex": safe, "$options": "i"}}]}
    patients = await db.patients.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return patients

@api_router.post("/patients")
async def create_patient(data: PatientInput, user: dict = Depends(require_roles("doctor", "nurse", "receptionist"))):
    doc = data.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso(),
                "created_by": user["name"]})
    await db.patients.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.get("/patients/{pid}")
async def get_patient(pid: str, user: dict = Depends(get_current_user)):
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return p

@api_router.put("/patients/{pid}")
async def update_patient(pid: str, data: PatientInput, user: dict = Depends(require_roles("doctor", "nurse", "receptionist"))):
    res = await db.patients.update_one({"id": pid}, {"$set": data.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Patient not found")
    return await db.patients.find_one({"id": pid}, {"_id": 0})

@api_router.delete("/patients/{pid}")
async def delete_patient(pid: str, user: dict = Depends(require_roles("doctor", "receptionist"))):
    await db.patients.delete_one({"id": pid})
    return {"ok": True}


# ---------------- Appointments ----------------
@api_router.get("/appointments")
async def list_appointments(user: dict = Depends(get_current_user)):
    appts = await db.appointments.find({}, {"_id": 0}).sort("date", 1).to_list(500)
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}" async for p in db.patients.find({}, {"_id": 0})}
    for a in appts:
        a["patient_name"] = patients.get(a["patient_id"], "Unknown")
    return appts

@api_router.post("/appointments")
async def create_appointment(data: AppointmentInput, user: dict = Depends(require_roles("doctor", "nurse", "receptionist", "psychologist"))):
    doc = data.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso()})
    await db.appointments.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.put("/appointments/{aid}")
async def update_appointment(aid: str, data: AppointmentInput, user: dict = Depends(require_roles("doctor", "nurse", "receptionist", "psychologist"))):
    res = await db.appointments.update_one({"id": aid}, {"$set": data.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return await db.appointments.find_one({"id": aid}, {"_id": 0})

@api_router.delete("/appointments/{aid}")
async def delete_appointment(aid: str, user: dict = Depends(require_roles("doctor", "nurse", "receptionist", "psychologist"))):
    await db.appointments.delete_one({"id": aid})
    return {"ok": True}


# ---------------- Progress Notes + AI ----------------
@api_router.get("/notes")
async def list_notes(patient_id: Optional[str] = None, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    q = {"patient_id": patient_id} if patient_id else {}
    notes = await db.notes.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return notes

@api_router.post("/notes")
async def create_note(data: NoteInput, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    doc = data.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso(), "author": user["name"]})
    await db.notes.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.post("/notes/summarize")
async def summarize_note(data: SummarizeInput, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="No content to summarize")
    try:
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"note-{uuid.uuid4()}",
            system_message=("You are a clinical documentation assistant. Summarize the "
                            "progress note into a concise, professional clinical summary with "
                            "Assessment and Plan when possible. Keep it under 120 words. "
                            "Do not invent facts."),
        ).with_model("openai", "gpt-5.4")
        resp = await chat.send_message(UserMessage(text=data.content))
        return {"summary": resp}
    except Exception as e:
        logger.exception("summarize failed")
        raise HTTPException(status_code=500, detail=f"AI summarization failed: {str(e)}")


# ---------------- Invoices / CPT ----------------
@api_router.get("/cpt-codes")
async def cpt_codes(user: dict = Depends(get_current_user)):
    return await db.cpt_codes.find({}, {"_id": 0}).sort("code", 1).to_list(1000)

@api_router.post("/cpt-codes")
async def create_cpt(data: CptInput, user: dict = Depends(require_roles("biller"))):
    if await db.cpt_codes.find_one({"code": data.code}):
        raise HTTPException(status_code=400, detail="CPT code already exists")
    doc = {"id": str(uuid.uuid4()), **data.model_dump(), "created_at": now_iso()}
    await db.cpt_codes.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.put("/cpt-codes/{cid}")
async def update_cpt(cid: str, data: CptInput, user: dict = Depends(require_roles("biller"))):
    res = await db.cpt_codes.update_one({"id": cid}, {"$set": data.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="CPT code not found")
    return await db.cpt_codes.find_one({"id": cid}, {"_id": 0})

@api_router.delete("/cpt-codes/{cid}")
async def delete_cpt(cid: str, user: dict = Depends(require_roles("biller"))):
    await db.cpt_codes.delete_one({"id": cid})
    return {"ok": True}

@api_router.get("/invoices")
async def list_invoices(user: dict = Depends(get_current_user)):
    invoices = await db.invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}" async for p in db.patients.find({}, {"_id": 0})}
    for inv in invoices:
        inv["patient_name"] = patients.get(inv["patient_id"], "Unknown")
    return invoices

@api_router.post("/invoices")
async def create_invoice(data: InvoiceInput, user: dict = Depends(require_roles("biller", "receptionist"))):
    items = [i.model_dump() for i in data.items]
    total = sum(i["amount"] * i["quantity"] for i in items)
    doc = {"id": str(uuid.uuid4()), "patient_id": data.patient_id, "items": items,
           "total": round(total, 2), "status": data.status, "notes": data.notes,
           "created_at": now_iso(), "created_by": user["name"]}
    await db.invoices.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.put("/invoices/{iid}/status")
async def update_invoice_status(iid: str, status: str, user: dict = Depends(require_roles("biller", "receptionist"))):
    if status not in INVOICE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    res = await db.invoices.update_one({"id": iid}, {"$set": {"status": status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return await db.invoices.find_one({"id": iid}, {"_id": 0})


# ---------------- Messages ----------------
@api_router.get("/messages")
async def list_messages(user: dict = Depends(get_current_user)):
    msgs = await db.messages.find(
        {"$or": [{"to_user_id": user["id"]}, {"from_user_id": user["id"]}]},
        {"_id": 0}).sort("created_at", -1).to_list(500)
    return msgs

@api_router.post("/messages")
async def send_message(data: MessageInput, user: dict = Depends(get_current_user)):
    to = await db.users.find_one({"id": data.to_user_id}, {"_id": 0})
    doc = {"id": str(uuid.uuid4()), "from_user_id": user["id"], "from_name": user["name"],
           "to_user_id": data.to_user_id, "to_name": to["name"] if to else "Unknown",
           "subject": data.subject, "body": data.body, "read": False, "created_at": now_iso()}
    await db.messages.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.put("/messages/{mid}/read")
async def mark_read(mid: str, user: dict = Depends(get_current_user)):
    res = await db.messages.update_one({"id": mid, "to_user_id": user["id"]}, {"$set": {"read": True}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True}


# ---------------- Forms ----------------
FORM_TEMPLATES = {
    "Intake": [
        {"name": "full_name", "en": "Full Name", "es": "Nombre Completo", "type": "text", "required": True},
        {"name": "dob", "en": "Date of Birth", "es": "Fecha de Nacimiento", "type": "date", "required": True},
        {"name": "phone", "en": "Phone", "es": "Teléfono", "type": "text", "required": False},
        {"name": "reason", "en": "Reason for Visit", "es": "Motivo de la Visita", "type": "textarea", "required": True},
        {"name": "medications", "en": "Current Medications", "es": "Medicamentos Actuales", "type": "textarea", "required": False},
        {"name": "allergies", "en": "Allergies", "es": "Alergias", "type": "text", "required": False},
    ],
    "Consent": [
        {"name": "patient_name", "en": "Patient Name", "es": "Nombre del Paciente", "type": "text", "required": True},
        {"name": "consent", "en": "I consent to treatment", "es": "Consiento al tratamiento", "type": "checkbox", "required": True},
        {"name": "signature", "en": "Signature (type full name)", "es": "Firma (escriba su nombre)", "type": "text", "required": True},
        {"name": "date", "en": "Date", "es": "Fecha", "type": "date", "required": True},
    ],
    "Medical History": [
        {"name": "conditions", "en": "Chronic Conditions", "es": "Condiciones Crónicas", "type": "textarea", "required": False},
        {"name": "surgeries", "en": "Past Surgeries", "es": "Cirugías Previas", "type": "textarea", "required": False},
        {"name": "family_history", "en": "Family History", "es": "Historia Familiar", "type": "textarea", "required": False},
        {"name": "smoking", "en": "Do you smoke?", "es": "¿Fuma?", "type": "select", "required": True,
         "options": [{"value": "no", "en": "No", "es": "No"}, {"value": "yes", "en": "Yes", "es": "Sí"}, {"value": "former", "en": "Former", "es": "Ex-fumador"}]},
    ],
    "Insurance": [
        {"name": "provider", "en": "Insurance Provider", "es": "Aseguradora", "type": "text", "required": True},
        {"name": "policy_number", "en": "Policy Number", "es": "Número de Póliza", "type": "text", "required": True},
        {"name": "group_number", "en": "Group Number", "es": "Número de Grupo", "type": "text", "required": False},
        {"name": "subscriber", "en": "Subscriber Name", "es": "Nombre del Titular", "type": "text", "required": True},
    ],
    "Referral": [
        {"name": "referring_provider", "en": "Referring Provider", "es": "Médico que Refiere", "type": "text", "required": True},
        {"name": "specialty", "en": "Specialty", "es": "Especialidad", "type": "text", "required": True},
        {"name": "reason", "en": "Reason for Referral", "es": "Motivo de la Referencia", "type": "textarea", "required": True},
    ],
}

@api_router.get("/forms")
async def list_forms(user: dict = Depends(get_current_user)):
    forms = await db.forms.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}" async for p in db.patients.find({}, {"_id": 0})}
    for f in forms:
        f["patient_name"] = patients.get(f.get("patient_id"), "-")
    return forms

@api_router.post("/forms")
async def create_form(data: FormInput, user: dict = Depends(get_current_user)):
    doc = data.model_dump()
    doc.update({"id": str(uuid.uuid4()), "public_token": uuid.uuid4().hex,
                "template": FORM_TEMPLATES.get(data.form_type, []), "responses": None,
                "attachment": None, "created_at": now_iso(), "created_by": user["name"]})
    await db.forms.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.post("/forms/upload")
async def upload_form(file: UploadFile = File(...), title: str = Form(...),
                      form_type: str = Form("Uploaded"), patient_id: str = Form(""),
                      user: dict = Depends(get_current_user)):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    if ext not in {"pdf", "png", "jpg", "jpeg", "webp", "doc", "docx", "txt"}:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    path = f"{APP_NAME}/forms/{user['id']}/{uuid.uuid4()}.{ext}"
    payload = await file.read()
    if len(payload) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 15MB)")
    try:
        result = put_object(path, payload, file.content_type or "application/octet-stream")
    except Exception as e:
        logger.exception("upload failed")
        raise HTTPException(status_code=502, detail="File storage failed")
    doc = {"id": str(uuid.uuid4()), "public_token": uuid.uuid4().hex,
           "title": title, "form_type": form_type, "patient_id": patient_id or None,
           "template": [], "responses": None, "status": "received",
           "attachment": {"storage_path": result["path"], "filename": file.filename,
                          "content_type": file.content_type, "size": result.get("size")},
           "created_at": now_iso(), "created_by": user["name"]}
    await db.forms.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.get("/forms/{fid}/download")
async def download_form(fid: str, auth: str = Query(None), authorization: str = Header(None)):
    token = None
    hdr = authorization or (f"Bearer {auth}" if auth else "")
    if hdr.startswith("Bearer "):
        token = hdr[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    f = await db.forms.find_one({"id": fid})
    if not f or not f.get("attachment"):
        raise HTTPException(status_code=404, detail="Attachment not found")
    data, ctype = get_object(f["attachment"]["storage_path"])
    return Response(content=data, media_type=f["attachment"].get("content_type") or ctype,
        headers={"Content-Disposition": f'inline; filename="{f["attachment"]["filename"]}"'})

@api_router.put("/forms/{fid}/status")
async def update_form_status(fid: str, status: str, user: dict = Depends(get_current_user)):
    if status not in FORM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    res = await db.forms.update_one({"id": fid}, {"$set": {"status": status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Form not found")
    return await db.forms.find_one({"id": fid}, {"_id": 0})


# ---------------- Public (unauthenticated) patient form ----------------
class FormSubmission(BaseModel):
    responses: dict

@api_router.get("/public/forms/{token}")
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

@api_router.post("/public/forms/{token}/submit")
async def public_submit_form(token: str, data: FormSubmission):
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


# ---------------- Dashboard stats ----------------
@api_router.get("/stats")
async def stats(user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).date().isoformat()
    return {
        "patients": await db.patients.count_documents({}),
        "appointments_today": await db.appointments.count_documents({"date": today}),
        "appointments_total": await db.appointments.count_documents({}),
        "pending_notes": await db.notes.count_documents({"summary": {"$in": [None, ""]}}),
        "unpaid_invoices": await db.invoices.count_documents({"status": "unpaid"}),
        "pending_forms": await db.forms.count_documents({"status": {"$in": ["sent", "pending"]}}),
        "unread_messages": await db.messages.count_documents({"to_user_id": user["id"], "read": False}),
    }


# ---------------- Billing Reports ----------------
def _inv_date(inv):
    return (inv.get("created_at") or "")[:10]

@api_router.get("/reports/billing")
async def billing_report(start: Optional[str] = None, end: Optional[str] = None,
                         user: dict = Depends(require_roles("biller", "admin"))):
    invoices = await db.invoices.find({}, {"_id": 0}).to_list(2000)
    if start:
        invoices = [i for i in invoices if _inv_date(i) >= start]
    if end:
        invoices = [i for i in invoices if _inv_date(i) <= end]

    total_billed = sum(i.get("total", 0) for i in invoices)
    collected = sum(i.get("total", 0) for i in invoices if i.get("status") == "paid")
    outstanding = sum(i.get("total", 0) for i in invoices if i.get("status") == "unpaid")

    # revenue over time (by day, collected)
    by_day = {}
    for i in invoices:
        d = _inv_date(i)
        by_day.setdefault(d, {"date": d, "billed": 0.0, "collected": 0.0})
        by_day[d]["billed"] += i.get("total", 0)
        if i.get("status") == "paid":
            by_day[d]["collected"] += i.get("total", 0)
    timeseries = sorted(by_day.values(), key=lambda x: x["date"])

    # breakdown by CPT code
    by_cpt = {}
    for i in invoices:
        for it in i.get("items", []):
            c = it.get("cpt_code", "?")
            by_cpt.setdefault(c, {"cpt_code": c, "description": it.get("description", ""),
                                  "count": 0, "revenue": 0.0})
            by_cpt[c]["count"] += it.get("quantity", 1)
            by_cpt[c]["revenue"] += it.get("amount", 0) * it.get("quantity", 1)
    cpt_breakdown = sorted(by_cpt.values(), key=lambda x: x["revenue"], reverse=True)

    return {
        "summary": {
            "total_billed": round(total_billed, 2),
            "collected": round(collected, 2),
            "outstanding": round(outstanding, 2),
            "invoice_count": len(invoices),
            "paid_count": len([i for i in invoices if i.get("status") == "paid"]),
        },
        "timeseries": [{"date": t["date"], "billed": round(t["billed"], 2),
                        "collected": round(t["collected"], 2)} for t in timeseries],
        "cpt_breakdown": [{**c, "revenue": round(c["revenue"], 2)} for c in cpt_breakdown],
    }

@api_router.get("/reports/billing/export")
async def billing_export(start: Optional[str] = None, end: Optional[str] = None,
                         auth: str = Query(None), authorization: str = Header(None)):
    token = None
    hdr = authorization or (f"Bearer {auth}" if auth else "")
    if hdr.startswith("Bearer "):
        token = hdr[7:]
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if payload.get("role") not in ("biller", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    invoices = await db.invoices.find({}, {"_id": 0}).to_list(2000)
    if start:
        invoices = [i for i in invoices if _inv_date(i) >= start]
    if end:
        invoices = [i for i in invoices if _inv_date(i) <= end]
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}" async for p in db.patients.find({}, {"_id": 0})}

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Invoice ID", "Date", "Patient", "CPT Codes", "Status", "Total"])
    for i in invoices:
        codes = "; ".join(it.get("cpt_code", "") for it in i.get("items", []))
        w.writerow([i.get("id"), _inv_date(i), patients.get(i.get("patient_id"), "Unknown"),
                    codes, i.get("status"), f'{i.get("total", 0):.2f}'])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=billing_report.csv"})


CPT_LIBRARY = [
    {"code": "99202", "description": "New patient office visit, 15-29 min", "amount": 75.00},
    {"code": "99203", "description": "New patient office visit, 30-44 min", "amount": 110.00},
    {"code": "99213", "description": "Established patient visit, 20-29 min", "amount": 90.00},
    {"code": "99214", "description": "Established patient visit, 30-39 min", "amount": 130.00},
    {"code": "99396", "description": "Preventive visit, 40-64 yrs", "amount": 160.00},
    {"code": "90686", "description": "Influenza vaccine", "amount": 35.00},
    {"code": "80053", "description": "Comprehensive metabolic panel", "amount": 55.00},
    {"code": "85025", "description": "Complete blood count (CBC)", "amount": 40.00},
    {"code": "93000", "description": "Electrocardiogram (ECG)", "amount": 65.00},
    {"code": "36415", "description": "Routine venipuncture", "amount": 20.00},
]

DEMO_USERS = [
    {"email": "doctor@vpp.com", "password": "doctor123", "name": "Dr. Elena Marte", "role": "doctor"},
    {"email": "nurse@vpp.com", "password": "nurse123", "name": "Rosa Fernández", "role": "nurse"},
    {"email": "psych@vpp.com", "password": "psych123", "name": "Dr. Luis Herrera", "role": "psychologist"},
    {"email": "reception@vpp.com", "password": "reception123", "name": "Carlos Núñez", "role": "receptionist"},
    {"email": "biller@vpp.com", "password": "biller123", "name": "María Santos", "role": "biller"},
]


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.patients.create_index("id")
    await db.login_attempts.create_index("identifier", unique=True)
    await db.login_attempts.create_index("expires_at", expireAfterSeconds=0)
    await db.forms.create_index("public_token")
    # seed CPT codes if collection empty
    if await db.cpt_codes.count_documents({}) == 0:
        await db.cpt_codes.insert_many([
            {"id": str(uuid.uuid4()), **c, "created_at": now_iso()} for c in CPT_LIBRARY])
    # seed/rotate admin (idempotent)
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_pw = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({"id": str(uuid.uuid4()), "email": admin_email,
            "password_hash": hash_password(admin_pw),
            "name": "Clinic Admin", "role": "admin", "created_at": now_iso()})
    elif not verify_password(admin_pw, existing["password_hash"]):
        await db.users.update_one({"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_pw)}})
    # seed demo staff ONLY when explicitly enabled (never in production)
    if os.environ.get("SEED_DEMO_USERS", "false").lower() == "true":
        for u in DEMO_USERS:
            if not await db.users.find_one({"email": u["email"]}):
                await db.users.insert_one({"id": str(uuid.uuid4()), "email": u["email"],
                    "password_hash": hash_password(u["password"]), "name": u["name"],
                    "role": u["role"], "created_at": now_iso()})
        logger.info("Demo users seeded (SEED_DEMO_USERS=true)")
    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    logger.info("Startup complete")


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
