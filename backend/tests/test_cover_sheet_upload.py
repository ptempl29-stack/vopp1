import io
import os
import requests
from fpdf import FPDF
from pypdf import PdfReader
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"] + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


def pdf(text):
    p = FPDF()
    p.add_page()
    p.set_font("Helvetica", size=20)
    p.cell(0, 10, text)
    return bytes(p.output())


tok = requests.post(f"{API}/auth/login", json={"email": "usvopp@yahoo.com", "password": "Football2023?"}).json()["token"]
H = {"Authorization": f"Bearer {tok}"}
pid = db.patients.find_one({"first_name": "ZZTEST", "last_name": "Smoke"})["id"]
DAY = "2026-01-07"
db.claim_packets.delete_many({"patient_id": pid, "claim_number": DAY})

c = requests.post(f"{API}/claims/from-date", headers=H, json={"patient_id": pid, "date": DAY}).json()
cid = c["id"]
check("no auto-generated cover item", not any(i.get("category") == "cover_sheet" for i in c["items"]))
check("missing cover blocks approval", "Missing required document: FMP Claim Cover Sheet" in c["approval_blockers"])

up = lambda name, txt: requests.post(f"{API}/claims/{cid}/upload", headers=H, data={"category": "cover_sheet"},  # noqa: E731
                                    files={"file": (name, pdf(txt), "application/pdf")}).json()
r = up("scan_cover_A.pdf", "ZZCOVER-A")
check("uploaded cover is position 1", r["items"][0]["category"] == "cover_sheet" and r["items"][0]["filename"] == "scan_cover_A.pdf")
check("cover blocker cleared", "Missing required document: FMP Claim Cover Sheet" not in r["approval_blockers"])
r = up("scan_cover_B.pdf", "ZZCOVER-B")
covers = [i for i in r["items"] if i.get("category") == "cover_sheet"]
check("replace keeps exactly one cover", len(covers) == 1 and covers[0]["filename"] == "scan_cover_B.pdf")
cats = [i.get("category") for i in r["items"]]
check("rest keeps required order", [x for x in cats if x != "cover_sheet"] ==
      sorted([x for x in cats if x != "cover_sheet"], key=["va_disability_letter", "invoice", "progress_note",
                                                            "provider_exequatur", "provider_diploma"].index))

ids = [i["id"] for i in r["items"]]
r = requests.put(f"{API}/claims/{cid}/items-order", headers=H, json={"ids": ids[1:] + ids[:1]}).json()
check("reorder cannot move cover off position 1", r["items"][0]["category"] == "cover_sheet")

m = requests.get(f"{API}/claims/{cid}/merged", headers=H)
if m.status_code == 200:
    pages = [pg.extract_text() or "" for pg in PdfReader(io.BytesIO(m.content)).pages]
    check("merged PDF page 1 is the uploaded cover", "ZZCOVER-B" in pages[0])
    check("no Fully Developed Claim checklist pages", not any("Fully Developed Claim" in tx or "Claim Summary" in tx for tx in pages))
    check("checklist endpoint removed", requests.get(f"{API}/claims/{cid}/checklist", headers=H).status_code in (404, 405))
else:
    check(f"merged PDF built ({m.status_code} {m.text[:120]})", False)

a = requests.post(f"{API}/claims/{cid}/approve", headers=H)
check("approval still blocked while other docs missing", a.status_code == 400)

db.claim_packets.delete_many({"id": cid})
print("ALL PASS" if ok else "SOME FAILED")
