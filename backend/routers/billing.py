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
from models.schemas import CptInput, InvoiceInput

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
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}" async for p in db.patients.find({}, {"_id": 0})}
    for inv in invoices:
        inv["patient_name"] = inv.get("patient_name") or patients.get(inv.get("patient_id"), "Unknown")
    await log_audit("view", "invoice", actor=user, detail=f"list ({len(invoices)})")
    return invoices


@router.get("/invoices/next-number")
async def next_invoice_number(user: dict = Depends(require_roles("biller", "receptionist"))):
    count = await db.invoices.count_documents({})
    return {"invoice_number": f"MB-{count + 1:04d}"}


@router.post("/invoices")
async def create_invoice(data: InvoiceInput, user: dict = Depends(require_roles("biller", "receptionist"))):
    items = [i.model_dump() for i in data.items]
    total = sum(i["amount"] * i["quantity"] for i in items)
    number = data.invoice_number
    if not number:
        count = await db.invoices.count_documents({})
        number = f"MB-{count + 1:04d}"
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
    await log_audit("update", "invoice", actor=user, resource_id=iid, detail=f"status={status}")
    return await db.invoices.find_one({"id": iid}, {"_id": 0})


# ---------------- Billing reports ----------------
def _inv_date(inv):
    return (inv.get("created_at") or "")[:10]


@router.get("/reports/billing")
async def billing_report(start: Optional[str] = None, end: Optional[str] = None,
                         user: dict = Depends(require_roles("biller", "admin"))):
    invoices = await db.invoices.find({}, {"_id": 0}).to_list(2000)
    if start:
        invoices = [i for i in invoices if _inv_date(i) >= start]
    if end:
        invoices = [i for i in invoices if _inv_date(i) <= end]

    total_billed = sum(i.get("total", 0) for i in invoices)
    collected = sum(i.get("total", 0) for i in invoices if i.get("status") == "paid")
    outstanding = sum(i.get("total", 0) for i in invoices if i.get("status") == "unpaid")

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
    }


@router.get("/reports/billing/export")
async def billing_export(start: Optional[str] = None, end: Optional[str] = None,
                         user: dict = Depends(require_roles("biller", "admin"))):
    invoices = await db.invoices.find({}, {"_id": 0}).to_list(2000)
    if start:
        invoices = [i for i in invoices if _inv_date(i) >= start]
    if end:
        invoices = [i for i in invoices if _inv_date(i) <= end]
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}" async for p in db.patients.find({}, {"_id": 0})}

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
