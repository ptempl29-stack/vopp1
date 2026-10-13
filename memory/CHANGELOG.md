# Changelog — Veterans of Puerto Plata

## 2026-06 (fork)
- **Claim list: filter + blocked-first sort**: `Claims.js` list now sorts by severity (Blocked → Review → Ready) by default and has a Check-status filter bar (All / Blocked / Review / Ready with live counts, `claim-filter-*`). Client-side only, no new endpoint.
- **Claim list status chips**: `GET /claims` now attaches validation to every packet via `_attach_validation_bulk` (batched note/invoice/patient lookups + grouped duplicate detection — no N+1). `Claims.js` list view shows a color-coded "CHECK" column chip (`claim-val-chip`): red Blocked / amber Review / green Ready, with the issue count and a hover tooltip of all messages. Validation logic extracted into pure `_compute_validation`.
- **One-click date fix**: `_validate_packet` now returns a `fix` suggestion when every document shares one date that differs from the claim date. New `POST /claims/{cid}/fix-date` applies it (updates `claim_number` + packet name). The validation panel shows a "Fix: set claim date to MM/DD/YYYY" button (`claim-validation-fix-date`).
- **FMP claim validation engine (turned on)**: `_validate_packet` in `routers/claims.py` runs on every claim response (`_claim_response`). Flags date mismatches (note vs claim date, invoice vs claim date, note vs invoice — all **blocked**), patient-name mismatch (invoice=blocked, note=warning), unsigned note / missing ICD-10 / invoice without line-items or CPT, and warns when another packet already exists for the same patient+date. Returned as `validation: {status, issues}` (ready/review/blocked). Frontend `ClaimValidation` panel in `Claims.js` shows a color-coded banner + issue list; "Merge & Save PDF" is disabled when blocked.
- **Finalize blocked on conflicts**: `_assert_not_blocked` guards `/claims/{cid}/merged`, `/merged/async`, and `/to-folder` (HTTP 400 with the blocking message).
- **Duplicate claim-item prevention**: `attach-invoice` / `attach-note` / `attach-form` return 400 if the same invoice/note/form is already in the packet.
- **Progress Note PDF**: removed the "Completed on [date] by [signer]" stamp from `folder_filing.note_pdf` (per user — in-app Completed badge/filters/CSV kept).

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


## 2026-10-13 — Claude 24-file patch hand-merged (PREVIEW ONLY, not deployed)
- Preview sandbox: core/sandbox.py + storage guards (prefix vpp-clinic-preview, ledger, no deletes, reads limited to sandbox-written docs), email/SMS/mailbox send blocked. Encrypted Preview backup in /root/vopp_backups (sha256 e907acd8…9aec), user verified on Mac.
- Invoice PDF: RNC, six columns, stored minutes, masked SSN (also folder invoice PDF); 4 callers updated.
- FMP: Complete only via admin POST /claims/{cid}/approve; merge/email/save never change status; separate submission/payment tracking; legacy Complete label; duplicate packet 409; strict Build-from-Date; approved/complete packets frozen from auto-sync; CPT_TIMING_RULES review flags (no data changes); checklist endpoint; to-folder tags source=claim_packet.
- Notes: append-only HMAC-sealed note_versions, substantive edit clears signature/completed/approval, provider-only re-sign, complete requires signature, billing review, versions + integrity endpoints, deletion tombstones.
- Forms provider credentials (staff only), messages threads/attachments/unread, folder servicing status, provider-active toggle, Completed Work Reports (audit-logged), i18n EN/ES.
- Not ported (by decision): patient/appointment sort changes, forced merge order, approval-time auto-filing.

## Signature fix (PREVIEW, not deployed)
- Cause: editing a signed/Completed note + inserting the provider's SAVED signature (same image) was treated as carried-over -> signature silently cleared (HTTP 200) and auto-complete failed.
- Fix: notes.py — signature submitted with a substantive revision = explicit re-sign (authorized provider only); non-substantive save without signature keeps existing; authorization by account id (author_id/attending_provider_id) with normalized legacy-name fallback (unique match); admins/non-clinical cannot sign; can't reassign attending to self to bypass. Notes.js — editing a protected note clears the pad.
- Tests: API 8/8, UI iteration_44 8/8. ZZTEST Psych user added.

## Claim packet corrections + provider name fix (PREVIEW, not deployed)
- Prod cause confirmed: account "Saday Cabrera Rodriguez" vs notes "Saday Cabrera" -> legacy name match failed -> 403 on signing. core/providers.py: exact normalized match, else same first name + all names contained, unique clinical account only.
- Build from Date: default order letter→invoice→note→exequatur→diploma (cover always first, fixed row in view); only signed+Completed notes attached/auto-linked; credentials by provider account id; Document Checklist page removed from merged PDF (checklist card in app).
- Approve (claims + FMP) blocked unless 5 docs present and note signed+Completed by assigned provider (id-based, signed_by_id stored on signing).
- messages attachment download: RFC 5987 filename (fixes 500 on U+202F names).
- Tests: API scenarios pass; UI iteration_45 7/7.
