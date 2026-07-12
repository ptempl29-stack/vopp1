import os
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from emergentintegrations.llm.chat import LlmChat, UserMessage

from core.db import db, now_iso, logger
from core.security import require_roles
from models.schemas import NoteInput, SummarizeInput

router = APIRouter()


@router.get("/notes")
async def list_notes(patient_id: Optional[str] = None, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    q = {"patient_id": patient_id} if patient_id else {}
    notes = await db.notes.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return notes


@router.post("/notes")
async def create_note(data: NoteInput, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    doc = data.model_dump()
    if doc.get("signature") and len(doc["signature"]) > 600000:
        raise HTTPException(status_code=400, detail="Signature too large")
    if doc.get("note_type") == "soap" and not doc.get("content"):
        parts = [("S", doc.get("subjective")), ("O", doc.get("objective")),
                 ("A", doc.get("assessment")), ("P", doc.get("plan"))]
        doc["content"] = "\n".join(f"{k}: {v}" for k, v in parts if v)
    if not doc.get("content"):
        raise HTTPException(status_code=400, detail="Note content is required")
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso(), "author": user["name"]})
    if doc.get("signature"):
        doc["signed_by"] = user["name"]
        doc["signed_at"] = now_iso()
    await db.notes.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/notes/summarize")
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
    except Exception:
        logger.exception("summarize failed")
        raise HTTPException(status_code=500, detail="AI summarization failed. Please try again later.")
