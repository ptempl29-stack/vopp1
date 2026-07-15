"""Backend tests for the Patient Folders feature (iteration 32)."""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://veteran-care-portal.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# Ensure all tests in this file share the same xdist worker (share module fixtures)
pytestmark = pytest.mark.xdist_group(name="patient_folders")

ADMIN_EMAIL = "usvopp@yahoo.com"
ADMIN_PASSWORD = "Football2023?"


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def ctx(admin_client):
    """Shared state: primary patient + a temp second patient (created + torn down)."""
    r = admin_client.get(f"{API}/folders/patients")
    assert r.status_code == 200
    patients = r.json()
    assert len(patients) >= 1
    primary = patients[0]

    # Create a temp second patient for cross-patient move
    p2 = admin_client.post(f"{API}/patients", json={
        "first_name": "TEST_MoveTarget", "last_name": "Patient", "dob": "1990-01-01",
        "sex": "M", "phone": "0000000000",
    })
    assert p2.status_code in (200, 201), p2.text
    second_id = p2.json()["id"]

    state = {"primary": primary, "second_id": second_id,
             "created_subfolder_ids": [], "created_item_ids": []}
    yield state

    # Teardown: bulk-delete created items, delete subfolders, delete 2nd patient
    if state["created_item_ids"]:
        admin_client.post(f"{API}/folders/items/bulk-delete", json={"ids": state["created_item_ids"]})
    for sid in state["created_subfolder_ids"]:
        admin_client.delete(f"{API}/folders/subfolders/{sid}")
    admin_client.delete(f"{API}/patients/{second_id}")


class TestListing:
    def test_list_patient_folders(self, admin_client):
        r = admin_client.get(f"{API}/folders/patients")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) >= 1
        p = data[0]
        for key in ("id", "name", "item_count", "subfolder_count"):
            assert key in p

    def test_get_patient_folder(self, admin_client, ctx):
        pid = ctx["primary"]["id"]
        r = admin_client.get(f"{API}/folders/{pid}")
        assert r.status_code == 200
        d = r.json()
        assert d["patient_id"] == pid
        assert "subfolders" in d and "items" in d

    def test_get_patient_folder_404(self, admin_client):
        r = admin_client.get(f"{API}/folders/nonexistent-xyz")
        assert r.status_code == 404

    def test_options_forms(self, admin_client):
        r = admin_client.get(f"{API}/folders/options/forms")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestSubfolders:
    def test_create_and_rename_subfolder(self, admin_client, ctx):
        pid = ctx["primary"]["id"]
        r = admin_client.post(f"{API}/folders/{pid}/subfolders", json={"name": "TEST_Labs"})
        assert r.status_code == 200, r.text
        sf = r.json()
        assert sf["name"] == "TEST_Labs"
        assert sf["patient_id"] == pid
        ctx["created_subfolder_ids"].append(sf["id"])
        ctx["primary_sub"] = sf["id"]

        # verify persisted via GET
        g = admin_client.get(f"{API}/folders/{pid}")
        assert any(s["id"] == sf["id"] for s in g.json()["subfolders"])

        # rename
        r2 = admin_client.put(f"{API}/folders/subfolders/{sf['id']}", json={"name": "TEST_Labs_Renamed"})
        assert r2.status_code == 200
        assert r2.json()["name"] == "TEST_Labs_Renamed"

    def test_create_subfolder_empty_name_400(self, admin_client, ctx):
        pid = ctx["primary"]["id"]
        r = admin_client.post(f"{API}/folders/{pid}/subfolders", json={"name": "  "})
        assert r.status_code == 400

    def test_create_subfolder_bad_patient_404(self, admin_client):
        r = admin_client.post(f"{API}/folders/badpid/subfolders", json={"name": "TEST_x"})
        assert r.status_code == 404


class TestItems:
    def test_upload_into_subfolder(self, admin_client, ctx):
        pid = ctx["primary"]["id"]
        sid = ctx["primary_sub"]
        files = {"file": ("test_upload.txt", io.BytesIO(b"hello world"), "text/plain")}
        data = {"subfolder_id": sid, "label": "TEST_Doc"}
        # Use a raw session to send multipart (need to strip content-type header for this call)
        s = requests.Session()
        s.headers.update({k: v for k, v in admin_client.headers.items() if k.lower() == "authorization"})
        r = s.post(f"{API}/folders/{pid}/upload", files=files, data=data)
        assert r.status_code == 200, r.text
        item = r.json()
        assert item["source"] == "upload"
        assert item["subfolder_id"] == sid
        assert item["label"] == "TEST_Doc"
        ctx["created_item_ids"].append(item["id"])
        ctx["upload_item"] = item

    def test_upload_bad_extension(self, admin_client, ctx):
        pid = ctx["primary"]["id"]
        s = requests.Session()
        s.headers.update({k: v for k, v in admin_client.headers.items() if k.lower() == "authorization"})
        files = {"file": ("bad.exe", io.BytesIO(b"x"), "application/octet-stream")}
        r = s.post(f"{API}/folders/{pid}/upload", files=files, data={"subfolder_id": "", "label": ""})
        assert r.status_code == 400

    def test_edit_item(self, admin_client, ctx):
        iid = ctx["upload_item"]["id"]
        r = admin_client.put(f"{API}/folders/items/{iid}",
                             json={"label": "TEST_Renamed", "description": "d1"})
        assert r.status_code == 200
        assert r.json()["label"] == "TEST_Renamed"
        assert r.json()["description"] == "d1"

    def test_download_item(self, admin_client, ctx):
        iid = ctx["upload_item"]["id"]
        r = admin_client.get(f"{API}/folders/items/{iid}/download")
        assert r.status_code == 200
        assert b"hello world" in r.content
        assert "attachment" in r.headers.get("content-disposition", "").lower()

    def test_move_within_same_patient_to_root(self, admin_client, ctx):
        iid = ctx["upload_item"]["id"]
        pid = ctx["primary"]["id"]
        r = admin_client.post(f"{API}/folders/items/{iid}/move",
                              json={"patient_id": pid, "subfolder_id": None})
        assert r.status_code == 200
        assert r.json()["subfolder_id"] is None

    def test_move_to_different_patient(self, admin_client, ctx):
        iid = ctx["upload_item"]["id"]
        target_pid = ctx["second_id"]
        r = admin_client.post(f"{API}/folders/items/{iid}/move",
                              json={"patient_id": target_pid, "subfolder_id": None})
        assert r.status_code == 200
        assert r.json()["patient_id"] == target_pid

        # verify appears in target
        g = admin_client.get(f"{API}/folders/{target_pid}")
        assert any(it["id"] == iid for it in g.json()["items"])
        # verify NOT in source
        g2 = admin_client.get(f"{API}/folders/{ctx['primary']['id']}")
        assert not any(it["id"] == iid for it in g2.json()["items"])

    def test_move_target_folder_not_found(self, admin_client, ctx):
        iid = ctx["upload_item"]["id"]
        r = admin_client.post(f"{API}/folders/items/{iid}/move",
                              json={"patient_id": ctx["second_id"], "subfolder_id": "wrong-sid"})
        assert r.status_code == 400

    def test_bulk_delete(self, admin_client, ctx):
        # upload one more for bulk delete
        pid = ctx["primary"]["id"]
        s = requests.Session()
        s.headers.update({k: v for k, v in admin_client.headers.items() if k.lower() == "authorization"})
        files = {"file": ("bulk.txt", io.BytesIO(b"bulk"), "text/plain")}
        r = s.post(f"{API}/folders/{pid}/upload", files=files, data={"subfolder_id": "", "label": "TEST_Bulk"})
        assert r.status_code == 200
        new_id = r.json()["id"]

        rb = admin_client.post(f"{API}/folders/items/bulk-delete", json={"ids": [new_id]})
        assert rb.status_code == 200
        assert rb.json()["deleted"] == 1

    def test_delete_single_item(self, admin_client, ctx):
        # delete the moved item
        iid = ctx["upload_item"]["id"]
        r = admin_client.delete(f"{API}/folders/items/{iid}")
        assert r.status_code == 200
        # remove from cleanup list to avoid double-delete
        if iid in ctx["created_item_ids"]:
            ctx["created_item_ids"].remove(iid)


class TestSubfolderDelete:
    def test_delete_subfolder_moves_items_to_root(self, admin_client, ctx):
        pid = ctx["primary"]["id"]
        # create a fresh subfolder + item
        sr = admin_client.post(f"{API}/folders/{pid}/subfolders", json={"name": "TEST_ToDelete"})
        assert sr.status_code == 200
        sid = sr.json()["id"]

        s = requests.Session()
        s.headers.update({k: v for k, v in admin_client.headers.items() if k.lower() == "authorization"})
        files = {"file": ("keep.txt", io.BytesIO(b"keep me"), "text/plain")}
        ur = s.post(f"{API}/folders/{pid}/upload", files=files, data={"subfolder_id": sid, "label": "TEST_Keep"})
        item_id = ur.json()["id"]
        ctx["created_item_ids"].append(item_id)

        # delete subfolder
        d = admin_client.delete(f"{API}/folders/subfolders/{sid}")
        assert d.status_code == 200

        # item now has subfolder_id=None, not deleted
        g = admin_client.get(f"{API}/folders/{pid}")
        found = [it for it in g.json()["items"] if it["id"] == item_id]
        assert len(found) == 1
        assert found[0]["subfolder_id"] is None
        # cleanup subfolder from list (already deleted)
        if sid in ctx["created_subfolder_ids"]:
            ctx["created_subfolder_ids"].remove(sid)


class TestAuthz:
    def test_unauthenticated_denied(self):
        r = requests.get(f"{API}/folders/patients")
        assert r.status_code in (401, 403)
