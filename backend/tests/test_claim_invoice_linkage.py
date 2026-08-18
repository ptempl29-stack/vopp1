from core.claim_invoices import (claim_folder_day, invoice_summary, related_invoice,
                                 unlinked_related_claims, payment_recipient_from_fields,
                                 progress_note_codes)


def test_invoice_created_after_claim_is_related_by_patient_and_service_date():
    claim = {"patient_id": "patient-1", "claim_number": "2026-08-17", "items": []}
    saved_invoice = {
        "id": "invoice-64", "patient_id": "patient-1", "service_date": "2026-08-17",
        "invoice_number": "MB-0064", "total": 425.50,
    }

    summary = invoice_summary(related_invoice(claim, [saved_invoice]))

    assert summary["invoice_id"] == "invoice-64"
    assert summary["invoice_number"] == "MB-0064"
    assert summary["amount_billed"] == 425.50


def test_invoice_created_before_claim_is_related_by_patient_and_service_date():
    saved_invoice = {
        "id": "invoice-65", "patient_id": "patient-1", "service_date": "2026-08-18T15:30:00Z",
        "invoice_number": "MB-0065", "total": 600.0,
    }
    new_claim = {"patient_id": "patient-1", "claim_number": "2026-08-18", "items": []}

    summary = invoice_summary(related_invoice(new_claim, [saved_invoice]))

    assert summary["invoice_number"] == "MB-0065"
    assert summary["amount_billed"] == 600.0


def test_explicit_invoice_link_wins_over_another_invoice_on_the_same_day():
    claim = {
        "patient_id": "patient-1", "claim_number": "2026-08-17",
        "source_invoice_id": "chosen-invoice", "items": [],
    }
    invoices = [
        {"id": "newest-invoice", "patient_id": "patient-1", "service_date": "2026-08-17"},
        {"id": "chosen-invoice", "patient_id": "patient-1", "service_date": "2026-08-17"},
    ]

    assert related_invoice(claim, invoices)["id"] == "chosen-invoice"


def test_unrelated_patient_or_date_does_not_populate_claim_summary():
    claim = {"patient_id": "patient-1", "claim_number": "2026-08-17", "items": []}
    invoices = [
        {"id": "wrong-patient", "patient_id": "patient-2", "service_date": "2026-08-17"},
        {"id": "wrong-date", "patient_id": "patient-1", "service_date": "2026-08-16"},
    ]

    assert related_invoice(claim, invoices) is None


def test_later_invoice_auto_links_an_existing_completed_claim():
    saved_invoice = {
        "id": "invoice-64", "patient_id": "patient-1", "service_date": "2026-08-17",
        "invoice_number": "MB-0064", "total": 425.50,
    }
    claims = [
        {"id": "completed-match", "status": "complete", "patient_id": "patient-1",
         "claim_number": "2026-08-17", "items": []},
        {"id": "wrong-date", "status": "complete", "patient_id": "patient-1",
         "claim_number": "2026-08-16", "items": []},
        {"id": "already-linked", "status": "complete", "patient_id": "patient-1",
         "claim_number": "2026-08-17", "source_invoice_id": "invoice-existing", "items": []},
    ]

    assert [claim["id"] for claim in unlinked_related_claims(saved_invoice, claims)] == ["completed-match"]


def test_patient_folder_uses_selected_claim_session_date():
    assert claim_folder_day("2026-07-15") == "07-15-2026"
    assert claim_folder_day("2026-07-15T18:22:00Z") == "07-15-2026"


def test_payment_recipient_reads_checked_cover_sheet_field_without_guessing_blank():
    assert payment_recipient_from_fields([("Pay Provider", "Yes"), ("Pay Veteran", "Off")]) == "provider"
    assert payment_recipient_from_fields([("Pay Provider", "Off"), ("Pay Veteran", "On")]) == "veteran"
    assert payment_recipient_from_fields([("Pay Provider", "Off"), ("Pay Veteran", "Off")]) is None


def test_progress_note_review_codes_preserve_values_and_expose_absence():
    assert progress_note_codes({"icd10": "F43.10", "cpt_code": "90837"}) == {
        "icd10": "F43.10", "cpt_code": "90837",
    }
    assert progress_note_codes({"icd10": "", "cpt_code": None}) == {
        "icd10": None, "cpt_code": None,
    }


def test_claim_summary_preserves_saved_invoice_codes_and_line_items():
    invoice = {
        "id": "invoice-64", "invoice_number": "MB-0064", "total": 425.50,
        "service_date": "2026-08-17", "patient_name": "Saved Patient Name",
        "icd10": "F43.10", "provider": "Saved Provider", "visit_reason": "Therapy",
        "items": [{"cpt_code": "90837", "quantity": 1, "amount": 425.50}],
    }

    summary = invoice_summary(invoice)

    assert summary["patient_name"] == "Saved Patient Name"
    assert summary["icd10"] == "F43.10"
    assert summary["provider"] == "Saved Provider"
    assert summary["items"] == invoice["items"]
