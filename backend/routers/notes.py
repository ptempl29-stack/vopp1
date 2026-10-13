import os
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from emergentintegrations.llm.chat import LlmChat, UserMessage

from core.db import db, now_iso, logger
from core.security import require_roles
from core.audit import log_audit
from models.schemas import NoteInput, SummarizeInput, IdList

router = APIRouter()

# Admin billing-readiness review of a signed progress note. This is an
# administrative/billing check only — it is NOT a clinical co-signature or
# review of care, and it never alters the provider's own clinical signature.
BILLING_REVIEW_STATUSES = {"approved", "needs_correction"}


class BillingReviewInput(BaseModel):
    status: str
    note: Optional[str] = None


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
        doc["billing_review_status"] = "pending_review"
    else:
        doc["billing_review_status"] = "unsigned"
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

    was_signed = bool(existing.get("signature"))
    was_approved = existing.get("billing_review_status") == "approved"
    resigned = bool(doc.get("signature")) and doc.get("signature") != existing.get("signature")

    if was_signed and (resigned or was_approved):
        # Archive the prior signed version + its full approval history before
        # changing anything — nothing about a past approval is ever lost.
        history_entry = {
            "content": existing.get("content"), "signature": existing.get("signature"),
            "signed_by": existing.get("signed_by"), "signed_at": existing.get("signed_at"),
            "billing_review_status": existing.get("billing_review_status"),
            "billing_reviewed_by": existing.get("billing_reviewed_by"),
            "billing_reviewed_at": existing.get("billing_reviewed_at"),
            "billing_review_note": existing.get("billing_review_note"),
            "archived_at": now_iso(), "archived_by": user["name"],
            "archived_reason": "re-signed" if resigned else "edited after billing approval",
        }
        doc["history"] = (existing.get("history") or []) + [history_entry]

    if resigned:
        # (Re-)signed: a new signature always needs a fresh billing review.
        doc["signed_by"] = user["name"]
        doc["signed_at"] = now_iso()
        doc["billing_review_status"] = "pending_review"
        doc["billing_reviewed_by"] = None
        doc["billing_reviewed_at"] = None
        doc["billing_review_note"] = None
    elif was_approved:
        # Approved note edited without drawing a fresh signature: the carried-over
        # signature image is now stale for the edited content. Require the
        # provider to actually re-sign, and billing to re-approve, before this
        # note counts as ready again.
        doc["signature"] = None
        doc["signed_by"] = None
        doc["signed_at"] = None
        doc["billing_review_status"] = "unsigned"
        doc["billing_reviewed_by"] = None
        doc["billing_reviewed_at"] = None
        doc["billing_review_note"] = None
    elif not doc.get("signature") and existing.get("signature"):
        # Signature removed: nothing left to bill-review.
        doc["billing_review_status"] = "unsigned"
        doc["billing_reviewed_by"] = None
        doc["billing_reviewed_at"] = None
        doc["billing_review_note"] = None
    await db.notes.update_one({"id": nid}, {"$set": doc})
    await log_audit("update", "note", actor=user, resource_id=nid,
                    detail=f"{doc.get('note_type','free')}: {doc.get('title','')}")
    return await db.notes.find_one({"id": nid}, {"_id": 0})


@router.put("/notes/{nid}/billing-review")
async def billing_review_note(nid: str, data: BillingReviewInput, user: dict = Depends(require_roles("admin"))):
    """Admin billing-readiness check on a signed progress note: confirms the
    note is ready to bill, or flags it for correction. This is an
    administrative/billing approval only — it is NOT a clinical co-signature,
    does not review the clinical content of care, and never touches the
    provider's own signature."""
    if data.status not in BILLING_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail="status must be 'approved' or 'needs_correction'")
    existing = await db.notes.find_one({"id": nid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Note not found")
    if not existing.get("signature"):
        raise HTTPException(status_code=400, detail="This note has not been signed by its provider yet")
    note_text = (data.note or "").strip() or None
    await db.notes.update_one({"id": nid}, {"$set": {
        "billing_review_status": data.status,
        "billing_reviewed_by": user["name"],
        "billing_reviewed_at": now_iso(),
        "billing_review_note": note_text,
    }})
    await log_audit("update", "note", actor=user, resource_id=nid,
                    detail=f"billing review: {data.status}" + (f" — {note_text}" if note_text else ""))
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
    from core.folder_filing import note_pdf, file_pdf_into_folder, fmt_date
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
    vd = note.get("visit_date")
    ds = fmt_date(vd)
    try:
        pdf = note_pdf(note, clinic)
    except Exception as e:
        logger.error(f"note pdf failed: {e}")
        raise HTTPException(status_code=500, detail="Could not render note PDF")
    item = await file_pdf_into_folder(pid, p["first_name"], pdf,
                                      f"Prog {ds}".strip(), f"Prog_{ds}.pdf", user, date_str=vd)
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
