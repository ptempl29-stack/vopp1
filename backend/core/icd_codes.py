"""Per-patient dismissed ICD-10 codes: hide a saved code from the pick-lists
in Invoices and Progress Notes without altering historical records."""
from core.db import db, now_iso


async def dismissed_icd(patient_id: str) -> set:
    if not patient_id:
        return set()
    docs = await db.dismissed_icd_codes.find(
        {"patient_id": patient_id}, {"_id": 0, "code": 1}).to_list(1000)
    return {d["code"] for d in docs}


async def add_dismissed_icd(patient_id: str, code: str, user: dict) -> None:
    await db.dismissed_icd_codes.update_one(
        {"patient_id": patient_id, "code": code},
        {"$setOnInsert": {"patient_id": patient_id, "code": code,
                          "dismissed_by": (user or {}).get("email"), "dismissed_at": now_iso()}},
        upsert=True)


async def remove_dismissed_icd(patient_id: str, code: str) -> None:
    await db.dismissed_icd_codes.delete_one({"patient_id": patient_id, "code": code})
