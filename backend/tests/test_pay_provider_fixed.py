import io
import os
import sys
import time
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
import requests  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from core.storage import get_object  # noqa: E402

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
API = os.environ["REACT_APP_BACKEND_URL"] + "/api"
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


img = Image.new("RGB", (1000, 1300), (245, 243, 236))
d = ImageDraw.Draw(img)
d.text((60, 60), "FMP CLAIM COVER SHEET VA Form 10-7959f-2   PAYMENT TO: [ ] PROVIDER  [X] VETERAN", fill=(0, 0, 0))
d.rectangle((60, 120, 940, 1200), outline=(0, 0, 0), width=3)
buf = io.BytesIO()
img.save(buf, "JPEG", quality=85)
raw = buf.getvalue()

H = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "usvopp@yahoo.com", "password": "Football2023?"}).json()["token"]}
pid = db.patients.find_one({"first_name": "ZZTEST", "last_name": "Smoke"})["id"]
db.claim_packets.delete_many({"patient_id": pid, "claim_number": "2026-01-07"})
cid = requests.post(f"{API}/claims/from-date", headers=H, json={"patient_id": pid, "date": "2026-01-07"}).json()["id"]
try:
    t0 = time.time()
    r = requests.post(f"{API}/claims/{cid}/upload", headers=H, data={"category": "cover_sheet"},
                      files={"file": ("scan_veteran_marked.jpg", raw, "image/jpeg")}, timeout=60).json()
    check(f"upload is instant, no AI read ({time.time() - t0:.1f}s)", time.time() - t0 < 2.5)
    doc = db.claim_packets.find_one({"id": cid})
    check("no payment detection stored", not any(k in doc for k in ("payment_review", "payment_review_reason"))
          and doc.get("payment_to") is None)
    check("no payment-box approval blocker", not any("Payment box" in b for b in r["approval_blockers"]))
    check("uploaded cover is first document", r["items"][0]["category"] == "cover_sheet")
    stored, _ = get_object(r["items"][0]["storage_path"])
    check("scan stored unchanged", stored == raw)
    pages = PdfReader(io.BytesIO(requests.get(f"{API}/claims/{cid}/merged", headers=H, timeout=120).content)).pages
    p1 = pages[0].extract_text()
    check("checklist is page 1", "Fully Developed Claim" in p1)
    check("payment line is fixed 'Pay Provider' even though scan marks Veteran",
          "Pay Provider" in p1 and "☒" not in p1 and "NEEDS STAFF REVIEW" not in p1 and "Veteran payment" not in p1)
    check("rest of checklist intact", all(x in p1 for x in ("Claim Summary", "Date of Service", "Diagnosis Treated", "Amount Billed")))
    idx = next(i for i, pg in enumerate(pages) if "Fully Developed Claim" not in (pg.extract_text() or "") and "Checklist" not in (pg.extract_text() or ""))
    check("uploaded cover follows checklist pages", idx >= 1)
    check("staff payment endpoint removed",
          requests.put(f"{API}/claims/{cid}/payment-recipient", headers=H, json={"payment_to": "veteran"}).status_code in (404, 405))
finally:
    db.claim_packets.delete_many({"id": cid})
print("ALL PASS" if ok else "SOME FAILED")
