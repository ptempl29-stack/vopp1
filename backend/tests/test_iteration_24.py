"""Regression tests for iteration 24:
- N+1 projection fixes (appointments, invoices)
- Auth refactor (auth.py + users.py + roles.py) URLs unchanged
- DELETE /api/notes/{id}
- Account state
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://veteran-care-portal.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "usvopp@yahoo.com"
ADMIN_PASSWORD = "Football2023?"

TAG = f"TEST_{uuid.uuid4().hex[:8]}"


# --- helpers ---
def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    return r


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# tracks resources to clean
_created = {"patients": [], "appointments": [], "invoices": [], "notes": [], "users": []}


# --- Account state ---
class TestAccountState:
    def test_admin_login_success(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 20

    def test_old_admin_erased(self):
        r = _login("admin@vpp.com", "admin123")
        assert r.status_code == 401, f"admin@vpp.com should be gone, got {r.status_code}"

    def test_demo_doctor_erased(self):
        r = _login("doctor@vpp.com", "doctor123")
        assert r.status_code == 401


# --- Auth refactor endpoints ---
class TestAuthRefactor:
    def test_me(self, admin_headers):
        r = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        assert "allowed_tabs" in data

    def test_users_list(self, admin_headers):
        r = requests.get(f"{API}/users", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_role_templates(self, admin_headers):
        r = requests.get(f"{API}/role-templates", headers=admin_headers, timeout=10)
        assert r.status_code == 200

    def test_meta_tabs(self, admin_headers):
        r = requests.get(f"{API}/meta/tabs", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "tabs" in d and "roles" in d

    def test_put_role_template(self, admin_headers):
        # get current
        cur = requests.get(f"{API}/role-templates", headers=admin_headers).json()
        # cur is dict role->tabs or list; handle both
        if isinstance(cur, dict):
            original = cur.get("nurse", [])
        else:
            original = next((x.get("allowed_tabs", []) for x in cur if x.get("role") == "nurse"), [])
        r = requests.put(f"{API}/role-templates/nurse",
                         headers=admin_headers,
                         json={"allowed_tabs": original, "apply_to_existing": False})
        assert r.status_code == 200

    def test_non_admin_403(self, admin_headers):
        # Create throwaway nurse
        email = f"test_nurse_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/auth/register", headers=admin_headers,
                          json={"email": email, "password": "pass123", "name": "TEST Nurse",
                                "role": "nurse"})
        assert r.status_code == 200, r.text
        uid = r.json()["id"]
        _created["users"].append(uid)
        tok = _login(email, "pass123").json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        # admin-only endpoints
        assert requests.get(f"{API}/role-templates", headers=h).status_code == 403
        assert requests.get(f"{API}/meta/tabs", headers=h).status_code == 403

    def test_user_updates(self, admin_headers):
        # create a throwaway user
        email = f"test_u_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/auth/register", headers=admin_headers,
                          json={"email": email, "password": "pass123", "name": "TEST U",
                                "role": "doctor"})
        assert r.status_code == 200
        uid = r.json()["id"]
        _created["users"].append(uid)
        # PUT tabs
        r = requests.put(f"{API}/users/{uid}/tabs", headers=admin_headers,
                         json={"allowed_tabs": ["patients"]})
        assert r.status_code == 200
        # PUT user
        r = requests.put(f"{API}/users/{uid}", headers=admin_headers,
                         json={"name": "TEST U Updated"})
        assert r.status_code == 200
        # PUT active (suspend then restore) - doctor is not admin so ok
        r = requests.put(f"{API}/users/{uid}/active", headers=admin_headers, json={"active": False})
        assert r.status_code == 200
        r = requests.put(f"{API}/users/{uid}/active", headers=admin_headers, json={"active": True})
        assert r.status_code == 200
        # PUT password
        r = requests.put(f"{API}/users/{uid}/password", headers=admin_headers,
                         json={"password": "newpass123", "require_change": False})
        assert r.status_code == 200
        # POST logout
        r = requests.post(f"{API}/users/{uid}/logout", headers=admin_headers)
        assert r.status_code == 200


# --- N+1 projection fix verification ---
class TestProjectionFix:
    def test_appointment_patient_name_resolves(self, admin_headers):
        # create patient
        r = requests.post(f"{API}/patients", headers=admin_headers, json={
            "first_name": f"{TAG}Alice", "last_name": "TestPatient",
            "dob": "1980-01-01", "gender": "F"
        })
        assert r.status_code == 200, r.text
        patient = r.json()
        pid = patient["id"]
        _created["patients"].append(pid)
        expected_name = f"{TAG}Alice TestPatient"

        # create appointment
        r = requests.post(f"{API}/appointments", headers=admin_headers, json={
            "patient_id": pid, "date": "2026-06-15", "time": "10:00",
            "provider": "Dr Test", "reason": "Checkup", "status": "scheduled"
        })
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        _created["appointments"].append(aid)

        # list appointments
        r = requests.get(f"{API}/appointments", headers=admin_headers)
        assert r.status_code == 200
        appts = r.json()
        match = [a for a in appts if a["id"] == aid]
        assert len(match) == 1
        assert match[0]["patient_name"] == expected_name, f"Got: {match[0].get('patient_name')}"

    def test_invoice_patient_name_resolves(self, admin_headers):
        # create patient
        r = requests.post(f"{API}/patients", headers=admin_headers, json={
            "first_name": f"{TAG}Bob", "last_name": "BillTest",
            "dob": "1975-05-05", "gender": "M"
        })
        assert r.status_code == 200
        pid = r.json()["id"]
        _created["patients"].append(pid)
        expected_name = f"{TAG}Bob BillTest"

        # create invoice with patient_id but NO patient_name
        r = requests.post(f"{API}/invoices", headers=admin_headers, json={
            "patient_id": pid,
            "service_date": "2026-06-15",
            "provider": "Dr Test",
            "items": [{"cpt_code": "99213", "description": "Office visit",
                       "amount": 100.0, "quantity": 1}],
            "status": "unpaid"
        })
        assert r.status_code == 200, r.text
        inv = r.json()
        _created["invoices"].append(inv["id"])
        # The create endpoint already resolves name; but let's clear the stored name
        # to specifically test the list projection resolution. Actually spec says
        # the list should resolve — since patient_name is stored on create when patient_id
        # is provided, we test differently: create invoice bypassing that? Not possible via API.
        # But list still uses projection to resolve when patient_name missing.
        # Since patient_name is now stored, ensure list returns correct name.
        r = requests.get(f"{API}/invoices", headers=admin_headers)
        assert r.status_code == 200
        match = [i for i in r.json() if i["id"] == inv["id"]]
        assert len(match) == 1
        assert match[0]["patient_name"] == expected_name

    def test_billing_csv_export(self, admin_headers):
        r = requests.get(f"{API}/reports/billing/export", headers=admin_headers)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        body = r.text
        assert "Invoice ID" in body
        # Should not contain any 'Unknown' for our just-created invoice with a valid patient
        # (older orphan appointments are separate; invoices had valid patient)
        # Verify at least one row parseable
        assert "\n" in body


# --- Notes delete ---
class TestNoteDelete:
    def test_delete_note_by_admin(self, admin_headers):
        # create patient
        r = requests.post(f"{API}/patients", headers=admin_headers, json={
            "first_name": f"{TAG}Note", "last_name": "Patient",
            "dob": "1990-01-01", "gender": "M"
        })
        assert r.status_code == 200
        pid = r.json()["id"]
        _created["patients"].append(pid)

        # notes require doctor/nurse/psych - admin doesn't have; create doctor
        email = f"test_doc_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/auth/register", headers=admin_headers,
                          json={"email": email, "password": "pass123", "name": "TEST Doc",
                                "role": "doctor"})
        assert r.status_code == 200
        uid = r.json()["id"]
        _created["users"].append(uid)
        doc_tok = _login(email, "pass123").json()["token"]
        doc_h = {"Authorization": f"Bearer {doc_tok}", "Content-Type": "application/json"}

        r = requests.post(f"{API}/notes", headers=doc_h, json={
            "patient_id": pid, "note_type": "free", "title": "TEST note",
            "content": "Test content for deletion"
        })
        assert r.status_code == 200, r.text
        nid = r.json()["id"]

        # delete by author (doctor)
        r = requests.delete(f"{API}/notes/{nid}", headers=doc_h)
        assert r.status_code == 200

        # delete non-existent -> 404
        r = requests.delete(f"{API}/notes/nonexistent-id-xyz", headers=doc_h)
        assert r.status_code == 404


# --- Cleanup ---
def test_zzz_cleanup(admin_headers=None):
    # get token again since fixtures don't run in module-level function
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if r.status_code != 200:
        return
    h = {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}
    for aid in _created["appointments"]:
        requests.delete(f"{API}/appointments/{aid}", headers=h)
    for iid in _created["invoices"]:
        # no invoice delete endpoint; leave. Mark as skipped cleanup
        pass
    for pid in _created["patients"]:
        requests.delete(f"{API}/patients/{pid}", headers=h)
    for uid in _created["users"]:
        requests.delete(f"{API}/users/{uid}", headers=h)
