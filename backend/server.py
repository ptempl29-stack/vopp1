from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid

from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from core.db import db, now_iso, logger, client
from core.security import hash_password, verify_password
from core.storage import init_storage
from core.audit import set_client_ip
from data.seed import CPT_LIBRARY, DEMO_USERS

from routers import (auth, settings, patients, appointments, notes,
                     billing, messages, forms, dashboard, audit, telehealth, claims)

app = FastAPI()
api_router = APIRouter(prefix="/api")

for module in (auth, settings, patients, appointments, notes,
               billing, messages, forms, dashboard, audit, telehealth, claims):
    api_router.include_router(module.router)


@app.middleware("http")
async def capture_client_ip(request, call_next):
    xff = request.headers.get("x-forwarded-for", "")
    ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "")
    set_client_ip(ip)
    return await call_next(request)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.patients.create_index("id")
    await db.login_attempts.create_index("identifier", unique=True)
    await db.login_attempts.create_index("expires_at", expireAfterSeconds=0)
    await db.forms.create_index("public_token")
    await db.audit_logs.create_index("expires_at", expireAfterSeconds=0)
    await db.audit_logs.create_index([("created_at", -1)])
    await db.audit_logs.create_index("actor_id")
    if await db.cpt_codes.count_documents({}) == 0:
        await db.cpt_codes.insert_many([
            {"id": str(uuid.uuid4()), **c, "created_at": now_iso()} for c in CPT_LIBRARY])
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
