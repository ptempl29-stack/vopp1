"""Iteration 25 tests: appointment types, filters, bulk-delete for appts/notes/forms/messages/assistant, patient deep-dive."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "usvopp@yahoo.com"
ADMIN_PASSWORD = __import__("os").getenv("TEST_ADMIN_PASSWORD", "Football2023?")


@pytest.fixture(scope="session")
def admin_client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="session")
def test_patient(admin_client):
    r = admin_client.post(f"{BASE_URL}/api/patients", json={
        "first_name": "TEST_Iter25", "last_name": "Patient",
        "dob": "1980-01-01", "gender": "M", "phone": "555-0000"
    })
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    yield pid
    admin_client.delete(f"{BASE_URL}/api/patients/{pid}")


# ---------- Phase 1: Appointment types + filters ----------
class TestAppointmentTypes:
    def test_create_telehealth_and_inperson(self, admin_client, test_patient):
        r1 = admin_client.post(f"{BASE_URL}/api/appointments", json={
            "patient_id": test_patient, "provider": "ADMIN",
            "date": "2026-12-01", "time": "10:00",
            "reason": "TEST_tele", "appointment_type": "telehealth"})
        assert r1.status_code in (200, 201), r1.text
        assert r1.json()["appointment_type"] == "telehealth"
        assert "created_by_id" in r1.json()

        r2 = admin_client.post(f"{BASE_URL}/api/appointments", json={
            "patient_id": test_patient, "provider": "ADMIN",
            "date": "2026-12-02", "time": "11:00",
            "reason": "TEST_inp", "appointment_type": "in_person"})
        assert r2.status_code in (200, 201)
        assert r2.json()["appointment_type"] == "in_person"

    def test_filter_by_type_and_patient(self, admin_client, test_patient):
        r = admin_client.get(f"{BASE_URL}/api/appointments",
                             params={"patient_id": test_patient, "appointment_type": "telehealth"})
        assert r.status_code == 200
        appts = r.json()
        assert len(appts) >= 1
        assert all(a["appointment_type"] == "telehealth" for a in appts)
        assert all(a["patient_id"] == test_patient for a in appts)

    def test_filter_by_provider(self, admin_client, test_patient):
        r = admin_client.get(f"{BASE_URL}/api/appointments",
                             params={"patient_id": test_patient, "provider": "ADMIN"})
        assert r.status_code == 200
        assert all(a["provider"] == "ADMIN" for a in r.json())


# ---------- Phase 3: Bulk delete ----------
class TestBulkDelete:
    def test_appts_bulk_delete(self, admin_client, test_patient):
        ids = []
        for i in range(3):
            r = admin_client.post(f"{BASE_URL}/api/appointments", json={
                "patient_id": test_patient, "provider": "ADMIN",
                "date": f"2026-11-1{i}", "time": "09:00",
                "reason": "TEST_bulk", "appointment_type": "in_person"})
            ids.append(r.json()["id"])
        r = admin_client.post(f"{BASE_URL}/api/appointments/bulk-delete",
                              json={"ids": ids})
        assert r.status_code == 200
        assert r.json() == {"deleted": 3, "skipped": 0}
        # Verify
        remaining = admin_client.get(f"{BASE_URL}/api/appointments",
                                     params={"patient_id": test_patient}).json()
        remaining_ids = {a["id"] for a in remaining}
        assert not set(ids) & remaining_ids

    def test_appts_single_delete(self, admin_client, test_patient):
        r = admin_client.post(f"{BASE_URL}/api/appointments", json={
            "patient_id": test_patient, "provider": "ADMIN",
            "date": "2026-11-20", "time": "09:00",
            "reason": "TEST_single", "appointment_type": "in_person"})
        aid = r.json()["id"]
        r = admin_client.delete(f"{BASE_URL}/api/appointments/{aid}")
        assert r.status_code == 200

    def test_notes_bulk_delete(self, admin_client, test_patient):
        ids = []
        for i in range(2):
            r = admin_client.post(f"{BASE_URL}/api/notes", json={
                "patient_id": test_patient, "title": f"TEST_note{i}",
                "content": "x", "note_type": "free"})
            assert r.status_code in (200, 201), r.text
            ids.append(r.json()["id"])
        r = admin_client.post(f"{BASE_URL}/api/notes/bulk-delete", json={"ids": ids})
        assert r.status_code == 200
        assert r.json()["deleted"] == 2

    def test_forms_bulk_delete(self, admin_client, test_patient):
        ids = []
        for i in range(2):
            r = admin_client.post(f"{BASE_URL}/api/forms", json={
                "patient_id": test_patient, "title": f"TEST_form{i}",
                "form_type": "generic", "fields": {}, "external_url": None,
                "status": "pending"})
            assert r.status_code in (200, 201), r.text
            ids.append(r.json()["id"])
        r = admin_client.post(f"{BASE_URL}/api/forms/bulk-delete", json={"ids": ids})
        assert r.status_code == 200
        assert r.json()["deleted"] == 2

    def test_messages_bulk_delete(self, admin_client):
        me = admin_client.get(f"{BASE_URL}/api/auth/me").json()
        my_id = me["id"]
        ids = []
        for i in range(2):
            r = admin_client.post(f"{BASE_URL}/api/messages", json={
                "to_user_id": my_id, "subject": f"TEST_m{i}", "body": "hi"})
            assert r.status_code in (200, 201), r.text
            ids.append(r.json()["id"])
        r = admin_client.post(f"{BASE_URL}/api/messages/bulk-delete",
                              json={"ids": ids})
        assert r.status_code == 200
        assert r.json()["deleted"] == 2

    def test_assistant_bulk_delete(self, admin_client):
        ids = []
        for _ in range(2):
            r = admin_client.post(f"{BASE_URL}/api/assistant/conversations")
            assert r.status_code in (200, 201)
            ids.append(r.json()["id"])
        r = admin_client.post(f"{BASE_URL}/api/assistant/conversations/bulk-delete",
                              json={"ids": ids})
        assert r.status_code == 200
        assert r.json()["deleted"] == 2


# ---------- RBAC test with a non-admin ----------
class TestRBAC:
    @pytest.fixture(scope="class")
    def staff_client(self, admin_client):
        email = f"TEST_staff_{uuid.uuid4().hex[:6]}@example.com"
        r = admin_client.post(f"{BASE_URL}/api/auth/register", json={
            "email": email, "password": "Passw0rd!", "name": "TEST Staff",
            "role": "doctor", "require_password_change": False})
        assert r.status_code in (200, 201), r.text
        uid = r.json()["id"]
        s = requests.Session()
        lr = s.post(f"{BASE_URL}/api/auth/login",
                    json={"email": email, "password": "Passw0rd!"})
        assert lr.status_code == 200, lr.text
        tok = lr.json().get("token") or lr.json().get("access_token")
        if tok:
            s.headers["Authorization"] = f"Bearer {tok}"
        yield s
        admin_client.delete(f"{BASE_URL}/api/users/{uid}")

    def test_staff_cannot_delete_admin_appointment(self, admin_client, staff_client, test_patient):
        # admin creates an appointment
        r = admin_client.post(f"{BASE_URL}/api/appointments", json={
            "patient_id": test_patient, "provider": "ADMIN",
            "date": "2026-12-10", "time": "12:00",
            "reason": "TEST_rbac", "appointment_type": "in_person"})
        aid = r.json()["id"]
        # staff attempts bulk delete
        br = staff_client.post(f"{BASE_URL}/api/appointments/bulk-delete",
                               json={"ids": [aid]})
        assert br.status_code == 200
        assert br.json()["deleted"] == 0
        assert br.json()["skipped"] == 1
        # cleanup
        admin_client.delete(f"{BASE_URL}/api/appointments/{aid}")
