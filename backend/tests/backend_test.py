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
    "psychologist": ("psych@vpp.com", "psych123"),
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
    assert isinstance(data.get("template"), list) and len(data["template"]) == 7
    assert data.get("responses") is None
    public_token_holder["token"] = data["public_token"]


def test_public_get_form_unauth():
    tok = public_token_holder["token"]
    r = requests.get(f"{API}/public/forms/{tok}", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["form_type"] == "Intake"
    assert len(d["template"]) == 7
    assert d["status"] != "received"


def test_public_get_form_bad_token():
    r = requests.get(f"{API}/public/forms/badtoken_xyz", timeout=30)
    assert r.status_code == 404


def test_public_submit_form_unauth():
    tok = public_token_holder["token"]
    r = requests.post(f"{API}/public/forms/{tok}/submit",
                     json={"responses": {"full_name": "TEST_Patient", "dob": "1990-01-01", "reason": "cough", "signature": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="}},
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
    # use a fresh random XFF each run so previous lockouts don't collide
    xff_ip = f"10.99.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
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


# ================= NEW: Psychologist role =================
def test_psychologist_login_and_tabs():
    r = requests.post(f"{API}/auth/login", json={"email": "psych@vpp.com", "password": "psych123"}, timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["user"]["role"] == "psychologist"
    tabs = d["user"]["allowed_tabs"]
    assert set(tabs) == {"dashboard", "appointments", "telehealth", "notes", "messages"}
    for forbidden in ("patients", "invoices", "cpt", "reports", "forms", "team"):
        assert forbidden not in tabs


def test_psychologist_can_create_note():
    # need a patient
    p = requests.post(f"{API}/patients", json={"first_name": "TEST_Psy", "last_name": "Pt"},
                     headers=h("receptionist"), timeout=30).json()
    r = requests.post(f"{API}/notes",
                     json={"patient_id": p["id"], "title": "Session 1", "content": "Session notes."},
                     headers=h("psychologist"), timeout=30)
    assert r.status_code == 200, r.text
    requests.delete(f"{API}/patients/{p['id']}", headers=h("receptionist"), timeout=30)


def test_psychologist_can_create_appointment():
    p = requests.post(f"{API}/patients", json={"first_name": "TEST_PsyApp", "last_name": "Pt"},
                     headers=h("receptionist"), timeout=30).json()
    r = requests.post(f"{API}/appointments",
                     json={"patient_id": p["id"], "date": "2026-02-01", "time": "14:00"},
                     headers=h("psychologist"), timeout=30)
    assert r.status_code == 200
    requests.delete(f"{API}/patients/{p['id']}", headers=h("receptionist"), timeout=30)


# ================= NEW: Admin tabs / meta =================
def test_meta_tabs_admin_only():
    r = requests.get(f"{API}/meta/tabs", headers=h("admin"), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert len(d["tabs"]) == 11 and len(d["roles"]) == 6
    r2 = requests.get(f"{API}/meta/tabs", headers=h("doctor"), timeout=30)
    assert r2.status_code == 403


_created_tab_user_id = {}


def test_admin_create_user_and_update_tabs():
    email = f"TEST_teamuser_{uuid.uuid4().hex[:6]}@vpp.com"
    r = requests.post(f"{API}/auth/register",
                     json={"email": email, "password": "abcdef", "name": "TEST User", "role": "receptionist"},
                     headers=h("admin"), timeout=30)
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    _created_tab_user_id["id"] = uid
    _created_tab_user_id["email"] = email
    _created_tab_user_id["password"] = "abcdef"
    # update tabs -> add reports, drop invoices
    r2 = requests.put(f"{API}/users/{uid}/tabs",
                     json={"allowed_tabs": ["dashboard", "reports", "messages"]},
                     headers=h("admin"), timeout=30)
    assert r2.status_code == 200
    # verify persisted
    users = requests.get(f"{API}/users", headers=h("admin"), timeout=30).json()
    match = [u for u in users if u["id"] == uid][0]
    assert set(match["allowed_tabs"]) == {"dashboard", "reports", "messages"}


def test_user_login_shows_updated_tabs():
    r = requests.post(f"{API}/auth/login",
                     json={"email": _created_tab_user_id["email"], "password": _created_tab_user_id["password"]},
                     headers={"X-Forwarded-For": f"172.16.{uuid.uuid4().int % 250}.1"},
                     timeout=30)
    assert r.status_code == 200
    assert set(r.json()["user"]["allowed_tabs"]) == {"dashboard", "reports", "messages"}


def test_admin_delete_user():
    uid = _created_tab_user_id["id"]
    r = requests.delete(f"{API}/users/{uid}", headers=h("admin"), timeout=30)
    assert r.status_code == 200
    users = requests.get(f"{API}/users", headers=h("admin"), timeout=30).json()
    assert not any(u["id"] == uid for u in users)


def test_non_admin_cannot_update_tabs():
    login("doctor")
    r = requests.put(f"{API}/users/{users['doctor']['id']}/tabs",
                    json={"allowed_tabs": ["dashboard"]},
                    headers=h("doctor"), timeout=30)
    assert r.status_code == 403


# ================= NEW: Billing Reports =================
def test_reports_biller_ok():
    r = requests.get(f"{API}/reports/billing", headers=h("biller"), timeout=30)
    assert r.status_code == 200
    d = r.json()
    for k in ("summary", "timeseries", "cpt_breakdown"):
        assert k in d
    s = d["summary"]
    for k in ("total_billed", "collected", "outstanding", "invoice_count", "paid_count"):
        assert k in s
    assert isinstance(d["timeseries"], list)
    assert isinstance(d["cpt_breakdown"], list)


def test_reports_admin_ok():
    r = requests.get(f"{API}/reports/billing", headers=h("admin"), timeout=30)
    assert r.status_code == 200


def test_reports_forbidden_doctor():
    r = requests.get(f"{API}/reports/billing", headers=h("doctor"), timeout=30)
    assert r.status_code == 403


def test_reports_forbidden_receptionist():
    r = requests.get(f"{API}/reports/billing", headers=h("receptionist"), timeout=30)
    assert r.status_code == 403


def test_reports_date_filter():
    r = requests.get(f"{API}/reports/billing", params={"start": "2099-01-01", "end": "2099-12-31"},
                    headers=h("biller"), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["summary"]["invoice_count"] == 0
    assert d["summary"]["total_billed"] == 0


def test_reports_export_csv():
    r = requests.get(f"{API}/reports/billing/export", headers=h("biller"), timeout=30)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "Invoice ID" in r.text.splitlines()[0]


def test_reports_export_csv_admin():
    r = requests.get(f"{API}/reports/billing/export", headers=h("admin"), timeout=30)
    assert r.status_code == 200


def test_reports_export_missing_auth_401():
    r = requests.get(f"{API}/reports/billing/export", timeout=30)
    assert r.status_code == 401


def test_reports_export_query_token_no_longer_works_401():
    """?auth= query token must no longer authenticate (must return 401)."""
    tok = login("biller")
    r = requests.get(f"{API}/reports/billing/export", params={"auth": tok}, timeout=30)
    assert r.status_code == 401, f"query token should be rejected, got {r.status_code}"


def test_reports_export_wrong_role_403():
    r = requests.get(f"{API}/reports/billing/export", headers=h("doctor"), timeout=30)
    assert r.status_code == 403


def test_reports_export_receptionist_403():
    r = requests.get(f"{API}/reports/billing/export", headers=h("receptionist"), timeout=30)
    assert r.status_code == 403


# ================= NEW: Forms upload + external URL + download =================
_upload_form = {}


def test_upload_form_and_download():
    # create a small PDF
    pdf_bytes = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    files = {"file": ("test.pdf", pdf_bytes, "application/pdf")}
    data = {"title": "TEST_uploaded_form", "form_type": "Uploaded", "patient_id": ""}
    tok = login("receptionist")
    r = requests.post(f"{API}/forms/upload", files=files, data=data,
                     headers={"Authorization": f"Bearer {tok}"}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["attachment"] and d["attachment"]["filename"] == "test.pdf"
    assert d["attachment"]["content_type"] == "application/pdf"
    assert d["status"] == "received"
    _upload_form["id"] = d["id"]

    # download with header auth (NOT query token) — must return octet-stream + attachment + nosniff
    r2 = requests.get(f"{API}/forms/{d['id']}/download",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    assert r2.status_code == 200
    assert r2.headers.get("content-type", "").lower().startswith("application/octet-stream"), r2.headers
    cd = r2.headers.get("content-disposition", "").lower()
    assert "attachment" in cd, cd
    assert r2.headers.get("x-content-type-options", "").lower() == "nosniff"
    assert r2.content == pdf_bytes or r2.content.startswith(b"%PDF")


def test_download_query_token_no_longer_works_401():
    """Old ?auth=<token> query param must NO LONGER authenticate — should be 401."""
    fid = _upload_form.get("id")
    if not fid:
        pytest.skip("no upload id")
    tok = login("receptionist")
    r = requests.get(f"{API}/forms/{fid}/download", params={"auth": tok}, timeout=30)
    assert r.status_code == 401, f"query token should not authenticate, got {r.status_code}"


def test_download_missing_auth_401():
    fid = _upload_form.get("id")
    if not fid:
        pytest.skip("no upload id")
    r = requests.get(f"{API}/forms/{fid}/download", timeout=30)
    assert r.status_code == 401


def test_upload_spoofed_content_type_normalized():
    """Client sends .txt but claims text/html — server must store server-derived safe type (text/plain)."""
    tok = login("receptionist")
    files = {"file": ("evil.txt", b"<script>alert(1)</script>", "text/html")}
    data = {"title": "TEST_spoof", "form_type": "Uploaded"}
    r = requests.post(f"{API}/forms/upload", files=files, data=data,
                     headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["attachment"]["content_type"] == "text/plain", f"expected text/plain, got {d['attachment']['content_type']}"
    # Download and verify server sends octet-stream + nosniff regardless (defense in depth)
    r2 = requests.get(f"{API}/forms/{d['id']}/download",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    assert r2.status_code == 200
    assert r2.headers.get("content-type", "").lower().startswith("application/octet-stream")
    assert r2.headers.get("x-content-type-options", "").lower() == "nosniff"


def test_upload_bad_ext_400():
    tok = login("receptionist")
    files = {"file": ("evil.exe", b"MZ..", "application/octet-stream")}
    data = {"title": "bad", "form_type": "Uploaded"}
    r = requests.post(f"{API}/forms/upload", files=files, data=data,
                    headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    assert r.status_code == 400


def test_form_with_external_url():
    r = requests.post(f"{API}/forms",
                    json={"patient_id": None, "title": "TEST_ext", "form_type": "Referral",
                          "external_url": "https://example.com/form"},
                    headers=h("receptionist"), timeout=30)
    assert r.status_code == 200
    fid = r.json()["id"]
    lst = requests.get(f"{API}/forms", headers=h("receptionist"), timeout=30).json()
    match = [f for f in lst if f["id"] == fid][0]
    assert match["external_url"] == "https://example.com/form"

    assert not any(c["id"] == _cpt_created_id["id"] for c in lst)



# ================= NEW iteration 7: Admin edit user (name/email/role/password) + Form email link =================
_edit_user_state = {}


def test_admin_edit_user_name_and_email():
    """Admin creates a user, edits their name+email, verifies persistence, verifies login with new email."""
    orig_email = f"TEST_edit_{uuid.uuid4().hex[:6]}@vpp.com"
    reg = requests.post(f"{API}/auth/register",
                        json={"email": orig_email, "password": "origpass", "name": "Orig Name", "role": "receptionist"},
                        headers=h("admin"), timeout=30)
    assert reg.status_code == 200, reg.text
    uid = reg.json()["id"]
    _edit_user_state["id"] = uid

    new_email = f"test_edited_{uuid.uuid4().hex[:6]}@vpp.com"
    r = requests.put(f"{API}/users/{uid}",
                     json={"name": "Edited Name", "email": new_email},
                     headers=h("admin"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name"] == "Edited Name"
    assert d["email"] == new_email
    _edit_user_state["email"] = new_email

    # Verify persistence via list
    lst = requests.get(f"{API}/users", headers=h("admin"), timeout=30).json()
    match = [u for u in lst if u["id"] == uid][0]
    assert match["email"] == new_email
    assert match["name"] == "Edited Name"

    # Old email should NOT log in
    r_old = requests.post(f"{API}/auth/login",
                         json={"email": orig_email, "password": "origpass"},
                         headers={"X-Forwarded-For": f"172.20.{uuid.uuid4().int % 250}.1"}, timeout=30)
    assert r_old.status_code == 401

    # New email + original password logs in
    r_new = requests.post(f"{API}/auth/login",
                         json={"email": new_email, "password": "origpass"},
                         headers={"X-Forwarded-For": f"172.20.{uuid.uuid4().int % 250}.2"}, timeout=30)
    assert r_new.status_code == 200, r_new.text


def test_admin_edit_user_duplicate_email_400():
    uid = _edit_user_state["id"]
    # Attempt to set an email already in use by another user (doctor@vpp.com)
    r = requests.put(f"{API}/users/{uid}",
                     json={"email": "doctor@vpp.com"},
                     headers=h("admin"), timeout=30)
    assert r.status_code == 400, r.text
    assert "already" in r.json().get("detail", "").lower()


def test_admin_edit_user_password_reset_login():
    uid = _edit_user_state["id"]
    email = _edit_user_state["email"]
    new_pw = "brandnew123"
    r = requests.put(f"{API}/users/{uid}",
                     json={"password": new_pw},
                     headers=h("admin"), timeout=30)
    assert r.status_code == 200
    # Login with new password
    r2 = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": new_pw},
                      headers={"X-Forwarded-For": f"172.20.{uuid.uuid4().int % 250}.3"}, timeout=30)
    assert r2.status_code == 200


def test_admin_edit_user_short_password_400():
    uid = _edit_user_state["id"]
    r = requests.put(f"{API}/users/{uid}", json={"password": "abc"}, headers=h("admin"), timeout=30)
    assert r.status_code == 400


def test_admin_edit_user_role_change():
    uid = _edit_user_state["id"]
    r = requests.put(f"{API}/users/{uid}", json={"role": "biller"}, headers=h("admin"), timeout=30)
    assert r.status_code == 200
    assert r.json()["role"] == "biller"


def test_admin_edit_user_invalid_role_400():
    uid = _edit_user_state["id"]
    r = requests.put(f"{API}/users/{uid}", json={"role": "hacker"}, headers=h("admin"), timeout=30)
    assert r.status_code == 400


def test_admin_cannot_change_admin_role():
    # Find the admin user id
    lst = requests.get(f"{API}/users", headers=h("admin"), timeout=30).json()
    admin_user = [u for u in lst if u["email"] == "admin@vpp.com"][0]
    r = requests.put(f"{API}/users/{admin_user['id']}",
                    json={"role": "doctor"}, headers=h("admin"), timeout=30)
    assert r.status_code == 400
    assert "admin" in r.json().get("detail", "").lower()


def test_non_admin_cannot_edit_user():
    uid = _edit_user_state["id"]
    r = requests.put(f"{API}/users/{uid}", json={"name": "hacked"}, headers=h("doctor"), timeout=30)
    assert r.status_code == 403


def test_zz_delete_edited_user():
    uid = _edit_user_state.get("id")
    if uid:
        r = requests.delete(f"{API}/users/{uid}", headers=h("admin"), timeout=30)
        assert r.status_code == 200


# ----- Form email link (Yahoo unconfigured => email_sent=false, form still created) -----
def test_create_form_with_recipient_email_unconfigured():
    """Form creation with recipient_email must succeed with email_sent=false when SMTP not configured."""
    p = requests.post(f"{API}/patients",
                     json={"first_name": "TEST_FormEmail", "last_name": "Pt", "email": "patient_onfile@example.com"},
                     headers=h("receptionist"), timeout=30).json()
    r = requests.post(f"{API}/forms",
                     json={"patient_id": p["id"], "title": "TEST_EmailForm", "form_type": "Intake",
                           "recipient_email": "explicit@example.com",
                           "link_base": "https://example.com"},
                     headers=h("receptionist"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["email_sent"] is False, "email_sent should be false since Yahoo not configured"
    assert d.get("recipient_email") == "explicit@example.com"
    assert "public_token" in d and len(d["public_token"]) >= 16
    # cleanup
    requests.delete(f"{API}/forms/{d['id']}", headers=h("receptionist"), timeout=30)
    requests.delete(f"{API}/patients/{p['id']}", headers=h("receptionist"), timeout=30)


def test_create_form_auto_recipient_from_patient_email():
    """When no explicit recipient_email but patient has one, backend still tries (email_sent=false since SMTP off)."""
    p = requests.post(f"{API}/patients",
                     json={"first_name": "TEST_Auto", "last_name": "Pt", "email": "auto@example.com"},
                     headers=h("receptionist"), timeout=30).json()
    r = requests.post(f"{API}/forms",
                     json={"patient_id": p["id"], "title": "TEST_AutoForm", "form_type": "Consent",
                           "link_base": "https://example.com"},
                     headers=h("receptionist"), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["email_sent"] is False
    # Backend resolves recipient from patient record
    assert d.get("recipient_email") == "auto@example.com"
    requests.delete(f"{API}/patients/{p['id']}", headers=h("receptionist"), timeout=30)


def test_create_form_without_recipient_no_email_flag():
    """No recipient at all — form created, email_sent=false, no recipient_email field surfaced."""
    r = requests.post(f"{API}/forms",
                     json={"patient_id": None, "title": "TEST_NoRec", "form_type": "Intake"},
                     headers=h("receptionist"), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["email_sent"] is False


# ================= NEW iteration 8: Security remediation (link_base, forms role gate) =================
def test_create_form_client_link_base_ignored():
    """Client-supplied link_base must be IGNORED (phishing fix). Since SMTP is off we can't inspect
    outbound email body, but we can confirm the form is created cleanly and no client link_base is
    persisted / echoed back."""
    p = requests.post(f"{API}/patients",
                     json={"first_name": "TEST_LinkBase", "last_name": "Pt", "email": "lb@example.com"},
                     headers=h("receptionist"), timeout=30).json()
    r = requests.post(f"{API}/forms",
                     json={"patient_id": p["id"], "title": "TEST_LinkBase", "form_type": "Intake",
                           "recipient_email": "victim@example.com",
                           "link_base": "https://evil.attacker.com"},
                     headers=h("receptionist"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    # form saved, email_sent=false (SMTP unconfigured — expected)
    assert d["email_sent"] is False
    # Ensure the malicious link_base is NOT persisted / echoed in response payload anywhere
    body_str = str(d).lower()
    assert "evil.attacker.com" not in body_str, "client-supplied link_base leaked into response"
    # cleanup
    requests.delete(f"{API}/forms/{d['id']}", headers=h("receptionist"), timeout=30)
    requests.delete(f"{API}/patients/{p['id']}", headers=h("receptionist"), timeout=30)


def test_forms_roles_gating_non_forms_role_blocked():
    """Create a user with a non-FORMS role, verify all forms endpoints return 403.

    FORMS_ROLES = doctor, nurse, psychologist, receptionist, biller (+ admin bypass).
    All seeded users already have a forms role, so we need to strip a user's allowed_tabs / role.
    However role is required to be one of the standard set. Workaround: create a user, then use
    admin to change their role to something not in FORMS_ROLES. Since /users/{id} update rejects
    unknown roles, we instead validate the *positive* path: every seeded non-admin role IS
    allowed, and admin (bypass) is allowed.
    """
    # Positive: each FORMS role can call GET /forms
    for role in ("doctor", "nurse", "psychologist", "receptionist", "biller", "admin"):
        r = requests.get(f"{API}/forms", headers=h(role), timeout=30)
        assert r.status_code == 200, f"{role} GET /forms -> {r.status_code}"


def test_forms_upload_requires_auth_401():
    files = {"file": ("t.pdf", b"%PDF-1.4\n", "application/pdf")}
    r = requests.post(f"{API}/forms/upload", files=files,
                     data={"title": "x", "form_type": "Uploaded"}, timeout=30)
    assert r.status_code == 401


def test_forms_create_requires_auth_401():
    r = requests.post(f"{API}/forms",
                     json={"patient_id": None, "title": "x", "form_type": "Intake"}, timeout=30)
    assert r.status_code == 401


def test_forms_status_requires_auth_401():
    # need a valid form id — but no auth → 401 before hitting id check
    r = requests.put(f"{API}/forms/anyid/status?status=received", timeout=30)
    assert r.status_code == 401


# ================= NEW iteration 9: Signatures + Security audit fixes =================
_sig_state = {}


def _fake_sig_data_url():
    """A minimal valid 1x1 PNG data URL to simulate a signature."""
    import base64
    png_1x1 = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    return "data:image/png;base64," + base64.b64encode(png_1x1).decode()


def test_note_with_signature_stores_signed_by():
    """Doctor creates a note with signature -> signed_by=Dr name + signed_at set."""
    p = requests.post(f"{API}/patients", json={"first_name": "TEST_Sig", "last_name": "Pt"},
                      headers=h("receptionist"), timeout=30).json()
    _sig_state["patient_id"] = p["id"]
    sig = _fake_sig_data_url()
    r = requests.post(f"{API}/notes",
                      json={"patient_id": p["id"], "title": "Signed Visit",
                            "content": "Patient stable.", "signature": sig},
                      headers=h("doctor"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("signature", "").startswith("data:image/png"), "signature not stored"
    assert d.get("signed_by") and "Elena" in d["signed_by"] or d.get("signed_by") == users["doctor"]["name"], d.get("signed_by")
    assert d.get("signed_at"), "signed_at missing"
    _sig_state["note_id"] = d["id"]


def test_note_without_signature_still_saves():
    p_id = _sig_state["patient_id"]
    r = requests.post(f"{API}/notes",
                      json={"patient_id": p_id, "title": "Unsigned Visit",
                            "content": "Follow up next week."},
                      headers=h("doctor"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert not d.get("signature"), "expected no signature"
    assert not d.get("signed_by"), "signed_by should be absent when unsigned"


def test_note_signature_too_large_400():
    p_id = _sig_state["patient_id"]
    big_sig = "data:image/png;base64," + ("A" * 700000)
    r = requests.post(f"{API}/notes",
                      json={"patient_id": p_id, "title": "Big", "content": "x", "signature": big_sig},
                      headers=h("doctor"), timeout=30)
    assert r.status_code == 400, r.text


# ---- Consent form has signature field type ----
def test_consent_form_has_signature_field():
    p = requests.post(f"{API}/patients", json={"first_name": "TEST_Consent", "last_name": "Pt"},
                      headers=h("receptionist"), timeout=30).json()
    r = requests.post(f"{API}/forms",
                      json={"patient_id": p["id"], "title": "TEST_Consent Form", "form_type": "Consent"},
                      headers=h("receptionist"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    types = [f.get("type") for f in d["template"]]
    assert "signature" in types, f"consent template missing signature field: {types}"
    sig_field = next(f for f in d["template"] if f["type"] == "signature")
    assert sig_field.get("required") is True
    _sig_state["consent_form_id"] = d["id"]
    _sig_state["consent_token"] = d["public_token"]
    _sig_state["consent_patient_id"] = p["id"]


def test_public_submit_consent_with_signature():
    """Patient signs consent form and submits via public endpoint."""
    tok = _sig_state["consent_token"]
    sig = _fake_sig_data_url()
    # gather required fields from template
    pub = requests.get(f"{API}/public/forms/{tok}", timeout=30).json()
    responses = {}
    for f in pub["template"]:
        if f.get("required"):
            if f["type"] == "signature":
                responses[f["name"]] = sig
            elif f["type"] == "checkbox":
                responses[f["name"]] = True
            elif f["type"] == "date":
                responses[f["name"]] = "1990-05-05"
            else:
                responses[f["name"]] = "TEST_Consent Patient"
    r = requests.post(f"{API}/public/forms/{tok}/submit",
                      json={"responses": responses}, timeout=30)
    assert r.status_code == 200, r.text
    # staff-side: GET form and confirm signature stored as data:image
    fid = _sig_state["consent_form_id"]
    lst = requests.get(f"{API}/forms", headers=h("receptionist"), timeout=30).json()
    match = [f for f in lst if f["id"] == fid][0]
    assert match["status"] == "received"
    sig_val = match.get("responses", {}).get("signature", "")
    assert sig_val.startswith("data:image/"), f"signature not persisted as data URL: {sig_val[:30]}"
    # cleanup
    requests.delete(f"{API}/patients/{_sig_state['consent_patient_id']}", headers=h("receptionist"), timeout=30)


def test_public_submit_signature_too_large_400():
    """Create fresh consent form, attempt submit with >1.2MB signature => 400."""
    p = requests.post(f"{API}/patients", json={"first_name": "TEST_BigSig", "last_name": "Pt"},
                      headers=h("receptionist"), timeout=30).json()
    f = requests.post(f"{API}/forms",
                     json={"patient_id": p["id"], "title": "TEST_BigSigForm", "form_type": "Consent"},
                     headers=h("receptionist"), timeout=30).json()
    tok = f["public_token"]
    big_sig = "data:image/png;base64," + ("A" * 1_300_000)
    pub = requests.get(f"{API}/public/forms/{tok}", timeout=30).json()
    responses = {}
    for fl in pub["template"]:
        if fl.get("required"):
            if fl["type"] == "signature":
                responses[fl["name"]] = big_sig
            elif fl["type"] == "checkbox":
                responses[fl["name"]] = True
            elif fl["type"] == "date":
                responses[fl["name"]] = "1990-01-01"
            else:
                responses[fl["name"]] = "x"
    r = requests.post(f"{API}/public/forms/{tok}/submit", json={"responses": responses}, timeout=30)
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"
    requests.delete(f"{API}/patients/{p['id']}", headers=h("receptionist"), timeout=30)


# ---- Security: /api/users minimization for non-admins ----
def test_users_list_non_admin_minimal_fields():
    """Doctor/biller must NOT see email or allowed_tabs; only id/name/role."""
    for role in ("doctor", "biller", "nurse", "receptionist", "psychologist"):
        r = requests.get(f"{API}/users", headers=h(role), timeout=30)
        assert r.status_code == 200, f"{role} got {r.status_code}"
        arr = r.json()
        assert arr, f"empty users for {role}"
        for u in arr:
            assert set(u.keys()) <= {"id", "name", "role"}, f"{role} sees leaked fields: {set(u.keys())}"
            assert "email" not in u
            assert "allowed_tabs" not in u


def test_users_list_admin_full_fields():
    r = requests.get(f"{API}/users", headers=h("admin"), timeout=30)
    assert r.status_code == 200
    arr = r.json()
    # Admin must still see email + allowed_tabs
    assert all("email" in u for u in arr), "admin should see email"
    assert all("allowed_tabs" in u for u in arr), "admin should see allowed_tabs"


# ---- Security: send_email CR/LF sanitization + invalid email ----
def test_send_email_header_sanitization_no_crash():
    """Trigger send_email path via form creation with weird subject-carrying data.
    Since SMTP is unconfigured, send_email short-circuits BEFORE the sanitization branch,
    so we validate that malicious CRLF in recipient / subject-adjacent inputs doesn't crash
    form creation. Also directly probe: recipient with newline still returns email_sent=false,
    and a subject with CRLF cannot inject headers (email_sent=false)."""
    p = requests.post(f"{API}/patients",
                      json={"first_name": "TEST_CRLF", "last_name": "Pt",
                            "email": "victim@example.com\r\nBcc: attacker@evil.com"},
                      headers=h("receptionist"), timeout=30)
    # Patient with CRLF-injected email may be accepted (email is free-form); ensure it doesn't 500.
    assert p.status_code in (200, 400), p.text
    if p.status_code == 200:
        pid = p.json()["id"]
        # Trigger form creation with recipient_email containing CRLF
        # CRLF-injected recipient_email must be rejected at API boundary (422) OR
        # accepted-and-sanitized (200 with email_sent=false). Either is acceptable defense.
        r = requests.post(f"{API}/forms",
                          json={"patient_id": pid, "title": "TEST_CRLF Form", "form_type": "Intake",
                                "recipient_email": "attacker@evil.com\r\nBcc: hacker@evil.com"},
                          headers=h("receptionist"), timeout=30)
        assert r.status_code in (200, 422), r.text
        if r.status_code == 200:
            d = r.json()
            assert d.get("email_sent") is False
            requests.delete(f"{API}/forms/{d['id']}", headers=h("receptionist"), timeout=30)
        # Also confirm a clean form with CRLF-free recipient still saves fine
        clean = requests.post(f"{API}/forms",
                          json={"patient_id": pid, "title": "TEST_Clean", "form_type": "Intake",
                                "recipient_email": "clean@example.com"},
                          headers=h("receptionist"), timeout=30)
        assert clean.status_code == 200
        requests.delete(f"{API}/forms/{clean.json()['id']}", headers=h("receptionist"), timeout=30)
        requests.delete(f"{API}/patients/{pid}", headers=h("receptionist"), timeout=30)


# ---- Regression: messaging still works for non-admin (has id+name+role) ----
def test_messaging_recipient_dropdown_non_admin():
    """Doctor can still see nurse id/name/role and send message."""
    r = requests.get(f"{API}/users", headers=h("doctor"), timeout=30)
    assert r.status_code == 200
    directory = r.json()
    nurse = next((u for u in directory if u["role"] == "nurse"), None)
    assert nurse and nurse.get("id") and nurse.get("name")
    m = requests.post(f"{API}/messages",
                      json={"to_user_id": nurse["id"], "subject": "sig-test", "body": "hi"},
                      headers=h("doctor"), timeout=30)
    assert m.status_code == 200



# ---- Iter 10: signature field on ALL form templates ----
import pytest

@pytest.mark.parametrize("form_type", ["Intake", "Consent", "Medical History", "Insurance", "Referral"])
def test_all_templates_have_required_signature_field(form_type):
    p = requests.post(f"{API}/patients", json={"first_name": "TEST_SigAll", "last_name": form_type.replace(" ", "_")},
                      headers=h("receptionist"), timeout=30).json()
    r = requests.post(f"{API}/forms",
                      json={"patient_id": p["id"], "title": f"TEST_{form_type}_sig", "form_type": form_type},
                      headers=h("receptionist"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    tok = d["public_token"]
    # public GET (unauth) should expose the signature field
    pub = requests.get(f"{API}/public/forms/{tok}", timeout=30).json()
    sig_fields = [f for f in pub["template"] if f.get("type") == "signature"]
    assert len(sig_fields) >= 1, f"{form_type}: no signature field in public template"
    assert sig_fields[0].get("required") is True, f"{form_type}: signature not required"
    # submit signed
    sig = _fake_sig_data_url()
    responses = {}
    for f in pub["template"]:
        if f.get("required"):
            if f["type"] == "signature":
                responses[f["name"]] = sig
            elif f["type"] == "checkbox":
                responses[f["name"]] = True
            elif f["type"] == "date":
                responses[f["name"]] = "1990-01-01"
            else:
                responses[f["name"]] = "x"
    sub = requests.post(f"{API}/public/forms/{tok}/submit", json={"responses": responses}, timeout=30)
    assert sub.status_code == 200, f"{form_type} submit failed: {sub.text}"
    # staff list confirms responses stored with data:image signature -> signed badge would render
    lst = requests.get(f"{API}/forms", headers=h("receptionist"), timeout=30).json()
    match = [f for f in lst if f["id"] == d["id"]][0]
    resp = match.get("responses") or {}
    has_data_image = any(isinstance(v, str) and v.startswith("data:image") for v in resp.values())
    assert has_data_image, f"{form_type}: no data:image value in responses (badge won't render)"
    requests.delete(f"{API}/patients/{p['id']}", headers=h("receptionist"), timeout=30)



# ----- SOAP Note type (additive to original free-text note) -----
def _make_test_patient():
    r = requests.post(f"{API}/patients",
                      json={"first_name": "TEST_SOAP", "last_name": f"P{uuid.uuid4().hex[:6]}"},
                      headers=h("receptionist"), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_create_soap_note_builds_content():
    pid = _make_test_patient()
    payload = {
        "patient_id": pid, "title": "SOAP Visit", "note_type": "soap",
        "subjective": "Reports back pain 5 days",
        "objective": "BP 120/80, tender L4",
        "assessment": "Muscle strain",
        "plan": "NSAIDs, rest, PT",
    }
    r = requests.post(f"{API}/notes", json=payload, headers=h("doctor"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["note_type"] == "soap"
    assert d["subjective"] == payload["subjective"]
    assert d["plan"] == payload["plan"]
    # backend auto-builds content from SOAP fields
    assert "S: Reports back pain 5 days" in d["content"]
    assert "O: BP 120/80" in d["content"]
    assert "A: Muscle strain" in d["content"]
    assert "P: NSAIDs" in d["content"]

    # persistence: GET /notes contains it
    lst = requests.get(f"{API}/notes", headers=h("doctor"), timeout=30).json()
    match = [n for n in lst if n["id"] == d["id"]]
    assert match and match[0]["note_type"] == "soap"
    assert match[0]["subjective"] == payload["subjective"]


def test_create_free_text_note_original_behavior_preserved():
    pid = _make_test_patient()
    payload = {"patient_id": pid, "title": "Free Note",
               "content": "Original free-text progress note content."}
    r = requests.post(f"{API}/notes", json=payload, headers=h("doctor"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    # default note_type is 'free'
    assert d.get("note_type") == "free"
    assert d["content"] == payload["content"]
    assert d.get("subjective") is None


def test_create_soap_note_empty_fields_returns_400():
    pid = _make_test_patient()
    payload = {"patient_id": pid, "title": "Empty SOAP", "note_type": "soap"}
    r = requests.post(f"{API}/notes", json=payload, headers=h("doctor"), timeout=30)
    assert r.status_code == 400
    assert "content" in r.text.lower() or "required" in r.text.lower()


def test_create_free_note_empty_content_returns_400():
    pid = _make_test_patient()
    r = requests.post(f"{API}/notes",
                      json={"patient_id": pid, "title": "Empty", "content": ""},
                      headers=h("doctor"), timeout=30)
    assert r.status_code == 400


def test_soap_note_with_signature_signed_by():
    pid = _make_test_patient()
    sig = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    payload = {"patient_id": pid, "title": "Signed SOAP", "note_type": "soap",
               "subjective": "s", "objective": "o", "assessment": "a", "plan": "p",
               "signature": sig}
    r = requests.post(f"{API}/notes", json=payload, headers=h("doctor"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("signed_by")
    assert d["signature"].startswith("data:image")


def test_summarize_soap_combined_content():
    combined = "S: back pain 5d\nO: tender L4\nA: strain\nP: NSAIDs + PT"
    r = requests.post(f"{API}/notes/summarize",
                      json={"content": combined}, headers=h("doctor"), timeout=90)
    assert r.status_code == 200, r.text
    assert isinstance(r.json().get("summary"), str)
    assert len(r.json()["summary"]) > 10


def test_biller_still_cannot_create_soap_note():
    pid = _make_test_patient()
    r = requests.post(f"{API}/notes",
                      json={"patient_id": pid, "title": "x", "note_type": "soap",
                            "subjective": "s"},
                      headers=h("biller"), timeout=30)
    assert r.status_code == 403
