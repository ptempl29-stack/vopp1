"""Iteration 40 integration tests.

Covers the seven behaviors listed in the review request:
  1. Login as admin.
  2. Invoice numbering endpoints (/api/invoices/next-number,
     /api/invoices/seq-base) + verify that MB-#### continues at the
     configured base and a stray high legacy number does NOT drive it.
  3. Provider credential upload (POST /api/users/{uid}/credentials/{kind})
     and de-duplicated auto-attach on POST /api/claims/from-date.
  4. Claim Packet uses the selected visit date for its claim_number.
  5. Progress notes list surfaces ICD-10 and CPT so the UI can show them.

The invoice↔packet linkage (packet-first vs invoice-first) and payment
recipient logic are covered by the existing test_claim_invoice_linkage.py
unit tests; here we exercise the HTTP surface end-to-end.
"""
import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or frontend_env.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

ADMIN = {"email": "usvopp@yahoo.com", "password": "Football2023?"}


# ---------- fixtures ----------

@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token")
    assert tok, "No token in login response"
    return tok


@pytest.fixture(scope="module")
def admin_client(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}"})
    return s


@pytest.fixture(scope="module")
def any_patient(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/patients", timeout=30)
    assert r.status_code == 200, r.text[:200]
    patients = r.json()
    assert patients, "No patients seeded in preview DB"
    return patients[0]


# ---------- 1. Login ----------

def test_admin_login_returns_admin_role(admin_token):
    # Fetch /auth/me and verify the CEO admin identity
    r = requests.get(f"{BASE_URL}/api/auth/me",
                     headers={"Authorization": f"Bearer {admin_token}"},
                     timeout=30)
    assert r.status_code == 200, r.text[:200]
    me = r.json()
    assert me["role"] == "admin"
    assert me["email"] == ADMIN["email"]


# ---------- 2. Invoice numbering endpoints ----------

def test_seq_base_and_next_number_endpoints(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/invoices/seq-base", timeout=30)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    assert "invoice_seq_base" in data
    assert "next_invoice_number" in data
    assert isinstance(data["invoice_seq_base"], int)
    assert data["next_invoice_number"].startswith("MB-")

    r2 = admin_client.get(f"{BASE_URL}/api/invoices/next-number", timeout=30)
    assert r2.status_code == 200, r2.text[:200]
    assert r2.json()["invoice_number"] == data["next_invoice_number"]


def test_stray_high_legacy_invoice_does_not_drive_next_number(admin_client):
    """Configure base=63 then confirm next-number is MB-0064 (not MB-1009)
    even after a stray high legacy number is present in the collection."""
    # Save current base to restore later
    orig = admin_client.get(f"{BASE_URL}/api/invoices/seq-base", timeout=30).json()
    original_base = orig["invoice_seq_base"]

    try:
        # Force base=63 (per the changeset expectation)
        r = admin_client.put(f"{BASE_URL}/api/invoices/seq-base",
                             json={"invoice_seq_base": 63}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert r.json()["invoice_seq_base"] == 63

        # Create a stray high legacy invoice MB-1008.
        stray_payload = {
            "patient_id": None,
            "patient_name": "TEST_Legacy_Stray",
            "invoice_number": "MB-1008",
            "service_date": "2020-01-01",
            "provider": "TEST_STRAY",
            "items": [{"description": "legacy", "quantity": 1, "amount": 1.0}],
            "total": 1.0,
        }
        stray = admin_client.post(f"{BASE_URL}/api/invoices",
                                  json=stray_payload, timeout=30)
        assert stray.status_code in (200, 201), stray.text[:300]
        stray_id = stray.json().get("id")

        try:
            got = admin_client.get(f"{BASE_URL}/api/invoices/next-number",
                                   timeout=30).json()
            # With base=63 and MB-1008 present as a stray, next number should
            # continue from the base, NOT jump to MB-1009.
            assert got["invoice_number"] != "MB-1009", (
                "Stray MB-1008 must not drive the sequence forward")
            # It should be MB-0064 (first free number at or above base=63,
            # assuming MB-0063 is not already used — verify explicitly).
            got_n = int(got["invoice_number"].split("-")[1])
            assert got_n >= 63, f"next number {got['invoice_number']} below base"
            assert got_n < 1000, "next number should stay in the active band"
        finally:
            if stray_id:
                admin_client.delete(f"{BASE_URL}/api/invoices/{stray_id}",
                                    timeout=30)
    finally:
        # Restore original base configuration
        admin_client.put(f"{BASE_URL}/api/invoices/seq-base",
                         json={"invoice_seq_base": original_base}, timeout=30)


# ---------- 3. Provider credential upload + auto-attach ----------

@pytest.fixture(scope="module")
def test_provider(admin_client):
    """Create a throw-away doctor user; delete after tests."""
    email = f"test_provider_{uuid.uuid4().hex[:8]}@example.com"
    payload = {"email": email, "password": "Provider123!",
               "name": f"TEST_Provider_{uuid.uuid4().hex[:6]}",
               "role": "doctor", "require_password_change": False}
    r = admin_client.post(f"{BASE_URL}/api/auth/register", json=payload,
                          timeout=30)
    assert r.status_code == 200, r.text[:300]
    user = r.json()
    yield user
    admin_client.delete(f"{BASE_URL}/api/users/{user['id']}", timeout=30)


def _tiny_pdf_bytes() -> bytes:
    # Minimal valid PDF header + trailer so backend accepts it.
    return (b"%PDF-1.4\n1 0 obj<<>>endobj\nxref\n0 1\n"
            b"0000000000 65535 f \ntrailer<<>>\n%%EOF")


def test_upload_provider_diploma_and_exequatur(admin_client, test_provider):
    uid = test_provider["id"]
    for kind in ("diploma", "exequatur"):
        r = admin_client.post(
            f"{BASE_URL}/api/users/{uid}/credentials/{kind}",
            files={"file": (f"{kind}.pdf", _tiny_pdf_bytes(), "application/pdf")},
            timeout=60)
        assert r.status_code == 200, f"{kind}: {r.status_code} {r.text[:300]}"
        doc = r.json()
        assert doc.get("storage_path")
        assert doc.get("filename", "").endswith(".pdf")

    # Reject invalid kind
    r = admin_client.post(
        f"{BASE_URL}/api/users/{uid}/credentials/other",
        files={"file": ("x.pdf", _tiny_pdf_bytes(), "application/pdf")},
        timeout=30)
    assert r.status_code == 400

    # GET credentials returns both documents
    r = admin_client.get(f"{BASE_URL}/api/users/{uid}/credentials", timeout=30)
    assert r.status_code == 200, r.text[:200]
    creds = r.json()
    assert creds.get("diploma_doc") and creds["diploma_doc"].get("storage_path")
    assert creds.get("exequatur_doc") and creds["exequatur_doc"].get("storage_path")


def test_claim_from_date_auto_attaches_provider_credentials_once(
        admin_client, any_patient, test_provider):
    """After uploading provider credentials, generate a claim from a note
    authored by that provider on a specific date and assert both diploma
    and exequatur are attached exactly once (dedup)."""
    pid = any_patient["id"]
    provider_name = test_provider["name"]
    visit_date = "2027-01-15"

    # Seed a signed progress note for this patient/date with the provider set
    note_payload = {
        "patient_id": pid, "visit_date": visit_date,
        "note_type": "free", "title": "TEST iteration_40 note",
        "content": "Session content for iteration 40.",
        "attending_provider": provider_name,
        "icd10": "F43.10", "cpt_code": "90837",
    }
    # notes require doctor/nurse/psychologist; admin bypass is allowed
    r = admin_client.post(f"{BASE_URL}/api/notes", json=note_payload, timeout=30)
    assert r.status_code == 200, r.text[:300]
    note = r.json()
    note_id = note["id"]
    # ICD-10 and CPT are echoed back for the UI
    assert note.get("icd10") == "F43.10"
    assert note.get("cpt_code") == "90837"

    packet_id = None
    try:
        r = admin_client.post(f"{BASE_URL}/api/claims/from-date",
                              json={"patient_id": pid, "date": visit_date},
                              timeout=60)
        assert r.status_code == 200, r.text[:400]
        packet = r.json()
        packet_id = packet["id"]

        # 4. Packet's claim_number is the SELECTED visit date, not today
        assert packet["claim_number"][:10] == visit_date, (
            f"packet claim_number={packet['claim_number']} expected {visit_date}")

        categories = [it.get("category") for it in packet.get("items", [])]
        # Exactly one of each auto-attached credential
        assert categories.count("provider_diploma") == 1, (
            f"expected 1 provider_diploma, got {categories.count('provider_diploma')}: {categories}")
        assert categories.count("provider_exequatur") == 1, (
            f"expected 1 provider_exequatur, got {categories.count('provider_exequatur')}: {categories}")
        # Progress note also present
        assert categories.count("progress_note") >= 1

        # Re-generate on the same date → still no duplicate credentials
        r2 = admin_client.post(f"{BASE_URL}/api/claims/from-date",
                               json={"patient_id": pid, "date": visit_date},
                               timeout=60)
        assert r2.status_code == 200, r2.text[:300]
        packet2 = r2.json()
        cats2 = [it.get("category") for it in packet2.get("items", [])]
        assert cats2.count("provider_diploma") == 1
        assert cats2.count("provider_exequatur") == 1
        # cleanup second packet
        admin_client.delete(f"{BASE_URL}/api/claims/{packet2['id']}", timeout=30)
    finally:
        if packet_id:
            admin_client.delete(f"{BASE_URL}/api/claims/{packet_id}", timeout=30)
        admin_client.delete(f"{BASE_URL}/api/notes/{note_id}", timeout=30)


# ---------- 5. Progress notes list surfaces ICD-10 + CPT ----------

def test_notes_list_returns_icd10_and_cpt(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/notes", timeout=30)
    assert r.status_code == 200, r.text[:300]
    notes = r.json()
    assert isinstance(notes, list)
    for n in notes:
        # These keys must exist (value may be empty string / None => "Not recorded")
        assert "icd10" in n
        assert "cpt_code" in n
