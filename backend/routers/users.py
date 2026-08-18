import uuid

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File

from core.db import db, now_iso, logger
from core.config import ROLES, ALL_TABS, APP_NAME
from core.security import hash_password, get_current_user, require_roles, effective_tabs
from core.audit import log_audit
from core.storage import put_object
from models.schemas import UpdateUserInput

router = APIRouter()

CREDENTIAL_KINDS = ("diploma", "exequatur")


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


# ---------------- provider credential documents ----------------
# Uploaded once per provider (diploma / exequatur), then automatically
# attached to every FMP claim packet for that provider — no need to
# re-upload per patient or per claim.
@router.get("/users/{uid}/credentials")
async def get_credentials(uid: str, user: dict = Depends(require_roles("admin", "biller"))):
    u = await db.users.find_one({"id": uid}, {"_id": 0, "diploma_doc": 1, "exequatur_doc": 1})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return {"diploma_doc": u.get("diploma_doc"), "exequatur_doc": u.get("exequatur_doc")}


@router.post("/users/{uid}/credentials/{kind}")
async def upload_credential(uid: str, kind: str, file: UploadFile = File(...),
                            user: dict = Depends(require_roles("admin"))):
    if kind not in CREDENTIAL_KINDS:
        raise HTTPException(status_code=400, detail="kind must be 'diploma' or 'exequatur'")
    target = await db.users.find_one({"id": uid}, {"_id": 0, "name": 1})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if not (file.filename or "").lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
        raise HTTPException(status_code=400, detail="Please upload a PDF or image file")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 15MB)")
    ext = file.filename.rsplit(".", 1)[-1].lower()
    ct = "application/pdf" if ext == "pdf" else f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"
    path = f"{APP_NAME}/providers/{uid}/{kind}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, data, ct)
    except Exception as e:
        logger.error(f"credential upload failed: {e}")
        raise HTTPException(status_code=502, detail="File storage failed")
    doc = {"storage_path": result["path"], "filename": file.filename[:160],
           "content_type": ct, "size": result.get("size"),
           "uploaded_at": now_iso(), "uploaded_by": user["name"]}
    await db.users.update_one({"id": uid}, {"$set": {f"{kind}_doc": doc}})
    try:
        from routers.claims import _sync_claims_for_provider
        await _sync_claims_for_provider(target.get("name"))
    except Exception as exc:
        logger.error(f"provider-credential claim auto-sync failed: {exc}")
    await log_audit("update", "user", actor=user, resource_id=uid, detail=f"{kind} credential uploaded")
    return doc
