# Changelog — Veterans of Puerto Plata

## 2026-10-01
- **Configurable unit rules**: CPT codes now carry a `default_units` field (CptInput schema + CPT Codes page form/column). Invoices `defaultQtyFor` reads each code's configured units from the loaded catalog (replaces hard-coded 90837/90791); selecting or note-prefilling a code auto-fills units + minutes. Existing codes backfilled to 1.
- **Auto-save drafts**: Mailbox compose auto-saves to `mail_drafts` ~2.5s after the last edit (debounced, silent), updating the same draft id; shows a subtle "Auto-saved" indicator. Manual Save draft still available.
- **Invoice generator (cherry-picked from user ZIP, older snapshot — not applied wholesale)**: Generate-Invoice button on Progress Notes (list/card/view) and Patient-detail notes → `/invoices?from_note=&patient_id=` deep-link prefills patient, DOB/SSN, service date, ICD-10, provider, and the note's CPT line.
- **CEO Mailbox**: connected (Yahoo IMAP/SMTP, usvopp@yahoo.com); unread badge on sidebar; attach from patient folders + from computer (inline base64, 15MB/file, 20MB total); drag-drop; size hints + over-limit warning; attachment type-icon previews; save/open/delete drafts.
- **Progress Notes**: mark-complete (green badge/highlight), bulk complete, open/completed filter + clickable tally, completed date+signer in list/card, auto-complete-on-sign, completion stamp in PDF, Export Completed CSV; attestation line prints session date MM/DD/YYYY everywhere.
- **ICD-10 & CPT dropdowns** (Notes + Invoices): "Previously used" dropdown (ICD has delete + Manage), and the "+" button reveals the full catalog (code — description) with a "New code" footer.

## Notes for next agent
- User often uploads OLD ZIP snapshots — always diff & cherry-pick, never overwrite (would revert mailbox/completion/dropdown work).
- Mailbox creds + drafts live in DB (preview vs prod separate) — re-enter in prod via Mailbox → Connection after deploy.
