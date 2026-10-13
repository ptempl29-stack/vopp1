# Read-only compatibility report: Claude patch 0de40ac → 42b0161 (24 files) vs current Preview code
Source: https://github.com/ptempl29-stack/vopp1/compare/0de40ac...42b0161.diff (sha256 873bd630…9818)
Status: NOTHING APPLIED. Dry-run only (`git apply --check`, `patch --dry-run`).

## Dry-run result
- Applies cleanly (16): schemas.py, appointments.py, folders.py, messages.py, patients.py, reports.py(new), users.py, server.py, App.js, sound.js(new), Appointments.js, Claims.js(fuzz), CompletedReports.js(new), Forms.js, Messages.js, PatientFolders.js, Team.js
- Failing hunks (8 files): claims.py 6/14, fmp.py 2/5, forms.py 1/8, notes.py 1/4, Layout.js 2/4, i18n.js 2/12, Notes.js 3/11
- Several "successful" hunks needed fuzz 3 → may land in wrong place. Manual port required.

## REQUIRED FIXES
R1 Invoice PDF RNC: patch drops `rnc`. Keep new layout, add `RNC: {settings.rnc}` to letterhead.
R2 Invoice PDF callers: new signature `_invoice_pdf(inv, settings)`; update ALL 4 current callers: claims.py L296, L907, L1122; fmp.py L375 (patch only knows 3, L296 would crash).
R3 SSN: invoices store full SSN → patch prints it. Mask to ***-**-1234.
R4 Six columns kept (CPT, Description, Units, Minutes, Unit Price, Fee). Minutes = Units×15 hard-coded → confirm.
R5 "Completed" date row on invoice PDF → confirm/omit (consistent with notes-PDF removal).
R6 FMP safeguards: hunks for merged / to-folder FAIL; manual port must keep `_assert_not_blocked` in merged, merged/async, to-folder; fmp approve already blocks (current L440) — patch's new filing step lands after that check, OK.
R7 to-folder: patch replaces file_pdf_into_folder (date_str/claim_folder_day, 502 on failure) with `_auto_file_packet_to_folder` that swallows errors and returns ok:true even if filing failed. Keep error reporting; tag folder item source="claim_packet"+claim_packet_id so Reports/Servicing work.
R8 Merge order: `_sorted_for_merge` overrides the existing manual reorder (PUT items-order). Decide.
R9 Duplication: `_sync_credentials_and_checklist` duplicates current `_sync_claim_packet_documents` auto-attach. Reuse existing; port only checklist+warnings.
R10 merged GET no longer marks complete, but async merge job + send-email still do → inconsistent. Decide.
R11 notes.py: hunk fails; current update_note has `_sync_matching_claims` + Completed feature (complete endpoint, export). Keep both. Editing an approved note clears provider signature while `completed` stays true → define rule.
R12 Notes.js: 3 hunks fail; keep current Completed filter, completeOnSign, export, ICD modal, asArray loading.
R13 Forms.js replaces form types → removes Intake/Consent/Medical History/Insurance/Referral (Preview has Intake/Consent forms). Append, don't replace.
R14 SECURITY forms.py: public_upload_back (unauthenticated token link) calls `_sync_form_attachment` → public uploader can overwrite a provider's diploma/exequatur. Restrict to staff routes.
R15 messages: list now sort asc + limit 2000 → newest dropped past 2000. Sort desc, reverse.
R16 Layout.js: current already polls /mailbox/unread badge; patch hunks fail. Merge both badges.
R17 Build-from-Date now lists only patients with status "completed" appointments; Preview has only "scheduled" → empty list. Decide/fallback.
R18 i18n.js: 2 hunks fail in Claims block (EN+ES) where FMP validation keys live. Manual merge, keep keys.
R19 reports.py: no audit logging of PHI report views (all other routers audit). Add log_audit.

## OPTIONAL
- appointments.py list sort date asc → created_at desc (confirm)
- patients.py sort by name
- reports PDF letterhead/RNC; biller access to notes report (diagnosis)
- GET checklist/merged write to DB (side effects on GET)
- message attachment: 15MB in-memory read; type by extension
- provider-active toggle, servicing status, billing review, threaded messages + ding, completed reports: fine as features
