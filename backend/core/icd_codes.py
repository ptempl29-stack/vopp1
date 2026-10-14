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


def split_icd(value) -> list:
    import re
    return [p.strip() for p in re.split(r"[,;\n]+", str(value or "")) if p.strip()]


async def icd_descriptions(value) -> list:
    """[{code, description}] for each code in an ICD-10 field, from the diagnosis library."""
    codes = split_icd(value)
    if not codes:
        return []
    cat = {d["code"].strip().upper(): (d.get("description") or "").strip()
           for d in await db.icd_codes.find({}, {"_id": 0, "code": 1, "description": 1}).to_list(5000)}
    return [{"code": c, "description": cat.get(c.upper(), "")} for c in codes]


async def with_icd_descriptions(doc: dict) -> dict:
    """PDF copy whose icd10 reads 'CODE — description' per line; saved descriptions win over the library."""
    codes = split_icd(doc.get("icd10"))
    if not codes:
        return doc
    saved = {str(d.get("code", "")).upper(): d.get("description") or "" for d in doc.get("icd10_descriptions") or []}
    lib = {d["code"].upper(): d["description"] for d in await icd_descriptions(doc.get("icd10"))}
    lines = []
    for c in codes:
        desc = saved.get(c.upper()) or lib.get(c.upper())
        lines.append(f"{c} — {desc}" if desc else c)
    return {**doc, "icd10": "\n".join(lines)}
