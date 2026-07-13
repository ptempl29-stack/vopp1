"""Backend tests for admin login-access controls: forced password change,
admin password reset, force logout, token versioning, RBAC, safeguards."""
import os
import uuid
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://veteran-care-portal.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@vpp.com", "password": "VPP-Adm1n!2026-Str0ng#Key"}
DOCTOR = {"email": "doctor@vpp.com", "password": "doctor123"}


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    return r


@pytest.fixture(scope="module")
def admin_token():
    r = _login(**ADMIN)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def doctor_token():
    r = _login(**DOCTOR)
    assert r.status_code == 200, f"Doctor login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def created_user_ids():
    ids = []
    yield ids
    # Cleanup
    r = _login(**ADMIN)
    if r.status_code == 200:
        tok = r.json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        for uid in ids:
            try:
                requests.delete(f"{API}/users/{uid}", headers=h)
            except Exception:
                pass


def _create_user(admin_token, require_change=True, role="receptionist"):
    email = f"TEST_{uuid.uuid4().hex[:10]}@vpp.com"
    password = "TempPass!123"
    h = {"Authorization": f"Bearer {admin_token}"}
    r = requests.post(f"{API}/auth/register", headers=h,
                      json={"email": email, "password": password, "name": "Test User",
                            "role": role, "require_password_change": require_change})
    assert r.status_code == 200, f"register failed {r.status_code} {r.text}"
    return r.json(), email, password


# ---------- LOGIN REGRESSION ----------
class TestLoginRegression:
    @pytest.mark.parametrize("acc", [
        {"email": "admin@vpp.com", "password": "VPP-Adm1n!2026-Str0ng#Key"},
        {"email": "doctor@vpp.com", "password": "doctor123"},
        {"email": "nurse@vpp.com", "password": "nurse123"},
        {"email": "reception@vpp.com", "password": "reception123"},
        {"email": "biller@vpp.com", "password": "biller123"},
        {"email": "psych@vpp.com", "password": "psych123"},
    ])
    def test_demo_accounts_login(self, acc):
        r = _login(**acc)
        assert r.status_code == 200, f"{acc['email']} login failed: {r.text}"
        data = r.json()
        assert "token" in data and "user" in data
        assert data["user"]["email"] == acc["email"]
        # Demo accounts should NOT be forced to change password
        assert data["user"].get("must_change_password") in (False, None), \
            f"{acc['email']} unexpectedly requires password change"

    def test_token_without_tv_claim_accepted(self):
        """Legacy tokens minted without 'tv' (defaults to 0) should still work
        as long as user's token_version is 0 (default)."""
        import jwt as pyjwt
        from datetime import datetime, timezone, timedelta
        # Get a demo user id first
        r = _login(**ADMIN)
        assert r.status_code == 200
        admin_tok = r.json()["token"]
        h = {"Authorization": f"Bearer {admin_tok}"}
        users = requests.get(f"{API}/users", headers=h).json()
        doctor = next(u for u in users if u["email"] == "doctor@vpp.com")
        # Mint a token WITHOUT tv claim
        secret = os.environ.get("JWT_SECRET")
        if not secret:
            # Load from backend .env
            with open("/app/backend/.env") as f:
                for line in f:
                    if line.startswith("JWT_SECRET="):
                        secret = line.strip().split("=", 1)[1].strip('"').strip("'")
                        break
        assert secret, "JWT_SECRET not found"
        payload = {"sub": doctor["id"], "email": doctor["email"], "role": doctor["role"],
                   "exp": datetime.now(timezone.utc) + timedelta(hours=1), "type": "access"}
        legacy_token = pyjwt.encode(payload, secret, algorithm="HS256")
        r2 = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {legacy_token}"})
        assert r2.status_code == 200, f"Legacy token (no tv) rejected: {r2.status_code} {r2.text}"


# ---------- FORCED PASSWORD CHANGE ----------
class TestForcedPasswordChange:
    def test_register_with_require_change(self, admin_token, created_user_ids):
        info, email, pw = _create_user(admin_token, require_change=True)
        created_user_ids.append(info["id"])
        assert info["must_change_password"] is True
        # Login shows must_change_password
        r = _login(email, pw)
        assert r.status_code == 200
        assert r.json()["user"]["must_change_password"] is True

    def test_change_password_wrong_current(self, admin_token, created_user_ids):
        info, email, pw = _create_user(admin_token, require_change=True)
        created_user_ids.append(info["id"])
        tok = _login(email, pw).json()["token"]
        r = requests.post(f"{API}/auth/change-password",
                          headers={"Authorization": f"Bearer {tok}"},
                          json={"current_password": "WRONG", "new_password": "NewPass!123"})
        assert r.status_code == 400

    def test_change_password_success_invalidates_old_token(self, admin_token, created_user_ids):
        info, email, pw = _create_user(admin_token, require_change=True)
        created_user_ids.append(info["id"])
        old_token = _login(email, pw).json()["token"]
        r = requests.post(f"{API}/auth/change-password",
                          headers={"Authorization": f"Bearer {old_token}"},
                          json={"current_password": pw, "new_password": "NewPass!123"})
        assert r.status_code == 200, r.text
        new_token = r.json()["token"]
        assert new_token and new_token != old_token
        # Old token rejected
        me_old = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {old_token}"})
        assert me_old.status_code == 401
        # New token works and must_change_password cleared
        me_new = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {new_token}"})
        assert me_new.status_code == 200
        assert me_new.json().get("must_change_password") in (False, None)
        # Login with new password works
        r2 = _login(email, "NewPass!123")
        assert r2.status_code == 200
        assert r2.json()["user"].get("must_change_password") in (False, None)


# ---------- ADMIN RESET PASSWORD ----------
class TestAdminResetPassword:
    def test_reset_invalidates_old_pw_and_old_session(self, admin_token, created_user_ids):
        info, email, pw = _create_user(admin_token, require_change=False)
        created_user_ids.append(info["id"])
        old_token = _login(email, pw).json()["token"]
        # Admin resets password
        r = requests.put(f"{API}/users/{info['id']}/password",
                         headers={"Authorization": f"Bearer {admin_token}"},
                         json={"password": "AdminReset!1", "require_change": True})
        assert r.status_code == 200
        # Old token rejected
        me_old = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {old_token}"})
        assert me_old.status_code == 401
        # Old password rejected
        r_old = _login(email, pw)
        assert r_old.status_code == 401
        # New password works and requires change
        r_new = _login(email, "AdminReset!1")
        assert r_new.status_code == 200
        assert r_new.json()["user"]["must_change_password"] is True

    def test_admin_cannot_reset_own_password(self, admin_token):
        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {admin_token}"}).json()
        r = requests.put(f"{API}/users/{me['id']}/password",
                         headers={"Authorization": f"Bearer {admin_token}"},
                         json={"password": "SomethingElse!1"})
        assert r.status_code == 400


# ---------- FORCE LOGOUT ----------
class TestForceLogout:
    def test_force_logout_invalidates_token(self, admin_token, created_user_ids):
        info, email, pw = _create_user(admin_token, require_change=False)
        created_user_ids.append(info["id"])
        tok = _login(email, pw).json()["token"]
        me1 = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert me1.status_code == 200
        # Admin force-logout
        r = requests.post(f"{API}/users/{info['id']}/logout",
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        me2 = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert me2.status_code == 401

    def test_admin_cannot_force_logout_self(self, admin_token):
        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {admin_token}"}).json()
        r = requests.post(f"{API}/users/{me['id']}/logout",
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 400


# ---------- RBAC ----------
class TestRBAC:
    def test_non_admin_cannot_reset_password(self, doctor_token, admin_token, created_user_ids):
        info, email, pw = _create_user(admin_token, require_change=False)
        created_user_ids.append(info["id"])
        r = requests.put(f"{API}/users/{info['id']}/password",
                         headers={"Authorization": f"Bearer {doctor_token}"},
                         json={"password": "hacked1!"})
        assert r.status_code == 403

    def test_non_admin_cannot_force_logout(self, doctor_token, admin_token, created_user_ids):
        info, email, pw = _create_user(admin_token, require_change=False)
        created_user_ids.append(info["id"])
        r = requests.post(f"{API}/users/{info['id']}/logout",
                          headers={"Authorization": f"Bearer {doctor_token}"})
        assert r.status_code == 403

    def test_change_password_requires_auth(self):
        r = requests.post(f"{API}/auth/change-password",
                          json={"current_password": "x", "new_password": "yyyyyy"})
        assert r.status_code == 401
