import io
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from core.db import db, now_iso, logger
from core.config import APP_NAME, EXT_CONTENT_TYPES
from core.security import require_roles
from core.audit import log_audit
from core.storage import put_object, get_object, delete_object
from routers.settings import get_settings_doc
from core.pdf_utils import new_pdf, pdf_bytes, FONT

router = APIRouter()


def _invoice_pdf(inv: dict, settings: dict) -> bytes:
    """Render an invoice exactly as it appears in the saved-invoice view:
    same letterhead/logo, same patient & invoice info, same 6-column items
    table (CPT, Description, Units, Minutes, Unit Price, Fee), same total."""
    import base64
    from io import BytesIO
    from core.folder_filing import disp_date

    settings = settings or {}
    clinic = settings.get("clinic_name") or "Veterans of Puerto Plata"
    GREEN = (25, 90, 60)
    GREY = (105, 105, 105)

    pdf = new_pdf()
    content_w = pdf.w - pdf.l_margin - pdf.r_margin

    # ---------------- Letterhead (logo + clinic info) ----------------
    logo = settings.get("logo") or ""
    text_x = pdf.l_margin
    y0 = pdf.get_y()
    if logo.startswith("data:image"):
        try:
            img = BytesIO(base64.b64decode(logo.split(",", 1)[1]))
            pdf.image(img, x=pdf.l_margin, y=y0, w=16, h=16)
            text_x = pdf.l_margin + 20
        except Exception as e:
            logger.error(f"invoice pdf logo render failed: {e}")
            text_x = pdf.l_margin
    pdf.set_xy(text_x, y0)
    pdf.set_font(FONT, "B", 16)
    pdf.cell(content_w - (text_x - pdf.l_margin), 7, clinic[:70], ln=True)
    if settings.get("tagline"):
        pdf.set_x(text_x)
        pdf.set_font(FONT, "", 9)
        pdf.set_text_color(*GREY)
        pdf.cell(0, 5, settings["tagline"][:100], ln=True)
    contact = [v for v in [
        settings.get("address"), settings.get("phone"),
        f"WhatsApp: {settings['whatsapp']}" if settings.get("whatsapp") else "",
        settings.get("email")] if v]
    if contact:
        pdf.set_x(text_x)
        pdf.set_font(FONT, "", 8)
        pdf.set_text_color(*GREY)
        pdf.cell(0, 5, "   |   ".join(contact)[:160], ln=True)
    extra = [v for v in [
        f"Mailing Address: {settings['mailing_address']}" if settings.get("mailing_address") else "",
        f"Primary Insurance: {settings['primary_insurance']}" if settings.get("primary_insurance") else ""] if v]
    if extra:
        pdf.set_x(text_x)
        pdf.cell(0, 5, "   |   ".join(extra)[:160], ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(max(pdf.get_y(), y0 + 18) + 2)
    pdf.set_draw_color(*GREEN)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + content_w, pdf.get_y())
    pdf.ln(5)

    # ---------------- Invoice # / service date ----------------
    pdf.set_font(FONT, "B", 13)
    pdf.cell(0, 8, f"Invoice {inv.get('invoice_number', '')}", ln=True)
    pdf.set_font(FONT, "", 9)
    pdf.set_text_color(*GREY)
    pdf.cell(0, 5, disp_date(inv.get("service_date")) if inv.get("service_date") else "", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # ---------------- Patient Information / Invoice Information ----------------
    col_gap = 8
    col_w = (content_w - col_gap) / 2
    left_x = pdf.l_margin
    right_x = pdf.l_margin + col_w + col_gap
    top_y = pdf.get_y()

    def info_block(x, title, rows):
        pdf.set_xy(x, top_y)
        pdf.set_font(FONT, "B", 8.5)
        pdf.set_text_color(*GREEN)
        pdf.cell(col_w, 5, title.upper(), ln=True)
        pdf.set_draw_color(*GREEN)
        pdf.line(x, pdf.get_y(), x + col_w, pdf.get_y())
        pdf.ln(1.5)
        for label, val in rows:
            pdf.set_x(x)
            pdf.set_font(FONT, "B", 8)
            pdf.set_text_color(*GREY)
            pdf.cell(28, 5.5, label)
            pdf.set_font(FONT, "", 8.5)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(col_w - 28, 5.5, str(val or "-")[:60], ln=True)
        return pdf.get_y()

    left_rows = [
        ("Full Name", inv.get("patient_name")),
        ("DOB", disp_date(inv.get("dob")) if inv.get("dob") else ""),
        ("SSN", inv.get("ssn")),
        ("Gender", inv.get("gender")),
        ("Policy No.", inv.get("policy_number")),
    ]
    right_rows = [
        ("Invoice No.", inv.get("invoice_number")),
        ("Service Date", disp_date(inv.get("service_date")) if inv.get("service_date") else ""),
        ("Completed", disp_date(inv.get("completed_at")) if inv.get("completed_at") else ""),
        ("Status", (inv.get("status") or "").replace("_", " ").title()),
        ("Visit Reason", inv.get("visit_reason")),
        ("ICD-10-CM", inv.get("icd10")),
        ("Provider", inv.get("provider")),
    ]
    y_left = info_block(left_x, "Patient Information", left_rows)
    y_right = info_block(right_x, "Invoice Information", right_rows)
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(max(y_left, y_right) + 3)

    # ---------------- Items table: CPT | Description | Units | Minutes | Unit Price | Fee ----------------
    cpt_w, desc_w, units_w, min_w, price_w = 22, 58, 18, 20, 28
    fee_w = content_w - (cpt_w + desc_w + units_w + min_w + price_w)

    pdf.set_font(FONT, "B", 8.5)
    pdf.set_fill_color(*GREEN)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(cpt_w, 7, "CPT", border=1, fill=True)
    pdf.cell(desc_w, 7, "Description", border=1, fill=True)
    pdf.cell(units_w, 7, "Units", border=1, align="R", fill=True)
    pdf.cell(min_w, 7, "Minutes", border=1, align="R", fill=True)
    pdf.cell(price_w, 7, "Unit Price", border=1, align="R", fill=True)
    pdf.cell(fee_w, 7, "Fee", border=1, align="R", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(FONT, "", 8.5)
    for it in inv.get("items", []):
        qty = it.get("quantity", 1) or 0
        unit_price = it.get("amount", 0) or 0
        fee = unit_price * qty
        pdf.cell(cpt_w, 7, str(it.get("cpt_code", ""))[:12], border=1)
        pdf.cell(desc_w, 7, str(it.get("description", ""))[:46], border=1)
        pdf.cell(units_w, 7, str(qty), border=1, align="R")
        pdf.cell(min_w, 7, str(qty * 15), border=1, align="R")
        pdf.cell(price_w, 7, f"${unit_price:.2f}", border=1, align="R")
        pdf.cell(fee_w, 7, f"${fee:.2f}", border=1, align="R", ln=True)

    # ---------------- Total (unchanged: stored invoice total, not recomputed) ----------------
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


def _guess_category(filename: str) -> str:
    fn = (filename or "").lower()
    for cat, kws in _CATEGORY_KEYWORDS:
        if any(k in fn for k in kws):
            return cat
    return ""


async def _auto_attach_credentials(items: list, patient_id: str, provider_name: str) -> list:
    """Append provider exequatur/diploma (uploaded once per provider, on the
    provider's user record) and the patient's VA disability letter (found by
    filename in their folder), if not already present in the packet."""
    have = {it.get("category") for it in items if it.get("category")}

    if provider_name and ("provider_diploma" not in have or "provider_exequatur" not in have):
        prov = await db.users.find_one({"name": provider_name}, {"_id": 0, "diploma_doc": 1, "exequatur_doc": 1})
        if prov:
            for kind, cat, label in (("diploma_doc", "provider_diploma", "Provider_Diploma"),
                                     ("exequatur_doc", "provider_exequatur", "Provider_Exequatur")):
                doc = prov.get(kind)
                if doc and cat not in have:
                    items.append({"id": str(uuid.uuid4()), "source": "upload", "form_id": None,
                                 "storage_path": doc["storage_path"],
                                 "filename": doc.get("filename") or f"{label}.pdf",
                                 "content_type": doc.get("content_type", "application/pdf"),
                                 "size": doc.get("size"), "category": cat})
                    have.add(cat)

    if patient_id and "va_disability_letter" not in have:
        docs = await db.folder_items.find({"patient_id": patient_id}, {"_id": 0}) \
            .sort("created_at", -1).to_list(200)
        match = next((d for d in docs if (d.get("category") or _guess_category(d.get("filename") or d.get("label") or "")) == "va_disability_letter"), None)
        if match:
            items.append({"id": str(uuid.uuid4()), "source": "upload", "form_id": None,
                         "storage_path": match["storage_path"],
                         "filename": match.get("filename") or match.get("label") or "VA_Disability_Letter.pdf",
                         "content_type": match.get("content_type", "application/pdf"),
                         "size": match.get("size"), "category": "va_disability_letter"})
    return items


def _packet_categories(items: list) -> set:
    """Checklist categories satisfied by the current item list. 'invoice' and
    'progress_note' are inferred from an item's source (attach-invoice /
    attach-note items don't carry an explicit category); everything else
    (uploads, auto-attached credentials/disability letter) uses its own
    'category' field."""
    return {_item_category(it) for it in items if _item_category(it)}


async def _derive_provider_name(items: list) -> Optional[str]:
    """Same priority as the from-date bulk flow: attending provider on an
    attached note first, then the provider on an attached invoice."""
    for it in items:
        if it.get("source") == "note" and it.get("note_id"):
            n = await db.notes.find_one({"id": it["note_id"]}, {"_id": 0, "attending_provider": 1})
            if n and n.get("attending_provider"):
                return n["attending_provider"]
    for it in items:
        if it.get("source") == "invoice" and it.get("invoice_id"):
            inv = await db.invoices.find_one({"id": it["invoice_id"]}, {"_id": 0, "attending_provider": 1, "provider": 1})
            if inv and (inv.get("attending_provider") or inv.get("provider")):
                return inv.get("attending_provider") or inv.get("provider")
    return None


async def _credential_warnings(patient_id: Optional[str], provider_name: Optional[str], cats: set) -> list:
    """Plain-language warnings for FMP-required documents still missing or
    unmatched after auto-attach: the veteran's VA disability letter, and the
    assigned provider's diploma/exequatur. `cats` is the packet's current
    checklist-category set (after auto-attach has already run)."""
    warnings = []
    if not patient_id:
        warnings.append("No patient linked to this claim — the VA disability letter can't be looked up.")
    elif "va_disability_letter" not in cats:
        warnings.append("VA Disability Verification Letter not found in the patient's documents.")
    if not provider_name:
        warnings.append("No provider could be determined for this claim — "
                        "provider diploma/exequatur can't be auto-attached yet.")
    else:
        prov = await db.users.find_one({"name": provider_name}, {"_id": 0, "diploma_doc": 1, "exequatur_doc": 1})
        if prov is None:
            warnings.append(f"No staff account matches provider name \"{provider_name}\" exactly — "
                            "credentials could not be matched (check for a typo or name mismatch).")
        else:
            if "provider_diploma" not in cats:
                warnings.append(f"No diploma on file for {provider_name}.")
            if "provider_exequatur" not in cats:
                warnings.append(f"No exequatur on file for {provider_name}.")
    return warnings


# Fixed order the merged packet's documents are assembled in, after the
# auto-generated summary + checklist pages. Anything not in this list (e.g.
# an extra manually-attached file) keeps its original relative position at
# the end, so nothing is ever silently dropped from the merge.
_MERGE_ORDER = ["cover_sheet", "va_disability_letter", "invoice", "progress_note",
                "provider_exequatur", "provider_diploma"]


def _item_category(item: dict) -> str:
    cat = item.get("category")
    if cat:
        return cat
    if item.get("source") == "invoice":
        return "invoice"
    if item.get("source") == "note":
        return "progress_note"
    return ""


def _sorted_for_merge(items: list) -> list:
    def key(item):
        cat = _item_category(item)
        try:
            return _MERGE_ORDER.index(cat)
        except ValueError:
            return len(_MERGE_ORDER)
    return sorted(items, key=key)  # stable: ties keep their original relative order


async def _sync_credentials_and_checklist(c: dict) -> tuple:
    """Auto-attach provider credentials + the veteran's VA disability letter
    (persisting any change), then report checklist status and plain-language
    warnings for anything still missing or that couldn't be matched."""
    items = c.get("items", [])
    provider_name = await _derive_provider_name(items)
    before_ids = {it["id"] for it in items}
    items = await _auto_attach_credentials(items, c.get("patient_id"), provider_name)
    if {it["id"] for it in items} != before_ids:
        await db.claim_packets.update_one({"id": c["id"]}, {"$set": {"items": items, "updated_at": now_iso()}})

    cats = _packet_categories(items)
    checklist = [{"category": cat, "label": label, "present": cat in cats} for cat, label in FMP_CHECKLIST]

    warnings = []
    if "invoice" not in cats:
        warnings.append("No itemized invoice attached yet.")
    if "progress_note" not in cats:
        warnings.append("No signed clinical progress note attached yet.")
    warnings += await _credential_warnings(c.get("patient_id"), provider_name, cats)
    return items, checklist, warnings


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
    payment_to: Optional[str] = "provider"


_COVER_FIELDS = ("va_claim_number", "veteran_physical_address",
                 "veteran_mailing_address", "diagnosis_narrative", "payment_to")


async def _patient_name(pid):
    if not pid:
        return None
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    return f"{p['first_name']} {p['last_name']}" if p else None


def _merge_items_pdf(items) -> bytes:
    from pypdf import PdfWriter, PdfReader
    from PIL import Image
    writer = PdfWriter()
    added = 0
    for item in items:
        try:
            data, _ = get_object(item["storage_path"])
            fn = item["filename"].lower()
            if fn.endswith(".pdf"):
                for page in PdfReader(io.BytesIO(data)).pages:
                    writer.add_page(page)
                added += 1
            elif fn.rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp"):
                img = Image.open(io.BytesIO(data)).convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="PDF")
                for page in PdfReader(io.BytesIO(buf.getvalue())).pages:
                    writer.add_page(page)
                added += 1
        except Exception as e:
            logger.error(f"merge skip {item.get('filename')}: {e}")
    if added == 0:
        raise HTTPException(status_code=400, detail="No PDF/image documents to merge in this packet")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


FMP_CHECKLIST = [
    ("cover_sheet", "FMP Claim Cover Sheet (VA Form 10-7959f-2)"),
    ("invoice", "Itemized Invoice"),
    ("progress_note", "Signed Clinical Progress Note / Initial Evaluation"),
    ("va_disability_letter", "VA Disability Verification Letter"),
    ("provider_exequatur", "Provider Exequatur"),
    ("provider_diploma", "Provider Diploma"),
]


async def _build_packet_pdf(c) -> bytes:
    """Build the full FMP packet PDF: auto-generated Summary cover + Checklist pages,
    followed by every attached document (merged)."""
    from pypdf import PdfWriter, PdfReader
    from PIL import Image
    from core.pdf_utils import new_pdf, pdf_bytes, FONT
    from core.folder_filing import fmt_date, disp_date

    settings = await get_settings_doc()
    clinic = settings.get("clinic_name", "Veterans of Puerto Plata")
    clinic_addr = settings.get("address", "")
    items = c.get("items", [])

    p = await db.patients.find_one({"id": c.get("patient_id")}, {"_id": 0}) if c.get("patient_id") else None
    vet_name = c.get("patient_name") or (f"{p['first_name']} {p['last_name']}" if p else "")
    dob = (p or {}).get("dob", "")
    ssn = (p or {}).get("ssn", "")

    inv = None
    inv_item = next((i for i in items if i.get("source") == "invoice" and i.get("invoice_id")), None)
    if inv_item:
        inv = await db.invoices.find_one({"id": inv_item["invoice_id"]}, {"_id": 0})
    note = None
    note_item = next((i for i in items if i.get("source") == "note" and i.get("note_id")), None)
    if note_item:
        note = await db.notes.find_one({"id": note_item["note_id"]}, {"_id": 0})

    provider = (inv or {}).get("attending_provider") or (note or {}).get("attending_provider") or ""
    icd = (inv or {}).get("icd10") or (note or {}).get("icd10") or ""
    diagnosis = c.get("diagnosis_narrative") or icd
    cpt_desc = ""
    if inv and inv.get("items"):
        it0 = inv["items"][0]
        cpt_desc = f"{it0.get('cpt_code', '')} - {it0.get('description', '')}".strip(" -")
    elif note:
        cpt_desc = note.get("cpt_code", "") or ""
    inv_no = (inv or {}).get("invoice_number", "")
    amount = (inv or {}).get("total")
    svc_date = disp_date(c.get("claim_number")) or disp_date((inv or {}).get("service_date")) or ""
    pay = "Provider payment requested - Provider box on VA Form 10-7959f-2" \
        if (c.get("payment_to") or "provider") == "provider" else "Veteran payment requested"

    # ================= Professional cover + checklist =================
    GREEN = (25, 90, 60)
    GREEN_LT = (232, 243, 237)
    TAN_LT = (247, 242, 232)
    INK = (38, 38, 38)
    GREY = (105, 105, 105)

    pdf = new_pdf()
    content_w = pdf.w - pdf.l_margin - pdf.r_margin

    def band(title, subtitle=None):
        y0 = pdf.get_y()
        pdf.set_fill_color(*GREEN)
        pdf.rect(pdf.l_margin, y0, content_w, 20, style="F")
        pdf.set_xy(pdf.l_margin + 4, y0 + 3.5)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font(FONT, "B", 9)
        pdf.cell(content_w - 8, 4.5, (clinic or "").upper()[:80], ln=True)
        pdf.set_x(pdf.l_margin + 4)
        pdf.set_font(FONT, "B", 14)
        pdf.cell(content_w - 8, 8, title, ln=True)
        pdf.set_y(y0 + 20)
        if subtitle:
            pdf.set_x(pdf.l_margin)
            pdf.set_fill_color(*TAN_LT)
            pdf.set_text_color(*GREY)
            pdf.set_font(FONT, "", 8.5)
            pdf.cell(content_w, 7, "  " + subtitle, ln=True, fill=True)
        pdf.set_text_color(*INK)
        pdf.ln(5)

    def section_title(txt):
        pdf.set_x(pdf.l_margin)
        pdf.set_font(FONT, "B", 10.5)
        pdf.set_text_color(*GREEN)
        pdf.cell(0, 7, txt, ln=True)
        y = pdf.get_y()
        pdf.set_draw_color(*GREEN)
        pdf.set_line_width(0.4)
        pdf.line(pdf.l_margin, y, pdf.l_margin + content_w, y)
        pdf.set_text_color(*INK)
        pdf.ln(2)

    lw, lh = 58, 6
    vw = content_w - lw

    def prow(label, val, idx):
        val = str(val or "-")
        pdf.set_font(FONT, "", 9)
        n = max(1, len(pdf.multi_cell(vw - 4, lh, val, dry_run=True, output="LINES")))
        rh = n * lh + 2
        y0 = pdf.get_y()
        if y0 + rh > pdf.h - pdf.b_margin:
            pdf.add_page()
            y0 = pdf.get_y()
        pdf.set_fill_color(*(GREEN_LT if idx % 2 == 0 else (255, 255, 255)))
        pdf.rect(pdf.l_margin, y0, content_w, rh, style="F")
        pdf.set_xy(pdf.l_margin + 2, y0 + 1)
        pdf.set_font(FONT, "B", 8.5)
        pdf.set_text_color(*GREY)
        pdf.multi_cell(lw - 2, lh, label)
        pdf.set_xy(pdf.l_margin + lw + 2, y0 + 1)
        pdf.set_font(FONT, "", 9)
        pdf.set_text_color(*INK)
        pdf.multi_cell(vw - 4, lh, val)
        pdf.set_y(y0 + rh)

    band("Foreign Medical Program - Fully Developed Claim",
         f"Claim Packet  ·  {vet_name or 'Veteran'}  ·  {svc_date or ''}")

    section_title("Claim Summary")
    rows = [
        ("Veteran", vet_name),
        ("Date of Birth", disp_date(dob) if dob else ""),
        ("SSN / VA Claim File No.", f"{ssn or '-'}  /  {c.get('va_claim_number') or '-'}"),
        ("Date of Service", svc_date),
        ("Provider", f"{provider}, {clinic}" if provider else clinic),
        ("Clinic Address", clinic_addr),
        ("Diagnosis Treated", diagnosis),
        ("CPT Code / Service", cpt_desc),
        ("Invoice No.", inv_no),
        ("Amount Billed", f"${amount:.2f}" if amount is not None else "-"),
        ("Payment Direction", pay),
    ]
    if c.get("veteran_physical_address"):
        rows.append(("Veteran Physical Address", c.get("veteran_physical_address")))
    if c.get("veteran_mailing_address"):
        rows.append(("Veteran Mailing Address", c.get("veteran_mailing_address")))
    for i, (l, v) in enumerate(rows):
        prow(l, v, i)

    # ---- Checklist page ----
    pdf.add_page()
    band("FMP Fully Developed Claim - Document Checklist",
         "Enclosed documents are marked complete below")
    cats = _packet_categories(items)

    section_title("Required Documents")
    box, rh = 5, 9
    for idx, (cat, label) in enumerate(FMP_CHECKLIST):
        present = cat in cats
        y0 = pdf.get_y()
        pdf.set_fill_color(*(GREEN_LT if idx % 2 == 0 else (255, 255, 255)))
        pdf.rect(pdf.l_margin, y0, content_w, rh, style="F")
        bx, by = pdf.l_margin + 3, y0 + (rh - box) / 2
        pdf.set_draw_color(*GREEN)
        pdf.set_line_width(0.3)
        if present:
            pdf.set_fill_color(*GREEN)
            pdf.rect(bx, by, box, box, style="DF")
            pdf.set_xy(bx, by - 1.1)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font(FONT, "B", 8)
            pdf.cell(box, box + 2, "X", align="C")
        else:
            pdf.rect(bx, by, box, box, style="D")
        pdf.set_xy(pdf.l_margin + 12, y0)
        pdf.set_text_color(*INK)
        pdf.set_font(FONT, "B" if present else "", 9.5)
        pdf.cell(content_w - 14, rh, label, ln=True)
        pdf.set_y(y0 + rh)

    pdf.ln(5)
    section_title("Suggested Submission Order")
    pdf.set_font(FONT, "", 8.5)
    pdf.set_text_color(*GREY)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(content_w, 5,
                   "1) Claim summary & checklist    2) FMP Claim Cover Sheet (VA Form 10-7959f-2)    "
                   "3) Itemized invoice    4) Signed clinical progress note    "
                   "5) VA disability verification letter    6) Provider credentials (exequatur & diploma).")
    pdf.set_text_color(*INK)

    cover_bytes = pdf_bytes(pdf)

    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(cover_bytes)).pages:
        writer.add_page(page)
    for item in _sorted_for_merge(items):
        try:
            data, _ = get_object(item["storage_path"])
            fn = item["filename"].lower()
            if fn.endswith(".pdf"):
                for page in PdfReader(io.BytesIO(data)).pages:
                    writer.add_page(page)
            elif fn.rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp"):
                img = Image.open(io.BytesIO(data)).convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="PDF")
                for page in PdfReader(io.BytesIO(buf.getvalue())).pages:
                    writer.add_page(page)
        except Exception as e:
            logger.error(f"packet merge skip {item.get('filename')}: {e}")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@router.get("/claims")
async def list_claims(user: dict = Depends(require_roles("admin"))):
    packets = await db.claim_packets.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    await log_audit("view", "claim", actor=user, detail=f"list ({len(packets)})")
    return packets


@router.post("/claims")
async def create_claim(data: ClaimInput, user: dict = Depends(require_roles("admin"))):
    if data.status not in CLAIM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    doc = {"id": str(uuid.uuid4()), "name": data.name, "patient_id": data.patient_id,
           "patient_name": await _patient_name(data.patient_id), "claim_number": data.claim_number,
           "status": data.status, "notes": data.notes, "items": [],
           **{f: getattr(data, f) for f in _COVER_FIELDS},
           "created_at": now_iso(), "created_by": user["name"]}
    await db.claim_packets.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "claim", actor=user, resource_id=doc["id"], detail=data.name)
    return doc


class ClaimFromDateInput(BaseModel):
    patient_id: str
    date: str


def _same_day(val, date_str) -> bool:
    return bool(val) and str(val)[:10] == str(date_str)[:10]


@router.post("/claims/from-date")
async def claim_from_date(data: ClaimFromDateInput, user: dict = Depends(require_roles("admin"))):
    from core.folder_filing import note_pdf
    p = await db.patients.find_one({"id": data.patient_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    pname = f"{p['first_name']} {p['last_name']}"
    d = data.date[:10]

    invs = await db.invoices.find({"patient_id": data.patient_id}, {"_id": 0}).to_list(500)
    invs = [i for i in invs if _same_day(i.get("service_date"), d)]
    notes = await db.notes.find({"patient_id": data.patient_id}, {"_id": 0}).to_list(500)
    notes = [n for n in notes if _same_day(n.get("visit_date"), d)]

    if not invs and not notes:
        raise HTTPException(status_code=404, detail="No invoice or progress note found for that patient on that date")

    settings_doc = await get_settings_doc()
    clinic = settings_doc.get("clinic_name", "Veterans of Puerto Plata")
    m = d.split("-")
    disp = f"{m[1]}/{m[2]}/{m[0]}" if len(m) == 3 else d
    packet_name = f"{pname} {disp} FMP Claim"

    items = []
    for inv in invs:
        try:
            pdf = _invoice_pdf(inv, settings_doc)
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
                      "content_type": "application/pdf", "size": result.get("size"), "category": "invoice"})

    for n in notes:
        note = {**n, "patient_name": pname, "dob": p.get("dob"), "ssn": p.get("ssn")}
        try:
            pdf = note_pdf(note, clinic)
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
                      "content_type": "application/pdf", "size": result.get("size"), "category": "progress_note"})

    provider_name = next((n.get("attending_provider") for n in notes if n.get("attending_provider")), None) \
        or next((i.get("attending_provider") or i.get("provider") for i in invs if i.get("attending_provider") or i.get("provider")), None)
    items = await _auto_attach_credentials(items, data.patient_id, provider_name)

    doc = {"id": str(uuid.uuid4()), "name": packet_name, "patient_id": data.patient_id,
           "patient_name": pname, "claim_number": d, "status": "draft", "notes": None,
           "items": items, "created_at": now_iso(), "created_by": user["name"]}
    await db.claim_packets.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "claim", actor=user, resource_id=doc["id"],
                    detail=f"from-date {pname} {d} ({len(items)} items)")
    return doc


@router.get("/claims/{cid}")
async def get_claim(cid: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    return c


@router.put("/claims/{cid}")
async def update_claim(cid: str, data: ClaimInput, user: dict = Depends(require_roles("admin"))):
    if data.status not in CLAIM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    updates = {"name": data.name, "patient_id": data.patient_id,
               "patient_name": await _patient_name(data.patient_id), "claim_number": data.claim_number,
               "status": data.status, "notes": data.notes,
               **{f: getattr(data, f) for f in _COVER_FIELDS},
               "updated_at": now_iso()}
    res = await db.claim_packets.update_one({"id": cid}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=data.name)
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.delete("/claims/{cid}")
async def delete_claim(cid: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if c:
        for it in c.get("items", []):
            if it.get("source") in ("upload", "invoice", "note") and it.get("storage_path"):
                delete_object(it["storage_path"])
    await db.claim_packets.delete_one({"id": cid})
    await log_audit("delete", "claim", actor=user, resource_id=cid)
    return {"ok": True}


@router.post("/claims/{cid}/attach-form")
async def attach_form(cid: str, payload: dict, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    form = await db.forms.find_one({"id": payload.get("form_id")})
    if not form or not form.get("attachment"):
        raise HTTPException(status_code=400, detail="Form has no attached document")
    att = form["attachment"]
    item = {"id": str(uuid.uuid4()), "source": "form", "form_id": form["id"],
            "storage_path": att["storage_path"], "filename": att["filename"],
            "content_type": att.get("content_type", "application/octet-stream"), "size": att.get("size"),
            "category": _guess_category(att["filename"])}
    await db.claim_packets.update_one({"id": cid}, {"$push": {"items": item}, "$set": {"updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"attach form {att['filename']}")
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.post("/claims/{cid}/upload")
async def upload_to_claim(cid: str, file: UploadFile = File(...), user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
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
            "size": result.get("size"), "category": _guess_category(file.filename)}
    await db.claim_packets.update_one({"id": cid}, {"$push": {"items": item}, "$set": {"updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"upload {file.filename}")
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


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
                    "note_type": n.get("note_type"), "reason": n.get("reason_for_visit")})
    return out


@router.get("/claims/options/patients")
async def attachable_patients(user: dict = Depends(require_roles("admin"))):
    pts = await db.patients.find({}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).to_list(1000)
    return [{"id": p["id"], "name": f"{p['first_name']} {p['last_name']}"} for p in pts]


@router.get("/claims/options/patients-by-date")
async def patients_with_completed_visit_on_date(date: str, user: dict = Depends(require_roles("admin"))):
    """For the Bill From Date flow: list patients with a COMPLETED visit on the
    given date, so staff pick the date first and then the patient. Cancelled
    (and any non-completed) appointments are excluded; this app has no
    separate no-show status today."""
    d = date[:10]
    appts = await db.appointments.find(
        {"status": "completed"}, {"_id": 0, "patient_id": 1, "date": 1}).to_list(5000)
    patient_ids = {a["patient_id"] for a in appts if _same_day(a.get("date"), d)}
    if not patient_ids:
        return []
    pts = await db.patients.find(
        {"id": {"$in": list(patient_ids)}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).to_list(1000)
    pts.sort(key=lambda p: (p["first_name"].lower(), p["last_name"].lower()))
    return [{"id": p["id"], "name": f"{p['first_name']} {p['last_name']}"} for p in pts]


@router.post("/claims/{cid}/attach-invoice")
async def attach_invoice(cid: str, payload: dict, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    inv = await db.invoices.find_one({"id": payload.get("invoice_id")}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    settings_doc = await get_settings_doc()
    try:
        pdf_bytes = _invoice_pdf(inv, settings_doc)
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
            "size": result.get("size")}
    await db.claim_packets.update_one({"id": cid}, {"$push": {"items": item}, "$set": {"updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"attach invoice {inv.get('invoice_number')}")
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    await _sync_credentials_and_checklist(c)
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.post("/claims/{cid}/attach-note")
async def attach_note(cid: str, payload: dict, user: dict = Depends(require_roles("admin"))):
    from core.folder_filing import note_pdf, disp_date
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    n = await db.notes.find_one({"id": payload.get("note_id")}, {"_id": 0})
    if not n:
        raise HTTPException(status_code=404, detail="Note not found")
    p = await db.patients.find_one({"id": n.get("patient_id")}, {"_id": 0}) if n.get("patient_id") else None
    pname = (f"{p['first_name']} {p['last_name']}" if p else n.get("patient_name")) or ""
    note = {**n, "patient_name": pname, "dob": (p or {}).get("dob") or n.get("dob"), "ssn": (p or {}).get("ssn")}
    clinic = (await get_settings_doc()).get("clinic_name", "Veterans of Puerto Plata")
    try:
        pdf = note_pdf(note, clinic)
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
            "size": result.get("size")}
    await db.claim_packets.update_one({"id": cid}, {"$push": {"items": item}, "$set": {"updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"attach note {fname}")
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    await _sync_credentials_and_checklist(c)
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.delete("/claims/{cid}/items/{item_id}")
async def remove_item(cid: str, item_id: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if c:
        it = next((i for i in c.get("items", []) if i["id"] == item_id), None)
        if it and it.get("source") in ("upload", "invoice", "note") and it.get("storage_path"):
            delete_object(it["storage_path"])
    await db.claim_packets.update_one({"id": cid}, {"$pull": {"items": {"id": item_id}}, "$set": {"updated_at": now_iso()}})
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


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


@router.get("/claims/{cid}/checklist")
async def claim_checklist(cid: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    _items, checklist, warnings = await _sync_credentials_and_checklist(c)
    return {"checklist": checklist, "warnings": warnings}


async def _auto_file_packet_to_folder(c: dict, pdf: bytes, user: dict):
    """Whenever a completed FMP claim packet is generated, file a copy into
    the correct patient's folder, under a 'Full Name – Date of Service'
    subfolder (reusing it if it already exists — never duplicating), without
    ever overwriting an earlier version. Never raises: a filing failure must
    never break the actual download the user is waiting on."""
    try:
        pid = c.get("patient_id")
        dos = (c.get("claim_number") or "").strip()
        if not pid or not dos:
            logger.error(f"packet auto-file skipped for {c.get('id')}: missing patient_id or date of service")
            return
        p = await db.patients.find_one({"id": pid}, {"_id": 0, "first_name": 1, "last_name": 1})
        if not p:
            logger.error(f"packet auto-file skipped for {c.get('id')}: patient {pid} not found")
            return
        folder_name = f"{p['first_name']} {p['last_name']} – {dos}"[:80]
        sf = await db.folder_subfolders.find_one({"patient_id": pid, "name": folder_name}, {"_id": 0})
        if not sf:
            sf = {"id": str(uuid.uuid4()), "patient_id": pid, "name": folder_name,
                  "created_at": now_iso(), "created_by": user["name"], "created_by_id": user["id"]}
            await db.folder_subfolders.insert_one(dict(sf))
        version = await db.folder_items.count_documents(
            {"patient_id": pid, "subfolder_id": sf["id"], "claim_packet_id": c["id"]}) + 1
        path = f"{APP_NAME}/folders/{pid}/{uuid.uuid4()}.pdf"
        result = put_object(path, pdf, "application/pdf")
        item = {"id": str(uuid.uuid4()), "patient_id": pid, "subfolder_id": sf["id"],
                "source": "claim_packet", "claim_packet_id": c["id"], "form_id": None,
                "storage_path": result["path"], "filename": f"FMP_Claim_Packet_{dos}_v{version}.pdf",
                "label": f"FMP Claim Packet ({dos}) v{version}"[:120], "content_type": "application/pdf",
                "size": result.get("size"), "created_at": now_iso(),
                "created_by": user["name"], "created_by_id": user["id"]}
        await db.folder_items.insert_one(item)
        await log_audit("create", "folder", actor=user, resource_id=pid,
                        detail=f"auto-filed FMP packet v{version} into '{folder_name}'")
    except Exception as e:
        logger.error(f"packet auto-file failed for {c.get('id')}: {e}")


@router.get("/claims/{cid}/merged")
async def merged_pdf(cid: str, user: dict = Depends(require_roles("admin"))):
    """Preview/download the combined packet. This is a READ-ONLY preview: it
    never changes the claim's status and never files a version into the
    patient's folder — that only happens on an explicit save (claim_to_folder
    below, or the FMP builder's 'Approve Packet' action). A packet can be
    previewed any number of times without creating duplicate saved versions."""
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    items, _checklist, _warnings = await _sync_credentials_and_checklist(c)
    c = {**c, "items": items}
    pdf = await _build_packet_pdf(c)
    await log_audit("view", "claim", actor=user, resource_id=cid, detail="previewed merged PDF")
    fname = (c.get("name") or "claim_packet").replace('"', "").replace(" ", "_")[:60]
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'})


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
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


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
    await db.claim_packets.update_one({"id": cid}, {"$set": {"items": ordered, "updated_at": now_iso()}})
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


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
    await db.claim_packets.update_one({"id": cid}, {"$set": {"status": "complete", "updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"emailed packet to {to} · marked complete")
    return {"ok": True, "to": to}


@router.post("/claims/{cid}/to-folder")
async def claim_to_folder(cid: str, user: dict = Depends(require_roles("admin"))):
    """Explicitly SAVE the packet: builds the current combined PDF, marks the
    claim complete, and files a new version into the patient's
    'Full Name – Date of Service' folder (never overwriting a prior save).
    This is the one place a packet actually gets filed — previewing/
    downloading via GET /claims/{cid}/merged never does."""
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    pid = c.get("patient_id")
    if not pid:
        raise HTTPException(status_code=400, detail="Claim packet has no linked patient")
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    items, _checklist, _warnings = await _sync_credentials_and_checklist(c)
    c = {**c, "items": items}
    pdf = await _build_packet_pdf(c)
    await db.claim_packets.update_one({"id": cid}, {"$set": {"status": "complete", "updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail="packet saved · marked complete")
    await _auto_file_packet_to_folder(c, pdf, user)
    return {"ok": True, "patient_name": f"{p['first_name']} {p['last_name']}"}
