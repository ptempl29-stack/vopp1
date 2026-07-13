"""Iteration 20 - Invite Staff feature tests"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://veteran-care-portal.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@vpp.com", "password": "VPP-Adm1n!2026-Str0ng#Key"}
DOCTOR = {"email": "doctor@vpp.com", "password": "doctor123"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def doctor_token():
    return _login(DOCTOR)


@pytest.fixture(scope="module")
def h_admin(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def h_doctor(doctor_token):
    return {"Authorization": f"Bearer {doctor_token}", "Content-Type": "application/json"}


created_invite_ids = []
created_user_emails = []


def _test_email(tag):
    return f"TEST_invite_{tag}_{int(time.time())}@example.com"


# ---------------- Admin CRUD ----------------
def test_list_invites_admin_ok(h_admin):
    r = requests.get(f"{API}/invites", headers=h_admin, timeout=30)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_invites_non_admin_403(h_doctor):
    r = requests.get(f"{API}/invites", headers=h_doctor, timeout=30)
    assert r.status_code == 403


def test_full_invite_lifecycle(h_admin):
    """Combined lifecycle test: create -> public get -> bad password -> accept -> reuse -> login."""
    email = _test_email("basic").lower()
    payload = {"email": email, "role": "nurse", "allowed_tabs": ["dashboard", "patients", "notes"]}
    r = requests.post(f"{API}/invites", headers=h_admin, json=payload, timeout=30)
    assert r.status_code == 200, r.text
    inv = r.json()
    assert inv["email"] == email
    assert inv["role"] == "nurse"
    assert inv["status"] == "pending"
    assert "token" in inv and len(inv["token"]) > 10
    assert sorted(inv["allowed_tabs"]) == sorted(["dashboard", "patients", "notes"])
    created_invite_ids.append(inv["id"])

    # Public GET
    g = requests.get(f"{API}/public/invites/{inv['token']}", timeout=30)
    assert g.status_code == 200
    gd = g.json()
    assert gd["email"] == email and gd["role"] == "nurse" and gd["status"] == "pending"
    assert "clinic" in gd

    # Bad token 404
    b = requests.get(f"{API}/public/invites/nonexistent-bad-token-xyz", timeout=30)
    assert b.status_code == 404

    # Short password 400
    sp = requests.post(f"{API}/public/invites/{inv['token']}/accept",
                      json={"name": "Test Nurse", "password": "abc"}, timeout=30)
    assert sp.status_code == 400

    # Accept success
    ac = requests.post(f"{API}/public/invites/{inv['token']}/accept",
                      json={"name": "TEST Nurse User", "password": "strongpass123"}, timeout=30)
    assert ac.status_code == 200, ac.text
    d = ac.json()
    assert "token" in d
    assert d["user"]["email"] == email
    assert d["user"]["role"] == "nurse"
    assert sorted(d["user"]["allowed_tabs"]) == sorted(["dashboard", "patients", "notes"])
    created_user_emails.append(email)

    # Reuse 400 (single-use)
    reuse = requests.post(f"{API}/public/invites/{inv['token']}/accept",
                      json={"name": "Another", "password": "strongpass123"}, timeout=30)
    assert reuse.status_code == 400

    # New user login with assigned tabs
    lg = requests.post(f"{API}/auth/login", json={"email": email, "password": "strongpass123"}, timeout=30)
    assert lg.status_code == 200, lg.text
    u = lg.json()["user"]
    assert u["role"] == "nurse"
    for tab in ["dashboard", "patients", "notes"]:
        assert tab in u["allowed_tabs"]


def test_create_invite_admin_role_rejected(h_admin):
    r = requests.post(f"{API}/invites", headers=h_admin,
                      json={"email": _test_email("admin"), "role": "admin"}, timeout=30)
    assert r.status_code == 400


def test_create_invite_existing_email_rejected(h_admin):
    r = requests.post(f"{API}/invites", headers=h_admin,
                      json={"email": "doctor@vpp.com", "role": "doctor"}, timeout=30)
    assert r.status_code == 400


def test_create_invite_non_admin_forbidden(h_doctor):
    r = requests.post(f"{API}/invites", headers=h_doctor,
                      json={"email": _test_email("forbidden"), "role": "nurse"}, timeout=30)
    assert r.status_code == 403


# ---------------- Public endpoints ----------------
def test_public_get_invite_bad_token_404():
    r = requests.get(f"{API}/public/invites/nonexistent-bad-token-xyz", timeout=30)
    assert r.status_code == 404


# ---------------- Delete / revoke ----------------
def test_delete_invite_admin(h_admin):
    email = _test_email("revoke")
    r = requests.post(f"{API}/invites", headers=h_admin,
                      json={"email": email, "role": "biller"}, timeout=30)
    assert r.status_code == 200
    iid = r.json()["id"]
    created_invite_ids.append(iid)
    d = requests.delete(f"{API}/invites/{iid}", headers=h_admin, timeout=30)
    assert d.status_code == 200
    # Verify it's gone
    lst = requests.get(f"{API}/invites", headers=h_admin, timeout=30).json()
    assert not any(i["id"] == iid for i in lst)


def test_delete_invite_non_admin_forbidden(h_doctor, h_admin):
    email = _test_email("noperm")
    r = requests.post(f"{API}/invites", headers=h_admin,
                      json={"email": email, "role": "biller"}, timeout=30)
    iid = r.json()["id"]
    created_invite_ids.append(iid)
    d = requests.delete(f"{API}/invites/{iid}", headers=h_doctor, timeout=30)
    assert d.status_code == 403


# ---------------- Cleanup ----------------
def test_zzz_cleanup(h_admin):
    """Cleanup created invites + users. Runs last (zzz name)."""
    # Delete created invites
    for iid in created_invite_ids:
        requests.delete(f"{API}/invites/{iid}", headers=h_admin, timeout=30)
    # Delete created users (via admin user delete)
    users = requests.get(f"{API}/users", headers=h_admin, timeout=30).json()
    for u in users:
        if u["email"] in created_user_emails:
            requests.delete(f"{API}/users/{u['id']}", headers=h_admin, timeout=30)
