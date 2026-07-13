"""
Iteration 22 backend tests — Suspend/Restore, Role Templates, RBAC.
Uses a throwaway nurse user; resets role_templates for nurse afterward.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@vpp.com", "password": "VPP-Adm1n!2026-Str0ng#Key"}
DOCTOR = {"email": "doctor@vpp.com", "password": "doctor123"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds)
    return r


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def doctor_token():
    r = _login(DOCTOR)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_id(admin_token):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    return r.json()["id"]


@pytest.fixture(scope="module")
def throwaway_user(admin_token):
    hdr = {"Authorization": f"Bearer {admin_token}"}
    email = f"TEST_throwaway_{uuid.uuid4().hex[:8]}@vpp.com"
    payload = {"email": email, "password": "testpass123", "name": "Test Throwaway",
               "role": "nurse"}
    r = requests.post(f"{API}/auth/register", json=payload, headers=hdr)
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    yield {"id": uid, "email": email, "password": "testpass123"}
    # cleanup
    requests.delete(f"{API}/users/{uid}", headers=hdr)


class TestSuspendRestore:
    def test_suspend_blocks_login(self, admin_token, throwaway_user):
        hdr = {"Authorization": f"Bearer {admin_token}"}
        # Confirm login works first
        r = _login({"email": throwaway_user["email"], "password": throwaway_user["password"]})
        assert r.status_code == 200

        # Suspend
        r = requests.put(f"{API}/users/{throwaway_user['id']}/active",
                         json={"active": False}, headers=hdr)
        assert r.status_code == 200
        assert r.json().get("active") is False

        # Login should now be 403
        r = _login({"email": throwaway_user["email"], "password": throwaway_user["password"]})
        assert r.status_code == 403, r.text
        assert "suspend" in r.json().get("detail", "").lower()

    def test_restore_allows_login(self, admin_token, throwaway_user):
        hdr = {"Authorization": f"Bearer {admin_token}"}
        r = requests.put(f"{API}/users/{throwaway_user['id']}/active",
                         json={"active": True}, headers=hdr)
        assert r.status_code == 200
        assert r.json().get("active") is True
        r = _login({"email": throwaway_user["email"], "password": throwaway_user["password"]})
        assert r.status_code == 200

    def test_suspend_invalidates_existing_jwt(self, admin_token, throwaway_user):
        hdr = {"Authorization": f"Bearer {admin_token}"}
        # login to get token
        r = _login({"email": throwaway_user["email"], "password": throwaway_user["password"]})
        assert r.status_code == 200
        tok = r.json()["token"]
        # /me works
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        # suspend
        requests.put(f"{API}/users/{throwaway_user['id']}/active",
                     json={"active": False}, headers=hdr)
        # existing jwt now 403
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403
        # restore for downstream tests
        requests.put(f"{API}/users/{throwaway_user['id']}/active",
                     json={"active": True}, headers=hdr)

    def test_cannot_suspend_self(self, admin_token, admin_id):
        hdr = {"Authorization": f"Bearer {admin_token}"}
        r = requests.put(f"{API}/users/{admin_id}/active",
                         json={"active": False}, headers=hdr)
        assert r.status_code == 400

    def test_cannot_suspend_admin_role(self, admin_token):
        hdr = {"Authorization": f"Bearer {admin_token}"}
        users = requests.get(f"{API}/users", headers=hdr).json()
        # Find any admin user (there might be only self, but test even so)
        admin_users = [u for u in users if u["role"] == "admin"]
        assert admin_users
        target = admin_users[0]
        r = requests.put(f"{API}/users/{target['id']}/active",
                         json={"active": False}, headers=hdr)
        assert r.status_code == 400


class TestRoleTemplates:
    def test_get_role_templates(self, admin_token):
        hdr = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/role-templates", headers=hdr)
        assert r.status_code == 200
        data = r.json()
        assert "nurse" in data and isinstance(data["nurse"], list)

    def test_put_role_template_and_apply(self, admin_token, throwaway_user):
        hdr = {"Authorization": f"Bearer {admin_token}"}
        # Save nurse template — using a minimal set
        new_tabs = ["dashboard", "patients", "appointments"]
        r = requests.put(f"{API}/role-templates/nurse",
                         json={"allowed_tabs": new_tabs, "apply_to_existing": True},
                         headers=hdr)
        assert r.status_code == 200
        body = r.json()
        assert body["allowed_tabs"] == new_tabs
        assert body["applied_to_existing"] >= 1

        # Verify throwaway user now has those tabs
        users = requests.get(f"{API}/users", headers=hdr).json()
        tw = next(u for u in users if u["id"] == throwaway_user["id"])
        assert tw["allowed_tabs"] == new_tabs

        # meta reflects it
        m = requests.get(f"{API}/meta/tabs", headers=hdr).json()
        assert m["defaults"]["nurse"] == new_tabs

        # New user via register inherits template
        email = f"TEST_inherit_{uuid.uuid4().hex[:6]}@vpp.com"
        r = requests.post(f"{API}/auth/register",
                         json={"email": email, "password": "pw123456",
                               "name": "Inherit Test", "role": "nurse"},
                         headers=hdr)
        assert r.status_code == 200
        assert r.json()["allowed_tabs"] == new_tabs
        # cleanup
        requests.delete(f"{API}/users/{r.json()['id']}", headers=hdr)

    def test_role_template_rejects_admin(self, admin_token):
        hdr = {"Authorization": f"Bearer {admin_token}"}
        r = requests.put(f"{API}/role-templates/admin",
                         json={"allowed_tabs": ["dashboard"]}, headers=hdr)
        assert r.status_code == 400

    def test_role_template_rejects_invalid(self, admin_token):
        hdr = {"Authorization": f"Bearer {admin_token}"}
        r = requests.put(f"{API}/role-templates/wizard",
                         json={"allowed_tabs": ["dashboard"]}, headers=hdr)
        assert r.status_code == 400


class TestRBAC:
    def test_non_admin_cannot_suspend(self, doctor_token, throwaway_user):
        hdr = {"Authorization": f"Bearer {doctor_token}"}
        r = requests.put(f"{API}/users/{throwaway_user['id']}/active",
                         json={"active": False}, headers=hdr)
        assert r.status_code == 403

    def test_non_admin_cannot_read_templates(self, doctor_token):
        hdr = {"Authorization": f"Bearer {doctor_token}"}
        r = requests.get(f"{API}/role-templates", headers=hdr)
        assert r.status_code == 403

    def test_non_admin_cannot_edit_templates(self, doctor_token):
        hdr = {"Authorization": f"Bearer {doctor_token}"}
        r = requests.put(f"{API}/role-templates/nurse",
                         json={"allowed_tabs": ["dashboard"]}, headers=hdr)
        assert r.status_code == 403

    def test_non_admin_cannot_read_meta_tabs(self, doctor_token):
        hdr = {"Authorization": f"Bearer {doctor_token}"}
        r = requests.get(f"{API}/meta/tabs", headers=hdr)
        assert r.status_code == 403


# Reset role template for nurse to avoid corrupting seed data.
@pytest.fixture(scope="module", autouse=True)
def _reset_nurse_template(admin_token):
    yield
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    async def _clean():
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "test_database")
        client = AsyncIOMotorClient(mongo_url)
        d = client[db_name]
        await d.role_templates.delete_one({"role": "nurse"})
        # restore seeded nurse tabs to default by $unset allowed_tabs — server will
        # fall back to DEFAULT_TABS. But seeded nurse@vpp.com should keep custom tabs
        # if they had any. Safer: $unset so effective_tabs falls back to defaults.
        await d.users.update_many({"role": "nurse", "email": {"$regex": "^(?!TEST_)"}},
                                  {"$unset": {"allowed_tabs": ""}})
        client.close()
    asyncio.get_event_loop().run_until_complete(_clean())
