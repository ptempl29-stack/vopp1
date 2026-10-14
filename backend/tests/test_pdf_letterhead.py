import io
import sys
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from pypdf import PdfReader  # noqa: E402
from core.folder_filing import invoice_pdf, note_pdf  # noqa: E402
from routers.claims import _invoice_pdf  # noqa: E402

S = {"clinic_name": "Veterans of Puerto Plata", "tagline": "Health Clinic", "rnc": "1-33-79564-7",
     "address": "Calle 5 #32, Edificio Largo Nombre, Sector Centro Historico, Puerto Plata, Republica Dominicana",
     "phone": "+1 (809) 555-0100", "whatsapp": "+1 809 555 0199", "email": "info@vpp-clinic.com",
     "mailing_address": "PO Box 123, Puerto Plata", "primary_insurance": "VA FMP"}
HEADER = ["Veterans of Puerto Plata", "Health Clinic", "RNC: 1-33-79564-7", "Republica Dominicana",
          "+1 (809) 555-0100", "WhatsApp: +1 809 555 0199", "info@vpp-clinic.com",
          "Mailing Address: PO Box 123", "Primary Insurance: VA FMP"]
inv = {"patient_name": "ZZTEST", "invoice_number": "INV-1", "items": [], "total": 0, "ssn": "111223333"}
note = {"patient_name": "ZZTEST", "visit_date": "2026-01-07", "content": "x", "ssn": "111223333"}
ok = True
for name, data in [("FMP claim invoice PDF", _invoice_pdf(inv, S)), ("folder invoice PDF", invoice_pdf(inv, S)),
                   ("progress note PDF", note_pdf(note, "x", "", S))]:
    txt = " ".join(PdfReader(io.BytesIO(data)).pages[0].extract_text().split())
    missing = [h for h in HEADER if h not in txt]
    ok &= not missing
    print(("PASS " if not missing else "FAIL ") + f"{name} full header" + (f" missing {missing}" if missing else ""))
    open(f"/tmp/{name.split()[0]}.pdf", "wb").write(data)
legacy = " ".join(PdfReader(io.BytesIO(note_pdf(note, "Old Clinic", "9-9"))).pages[0].extract_text().split())
c = "Old Clinic" in legacy and "RNC: 9-9" in legacy and "Progress Note" in legacy
ok &= c
print(("PASS " if c else "FAIL ") + "note PDF without settings still renders clinic + RNC")
print("ALL PASS" if ok else "SOME FAILED")
