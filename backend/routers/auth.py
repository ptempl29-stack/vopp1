import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends
from datetime import timedelta

from core.db import db, now_iso
from core.config import ROLES, ALL_TABS, DEFAULT_TABS, MAX_LOGIN_ATTEMPTS, LOCKOUT_MINUTES
from core.security import (hash_password, verify_password, create_access_token,
                           get_current_user, require_roles, effective_tabs)
from core.audit import log_audit
from models.schemas import LoginInput, RegisterInput, UpdateUserInput

router = APIRouter()


@router.post("/auth/login")
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
        await log_audit("login_failed", "auth", detail=email)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await db.login_attempts.delete_one({"identifier": identifier})
    token = create_access_token(user["id"], user["email"], user["role"])
    await log_audit("login_success", "auth", actor=user)
    return {"token": token, "user": {"id": user["id"], "email": user["email"],
            "name": user["name"], "role": user["role"], "allowed_tabs": effective_tabs(user)}}


@router.post("/auth/register")
async def register(data: RegisterInput, current: dict = Depends(require_roles("admin"))):
    if data.role not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
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


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    user["allowed_tabs"] = effective_tabs(user)
    return user


@router.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    if user["role"] == "admin":
        users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(200)
        for u in users:
            u["allowed_tabs"] = effective_tabs(u)
        return users
    users = await db.users.find({}, {"_id": 0, "id": 1, "name": 1, "role": 1}).to_list(200)
    return users


@router.put("/users/{uid}/tabs")
async def update_user_tabs(uid: str, payload: dict, current: dict = Depends(require_roles("admin"))):
    tabs = [tt for tt in payload.get("allowed_tabs", []) if tt in ALL_TABS]
    res = await db.users.update_one({"id": uid}, {"$set": {"allowed_tabs": tabs}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    u = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})
    return u


@router.put("/users/{uid}")
async def update_user(uid: str, data: UpdateUserInput, current: dict = Depends(require_roles("admin"))):
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    updates = {}
    if data.name:
        updates["name"] = data.name
    if data.email:
        new_email = data.email.lower()
        clash = await db.users.find_one({"email": new_email, "id": {"$ne": uid}})
        if clash:
            raise HTTPException(status_code=400, detail="Email already in use")
        updates["email"] = new_email
    if data.role:
        if data.role not in ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        if target.get("role") == "admin" and data.role != "admin":
            raise HTTPException(status_code=400, detail="Cannot change an admin's role")
        updates["role"] = data.role
    if data.password:
        if len(data.password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        updates["password_hash"] = hash_password(data.password)
    if updates:
        await db.users.update_one({"id": uid}, {"$set": updates})
    u = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})
    u["allowed_tabs"] = effective_tabs(u)
    return u


@router.delete("/users/{uid}")
async def delete_user(uid: str, current: dict = Depends(require_roles("admin"))):
    if uid == current["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    await db.users.delete_one({"id": uid})
    return {"ok": True}


@router.get("/meta/tabs")
async def meta_tabs(current: dict = Depends(require_roles("admin"))):
    return {"tabs": ALL_TABS, "roles": ROLES, "defaults": DEFAULT_TABS}
