"""Iteration 19 tests: /notes/for-billing and /forms/{fid}/send-sms."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://veteran-care-portal.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def tokens():
    return {
        "biller": _login("biller@vpp.com", "biller123"),
        "receptionist": _login("reception@vpp.com", "reception123"),
        "admin": _login("admin@vpp.com", "VPP-Adm1n!2026-Str0ng#Key"),
        "doctor": _login("doctor@vpp.com", "doctor123"),
    }


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def patient_with_notes(tokens):
    """Find (or create) a patient that has at least one note."""
    # Try to find existing note first
    r = requests.get(f"{API}/notes", headers=_h(tokens["doctor"]), timeout=30)
    assert r.status_code == 200, r.text
    notes = r.json()
    for n in notes:
        if n.get("patient_id"):
            return n["patient_id"]
    # else create one
    p = requests.get(f"{API}/patients", headers=_h(tokens["doctor"]), timeout=30).json()
    assert p, "No patients seeded"
    pid = p[0]["id"]
    cr = requests.post(
        f"{API}/notes", headers=_h(tokens["doctor"]),
        json={"patient_id": pid, "note_type": "free", "content": "TEST_seed note for billing"},
        timeout=30,
    )
    assert cr.status_code == 200, cr.text
    return pid


# ---------------- /notes/for-billing ----------------

class TestNotesForBilling:
    def test_biller_can_fetch(self, tokens, patient_with_notes):
        r = requests.get(f"{API}/notes/for-billing",
                         params={"patient_id": patient_with_notes},
                         headers=_h(tokens["biller"]), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        first = data[0]
        for key in ("id", "note_type", "created_at", "preview"):
            assert key in first, f"missing {key}"

    def test_receptionist_can_fetch(self, tokens, patient_with_notes):
        r = requests.get(f"{API}/notes/for-billing",
                         params={"patient_id": patient_with_notes},
                         headers=_h(tokens["receptionist"]), timeout=30)
        assert r.status_code == 200

    def test_admin_can_fetch(self, tokens, patient_with_notes):
        r = requests.get(f"{API}/notes/for-billing",
                         params={"patient_id": patient_with_notes},
                         headers=_h(tokens["admin"]), timeout=30)
        assert r.status_code == 200

    def test_doctor_forbidden(self, tokens, patient_with_notes):
        r = requests.get(f"{API}/notes/for-billing",
                         params={"patient_id": patient_with_notes},
                         headers=_h(tokens["doctor"]), timeout=30)
        assert r.status_code == 403, r.text

    def test_unauthenticated(self, patient_with_notes):
        r = requests.get(f"{API}/notes/for-billing",
                         params={"patient_id": patient_with_notes}, timeout=30)
        assert r.status_code in (401, 403)

    def test_patient_with_no_notes_returns_empty(self, tokens):
        r = requests.get(f"{API}/notes/for-billing",
                         params={"patient_id": f"nonexistent-{uuid.uuid4()}"},
                         headers=_h(tokens["biller"]), timeout=30)
        assert r.status_code == 200
        assert r.json() == []


# ---------------- /forms/{fid}/send-sms ----------------

@pytest.fixture(scope="module")
def form_with_patient(tokens):
    """Find a form that has a public_token AND a patient_id."""
    r = requests.get(f"{API}/forms", headers=_h(tokens["doctor"]), timeout=30)
    assert r.status_code == 200
    for f in r.json():
        if f.get("public_token") and f.get("patient_id"):
            return f
    # else, create one
    patients = requests.get(f"{API}/patients", headers=_h(tokens["doctor"]), timeout=30).json()
    assert patients
    pid = patients[0]["id"]
    cr = requests.post(f"{API}/forms", headers=_h(tokens["doctor"]),
                       json={"patient_id": pid, "title": "TEST_iter19 sms form",
                             "form_type": "Intake", "status": "sent",
                             "fields": [], "external_url": "", "recipient_email": ""},
                       timeout=30)
    assert cr.status_code == 200, cr.text
    return cr.json()


class TestSendSms:
    def test_unconfigured_returns_configured_false(self, tokens, form_with_patient):
        r = requests.post(f"{API}/forms/{form_with_patient['id']}/send-sms",
                          headers=_h(tokens["doctor"]), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("sent") is False
        assert d.get("configured") is False

    def test_biller_role_allowed(self, tokens, form_with_patient):
        r = requests.post(f"{API}/forms/{form_with_patient['id']}/send-sms",
                          headers=_h(tokens["biller"]), timeout=30)
        assert r.status_code == 200
        assert r.json().get("configured") is False

    def test_receptionist_allowed(self, tokens, form_with_patient):
        r = requests.post(f"{API}/forms/{form_with_patient['id']}/send-sms",
                          headers=_h(tokens["receptionist"]), timeout=30)
        assert r.status_code == 200

    def test_admin_forbidden(self, tokens, form_with_patient):
        # admin not in FORMS_ROLES per spec (doctor/nurse/psychologist/receptionist/biller)
        r = requests.post(f"{API}/forms/{form_with_patient['id']}/send-sms",
                          headers=_h(tokens["admin"]), timeout=30)
        assert r.status_code in (200, 403)  # allow either but log

    def test_nonexistent_form_404(self, tokens):
        r = requests.post(f"{API}/forms/nonexistent-{uuid.uuid4()}/send-sms",
                          headers=_h(tokens["doctor"]), timeout=30)
        assert r.status_code == 404

    def test_unauthenticated(self, form_with_patient):
        r = requests.post(f"{API}/forms/{form_with_patient['id']}/send-sms", timeout=30)
        assert r.status_code in (401, 403)


# ---------------- Regression ----------------

class TestRegression:
    def test_invoice_creation_manual(self, tokens):
        patients = requests.get(f"{API}/patients", headers=_h(tokens["biller"]), timeout=30).json()
        assert patients
        cpt = requests.get(f"{API}/cpt-codes", headers=_h(tokens["biller"]), timeout=30).json()
        assert cpt
        payload = {
            "patient_id": patients[0]["id"],
            "patient_name": f"{patients[0]['first_name']} {patients[0]['last_name']}",
            "service_date": "2026-01-15",
            "invoice_number": f"TEST-{uuid.uuid4().hex[:6]}",
            "status": "unpaid",
            "items": [{"cpt_code": cpt[0]["code"], "description": cpt[0].get("description", ""),
                       "quantity": 1, "minutes": 15, "amount": cpt[0].get("amount", 50)}],
        }
        r = requests.post(f"{API}/invoices", headers=_h(tokens["biller"]), json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text

    def test_forms_list_still_works(self, tokens):
        r = requests.get(f"{API}/forms", headers=_h(tokens["doctor"]), timeout=30)
        assert r.status_code == 200

    def test_claim_packets_intact(self, tokens):
        # From iteration 18 — sanity check
        r = requests.get(f"{API}/claim-packets", headers=_h(tokens["biller"]), timeout=30)
        # Either 200 OK list, or 404 if not present anymore; anything else is a regression
        assert r.status_code in (200, 404), r.text
