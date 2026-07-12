import re
import uuid

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from core.db import db, now_iso
from core.security import get_current_user, require_roles
from models.schemas import PatientInput

router = APIRouter()


@router.get("/patients")
async def list_patients(search: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {}
    if search:
        safe = re.escape(search.strip()[:80])
        q = {"$or": [{"first_name": {"$regex": safe, "$options": "i"}},
                     {"last_name": {"$regex": safe, "$options": "i"}}]}
    patients = await db.patients.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return patients


@router.post("/patients")
async def create_patient(data: PatientInput, user: dict = Depends(require_roles("doctor", "nurse", "receptionist"))):
    doc = data.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso(), "created_by": user["name"]})
    await db.patients.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/patients/{pid}")
async def get_patient(pid: str, user: dict = Depends(get_current_user)):
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return p


@router.put("/patients/{pid}")
async def update_patient(pid: str, data: PatientInput, user: dict = Depends(require_roles("doctor", "nurse", "receptionist"))):
    res = await db.patients.update_one({"id": pid}, {"$set": data.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Patient not found")
    return await db.patients.find_one({"id": pid}, {"_id": 0})


@router.delete("/patients/{pid}")
async def delete_patient(pid: str, user: dict = Depends(require_roles("doctor", "receptionist"))):
    await db.patients.delete_one({"id": pid})
    return {"ok": True}
