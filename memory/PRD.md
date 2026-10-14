# PRD — Veterans of Puerto Plata (Clinic Management)

## Original Problem Statement
Bilingual (EN/ES) health clinic web app for managing patients, appointments, progress notes, invoices, CPT codes, internal messaging, and digital form handling. Calming tan & money-green palette, professional yet welcoming. Secure user roles, encrypted data storage, payment gateway integration. Key pillars: JWT RBAC with CEO-controlled per-user tab access, unified Progress Notes editor (AI + manual), Doxy.me telehealth, Resend outbound email + IMAP CEO Mailbox, FMP Claim Packet automation.

## Architecture
- Backend: FastAPI + MongoDB (motor), JWT auth (bcrypt), RBAC via require_roles(); modular routers under /api. PyMuPDF (fitz) + fpdf2 for PDFs.
- Frontend: React + Tailwind + shadcn, AuthContext (Bearer token), LanguageContext (EN/ES), PrivacyContext, react-router.
- Integrations: Emergent LLM key (AI notes/assistant), Doxy.me telehealth, Resend email, Twilio SMS (inactive — needs keys), IMAP/SMTP Yahoo (blocked — needs app password).

## Current admin
usvopp@yahoo.com / Football2023? (display name "CEO"). SEED_DEMO_USERS=false.

## Recently implemented (2026-10)
- **Progress Note "Mark complete"** (2026-10-01): notes carry a `completed` flag + `completed_at`/`completed_by`. New `PUT /api/notes/{nid}/complete {completed:bool}` (doctor/nurse/psychologist/admin, audited). Notes.js: per-note toggle button (`complete-note-{id}`) in card + list views; completed notes render a green **COMPLETED** badge (`note-completed-badge-{id}`), a green ring + light-green highlight on the card, and green row tint in list view. Button toggles Mark complete ↔ Reopen. i18n EN/ES keys added. Verified via API round-trip + screenshot.
- E-signature attestation line on progress notes (signer = attending_provider, fallback Saday Rodriguez Cabrera; date mm/dd/yyyy) — confirmed working, no change needed (2026-10-01).

(See CHANGELOG below / earlier iterations for full history — notes, invoices, claims, folders, FMP automation, AI assistant, ICD catalog, async packet builds, etc.)

## Pending / Backlog
- BLOCKED: Yahoo IMAP Mailbox — needs valid 16-char Yahoo App Password.
- DONE (2026-06): FMP validation engine turned on — mismatch flagging, blocked-finalize, duplicate-item prevention, same-day packet warning (see CHANGELOG).
- P2: Stripe payment gateway for invoices (needs user go-ahead; test key in env).
- P3: real in-browser .docx/.xlsx editing (deferred); refactor large files (claims.py, Forms.js, Invoices.js).

## Key endpoints (recent)
- PUT /api/notes/{nid}/complete — toggle note completion.
- POST /api/chat — public Claude endpoint (CHAT_API_KEY, rate-limited).
- POST /api/claims/{cid}/merged/async — background heavy PDF build.
- PUT /api/patients/{pid}/icd-bulk — bulk replace/remove ICD-10 across a patient's records.
- GET/POST /api/icd-codes — global ICD-10 catalog.

## Notes for next agent
- ZIP uploads from user are often OLD snapshots — always diff before applying; cherry-pick only genuinely new additions.
- ClaimBuilder.js frontend page was removed per user request; FMP backend endpoints remain.
- Production secrets (EMERGENT_LLM_KEY) must be set in deployment env; redeploys don't overwrite existing secrets.

## Status (Preview) — Claude 24-file update
- Implemented and tested in PREVIEW ONLY (see CHANGELOG). NOT deployed.
- Production blockers before publish: set production Secrets VOPP_ENV=production and a production-only NOTE_INTEGRITY_KEY (else preview values propagate via .env), production MongoDB export + document inventory, final user authorization.
- Open decisions: CPT 90837 units (4 × $150 vs 1 per session), CPT timing rules confirmation, audit-log retention policy.

## 2026-06 Disability letter auto-attach fix (PREVIEW ONLY, not deployed)
- Root cause (confirmed read-only in prod): matcher only checked folder_items filename keywords; prod letter (David Turner) exists only as a Forms doc (form_type "Disability Breakdown Letter").
- Fix in backend/routers/claims.py: _disability_letter_candidates (forms + folder category/description/label + expanded ES/EN keywords, patient-scoped, dedup); attaches only when exactly 1; >1 => approval blocker for staff review; warning log when not attached.
- Test: backend/tests/test_disability_letter_match.py (8/8 pass) + E2E from-date in Preview with ZZTEST data.
- Awaiting user authorization to deploy.

## 2026-06 FMP Cover Sheet upload (PREVIEW ONLY, not deployed)
- Cover row stays at top; "generated automatically" removed; Upload/Replace/View/Remove on the row (Claims.js, i18n.js).
- Backend claims.py: cover_sheet added to APPROVAL_REQUIRED (6 docs); POST /claims/{cid}/upload category=cover_sheet replaces existing cover, position 1, refused on approved/submitted packets; _cover_first used in merge + items-order; auto summary page removed for non-frozen packets (legacy approved/submitted/complete keep historical output); >1 cover = blocker.
- Tests: backend/tests/test_cover_sheet_upload.py 10/10, disability 8/8, iteration_46 frontend 8/8.
- fmp.py "Generate FMP Packet" template date-stamp flow unchanged.
- 2026-06: Added "Ready to approve" badge (list + detail; ready_to_approve flag from claims.py _ready_to_approve). Deploy of cover sheet + badge authorized and queued.
- 2026-06: Bulk approval (PREVIEW ONLY): "Ready to approve" filter chip, row checkboxes, confirm + result modals; POST /api/claims/bulk-approve (admin, per-packet re-validation via _approve_one, skips cover_review/not-ready with reasons, audit "(bulk)"). Tests iteration_47/48 pass. Not deployed.
- 2026-06: Full SSN (PREVIEW ONLY): core/ssn.py format_ssn (XXX-XX-XXXX) + with_patient_ssn (patient record by patient_id wins, fallback typed). Used in claims._invoice_pdf, folder_filing.invoice_pdf, note_pdf (new SSN line), billing/claims/fmp call sites. Saved PDFs untouched; Privacy mode toggle kept. Test backend/tests/test_full_ssn.py 11/11. Not deployed.
- 2026-06: SSN access by role (PREVIEW ONLY): settings key "ssn_access" (default all roles), admin-only GET/PUT /api/settings/ssn-access (audited); redact_ssn masks ***-**-1234 in patients/invoices/notes responses; guard_ssn_write keeps stored SSN for restricted roles; /auth/me can_view_full_ssn; SSN inputs readOnly; SsnAccessCard on Team page. PDFs always full. Tests: test_ssn_access_roles.py 18/18, iteration_49. Not deployed.
- 2026-06: PDF letterhead (PREVIEW ONLY): shared folder_filing.letterhead(); progress-note PDF now uses full company header (logo, name, tagline, RNC, address, phone, WhatsApp, email, mailing, insurance); FMP invoice contact line wraps instead of truncating at 160 chars. Test tests/test_pdf_letterhead.py 4/4. Not deployed.
- 2026-06: Checklist restored + payment box reading (PREVIEW ONLY): merged PDF = generated Fully Developed Claim checklist pages first, then uploaded cover sheet, then rest. core/payment_box.py: fillable/text PDF read first, else Claude Sonnet 5.5 vision (claude-sonnet-5-5, EMERGENT_LLM_KEY) -> provider/veteran/unclear; unclear => payment_review + approval blocker; PUT /api/claims/{cid}/payment-recipient (staff confirm). Checklist shows ☒/☐. Edit modal no longer defaults payment_to to provider. Test tests/test_payment_box.py 16/16. Not deployed.
- 2026-06: ICD-10-CM descriptions (PREVIEW ONLY): core/icd_codes.with_icd_descriptions (split , ; newline; catalog lookup; code-only when no description) used in all invoice PDF call sites (billing, claims x3, fmp) + checklist Diagnosis Treated; claims info_block wraps (align L). Invoices.js IcdDescriptions under ICD field + view modal, amber "Description not on file" (no-print). Test tests/test_icd_descriptions.py 9/9. Not deployed.
- 2026-06: Payment line fixed "Pay Provider" on checklist (PREVIEW ONLY); removed scan auto-detect (core/payment_box.py deleted), payment review blocker, PUT /claims/{cid}/payment-recipient, cover-row Provider/Veteran buttons, edit-modal Payment To select. fmp.py template flow (_read_payment_recipient + "Select the payment recipient" block) left unchanged. Test tests/test_pay_provider_fixed.py 10/10. Not deployed.
- 2026-06: Fully Developed Claim checklist REMOVED completely (PREVIEW ONLY): _build_packet_pdf now merges documents only (uploaded cover first) for all packets incl. approved; GET /claims/{cid}/checklist removed; checklist row + i18n keys removed. On-screen "Claim Summary" card (invoice no./amount) kept. Not deployed.
