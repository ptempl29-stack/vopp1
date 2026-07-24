from fastapi import APIRouter, HTTPException, Depends

from core.db import db
from core.config import ROLES, ALL_TABS
from core.security import hash_password, get_current_user, require_roles, effective_tabs
from core.audit import log_audit
from models.schemas import UpdateUserInput

router = APIRouter()


@router.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    if user["role"] == "admin":
        users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(200)
        for u in users:
            u["allowed_tabs"] = effective_tabs(u)
        return users
    users = await db.users.find({}, {"_id": 0, "id": 1, "name": 1, "role": 1, "title": 1, "exequatur_number": 1}).to_list(200)
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


@router.put("/users/{uid}/active")
async def set_user_active(uid: str, payload: dict, current: dict = Depends(require_roles("admin"))):
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if uid == current["id"]:
        raise HTTPException(status_code=400, detail="You cannot change your own access")
    if target.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Cannot suspend an administrator")
    active = bool(payload.get("active", True))
    await db.users.update_one({"id": uid}, {"$set": {"active": active}})
    await log_audit("update", "user", actor=current, resource_id=uid,
                    detail=f"access {'restored' if active else 'suspended'}")
    u = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})
    u["allowed_tabs"] = effective_tabs(u)
    return u


@router.put("/users/{uid}/password")
async def admin_reset_password(uid: str, payload: dict, current: dict = Depends(require_roles("admin"))):
    if uid == current["id"]:
        raise HTTPException(status_code=400, detail="Use Change Password to update your own password")
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    new_pw = (payload or {}).get("password", "")
    if len(new_pw) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    require_change = payload.get("require_change", True)
    await db.users.update_one({"id": uid}, {
        "$set": {"password_hash": hash_password(new_pw), "must_change_password": bool(require_change)},
        "$inc": {"token_version": 1}})
    await log_audit("update", "user", actor=current, resource_id=uid, detail="password reset")
    return {"ok": True}


@router.post("/users/{uid}/logout")
async def force_logout(uid: str, current: dict = Depends(require_roles("admin"))):
    if uid == current["id"]:
        raise HTTPException(status_code=400, detail="Cannot force-logout your own account")
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"id": uid}, {"$inc": {"token_version": 1}})
    await log_audit("update", "user", actor=current, resource_id=uid, detail="force logout")
    return {"ok": True}
