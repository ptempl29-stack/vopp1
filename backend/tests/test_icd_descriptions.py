import asyncio
import copy
import io
import sys
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from pypdf import PdfReader  # noqa: E402
from core.icd_codes import with_icd_descriptions  # noqa: E402
from core.folder_filing import invoice_pdf  # noqa: E402
from routers.claims import _invoice_pdf  # noqa: E402

PTSD, MDD = "Post-traumatic stress disorder, unspecified", "Major depressive disorder, single episode, unspecified"
txt = lambda b: "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(b)).pages)  # noqa: E731


async def main():
    ok = True

    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + name)

    inv = {"patient_name": "ZZTEST", "invoice_number": "INV-ZZ", "icd10": "F43.10, F32.9; 7eth", "total": 300.0,
           "items": [{"cpt_code": "90837", "description": "Psychotherapy 60 min", "quantity": 2, "amount": 150.0, "minutes": 60}]}
    orig = copy.deepcopy(inv)
    r = await with_icd_descriptions(inv)
    check("each code followed by its own description", r["icd10"].split("\n") == ["F43.10", PTSD, "F32.9", MDD, "7eth"])
    check("code without description shown alone (no guess)", r["icd10"].endswith("7eth"))
    check("original invoice untouched (amounts/CPT/data)", inv == orig)
    check("single code", (await with_icd_descriptions({"icd10": "F43.10"}))["icd10"] == f"F43.10\n{PTSD}")
    check("empty code unchanged", (await with_icd_descriptions({"icd10": ""}))["icd10"] == "")
    for name, pdf in [("FMP claim invoice PDF", _invoice_pdf(r, {})), ("folder invoice PDF", invoice_pdf(r, {}))]:
        t = " ".join(txt(pdf).split())
        check(f"{name}: description beneath each code", f"F43.10 {PTSD}" in t.replace("\n", " ") or
              (t.find("F43.10") < t.find("Post-traumatic") < t.find("F32.9") < t.find("Major depressive") < t.find("7eth")))
        check(f"{name}: CPT and amounts unchanged", "90837" in t and "$150.00" in t and "$300.00" in t)
    print("ALL PASS" if ok else "SOME FAILED")


asyncio.run(main())
