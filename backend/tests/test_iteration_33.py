"""Iteration 33 - Forms new endpoints + Patient Folders drag/preview backend."""
import os
import io
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "usvopp@yahoo.com"
ADMIN_PASSWORD = "Football2023?"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    token = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def patient_id(admin_session):
    # Get existing or create test patient
    r = admin_session.get(f"{BASE_URL}/api/patients")
    assert r.status_code == 200
    plist = r.json()
    if plist:
        return plist[0]["id"]
    r = admin_session.post(f"{BASE_URL}/api/patients", json={
        "first_name": "TEST_Iter33", "last_name": "Patient",
        "email": "iter33@example.com"
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ---------- Forms create with empty recipient ----------
def test_create_form_empty_recipient_email(admin_session):
    payload = {"title": "TEST_Iter33 Empty Email",
               "form_type": "New Patient Intake",
               "status": "sent",
               "recipient_email": None,
               "external_url": "",
               "patient_id": None}
    r = admin_session.post(f"{BASE_URL}/api/forms", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["title"] == "TEST_Iter33 Empty Email"
    assert "id" in data
    admin_session._empty_form_id = data["id"]
    # cleanup
    d = admin_session.delete(f"{BASE_URL}/api/forms/{data['id']}")
    assert d.status_code == 200


# ---------- PUT /forms/{fid} update ----------
def test_update_form_fields_and_responses(admin_session, patient_id):
    # Create a form
    payload = {"title": "TEST_Iter33 Update", "form_type": "New Patient Intake",
               "status": "sent", "recipient_email": None, "external_url": "",
               "patient_id": patient_id}
    r = admin_session.post(f"{BASE_URL}/api/forms", json=payload)
    assert r.status_code == 200
    fid = r.json()["id"]

    # Update title/type/status/recipient/url/responses
    upd = {"title": "TEST_Iter33 Updated Title",
           "form_type": "New Patient Intake",
           "status": "received",
           "external_url": "https://example.com/x",
           "recipient_email": "someone@example.com",
           "responses": {"name": "John Doe", "notes": "Test note"}}
    r = admin_session.put(f"{BASE_URL}/api/forms/{fid}", json=upd)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["title"] == "TEST_Iter33 Updated Title"
    assert data["status"] == "received"
    assert data["responses"] == {"name": "John Doe", "notes": "Test note"}
    assert data["recipient_email"] == "someone@example.com"

    # GET verify persistence
    r2 = admin_session.get(f"{BASE_URL}/api/forms")
    got = [f for f in r2.json() if f["id"] == fid][0]
    assert got["title"] == "TEST_Iter33 Updated Title"
    assert got["responses"]["name"] == "John Doe"

    # Cleanup
    admin_session.delete(f"{BASE_URL}/api/forms/{fid}")


def test_update_form_invalid_status(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/forms", json={
        "title": "TEST_Iter33 InvStatus", "form_type": "New Patient Intake",
        "status": "sent", "recipient_email": None, "external_url": "",
        "patient_id": None})
    fid = r.json()["id"]
    r = admin_session.put(f"{BASE_URL}/api/forms/{fid}", json={"status": "bogus_status"})
    assert r.status_code == 400
    admin_session.delete(f"{BASE_URL}/api/forms/{fid}")


def test_update_form_not_found(admin_session):
    r = admin_session.put(f"{BASE_URL}/api/forms/{uuid.uuid4()}",
                          json={"title": "x"})
    assert r.status_code == 404


# ---------- POST /forms/{fid}/send-email ----------
def test_send_email_not_configured(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/forms", json={
        "title": "TEST_Iter33 Email", "form_type": "New Patient Intake",
        "status": "sent", "recipient_email": None, "external_url": "",
        "patient_id": None})
    fid = r.json()["id"]

    r = admin_session.post(f"{BASE_URL}/api/forms/{fid}/send-email",
                           json={"recipient_email": "anyone@example.com"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sent"] is False
    assert data["configured"] is False

    admin_session.delete(f"{BASE_URL}/api/forms/{fid}")


def test_send_email_invalid_email(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/forms", json={
        "title": "TEST_Iter33 EmailInv", "form_type": "New Patient Intake",
        "status": "sent", "recipient_email": None, "external_url": "",
        "patient_id": None})
    fid = r.json()["id"]
    r = admin_session.post(f"{BASE_URL}/api/forms/{fid}/send-email",
                           json={"recipient_email": "not-an-email"})
    assert r.status_code == 422
    admin_session.delete(f"{BASE_URL}/api/forms/{fid}")


# ---------- POST /forms/{fid}/to-folder ----------
def test_to_folder_field_form_generates_pdf(admin_session, patient_id):
    # field-based form with responses, no attachment
    r = admin_session.post(f"{BASE_URL}/api/forms", json={
        "title": "TEST_Iter33 FieldForm", "form_type": "New Patient Intake",
        "status": "received", "recipient_email": None, "external_url": "",
        "patient_id": patient_id})
    fid = r.json()["id"]
    # add responses
    admin_session.put(f"{BASE_URL}/api/forms/{fid}",
                      json={"responses": {"Name": "Test", "DOB": "1990-01-01"}})

    r = admin_session.post(f"{BASE_URL}/api/forms/{fid}/to-folder",
                           json={"patient_id": patient_id})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    # Verify item appears in folder
    r = admin_session.get(f"{BASE_URL}/api/folders/{patient_id}")
    assert r.status_code == 200
    items = r.json()["items"]
    matched = [i for i in items if i.get("form_id") == fid]
    assert len(matched) >= 1
    it = matched[0]
    assert it["content_type"] == "application/pdf"
    assert it["source"] == "upload"
    # cleanup item and form
    iid = it["id"]; admin_session.delete(f"{BASE_URL}/api/folders/items/{iid}")
    admin_session.delete(f"{BASE_URL}/api/forms/{fid}")


def test_to_folder_attachment_form(admin_session, patient_id):
    # Upload a form with an attachment
    files = {"file": ("test.pdf", b"%PDF-1.4\n%TEST\n", "application/pdf")}
    data = {"title": "TEST_Iter33 UploadForm", "form_type": "Uploaded"}
    # remove Content-Type header for multipart
    headers = {k: v for k, v in admin_session.headers.items() if k.lower() != "content-type"}
    r = requests.post(f"{BASE_URL}/api/forms/upload", files=files, data=data, headers=headers)
    assert r.status_code == 200, r.text
    fid = r.json()["id"]

    r = admin_session.post(f"{BASE_URL}/api/forms/{fid}/to-folder",
                           json={"patient_id": patient_id})
    assert r.status_code == 200, r.text

    r = admin_session.get(f"{BASE_URL}/api/folders/{patient_id}")
    items = [i for i in r.json()["items"] if i.get("form_id") == fid]
    assert len(items) >= 1
    it = items[0]
    assert it["source"] == "form"
    iid = it["id"]; admin_session.delete(f"{BASE_URL}/api/folders/items/{iid}")
    admin_session.delete(f"{BASE_URL}/api/forms/{fid}")


def test_to_folder_invalid_patient(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/forms", json={
        "title": "TEST_Iter33 InvPat", "form_type": "New Patient Intake",
        "status": "sent", "recipient_email": None, "external_url": "",
        "patient_id": None})
    fid = r.json()["id"]
    r = admin_session.post(f"{BASE_URL}/api/forms/{fid}/to-folder",
                           json={"patient_id": "no-such-patient"})
    assert r.status_code == 404
    admin_session.delete(f"{BASE_URL}/api/forms/{fid}")


# ---------- RBAC ----------
def test_rbac_unauthenticated_blocked(admin_session):
    s = requests.Session()
    r = s.put(f"{BASE_URL}/api/forms/whatever", json={"title": "x"})
    assert r.status_code in (401, 403)
    r = s.post(f"{BASE_URL}/api/forms/whatever/send-email",
               json={"recipient_email": "a@b.com"})
    assert r.status_code in (401, 403)
    r = s.post(f"{BASE_URL}/api/forms/whatever/to-folder",
               json={"patient_id": "x"})
    assert r.status_code in (401, 403)
