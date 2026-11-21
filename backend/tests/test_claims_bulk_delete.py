"""Client Packets bulk delete (POST /api/claims/bulk-delete) — runs against a live server like the other iteration tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": os.environ.get("ADMIN_EMAIL", ""), "password": os.environ.get("ADMIN_PASSWORD", "")})
    assert r.status_code == 200
    return s


def _packet(c, name):
    r = c.post(f"{BASE_URL}/api/claims", json={"name": name, "status": "draft"})
    assert r.status_code == 200
    return r.json()["id"]


def test_bulk_delete_removes_only_selected_packets(admin_client):
    a, b, keep = (_packet(admin_client, f"TEST bulk {n}") for n in ("a", "b", "keep"))
    r = admin_client.post(f"{BASE_URL}/api/claims/bulk-delete", json={"ids": [a, b, "no-such-id"]})
    assert r.status_code == 200 and r.json() == {"deleted": 2, "skipped": 1}
    left = {p["id"] for p in admin_client.get(f"{BASE_URL}/api/claims").json()}
    assert a not in left and b not in left and keep in left
    admin_client.delete(f"{BASE_URL}/api/claims/{keep}")


def test_bulk_delete_requires_admin():
    r = requests.post(f"{BASE_URL}/api/claims/bulk-delete", json={"ids": ["x"]})
    assert r.status_code in (401, 403)
