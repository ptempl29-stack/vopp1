import os
import re
import csv
import io
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from emergentintegrations.llm.chat import LlmChat, UserMessage

from core.db import db, now_iso, logger
from core.security import require_roles
from core.audit import log_audit
from core.ssn import redact_ssn, guard_ssn_write
from core.icd_codes import dismissed_icd, add_dismissed_icd, remove_dismissed_icd
from core.folder_filing import disp_date
from models.schemas import NoteInput, SummarizeInput, IdList
from core.config import CLINICAL_ROLES
from core.note_versions import archive_version, verify_chain, is_substantive, needs_protection

BILLING_REVIEW_STATUSES = {"approved", "needs_correction"}


class BillingReviewInput(BaseModel):
    status: str
    note: Optional[str] = None


from core.providers import resolve_provider_id as _resolve_provider_id  # noqa: E402


async def _is_note_provider(user: dict, note: dict) -> bool:
    """Authorize by verified account id: the note's author or attending provider only."""
    if user["role"] not in CLINICAL_ROLES:
        return False
    if user["id"] in (note.get("author_id"), note.get("attending_provider_id")):
        return True
    if not note.get("attending_provider_id") and await _resolve_provider_id(note.get("attending_provider")) == user["id"]:
        return True
    return not note.get("author_id") and await _resolve_provider_id(note.get("author")) == user["id"]

router = APIRouter()


@router.get("/notes")
async def list_notes(patient_id: Optional[str] = None, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    q = {"patient_id": patient_id} if patient_id else {}
    notes = await db.notes.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    await log_audit("view", "note", actor=user,
                    detail=f"list ({len(notes)})" + (f" patient={patient_id}" if patient_id else ""))
    return await redact_ssn(user, notes)


@router.post("/notes")
async def create_note(data: NoteInput, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    doc = await guard_ssn_write(user, data.model_dump())
    if doc.get("signature") and len(doc["signature"]) > 600000:
        raise HTTPException(status_code=400, detail="Signature too large")
    if doc.get("note_type") == "soap" and not doc.get("content"):
        parts = [("S", doc.get("subjective")), ("O", doc.get("objective")),
                 ("A", doc.get("assessment")), ("P", doc.get("plan"))]
        doc["content"] = "\n".join(f"{k}: {v}" for k, v in parts if v)
    if not doc.get("content"):
        raise HTTPException(status_code=400, detail="Note content is required")
    doc.pop("title_nonclinical_confirmed", None)
    if doc.get("signature") and user["role"] not in CLINICAL_ROLES:
        raise HTTPException(status_code=403, detail="Only clinical providers may sign progress notes")
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso(), "author": user["name"], "author_id": user["id"],
                "attending_provider_id": await _resolve_provider_id(doc.get("attending_provider"))})
    if doc.get("signature"):
        doc["signed_by"] = user["name"]
        doc["signed_by_id"] = user["id"]
        doc["signed_at"] = now_iso()
    doc["billing_review_status"] = "pending_review" if doc.get("signature") else "unsigned"
    await db.notes.insert_one(doc)
    doc.pop("_id", None)
    try:
        from routers.claims import _sync_matching_claims
        await _sync_matching_claims(doc.get("patient_id"), doc.get("visit_date"))
    except Exception as exc:
        logger.error(f"note-to-claim auto-sync failed: {exc}")
    await log_audit("create", "note", actor=user, resource_id=doc["id"],
                    detail=f"{doc.get('note_type','free')}: {doc.get('title','')}")
    return await redact_ssn(user, doc)


@router.put("/notes/{nid}")
async def update_note(nid: str, data: NoteInput, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    existing = await db.notes.find_one({"id": nid})
    if not existing:
        raise HTTPException(status_code=404, detail="Note not found")
    doc = await guard_ssn_write(user, data.model_dump(), existing.get("ssn"))
    title_ok = doc.pop("title_nonclinical_confirmed", False)
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
    if (doc.get("attending_provider") or "") != (existing.get("attending_provider") or ""):
        doc["attending_provider_id"] = await _resolve_provider_id(doc.get("attending_provider"))
    protected = needs_protection(existing)
    substantive = protected and is_substantive(existing, {**doc, "title_nonclinical_confirmed": title_ok})
    if protected and not substantive and not doc.get("signature"):
        for f in ("signature", "signed_by", "signed_at"):
            doc.pop(f, None)  # non-substantive save without re-signing keeps the existing signature
    # A signature submitted with a substantive revision is an explicit signing of the NEW version,
    # even when it is the provider's saved/default signature image.
    resigned = bool(doc.get("signature")) and (doc.get("signature") != existing.get("signature") or substantive)
    revised = bool(existing.get("version_count")) and not existing.get("signature")
    if resigned and not await _is_note_provider(user, existing if existing.get("attending_provider") else {**existing, **doc}):
        raise HTTPException(status_code=403, detail="Only the note's attending or authoring provider may sign this note")
    if protected and (substantive or resigned):
        await archive_version(existing, "substantive edit" if substantive else "re-signed", user)
        doc["version_count"] = (existing.get("version_count") or 0) + 1
        doc["revised_at"] = now_iso()
    if substantive:
        doc.update({"completed": False, "completed_at": None, "completed_by": None,
                    "billing_reviewed_by": None, "billing_reviewed_at": None, "billing_review_note": None})
        if not resigned:
            doc.update({"signature": None, "signed_by": None, "signed_by_id": None, "signed_at": None})
    if resigned:
        doc["signed_by"] = user["name"]
        doc["signed_by_id"] = user["id"]
        doc["signed_at"] = now_iso()
        doc["billing_review_status"] = "pending_review"
        doc.update({"billing_reviewed_by": None, "billing_reviewed_at": None, "billing_review_note": None})
    elif not doc.get("signature"):
        doc["billing_review_status"] = "unsigned"
    await db.notes.update_one({"id": nid}, {"$set": doc})
    updated = await db.notes.find_one({"id": nid}, {"_id": 0})
    try:
        from routers.claims import _sync_matching_claims
        await _sync_matching_claims(updated.get("patient_id"), updated.get("visit_date"))
    except Exception as exc:
        logger.error(f"note-to-claim auto-sync failed: {exc}")
    await log_audit("update", "note", actor=user, resource_id=nid,
                    detail=f"{doc.get('note_type','free')}: {doc.get('title','')}")
    return await redact_ssn(user, updated)


@router.delete("/notes/{nid}")
async def delete_note(nid: str, user: dict = Depends(require_roles("doctor", "nurse", "psychologist", "admin"))):
    existing = await db.notes.find_one({"id": nid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Note not found")
    if user["role"] != "admin" and existing.get("author") not in (user["name"], None):
        raise HTTPException(status_code=403, detail="You can only delete notes you authored")
    await archive_version(existing, "note deleted", user)
    await db.notes.delete_one({"id": nid})
    await log_audit("delete", "note", actor=user, resource_id=nid,
                    detail=f"{existing.get('note_type', 'free')}: {existing.get('title', '')}")
    return {"ok": True}


class CompleteInput(BaseModel):
    completed: bool


@router.put("/notes/{nid}/complete")
async def set_note_complete(nid: str, data: CompleteInput,
                            user: dict = Depends(require_roles("doctor", "nurse", "psychologist", "admin"))):
    existing = await db.notes.find_one({"id": nid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Note not found")
    if data.completed and not existing.get("signature"):
        raise HTTPException(status_code=400, detail="A note must be signed by its provider before it can be completed")
    if data.completed:
        upd = {"completed": True, "completed_at": now_iso(), "completed_by": user["name"]}
    else:
        upd = {"completed": False, "completed_at": None, "completed_by": None}
    await db.notes.update_one({"id": nid}, {"$set": upd})
    await log_audit("update", "note", actor=user, resource_id=nid,
                    detail="marked complete" if data.completed else "reopened")
    return {"ok": True, **upd}


@router.get("/notes/export-completed")
async def export_completed_notes(start: Optional[str] = None, end: Optional[str] = None,
                                 user: dict = Depends(require_roles("doctor", "nurse", "psychologist", "admin"))):
    def sess(n):
        return (n.get("visit_date") or (n.get("created_at") or "")[:10] or "")
    notes = await db.notes.find({"completed": True}, {"_id": 0}).to_list(2000)
    if start:
        notes = [n for n in notes if sess(n) >= start]
    if end:
        notes = [n for n in notes if sess(n) <= end]
    notes.sort(key=sess)
    patients = {}
    async for p in db.patients.find({}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).limit(5000):
        patients[p["id"]] = f"{p['first_name']} {p['last_name']}"
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Patient", "Session Date", "Provider", "ICD-10", "CPT", "Risk",
                "Completed Date", "Completed By"])
    for n in notes:
        w.writerow([
            patients.get(n.get("patient_id"), "Unknown"),
            disp_date(sess(n)),
            n.get("attending_provider") or n.get("author") or "",
            n.get("icd10") or "", n.get("cpt_code") or "", n.get("risk_level") or "",
            disp_date(n.get("completed_at")), n.get("completed_by") or "",
        ])
    out.seek(0)
    await log_audit("view", "note", actor=user, detail=f"export-completed ({len(notes)})")
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=completed_notes.csv"})


@router.post("/notes/bulk-complete")
async def bulk_complete_notes(data: IdList, user: dict = Depends(require_roles("doctor", "nurse", "psychologist", "admin"))):
    if not data.ids:
        return {"updated": 0}
    res = await db.notes.update_many(
        {"id": {"$in": data.ids}, "signature": {"$nin": [None, ""]}},
        {"$set": {"completed": True, "completed_at": now_iso(), "completed_by": user["name"]}})
    await log_audit("update", "note", actor=user, detail=f"bulk complete ({res.modified_count})")
    return {"updated": res.modified_count}


@router.post("/notes/bulk-delete")
async def bulk_delete_notes(data: IdList, user: dict = Depends(require_roles("doctor", "nurse", "psychologist", "admin"))):
    docs = await db.notes.find({"id": {"$in": data.ids}}, {"_id": 0, "id": 1, "author": 1}).to_list(1000)
    deletable = [d["id"] for d in docs
                 if user["role"] == "admin" or d.get("author") in (user["name"], None)]
    if deletable:
        async for n in db.notes.find({"id": {"$in": deletable}}, {"_id": 0}):
            await archive_version(n, "note deleted", user)
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
    rnc = (s or {}).get("rnc", "")
    vd = note.get("visit_date")
    ds = fmt_date(vd)
    try:
        pdf = note_pdf(note, clinic, rnc)
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
    hidden = await dismissed_icd(patient_id)
    return {"icd10": sorted((set(icd) | set(icd_inv)) - hidden), "cpt": sorted(c for c in cpt if c)}


class DismissCode(BaseModel):
    patient_id: str
    code: str


@router.post("/notes/patient-code-history/dismiss")
async def notes_dismiss_icd(data: DismissCode, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    await add_dismissed_icd(data.patient_id, data.code, user)
    return {"ok": True}


@router.post("/notes/patient-code-history/restore")
async def notes_restore_icd(data: DismissCode, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    await remove_dismissed_icd(data.patient_id, data.code)
    return {"ok": True}


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
            "cpt_code": n.get("cpt_code"),
            "attending_provider": n.get("attending_provider"),
            "dob": n.get("dob"), "gender": n.get("gender"), "ssn": n.get("ssn"),
            "preview": content[:180] + ("…" if len(content) > 180 else ""),
        })
    return await redact_ssn(user, out)


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


@router.put("/notes/{nid}/billing-review")
async def billing_review_note(nid: str, data: BillingReviewInput, user: dict = Depends(require_roles("admin"))):
    """Administrative billing-readiness check only — not a clinical co-signature."""
    if data.status not in BILLING_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail="status must be 'approved' or 'needs_correction'")
    existing = await db.notes.find_one({"id": nid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Note not found")
    if not existing.get("signature"):
        raise HTTPException(status_code=400, detail="This note has not been signed by its provider yet")
    note_text = (data.note or "").strip()[:2000] or None
    await db.notes.update_one({"id": nid}, {"$set": {
        "billing_review_status": data.status, "billing_reviewed_by": user["name"],
        "billing_reviewed_at": now_iso(), "billing_review_note": note_text}})
    await log_audit("update", "note", actor=user, resource_id=nid,
                    detail=f"billing review: {data.status}" + (f" — {note_text}" if note_text else ""))
    return await db.notes.find_one({"id": nid}, {"_id": 0})


@router.get("/notes/{nid}/versions")
async def note_versions(nid: str, user: dict = Depends(require_roles("doctor", "nurse", "psychologist", "admin"))):
    note = await db.notes.find_one({"id": nid}, {"_id": 0, "attending_provider": 1, "attending_provider_id": 1, "author": 1, "author_id": 1, "version_count": 1})
    first = await db.note_versions.find_one({"note_id": nid}, {"_id": 0, "snapshot.attending_provider": 1})
    if not note and not first:
        raise HTTPException(status_code=404, detail="Note not found")
    ref = note or {"attending_provider": (first or {}).get("snapshot", {}).get("attending_provider")}
    if user["role"] != "admin" and not await _is_note_provider(user, ref):
        raise HTTPException(status_code=403, detail="Only admins or the note's provider can view version history")
    versions = await db.note_versions.find({"note_id": nid}, {"_id": 0}).sort("version", 1).to_list(1000)
    integrity = await verify_chain(nid, (note or {}).get("version_count") if note else None)
    await log_audit("view", "note", actor=user, resource_id=nid, detail=f"version history ({len(versions)})")
    return await redact_ssn(user, {"versions": versions, "integrity": integrity})


@router.get("/notes-integrity/verify")
async def verify_all_versions(user: dict = Depends(require_roles("admin"))):
    ids = await db.note_versions.distinct("note_id")
    counts = {n["id"]: n.get("version_count") async for n in db.notes.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "version_count": 1})}
    failed = []
    for nid in ids:
        r = await verify_chain(nid, counts.get(nid) if nid in counts else None)
        if not r["ok"]:
            failed.append({"note_id": nid, "problems": r["problems"]})
    await log_audit("view", "note", actor=user, detail=f"integrity verify ({len(ids)} notes, {len(failed)} failed)")
    return {"checked": len(ids), "failed": failed}

