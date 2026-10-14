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
from pypdf import PdfReader  # noqa: E402
from core.db import db  # noqa: E402
from core.ssn import format_ssn, with_patient_ssn  # noqa: E402
from core.folder_filing import invoice_pdf, note_pdf  # noqa: E402
from routers.claims import _invoice_pdf  # noqa: E402

text = lambda b: " ".join(p.extract_text() for p in PdfReader(io.BytesIO(b)).pages)  # noqa: E731


async def main():
    ok = True

    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + name)

    a, b, c = (f"ZZTEST-SSN-{uuid.uuid4()}" for _ in range(3))
    await db.patients.insert_many([
        {"id": a, "first_name": "ZZTEST", "last_name": "SsnA", "ssn": "111223333"},
        {"id": b, "first_name": "ZZTEST", "last_name": "SsnB", "ssn": "444-55-6666"},
        {"id": c, "first_name": "ZZTEST", "last_name": "SsnC", "ssn": ""}])
    try:
        check("format 9 digits", format_ssn("111223333") == "111-22-3333" and format_ssn("444-55-6666") == "444-55-6666")
        check("non-9-digit shown as entered", format_ssn("12345") == "12345" and format_ssn(None) == "")
        inv_a = {"patient_id": a, "patient_name": "ZZTEST SsnA", "ssn": "999-99-9999", "items": [], "total": 0}
        r = await with_patient_ssn(inv_a)
        check("patient record SSN wins over stale invoice copy", r["ssn"] == "111223333")
        check("original invoice dict not modified", inv_a["ssn"] == "999-99-9999")
        r = await with_patient_ssn({"patient_id": c, "ssn": "777-88-9999"})
        check("falls back to typed SSN when patient has none", r["ssn"] == "777-88-9999")
        r = await with_patient_ssn({"patient_id": b})
        check("each invoice uses only its own patient", r["ssn"] == "444-55-6666")
        t1 = text(_invoice_pdf(await with_patient_ssn(inv_a), {"clinic_name": "VOPP", "rnc": "1-23"}))
        check("FMP invoice PDF shows full SSN", "111-22-3333" in t1 and "***" not in t1 and "444-55-6666" not in t1)
        check("FMP invoice PDF keeps RNC", "1-23" in t1)
        t2 = text(invoice_pdf(await with_patient_ssn({**inv_a, "patient_id": b}), {"clinic_name": "VOPP"}))
        check("folder invoice PDF shows full SSN of its patient", "444-55-6666" in t2 and "111-22-3333" not in t2)
        t3 = text(note_pdf({"patient_name": "ZZTEST SsnA", "dob": "1970-01-01", "ssn": "111223333",
                            "visit_date": "2026-01-07", "content": "x"}, "VOPP"))
        check("note PDF has SSN line", "SSN:" in t3 and "111-22-3333" in t3)
        api = os.environ["REACT_APP_BACKEND_URL"] + "/api"
        check("patient SSN requires login", requests.get(f"{api}/patients/{a}").status_code == 401)
    finally:
        await db.patients.delete_many({"id": {"$in": [a, b, c]}})
    print("ALL PASS" if ok else "SOME FAILED")


asyncio.run(main())
