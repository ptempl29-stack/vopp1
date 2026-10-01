# Changelog — Veterans of Puerto Plata

## 2026-10-01
- **CEO Mailbox connected**: saved valid Yahoo IMAP/SMTP creds (usvopp@yahoo.com, app password jmajthbykqnlrljz) via encrypted `PUT /api/mailbox/settings`. IMAP+SMTP verified. NOTE: creds live in DB (preview vs prod separate) — re-enter in prod via Mailbox → Connection after deploy.
- **Mailbox unread badge**: `GET /api/mailbox/unread` (IMAP UNSEEN count); Layout.js polls every 60s + on `mailbox-refresh` window event (fired on open/delete), shows green count badge on the Mailbox sidebar tab (admin only).
- **Attach from patient folder in Mailbox compose/reply**: `GET /api/mailbox/attachable/{patient_id}` lists a patient's folder_items; `ComposeIn.attachment_item_ids` + `_send_message` now pulls bytes from object storage (`get_object`) and attaches them. Compose modal: patient picker → document picker → removable attachment chips. Verified: sent email in Sent folder carried Prog_07-15-2026.pdf.
- **Progress Notes ICD-10 & CPT dropdowns**: replaced free-text+chips with a "Previously used" dropdown (ICD has per-code delete + Manage footer). Removed the standalone "All codes" select; the **+** button now reveals the full catalog (code — description), with a "New ICD-10 Code" footer to add. Same pattern applied to Invoices ICD field.
- **Progress Notes completion**: mark-complete toggle (green badge/highlight), bulk complete, open/completed filter + clickable tally, completed date+signer in list/card, auto-complete-on-sign checkbox, completion stamp in PDF, Export Completed CSV (`GET /api/notes/export-completed`).
- **Attestation line** now prints the session date in MM/DD/YYYY across card/view/print/PDF; "Completed on MM/DD/YYYY by {signer}" stamped on note PDFs.
