import io
import re
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from core.db import db
from core.audit import log_audit
from core.security import require_roles
from core.pdf_utils import new_pdf, pdf_bytes, FONT
from core.folder_filing import disp_date

router = APIRouter()

REPORT_ROLES = ("admin", "biller")


def _in_range(date_str, start, end) -> bool:
    d = (date_str or "")[:10]
    if not d:
        return False
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


async def _patients_map():
    return {p["id"]: p async for p in db.patients.find({}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1})}


async def _fetch_completed_invoices(start, end, patient_id, status):
    invoices = await db.invoices.find({}, {"_id": 0}).to_list(5000)
    pmap = await _patients_map()
    out = []
    for inv in invoices:
        d = (inv.get("service_date") or "")[:10]
        if not _in_range(d, start, end):
            continue
        if patient_id and inv.get("patient_id") != patient_id:
            continue
        if status and status != "all" and inv.get("status") != status:
            continue
        p = pmap.get(inv.get("patient_id"))
        pname = inv.get("patient_name") or (f"{p['first_name']} {p['last_name']}" if p else "Unknown")
        cpt = "; ".join(it.get("cpt_code", "") for it in inv.get("items", []) if it.get("cpt_code"))
        out.append({
            "invoice_id": inv["id"], "patient_id": inv.get("patient_id"), "patient_name": pname,
            "invoice_number": inv.get("invoice_number"), "service_date": d,
            "diagnosis": inv.get("icd10") or "", "cpt_code": cpt,
            "amount": inv.get("total", 0), "status": inv.get("status") or "",
        })
    out.sort(key=lambda r: r["service_date"])
    return out


async def _fetch_completed_notes(start, end, patient_id):
    notes = await db.notes.find({}, {"_id": 0}).to_list(5000)
    pmap = await _patients_map()
    out = []
    for n in notes:
        d = (n.get("visit_date") or (n.get("created_at") or ""))[:10]
        if not _in_range(d, start, end):
            continue
        if patient_id and n.get("patient_id") != patient_id:
            continue
        if not n.get("signature"):
            continue  # a note isn't "completed" work until its provider has signed it
        p = pmap.get(n.get("patient_id"))
        pname = f"{p['first_name']} {p['last_name']}" if p else (n.get("patient_name") or "Unknown")
        out.append({
            "note_id": n["id"], "patient_id": n.get("patient_id"), "patient_name": pname,
            "visit_date": d, "diagnosis": n.get("icd10") or "",
            "provider": n.get("attending_provider") or n.get("author") or "",
            "note_type": n.get("note_type") or "free",
            "billing_review_status": n.get("billing_review_status") or "unsigned",
        })
    out.sort(key=lambda r: r["visit_date"])
    return out


_LEGACY_NAME = re.compile(r"^Claim_Packet_(\d{2})-(\d{2})-(\d{4})")


async def _fetch_completed_packets(start, end, patient_id, status):
    """Filed packets: tagged items, plus legacy folder files matched READ-ONLY by
    filename + patient + date. Ambiguous/unmatched legacy files are flagged, never modified."""
    q = {"$or": [{"source": "claim_packet"}, {"filename": {"$regex": "^Claim_Packet_"}}]}
    if patient_id:
        q["patient_id"] = patient_id
    items = await db.folder_items.find(q, {"_id": 0}).to_list(5000)
    pmap = await _patients_map()
    claims = await db.claim_packets.find({}, {"_id": 0, "id": 1, "claim_number": 1, "patient_id": 1}).to_list(5000)
    by_id = {c["id"]: c for c in claims}
    out = []
    for it in items:
        match = "tagged"
        claim = by_id.get(it.get("claim_packet_id"))
        if not claim:
            m = _LEGACY_NAME.match(it.get("filename") or "")
            day = f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else ""
            cands = [c for c in claims if c.get("patient_id") == it.get("patient_id")
                     and str(c.get("claim_number") or "")[:10] == day] if day else []
            claim = cands[0] if len(cands) == 1 else {"claim_number": day}
            match = "legacy_matched" if len(cands) == 1 else ("legacy_ambiguous" if cands else "legacy_unmatched")
        d = (claim.get("claim_number") or "")[:10]
        if not _in_range(d, start, end):
            continue
        st = it.get("servicing_status") or "not_set"
        if status and status != "all" and st != status:
            continue
        p = pmap.get(it.get("patient_id"))
        pname = f"{p['first_name']} {p['last_name']}" if p else "Unknown"
        out.append({
            "item_id": it["id"], "patient_id": it.get("patient_id"), "patient_name": pname,
            "service_date": d, "filename": it.get("filename"), "version_label": it.get("label"),
            "servicing_status": st, "servicing_note": it.get("servicing_note"),
            "filed_at": it.get("created_at"), "match": match,
        })
    out.sort(key=lambda r: r["service_date"])
    return out


@router.get("/reports/completed-invoices")
async def completed_invoices_report(start: Optional[str] = None, end: Optional[str] = None,
                                    patient_id: Optional[str] = None, status: str = "paid",
                                    user: dict = Depends(require_roles(*REPORT_ROLES))):
    rows = await _fetch_completed_invoices(start, end, patient_id, status)
    await log_audit("view", "report", actor=user, detail=f"invoices report ({len(rows)})")
    return rows


@router.get("/reports/completed-notes")
async def completed_notes_report(start: Optional[str] = None, end: Optional[str] = None,
                                 patient_id: Optional[str] = None,
                                 user: dict = Depends(require_roles(*REPORT_ROLES))):
    rows = await _fetch_completed_notes(start, end, patient_id)
    await log_audit("view", "report", actor=user, detail=f"notes report ({len(rows)})")
    return rows


@router.get("/reports/completed-packets")
async def completed_packets_report(start: Optional[str] = None, end: Optional[str] = None,
                                   patient_id: Optional[str] = None, status: str = "complete",
                                   user: dict = Depends(require_roles(*REPORT_ROLES))):
    rows = await _fetch_completed_packets(start, end, patient_id, status)
    await log_audit("view", "report", actor=user, detail=f"packets report ({len(rows)})")
    return rows


def _report_pdf(title: str, clinic: str, columns: list, rows: list) -> bytes:
    pdf = new_pdf()
    pdf.set_font(FONT, "B", 16)
    pdf.cell(0, 10, clinic[:70], ln=True)
    pdf.set_font(FONT, "B", 13)
    pdf.cell(0, 9, title, ln=True)
    pdf.ln(2)
    content_w = pdf.w - pdf.l_margin - pdf.r_margin
    col_w = content_w / len(columns)
    pdf.set_font(FONT, "B", 8.5)
    pdf.set_fill_color(25, 90, 60)
    pdf.set_text_color(255, 255, 255)
    for label, _key in columns:
        pdf.cell(col_w, 7, label, border=1, fill=True)
    pdf.ln(7)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(FONT, "", 8)
    for row in rows:
        if pdf.get_y() > pdf.h - 20:
            pdf.add_page()
        for label, key in columns:
            val = row.get(key, "")
            pdf.cell(col_w, 6.5, str(val)[:40], border=1)
        pdf.ln(6.5)
    if not rows:
        pdf.ln(2)
        pdf.cell(0, 8, "No records match this filter.", ln=True)
    pdf.ln(4)
    pdf.set_font(FONT, "", 8)
    pdf.cell(0, 6, f"{len(rows)} record(s)", ln=True)
    return pdf_bytes(pdf)


async def _clinic_name():
    s = await db.settings.find_one({"key": "clinic"}, {"_id": 0, "clinic_name": 1})
    return (s or {}).get("clinic_name") or "Veterans of Puerto Plata"


@router.get("/reports/completed-invoices/pdf")
async def completed_invoices_pdf(start: Optional[str] = None, end: Optional[str] = None,
                                 patient_id: Optional[str] = None, status: str = "paid",
                                 user: dict = Depends(require_roles(*REPORT_ROLES))):
    rows = await _fetch_completed_invoices(start, end, patient_id, status)
    for r in rows:
        r["service_date"] = disp_date(r["service_date"])
        r["amount"] = f"${r['amount']:.2f}"
    await log_audit("export", "report", actor=user, detail=f"pdf ({len(rows)})")
    pdf = _report_pdf("Completed Invoices Report", await _clinic_name(), [
        ("Patient", "patient_name"), ("Date of Service", "service_date"), ("Diagnosis", "diagnosis"),
        ("CPT", "cpt_code"), ("Amount", "amount"), ("Status", "status"),
    ], rows)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="completed_invoices_report.pdf"'})


@router.get("/reports/completed-notes/pdf")
async def completed_notes_pdf(start: Optional[str] = None, end: Optional[str] = None,
                              patient_id: Optional[str] = None,
                              user: dict = Depends(require_roles(*REPORT_ROLES))):
    rows = await _fetch_completed_notes(start, end, patient_id)
    for r in rows:
        r["visit_date"] = disp_date(r["visit_date"])
    await log_audit("export", "report", actor=user, detail=f"pdf ({len(rows)})")
    pdf = _report_pdf("Completed Progress Notes Report", await _clinic_name(), [
        ("Patient", "patient_name"), ("Date of Service", "visit_date"), ("Diagnosis", "diagnosis"),
        ("Provider", "provider"), ("Billing Status", "billing_review_status"),
    ], rows)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="completed_notes_report.pdf"'})


@router.get("/reports/completed-packets/pdf")
async def completed_packets_pdf(start: Optional[str] = None, end: Optional[str] = None,
                                patient_id: Optional[str] = None, status: str = "complete",
                                user: dict = Depends(require_roles(*REPORT_ROLES))):
    rows = await _fetch_completed_packets(start, end, patient_id, status)
    for r in rows:
        r["service_date"] = disp_date(r["service_date"])
    await log_audit("export", "report", actor=user, detail=f"pdf ({len(rows)})")
    pdf = _report_pdf("Completed Claim Packets Report", await _clinic_name(), [
        ("Patient", "patient_name"), ("Date of Service", "service_date"), ("File", "filename"),
        ("Status", "servicing_status"),
    ], rows)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="completed_packets_report.pdf"'})
