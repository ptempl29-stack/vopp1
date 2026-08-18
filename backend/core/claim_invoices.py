from collections.abc import Iterable
from typing import Callable, Optional


def service_day(value: object) -> str:
    """Normalize stored ISO dates/timestamps to the day used to relate records."""
    return str(value or "")[:10]


def claim_folder_day(value: object) -> str:
    """Format the selected claim/session date for Patient Folder names."""
    day = service_day(value)
    parts = day.split("-")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        return f"{parts[1]}-{parts[2]}-{parts[0]}"
    return day


def payment_recipient_from_fields(fields: Iterable[tuple[object, object]]) -> Optional[str]:
    """Read a checked Veteran/Provider value from PDF form-field name/value pairs."""
    selected = set()
    for raw_name, raw_value in fields:
        name = str(raw_name or "").lower()
        value = str(raw_value or "").strip().lower()
        if value in ("", "0", "false", "no", "none", "off", "unchecked"):
            continue
        text = f"{name} {value}"
        if "veteran" in text:
            selected.add("veteran")
        if "provider" in text:
            selected.add("provider")
    return selected.pop() if len(selected) == 1 else None


def progress_note_codes(note: Optional[dict]) -> dict:
    """Return only codes actually recorded on a progress note."""
    note = note or {}
    icd10 = str(note.get("icd10") or "").strip() or None
    cpt_code = str(note.get("cpt_code") or "").strip() or None
    return {"icd10": icd10, "cpt_code": cpt_code}


def claim_document_key(item: Optional[dict]) -> Optional[str]:
    """Return a stable key used to remember a user's explicit removal."""
    item = item or {}
    for prefix, field in (("invoice", "invoice_id"), ("note", "note_id"),
                          ("form", "form_id"), ("folder", "folder_item_id"),
                          ("storage", "storage_path")):
        value = item.get(field)
        if value:
            return f"{prefix}:{value}"
    return None


def without_excluded_claim_documents(items: Iterable[dict], excluded_keys: Iterable[str]) -> list[dict]:
    """Keep automatic synchronization from restoring a document the user removed."""
    excluded = set(excluded_keys)
    return [item for item in items if claim_document_key(item) not in excluded]


def best_effort_cleanup(paths: Iterable[str], remover: Callable[[str], object]) -> list[str]:
    """Attempt every storage cleanup and report failures without interrupting deletion."""
    failed = []
    for path in paths:
        try:
            remover(path)
        except Exception:
            failed.append(path)
    return failed


def linked_invoice_id(claim: dict) -> Optional[str]:
    """Return an invoice explicitly linked to a claim packet, if present."""
    if claim.get("source_invoice_id"):
        return claim["source_invoice_id"]
    item = next(
        (item for item in claim.get("items", [])
         if item.get("source") == "invoice" and item.get("invoice_id")),
        None,
    )
    return item.get("invoice_id") if item else None


def related_invoice(claim: dict, invoices: Iterable[dict]) -> Optional[dict]:
    """Choose the explicit invoice, or one with the claim's patient and date."""
    candidates = list(invoices)
    explicit_id = linked_invoice_id(claim)
    if explicit_id:
        explicit = next((invoice for invoice in candidates if invoice.get("id") == explicit_id), None)
        if explicit:
            return explicit

    patient_id = claim.get("patient_id")
    claim_day = service_day(claim.get("claim_number"))
    if not patient_id or not claim_day:
        return None
    return next(
        (invoice for invoice in candidates
         if invoice.get("patient_id") == patient_id
         and service_day(invoice.get("service_date")) == claim_day),
        None,
    )


def invoice_summary(invoice: Optional[dict]) -> Optional[dict]:
    if not invoice:
        return None
    return {
        "invoice_id": invoice.get("id"),
        "invoice_number": invoice.get("invoice_number"),
        "amount_billed": invoice.get("total"),
        "service_date": invoice.get("service_date"),
        "patient_name": invoice.get("patient_name"),
        "icd10": invoice.get("icd10"),
        "provider": invoice.get("provider") or invoice.get("attending_provider"),
        "visit_reason": invoice.get("visit_reason"),
        "items": invoice.get("items") or [],
    }


def unlinked_related_claims(invoice: dict, claims: Iterable[dict]) -> list[dict]:
    """Return claim packets that should receive this invoice automatically."""
    patient_id = invoice.get("patient_id")
    invoice_day = service_day(invoice.get("service_date"))
    if not invoice.get("id") or not patient_id or not invoice_day:
        return []
    return [
        claim for claim in claims
        if claim.get("patient_id") == patient_id
        and service_day(claim.get("claim_number")) == invoice_day
        and not linked_invoice_id(claim)
    ]
