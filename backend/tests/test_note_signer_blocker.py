import asyncio
import io
import os
import sys
import uuid
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from routers.claims import _approval_blockers  # noqa: E402
from core.folder_filing import note_pdf  # noqa: E402

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
API = os.environ["REACT_APP_BACKEND_URL"] + "/api"
SIG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


pid = db.patients.find_one({"first_name": "ZZTEST", "last_name": "Smoke"})["id"]
nid = f"zz-note-{uuid.uuid4()}"
# legacy-shaped note like production: names only, signed by an admin account, no ids
db.notes.insert_one({"id": nid, "patient_id": pid, "title": "ZZTEST legacy", "content": "x", "visit_date": "2026-03-03",
                     "attending_provider": "ZZTEST Psych", "signed_by": "CEO", "author": "CEO", "signature": SIG,
                     "signed_at": "2026-03-03T10:00:00", "completed": True, "completed_at": "2026-03-03T10:00:00"})
claim = {"patient_id": pid, "items": [{"source": "note", "note_id": nid, "category": "progress_note"},
                                      {"source": "note", "note_id": "zz-missing-note", "category": "progress_note"}]}
LOOP = asyncio.new_event_loop()
try:
    b = LOOP.run_until_complete(_approval_blockers(claim))
    check("admin-signed note blocked with names", any("signed by CEO, but it must be signed by its attending provider, ZZTEST Psych" in x for x in b))
    check("deleted note link flagged", "Attached progress note no longer exists — re-attach." in b)
    before = db.notes.find_one({"id": nid}, {"_id": 0})
    check("blocker check changed no data", before["signed_by"] == "CEO" and before["signature"] == SIG and "signed_by_id" not in before)
    db.notes.update_one({"id": nid}, {"$set": {"attending_provider": "Nobody Known"}})
    b = LOOP.run_until_complete(_approval_blockers({**claim, "items": claim["items"][:1]}))
    check("unmatched attending provider explained", any("does not match a clinical provider account" in x for x in b))
    db.notes.update_one({"id": nid}, {"$set": {"attending_provider": "ZZTEST Psych"}})
    # the attending provider signs it herself
    tok = requests.post(f"{API}/auth/login", json={"email": "zztest.psych@example.com", "password": "ZZtest-2026!"}).json()["token"]
    n = db.notes.find_one({"id": nid}, {"_id": 0})
    body = {k: n.get(k) for k in ("patient_id", "title", "content", "visit_date", "attending_provider")}
    r = requests.put(f"{API}/notes/{nid}", headers={"Authorization": f"Bearer {tok}"}, json={**body, "signature": SIG.replace("A60e6kg", "A60e6kh")})
    check(f"attending provider can re-sign ({r.status_code})", r.status_code == 200)
    n = db.notes.find_one({"id": nid}, {"_id": 0})
    check("signer now recorded by account id", n.get("signed_by") == "ZZTEST Psych" and n.get("signed_by_id"))
    db.notes.update_one({"id": nid}, {"$set": {"completed": True}})
    b = LOOP.run_until_complete(_approval_blockers({**claim, "items": claim["items"][:1]}))
    check("no signer blocker after provider signs", not any("signed" in x.lower() for x in b))
    pdf = note_pdf(db.notes.find_one({"id": nid}, {"_id": 0}), "VOPP")
    import fitz
    check("signature image embedded in note PDF", len(fitz.open(stream=pdf, filetype="pdf")[0].get_images()) >= 1)
finally:
    db.notes.delete_many({"id": nid})
    db.note_versions.delete_many({"note_id": nid})
print("ALL PASS" if ok else "SOME FAILED")
