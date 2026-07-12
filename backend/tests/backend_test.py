"""Backend tests for Veterans of Puerto Plata."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].splitlines()[0].strip()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "doctor": ("doctor@vpp.com", "doctor123"),
    "nurse": ("nurse@vpp.com", "nurse123"),
    "receptionist": ("reception@vpp.com", "reception123"),
    "biller": ("biller@vpp.com", "biller123"),
    "admin": ("admin@vpp.com", "VPP-Adm1n!2026-Str0ng#Key"),
}

tokens = {}
users = {}


def login(role):
    if role in tokens:
        return tokens[role]
    email, pw = CREDS[role]
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login {role} failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and "user" in data
    tokens[role] = data["token"]
    users[role] = data["user"]
    return data["token"]


def h(role):
    return {"Authorization": f"Bearer {login(role)}"}


# ----- Auth -----
@pytest.mark.parametrize("role", list(CREDS.keys()))
def test_login_all_roles(role):
    email, pw = CREDS[role]
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["email"] == email
    assert data["user"]["role"] == role


def test_login_invalid():
    r = requests.post(f"{API}/auth/login", json={"email": "x@y.com", "password": "bad"}, timeout=30)
    assert r.status_code == 401


def test_auth_me():
    r = requests.get(f"{API}/auth/me", headers=h("doctor"), timeout=30)
    assert r.status_code == 200
    assert r.json()["email"] == "doctor@vpp.com"


def test_auth_me_no_token():
    r = requests.get(f"{API}/auth/me", timeout=30)
    assert r.status_code == 401


# ----- Patients -----
created_patient_id = None


def test_create_patient_receptionist():
    global created_patient_id
    payload = {"first_name": "TEST_Juan", "last_name": "Perez", "phone": "555-1234"}
    r = requests.post(f"{API}/patients", json=payload, headers=h("receptionist"), timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["first_name"] == "TEST_Juan"
    assert "id" in data
    created_patient_id = data["id"]


def test_list_patients():
    r = requests.get(f"{API}/patients", headers=h("doctor"), timeout=30)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_search_patients():
    r = requests.get(f"{API}/patients?search=TEST_Juan", headers=h("doctor"), timeout=30)
    assert r.status_code == 200
    names = [p["first_name"] for p in r.json()]
    assert any("TEST_Juan" in n for n in names)


def test_update_patient():
    r = requests.put(f"{API}/patients/{created_patient_id}",
                     json={"first_name": "TEST_Juan", "last_name": "Perez-Updated", "phone": "555-9999"},
                     headers=h("receptionist"), timeout=30)
    assert r.status_code == 200
    assert r.json()["last_name"] == "Perez-Updated"


def test_biller_cannot_create_patient():
    r = requests.post(f"{API}/patients", json={"first_name": "TEST_x", "last_name": "y"},
                      headers=h("biller"), timeout=30)
    assert r.status_code == 403


# ----- Appointments -----
created_appt_id = None


def test_create_appointment():
    global created_appt_id
    r = requests.post(f"{API}/appointments",
                      json={"patient_id": created_patient_id, "date": "2026-01-20", "time": "10:00", "reason": "checkup"},
                      headers=h("receptionist"), timeout=30)
    assert r.status_code == 200
    created_appt_id = r.json()["id"]


def test_list_appointments_has_patient_name():
    r = requests.get(f"{API}/appointments", headers=h("doctor"), timeout=30)
    assert r.status_code == 200
    appts = r.json()
    found = [a for a in appts if a["id"] == created_appt_id]
    assert found and "patient_name" in found[0]
    assert "TEST_Juan" in found[0]["patient_name"]


# ----- Notes -----
def test_create_note_doctor():
    r = requests.post(f"{API}/notes",
                      json={"patient_id": created_patient_id, "title": "Visit", "content": "Patient reports headache."},
                      headers=h("doctor"), timeout=30)
    assert r.status_code == 200


def test_receptionist_cannot_create_note():
    r = requests.post(f"{API}/notes",
                      json={"patient_id": created_patient_id, "title": "x", "content": "y"},
                      headers=h("receptionist"), timeout=30)
    assert r.status_code == 403


def test_summarize_note_success():
    """AI summarize should now return real summary (LLM budget recharged)."""
    r = requests.post(f"{API}/notes/summarize",
                      json={"content": "Patient reports persistent headache for 3 days, worsening at night. Denies fever or vision changes. Taking OTC ibuprofen with minimal relief."},
                      headers=h("doctor"), timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "summary" in data
    assert isinstance(data["summary"], str)
    assert len(data["summary"]) > 10


def test_summarize_note_forbidden_for_biller():
    r = requests.post(f"{API}/notes/summarize",
                      json={"content": "hi"},
                      headers=h("biller"), timeout=30)
    assert r.status_code == 403


# ----- Invoices -----
def test_cpt_codes():
    r = requests.get(f"{API}/cpt-codes", headers=h("biller"), timeout=30)
    assert r.status_code == 200
    codes = r.json()
    assert len(codes) >= 5
    assert all("code" in c and "amount" in c for c in codes)


created_invoice_id = None


def test_create_invoice_biller():
    global created_invoice_id
    items = [
        {"cpt_code": "99213", "description": "Est visit", "amount": 90.0, "quantity": 1},
        {"cpt_code": "85025", "description": "CBC", "amount": 40.0, "quantity": 2},
    ]
    r = requests.post(f"{API}/invoices",
                      json={"patient_id": created_patient_id, "items": items},
                      headers=h("biller"), timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 170.0
    created_invoice_id = data["id"]


def test_mark_invoice_paid():
    r = requests.put(f"{API}/invoices/{created_invoice_id}/status?status=paid",
                     headers=h("biller"), timeout=30)
    assert r.status_code == 200
    assert r.json()["status"] == "paid"


# ----- Forms -----
created_form_id = None


public_token_holder = {}

def test_create_form():
    global created_form_id
    r = requests.post(f"{API}/forms",
                      json={"patient_id": created_patient_id, "title": "Intake", "form_type": "Intake"},
                      headers=h("receptionist"), timeout=30)
    assert r.status_code == 200
    data = r.json()
    created_form_id = data["id"]
    # New public form fields
    assert "public_token" in data and isinstance(data["public_token"], str) and len(data["public_token"]) >= 16
    assert isinstance(data.get("template"), list) and len(data["template"]) == 6
    assert data.get("responses") is None
    public_token_holder["token"] = data["public_token"]


def test_public_get_form_unauth():
    tok = public_token_holder["token"]
    r = requests.get(f"{API}/public/forms/{tok}", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["form_type"] == "Intake"
    assert len(d["template"]) == 6
    assert d["status"] != "received"


def test_public_get_form_bad_token():
    r = requests.get(f"{API}/public/forms/badtoken_xyz", timeout=30)
    assert r.status_code == 404


def test_public_submit_form_unauth():
    tok = public_token_holder["token"]
    r = requests.post(f"{API}/public/forms/{tok}/submit",
                     json={"responses": {"full_name": "TEST_Patient", "dob": "1990-01-01", "reason": "cough"}},
                     timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True


def test_public_submit_resubmit_blocked():
    tok = public_token_holder["token"]
    r = requests.post(f"{API}/public/forms/{tok}/submit",
                     json={"responses": {"full_name": "x"}}, timeout=30)
    assert r.status_code == 400
    assert "already" in (r.json().get("detail", "").lower())


def test_form_status_received_after_submit():
    r = requests.get(f"{API}/forms", headers=h("doctor"), timeout=30)
    assert r.status_code == 200
    found = [f for f in r.json() if f["id"] == created_form_id]
    assert found and found[0]["status"] == "received"
    assert found[0].get("responses", {}).get("full_name") == "TEST_Patient"


def test_list_forms_has_patient_name():
    r = requests.get(f"{API}/forms", headers=h("doctor"), timeout=30)
    assert r.status_code == 200
    forms = r.json()
    found = [f for f in forms if f["id"] == created_form_id]
    assert found and "patient_name" in found[0]


def test_mark_form_received():
    r = requests.put(f"{API}/forms/{created_form_id}/status?status=received",
                     headers=h("receptionist"), timeout=30)
    assert r.status_code == 200


# ----- Messages -----
created_msg_id = None


def test_send_message():
    global created_msg_id
    # get user ids
    login("doctor"); login("nurse")
    nurse_id = users["nurse"]["id"]
    r = requests.post(f"{API}/messages",
                      json={"to_user_id": nurse_id, "subject": "hi", "body": "hello"},
                      headers=h("doctor"), timeout=30)
    assert r.status_code == 200
    created_msg_id = r.json()["id"]


def test_recipient_inbox():
    r = requests.get(f"{API}/messages", headers=h("nurse"), timeout=30)
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()]
    assert created_msg_id in ids


def test_mark_message_read():
    r = requests.put(f"{API}/messages/{created_msg_id}/read", headers=h("nurse"), timeout=30)
    assert r.status_code == 200


# ----- Stats -----
def test_stats():
    r = requests.get(f"{API}/stats", headers=h("admin"), timeout=30)
    assert r.status_code == 200
    keys = {"patients", "appointments_today", "appointments_total", "pending_notes",
            "unpaid_invoices", "pending_forms", "unread_messages"}
    assert keys.issubset(r.json().keys())


# ----- Cleanup -----
def test_zz_delete_patient():
    r = requests.delete(f"{API}/patients/{created_patient_id}", headers=h("receptionist"), timeout=30)
    assert r.status_code == 200
    g = requests.get(f"{API}/patients/{created_patient_id}", headers=h("doctor"), timeout=30)
    assert g.status_code == 404


def test_zz_delete_appointment():
    r = requests.delete(f"{API}/appointments/{created_appt_id}", headers=h("receptionist"), timeout=30)
    assert r.status_code == 200


# ----- Security: PHI restriction on GET /api/notes -----
def test_notes_get_forbidden_biller():
    r = requests.get(f"{API}/notes", headers=h("biller"), timeout=30)
    assert r.status_code == 403


def test_notes_get_forbidden_receptionist():
    r = requests.get(f"{API}/notes", headers=h("receptionist"), timeout=30)
    assert r.status_code == 403


def test_notes_get_allowed_clinical():
    for role in ("doctor", "nurse", "admin"):
        r = requests.get(f"{API}/notes", headers=h(role), timeout=30)
        assert r.status_code == 200, f"{role} got {r.status_code}"


# ----- Security: Admin strong password + old password rejected -----
def test_admin_old_password_rejected():
    # use unique XFF so we don't lock out the real admin
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@vpp.com", "password": "admin123"},
                      headers={"X-Forwarded-For": "9.9.9.9"},
                      timeout=30)
    assert r.status_code == 401


# ----- Security: Regex DoS safe -----
def test_regex_dos_safe():
    import time
    payload = "(((a+)+)+)"
    t0 = time.time()
    r = requests.get(f"{API}/patients", params={"search": payload}, headers=h("doctor"), timeout=15)
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 5, f"regex search took {elapsed}s"


# ----- Security: Status allowlists -----
def test_invoice_status_invalid_400():
    # create fresh patient+invoice for this test
    p = requests.post(f"{API}/patients", json={"first_name": "TEST_St", "last_name": "Atus"},
                     headers=h("receptionist"), timeout=30).json()
    inv = requests.post(f"{API}/invoices",
                       json={"patient_id": p["id"], "items": [{"cpt_code": "99213", "description": "v", "amount": 10.0, "quantity": 1}]},
                       headers=h("biller"), timeout=30).json()
    r = requests.put(f"{API}/invoices/{inv['id']}/status?status=garbage", headers=h("biller"), timeout=30)
    assert r.status_code == 400
    r2 = requests.put(f"{API}/invoices/{inv['id']}/status?status=paid", headers=h("biller"), timeout=30)
    assert r2.status_code == 200
    # cleanup
    requests.delete(f"{API}/patients/{p['id']}", headers=h("receptionist"), timeout=30)


def test_form_status_invalid_400():
    p = requests.post(f"{API}/patients", json={"first_name": "TEST_Fs", "last_name": "St"},
                     headers=h("receptionist"), timeout=30).json()
    f = requests.post(f"{API}/forms",
                     json={"patient_id": p["id"], "title": "T", "form_type": "Intake"},
                     headers=h("receptionist"), timeout=30).json()
    r = requests.put(f"{API}/forms/{f['id']}/status?status=garbage", headers=h("receptionist"), timeout=30)
    assert r.status_code == 400
    r2 = requests.put(f"{API}/forms/{f['id']}/status?status=received", headers=h("receptionist"), timeout=30)
    assert r2.status_code == 200
    requests.delete(f"{API}/patients/{p['id']}", headers=h("receptionist"), timeout=30)


# ----- Security: Message ownership -----
def test_message_read_non_recipient_404():
    login("doctor"); login("nurse"); login("biller")
    nurse_id = users["nurse"]["id"]
    # doctor sends to nurse
    msg = requests.post(f"{API}/messages",
                       json={"to_user_id": nurse_id, "subject": "own", "body": "test"},
                       headers=h("doctor"), timeout=30).json()
    # biller (non-recipient) tries to mark read
    r = requests.put(f"{API}/messages/{msg['id']}/read", headers=h("biller"), timeout=30)
    assert r.status_code == 404
    # actual recipient succeeds
    r2 = requests.put(f"{API}/messages/{msg['id']}/read", headers=h("nurse"), timeout=30)
    assert r2.status_code == 200


# ----- Security: Brute force lockout (uses unique XFF) -----
def test_brute_force_lockout_returns_429():
    xff_ip = "10.99.88.77"
    email = "bruteforce_target@vpp.com"
    headers = {"X-Forwarded-For": xff_ip, "Content-Type": "application/json"}
    for i in range(5):
        r = requests.post(f"{API}/auth/login",
                         json={"email": email, "password": "wrongpass"},
                         headers=headers, timeout=30)
        assert r.status_code == 401, f"attempt {i+1} got {r.status_code}"
    # 6th attempt should be 429
    r6 = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": "wrongpass"},
                      headers=headers, timeout=30)
    assert r6.status_code == 429, r6.text


def test_different_account_still_logs_in_after_lockout():
    # Even after locking out one identifier, a fresh account/IP works
    r = requests.post(f"{API}/auth/login",
                     json={"email": "doctor@vpp.com", "password": "doctor123"},
                     headers={"X-Forwarded-For": "10.99.88.66"},
                     timeout=30)
    assert r.status_code == 200


# ----- CPT Codes Module -----
_cpt_created_id = {}


def test_cpt_list_seeded():
    r = requests.get(f"{API}/cpt-codes", headers=h("biller"), timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 10
    codes = [c["code"] for c in data]
    assert "99213" in codes


def test_cpt_create_biller():
    payload = {"code": f"TEST{uuid.uuid4().hex[:5].upper()}", "description": "TEST_service", "amount": 42.5}
    r = requests.post(f"{API}/cpt-codes", json=payload, headers=h("biller"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["code"] == payload["code"]
    _cpt_created_id["id"] = d["id"]
    _cpt_created_id["code"] = d["code"]


def test_cpt_create_duplicate_400():
    payload = {"code": _cpt_created_id["code"], "description": "dup", "amount": 1.0}
    r = requests.post(f"{API}/cpt-codes", json=payload, headers=h("biller"), timeout=30)
    assert r.status_code == 400


def test_cpt_create_forbidden_doctor():
    r = requests.post(f"{API}/cpt-codes",
                     json={"code": "TEST_FORBID", "description": "x", "amount": 1.0},
                     headers=h("doctor"), timeout=30)
    assert r.status_code == 403


def test_cpt_create_forbidden_receptionist():
    r = requests.post(f"{API}/cpt-codes",
                     json={"code": "TEST_FORBID2", "description": "x", "amount": 1.0},
                     headers=h("receptionist"), timeout=30)
    assert r.status_code == 403


def test_cpt_edit():
    r = requests.put(f"{API}/cpt-codes/{_cpt_created_id['id']}",
                    json={"code": _cpt_created_id["code"], "description": "TEST_updated", "amount": 99.9},
                    headers=h("biller"), timeout=30)
    assert r.status_code == 200
    assert r.json()["description"] == "TEST_updated"
    # verify via GET
    lst = requests.get(f"{API}/cpt-codes", headers=h("biller"), timeout=30).json()
    match = [c for c in lst if c["id"] == _cpt_created_id["id"]]
    assert match and match[0]["amount"] == 99.9


def test_cpt_delete():
    r = requests.delete(f"{API}/cpt-codes/{_cpt_created_id['id']}", headers=h("biller"), timeout=30)
    assert r.status_code == 200
    lst = requests.get(f"{API}/cpt-codes", headers=h("biller"), timeout=30).json()
    assert not any(c["id"] == _cpt_created_id["id"] for c in lst)
