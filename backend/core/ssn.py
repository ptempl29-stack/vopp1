import re

from core.db import db
from core.config import ROLES


def format_ssn(ssn) -> str:
    """Full SSN as XXX-XX-XXXX; other lengths are shown as entered."""
    raw = str(ssn or "").strip()
    digits = re.sub(r"\D", "", raw)
    return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}" if len(digits) == 9 else raw


def mask_ssn(ssn) -> str:
    digits = re.sub(r"\D", "", str(ssn or ""))
    return f"***-**-{digits[-4:]}" if len(digits) >= 4 else ("***" if ssn else ssn)


async def with_patient_ssn(doc: dict) -> dict:
    """Copy of doc whose SSN comes from its own linked patient record (by patient_id);
    falls back to the SSN typed on the document only when that patient has none."""
    pid = doc.get("patient_id")
    p = await db.patients.find_one({"id": pid}, {"_id": 0, "ssn": 1}) if pid else None
    return {**doc, "ssn": (p or {}).get("ssn") or doc.get("ssn")}


async def ssn_full_roles() -> list:
    s = await db.settings.find_one({"key": "ssn_access"}, {"_id": 0})
    return sorted(set((s or {}).get("full_roles", ROLES)) | {"admin"})


async def can_view_full_ssn(user: dict) -> bool:
    return user.get("role") == "admin" or user.get("role") in await ssn_full_roles()


def _mask_tree(obj):
    if isinstance(obj, list):
        return [_mask_tree(x) for x in obj]
    if isinstance(obj, dict):
        return {k: (mask_ssn(v) if k == "ssn" else _mask_tree(v)) for k, v in obj.items()}
    return obj


async def redact_ssn(user: dict, data):
    """Mask every 'ssn' value in an API response for roles without full-SSN access."""
    return data if await can_view_full_ssn(user) else _mask_tree(data)


async def guard_ssn_write(user: dict, doc: dict, existing_ssn=None) -> dict:
    """Roles without full access can't enter or change SSNs: the stored value is kept."""
    if not await can_view_full_ssn(user):
        doc["ssn"] = existing_ssn
    return doc
