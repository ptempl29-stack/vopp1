"""Iteration 35: Backend tests for FMP claim packet cover + checklist merged PDF,
invoice numbering MB-0025 floor, item category tagging, and USD-DOP rate settings."""
import io
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN = {"email": "usvopp@yahoo.com", "password": "Football2023?"}
TEST_PATIENT_ID = "6fa0fdd7-8ecf-4619-bb59-03265cbe7834"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    token = r.json().get("token")
    if token:
        sess.headers.update({"Authorization": f"Bearer {token}"})
    return sess


# ---------- Invoice numbering ----------
class TestInvoiceNumbering:
    def test_next_number_floor(self, s):
        r = s.get(f"{BASE}/api/invoices/next-number")
        assert r.status_code == 200
        num = r.json()["invoice_number"]
        assert num.startswith("MB-")
        seq = int(num.split("-")[1])
        assert seq >= 25, f"expected floor 25, got {num}"

    def test_create_invoice_gets_number_and_advances(self, s):
        before = s.get(f"{BASE}/api/invoices/next-number").json()["invoice_number"]
        payload = {
            "patient_id": TEST_PATIENT_ID,
            "service_date": "2026-07-15",
            "items": [{"cpt_code": "99213", "description": "Test", "amount": 100.0, "quantity": 1}],
            "status": "unpaid",
        }
        r = s.post(f"{BASE}/api/invoices", json=payload)
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv["invoice_number"] == before, f"created invoice # {inv['invoice_number']} != expected {before}"
        after = s.get(f"{BASE}/api/invoices/next-number").json()["invoice_number"]
        assert int(after.split("-")[1]) == int(before.split("-")[1]) + 1
        # cleanup
        s.delete(f"{BASE}/api/invoices/{inv['id']}")


# ---------- Settings usd_to_dop ----------
class TestSettingsRate:
    def test_public_settings_has_usd_to_dop(self, s):
        r = requests.get(f"{BASE}/api/public/settings", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "usd_to_dop" in d
        assert isinstance(d["usd_to_dop"], (int, float))

    def test_put_settings_persists_rate(self, s):
        cur = s.get(f"{BASE}/api/settings")
        assert cur.status_code == 200
        body = cur.json()
        body["usd_to_dop"] = 63.5
        r = s.put(f"{BASE}/api/settings", json=body)
        assert r.status_code == 200, r.text
        got = s.get(f"{BASE}/api/settings").json()
        assert float(got["usd_to_dop"]) == 63.5
        # public reflects it
        pub = requests.get(f"{BASE}/api/public/settings").json()
        assert float(pub["usd_to_dop"]) == 63.5
        # restore to 60
        body["usd_to_dop"] = 60
        s.put(f"{BASE}/api/settings", json=body)


# ---------- Claim packet cover fields + category + merged PDF ----------
class TestClaimPacketFMP:
    @pytest.fixture(scope="class")
    def packet(self, s):
        # find existing packet with items OR build from-date
        r = s.get(f"{BASE}/api/claims")
        packets = r.json()
        # Prefer any packet for the test patient with items
        chosen = next((p for p in packets if p.get("patient_id") == TEST_PATIENT_ID and p.get("items")), None)
        if not chosen:
            # attempt build from-date
            r2 = s.post(f"{BASE}/api/claims/from-date", json={"patient_id": TEST_PATIENT_ID, "date": "2026-07-15"})
            if r2.status_code == 200:
                chosen = r2.json()
            else:
                pytest.skip(f"No packet available and from-date failed: {r2.status_code} {r2.text}")
        return chosen

    def test_cover_fields_persist(self, s, packet):
        cid = packet["id"]
        payload = {
            "name": packet.get("name") or "FMP",
            "patient_id": packet.get("patient_id"),
            "claim_number": packet.get("claim_number"),
            "status": packet.get("status", "draft"),
            "notes": packet.get("notes"),
            "va_claim_number": "VA-TEST-9911",
            "veteran_physical_address": "Calle Real 1, Puerto Plata",
            "veteran_mailing_address": "PO Box 42, Puerto Plata",
            "diagnosis_narrative": "Test diagnosis narrative",
            "payment_to": "provider",
        }
        r = s.put(f"{BASE}/api/claims/{cid}", json=payload)
        assert r.status_code == 200, r.text
        upd = r.json()
        assert upd["va_claim_number"] == "VA-TEST-9911"
        assert upd["payment_to"] == "provider"
        assert upd["veteran_physical_address"].startswith("Calle Real")
        assert upd["veteran_mailing_address"].startswith("PO Box")
        assert upd["diagnosis_narrative"] == "Test diagnosis narrative"
        # verify GET persists
        got = s.get(f"{BASE}/api/claims/{cid}").json()
        assert got["va_claim_number"] == "VA-TEST-9911"

    def test_item_category_persists(self, s, packet):
        cid = packet["id"]
        cur = s.get(f"{BASE}/api/claims/{cid}").json()
        items = cur.get("items", [])
        if not items:
            pytest.skip("No items in packet")
        iid = items[0]["id"]
        r = s.put(f"{BASE}/api/claims/{cid}/items/{iid}",
                  json={"category": "va_disability_letter"})
        assert r.status_code == 200, r.text
        got = s.get(f"{BASE}/api/claims/{cid}").json()
        found = next(i for i in got["items"] if i["id"] == iid)
        assert found.get("category") == "va_disability_letter"

    def test_merged_pdf_structure(self, s, packet):
        cid = packet["id"]
        r = s.get(f"{BASE}/api/claims/{cid}/merged")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        content = r.content
        assert content[:4] == b"%PDF"
        try:
            from pypdf import PdfReader
        except ImportError:
            pytest.skip("pypdf not installed")
        reader = PdfReader(io.BytesIO(content))
        pages = len(reader.pages)
        assert pages >= 2, f"expected at least 2 pages (cover+checklist), got {pages}"
        p1 = reader.pages[0].extract_text() or ""
        p2 = reader.pages[1].extract_text() or ""
        assert "Foreign Medical Program" in p1, f"cover text missing: {p1[:200]}"
        assert "Fully Developed Claim Packet" in p1
        # cover key rows
        for kw in ["Veteran:", "Diagnosis Treated", "Payment Direction"]:
            assert kw in p1, f"missing '{kw}' in cover"
        assert "FMP Fully Developed Claim Checklist" in p2
        # progress note or invoice auto-check + tagged category
        assert "[X]" in p2 or "[ X ]" in p2

        # verify packet count = 2 + doc pages
        got = s.get(f"{BASE}/api/claims/{cid}").json()
        # sum pages from items
        expected_doc_pages = 0
        for it in got["items"]:
            # download and count pages if PDF
            dr = s.get(f"{BASE}/api/claims/{cid}/items/{it['id']}/download")
            if dr.status_code == 200 and dr.content[:4] == b"%PDF":
                try:
                    expected_doc_pages += len(PdfReader(io.BytesIO(dr.content)).pages)
                except Exception:
                    pass
            else:
                # image => 1 page
                expected_doc_pages += 1
        assert pages == 2 + expected_doc_pages, \
            f"page count {pages} != 2 (cover+checklist) + {expected_doc_pages} doc pages"

        # verify status was set to complete
        got2 = s.get(f"{BASE}/api/claims/{cid}").json()
        assert got2["status"] == "complete"
