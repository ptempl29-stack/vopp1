import re

from core.db import db


def format_ssn(ssn) -> str:
    """Full SSN as XXX-XX-XXXX; other lengths are shown as entered."""
    raw = str(ssn or "").strip()
    digits = re.sub(r"\D", "", raw)
    return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}" if len(digits) == 9 else raw


async def with_patient_ssn(doc: dict) -> dict:
    """Copy of doc whose SSN comes from its own linked patient record (by patient_id);
    falls back to the SSN typed on the document only when that patient has none."""
    pid = doc.get("patient_id")
    p = await db.patients.find_one({"id": pid}, {"_id": 0, "ssn": 1}) if pid else None
    return {**doc, "ssn": (p or {}).get("ssn") or doc.get("ssn")}
