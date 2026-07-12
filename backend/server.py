from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import FastAPI, APIRouter, Request, HTTPException, Depends
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
ROLES = ["doctor", "nurse", "receptionist", "biller", "admin"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------- Auth helpers ----------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {"sub": user_id, "email": email, "role": role,
               "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "access"}
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
    status: str = "sent"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------- Auth routes ----------------
@api_router.post("/auth/login")
async def login(data: LoginInput):
    user = await db.users.find_one({"email": data.email.lower()})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"], user["role"])
    return {"token": token, "user": {"id": user["id"], "email": user["email"],
            "name": user["name"], "role": user["role"]}}

@api_router.post("/auth/register")
async def register(data: RegisterInput, current: dict = Depends(require_roles("admin"))):
    if data.role not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if await db.users.find_one({"email": data.email.lower()}):
        raise HTTPException(status_code=400, detail="Email already registered")
    user = {"id": str(uuid.uuid4()), "email": data.email.lower(),
            "password_hash": hash_password(data.password), "name": data.name,
            "role": data.role, "created_at": now_iso()}
    await db.users.insert_one(user)
    return {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]}

@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

@api_router.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(200)
    return users


# ---------------- Patients ----------------
@api_router.get("/patients")
async def list_patients(search: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {}
    if search:
        q = {"$or": [{"first_name": {"$regex": search, "$options": "i"}},
                     {"last_name": {"$regex": search, "$options": "i"}}]}
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
async def create_appointment(data: AppointmentInput, user: dict = Depends(require_roles("doctor", "nurse", "receptionist"))):
    doc = data.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso()})
    await db.appointments.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.put("/appointments/{aid}")
async def update_appointment(aid: str, data: AppointmentInput, user: dict = Depends(require_roles("doctor", "nurse", "receptionist"))):
    res = await db.appointments.update_one({"id": aid}, {"$set": data.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return await db.appointments.find_one({"id": aid}, {"_id": 0})

@api_router.delete("/appointments/{aid}")
async def delete_appointment(aid: str, user: dict = Depends(require_roles("doctor", "nurse", "receptionist"))):
    await db.appointments.delete_one({"id": aid})
    return {"ok": True}


# ---------------- Progress Notes + AI ----------------
@api_router.get("/notes")
async def list_notes(patient_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {"patient_id": patient_id} if patient_id else {}
    notes = await db.notes.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return notes

@api_router.post("/notes")
async def create_note(data: NoteInput, user: dict = Depends(require_roles("doctor", "nurse"))):
    doc = data.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso(), "author": user["name"]})
    await db.notes.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.post("/notes/summarize")
async def summarize_note(data: SummarizeInput, user: dict = Depends(require_roles("doctor", "nurse"))):
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
    return CPT_LIBRARY

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
    await db.messages.update_one({"id": mid}, {"$set": {"read": True}})
    return {"ok": True}


# ---------------- Forms ----------------
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
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso(), "created_by": user["name"]})
    await db.forms.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.put("/forms/{fid}/status")
async def update_form_status(fid: str, status: str, user: dict = Depends(get_current_user)):
    res = await db.forms.update_one({"id": fid}, {"$set": {"status": status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Form not found")
    return await db.forms.find_one({"id": fid}, {"_id": 0})


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
    {"email": "reception@vpp.com", "password": "reception123", "name": "Carlos Núñez", "role": "receptionist"},
    {"email": "biller@vpp.com", "password": "biller123", "name": "María Santos", "role": "biller"},
]


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.patients.create_index("id")
    # seed admin
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    if not await db.users.find_one({"email": admin_email}):
        await db.users.insert_one({"id": str(uuid.uuid4()), "email": admin_email,
            "password_hash": hash_password(os.environ["ADMIN_PASSWORD"]),
            "name": "Clinic Admin", "role": "admin", "created_at": now_iso()})
    # seed role users
    for u in DEMO_USERS:
        if not await db.users.find_one({"email": u["email"]}):
            await db.users.insert_one({"id": str(uuid.uuid4()), "email": u["email"],
                "password_hash": hash_password(u["password"]), "name": u["name"],
                "role": u["role"], "created_at": now_iso()})
    logger.info("Startup seeding complete")


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
