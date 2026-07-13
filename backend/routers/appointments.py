import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from core.db import db, now_iso
from core.security import get_current_user, require_roles
from models.schemas import AppointmentInput, IdList

router = APIRouter()

STAFF = ("doctor", "nurse", "receptionist", "psychologist")


@router.get("/appointments")
async def list_appointments(patient_id: Optional[str] = None, appointment_type: Optional[str] = None,
                            provider: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {}
    if patient_id:
        q["patient_id"] = patient_id
    if appointment_type:
        q["appointment_type"] = appointment_type
    if provider:
        q["provider"] = provider
    appts = await db.appointments.find(q, {"_id": 0}).sort("date", 1).to_list(500)
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}"
                async for p in db.patients.find({}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1})}
    for a in appts:
        a["patient_name"] = patients.get(a["patient_id"], "Unknown")
    return appts


@router.post("/appointments")
async def create_appointment(data: AppointmentInput, user: dict = Depends(require_roles(*STAFF))):
    doc = data.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso(),
                "created_by": user["name"], "created_by_id": user["id"]})
    await db.appointments.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/appointments/{aid}")
async def update_appointment(aid: str, data: AppointmentInput, user: dict = Depends(require_roles(*STAFF))):
    res = await db.appointments.update_one({"id": aid}, {"$set": data.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return await db.appointments.find_one({"id": aid}, {"_id": 0})


@router.post("/appointments/bulk-delete")
async def bulk_delete_appointments(data: IdList, user: dict = Depends(require_roles(*STAFF))):
    docs = await db.appointments.find({"id": {"$in": data.ids}}, {"_id": 0, "id": 1, "created_by_id": 1}).to_list(1000)
    deletable = [d["id"] for d in docs
                 if user["role"] == "admin" or d.get("created_by_id") in (user["id"], None)]
    if deletable:
        await db.appointments.delete_many({"id": {"$in": deletable}})
    return {"deleted": len(deletable), "skipped": len(data.ids) - len(deletable)}


@router.delete("/appointments/{aid}")
async def delete_appointment(aid: str, user: dict = Depends(require_roles(*STAFF))):
    existing = await db.appointments.find_one({"id": aid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if user["role"] != "admin" and existing.get("created_by_id") not in (user["id"], None):
        raise HTTPException(status_code=403, detail="You can only delete appointments you created")
    await db.appointments.delete_one({"id": aid})
    return {"ok": True}
