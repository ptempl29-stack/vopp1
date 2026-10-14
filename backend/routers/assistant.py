import os
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from emergentintegrations.llm.chat import LlmChat, UserMessage

from core.db import db, now_iso, logger
from core.security import get_current_user
from core.audit import log_audit
from models.schemas import IdList

router = APIRouter()

SYSTEM_PROMPT = (
    "You are the clinical staff assistant for Veterans of Puerto Plata, a bilingual "
    "(English/Spanish) health clinic. You help doctors, nurses, psychologists, "
    "receptionists and billers with clinical documentation, summarizing notes, drafting "
    "letters, explaining CPT/ICD-10 codes, and general workflow questions. "
    "Reply in the same language the user writes in (English or Spanish). Be concise, "
    "professional and accurate. Do NOT invent clinical facts or patient data, and remind "
    "staff that your output is assistance only and not a substitute for professional "
    "medical judgment. Never request or store real patient identifiers (SSN, full DOB)."
)
MAX_HISTORY = 20


class MessageInput(BaseModel):
    content: str


def _title_from(text: str) -> str:
    t = " ".join((text or "").split())
    return (t[:48] + "…") if len(t) > 48 else (t or "New chat")


def _summary(conv: dict) -> dict:
    return {"id": conv["id"], "title": conv.get("title", "New chat"),
            "updated_at": conv.get("updated_at"), "created_at": conv.get("created_at"),
            "message_count": len(conv.get("messages", []))}


async def _owned(cid: str, user: dict) -> dict:
    conv = await db.ai_conversations.find_one({"id": cid, "user_id": user["id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.get("/assistant/conversations")
async def list_conversations(user: dict = Depends(get_current_user)):
    convs = await db.ai_conversations.find({"user_id": user["id"]}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    return [_summary(c) for c in convs]


@router.post("/assistant/conversations")
async def create_conversation(user: dict = Depends(get_current_user)):
    conv = {"id": str(uuid.uuid4()), "user_id": user["id"], "title": "New chat",
            "messages": [], "created_at": now_iso(), "updated_at": now_iso()}
    await db.ai_conversations.insert_one(conv)
    conv.pop("_id", None)
    return conv


@router.post("/assistant/conversations/bulk-delete")
async def bulk_delete_conversations(data: IdList, user: dict = Depends(get_current_user)):
    res = await db.ai_conversations.delete_many({"id": {"$in": data.ids}, "user_id": user["id"]})
    return {"deleted": res.deleted_count, "skipped": len(data.ids) - res.deleted_count}


@router.get("/assistant/conversations/{cid}")
async def get_conversation(cid: str, user: dict = Depends(get_current_user)):
    return await _owned(cid, user)


@router.delete("/assistant/conversations/{cid}")
async def delete_conversation(cid: str, user: dict = Depends(get_current_user)):
    await db.ai_conversations.delete_one({"id": cid, "user_id": user["id"]})
    return {"ok": True}


@router.post("/assistant/conversations/{cid}/message")
async def send_message(cid: str, data: MessageInput, user: dict = Depends(get_current_user)):
    text = (data.content or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message is empty")
    if len(text) > 8000:
        raise HTTPException(status_code=400, detail="Message too long")
    conv = await _owned(cid, user)
    history = conv.get("messages", [])[-MAX_HISTORY:]

    context = ""
    if history:
        lines = [f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in history]
        context = "\n\nConversation so far:\n" + "\n".join(lines)

    try:
        chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=cid,
                       system_message=SYSTEM_PROMPT + context).with_model("openai", "gpt-5.4")
        reply = await chat.send_message(UserMessage(text=text))
    except Exception:
        logger.exception("assistant chat failed")
        raise HTTPException(status_code=502, detail="AI assistant is unavailable right now. Please try again later.")

    user_msg = {"role": "user", "content": text, "ts": now_iso()}
    ai_msg = {"role": "assistant", "content": reply, "ts": now_iso()}
    update = {"$push": {"messages": {"$each": [user_msg, ai_msg]}}, "$set": {"updated_at": now_iso()}}
    if not conv.get("messages"):
        update["$set"]["title"] = _title_from(text)
    await db.ai_conversations.update_one({"id": cid}, update)
    await log_audit("create", "assistant", actor=user, resource_id=cid, detail="chat message")
    return {"reply": reply, "user_message": user_msg, "assistant_message": ai_msg}
