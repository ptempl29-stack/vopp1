import os
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from emergentintegrations.llm.chat import LlmChat, UserMessage

from core.db import db, now_iso, logger
from core.security import require_roles
from core.audit import log_audit
from models.schemas import NoteInput, SummarizeInput, IdList

router = APIRouter()


@router.get("/notes")
async def list_notes(patient_id: Optional[str] = None, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    q = {"patient_id": patient_id} if patient_id else {}
    notes = await db.notes.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    await log_audit("view", "note", actor=user,
                    detail=f"list ({len(notes)})" + (f" patient={patient_id}" if patient_id else ""))
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
    await log_audit("create", "note", actor=user, resource_id=doc["id"],
                    detail=f"{doc.get('note_type','free')}: {doc.get('title','')}")
    return doc


@router.put("/notes/{nid}")
async def update_note(nid: str, data: NoteInput, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    existing = await db.notes.find_one({"id": nid})
    if not existing:
        raise HTTPException(status_code=404, detail="Note not found")
    doc = data.model_dump()
    if doc.get("signature") and len(doc["signature"]) > 600000:
        raise HTTPException(status_code=400, detail="Signature too large")
    if doc.get("note_type") == "soap" and not doc.get("content"):
        parts = [("S", doc.get("subjective")), ("O", doc.get("objective")),
                 ("A", doc.get("assessment")), ("P", doc.get("plan"))]
        doc["content"] = "\n".join(f"{k}: {v}" for k, v in parts if v)
    if not doc.get("content"):
        raise HTTPException(status_code=400, detail="Note content is required")
    doc["updated_at"] = now_iso()
    doc["updated_by"] = user["name"]
    if doc.get("signature") and doc.get("signature") != existing.get("signature"):
        doc["signed_by"] = user["name"]
        doc["signed_at"] = now_iso()
    await db.notes.update_one({"id": nid}, {"$set": doc})
    await log_audit("update", "note", actor=user, resource_id=nid,
                    detail=f"{doc.get('note_type','free')}: {doc.get('title','')}")
    return await db.notes.find_one({"id": nid}, {"_id": 0})


@router.delete("/notes/{nid}")
async def delete_note(nid: str, user: dict = Depends(require_roles("doctor", "nurse", "psychologist", "admin"))):
    existing = await db.notes.find_one({"id": nid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Note not found")
    if user["role"] != "admin" and existing.get("author") not in (user["name"], None):
        raise HTTPException(status_code=403, detail="You can only delete notes you authored")
    await db.notes.delete_one({"id": nid})
    await log_audit("delete", "note", actor=user, resource_id=nid,
                    detail=f"{existing.get('note_type', 'free')}: {existing.get('title', '')}")
    return {"ok": True}


@router.post("/notes/bulk-delete")
async def bulk_delete_notes(data: IdList, user: dict = Depends(require_roles("doctor", "nurse", "psychologist", "admin"))):
    docs = await db.notes.find({"id": {"$in": data.ids}}, {"_id": 0, "id": 1, "author": 1}).to_list(1000)
    deletable = [d["id"] for d in docs
                 if user["role"] == "admin" or d.get("author") in (user["name"], None)]
    if deletable:
        await db.notes.delete_many({"id": {"$in": deletable}})
    await log_audit("delete", "note", actor=user, detail=f"bulk ({len(deletable)})")
    return {"deleted": len(deletable), "skipped": len(data.ids) - len(deletable)}


@router.post("/notes/{nid}/to-folder")
async def note_to_folder(nid: str, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    from core.folder_filing import note_pdf, file_pdf_into_folder
    note = await db.notes.find_one({"id": nid}, {"_id": 0})
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    pid = note.get("patient_id")
    if not pid:
        raise HTTPException(status_code=400, detail="Note has no linked patient")
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    note = {**note, "patient_name": f"{p['first_name']} {p['last_name']}", "dob": p.get("dob"), "ssn": p.get("ssn")}
    s = await db.settings.find_one({"key": "clinic"}, {"_id": 0})
    clinic = (s or {}).get("clinic_name", "Veterans of Puerto Plata")
    from datetime import datetime, timezone
    ds = datetime.now(timezone.utc).strftime("%m-%d-%Y")
    try:
        pdf = note_pdf(note, clinic)
    except Exception as e:
        logger.error(f"note pdf failed: {e}")
        raise HTTPException(status_code=500, detail="Could not render note PDF")
    item = await file_pdf_into_folder(pid, p["first_name"], pdf,
                                      f"Progress Note {ds}", f"Progress_Note_{ds}.pdf", user)
    if not item:
        raise HTTPException(status_code=502, detail="Could not file PDF")
    await log_audit("create", "folder", actor=user, resource_id=pid, detail=f"auto-filed note {nid}")
    return {"ok": True, "patient_name": note["patient_name"]}


@router.get("/notes/patient-code-history")
async def patient_code_history(patient_id: str, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    icd = await db.notes.distinct("icd10", {"patient_id": patient_id, "icd10": {"$nin": [None, ""]}})
    icd_inv = await db.invoices.distinct("icd10", {"patient_id": patient_id, "icd10": {"$nin": [None, ""]}})
    cpt = await db.notes.distinct("cpt_code", {"patient_id": patient_id, "cpt_code": {"$nin": [None, ""]}})
    return {"icd10": sorted(set(icd) | set(icd_inv)), "cpt": sorted(c for c in cpt if c)}


@router.get("/notes/for-billing")
async def notes_for_billing(patient_id: str,
                            user: dict = Depends(require_roles("biller", "receptionist", "admin"))):
    notes = await db.notes.find({"patient_id": patient_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    await log_audit("view", "note", actor=user, detail=f"for-billing patient={patient_id} ({len(notes)})")
    out = []
    for n in notes:
        content = (n.get("content") or "").strip()
        out.append({
            "id": n["id"], "note_type": n.get("note_type", "free"),
            "created_at": n.get("created_at"), "visit_date": n.get("visit_date"),
            "reason_for_visit": n.get("reason_for_visit"), "icd10": n.get("icd10"),
            "attending_provider": n.get("attending_provider"),
            "dob": n.get("dob"), "gender": n.get("gender"), "ssn": n.get("ssn"),
            "preview": content[:180] + ("…" if len(content) > 180 else ""),
        })
    return out


@router.post("/notes/summarize")
async def summarize_note(data: SummarizeInput, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="No content to summarize")
    try:
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"note-{uuid.uuid4()}",
            system_message=(
                "You are a licensed, highly experienced clinical psychologist with extensive "
                "knowledge in psychotherapy, diagnosis, and clinical documentation. Rewrite/expand "
                "the provided progress note into a polished, professional clinical narrative written "
                "in the confident, precise tone of a seasoned psychologist. Organize it into the "
                "standard progress-note sections (Subjective, Objective, Assessment, Plan) and write "
                "3 to 4 sentences for EACH section. Use appropriate clinical terminology, remain "
                "objective, and do NOT invent facts not supported by the input — expand only on what "
                "is clinically implied. Return only the note text."),
        ).with_model("openai", "gpt-5.4")
        resp = await chat.send_message(UserMessage(text=data.content))
        return {"summary": resp}
    except Exception:
        logger.exception("summarize failed")
        raise HTTPException(status_code=500, detail="AI summarization failed. Please try again later.")
