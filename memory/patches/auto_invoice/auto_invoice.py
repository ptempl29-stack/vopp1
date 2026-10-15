import re
import uuid

from core.db import db, now_iso
from core.audit import log_audit


def _signed_completed(n: dict) -> bool:
    return (n.get("signature") or "").startswith("data:image") and bool(n.get("completed"))


async def _unique_next_number() -> str:
    from routers.billing import _compute_next_number
    return await _compute_next_number()


async def auto_invoice_for_day(patient: dict, notes: list, day: str, user: dict):
    """Create ONE invoice for a patient's service day from the signed, completed progress notes.
    Returns (invoice | None, problems). Never guesses: any missing CPT/price -> no invoice, explained."""
    signed = [n for n in notes if _signed_completed(n)]
    if not signed:
        return None, ["No invoice was created: the progress note for this date is not signed and Completed."]
    if await db.invoices.find_one({"patient_id": patient["id"], "auto_from_note_ids": {"$in": [n["id"] for n in signed]}}):
        return None, ["No invoice was created: an invoice was already generated from this progress note."]
    library = {c["code"].strip().upper(): c for c in await db.cpt_codes.find({}, {"_id": 0}).to_list(1000)}
    items, problems = [], []
    for n in signed:
        codes = [c.strip() for c in re.split(r"[,;\s]+", n.get("cpt_code") or "") if c.strip()]
        if not codes:
            problems.append(f"No invoice was created: the progress note on {day} has no CPT code.")
        for code in codes:
            cpt = library.get(code.upper())
            if not cpt or cpt.get("amount") is None:
                problems.append(f"No invoice was created: CPT {code} is not in the approved CPT list with a rate.")
                continue
            items.append({"cpt_code": cpt["code"], "description": cpt.get("description", ""),
                          "quantity": int(cpt.get("default_units") or 1), "minutes": 0, "amount": float(cpt["amount"])})
    if problems or not items:
        return None, problems or ["No invoice was created: no billable CPT code found."]
    icd = next((n.get("icd10") for n in signed if n.get("icd10")), None)
    provider = next((n.get("attending_provider") for n in signed if n.get("attending_provider")), None)
    for _ in range(5):
        number = await _unique_next_number()
        if not await db.invoices.find_one({"invoice_number": number}):
            break
    doc = {"id": str(uuid.uuid4()), "invoice_number": number, "patient_id": patient["id"],
           "patient_name": f"{patient['first_name']} {patient['last_name']}", "dob": patient.get("dob"),
           "ssn": patient.get("ssn"), "policy_number": patient.get("policy_number"), "gender": patient.get("gender"),
           "service_date": day, "visit_reason": next((n.get("title") for n in signed if n.get("title")), None),
           "icd10": icd, "provider": provider, "attending_provider": provider, "items": items,
           "total": round(sum(i["amount"] * i["quantity"] for i in items), 2), "status": "unpaid",
           "notes": "Auto-generated from the signed progress note by Build Packet — review before billing.",
           "auto_generated": True, "auto_from_note_ids": [n["id"] for n in signed],
           "completed_at": None, "created_at": now_iso(), "created_by": user["name"]}
    await db.invoices.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "invoice", actor=user, resource_id=doc["id"],
                    detail=f"{number} · auto from progress note {day} · ${doc['total']}")
    return doc, []
