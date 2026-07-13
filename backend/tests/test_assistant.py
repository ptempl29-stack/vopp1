import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://veteran-care-portal.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def doctor_token():
    return _login("doctor@vpp.com", "doctor123")


@pytest.fixture(scope="module")
def biller_token():
    return _login("biller@vpp.com", "biller123")


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@vpp.com", "VPP-Adm1n!2026-Str0ng#Key")


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- RBAC / tab visibility ----------
class TestAssistantTabAccess:
    def test_doctor_has_assistant_tab(self, doctor_token):
        r = requests.get(f"{API}/auth/me", headers=_h(doctor_token), timeout=15)
        assert r.status_code == 200
        j = r.json()
        tabs = j.get("allowed_tabs") or j.get("user", {}).get("allowed_tabs") or []
        assert "assistant" in tabs, f"doctor tabs missing assistant: {tabs}"

    def test_admin_has_assistant_tab(self, admin_token):
        r = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15)
        assert r.status_code == 200
        j = r.json()
        tabs = j.get("allowed_tabs") or j.get("user", {}).get("allowed_tabs") or []
        assert "assistant" in tabs
        assert len(tabs) == 14, f"admin should have 14 tabs, got {len(tabs)}: {tabs}"

    def test_biller_no_assistant_tab(self, biller_token):
        r = requests.get(f"{API}/auth/me", headers=_h(biller_token), timeout=15)
        assert r.status_code == 200
        j = r.json()
        tabs = j.get("allowed_tabs") or j.get("user", {}).get("allowed_tabs") or []
        assert "assistant" not in tabs, f"biller should NOT have assistant tab: {tabs}"


# ---------- Conversation CRUD ----------
_created_convs = []  # cleanup tracking (doctor)


class TestConversationCRUD:
    def test_create_conversation(self, doctor_token):
        r = requests.post(f"{API}/assistant/conversations", headers=_h(doctor_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "id" in data
        assert data.get("title") == "New chat"
        assert data.get("messages") == []
        _created_convs.append(data["id"])

    def test_list_conversations(self, doctor_token):
        r = requests.get(f"{API}/assistant/conversations", headers=_h(doctor_token), timeout=15)
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list)
        assert any(c["id"] == _created_convs[0] for c in arr)
        c = next(c for c in arr if c["id"] == _created_convs[0])
        for k in ("id", "title", "message_count", "updated_at"):
            assert k in c

    def test_delete_conversation(self, doctor_token):
        r = requests.post(f"{API}/assistant/conversations", headers=_h(doctor_token), timeout=15)
        cid = r.json()["id"]
        d = requests.delete(f"{API}/assistant/conversations/{cid}", headers=_h(doctor_token), timeout=15)
        assert d.status_code == 200
        g = requests.get(f"{API}/assistant/conversations/{cid}", headers=_h(doctor_token), timeout=15)
        assert g.status_code == 404


# ---------- Message validation ----------
class TestMessageValidation:
    def _new_conv(self, tok):
        r = requests.post(f"{API}/assistant/conversations", headers=_h(tok), timeout=15)
        cid = r.json()["id"]
        _created_convs.append(cid)
        return cid

    def test_empty_content_400(self, doctor_token):
        cid = self._new_conv(doctor_token)
        r = requests.post(f"{API}/assistant/conversations/{cid}/message",
                          headers=_h(doctor_token), json={"content": "   "}, timeout=15)
        assert r.status_code == 400

    def test_too_long_400(self, doctor_token):
        cid = self._new_conv(doctor_token)
        r = requests.post(f"{API}/assistant/conversations/{cid}/message",
                          headers=_h(doctor_token), json={"content": "a" * 8001}, timeout=15)
        assert r.status_code == 400


# ---------- Real AI multi-turn ----------
class TestMultiTurn:
    def test_multiturn_context(self, doctor_token):
        # create fresh conversation
        r = requests.post(f"{API}/assistant/conversations", headers=_h(doctor_token), timeout=15)
        cid = r.json()["id"]
        _created_convs.append(cid)

        # Message 1 — establish fact
        r1 = requests.post(f"{API}/assistant/conversations/{cid}/message",
                           headers=_h(doctor_token),
                           json={"content": "Please remember: my name is Dr. Elena. Just acknowledge briefly."},
                           timeout=60)
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        assert "reply" in j1 and isinstance(j1["reply"], str) and len(j1["reply"]) > 0
        assert j1["user_message"]["role"] == "user"
        assert j1["assistant_message"]["role"] == "assistant"

        # Verify title auto-derived and message_count = 2
        lst = requests.get(f"{API}/assistant/conversations", headers=_h(doctor_token), timeout=15).json()
        c = next(c for c in lst if c["id"] == cid)
        assert c["message_count"] == 2
        assert c["title"] != "New chat", f"title should auto-derive, got: {c['title']}"

        # Message 2 — test context recall
        r2 = requests.post(f"{API}/assistant/conversations/{cid}/message",
                           headers=_h(doctor_token),
                           json={"content": "What name did I just tell you? Reply with the name only."},
                           timeout=60)
        assert r2.status_code == 200, r2.text
        reply2 = r2.json()["reply"].lower()
        assert "elena" in reply2, f"Multi-turn context lost. Reply: {reply2}"

        # message_count now 4
        lst2 = requests.get(f"{API}/assistant/conversations", headers=_h(doctor_token), timeout=15).json()
        c2 = next(c for c in lst2 if c["id"] == cid)
        assert c2["message_count"] == 4


# ---------- Ownership isolation ----------
class TestOwnership:
    def test_biller_cannot_access_doctor_conversation(self, doctor_token, biller_token):
        # doctor creates
        r = requests.post(f"{API}/assistant/conversations", headers=_h(doctor_token), timeout=15)
        cid = r.json()["id"]
        _created_convs.append(cid)

        # biller GET -> 404
        g = requests.get(f"{API}/assistant/conversations/{cid}", headers=_h(biller_token), timeout=15)
        assert g.status_code == 404

        # biller POST message -> 404
        m = requests.post(f"{API}/assistant/conversations/{cid}/message",
                          headers=_h(biller_token), json={"content": "hi"}, timeout=15)
        assert m.status_code == 404

        # biller DELETE -> should not delete; then doctor still sees it
        requests.delete(f"{API}/assistant/conversations/{cid}", headers=_h(biller_token), timeout=15)
        g2 = requests.get(f"{API}/assistant/conversations/{cid}", headers=_h(doctor_token), timeout=15)
        assert g2.status_code == 200, "doctor's conversation should still exist after biller delete attempt"


# ---------- Cleanup ----------
def test_zzz_cleanup(doctor_token):
    for cid in _created_convs:
        requests.delete(f"{API}/assistant/conversations/{cid}", headers=_h(doctor_token), timeout=15)
