# Auto invoice from signed progress note (Build Packet) — portable patch
Built on ab8213f code (2026-10-15). Self-contained module + small hooks.
Files:
- auto_invoice.py -> copy to backend/core/auto_invoice.py (unchanged on any version; uses routers.billing._compute_next_number or equivalent next-number helper, db.cpt_codes {code, description, amount, default_units}).
- auto_invoice_hooks.patch -> hook in POST /claims/from-date (call auto_invoice_for_day when no invoice exists for the date; attach; return auto_invoice_problems), toast in Claims.js, i18n key autoInvoiceCreated.
- test_auto_invoice.py -> backend/tests (synthetic ZZTEST data only), 13 checks.
Reapply on 8bcbfab: copy module; in claims.py claim_from_date add the same 6-line hook before items are built (8bcbfab uses next-number helper in routers/billing.py or core/invoice_numbers.py — adjust _unique_next_number import); add auto_invoice flag on invoice item; Claims.js toast; i18n key. Run test.
