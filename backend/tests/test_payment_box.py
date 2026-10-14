import io
import os
import sys
import time
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
import requests  # noqa: E402
from PIL import Image, ImageDraw, ImageFont, ImageFilter  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from core.storage import get_object  # noqa: E402

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
API = os.environ["REACT_APP_BACKEND_URL"] + "/api"
FONT = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


def scan(mark):
    """Synthetic scanned 10-7959f-2 with a hand-drawn X in the chosen payment box(es)."""
    img = Image.new("RGB", (1240, 1600), (246, 244, 238))
    d = ImageDraw.Draw(img)
    f, fb = ImageFont.truetype(FONT, 26), ImageFont.truetype(FONT, 34)
    d.text((80, 60), "DEPARTMENT OF VETERANS AFFAIRS", font=fb, fill=(20, 20, 20))
    d.text((80, 110), "FOREIGN MEDICAL PROGRAM (FMP) CLAIM COVER SHEET", font=f, fill=(20, 20, 20))
    d.text((80, 150), "VA Form 10-7959f-2", font=f, fill=(60, 60, 60))
    y = 240
    for lbl in ["1. Veteran's Name: ZZTEST Smoke", "2. VA Claim File No.: 000-00-1234",
                "3. Date(s) of Service: 01/07/2026", "4. Provider: Veterans of Puerto Plata"]:
        d.text((80, y), lbl, font=f, fill=(30, 30, 30))
        d.line((80, y + 40, 1160, y + 40), fill=(150, 150, 150), width=2)
        y += 90
    d.text((80, y + 20), "5. PAYMENT TO (check one):", font=fb, fill=(20, 20, 20))
    boxes = {"provider": (120, y + 90), "veteran": (620, y + 90)}
    for who, (bx, by) in boxes.items():
        d.rectangle((bx, by, bx + 50, by + 50), outline=(20, 20, 20), width=4)
        d.text((bx + 75, by + 5), who.upper(), font=fb, fill=(20, 20, 20))
        if who in mark:
            d.line((bx + 6, by + 6, bx + 46, by + 46), fill=(10, 30, 120), width=7)
            d.line((bx + 46, by + 4, bx + 4, by + 47), fill=(10, 30, 120), width=7)
    d.text((80, y + 220), "Signature of Veteran: ______________________   Date: __________", font=f, fill=(30, 30, 30))
    img = img.rotate(0.8, expand=False, fillcolor=(246, 244, 238)).filter(ImageFilter.GaussianBlur(0.7))
    return img


def as_jpg(img):
    b = io.BytesIO()
    img.save(b, "JPEG", quality=80)
    return b.getvalue()


def as_scanned_pdf(img):
    b = io.BytesIO()
    img.save(b, "PDF", resolution=150)
    return b.getvalue()


H = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "usvopp@yahoo.com", "password": "Football2023?"}).json()["token"]}
pid = db.patients.find_one({"first_name": "ZZTEST", "last_name": "Smoke"})["id"]
DAY = "2026-01-07"
db.claim_packets.delete_many({"patient_id": pid, "claim_number": DAY})
cid = requests.post(f"{API}/claims/from-date", headers=H, json={"patient_id": pid, "date": DAY}).json()["id"]


def upload(name, data, ct):
    t0 = time.time()
    r = requests.post(f"{API}/claims/{cid}/upload", headers=H, data={"category": "cover_sheet"},
                      files={"file": (name, data, ct)}, timeout=120).json()
    print(f"     {name}: payment_to={r.get('payment_to')} source={r.get('payment_to_source')} "
          f"reason={r.get('payment_review_reason')!r} ({time.time() - t0:.1f}s)")
    return r


PAY_MSG = "Payment box on the FMP Claim Cover Sheet needs staff review — choose Provider or Veteran."
try:
    raw = as_jpg(scan({"provider"}))
    r = upload("scan_provider.jpg", raw, "image/jpeg")
    check("CASE 1 provider box (JPG scan) -> provider", r.get("payment_to") == "provider" and not r.get("payment_review"))
    check("no payment blocker when read", PAY_MSG not in r["approval_blockers"])
    cover = next(i for i in r["items"] if i["category"] == "cover_sheet")
    stored, _ = get_object(cover["storage_path"])
    check("original scan stored byte-for-byte unchanged", stored == raw)
    m = requests.get(f"{API}/claims/{cid}/merged", headers=H, timeout=120)
    pages = PdfReader(io.BytesIO(m.content)).pages
    p1 = pages[0].extract_text()
    check("merged PDF page 1 is the Fully Developed Claim checklist", "Fully Developed Claim" in p1)
    check("checklist PDF shows Provider marked", "☒ Provider" in p1 and "☐ Veteran" in p1)
    cover_page = next(i for i, pg in enumerate(pages) if "Fully Developed Claim" not in (pg.extract_text() or ""))
    check("uploaded cover sheet follows checklist pages", cover_page >= 1 and not (pages[cover_page].extract_text() or "").strip())

    r = upload("scan_veteran.pdf", as_scanned_pdf(scan({"veteran"})), "application/pdf")
    check("CASE 2 veteran box (scanned PDF) -> veteran", r.get("payment_to") == "veteran" and not r.get("payment_review"))
    p1 = PdfReader(io.BytesIO(requests.get(f"{API}/claims/{cid}/merged", headers=H, timeout=120).content)).pages[0].extract_text()
    check("checklist PDF shows Veteran marked", "☐ Provider" in p1 and "☒ Veteran" in p1)

    r = upload("scan_blank.jpg", as_jpg(scan(set())), "image/jpeg")
    check("CASE 3 no box marked -> staff review, no guess", r.get("payment_to") is None and r.get("payment_review"))
    check("unclear blocks approval with clear message", PAY_MSG in r["approval_blockers"])
    p1 = PdfReader(io.BytesIO(requests.get(f"{API}/claims/{cid}/merged", headers=H, timeout=120).content)).pages[0].extract_text()
    check("checklist PDF flags NEEDS STAFF REVIEW", "NEEDS STAFF REVIEW" in p1)

    r = upload("scan_both.jpg", as_jpg(scan({"provider", "veteran"})), "image/jpeg")
    check("CASE 4 both boxes marked -> staff review", r.get("payment_to") is None and r.get("payment_review"))

    r = requests.put(f"{API}/claims/{cid}/payment-recipient", headers=H, json={"payment_to": "veteran"}).json()
    check("staff confirms Veteran -> blocker cleared", r["payment_to"] == "veteran" and r["payment_to_source"] == "staff_confirmed"
          and PAY_MSG not in r["approval_blockers"])
    check("invalid staff choice rejected",
          requests.put(f"{API}/claims/{cid}/payment-recipient", headers=H, json={"payment_to": "both"}).status_code == 400)
    check("exactly one cover sheet in packet", sum(i["category"] == "cover_sheet" for i in r["items"]) == 1)
finally:
    db.claim_packets.delete_many({"id": cid})
print("ALL PASS" if ok else "SOME FAILED")
