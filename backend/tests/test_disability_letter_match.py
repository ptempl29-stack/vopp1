import asyncio
import uuid
import sys
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from core.db import db  # noqa: E402
from routers.claims import _disability_letter_candidates, _auto_attach_credentials  # noqa: E402

P = lambda: f"ZZTEST-{uuid.uuid4()}"  # noqa: E731


async def fi(pid, **kw):
    doc = {"id": str(uuid.uuid4()), "patient_id": pid, "storage_path": f"vpp-clinic-preview/zztest/{uuid.uuid4()}.pdf",
           "content_type": "application/pdf", "created_at": "2026-06-01T00:00:00", **kw}
    await db.folder_items.insert_one(dict(doc))
    return doc


async def main():
    pids, ok = [], True

    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + name)

    # 1 scan filename, letter identified only by label
    a = P(); pids.append(a)
    await fi(a, filename="scan0001.pdf", label="Carta de desglose VA")
    await fi(a, filename="ID_card.pdf", label="ID")
    items = await _auto_attach_credentials([], a, "")
    check("label-only letter attaches", [i["category"] for i in items] == ["va_disability_letter"])
    # 2 explicit category tag with neutral filename
    b = P(); pids.append(b)
    await fi(b, filename="document.pdf", label="document", category="va_disability_letter")
    check("category-tagged letter attaches", len(await _auto_attach_credentials([], b, "")) == 1)
    # 3 form-only letter (never moved to folder)
    c = P(); pids.append(c)
    await db.forms.insert_one({"id": str(uuid.uuid4()), "patient_id": c, "form_type": "Disability Breakdown Letter",
                               "title": "Letter", "attachment": {"storage_path": f"vpp-clinic-preview/zztest/{uuid.uuid4()}.pdf",
                                                                 "filename": "upload.pdf"}})
    items = await _auto_attach_credentials([], c, "")
    check("form-only letter attaches", len(items) == 1 and items[0]["form_id"])
    # 4 ambiguity: two distinct guessed letters -> nothing attached
    d = P(); pids.append(d)
    await fi(d, filename="VA_disability_2024.pdf"); await fi(d, filename="VA_disability_2025.pdf")
    check("ambiguous letters not attached", await _auto_attach_credentials([], d, "") == []
          and len(await _disability_letter_candidates(d)) == 2)
    # 5 explicit beats guessed
    e = P(); pids.append(e)
    await fi(e, filename="old_disability.pdf"); await fi(e, filename="x.pdf", category="va_disability_letter")
    check("explicit wins over guess", len(await _disability_letter_candidates(e)) == 1)
    # 6 never another patient's letter
    f = P(); pids.append(f)
    check("other patient letter never used", await _auto_attach_credentials([], f, "") == [])
    # 7 genuinely missing / other docs not misclassified
    g = P(); pids.append(g)
    await fi(g, filename="Provider_Diploma.pdf", label="diploma - disability clinic"); await fi(g, filename="Claim_Packet_VA_disability.pdf")
    check("invoice/claim-packet not treated as letter", await _disability_letter_candidates(g) == [])
    # 8 same storage already in packet without category -> tagged, not duplicated
    h = P(); pids.append(h)
    doc = await fi(h, filename="scan.pdf", category="va_disability_letter")
    items = await _auto_attach_credentials([{"storage_path": doc["storage_path"], "category": ""}], h, "")
    check("existing item tagged not duplicated", len(items) == 1 and items[0]["category"] == "va_disability_letter")

    await db.folder_items.delete_many({"patient_id": {"$in": pids}})
    await db.forms.delete_many({"patient_id": {"$in": pids}})
    print("ALL PASS" if ok else "SOME FAILED")


asyncio.run(main())
