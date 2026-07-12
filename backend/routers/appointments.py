import uuid

from fastapi import APIRouter, HTTPException, Depends

from core.db import db, now_iso
from core.security import get_current_user, require_roles
from models.schemas import AppointmentInput

router = APIRouter()


@router.get("/appointments")
async def list_appointments(user: dict = Depends(get_current_user)):
    appts = await db.appointments.find({}, {"_id": 0}).sort("date", 1).to_list(500)
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}" async for p in db.patients.find({}, {"_id": 0})}
    for a in appts:
        a["patient_name"] = patients.get(a["patient_id"], "Unknown")
    return appts


@router.post("/appointments")
async def create_appointment(data: AppointmentInput, user: dict = Depends(require_roles("doctor", "nurse", "receptionist", "psychologist"))):
    doc = data.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso()})
    await db.appointments.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/appointments/{aid}")
async def update_appointment(aid: str, data: AppointmentInput, user: dict = Depends(require_roles("doctor", "nurse", "receptionist", "psychologist"))):
    res = await db.appointments.update_one({"id": aid}, {"$set": data.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return await db.appointments.find_one({"id": aid}, {"_id": 0})


@router.delete("/appointments/{aid}")
async def delete_appointment(aid: str, user: dict = Depends(require_roles("doctor", "nurse", "receptionist", "psychologist"))):
    await db.appointments.delete_one({"id": aid})
    return {"ok": True}
