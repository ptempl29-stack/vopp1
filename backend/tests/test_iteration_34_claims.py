"""Iteration 34: Claim Packet per-item actions + packet Send/Merge -> complete."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "usvopp@yahoo.com"
ADMIN_PASSWORD = "Football2023?"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def test_patient(h):
    # Reuse existing Test Patient
    r = requests.get(f"{BASE_URL}/api/claims/options/patients", headers=h)
    assert r.status_code == 200
    tp = next((p for p in r.json() if p["name"] == "Test Patient"), None)
    assert tp, "Test Patient required"
    return tp


@pytest.fixture(scope="module")
def packet(h, test_patient):
    """Build a fresh packet via from-date so this run is idempotent."""
    r = requests.post(f"{BASE_URL}/api/claims/from-date", headers=h,
                      json={"patient_id": test_patient["id"], "date": "2026-07-15"})
    assert r.status_code == 200, r.text
    pkt = r.json()
    assert len(pkt["items"]) >= 1
    yield pkt
    # cleanup
    requests.delete(f"{BASE_URL}/api/claims/{pkt['id']}", headers=h)


def test_get_packet(h, packet):
    r = requests.get(f"{BASE_URL}/api/claims/{packet['id']}", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "draft"


def test_rename_item(h, packet):
    item_id = packet["items"][0]["id"]
    new_name = "TEST_Renamed_Invoice.pdf"
    r = requests.put(f"{BASE_URL}/api/claims/{packet['id']}/items/{item_id}",
                     headers=h, json={"filename": new_name})
    assert r.status_code == 200
    got = next(i for i in r.json()["items"] if i["id"] == item_id)
    assert got["filename"] == new_name


def test_rename_item_empty(h, packet):
    item_id = packet["items"][0]["id"]
    r = requests.put(f"{BASE_URL}/api/claims/{packet['id']}/items/{item_id}",
                     headers=h, json={"filename": "   "})
    assert r.status_code == 400


def test_rename_unknown(h, packet):
    r = requests.put(f"{BASE_URL}/api/claims/{packet['id']}/items/does-not-exist",
                     headers=h, json={"filename": "x.pdf"})
    assert r.status_code == 404


def test_reorder(h, packet):
    if len(packet["items"]) < 2:
        pytest.skip("need 2+ items")
    ids = [i["id"] for i in packet["items"]]
    reversed_ids = list(reversed(ids))
    r = requests.put(f"{BASE_URL}/api/claims/{packet['id']}/items-order",
                     headers=h, json={"ids": reversed_ids})
    assert r.status_code == 200
    got = [i["id"] for i in r.json()["items"]]
    assert got == reversed_ids
    # persist check
    r2 = requests.get(f"{BASE_URL}/api/claims/{packet['id']}", headers=h)
    assert [i["id"] for i in r2.json()["items"]] == reversed_ids


def test_download_item(h, packet):
    item_id = packet["items"][0]["id"]
    r = requests.get(f"{BASE_URL}/api/claims/{packet['id']}/items/{item_id}/download",
                     headers=h)
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "").lower()
    assert len(r.content) > 100


def test_item_to_folder(h, packet, test_patient):
    item_id = packet["items"][0]["id"]
    r = requests.post(f"{BASE_URL}/api/claims/{packet['id']}/items/{item_id}/to-folder",
                     headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "FMP Claim" in body["subfolder"]
    # Verify it appears in the folder
    fr = requests.get(f"{BASE_URL}/api/folders/{test_patient['id']}", headers=h)
    assert fr.status_code == 200
    subfolders = fr.json().get("subfolders", [])
    assert any(body["subfolder"] in s.get("name", "") for s in subfolders), \
        f"subfolder {body['subfolder']} not in {[s.get('name') for s in subfolders]}"


def test_merged_marks_complete(h, packet):
    r = requests.get(f"{BASE_URL}/api/claims/{packet['id']}/merged", headers=h)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert len(r.content) > 200
    # status now complete
    g = requests.get(f"{BASE_URL}/api/claims/{packet['id']}", headers=h)
    assert g.json()["status"] == "complete"


def test_send_email_wiring(h, packet):
    """Endpoint should be wired. Result depends on Resend config/quota.
    Acceptable: 200 (sent), 400 (not configured), or 502 (quota/domain)."""
    r = requests.post(f"{BASE_URL}/api/claims/{packet['id']}/send-email",
                      headers=h, json={"to": "noreply@example.com"})
    assert r.status_code in (200, 400, 502), r.text
    if r.status_code == 200:
        assert r.json()["ok"] is True


def test_send_email_missing_recipient(h, packet):
    r = requests.post(f"{BASE_URL}/api/claims/{packet['id']}/send-email",
                      headers=h, json={"to": ""})
    assert r.status_code == 400


def test_delete_item(h, packet):
    item_id = packet["items"][-1]["id"]  # last one
    r = requests.delete(f"{BASE_URL}/api/claims/{packet['id']}/items/{item_id}",
                       headers=h)
    assert r.status_code == 200
    assert all(i["id"] != item_id for i in r.json()["items"])


def test_status_complete_valid_in_update(h, packet):
    """PUT /claims/{cid} should accept status='complete'."""
    r = requests.put(f"{BASE_URL}/api/claims/{packet['id']}", headers=h,
                     json={"name": packet["name"], "patient_id": packet.get("patient_id"),
                           "claim_number": packet.get("claim_number"),
                           "status": "complete", "notes": None})
    assert r.status_code == 200
    assert r.json()["status"] == "complete"


def test_rbac_unauth():
    r = requests.get(f"{BASE_URL}/api/claims")
    assert r.status_code in (401, 403)
