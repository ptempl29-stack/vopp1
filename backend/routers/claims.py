import io
import re
import gc
import uuid
import asyncio
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from core.db import db, now_iso, logger
from core.config import APP_NAME, EXT_CONTENT_TYPES
from core.security import require_roles
from core.audit import log_audit
from core.storage import put_object, get_object, delete_object
from core.claim_invoices import (best_effort_cleanup, claim_document_key, invoice_summary,
                                 linked_invoice_id, progress_note_codes, related_invoice,
                                 unlinked_related_claims, claim_folder_day,
                                 without_excluded_claim_documents)
from routers.settings import get_settings_doc
from core.pdf_utils import new_pdf, pdf_bytes, FONT
from core.ssn import format_ssn, with_patient_ssn
from core.icd_codes import with_icd_descriptions

router = APIRouter()


def _invoice_pdf(inv: dict, settings: dict) -> bytes:
    """Saved-invoice layout: letterhead (with RNC), patient/invoice info, six-column items
    table (CPT, Description, Units, Minutes, Unit Price, Fee) and the stored total.
    Full SSN from the invoice's own patient; Minutes is the stored item value, never calculated."""
    import base64
    from io import BytesIO
    from core.folder_filing import disp_date

    settings = settings or {}
    clinic = settings.get("clinic_name") or "Veterans of Puerto Plata"
    GREEN, GREY = (25, 90, 60), (105, 105, 105)
    pdf = new_pdf()
    content_w = pdf.w - pdf.l_margin - pdf.r_margin

    logo = settings.get("logo") or ""
    text_x, y0 = pdf.l_margin, pdf.get_y()
    if logo.startswith("data:image"):
        try:
            pdf.image(BytesIO(base64.b64decode(logo.split(",", 1)[1])), x=pdf.l_margin, y=y0, w=16, h=16)
            text_x = pdf.l_margin + 20
        except Exception as e:
            logger.error(f"invoice pdf logo render failed: {e}")
    pdf.set_xy(text_x, y0)
    pdf.set_font(FONT, "B", 16)
    pdf.cell(content_w - (text_x - pdf.l_margin), 7, clinic[:70], ln=True)
    lines = []
    if settings.get("tagline"):
        lines.append((9, settings["tagline"][:100]))
    if settings.get("rnc"):
        lines.append((9, f"RNC: {settings['rnc']}"))
    contact = [v for v in [settings.get("address"),
               "  ".join(x for x in (settings.get("email"), settings.get("phone")) if x),
               f"WhatsApp: {settings['whatsapp']}" if settings.get("whatsapp") else ""] if v]
    if contact:
        lines.append((8, "   |   ".join(contact)))
    extra = [v for v in [f"Mailing Address: {settings['mailing_address']}" if settings.get("mailing_address") else "",
             f"Primary Insurance: {settings['primary_insurance']}" if settings.get("primary_insurance") else ""] if v]
    if extra:
        lines.append((8, "   |   ".join(extra)))
    pdf.set_text_color(*GREY)
    for size, text in lines:
        pdf.set_x(text_x)
        pdf.set_font(FONT, "", size)
        pdf.multi_cell(content_w - (text_x - pdf.l_margin), 5, text)
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(max(pdf.get_y(), y0 + 18) + 2)
    pdf.set_draw_color(*GREEN)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + content_w, pdf.get_y())
    pdf.ln(5)

    pdf.set_font(FONT, "B", 13)
    pdf.cell(0, 8, f"Invoice {inv.get('invoice_number', '')}", ln=True)
    pdf.ln(2)

    col_gap = 8
    col_w = (content_w - col_gap) / 2
    top_y = pdf.get_y()

    def info_block(x, title, rows):
        pdf.set_xy(x, top_y)
        pdf.set_font(FONT, "B", 8.5)
        pdf.set_text_color(*GREEN)
        pdf.cell(col_w, 5, title.upper(), ln=True)
        pdf.line(x, pdf.get_y(), x + col_w, pdf.get_y())
        pdf.ln(1.5)
        for label, val in rows:
            pdf.set_x(x)
            pdf.set_font(FONT, "B", 8)
            pdf.set_text_color(*GREY)
            pdf.cell(28, 5.5, label)
            pdf.set_font(FONT, "", 8.5)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(col_w - 28, 5.5 if "\n" not in str(val or "") else 4.5, str(val or "-"), align="L")
        return pdf.get_y()

    y_left = info_block(pdf.l_margin, "Patient Information", [
        ("Full Name", inv.get("patient_name")),
        ("DOB", disp_date(inv.get("dob")) if inv.get("dob") else ""),
        ("SSN", format_ssn(inv.get("ssn"))),
        ("Gender", inv.get("gender")),
        ("Policy No.", inv.get("policy_number"))])
    y_right = info_block(pdf.l_margin + col_w + col_gap, "Invoice Information", [
        ("Invoice No.", inv.get("invoice_number")),
        ("Service Date", disp_date(inv.get("service_date")) if inv.get("service_date") else ""),
        ("Status", (inv.get("status") or "").replace("_", " ").title()),
        ("Visit Reason", inv.get("visit_reason")),
        ("ICD-10-CM", inv.get("icd10")),
        ("Provider", inv.get("provider"))])
    pdf.set_y(max(y_left, y_right) + 3)

    cpt_w, desc_w, units_w, min_w, price_w = 22, 58, 18, 20, 28
    fee_w = content_w - (cpt_w + desc_w + units_w + min_w + price_w)
    pdf.set_font(FONT, "B", 8.5)
    pdf.set_fill_color(*GREEN)
    pdf.set_text_color(255, 255, 255)
    for w, label, al in ((cpt_w, "CPT", "L"), (desc_w, "Description", "L"), (units_w, "Units", "R"),
                         (min_w, "Minutes", "R"), (price_w, "Unit Price", "R")):
        pdf.cell(w, 7, label, border=1, align=al, fill=True)
    pdf.cell(fee_w, 7, "Fee", border=1, align="R", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(FONT, "", 8.5)
    for it in inv.get("items", []):
        qty = it.get("quantity", 1) or 0
        unit_price = it.get("amount", 0) or 0
        minutes = it.get("minutes")
        pdf.cell(cpt_w, 7, str(it.get("cpt_code", ""))[:12], border=1)
        pdf.cell(desc_w, 7, str(it.get("description", ""))[:46], border=1)
        pdf.cell(units_w, 7, str(qty), border=1, align="R")
        pdf.cell(min_w, 7, str(minutes) if minutes not in (None, "", 0) else "", border=1, align="R")
        pdf.cell(price_w, 7, f"${unit_price:.2f}", border=1, align="R")
        pdf.cell(fee_w, 7, f"${unit_price * qty:.2f}", border=1, align="R", ln=True)

    pdf.ln(4)
    pdf.set_font(FONT, "B", 9)
    pdf.cell(content_w - 45, 8, "TOTAL", align="R")
    pdf.set_font(FONT, "B", 15)
    pdf.set_text_color(*GREEN)
    pdf.cell(45, 8, f"${inv.get('total', 0):.2f}", align="R", ln=True)
    pdf.set_text_color(0, 0, 0)
    if inv.get("notes"):
        pdf.ln(3)
        pdf.set_font(FONT, "", 9)
        pdf.multi_cell(0, 5.5, f"Notes: {inv['notes']}")
    return pdf_bytes(pdf)

# Explicit CPT timing rules — PENDING CLINIC/FMP CONFIRMATION. Used for review flags only;
# never changes stored units, minutes, prices or invoices.
CPT_TIMING_RULES = {
    "99202": {"rule": "per_visit_time", "min": 15}, "99203": {"rule": "per_visit_time", "min": 30},
    "99213": {"rule": "per_visit_time", "min": 20}, "99214": {"rule": "per_visit_time", "min": 30},
    "90837": {"rule": "per_session_time", "min": 53, "standard_units": 1},
    "99396": {"rule": "untimed"}, "90686": {"rule": "untimed"}, "80053": {"rule": "untimed"},
    "85025": {"rule": "untimed"}, "93000": {"rule": "untimed"}, "36415": {"rule": "untimed"},
}


def cpt_billing_flags(item: dict) -> list:
    code = str(item.get("cpt_code") or "").strip()
    rule = CPT_TIMING_RULES.get(code)
    if not code:
        return []
    if not rule:
        return [f"CPT {code}: no confirmed timing/billing rule on file — review."]
    flags, minutes = [], item.get("minutes")
    if rule["rule"] != "untimed":
        if minutes in (None, "", 0):
            flags.append(f"CPT {code}: timed service has no minutes recorded — review.")
        elif float(minutes) < rule["min"]:
            flags.append(f"CPT {code}: {minutes} min is below the {rule['min']}-minute threshold — review.")
    std = rule.get("standard_units")
    if std and (item.get("quantity") or 1) != std:
        flags.append(f"CPT {code}: billed with {item.get('quantity')} units; standard CPT convention is {std} per session "
                     "— confirm the FMP billing arrangement.")
    return flags


# Default document order for packets built from a date (cover sheet is always generated first).
FMP_DEFAULT_ORDER = {"cover_sheet": -1, "va_disability_letter": 0, "invoice": 1, "progress_note": 2,
                     "provider_exequatur": 3, "provider_diploma": 4}
APPROVAL_REQUIRED = (("cover_sheet", "FMP Claim Cover Sheet"),
                     ("va_disability_letter", "VA Disability Breakdown Letter"), ("invoice", "Invoice"),
                     ("progress_note", "Progress Note"), ("provider_exequatur", "Provider Exequatur"),
                     ("provider_diploma", "Provider Diploma"))


async def _approval_blockers(claim: dict) -> list:
    """Reasons a packet cannot be approved yet (does not block preview/merge)."""
    from core.providers import note_provider_id, note_signer_id
    items = claim.get("items") or []
    cats = {it.get("category") for it in items}
    problems = [f"Missing required document: {label}" for cat, label in APPROVAL_REQUIRED if cat not in cats]
    if sum(1 for it in items if it.get("category") == "cover_sheet") > 1:
        problems.append("More than one FMP Claim Cover Sheet is attached — keep only one.")
    if "va_disability_letter" not in cats and claim.get("patient_id"):
        n_letters = len(await _disability_letter_candidates(claim["patient_id"]))
        if n_letters > 1:
            problems.append(f"{n_letters} possible VA Disability Letters were found in this patient's folder — "
                            "staff must review and attach the correct one.")
    note_ids = [it["note_id"] for it in items if it.get("source") == "note" and it.get("note_id")]
    found = await db.notes.find({"id": {"$in": note_ids}}, {"_id": 0}).to_list(50) if note_ids else []
    if len({n["id"] for n in found}) < len(set(note_ids)):
        problems.append("Attached progress note no longer exists — re-attach.")
    for n in found:
        if not (n.get("signature") or "").startswith("data:image"):
            problems.append("The progress note is not signed by its provider.")
            continue
        if not n.get("completed"):
            problems.append("The progress note is not marked Completed.")
        assigned, signer = await note_provider_id(n), await note_signer_id(n)
        if not assigned:
            problems.append(f"The progress note's attending provider ({n.get('attending_provider') or 'not set'}) "
                            "does not match a clinical provider account — set the attending provider.")
        elif not signer or assigned != signer:
            problems.append(f"The progress note was signed by {n.get('signed_by') or 'an unknown account'}, "
                            f"but it must be signed by its attending provider, {n.get('attending_provider')}.")
    if note_ids and len(note_ids) != len(set(note_ids)):
        problems.append("The same progress note is attached more than once.")
    return problems


CLAIM_STATUSES = {"draft", "submitted", "complete"}
UPLOAD_EXTS = {"pdf", "png", "jpg", "jpeg", "webp", "doc", "docx", "txt", "xls", "xlsx"}
EXTRA_CT = {"xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


# Keyword -> FMP checklist category (matched against the lowercased filename).
_CATEGORY_KEYWORDS = [
    ("provider_diploma", ("diploma", "titulo", "título", "degree")),
    ("provider_exequatur", ("exequatur", "exequátur", "exequator")),
    ("cover_sheet", ("cover", "caratula", "carátula", "7959f-2", "7959f2", "10-7959f-2")),
    ("fmp_registration", ("registration", "registro", "7959f-1", "7959f1", "10-7959f-1", "enroll")),
    ("va_disability_letter", ("disability", "discapacidad", "disabilidad", "rating", "va letter", "va-letter")),
    ("invoice", ("invoice", "factura")),
    ("progress_note", ("progress", "nota de progreso", "progress note", "clinical note")),
]


def _cover_first(items: list) -> list:
    return [i for i in items if i.get("category") == "cover_sheet"] + \
           [i for i in items if i.get("category") != "cover_sheet"]


def _guess_category(filename: str) -> str:
    fn = (filename or "").lower()
    for cat, kws in _CATEGORY_KEYWORDS:
        if any(k in fn for k in kws):
            return cat
    return ""


async def _auto_attach_credentials(items: list, patient_id: str, provider_name: str, provider_id: str = None) -> list:
    """Append provider exequatur/diploma (uploaded once per provider, on the
    provider's user record) and the patient's VA disability letter (found by
    filename in their folder), if not already present in the packet."""
    have = {it.get("category") for it in items if it.get("category")}

    if (provider_name or provider_id) and ("provider_diploma" not in have or "provider_exequatur" not in have):
        from core.providers import resolve_provider_id
        pid_ = provider_id or await resolve_provider_id(provider_name)
        prov = await db.users.find_one({"id": pid_}, {"_id": 0, "diploma_doc": 1, "exequatur_doc": 1}) if pid_ else None
        if prov:
            for kind, cat, label in (("diploma_doc", "provider_diploma", "Provider_Diploma"),
                                     ("exequatur_doc", "provider_exequatur", "Provider_Exequatur")):
                doc = prov.get(kind)
                if doc and cat not in have:
                    items.append({"id": str(uuid.uuid4()), "source": "upload", "form_id": None,
                                 "storage_path": doc["storage_path"],
                                 "filename": doc.get("filename") or f"{label}.pdf",
                                 "content_type": doc.get("content_type", "application/pdf"),
                                 "size": doc.get("size"), "category": cat,
                                 "provider_name": provider_name, "auto_linked": True})
                    have.add(cat)

    if patient_id and "va_disability_letter" not in have:
        candidates = await _disability_letter_candidates(patient_id)
        if len(candidates) != 1:
            logger.warning(f"VA disability letter not auto-attached for patient {patient_id}: {len(candidates)} candidates")
        if len(candidates) == 1:  # ambiguous (>1) is left for staff review, never guessed
            match = candidates[0]
            existing = next((it for it in items if it.get("storage_path") == match["storage_path"]), None)
            if existing:
                existing["category"] = "va_disability_letter"
            else:
                items.append({"id": str(uuid.uuid4()), "source": "upload", "form_id": match.get("form_id"),
                              "folder_item_id": match.get("folder_item_id"),
                              "storage_path": match["storage_path"], "filename": match["filename"],
                              "content_type": match.get("content_type", "application/pdf"),
                              "size": match.get("size"), "category": "va_disability_letter",
                              "auto_linked": True})
    return items


_LETTER_KEYWORDS = ("disability", "discapacidad", "disabilidad", "desglose", "breakdown", "rating",
                    "va letter", "va-letter", "carta va", "carta de la va")


async def _disability_letter_candidates(patient_id: str) -> list:
    """Distinct VA disability letters belonging to this patient only. Explicitly tagged
    documents (category / Disability Breakdown Letter form) win over filename/label guesses."""
    from routers.forms import DISABILITY_LETTER_FORM_TYPE
    explicit, guessed, seen = [], [], set()

    def add(bucket, path, **meta):
        if path and path not in seen:
            seen.add(path)
            bucket.append({"storage_path": path, **meta})

    forms = await db.forms.find({"patient_id": patient_id, "form_type": DISABILITY_LETTER_FORM_TYPE,
                                 "attachment.storage_path": {"$exists": True}}, {"_id": 0}).to_list(50)
    for f in forms:
        att = f["attachment"]
        add(explicit, att["storage_path"], form_id=f["id"], filename=att.get("filename") or "VA_Disability_Letter.pdf",
            content_type=att.get("content_type", "application/pdf"), size=att.get("size"))
    docs = await db.folder_items.find({"patient_id": patient_id}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    for d in docs:
        fn = d.get("filename") or d.get("label") or ""
        if d.get("description") == "Moved from FMP Claim" or fn.startswith("Claim_Packet_"):
            continue
        meta = dict(folder_item_id=d.get("id"), form_id=d.get("form_id"), filename=fn or "VA_Disability_Letter.pdf",
                    content_type=d.get("content_type", "application/pdf"), size=d.get("size"))
        if d.get("category") == "va_disability_letter" or d.get("description") == DISABILITY_LETTER_FORM_TYPE:
            add(explicit, d.get("storage_path"), **meta)
            continue
        text = " ".join(str(d.get(k) or "") for k in ("filename", "label", "description")).lower()
        if (_guess_category(d.get("filename") or "") in ("", "va_disability_letter")
                and _guess_category(d.get("label") or "") in ("", "va_disability_letter")
                and any(k in text for k in _LETTER_KEYWORDS)):
            add(guessed, d.get("storage_path"), **meta)
    return explicit or guessed


class ClaimInput(BaseModel):
    name: str
    patient_id: Optional[str] = None
    claim_number: Optional[str] = None
    status: str = "draft"
    notes: Optional[str] = None
    va_claim_number: Optional[str] = None
    veteran_physical_address: Optional[str] = None
    veteran_mailing_address: Optional[str] = None
    diagnosis_narrative: Optional[str] = None
    payment_to: Optional[str] = None


_COVER_FIELDS = ("va_claim_number", "veteran_physical_address",
                 "veteran_mailing_address", "diagnosis_narrative", "payment_to")


async def _patient_name(pid):
    if not pid:
        return None
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    return f"{p['first_name']} {p['last_name']}" if p else None


def _append_document(writer, data: bytes, filename: str) -> bool:
    """Append a stored PDF or image to a PdfWriter with minimal peak memory.
    Large images are downscaled before embedding to avoid OOM on constrained tiers."""
    from pypdf import PdfReader
    from PIL import Image
    fn = (filename or "").lower()
    if fn.endswith(".pdf"):
        for page in PdfReader(io.BytesIO(data)).pages:
            writer.add_page(page)
        return True
    if fn.rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp"):
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
        MAX_EDGE = 2200  # keeps documents legible while cutting decoded-image RAM
        if max(img.size) > MAX_EDGE:
            img.thumbnail((MAX_EDGE, MAX_EDGE))
        buf = io.BytesIO()
        img.save(buf, format="PDF", resolution=150.0)
        img.close()
        for page in PdfReader(io.BytesIO(buf.getvalue())).pages:
            writer.add_page(page)
        buf.close()
        return True
    return False


def _merge_items_pdf(items) -> bytes:
    from pypdf import PdfWriter
    writer = PdfWriter()
    added = 0
    for item in items:
        try:
            data, _ = get_object(item["storage_path"])
            if _append_document(writer, data, item["filename"]):
                added += 1
            del data
        except Exception as e:
            logger.error(f"merge skip {item.get('filename')}: {e}")
    if added == 0:
        raise HTTPException(status_code=400, detail="No PDF/image documents to merge in this packet")
    out = io.BytesIO()
    writer.write(out)
    writer.close()
    result = out.getvalue()
    out.close()
    gc.collect()
    return result


FMP_CHECKLIST = [
    ("cover_sheet", "FMP Claim Cover Sheet (VA Form 10-7959f-2)"),
    ("invoice", "Itemized Invoice"),
    ("progress_note", "Signed Clinical Progress Note / Initial Evaluation"),
    ("va_disability_letter", "VA Disability Verification Letter"),
    ("provider_exequatur", "Provider Exequatur"),
    ("provider_diploma", "Provider Diploma"),
]


async def _resolve_claim_invoice(claim: dict) -> Optional[dict]:
    """Resolve live invoice values for a claim, regardless of creation order."""
    explicit_id = linked_invoice_id(claim)
    if explicit_id:
        invoice = await db.invoices.find_one({"id": explicit_id}, {"_id": 0})
        if invoice:
            return invoice

    patient_id = claim.get("patient_id")
    claim_number = claim.get("claim_number")
    if not patient_id or not claim_number:
        return None
    invoices = await db.invoices.find(
        {"patient_id": patient_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return related_invoice(claim, invoices)


async def _resolve_claim_note(claim: dict) -> Optional[dict]:
    note_id = claim.get("source_note_id")
    if not note_id:
        item = next((item for item in claim.get("items", [])
                     if item.get("source") == "note" and item.get("note_id")), None)
        note_id = item.get("note_id") if item else None
    if note_id:
        note = await db.notes.find_one({"id": note_id}, {"_id": 0})
        if note:
            return note
    patient_id = claim.get("patient_id")
    claim_day = str(claim.get("claim_number") or "")[:10]
    if not patient_id or not claim_day:
        return None
    notes = await db.notes.find(  # auto-link only signed AND Completed notes
        {"patient_id": patient_id, "completed": True, "signature": {"$nin": [None, ""]}}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return next((note for note in notes
                 if str(note.get("visit_date") or "")[:10] == claim_day), None)


def _form_day(form: dict) -> str:
    responses = form.get("responses") or {}
    for value in (form.get("service_date"), responses.get("service_date"), responses.get("date"),
                  form.get("submitted_at"), form.get("created_at")):
        day = str(value or "")[:10]
        if day:
            return day
    return ""


async def _sync_claim_packet_documents(claim: dict) -> dict:
    """Attach all safely matched patient/date documents to one claim packet."""
    patient_id = claim.get("patient_id")
    claim_day = str(claim.get("claim_number") or "")[:10]
    if not claim.get("id") or not patient_id or not claim_day:
        return claim
    if claim.get("approved") or claim.get("submission_status") == "submitted" or claim.get("status") == "complete":
        return claim  # frozen: approved/submitted/legacy-complete packets keep their historical documents

    original_items = claim.get("items", [])
    excluded_keys = set(claim.get("excluded_document_keys") or [])
    items = [dict(item) for item in without_excluded_claim_documents(original_items, excluded_keys)]
    original_keys = {(item.get("source"), item.get("invoice_id"), item.get("note_id"),
                      item.get("form_id"), item.get("folder_item_id"), item.get("storage_path"))
                     for item in items}
    patient = await db.patients.find_one({"id": patient_id}, {"_id": 0})
    clinic = (await get_settings_doc()).get("clinic_name", "Veterans of Puerto Plata")
    rnc = (await get_settings_doc()).get("rnc", "")
    invoice = await _resolve_claim_invoice(claim)
    note = await _resolve_claim_note(claim)

    if invoice:
        for item in items:
            if item.get("invoice_id") == invoice.get("id"):
                item["invoice_number"] = invoice.get("invoice_number")
                item["amount"] = invoice.get("total")

    invoice_key = claim_document_key({"invoice_id": (invoice or {}).get("id")})
    if (invoice and invoice_key not in excluded_keys
            and not any(item.get("invoice_id") == invoice.get("id") for item in items)):
        try:
            pdf = _invoice_pdf(await with_icd_descriptions(await with_patient_ssn(invoice)), await get_settings_doc())
            path = f"{APP_NAME}/claims/{claim['id']}/{uuid.uuid4()}.pdf"
            stored = put_object(path, pdf, "application/pdf")
            items.append({"id": str(uuid.uuid4()), "source": "invoice", "form_id": None,
                          "invoice_id": invoice["id"], "storage_path": stored["path"],
                          "filename": f"Invoice_{invoice.get('invoice_number') or invoice['id'][:8]}.pdf",
                          "content_type": "application/pdf", "size": stored.get("size"),
                          "category": "invoice", "invoice_number": invoice.get("invoice_number"),
                          "amount": invoice.get("total"), "auto_linked": True})
        except Exception as exc:
            logger.error(f"claim invoice auto-attach failed: {exc}")

    if note:
        codes = progress_note_codes(note)
        for item in items:
            if item.get("note_id") == note.get("id"):
                item.update(codes)

    note_key = claim_document_key({"note_id": (note or {}).get("id")})
    if (note and note_key not in excluded_keys
            and not any(item.get("note_id") == note.get("id") for item in items)):
        try:
            from core.folder_filing import note_pdf, fmt_date
            rendered = {**note,
                        "patient_name": (f"{patient['first_name']} {patient['last_name']}" if patient else ""),
                        "dob": (patient or {}).get("dob"), "ssn": (patient or {}).get("ssn")}
            pdf = note_pdf(await with_icd_descriptions(rendered), clinic, rnc, await get_settings_doc())
            path = f"{APP_NAME}/claims/{claim['id']}/{uuid.uuid4()}.pdf"
            stored = put_object(path, pdf, "application/pdf")
            items.append({"id": str(uuid.uuid4()), "source": "note", "form_id": None,
                          "note_id": note["id"], "storage_path": stored["path"],
                          "filename": f"Progress_Note_{fmt_date(claim_day)}.pdf",
                          "content_type": "application/pdf", "size": stored.get("size"),
                          "category": "progress_note", "auto_linked": True,
                          **progress_note_codes(note)})
        except Exception as exc:
            logger.error(f"claim note auto-attach failed: {exc}")

    forms = await db.forms.find({"patient_id": patient_id}, {"_id": 0}).to_list(500)
    for form in forms:
        form_key = claim_document_key({"form_id": form.get("id")})
        if (form_key in excluded_keys or _form_day(form) != claim_day
                or any(item.get("form_id") == form.get("id") for item in items)):
            continue
        try:
            attachment = form.get("attachment")
            if attachment:
                storage_path = attachment["storage_path"]
                filename = attachment["filename"]
                content_type = attachment.get("content_type", "application/octet-stream")
                size = attachment.get("size")
            else:
                from routers.forms import _form_pdf
                rendered = {**form,
                            "patient_name": (f"{patient['first_name']} {patient['last_name']}" if patient else "")}
                pdf = _form_pdf(rendered, clinic, rnc)
                stored = put_object(f"{APP_NAME}/claims/{claim['id']}/{uuid.uuid4()}.pdf",
                                    pdf, "application/pdf")
                storage_path = stored["path"]
                filename = f"{(form.get('title') or 'Patient_Form').replace('/', '-')[:60]}.pdf"
                content_type = "application/pdf"
                size = stored.get("size")
            items.append({"id": str(uuid.uuid4()), "source": "form", "form_id": form["id"],
                          "storage_path": storage_path, "filename": filename,
                          "content_type": content_type, "size": size,
                          "category": _guess_category(filename), "auto_linked": True})
        except Exception as exc:
            logger.error(f"claim form auto-attach failed: {exc}")

    folder_day = claim_folder_day(claim_day)
    subfolders = await db.folder_subfolders.find({"patient_id": patient_id}, {"_id": 0}).to_list(500)
    matching_subfolder_ids = [folder["id"] for folder in subfolders if folder_day in (folder.get("name") or "")]
    if matching_subfolder_ids:
        folder_items = await db.folder_items.find(
            {"patient_id": patient_id, "subfolder_id": {"$in": matching_subfolder_ids}}, {"_id": 0}
        ).to_list(1000)
        for folder_item in folder_items:
            filename = folder_item.get("filename") or folder_item.get("label") or "Document"
            folder_key = claim_document_key({"folder_item_id": folder_item.get("id")})
            if folder_key in excluded_keys:
                continue
            if folder_item.get("description") == "Moved from FMP Claim" or filename.startswith("Claim_Packet_"):
                continue
            category = folder_item.get("category") or _guess_category(filename)
            if any(item.get("folder_item_id") == folder_item.get("id")
                   or item.get("storage_path") == folder_item.get("storage_path") for item in items):
                continue
            if category and any(item.get("category") == category for item in items):
                continue
            items.append({"id": str(uuid.uuid4()), "source": "upload", "form_id": folder_item.get("form_id"),
                          "folder_item_id": folder_item["id"], "storage_path": folder_item["storage_path"],
                          "filename": filename, "content_type": folder_item.get("content_type", "application/octet-stream"),
                          "size": folder_item.get("size"), "category": category, "auto_linked": True})

    provider_name = ((invoice or {}).get("attending_provider") or (invoice or {}).get("provider")
                     or (note or {}).get("attending_provider") or "")
    items = [item for item in items
             if item.get("category") not in ("provider_diploma", "provider_exequatur")
             or not item.get("provider_name") or item.get("provider_name") == provider_name]
    items = await _auto_attach_credentials(items, patient_id, provider_name)
    items = without_excluded_claim_documents(items, excluded_keys)

    new_keys = {(item.get("source"), item.get("invoice_id"), item.get("note_id"),
                 item.get("form_id"), item.get("folder_item_id"), item.get("storage_path"))
                for item in items}
    updates = {}
    if new_keys != original_keys or items != original_items:
        updates["items"] = items
    if invoice and not linked_invoice_id(claim):
        updates["source_invoice_id"] = invoice["id"]
        updates["invoice_link_source"] = "automatic"
    if note and not claim.get("source_note_id"):
        updates["source_note_id"] = note["id"]
    if updates:
        updates["updated_at"] = now_iso()
        await db.claim_packets.update_one({"id": claim["id"]}, {"$set": updates})
        claim = {**claim, **updates}
    return claim


async def _link_invoice_to_related_claims(invoice: dict) -> int:
    """Persist an automatic invoice link on matching, currently unlinked claims."""
    patient_id = invoice.get("patient_id")
    service_date = str(invoice.get("service_date") or "")[:10]
    if not invoice.get("id") or not patient_id or not service_date:
        return 0

    claims = await db.claim_packets.find(
        {"patient_id": patient_id}, {"_id": 0}
    ).to_list(500)
    linked = 0
    for claim in unlinked_related_claims(invoice, claims):
        result = await db.claim_packets.update_one(
            {"id": claim["id"], "source_invoice_id": {"$in": [None, ""]}},
            {"$set": {"source_invoice_id": invoice["id"],
                      "invoice_link_source": "automatic", "updated_at": now_iso()}},
        )
        linked += result.modified_count
        await _sync_claim_packet_documents({**claim, "source_invoice_id": invoice["id"]})
    await _sync_matching_claims(patient_id, service_date)
    return linked


async def _sync_matching_claims(patient_id: str, service_date: object) -> int:
    """Synchronize all claims for one patient and exact service/claim day."""
    day = str(service_date or "")[:10]
    if not patient_id or not day:
        return 0
    claims = await db.claim_packets.find({"patient_id": patient_id}, {"_id": 0}).to_list(500)
    matches = [claim for claim in claims if str(claim.get("claim_number") or "")[:10] == day]
    for claim in matches:
        await _sync_claim_packet_documents(claim)
    return len(matches)


async def _sync_folder_item_claims(folder_item: dict) -> int:
    """Synchronize a folder document only to claims matching its dated folder."""
    subfolder_id = folder_item.get("subfolder_id")
    patient_id = folder_item.get("patient_id")
    if not patient_id or not subfolder_id:
        return 0
    subfolder = await db.folder_subfolders.find_one({"id": subfolder_id, "patient_id": patient_id}, {"_id": 0})
    match = re.search(r"(\d{2})-(\d{2})-(\d{4})", (subfolder or {}).get("name", ""))
    if not match:
        return 0
    return await _sync_matching_claims(patient_id, f"{match.group(3)}-{match.group(1)}-{match.group(2)}")


async def _sync_claims_for_provider(provider_name: str) -> int:
    if not provider_name:
        return 0
    claims = await db.claim_packets.find({}, {"_id": 0}).to_list(500)
    matched = 0
    for claim in claims:
        invoice = await _resolve_claim_invoice(claim)
        note = await _resolve_claim_note(claim)
        claim_provider = ((invoice or {}).get("attending_provider") or (invoice or {}).get("provider")
                          or (note or {}).get("attending_provider") or "")
        if claim_provider == provider_name:
            await _sync_claim_packet_documents(claim)
            matched += 1
    return matched


async def _claim_with_invoice_summary(claim: dict) -> dict:
    result = dict(claim)
    invoice = await _resolve_claim_invoice(claim)
    if invoice and claim.get("id") and not linked_invoice_id(claim):
        await db.claim_packets.update_one(
            {"id": claim["id"], "source_invoice_id": {"$in": [None, ""]}},
            {"$set": {"source_invoice_id": invoice["id"],
                      "invoice_link_source": "automatic", "updated_at": now_iso()}},
        )
        result["source_invoice_id"] = invoice["id"]
        result["invoice_link_source"] = "automatic"
    result["invoice_summary"] = invoice_summary(invoice)
    return result


def _norm_date(v) -> str:
    return str(v or "").strip()[:10]


async def _validate_packet(claim: dict) -> dict:
    """Load this packet's documents and run the mismatch/completeness checks."""
    items = claim.get("items") or []
    patient = await db.patients.find_one({"id": claim.get("patient_id")}, {"_id": 0}) if claim.get("patient_id") else None
    note_ids = [it.get("note_id") for it in items if it.get("source") == "note" and it.get("note_id")]
    inv_ids = [it.get("invoice_id") for it in items if it.get("source") == "invoice" and it.get("invoice_id")]
    notes = await db.notes.find({"id": {"$in": note_ids}}, {"_id": 0}).to_list(100) if note_ids else []
    invoices = await db.invoices.find({"id": {"$in": inv_ids}}, {"_id": 0}).to_list(100) if inv_ids else []
    dup_exists = False
    dos = _norm_date(claim.get("claim_number"))
    if claim.get("patient_id") and dos:
        dup = await db.claim_packets.find_one(
            {"patient_id": claim["patient_id"], "claim_number": dos, "id": {"$ne": claim.get("id")}},
            {"_id": 0, "id": 1})
        dup_exists = bool(dup)
    return _compute_validation(claim, patient, notes, invoices, dup_exists)


def _compute_validation(claim: dict, patient: Optional[dict], notes: list,
                        invoices: list, dup_exists: bool) -> dict:
    """Pure mismatch + completeness checks. Returns {status, issues, fix}."""
    from core.folder_filing import disp_date
    issues, seen = [], set()

    def add(level, msg):
        k = (level, msg)
        if k not in seen:
            seen.add(k)
            issues.append({"level": level, "message": msg})

    dos = _norm_date(claim.get("claim_number"))
    pname = f"{patient['first_name']} {patient['last_name']}".strip().lower() if patient else ""

    for n in notes:
        nd = _norm_date(n.get("visit_date"))
        if nd and dos and nd != dos:
            add("blocked", f"Date mismatch: progress note ({disp_date(nd)}) does not match the claim date ({disp_date(dos)}).")
    for inv in invoices:
        idt = _norm_date(inv.get("service_date"))
        if idt and dos and idt != dos:
            add("blocked", f"Date mismatch: invoice ({disp_date(idt)}) does not match the claim date ({disp_date(dos)}).")
    for n in notes:
        nd = _norm_date(n.get("visit_date"))
        for inv in invoices:
            idt = _norm_date(inv.get("service_date"))
            if nd and idt and nd != idt:
                add("blocked", f"Date mismatch: progress note ({disp_date(nd)}) and invoice ({disp_date(idt)}) are for different dates.")

    if patient:
        for inv in invoices:
            inm = (inv.get("patient_name") or "").strip().lower()
            if inm and inm != pname:
                add("blocked", "Patient name on an invoice does not match the patient on this claim.")
        for n in notes:
            nnm = (n.get("patient_name") or "").strip().lower()
            if nnm and nnm != pname:
                add("warning", "Patient name on a progress note differs from the patient record.")

    for n in notes:
        if not (n.get("signature") or "").startswith("data:image"):
            add("warning", "A progress note in this packet is not signed.")
        if not n.get("icd10"):
            add("warning", "A progress note has no diagnosis (ICD-10) code.")
    for inv in invoices:
        if not inv.get("items"):
            add("blocked", "An invoice in this packet has no service line items.")
        elif not any(it.get("cpt_code") for it in inv.get("items", [])):
            add("warning", "An invoice has no procedure (CPT) code.")

    if not notes and not invoices:
        add("warning", "This packet has no progress note or invoice attached.")

    for n in notes:
        if n.get("version_count") and not n.get("signature"):
            add("blocked", "A linked progress note was revised and must be re-signed by its provider.")
        elif n.get("version_count") and n.get("billing_review_status") != "approved":
            add("warning", "A linked progress note was revised and needs a new billing approval.")
        if claim.get("approved") and n.get("revised_at") and n["revised_at"] > (claim.get("approved_at") or ""):
            add("warning", "A linked progress note was revised after this packet was approved.")
    for inv in invoices:
        for it in inv.get("items", []):
            for msg in cpt_billing_flags(it):
                add("warning", msg)

    if dup_exists:
        add("warning", "Another claim packet already exists for this patient and date of service.")

    # One-click fix: when every document agrees on a single date that differs
    # from the claim date, the claim date is simply out of sync — offer to apply it.
    fix = None
    doc_dates = {d for d in (_norm_date(n.get("visit_date")) for n in notes) if d}
    doc_dates |= {d for d in (_norm_date(inv.get("service_date")) for inv in invoices) if d}
    if len(doc_dates) == 1:
        only = next(iter(doc_dates))
        if dos and only != dos:
            fix = {"type": "set_claim_date", "date": only}

    status = ("blocked" if any(i["level"] == "blocked" for i in issues)
              else "review" if any(i["level"] == "warning" for i in issues)
              else "ready")
    return {"status": status, "issues": issues, "fix": fix}


async def _attach_validation_bulk(packets: list) -> list:
    """Compute validation for a list of packets with batched lookups (no N+1)."""
    from collections import Counter
    note_ids, inv_ids, pat_ids = set(), set(), set()
    for c in packets:
        for it in c.get("items") or []:
            if it.get("source") == "note" and it.get("note_id"):
                note_ids.add(it["note_id"])
            if it.get("source") == "invoice" and it.get("invoice_id"):
                inv_ids.add(it["invoice_id"])
        if c.get("patient_id"):
            pat_ids.add(c["patient_id"])
    notes_map = {n["id"]: n for n in await db.notes.find({"id": {"$in": list(note_ids)}}, {"_id": 0}).to_list(5000)} if note_ids else {}
    inv_map = {i["id"]: i for i in await db.invoices.find({"id": {"$in": list(inv_ids)}}, {"_id": 0}).to_list(5000)} if inv_ids else {}
    pat_map = {p["id"]: p for p in await db.patients.find({"id": {"$in": list(pat_ids)}}, {"_id": 0}).to_list(5000)} if pat_ids else {}
    key_counts = Counter((c.get("patient_id"), _norm_date(c.get("claim_number")))
                         for c in packets if c.get("patient_id") and _norm_date(c.get("claim_number")))
    for c in packets:
        items = c.get("items") or []
        notes = [notes_map[it["note_id"]] for it in items
                 if it.get("source") == "note" and it.get("note_id") in notes_map]
        invoices = [inv_map[it["invoice_id"]] for it in items
                    if it.get("source") == "invoice" and it.get("invoice_id") in inv_map]
        patient = pat_map.get(c.get("patient_id"))
        key = (c.get("patient_id"), _norm_date(c.get("claim_number")))
        dup_exists = bool(c.get("patient_id")) and bool(_norm_date(c.get("claim_number"))) and key_counts.get(key, 0) > 1
        c["validation"] = _compute_validation(c, patient, notes, invoices, dup_exists)
    return packets


async def _assert_not_blocked(claim: dict):
    v = await _validate_packet(claim)
    if v["status"] == "blocked":
        msgs = "; ".join(i["message"] for i in v["issues"] if i["level"] == "blocked")
        raise HTTPException(status_code=400,
            detail=f"Resolve the blocking issue(s) before finalizing this packet: {msgs}")


async def _claim_response(claim_id: str) -> Optional[dict]:
    claim = await db.claim_packets.find_one({"id": claim_id}, {"_id": 0})
    if not claim:
        return None
    claim = await _sync_claim_packet_documents(claim)
    result = await _claim_with_invoice_summary(claim)
    result["validation"] = await _validate_packet(result)
    result["approval_blockers"] = await _approval_blockers(result)
    result["ready_to_approve"] = await _ready_to_approve(result, result["approval_blockers"])
    return result


async def _ready_to_approve(c: dict, blockers: list = None) -> bool:
    if c.get("approved") or c.get("status") == "complete" or (c.get("validation") or {}).get("status") == "blocked":
        return False
    cats = {it.get("category") for it in c.get("items") or []}
    if any(cat not in cats for cat, _ in APPROVAL_REQUIRED):
        return False
    return not (blockers if blockers is not None else await _approval_blockers(c))


async def _build_packet_pdf(c) -> bytes:
    """FMP packet PDF: the attached documents merged, staff-uploaded cover sheet first."""
    from pypdf import PdfWriter
    c = await _sync_claim_packet_documents(c)
    writer = PdfWriter()
    for item in _cover_first(c.get("items", [])):
        try:
            data, _ = get_object(item["storage_path"])
            _append_document(writer, data, item["filename"])
            del data
        except Exception as e:
            logger.error(f"packet merge skip {item.get('filename')}: {e}")
    if not writer.pages:
        raise HTTPException(status_code=400, detail="No PDF/image documents to merge in this packet")
    out = io.BytesIO()
    writer.write(out)
    writer.close()
    result = out.getvalue()
    out.close()
    gc.collect()
    return result


@router.get("/claims")
async def list_claims(user: dict = Depends(require_roles("admin"))):
    packets = await db.claim_packets.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    packets = await _attach_validation_bulk(packets)
    for p in packets:
        p["ready_to_approve"] = await _ready_to_approve(p)
    await log_audit("view", "claim", actor=user, detail=f"list ({len(packets)})")
    return packets


@router.post("/claims")
async def create_claim(data: ClaimInput, user: dict = Depends(require_roles("admin"))):
    if data.status not in CLAIM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    if data.status == "complete":
        raise HTTPException(status_code=400, detail="A packet becomes Complete only through explicit administrator approval")
    await _refuse_duplicate_packet(data.patient_id, data.claim_number)
    doc = {"id": str(uuid.uuid4()), "name": data.name, "patient_id": data.patient_id,
           "patient_name": await _patient_name(data.patient_id), "claim_number": data.claim_number,
           "status": data.status, "notes": data.notes, "items": [],
           **{f: getattr(data, f) for f in _COVER_FIELDS},
           "created_at": now_iso(), "created_by": user["name"]}
    await db.claim_packets.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "claim", actor=user, resource_id=doc["id"], detail=data.name)
    return await _claim_response(doc["id"])


class ClaimFromDateInput(BaseModel):
    patient_id: str
    date: str


def _same_day(val, date_str) -> bool:
    return bool(val) and str(val)[:10] == str(date_str)[:10]


async def _refuse_duplicate_packet(patient_id, claim_date, exclude_id=None):
    day = _norm_date(claim_date)
    if not patient_id or not day:
        return
    q = {"patient_id": patient_id}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    async for c in db.claim_packets.find(q, {"_id": 0, "id": 1, "name": 1, "claim_number": 1}):
        if _norm_date(c.get("claim_number")) == day:
            raise HTTPException(status_code=409, detail=f"A claim packet already exists for this patient and date "
                                                        f"of service ({c.get('name') or c['id']}).")


async def _qualifying_patient_ids(day: str) -> set:
    """Strict server-side evidence of a visit on `day`: a COMPLETED appointment, or a
    progress note that is signed AND marked Completed. Scheduled/cancelled visits don't count."""
    ids = set()
    async for a in db.appointments.find({"status": "completed"}, {"_id": 0, "patient_id": 1, "date": 1}):
        if a.get("patient_id") and _same_day(a.get("date"), day):
            ids.add(a["patient_id"])
    async for n in db.notes.find({"completed": True, "signature": {"$nin": [None, ""]}},
                                 {"_id": 0, "patient_id": 1, "visit_date": 1}):
        if n.get("patient_id") and _same_day(n.get("visit_date"), day):
            ids.add(n["patient_id"])
    return ids


@router.get("/claims/options/patients-by-date")
async def patients_with_visit_on_date(date: str, user: dict = Depends(require_roles("admin"))):
    ids = await _qualifying_patient_ids(date[:10])
    if not ids:
        return []
    pts = await db.patients.find({"id": {"$in": list(ids)}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).to_list(1000)
    pts.sort(key=lambda p: (p["first_name"].lower(), p["last_name"].lower()))
    return [{"id": p["id"], "name": f"{p['first_name']} {p['last_name']}"} for p in pts]


class TrackingInput(BaseModel):
    submission_status: Optional[str] = None
    payment_status: Optional[str] = None


SUBMISSION_STATUSES = {"not_submitted", "submitted"}
PAYMENT_STATUSES = {"unpaid", "paid", "denied"}


async def _approve_one(c: dict, user: dict):
    await _assert_not_blocked(c)
    blockers = await _approval_blockers(c)
    if blockers:
        raise HTTPException(status_code=400, detail="Cannot approve: " + " ".join(blockers))
    await db.claim_packets.update_one({"id": c["id"]}, {"$set": {
        "approved": True, "approved_by": user["name"], "approved_by_id": user["id"],
        "approved_at": now_iso(), "status": "complete", "updated_at": now_iso()}})


@router.post("/claims/{cid}/approve")
async def approve_claim(cid: str, user: dict = Depends(require_roles("admin"))):
    """The ONLY way a packet becomes Complete: explicit administrator approval."""
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    await _approve_one(c, user)
    await log_audit("update", "claim", actor=user, resource_id=cid, detail="approved packet · Complete")
    return await _claim_response(cid)


class BulkApproveInput(BaseModel):
    ids: List[str]


@router.post("/claims/bulk-approve")
async def bulk_approve_claims(data: BulkApproveInput, user: dict = Depends(require_roles("admin"))):
    """Approve several ready packets; each is re-validated individually and skipped with a reason if not ready."""
    approved, skipped = [], []
    for cid in dict.fromkeys(data.ids[:200]):
        c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
        name = (c or {}).get("name") or cid
        if not c:
            skipped.append({"id": cid, "name": name, "reason": "Claim packet not found"})
            continue
        if c.get("approved") or c.get("status") == "complete":
            skipped.append({"id": cid, "name": name, "reason": "Already approved"})
            continue
        if c.get("cover_review"):
            skipped.append({"id": cid, "name": name,
                            "reason": "Cover-sheet date must be confirmed — approve this packet individually"})
            continue
        try:
            await _approve_one(c, user)
        except HTTPException as e:
            skipped.append({"id": cid, "name": name, "reason": str(e.detail)})
            continue
        await log_audit("update", "claim", actor=user, resource_id=cid, detail="approved packet · Complete (bulk)")
        approved.append({"id": cid, "name": name})
    return {"approved": approved, "skipped": skipped}


@router.put("/claims/{cid}/tracking")
async def update_tracking(cid: str, data: TrackingInput, user: dict = Depends(require_roles("admin"))):
    """Submission and payment are tracked separately from approval."""
    upd = {}
    if data.submission_status is not None:
        if data.submission_status not in SUBMISSION_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid submission status")
        upd.update({"submission_status": data.submission_status,
                    "submitted_at": now_iso() if data.submission_status == "submitted" else None,
                    "submitted_by": user["name"] if data.submission_status == "submitted" else None})
    if data.payment_status is not None:
        if data.payment_status not in PAYMENT_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid payment status")
        upd["payment_status"] = data.payment_status
    if not upd:
        raise HTTPException(status_code=400, detail="Nothing to update")
    res = await db.claim_packets.update_one({"id": cid}, {"$set": {**upd, "updated_at": now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"tracking {upd}")
    return await _claim_response(cid)


@router.post("/claims/from-date")
async def claim_from_date(data: ClaimFromDateInput, user: dict = Depends(require_roles("admin"))):
    from core.folder_filing import note_pdf
    p = await db.patients.find_one({"id": data.patient_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    pname = f"{p['first_name']} {p['last_name']}"
    d = data.date[:10]
    if data.patient_id not in await _qualifying_patient_ids(d):
        raise HTTPException(status_code=400, detail="This patient has no completed appointment or signed, completed "
                                                    "progress note on that date of service")
    await _refuse_duplicate_packet(data.patient_id, d)

    invs = await db.invoices.find({"patient_id": data.patient_id}, {"_id": 0}).to_list(500)
    invs = [i for i in invs if _same_day(i.get("service_date"), d)]
    notes = await db.notes.find({"patient_id": data.patient_id}, {"_id": 0}).to_list(500)
    notes = [n for n in notes if _same_day(n.get("visit_date"), d)
             and n.get("completed") and (n.get("signature") or "").startswith("data:image")]

    if not invs and not notes:
        raise HTTPException(status_code=404, detail="No invoice or progress note found for that patient on that date")

    clinic = (await get_settings_doc()).get("clinic_name", "Veterans of Puerto Plata")
    rnc = (await get_settings_doc()).get("rnc", "")
    m = d.split("-")
    disp = f"{m[1]}/{m[2]}/{m[0]}" if len(m) == 3 else d
    packet_name = f"{pname} {disp} FMP Claim"

    items = []
    for inv in invs:
        try:
            pdf = _invoice_pdf(await with_icd_descriptions(await with_patient_ssn(inv)), await get_settings_doc())
        except Exception as e:
            logger.error(f"from-date invoice pdf failed: {e}")
            continue
        fname = f"Invoice_{inv.get('invoice_number', inv['id'][:8])}.pdf"
        path = f"{APP_NAME}/claims/from-date/{uuid.uuid4()}.pdf"
        try:
            result = put_object(path, pdf, "application/pdf")
        except Exception as e:
            logger.error(f"from-date invoice storage failed: {e}")
            continue
        items.append({"id": str(uuid.uuid4()), "source": "invoice", "form_id": None,
                      "invoice_id": inv["id"], "storage_path": result["path"], "filename": fname,
                      "content_type": "application/pdf", "size": result.get("size"), "category": "invoice",
                      "invoice_number": inv.get("invoice_number"), "amount": inv.get("total")})

    for n in notes:
        note = {**n, "patient_name": pname, "dob": p.get("dob"), "ssn": p.get("ssn")}
        try:
            pdf = note_pdf(await with_icd_descriptions(note), clinic, rnc, await get_settings_doc())
        except Exception as e:
            logger.error(f"from-date note pdf failed: {e}")
            continue
        fname = f"Progress_Note_{disp.replace('/', '-')}.pdf"
        path = f"{APP_NAME}/claims/from-date/{uuid.uuid4()}.pdf"
        try:
            result = put_object(path, pdf, "application/pdf")
        except Exception as e:
            logger.error(f"from-date note storage failed: {e}")
            continue
        items.append({"id": str(uuid.uuid4()), "source": "note", "form_id": None, "note_id": n["id"],
                      "storage_path": result["path"], "filename": fname,
                      "content_type": "application/pdf", "size": result.get("size"), "category": "progress_note",
                      **progress_note_codes(n)})

    provider_name = next((n.get("attending_provider") for n in notes if n.get("attending_provider")), None) \
        or next((i.get("attending_provider") or i.get("provider") for i in invs if i.get("attending_provider") or i.get("provider")), None)
    from core.providers import note_provider_id
    provider_id = next((pid_ for pid_ in [await note_provider_id(n) for n in notes] if pid_), None)
    items = await _auto_attach_credentials(items, data.patient_id, provider_name, provider_id)
    items.sort(key=lambda it: FMP_DEFAULT_ORDER.get(it.get("category"), len(FMP_DEFAULT_ORDER)))

    doc = {"id": str(uuid.uuid4()), "name": packet_name, "patient_id": data.patient_id,
           "patient_name": pname, "claim_number": d, "status": "draft", "notes": None,
           "items": items, "created_at": now_iso(), "created_by": user["name"]}
    await db.claim_packets.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "claim", actor=user, resource_id=doc["id"],
                    detail=f"from-date {pname} {d} ({len(items)} items)")
    return await _claim_response(doc["id"])


class FixDateInput(BaseModel):
    date: Optional[str] = None


@router.post("/claims/{cid}/fix-date")
async def fix_claim_date(cid: str, data: FixDateInput, user: dict = Depends(require_roles("admin"))):
    from core.folder_filing import disp_date
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    v = await _validate_packet(c)
    target = _norm_date(data.date) or (v.get("fix") or {}).get("date")
    if not target:
        raise HTTPException(status_code=400, detail="No matching document date is available to apply.")
    updates = {"claim_number": target, "updated_at": now_iso()}
    if c.get("patient_id"):
        p = await db.patients.find_one({"id": c["patient_id"]}, {"_id": 0})
        if p:
            updates["name"] = f"{p['first_name']} {p['last_name']} {disp_date(target)} FMP Claim"
    await db.claim_packets.update_one({"id": cid}, {"$set": updates})
    await log_audit("update", "claim", actor=user, resource_id=cid,
                    detail=f"fix claim date -> {target}")
    return await _claim_response(cid)


@router.get("/claims/{cid}")
async def get_claim(cid: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    return await _claim_response(cid)


@router.put("/claims/{cid}")
async def update_claim(cid: str, data: ClaimInput, user: dict = Depends(require_roles("admin"))):
    if data.status not in CLAIM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    current = await db.claim_packets.find_one({"id": cid}, {"_id": 0, "status": 1})
    if current and data.status == "complete" and current.get("status") != "complete":
        raise HTTPException(status_code=400, detail="Use Approve — a packet becomes Complete only through explicit administrator approval")
    await _refuse_duplicate_packet(data.patient_id, data.claim_number, exclude_id=cid)
    updates = {"name": data.name, "patient_id": data.patient_id,
               "patient_name": await _patient_name(data.patient_id), "claim_number": data.claim_number,
               "status": data.status, "notes": data.notes,
               **{f: getattr(data, f) for f in _COVER_FIELDS},
               "updated_at": now_iso()}
    res = await db.claim_packets.update_one({"id": cid}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=data.name)
    return await _claim_response(cid)


@router.delete("/claims/{cid}")
async def delete_claim(cid: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    cleanup_paths = [it["storage_path"] for it in c.get("items", [])
                     if it.get("source") in ("upload", "invoice", "note")
                     and it.get("storage_path")]
    await db.claim_packets.delete_one({"id": cid})
    cleanup_failures = best_effort_cleanup(cleanup_paths, delete_object)
    if cleanup_failures:
        logger.error(f"claim {cid} deleted with {len(cleanup_failures)} storage cleanup failure(s)")
    await log_audit("delete", "claim", actor=user, resource_id=cid,
                    detail=f"cleanup_pending={len(cleanup_failures)}")
    return {"ok": True, "cleanup_pending": len(cleanup_failures)}


@router.post("/claims/{cid}/attach-form")
async def attach_form(cid: str, payload: dict, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    form = await db.forms.find_one({"id": payload.get("form_id")})
    if not form or not form.get("attachment"):
        raise HTTPException(status_code=400, detail="Form has no attached document")
    if any(it.get("form_id") == form["id"] for it in (c.get("items") or [])):
        raise HTTPException(status_code=400, detail="This form is already in the packet.")
    att = form["attachment"]
    item = {"id": str(uuid.uuid4()), "source": "form", "form_id": form["id"],
            "storage_path": att["storage_path"], "filename": att["filename"],
            "content_type": att.get("content_type", "application/octet-stream"), "size": att.get("size"),
            "category": _guess_category(att["filename"])}
    await db.claim_packets.update_one(
        {"id": cid}, {"$push": {"items": item},
                      "$pull": {"excluded_document_keys": claim_document_key(item)},
                      "$set": {"updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"attach form {att['filename']}")
    return await _claim_response(cid)


@router.post("/claims/{cid}/upload")
async def upload_to_claim(cid: str, file: UploadFile = File(...), category: str = Form(""),
                          user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    is_cover = category == "cover_sheet"
    if is_cover and (c.get("approved") or c.get("submission_status") == "submitted" or c.get("status") == "complete"):
        raise HTTPException(status_code=400, detail="This packet is approved/submitted; its cover sheet cannot be changed")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    if ext not in UPLOAD_EXTS:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    safe_ct = EXT_CONTENT_TYPES.get(ext) or EXTRA_CT.get(ext, "application/octet-stream")
    payload = await file.read()
    if len(payload) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 15MB)")
    path = f"{APP_NAME}/claims/{cid}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, payload, safe_ct)
    except Exception as e:
        logger.error(f"claim upload failed: {e}")
        raise HTTPException(status_code=502, detail="File storage failed")
    item = {"id": str(uuid.uuid4()), "source": "upload", "form_id": None,
            "storage_path": result["path"], "filename": file.filename, "content_type": safe_ct,
            "size": result.get("size"), "category": "cover_sheet" if is_cover else _guess_category(file.filename)}
    if is_cover:  # one cover sheet per packet; the replaced file stays in storage; the scan is never modified
        others = [i for i in c.get("items", []) if i.get("category") != "cover_sheet"]
        await db.claim_packets.update_one({"id": cid}, {"$set": {"items": [item] + others, "updated_at": now_iso()}})
    else:
        await db.claim_packets.update_one(
            {"id": cid}, {"$push": {"items": item}, "$set": {"updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid,
                    detail=f"upload {'cover sheet ' if is_cover else ''}{file.filename}")
    return await _claim_response(cid)


@router.get("/claims/options/forms")
async def attachable_forms(user: dict = Depends(require_roles("admin"))):
    forms = await db.forms.find({"attachment": {"$ne": None}}, {"_id": 0}).sort("created_at", -1).to_list(500)
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}" async for p in db.patients.find({}, {"_id": 0})}
    return [{"id": f["id"], "title": f.get("title"), "form_type": f.get("form_type"),
             "filename": f["attachment"].get("filename"),
             "patient_name": patients.get(f.get("patient_id"), "-")} for f in forms]


@router.get("/claims/options/invoices")
async def attachable_invoices(user: dict = Depends(require_roles("admin"))):
    invoices = await db.invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [{"id": i["id"], "invoice_number": i.get("invoice_number"),
             "patient_name": i.get("patient_name") or "-", "total": i.get("total", 0),
             "status": i.get("status"), "service_date": i.get("service_date")} for i in invoices]


@router.get("/claims/options/notes")
async def attachable_notes(user: dict = Depends(require_roles("admin"))):
    notes = await db.notes.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}" async for p in db.patients.find({}, {"_id": 0})}
    out = []
    for n in notes:
        out.append({"id": n["id"],
                    "patient_name": patients.get(n.get("patient_id")) or n.get("patient_name") or "-",
                    "date": n.get("visit_date") or (n.get("created_at") or "")[:10],
                    "note_type": n.get("note_type"), "reason": n.get("reason_for_visit"),
                    **progress_note_codes(n)})
    return out


@router.get("/claims/options/patients")
async def attachable_patients(user: dict = Depends(require_roles("admin"))):
    pts = await db.patients.find({}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).to_list(1000)
    return [{"id": p["id"], "name": f"{p['first_name']} {p['last_name']}"} for p in pts]


@router.post("/claims/{cid}/attach-invoice")
async def attach_invoice(cid: str, payload: dict, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    inv = await db.invoices.find_one({"id": payload.get("invoice_id")}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if any(it.get("invoice_id") == inv["id"] for it in (c.get("items") or [])):
        raise HTTPException(status_code=400, detail="This invoice is already in the packet.")
    clinic = (await get_settings_doc()).get("clinic_name", "Veterans of Puerto Plata")
    rnc = (await get_settings_doc()).get("rnc", "")
    try:
        pdf_bytes = _invoice_pdf(await with_icd_descriptions(await with_patient_ssn(inv)), await get_settings_doc())
    except Exception as e:
        logger.error(f"invoice pdf failed: {e}")
        raise HTTPException(status_code=500, detail="Could not render invoice PDF")
    fname = f"Invoice_{inv.get('invoice_number', inv['id'][:8])}.pdf"
    path = f"{APP_NAME}/claims/{cid}/{uuid.uuid4()}.pdf"
    try:
        result = put_object(path, pdf_bytes, "application/pdf")
    except Exception as e:
        logger.error(f"invoice storage failed: {e}")
        raise HTTPException(status_code=502, detail="File storage failed")
    item = {"id": str(uuid.uuid4()), "source": "invoice", "form_id": None, "invoice_id": inv["id"],
            "storage_path": result["path"], "filename": fname, "content_type": "application/pdf",
            "size": result.get("size"), "category": "invoice",
            "invoice_number": inv.get("invoice_number"), "amount": inv.get("total")}
    await db.claim_packets.update_one(
        {"id": cid},
        {"$push": {"items": item},
         "$pull": {"excluded_document_keys": claim_document_key(item)},
         "$set": {"source_invoice_id": inv["id"], "invoice_link_source": "manual",
                  "updated_at": now_iso()}},
    )
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"attach invoice {inv.get('invoice_number')}")
    return await _claim_response(cid)


@router.post("/claims/{cid}/attach-note")
async def attach_note(cid: str, payload: dict, user: dict = Depends(require_roles("admin"))):
    from core.folder_filing import note_pdf, disp_date
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    n = await db.notes.find_one({"id": payload.get("note_id")}, {"_id": 0})
    if not n:
        raise HTTPException(status_code=404, detail="Note not found")
    if any(it.get("note_id") == n["id"] for it in (c.get("items") or [])):
        raise HTTPException(status_code=400, detail="This progress note is already in the packet.")
    p = await db.patients.find_one({"id": n.get("patient_id")}, {"_id": 0}) if n.get("patient_id") else None
    pname = (f"{p['first_name']} {p['last_name']}" if p else n.get("patient_name")) or ""
    note = {**n, "patient_name": pname, "dob": (p or {}).get("dob") or n.get("dob"), "ssn": (p or {}).get("ssn")}
    clinic = (await get_settings_doc()).get("clinic_name", "Veterans of Puerto Plata")
    rnc = (await get_settings_doc()).get("rnc", "")
    try:
        pdf = note_pdf(await with_icd_descriptions(note), clinic, rnc, await get_settings_doc())
    except Exception as e:
        logger.error(f"note pdf failed: {e}")
        raise HTTPException(status_code=500, detail="Could not render note PDF")
    vd = n.get("visit_date") or (n.get("created_at") or "")[:10]
    fname = f"Progress_Note_{disp_date(vd).replace('/', '-')}.pdf" if vd else "Progress_Note.pdf"
    path = f"{APP_NAME}/claims/{cid}/{uuid.uuid4()}.pdf"
    try:
        result = put_object(path, pdf, "application/pdf")
    except Exception as e:
        logger.error(f"note storage failed: {e}")
        raise HTTPException(status_code=502, detail="File storage failed")
    item = {"id": str(uuid.uuid4()), "source": "note", "form_id": None, "note_id": n["id"],
            "storage_path": result["path"], "filename": fname, "content_type": "application/pdf",
            "size": result.get("size"), "category": "progress_note", **progress_note_codes(n)}
    await db.claim_packets.update_one(
        {"id": cid}, {"$push": {"items": item},
                      "$pull": {"excluded_document_keys": claim_document_key(item)},
                      "$set": {"source_note_id": n["id"], "updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"attach note {fname}")
    return await _claim_response(cid)


@router.delete("/claims/{cid}/items/{item_id}")
async def remove_item(cid: str, item_id: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    item = next((candidate for candidate in c.get("items", [])
                 if candidate.get("id") == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Claim packet item not found")
    document_key = claim_document_key(item)
    update = {"$pull": {"items": {"id": item_id}}, "$set": {"updated_at": now_iso()}}
    if document_key:
        update["$addToSet"] = {"excluded_document_keys": document_key}
    await db.claim_packets.update_one({"id": cid}, update)
    cleanup_paths = [item["storage_path"]] if (
        item.get("source") in ("upload", "invoice", "note") and item.get("storage_path")) else []
    cleanup_failures = best_effort_cleanup(cleanup_paths, delete_object)
    if cleanup_failures:
        logger.error(f"claim {cid} item {item_id} removed with storage cleanup pending")
    result = await _claim_response(cid)
    result["cleanup_pending"] = len(cleanup_failures)
    return result


@router.get("/claims/{cid}/items/{item_id}/download")
async def download_item(cid: str, item_id: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    item = next((i for i in c.get("items", []) if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    data, _ = get_object(item["storage_path"])
    fname = item["filename"].replace('"', "").replace("\n", "").replace("\r", "")
    return Response(content=data, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-Content-Type-Options": "nosniff"})


@router.get("/claims/{cid}/merged")
async def merged_pdf(cid: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    await _assert_not_blocked(c)
    pdf = await _build_packet_pdf(c)
    await log_audit("view", "claim", actor=user, resource_id=cid, detail="merged PDF downloaded")
    fname = (c.get("name") or "claim_packet").replace('"', "").replace(" ", "_")[:60]
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'})


_BUILD_SEM = asyncio.Semaphore(1)
_bg_tasks = set()


async def _run_merge_job(cid: str, job_id: str):
    async with _BUILD_SEM:  # serialize heavy builds so concurrent packets can't stack memory
        await db.claim_pdf_jobs.update_one({"id": job_id}, {"$set": {"status": "running", "updated_at": now_iso()}})
        try:
            c = await db.claim_packets.find_one({"id": cid})
            pdf = await _build_packet_pdf(c)
            key = f"{APP_NAME}/claim_jobs/{cid}/{job_id}.pdf"
            stored = put_object(key, pdf, "application/pdf")
            key = stored.get("path") or key
            await db.claim_pdf_jobs.update_one({"id": job_id},
                {"$set": {"status": "done", "storage_path": key, "updated_at": now_iso()}})
        except Exception as e:
            logger.exception("merge job failed")
            await db.claim_pdf_jobs.update_one({"id": job_id},
                {"$set": {"status": "error", "error": str(e)[:300], "updated_at": now_iso()}})


@router.post("/claims/{cid}/merged/async")
async def start_merge_job(cid: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    await _assert_not_blocked(c)
    job_id = str(uuid.uuid4())
    fname = (c.get("name") or "claim_packet").replace('"', "").replace(" ", "_")[:60] + ".pdf"
    await db.claim_pdf_jobs.insert_one({"id": job_id, "claim_id": cid, "status": "queued",
        "filename": fname, "created_at": now_iso(), "updated_at": now_iso(), "requested_by": user.get("email")})
    task = asyncio.create_task(_run_merge_job(cid, job_id))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return {"job_id": job_id, "status": "queued"}


@router.get("/claims/{cid}/jobs/{job_id}")
async def merge_job_status(cid: str, job_id: str, user: dict = Depends(require_roles("admin"))):
    j = await db.claim_pdf_jobs.find_one({"id": job_id, "claim_id": cid}, {"_id": 0})
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": j["status"], "ready": j["status"] == "done", "error": j.get("error"), "filename": j.get("filename")}


@router.get("/claims/{cid}/jobs/{job_id}/download")
async def merge_job_download(cid: str, job_id: str, user: dict = Depends(require_roles("admin"))):
    j = await db.claim_pdf_jobs.find_one({"id": job_id, "claim_id": cid}, {"_id": 0})
    if not j or j.get("status") != "done" or not j.get("storage_path"):
        raise HTTPException(status_code=409, detail="Packet is not ready")
    data, _ = get_object(j["storage_path"])
    return StreamingResponse(io.BytesIO(data), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{j.get("filename") or "claim_packet.pdf"}"'})


class ItemRename(BaseModel):
    filename: Optional[str] = None
    category: Optional[str] = None


@router.put("/claims/{cid}/items/{item_id}")
async def rename_item(cid: str, item_id: str, data: ItemRename, user: dict = Depends(require_roles("admin"))):
    sets = {"updated_at": now_iso()}
    if data.filename is not None:
        name = data.filename.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name is required")
        sets["items.$.filename"] = name[:120]
    if data.category is not None:
        sets["items.$.category"] = data.category.strip()[:40]
    res = await db.claim_packets.update_one(
        {"id": cid, "items.id": item_id}, {"$set": sets})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    await log_audit("update", "claim", actor=user, resource_id=cid, detail="edit item")
    return await _claim_response(cid)


class ItemOrder(BaseModel):
    ids: list


@router.put("/claims/{cid}/items-order")
async def reorder_items(cid: str, data: ItemOrder, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    items = c.get("items", [])
    by_id = {i["id"]: i for i in items}
    ordered = [by_id[i] for i in data.ids if i in by_id]
    ordered += [i for i in items if i["id"] not in set(data.ids)]
    ordered = _cover_first(ordered)
    await db.claim_packets.update_one({"id": cid}, {"$set": {"items": ordered, "updated_at": now_iso()}})
    return await _claim_response(cid)


@router.post("/claims/{cid}/items/{item_id}/to-folder")
async def item_to_folder(cid: str, item_id: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    pid = c.get("patient_id")
    if not pid:
        raise HTTPException(status_code=400, detail="Claim packet has no linked patient")
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    item = next((i for i in c.get("items", []) if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    try:
        data, _ = get_object(item["storage_path"])
    except Exception as e:
        logger.error(f"item to-folder read failed: {e}")
        raise HTTPException(status_code=502, detail="Could not read document")
    from core.folder_filing import _ensure_subfolder, fmt_date
    ds = fmt_date(c.get("claim_number")) if c.get("claim_number") else None
    from datetime import datetime, timezone
    ds = ds or datetime.now(timezone.utc).strftime("%m-%d-%Y")
    sub_name = f"{p['first_name']} {ds} FMP Claim"
    sid = await _ensure_subfolder(pid, sub_name, user)
    ext = item["filename"].rsplit(".", 1)[-1].lower() if "." in item["filename"] else "pdf"
    path = f"{APP_NAME}/folders/{pid}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, data, item.get("content_type", "application/pdf"))
    except Exception as e:
        logger.error(f"item to-folder store failed: {e}")
        raise HTTPException(status_code=502, detail="File storage failed")
    doc = {"id": str(uuid.uuid4()), "patient_id": pid, "subfolder_id": sid,
           "source": "upload", "form_id": None, "storage_path": result["path"],
           "filename": item["filename"][:120], "label": item["filename"][:120],
           "description": "Moved from FMP Claim", "content_type": item.get("content_type", "application/pdf"),
           "size": result.get("size"), "created_at": now_iso(),
           "created_by": user.get("name"), "created_by_id": user.get("id")}
    await db.folder_items.insert_one(doc)
    await log_audit("create", "folder", actor=user, resource_id=pid, detail=f"moved claim item to folder")
    return {"ok": True, "patient_name": f"{p['first_name']} {p['last_name']}", "subfolder": sub_name}


class SendPacket(BaseModel):
    to: str


@router.post("/claims/{cid}/send-email")
async def send_packet_email(cid: str, data: SendPacket, user: dict = Depends(require_roles("admin"))):
    from core.email_utils import send_email, email_configured
    to = (data.to or "").strip()
    if not to:
        raise HTTPException(status_code=400, detail="Recipient email is required")
    if not email_configured():
        raise HTTPException(status_code=400, detail="Email is not configured on the server")
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    pdf = await _build_packet_pdf(c)
    fname = (c.get("name") or "FMP_Claim").replace('"', "").replace(" ", "_")[:60] + ".pdf"
    ok = send_email(to, f"{c.get('name') or 'FMP Claim'}",
                    f"Attached is the merged claim packet: {c.get('name') or 'FMP Claim'}.",
                    attachments=[{"filename": fname, "content": pdf, "content_type": "application/pdf"}])
    if not ok:
        raise HTTPException(status_code=502, detail="Send failed — check the sender domain and recipient address")
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"emailed packet to {to}")
    return {"ok": True, "to": to}


@router.post("/claims/{cid}/to-folder")
async def claim_to_folder(cid: str, user: dict = Depends(require_roles("admin"))):
    from core.folder_filing import file_pdf_into_folder
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    await _assert_not_blocked(c)
    pid = c.get("patient_id")
    if not pid:
        raise HTTPException(status_code=400, detail="Claim packet has no linked patient")
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    pdf = await _build_packet_pdf(c)
    claim_date = str(c.get("claim_number") or "")[:10]
    ds = claim_folder_day(claim_date)
    if not ds:
        raise HTTPException(status_code=400, detail="Claim packet has no visit/session date")
    name = (c.get("name") or "Claim Packet")[:40]
    item = await file_pdf_into_folder(pid, p["first_name"], pdf,
                                      f"{name} {ds}", f"Claim_Packet_{ds}.pdf", user,
                                      date_str=claim_date)
    if not item:
        raise HTTPException(status_code=502, detail="Could not file PDF")
    await db.folder_items.update_one({"id": item["id"]}, {"$set": {"source": "claim_packet", "claim_packet_id": cid}})
    await log_audit("create", "folder", actor=user, resource_id=pid, detail=f"auto-filed claim {cid}")
    return {"ok": True, "patient_name": f"{p['first_name']} {p['last_name']}"}
