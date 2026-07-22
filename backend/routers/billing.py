import io
import csv
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from core.db import db, now_iso
from core.config import INVOICE_STATUSES
from core.security import get_current_user, require_roles
from core.audit import log_audit
from models.schemas import CptInput, InvoiceInput, IdList

router = APIRouter()


# ---------------- CPT codes ----------------
@router.get("/cpt-codes")
async def cpt_codes(user: dict = Depends(get_current_user)):
    return await db.cpt_codes.find({}, {"_id": 0}).sort("code", 1).to_list(1000)


@router.post("/cpt-codes")
async def create_cpt(data: CptInput, user: dict = Depends(require_roles("biller"))):
    if await db.cpt_codes.find_one({"code": data.code}):
        raise HTTPException(status_code=400, detail="CPT code already exists")
    doc = {"id": str(uuid.uuid4()), **data.model_dump(), "created_at": now_iso()}
    await db.cpt_codes.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/cpt-codes/{cid}")
async def update_cpt(cid: str, data: CptInput, user: dict = Depends(require_roles("biller"))):
    res = await db.cpt_codes.update_one({"id": cid}, {"$set": data.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="CPT code not found")
    return await db.cpt_codes.find_one({"id": cid}, {"_id": 0})


@router.delete("/cpt-codes/{cid}")
async def delete_cpt(cid: str, user: dict = Depends(require_roles("biller"))):
    await db.cpt_codes.delete_one({"id": cid})
    return {"ok": True}


# ---------------- Invoices ----------------
@router.get("/invoices")
async def list_invoices(user: dict = Depends(require_roles("biller", "receptionist"))):
    invoices = await db.invoices.find({}, {"_id": 0, "ssn": 0, "policy_number": 0}).sort("created_at", -1).to_list(500)
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}"
                async for p in db.patients.find({}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).limit(5000)}
    for inv in invoices:
        inv["patient_name"] = patients.get(inv.get("patient_id")) or inv.get("patient_name") or "Unknown"
    await log_audit("view", "invoice", actor=user, detail=f"list ({len(invoices)})")
    return invoices


INVOICE_SEQ_BASE = 36


async def _compute_next_number() -> str:
    nums = await db.invoices.distinct("invoice_number")
    mx = 0
    for n in nums:
        if isinstance(n, str) and n.startswith("MB-"):
            try:
                mx = max(mx, int(n.split("-")[1]))
            except (ValueError, IndexError):
                pass
    return f"MB-{max(mx + 1, INVOICE_SEQ_BASE):04d}"


@router.get("/invoices/next-number")
async def next_invoice_number(user: dict = Depends(require_roles("biller", "receptionist"))):
    return {"invoice_number": await _compute_next_number()}


@router.get("/invoices/patient-code-history")
async def invoice_code_history(patient_id: str, user: dict = Depends(require_roles("biller", "receptionist"))):
    icd_inv = await db.invoices.distinct("icd10", {"patient_id": patient_id, "icd10": {"$nin": [None, ""]}})
    icd_notes = await db.notes.distinct("icd10", {"patient_id": patient_id, "icd10": {"$nin": [None, ""]}})
    return {"icd10": sorted(set(icd_inv) | set(icd_notes))}


@router.post("/invoices")
async def create_invoice(data: InvoiceInput, user: dict = Depends(require_roles("biller", "receptionist"))):
    items = [i.model_dump() for i in data.items]
    total = sum(i["amount"] * i["quantity"] for i in items)
    number = data.invoice_number
    if not number:
        number = await _compute_next_number()
    name = data.patient_name
    if not name and data.patient_id:
        p = await db.patients.find_one({"id": data.patient_id}, {"_id": 0})
        if p:
            name = f"{p['first_name']} {p['last_name']}"
    doc = {"id": str(uuid.uuid4()), "invoice_number": number,
           "patient_id": data.patient_id, "patient_name": name,
           "dob": data.dob, "ssn": data.ssn, "policy_number": data.policy_number, "gender": data.gender,
           "service_date": data.service_date, "visit_reason": data.visit_reason,
           "icd10": data.icd10, "provider": data.provider,
           "items": items, "total": round(total, 2), "status": data.status, "notes": data.notes,
           "completed_at": now_iso() if data.status == "paid" else None,
           "created_at": now_iso(), "created_by": user["name"]}
    await db.invoices.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "invoice", actor=user, resource_id=doc["id"],
                    detail=f"{number} · {name or ''} · ${doc['total']}")
    return doc


@router.put("/invoices/{iid}/status")
async def update_invoice_status(iid: str, status: str, user: dict = Depends(require_roles("biller", "receptionist"))):
    if status not in INVOICE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    res = await db.invoices.update_one({"id": iid}, {"$set": {"status": status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    existing = await db.invoices.find_one({"id": iid}, {"_id": 0})
    completed = (existing.get("completed_at") or now_iso()) if status == "paid" else None
    await db.invoices.update_one({"id": iid}, {"$set": {"completed_at": completed}})
    await log_audit("update", "invoice", actor=user, resource_id=iid, detail=f"status={status}")
    return await db.invoices.find_one({"id": iid}, {"_id": 0})


@router.get("/invoices/{iid}")
async def get_invoice(iid: str, user: dict = Depends(require_roles("biller", "receptionist"))):
    inv = await db.invoices.find_one({"id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.get("patient_id"):
        p = await db.patients.find_one({"id": inv["patient_id"]}, {"_id": 0})
        if p:
            inv["patient_name"] = f"{p['first_name']} {p['last_name']}"
            inv["dob"] = p.get("dob") or inv.get("dob")
            inv["ssn"] = p.get("ssn") or inv.get("ssn")
            inv["gender"] = p.get("gender") or inv.get("gender")
    await log_audit("view", "invoice", actor=user, resource_id=iid, detail=inv.get("invoice_number", ""))
    return inv


@router.post("/invoices/{iid}/to-folder")
async def invoice_to_folder(iid: str, user: dict = Depends(require_roles("biller", "receptionist"))):
    from core.folder_filing import invoice_pdf, file_pdf_into_folder, fmt_date
    inv = await db.invoices.find_one({"id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    pid = inv.get("patient_id")
    if not pid:
        raise HTTPException(status_code=400, detail="Invoice has no linked patient")
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    inv = {**inv, "patient_name": f"{p['first_name']} {p['last_name']}", "dob": p.get("dob")}
    s = await db.settings.find_one({"key": "clinic"}, {"_id": 0})
    clinic = (s or {}).get("clinic_name", "Veterans of Puerto Plata")
    sd = inv.get("service_date")
    ds = fmt_date(sd)
    num = inv.get("invoice_number") or "Invoice"
    try:
        pdf = invoice_pdf(inv, clinic)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not render invoice PDF")
    label = f"Patient Invoice {num} {ds}".strip()
    item = await file_pdf_into_folder(pid, p["first_name"], pdf,
                                      label, f"Patient_Invoice_{num}_{ds}.pdf", user, date_str=sd)
    if not item:
        raise HTTPException(status_code=502, detail="Could not file PDF")
    await log_audit("create", "folder", actor=user, resource_id=pid, detail=f"auto-filed invoice {iid}")
    return {"ok": True, "patient_name": inv["patient_name"]}


@router.put("/invoices/{iid}")
async def update_invoice(iid: str, data: InvoiceInput, user: dict = Depends(require_roles("biller", "receptionist"))):
    existing = await db.invoices.find_one({"id": iid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")
    items = [i.model_dump() for i in data.items]
    total = sum(i["amount"] * i["quantity"] for i in items)
    name = data.patient_name
    if not name and data.patient_id:
        p = await db.patients.find_one({"id": data.patient_id}, {"_id": 0})
        if p:
            name = f"{p['first_name']} {p['last_name']}"
    upd = {"invoice_number": data.invoice_number or existing.get("invoice_number"),
           "patient_id": data.patient_id, "patient_name": name,
           "dob": data.dob, "ssn": data.ssn, "policy_number": data.policy_number, "gender": data.gender,
           "service_date": data.service_date, "visit_reason": data.visit_reason,
           "icd10": data.icd10, "provider": data.provider,
           "items": items, "total": round(total, 2), "status": data.status, "notes": data.notes,
           "completed_at": (existing.get("completed_at") or now_iso()) if data.status == "paid" else None,
           "updated_at": now_iso(), "updated_by": user["name"]}
    await db.invoices.update_one({"id": iid}, {"$set": upd})
    await log_audit("update", "invoice", actor=user, resource_id=iid,
                    detail=f"{upd['invoice_number']} · {name or ''} · ${upd['total']}")
    return await db.invoices.find_one({"id": iid}, {"_id": 0})


@router.post("/invoices/bulk-delete")
async def bulk_delete_invoices(data: IdList, user: dict = Depends(require_roles("biller", "receptionist", "admin"))):
    docs = await db.invoices.find({"id": {"$in": data.ids}}, {"_id": 0, "id": 1, "created_by": 1}).to_list(1000)
    deletable = [d["id"] for d in docs
                 if user["role"] == "admin" or d.get("created_by") in (user["name"], None)]
    if deletable:
        await db.invoices.delete_many({"id": {"$in": deletable}})
    await log_audit("delete", "invoice", actor=user, detail=f"bulk ({len(deletable)})")
    return {"deleted": len(deletable), "skipped": len(data.ids) - len(deletable)}


@router.delete("/invoices/{iid}")
async def delete_invoice(iid: str, user: dict = Depends(require_roles("biller", "receptionist", "admin"))):
    existing = await db.invoices.find_one({"id": iid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if user["role"] != "admin" and existing.get("created_by") not in (user["name"], None):
        raise HTTPException(status_code=403, detail="You can only delete invoices you created")
    await db.invoices.delete_one({"id": iid})
    await log_audit("delete", "invoice", actor=user, resource_id=iid, detail=existing.get("invoice_number", ""))
    return {"ok": True}


# ---------------- Billing reports ----------------
def _inv_date(inv):
    return (inv.get("created_at") or "")[:10]


@router.get("/reports/billing")
async def billing_report(start: Optional[str] = None, end: Optional[str] = None,
                         patient_id: Optional[str] = None, provider: Optional[str] = None,
                         appointment_type: Optional[str] = None,
                         user: dict = Depends(require_roles("biller", "admin"))):
    invoices = await db.invoices.find({}, {"_id": 0}).to_list(2000)
    if start:
        invoices = [i for i in invoices if _inv_date(i) >= start]
    if end:
        invoices = [i for i in invoices if _inv_date(i) <= end]
    if patient_id:
        invoices = [i for i in invoices if i.get("patient_id") == patient_id]
    if provider:
        invoices = [i for i in invoices if i.get("provider") == provider]
    if appointment_type:
        pts = set(await db.appointments.distinct("patient_id", {"appointment_type": appointment_type}))
        invoices = [i for i in invoices if i.get("patient_id") in pts]

    patients_map = {p["id"]: f"{p['first_name']} {p['last_name']}"
                    async for p in db.patients.find({}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).limit(5000)}
    pname = lambda i: i.get("patient_name") or patients_map.get(i.get("patient_id"), "Unknown")

    total_billed = sum(i.get("total", 0) for i in invoices)
    collected = sum(i.get("total", 0) for i in invoices if i.get("status") == "paid")
    outstanding = sum(i.get("total", 0) for i in invoices if i.get("status") != "paid")

    by_day = {}
    for i in invoices:
        d = _inv_date(i)
        by_day.setdefault(d, {"date": d, "billed": 0.0, "collected": 0.0})
        by_day[d]["billed"] += i.get("total", 0)
        if i.get("status") == "paid":
            by_day[d]["collected"] += i.get("total", 0)
    timeseries = sorted(by_day.values(), key=lambda x: x["date"])

    by_cpt = {}
    for i in invoices:
        for it in i.get("items", []):
            c = it.get("cpt_code", "?")
            by_cpt.setdefault(c, {"cpt_code": c, "description": it.get("description", ""),
                                  "count": 0, "revenue": 0.0})
            by_cpt[c]["count"] += it.get("quantity", 1)
            by_cpt[c]["revenue"] += it.get("amount", 0) * it.get("quantity", 1)
    cpt_breakdown = sorted(by_cpt.values(), key=lambda x: x["revenue"], reverse=True)

    by_patient = {}
    for i in invoices:
        n = pname(i)
        e = by_patient.setdefault(n, {"patient": n, "revenue": 0.0, "count": 0})
        e["revenue"] += i.get("total", 0)
        e["count"] += 1
    patient_breakdown = sorted(by_patient.values(), key=lambda x: x["revenue"], reverse=True)

    inv_list = sorted([{
        "id": i["id"], "invoice_number": i.get("invoice_number"), "patient_name": pname(i),
        "service_date": _inv_date(i), "status": i.get("status"), "total": round(i.get("total", 0), 2),
        "provider": i.get("provider"),
    } for i in invoices], key=lambda x: x["service_date"], reverse=True)

    return {
        "summary": {
            "total_billed": round(total_billed, 2),
            "collected": round(collected, 2),
            "outstanding": round(outstanding, 2),
            "invoice_count": len(invoices),
            "paid_count": len([i for i in invoices if i.get("status") == "paid"]),
        },
        "timeseries": [{"date": t["date"], "billed": round(t["billed"], 2),
                        "collected": round(t["collected"], 2)} for t in timeseries],
        "cpt_breakdown": [{**c, "revenue": round(c["revenue"], 2)} for c in cpt_breakdown],
        "patient_breakdown": [{**c, "revenue": round(c["revenue"], 2)} for c in patient_breakdown],
        "invoices": inv_list,
    }


@router.get("/reports/billing/export")
async def billing_export(start: Optional[str] = None, end: Optional[str] = None,
                         user: dict = Depends(require_roles("biller", "admin"))):
    invoices = await db.invoices.find({}, {"_id": 0}).to_list(2000)
    if start:
        invoices = [i for i in invoices if _inv_date(i) >= start]
    if end:
        invoices = [i for i in invoices if _inv_date(i) <= end]
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}"
                async for p in db.patients.find({}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).limit(5000)}

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Invoice ID", "Date", "Patient", "CPT Codes", "Status", "Total"])
    for i in invoices:
        codes = "; ".join(it.get("cpt_code", "") for it in i.get("items", []))
        w.writerow([i.get("id"), _inv_date(i), patients.get(i.get("patient_id"), "Unknown"),
                    codes, i.get("status"), f'{i.get("total", 0):.2f}'])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=billing_report.csv"})
