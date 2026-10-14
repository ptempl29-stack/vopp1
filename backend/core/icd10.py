"""ICD-10-CM code lookup and display formatting.

Looks up official code descriptions against the NLM Clinical Table Search
Service (clinicaltables.nlm.nih.gov/api/icd10cm), the free public lookup
service the U.S. National Library of Medicine builds directly from the
CMS/CDC ICD-10-CM annual release — the same authoritative source most
clinical software uses for ICD-10-CM autocomplete. Nothing here is a
guessed or hand-typed description.

Every resolved code is cached in Mongo (`icd10_cache`) so a code already
looked up once renders instantly afterward and keeps working even if the
external service is briefly unreachable. A code that can't be resolved
(unknown code, or the lookup service is down) simply renders as the bare
code — it never raises, and it never blocks saving a note or invoice.

This module only ever READS a code and returns a description. It never
writes to a patient, note, invoice, or claim record, and the diagnosis
field stored on those records is untouched: it still holds only the bare
code (e.g. "F43.10"). The "CODE — Description" label is built at
display/render time only, by format_label() / label_for().
"""
import httpx

from core.db import db

NLM_SEARCH_URL = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"
_TIMEOUT = 4.0


def format_label(code: str, description: str) -> str:
    """The one approved display format: 'F43.10 — Post-traumatic stress
    disorder, unspecified'. Falls back to the bare code when no
    description could be resolved, so an unrecognized or legacy code
    never disappears from view."""
    code = (code or "").strip()
    if not code:
        return ""
    return f"{code} — {description}" if description else code


async def _cache_get(code: str):
    doc = await db.icd10_cache.find_one({"code": code}, {"_id": 0})
    return doc["description"] if doc else None


async def _cache_set(code: str, description: str):
    if not code or not description:
        return
    await db.icd10_cache.update_one(
        {"code": code},
        {"$set": {"code": code, "description": description}},
        upsert=True,
    )


async def describe(code: str) -> str:
    """Official description for a single ICD-10-CM code, or '' if it
    can't be resolved. Never raises."""
    code = (code or "").strip().upper()
    if not code:
        return ""
    cached = await _cache_get(code)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(NLM_SEARCH_URL, params={"sf": "code", "terms": code, "maxList": 1})
            r.raise_for_status()
            data = r.json()
        rows = data[3] if len(data) > 3 else []
        for row in rows:
            if row and str(row[0]).upper() == code:
                await _cache_set(code, row[1])
                return row[1]
    except Exception:
        pass
    return ""


async def label_for(code: str) -> str:
    """Convenience: resolve + format in one call. Used right before
    building a PDF, so the PDF draws a pre-formatted label without the
    drawing code itself needing to know about descriptions at all."""
    code = (code or "").strip()
    if not code:
        return ""
    description = await describe(code)
    return format_label(code, description)


async def search(term: str, limit: int = 20):
    """Search ICD-10-CM codes by code prefix OR description keyword.
    Returns [{"code", "description", "label"}, ...], newest/best match
    first, as served by the NLM service. Empty list (never an error) if
    the lookup service is unreachable — callers fall back to free-text
    entry so this never blocks data entry."""
    term = (term or "").strip()
    if not term:
        return []
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(NLM_SEARCH_URL, params={"sf": "code,name", "terms": term, "maxList": limit})
            r.raise_for_status()
            data = r.json()
        rows = data[3] if len(data) > 3 else []
        results = []
        for row in rows:
            if not row or len(row) < 2:
                continue
            code, description = row[0], row[1]
            await _cache_set(code, description)
            results.append({"code": code, "description": description, "label": format_label(code, description)})
        return results
    except Exception:
        return []
