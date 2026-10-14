import re
import uuid

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from pydantic import BaseModel

from core.db import db, now_iso
from core.security import get_current_user, require_roles
from core.audit import log_audit
from core.ssn import redact_ssn, guard_ssn_write
from models.schemas import PatientInput

router = APIRouter()


class IcdBulk(BaseModel):
    code: str
    replacement: Optional[str] = None


@router.post("/patients/{pid}/icd-bulk")
async def icd_bulk_cleanup(pid: str, data: IcdBulk,
                           user: dict = Depends(require_roles("doctor", "nurse", "psychologist", "biller", "receptionist"))):
    """Remove or replace an ICD-10 code across ALL of a patient's notes and invoices in one action."""
    code = (data.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Code is required")
    new_val = (data.replacement or "").strip()
    nres = await db.notes.update_many({"patient_id": pid, "icd10": code}, {"$set": {"icd10": new_val}})
    ires = await db.invoices.update_many({"patient_id": pid, "icd10": code}, {"$set": {"icd10": new_val}})
    await db.dismissed_icd_codes.delete_one({"patient_id": pid, "code": code})
    await log_audit("update", "patient", actor=user, resource_id=pid,
                    detail=f"ICD bulk {'replace→'+new_val if new_val else 'remove'} '{code}' · notes {nres.modified_count} · invoices {ires.modified_count}")
    return {"code": code, "replacement": new_val or None,
            "notes_updated": nres.modified_count, "invoices_updated": ires.modified_count}


@router.get("/patients")
async def list_patients(search: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {}
    if search:
        safe = re.escape(search.strip()[:80])
        q = {"$or": [{"first_name": {"$regex": safe, "$options": "i"}},
                     {"last_name": {"$regex": safe, "$options": "i"}}]}
    patients = await db.patients.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    await log_audit("view", "patient", actor=user,
                    detail=f"list ({len(patients)})" + (f" search='{search[:40]}'" if search else ""))
    return await redact_ssn(user, patients)


@router.post("/patients")
async def create_patient(data: PatientInput, user: dict = Depends(require_roles("doctor", "nurse", "receptionist"))):
    doc = await guard_ssn_write(user, data.model_dump())
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso(), "created_by": user["name"]})
    await db.patients.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "patient", actor=user, resource_id=doc["id"],
                    detail=f"{doc['first_name']} {doc['last_name']}")
    return await redact_ssn(user, doc)


@router.get("/patients/{pid}")
async def get_patient(pid: str, user: dict = Depends(get_current_user)):
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    await log_audit("view", "patient", actor=user, resource_id=pid,
                    detail=f"{p.get('first_name','')} {p.get('last_name','')}")
    return await redact_ssn(user, p)


@router.put("/patients/{pid}")
async def update_patient(pid: str, data: PatientInput, user: dict = Depends(require_roles("doctor", "nurse", "receptionist"))):
    existing = await db.patients.find_one({"id": pid}, {"_id": 0, "ssn": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Patient not found")
    await db.patients.update_one({"id": pid}, {"$set": await guard_ssn_write(user, data.model_dump(), existing.get("ssn"))})
    await log_audit("update", "patient", actor=user, resource_id=pid,
                    detail=f"{data.first_name} {data.last_name}")
    return await redact_ssn(user, await db.patients.find_one({"id": pid}, {"_id": 0}))


@router.delete("/patients/{pid}")
async def delete_patient(pid: str, user: dict = Depends(require_roles("doctor", "receptionist"))):
    await db.patients.delete_one({"id": pid})
    await log_audit("delete", "patient", actor=user, resource_id=pid)
    return {"ok": True}
