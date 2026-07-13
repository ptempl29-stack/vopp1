import uuid
import secrets

from fastapi import APIRouter, HTTPException, Depends

from core.db import db, now_iso
from core.config import ROLES, ALL_TABS, DEFAULT_TABS
from core.security import hash_password, create_access_token, require_roles, effective_tabs
from core.audit import log_audit
from routers.settings import get_settings_doc
from models.schemas import InviteInput, InviteAccept

router = APIRouter()


def _public(inv: dict) -> dict:
    return {"id": inv["id"], "email": inv["email"], "role": inv["role"],
            "allowed_tabs": inv.get("allowed_tabs", []), "status": inv["status"],
            "token": inv["token"], "created_at": inv.get("created_at"),
            "created_by": inv.get("created_by"), "accepted_at": inv.get("accepted_at")}


@router.get("/invites")
async def list_invites(user: dict = Depends(require_roles("admin"))):
    invs = await db.invites.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [_public(i) for i in invs]


@router.post("/invites")
async def create_invite(data: InviteInput, user: dict = Depends(require_roles("admin"))):
    if data.role not in ROLES or data.role == "admin":
        raise HTTPException(status_code=400, detail="Invalid role")
    email = data.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="A user with this email already exists")
    tabs = data.allowed_tabs if data.allowed_tabs is not None else DEFAULT_TABS.get(data.role, ["dashboard"])
    tabs = [tt for tt in tabs if tt in ALL_TABS]
    inv = {"id": str(uuid.uuid4()), "token": secrets.token_urlsafe(32), "email": email,
           "role": data.role, "allowed_tabs": tabs, "status": "pending",
           "created_at": now_iso(), "created_by": user["name"]}
    await db.invites.insert_one(inv)
    await log_audit("create", "invite", actor=user, resource_id=inv["id"], detail=email)
    return _public(inv)


@router.delete("/invites/{iid}")
async def delete_invite(iid: str, user: dict = Depends(require_roles("admin"))):
    await db.invites.delete_one({"id": iid})
    await log_audit("delete", "invite", actor=user, resource_id=iid)
    return {"ok": True}


# ---------------- Public (unauthenticated) ----------------
@router.get("/public/invites/{token}")
async def get_public_invite(token: str):
    inv = await db.invites.find_one({"token": token}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invite not found")
    if inv["status"] != "pending":
        raise HTTPException(status_code=400, detail="This invite has already been used")
    clinic = (await get_settings_doc()).get("clinic_name", "Veterans of Puerto Plata")
    return {"email": inv["email"], "role": inv["role"], "status": inv["status"], "clinic": clinic}


@router.post("/public/invites/{token}/accept")
async def accept_invite(token: str, data: InviteAccept):
    inv = await db.invites.find_one({"token": token})
    if not inv:
        raise HTTPException(status_code=404, detail="Invite not found")
    if inv["status"] != "pending":
        raise HTTPException(status_code=400, detail="This invite has already been used")
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if await db.users.find_one({"email": inv["email"]}):
        await db.invites.update_one({"id": inv["id"]}, {"$set": {"status": "accepted"}})
        raise HTTPException(status_code=400, detail="An account already exists for this email. Please sign in.")
    tabs = [tt for tt in inv.get("allowed_tabs", []) if tt in ALL_TABS] or DEFAULT_TABS.get(inv["role"], ["dashboard"])
    user_doc = {"id": str(uuid.uuid4()), "email": inv["email"],
                "password_hash": hash_password(data.password), "name": data.name.strip(),
                "role": inv["role"], "allowed_tabs": tabs, "created_at": now_iso()}
    await db.users.insert_one(user_doc)
    await db.invites.update_one({"id": inv["id"]},
        {"$set": {"status": "accepted", "accepted_at": now_iso(), "user_id": user_doc["id"]}})
    await log_audit("create", "user", actor=user_doc, resource_id=user_doc["id"], detail=f"invite accepted {inv['email']}")
    access = create_access_token(user_doc["id"], user_doc["email"], user_doc["role"])
    return {"token": access, "user": {"id": user_doc["id"], "email": user_doc["email"],
            "name": user_doc["name"], "role": user_doc["role"],
            "allowed_tabs": effective_tabs(user_doc), "default_signature": "", "doxy_room": ""}}
