import uuid

from fastapi import APIRouter, HTTPException, Depends

from core.db import db, now_iso
from core.security import get_current_user
from models.schemas import MessageInput

router = APIRouter()


@router.get("/messages")
async def list_messages(user: dict = Depends(get_current_user)):
    msgs = await db.messages.find(
        {"$or": [{"to_user_id": user["id"]}, {"from_user_id": user["id"]}]},
        {"_id": 0}).sort("created_at", -1).to_list(500)
    return msgs


@router.post("/messages")
async def send_message(data: MessageInput, user: dict = Depends(get_current_user)):
    to = await db.users.find_one({"id": data.to_user_id}, {"_id": 0})
    doc = {"id": str(uuid.uuid4()), "from_user_id": user["id"], "from_name": user["name"],
           "to_user_id": data.to_user_id, "to_name": to["name"] if to else "Unknown",
           "subject": data.subject, "body": data.body, "read": False, "created_at": now_iso()}
    await db.messages.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/messages/{mid}/read")
async def mark_read(mid: str, user: dict = Depends(get_current_user)):
    res = await db.messages.update_one({"id": mid, "to_user_id": user["id"]}, {"$set": {"read": True}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True}
