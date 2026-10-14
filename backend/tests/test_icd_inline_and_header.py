import asyncio
import io
import os
import sys
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from core.icd_codes import with_icd_descriptions  # noqa: E402
from core.folder_filing import invoice_pdf, note_pdf  # noqa: E402
from routers.claims import _invoice_pdf  # noqa: E402

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
API = os.environ["REACT_APP_BACKEND_URL"] + "/api"
PTSD = "Post-traumatic stress disorder, unspecified"
ok = True
txt = lambda b: " ".join(" ".join(p.extract_text() for p in PdfReader(io.BytesIO(b)).pages).split())  # noqa: E731


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


login = lambda e, p: {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["token"]}  # noqa: E731
admin, psych = login("usvopp@yahoo.com", "Football2023?"), login("zztest.psych@example.com", "ZZtest-2026!")
pid = db.patients.find_one({"first_name": "ZZTEST", "last_name": "Smoke"})["id"]
S = db.settings.find_one({"key": "clinic"}, {"_id": 0})
before_inv = list(db.invoices.find({"icd10_descriptions": {"$exists": True}}, {"id": 1}))
before_notes = db.notes.count_documents({"icd10_descriptions": {"$exists": True}})
LOOP = asyncio.new_event_loop()
inv_id = note_id = None
try:
    inv = requests.post(f"{API}/invoices", headers=admin, json={"patient_id": pid, "icd10": "F43.10, 7eth", "status": "in_transit",
                        "items": [{"cpt_code": "90837", "description": "Psychotherapy", "quantity": 1, "amount": 150}]}).json()
    inv_id = inv["id"]
    check("invoice saves code + description", inv.get("icd10_descriptions") == [{"code": "F43.10", "description": PTSD}, {"code": "7eth", "description": ""}])
    got = requests.get(f"{API}/invoices/{inv_id}", headers=admin).json()
    check("persists on reopen", got["icd10_descriptions"][0]["description"] == PTSD)
    db.icd_codes.update_one({"code": "F43.10"}, {"$set": {"description": "CHANGED LIB TEXT"}})
    doc = LOOP.run_until_complete(with_icd_descriptions(db.invoices.find_one({"id": inv_id}, {"_id": 0})))
    check("saved description wins over later library edits", doc["icd10"] == f"F43.10 — {PTSD}\n7eth")
    db.icd_codes.update_one({"code": "F43.10"}, {"$set": {"description": PTSD}})
    for name, pdf in [("FMP invoice PDF", _invoice_pdf(doc, S)), ("folder invoice PDF", invoice_pdf(doc, S))]:
        t = txt(pdf)
        check(f"{name}: description on same line as code", f"F43.10 — {PTSD}" in t)
        check(f"{name}: header 'ptemple@yahoo.com 809-393-7036'", "ptemple@yahoo.com 809-393-7036" in t)
        check(f"{name}: amounts unchanged", "$150.00" in t and "90837" in t)
    n = requests.post(f"{API}/notes", headers=psych, json={"patient_id": pid, "title": "ZZTEST icd", "content": "x",
                      "visit_date": "2026-03-04", "icd10": "F43.10", "attending_provider": "ZZTEST Psych"}).json()
    note_id = n["id"]
    check("progress note saves code + description", n.get("icd10_descriptions") == [{"code": "F43.10", "description": PTSD}])
    t = txt(note_pdf(LOOP.run_until_complete(with_icd_descriptions(db.notes.find_one({"id": note_id}, {"_id": 0}))), "x", "", S))
    check("note PDF: code — description on same line", f"F43.10 — {PTSD}" in t)
    check("note PDF header has email then phone", "ptemple@yahoo.com 809-393-7036" in t)
    check("existing invoices untouched", [d["id"] for d in db.invoices.find({"icd10_descriptions": {"$exists": True}}, {"id": 1}) if d["id"] != inv_id]
          == [d["id"] for d in before_inv])
    check("existing notes untouched", db.notes.count_documents({"icd10_descriptions": {"$exists": True}}) == before_notes + 1)
finally:
    db.invoices.delete_many({"id": inv_id})
    db.notes.delete_many({"id": note_id})
print("ALL PASS" if ok else "SOME FAILED")
