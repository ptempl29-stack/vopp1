import uuid

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import Response
from typing import Optional

from core.db import db, now_iso, logger
from core.config import APP_NAME, EXT_CONTENT_TYPES
from core.security import get_current_user
from core.audit import log_audit
from core.storage import put_object, get_object
from models.schemas import IdList

router = APIRouter()


@router.get("/messages")
async def list_messages(user: dict = Depends(get_current_user)):
    msgs = await db.messages.find(
        {"$or": [{"to_user_id": user["id"]}, {"from_user_id": user["id"]}]},
        {"_id": 0}).sort("created_at", 1).to_list(2000)
    return msgs


@router.get("/messages/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    n = await db.messages.count_documents({"to_user_id": user["id"], "read": False})
    return {"unread": n}


@router.post("/messages")
async def send_message(to_user_id: str = Form(...), subject: str = Form(""), body: str = Form(...),
                       thread_id: str = Form(""), file: Optional[UploadFile] = File(None),
                       user: dict = Depends(get_current_user)):
    if not body.strip() and not file:
        raise HTTPException(status_code=400, detail="Message body is required")
    to = await db.users.find_one({"id": to_user_id}, {"_id": 0, "name": 1})
    if not to:
        raise HTTPException(status_code=404, detail="Recipient not found")
    attachment = None
    if file is not None:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
        if ext not in EXT_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail="Unsupported file type")
        payload = await file.read()
        if len(payload) > 15 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (max 15MB)")
        path = f"{APP_NAME}/messages/{user['id']}/{uuid.uuid4()}.{ext}"
        try:
            result = put_object(path, payload, EXT_CONTENT_TYPES[ext])
        except Exception as e:
            logger.error(f"message attachment upload failed: {e}")
            raise HTTPException(status_code=502, detail="File storage failed")
        attachment = {"storage_path": result["path"], "filename": file.filename,
                      "content_type": EXT_CONTENT_TYPES[ext], "size": result.get("size")}
    doc = {"id": str(uuid.uuid4()), "thread_id": thread_id or str(uuid.uuid4()),
           "from_user_id": user["id"], "from_name": user["name"],
           "to_user_id": to_user_id, "to_name": to["name"],
           "subject": subject or "", "body": body, "attachment": attachment,
           "read": False, "created_at": now_iso()}
    await db.messages.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "message", actor=user, resource_id=doc["id"], detail=f"to {to['name']}")
    return doc


@router.get("/messages/{mid}/attachment")
async def download_attachment(mid: str, user: dict = Depends(get_current_user)):
    m = await db.messages.find_one({"id": mid}, {"_id": 0})
    if not m or not m.get("attachment"):
        raise HTTPException(status_code=404, detail="Attachment not found")
    if user["id"] not in (m["from_user_id"], m["to_user_id"]):
        raise HTTPException(status_code=403, detail="You are not a participant in this conversation")
    data, _ = get_object(m["attachment"]["storage_path"])
    fname = m["attachment"]["filename"].replace('"', "").replace("\n", "").replace("\r", "")
    await log_audit("view", "message", actor=user, resource_id=mid, detail=f"download: {fname}")
    return Response(content=data, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"',
                 "X-Content-Type-Options": "nosniff"})


@router.put("/messages/{mid}/read")
async def mark_read(mid: str, user: dict = Depends(get_current_user)):
    res = await db.messages.update_one({"id": mid, "to_user_id": user["id"]}, {"$set": {"read": True}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True}


@router.put("/messages/thread/{thread_id}/read")
async def mark_thread_read(thread_id: str, user: dict = Depends(get_current_user)):
    await db.messages.update_many({"thread_id": thread_id, "to_user_id": user["id"], "read": False},
                                  {"$set": {"read": True}})
    return {"ok": True}


@router.post("/messages/bulk-delete")
async def bulk_delete_messages(data: IdList, user: dict = Depends(get_current_user)):
    q = {"id": {"$in": data.ids}}
    if user["role"] != "admin":
        q["$or"] = [{"from_user_id": user["id"]}, {"to_user_id": user["id"]}]
    res = await db.messages.delete_many(q)
    return {"deleted": res.deleted_count, "skipped": len(data.ids) - res.deleted_count}


@router.delete("/messages/{mid}")
async def delete_message(mid: str, user: dict = Depends(get_current_user)):
    q = {"id": mid}
    if user["role"] != "admin":
        q["$or"] = [{"from_user_id": user["id"]}, {"to_user_id": user["id"]}]
    res = await db.messages.delete_one(q)
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True}
