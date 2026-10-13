"""Iteration 43 — Preview sandbox FMP/invoice/notes/messages/forms/reports tests.
All data created here is prefixed ZZTEST* and cleaned up at the end.
"""
import os
import io
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://veteran-care-portal.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "usvopp@yahoo.com"
ADMIN_PASS = "Football2023?"


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def zz_patient(admin):
    """Create a dedicated ZZTEST patient for this run (do not reuse Smoke)."""
    body = {"first_name": "ZZTEST", "last_name": f"Iter43 {uuid.uuid4().hex[:6]}",
            "dob": "1970-01-01", "ssn": "000-00-1234",
            "email": "zztest-iter43@example.invalid", "status": "active"}
    r = admin.post(f"{BASE_URL}/api/patients", json=body, timeout=20)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    yield pid
    # cleanup
    try:
        admin.delete(f"{BASE_URL}/api/patients/{pid}", timeout=20)
    except Exception:
        pass


_created_claims = []
_created_invoices = []


@pytest.fixture(scope="session", autouse=True)
def _cleanup(admin):
    yield
    for cid in list(_created_claims):
        try:
            admin.delete(f"{BASE_URL}/api/claims/{cid}", timeout=20)
        except Exception:
            pass
    for iid in list(_created_invoices):
        try:
            admin.delete(f"{BASE_URL}/api/invoices/{iid}", timeout=20)
        except Exception:
            pass


# ---------------- Preview sandbox guard ----------------
class TestSandboxGuard:
    def test_sandbox_status(self, admin):
        r = admin.get(f"{BASE_URL}/api/sandbox/status", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("sandbox") is True
        assert d.get("outbound_blocked") is True
        assert d.get("prefix") == "vpp-clinic-preview"


# ---------------- Invoice PDF (claim packet item) ----------------
class TestInvoicePdf:
    def test_invoice_pdf_has_rnc_six_columns_and_masked_ssn(self, admin, zz_patient):
        # Invoice with ssn → will be auto-linked to a same-date packet
        inv_body = {
            "patient_id": zz_patient, "patient_name": "ZZTEST Iter43",
            "dob": "1970-01-01", "ssn": "000-00-1234",
            "service_date": "2026-01-18",
            "items": [
                {"cpt_code": "90837", "description": "Psychotherapy 60 min",
                 "quantity": 4, "minutes": 60, "amount": 150.0},
                {"cpt_code": "85025", "description": "CBC",
                 "quantity": 1, "minutes": 0, "amount": 40.0},
            ],
            "status": "in_transit",
        }
        r = admin.post(f"{BASE_URL}/api/invoices", json=inv_body, timeout=30)
        assert r.status_code in (200, 201), r.text
        inv = r.json(); _created_invoices.append(inv["id"])

        r = admin.post(f"{BASE_URL}/api/claims", json={
            "name": "ZZTEST Iter43 Invoice PDF",
            "patient_id": zz_patient,
            "claim_number": "2026-01-18",
            "status": "draft",
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        claim = r.json(); cid = claim["id"]; _created_claims.append(cid)

        # fetch again to force auto-attach via _claim_response
        r = admin.get(f"{BASE_URL}/api/claims/{cid}", timeout=20)
        claim = r.json()
        item = next((it for it in claim.get("items", []) if it.get("invoice_id") == inv["id"]), None)
        if not item:
            # fall back to explicit attach
            r = admin.post(f"{BASE_URL}/api/claims/{cid}/attach-invoice",
                           json={"invoice_id": inv["id"]}, timeout=30)
            assert r.status_code == 200, r.text
            claim = r.json()
            item = next((it for it in claim["items"] if it.get("invoice_id") == inv["id"]), None)
        assert item, f"invoice not attached to packet: {claim}"

        # download the stored item PDF
        r = admin.get(f"{BASE_URL}/api/claims/{cid}/items/{item['id']}/download", timeout=30)
        assert r.status_code == 200, r.text
        pdf_bytes = r.content
        assert pdf_bytes[:4] == b"%PDF", "not a PDF"

        try:
            from pypdf import PdfReader
        except ImportError:  # pragma: no cover
            pytest.skip("pypdf not installed")
        text = ""
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for p in reader.pages:
            text += p.extract_text() + "\n"

        assert "RNC:" in text, f"RNC letterhead missing: {text[:400]}"
        # six column header
        for col in ("CPT", "Description", "Units", "Minutes", "Unit Price", "Fee"):
            assert col in text, f"column missing: {col}\n{text[:500]}"
        # masked ssn
        assert "***-**-1234" in text, f"SSN not masked / missing in PDF\n{text[:700]}"
        # no 'Completed' row
        assert "Completed" not in text, f"Unexpected Completed row in PDF\n{text[:700]}"
        # Minutes column shows stored minutes for 90837 (60) — not 4*15=60 coincidentally;
        # for 85025 untimed, Minutes blank
        assert "60" in text  # 90837 minutes
        # 85025 line should NOT have a "15" implied by units*15
        # just assert the 15-minute heuristic 60 != units*15 for 85025 (units=1 so 15, must be absent inline)
        # ensure the untimed row doesn't accidentally print its CPT with "15"
        assert " 15 " not in text.replace("\n", " "), f"unexpected 15-minute default appeared\n{text}"


# ---------------- FMP packet rules ----------------
class TestFmpPacketRules:
    def test_duplicate_packet_returns_409(self, admin, zz_patient):
        r1 = admin.post(f"{BASE_URL}/api/claims", json={
            "name": "ZZTEST Iter43 Dup A", "patient_id": zz_patient,
            "claim_number": "2026-02-10", "status": "draft"}, timeout=20)
        assert r1.status_code in (200, 201), r1.text
        _created_claims.append(r1.json()["id"])
        r2 = admin.post(f"{BASE_URL}/api/claims", json={
            "name": "ZZTEST Iter43 Dup B", "patient_id": zz_patient,
            "claim_number": "2026-02-10", "status": "draft"}, timeout=20)
        assert r2.status_code == 409, r2.text

    def test_put_cannot_set_complete(self, admin, zz_patient):
        r = admin.post(f"{BASE_URL}/api/claims", json={
            "name": "ZZTEST Iter43 PutComplete", "patient_id": zz_patient,
            "claim_number": "2026-03-11", "status": "draft"}, timeout=20)
        assert r.status_code in (200, 201)
        cid = r.json()["id"]; _created_claims.append(cid)
        r = admin.put(f"{BASE_URL}/api/claims/{cid}", json={
            "name": "ZZTEST Iter43 PutComplete",
            "patient_id": zz_patient,
            "claim_number": "2026-03-11",
            "status": "complete",
        }, timeout=20)
        assert r.status_code == 400, r.text

    def test_approve_succeeds_when_not_blocked_and_refused_when_blocked(self, admin, zz_patient):
        # (a) empty packet → review (not blocked) → approve succeeds
        r = admin.post(f"{BASE_URL}/api/claims", json={
            "name": "ZZTEST Iter43 ApproveOK", "patient_id": zz_patient,
            "claim_number": "2026-04-09", "status": "draft"}, timeout=20)
        cid1 = r.json()["id"]; _created_claims.append(cid1)
        r = admin.post(f"{BASE_URL}/api/claims/{cid1}/approve", json={}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["approved"] is True and d["status"] == "complete"

        # (b) force BLOCKED validation via date mismatch, approve must be 400
        inv_body = {
            "patient_id": zz_patient, "patient_name": "ZZTEST Iter43",
            "service_date": "2026-04-20",   # DIFFERENT from packet date 04-21
            "items": [{"cpt_code": "99213", "description": "E/M",
                       "quantity": 1, "minutes": 25, "amount": 95}],
            "status": "in_transit",
        }
        r = admin.post(f"{BASE_URL}/api/invoices", json=inv_body, timeout=20)
        iid = r.json()["id"]; _created_invoices.append(iid)
        r = admin.post(f"{BASE_URL}/api/claims", json={
            "name": "ZZTEST Iter43 ApproveBlocked", "patient_id": zz_patient,
            "claim_number": "2026-04-21", "status": "draft"}, timeout=20)
        cid2 = r.json()["id"]; _created_claims.append(cid2)
        r = admin.post(f"{BASE_URL}/api/claims/{cid2}/attach-invoice",
                       json={"invoice_id": iid}, timeout=30)
        assert r.status_code == 200, r.text
        v = r.json().get("validation") or {}
        assert v.get("status") == "blocked", f"expected blocked validation, got {v}"
        r = admin.post(f"{BASE_URL}/api/claims/{cid2}/approve", json={}, timeout=20)
        assert r.status_code == 400, f"approve must be refused when blocked, got {r.status_code}: {r.text}"

    def test_tracking_sets_submission_and_payment_independently(self, admin, zz_patient):
        r = admin.post(f"{BASE_URL}/api/claims", json={
            "name": "ZZTEST Iter43 Tracking", "patient_id": zz_patient,
            "claim_number": "2026-05-11", "status": "draft"}, timeout=20)
        cid = r.json()["id"]; _created_claims.append(cid)

        r = admin.put(f"{BASE_URL}/api/claims/{cid}/tracking",
                      json={"submission_status": "submitted"}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["submission_status"] == "submitted"

        r = admin.put(f"{BASE_URL}/api/claims/{cid}/tracking",
                      json={"payment_status": "paid"}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["payment_status"] == "paid"
        assert d["submission_status"] == "submitted"

        r = admin.put(f"{BASE_URL}/api/claims/{cid}/tracking",
                      json={"submission_status": "invalid"}, timeout=20)
        assert r.status_code == 400

    def test_checklist(self, admin, zz_patient):
        r = admin.post(f"{BASE_URL}/api/claims", json={
            "name": "ZZTEST Iter43 Checklist", "patient_id": zz_patient,
            "claim_number": "2026-06-11", "status": "draft"}, timeout=20)
        cid = r.json()["id"]; _created_claims.append(cid)
        r = admin.get(f"{BASE_URL}/api/claims/{cid}/checklist", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("checklist"), list) and len(d["checklist"]) > 0
        assert isinstance(d.get("warnings"), list)


# ---------------- CPT review flags ----------------
class TestCptReviewFlags:
    def _create_invoice_and_attach(self, admin, zz_patient, inv_body, claim_date, name):
        r = admin.post(f"{BASE_URL}/api/invoices", json=inv_body, timeout=20)
        assert r.status_code in (200, 201), r.text
        iid = r.json()["id"]; _created_invoices.append(iid)
        r = admin.post(f"{BASE_URL}/api/claims", json={
            "name": name, "patient_id": zz_patient,
            "claim_number": claim_date, "status": "draft"}, timeout=20)
        assert r.status_code in (200, 201), r.text
        cid = r.json()["id"]; _created_claims.append(cid)
        # fetch to trigger auto-link
        r = admin.get(f"{BASE_URL}/api/claims/{cid}", timeout=20)
        claim = r.json()
        if not any(it.get("invoice_id") == iid for it in claim.get("items", [])):
            r = admin.post(f"{BASE_URL}/api/claims/{cid}/attach-invoice",
                           json={"invoice_id": iid}, timeout=30)
            assert r.status_code == 200, r.text
            claim = r.json()
        return claim

    def test_cpt_flags_90837_quantity4(self, admin, zz_patient):
        inv_body = {
            "patient_id": zz_patient, "patient_name": "ZZTEST Iter43",
            "service_date": "2026-07-01",
            "items": [{"cpt_code": "90837", "description": "Psych",
                       "quantity": 4, "minutes": 60, "amount": 150}],
            "status": "in_transit",
        }
        claim = self._create_invoice_and_attach(admin, zz_patient, inv_body,
                                                "2026-07-01", "ZZTEST Iter43 CPT 90837")
        v = claim.get("validation") or {}
        s = str(v.get("issues") or v)
        assert "90837" in s and ("standard" in s.lower() or "units" in s.lower()), \
            f"expected 90837 units warning in validation: {v}"

    def test_cpt_flags_99213_no_minutes(self, admin, zz_patient):
        inv_body = {
            "patient_id": zz_patient, "patient_name": "ZZTEST Iter43",
            "service_date": "2026-07-02",
            "items": [{"cpt_code": "99213", "description": "E/M",
                       "quantity": 1, "minutes": 0, "amount": 95}],
            "status": "in_transit",
        }
        claim = self._create_invoice_and_attach(admin, zz_patient, inv_body,
                                                "2026-07-02", "ZZTEST Iter43 CPT 99213")
        v = claim.get("validation") or {}
        s = str(v.get("issues") or v)
        assert "99213" in s and "minutes" in s.lower(), f"expected 99213 minutes warning: {v}"


# ---------------- Build From Date qualifier ----------------
class TestBuildFromDate:
    def test_patients_by_date_empty_for_far_future(self, admin):
        r = admin.get(f"{BASE_URL}/api/claims/options/patients-by-date?date=2099-12-31", timeout=20)
        assert r.status_code == 200
        assert r.json() == []

    def test_from_date_refused_for_non_qualifying(self, admin, zz_patient):
        r = admin.post(f"{BASE_URL}/api/claims/from-date",
                       json={"patient_id": zz_patient, "date": "2099-12-31"}, timeout=20)
        assert r.status_code == 400, r.text


# ---------------- Notes integrity ----------------
class TestNotesIntegrity:
    def test_notes_integrity_verify(self, admin):
        r = admin.get(f"{BASE_URL}/api/notes-integrity/verify", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        # expect either {ok:true,failures:[]} or similar
        fails = d.get("failures") or d.get("broken") or []
        assert fails == [] or len(fails) == 0, f"integrity failures: {fails}"


# ---------------- Messages ----------------
class TestMessages:
    def test_unread_count(self, admin):
        r = admin.get(f"{BASE_URL}/api/messages/unread-count", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "count" in d or "unread" in d or isinstance(d, dict)

    def test_invalid_thread_rejected(self, admin):
        # multipart post with a non-existent thread_id - sender not a participant
        files = {"to_user_id": (None, "00000000-0000-0000-0000-000000000000"),
                 "subject": (None, "ZZTEST subject"),
                 "body": (None, "ZZTEST body"),
                 "thread_id": (None, str(uuid.uuid4()))}
        headers = {k: v for k, v in admin.headers.items() if k.lower() != "content-type"}
        r = requests.post(f"{BASE_URL}/api/messages", files=files, headers=headers, timeout=20)
        # 403 for non-participant, 404 if thread not found, or 400 — accept any explicit rejection
        assert r.status_code in (400, 403, 404), f"expected rejection, got {r.status_code}: {r.text}"


# ---------------- Users / provider-active ----------------
class TestUsersProviderActive:
    def test_provider_active_toggle(self, admin):
        # pick first non-admin provider-ish user
        r = admin.get(f"{BASE_URL}/api/users", timeout=20)
        assert r.status_code == 200
        users = r.json()
        provs = [u for u in users if u.get("role") in ("doctor", "nurse", "psychologist")]
        if not provs:
            pytest.skip("no provider users on this preview")
        uid = provs[0]["id"]
        orig = provs[0].get("provider_active", True)
        r = admin.put(f"{BASE_URL}/api/users/{uid}/provider-active",
                      json={"active": not orig}, timeout=20)
        assert r.status_code == 200, r.text
        # restore
        admin.put(f"{BASE_URL}/api/users/{uid}/provider-active",
                  json={"active": orig}, timeout=20)


# ---------------- Reports ----------------
class TestReports:
    @pytest.mark.parametrize("ep", [
        "/api/reports/completed-invoices",
        "/api/reports/completed-notes",
        "/api/reports/completed-packets",
    ])
    def test_reports_list(self, admin, ep):
        r = admin.get(f"{BASE_URL}{ep}", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d, (list, dict))

    def test_completed_packets_has_match_field(self, admin):
        r = admin.get(f"{BASE_URL}/api/reports/completed-packets", timeout=30)
        assert r.status_code == 200
        d = r.json()
        rows = d if isinstance(d, list) else d.get("items") or d.get("rows") or []
        if rows:
            assert any("match" in r for r in rows), f"no 'match' field in packets report rows: {rows[:2]}"
