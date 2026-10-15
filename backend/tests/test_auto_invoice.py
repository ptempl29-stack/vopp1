import os
import sys
import uuid
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
API = os.environ["REACT_APP_BACKEND_URL"] + "/api"
SIG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
H = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "usvopp@yahoo.com", "password": "Football2023?"}).json()["token"]}
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


def nums():
    out = []
    for n in db.invoices.distinct("invoice_number"):
        try:
            out.append(int(str(n).split("-")[1]))
        except (IndexError, ValueError):
            pass
    return out


pid = f"ZZTEST-AUTO-{uuid.uuid4()}"
db.patients.insert_one({"id": pid, "first_name": "ZZTEST", "last_name": "AutoInvoice", "dob": "1970-01-01", "ssn": "123-45-6789"})
cpt = db.cpt_codes.find_one({"code": "90837"})
base = dict(patient_id=pid, title="ZZTEST session", content="x", attending_provider="ZZTEST Psych", icd10="F43.10")
notes = {"ok": {**base, "visit_date": "2026-05-01", "cpt_code": "90837", "signature": SIG, "completed": True},
         "nocpt": {**base, "visit_date": "2026-05-02", "cpt_code": "", "signature": SIG, "completed": True},
         "badcpt": {**base, "visit_date": "2026-05-03", "cpt_code": "ZZ999", "signature": SIG, "completed": True},
         "unsigned": {**base, "visit_date": "2026-05-04", "cpt_code": "90837", "signature": None, "completed": False}}
for k, n in notes.items():
    n["id"] = f"zz-auto-{k}-{uuid.uuid4()}"
    db.notes.insert_one(dict(n))
before_count, before_max = db.invoices.count_documents({}), max(nums() or [0])
build = lambda day: requests.post(f"{API}/claims/from-date", headers=H, json={"patient_id": pid, "date": day}).json()  # noqa: E731
try:
    r = build("2026-05-01")
    inv = db.invoices.find_one({"patient_id": pid, "service_date": "2026-05-01"}, {"_id": 0})
    check("invoice auto-created from signed, completed note", inv is not None and inv["auto_generated"])
    check(f"next number in MB sequence ({inv and inv['invoice_number']})", inv and inv["invoice_number"] == f"MB-{max(before_max + 1, 63):04d}")
    check("CPT rate/units from approved CPT list", inv and inv["items"] == [{"cpt_code": "90837", "description": cpt["description"],
          "quantity": int(cpt.get("default_units") or 1), "minutes": 0, "amount": float(cpt["amount"])}])
    check("total = rate x units", inv and inv["total"] == round(float(cpt["amount"]) * int(cpt.get("default_units") or 1), 2))
    check("patient + note data copied (DOB, SSN, ICD, provider)", inv and (inv["dob"], inv["ssn"], inv["icd10"], inv["provider"]) ==
          ("1970-01-01", "123-45-6789", "F43.10", "ZZTEST Psych"))
    check("invoice attached to packet", any(i.get("invoice_id") == (inv or {}).get("id") and i["category"] == "invoice" for i in r["items"]))
    check("note also attached", any(i.get("note_id") == notes["ok"]["id"] for i in r["items"]))
    r2 = build("2026-05-01")
    check("rebuilding same date creates NO duplicate invoice", db.invoices.count_documents({"patient_id": pid, "service_date": "2026-05-01"}) == 1
          and any(i.get("invoice_id") == inv["id"] for i in r2["items"]))
    for day, key, msg in [("2026-05-02", "nocpt", "has no CPT code"), ("2026-05-03", "badcpt", "not in the approved CPT list"),
                          ("2026-05-04", "unsigned", "not signed and Completed")]:
        r = build(day)
        check(f"{key}: no invoice, clear message", db.invoices.count_documents({"patient_id": pid, "service_date": day}) == 0
              and any(msg in m for m in r.get("auto_invoice_problems", [])))
    check("only one invoice added overall", db.invoices.count_documents({}) == before_count + 1)
    check("audit logged", db.audit_logs.find_one({"resource_id": inv["id"], "action": "create"}) is not None)
finally:
    db.invoices.delete_many({"patient_id": pid})
    db.claim_packets.delete_many({"patient_id": pid})
    db.notes.delete_many({"patient_id": pid})
    db.patients.delete_one({"id": pid})
print("ALL PASS" if ok else "SOME FAILED")
