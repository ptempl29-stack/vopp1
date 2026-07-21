# PRD — Veterans of Puerto Plata (Clinic Management)

## Original Problem Statement
Bilingual (EN/ES) health clinic web app for managing patients, appointments, progress notes, invoices, CPT codes, internal messaging, and digital form handling. Calming tan & money-green palette, professional yet welcoming. Secure user roles (doctors, nurses, receptionists, billers), responsive design, robust form management. Added mid-build: Telehealth video calling.

## User Choices
- Auth: JWT email/password (custom), demo accounts per role.
- Payments: skipped for now (no gateway).
- AI: progress-note summarization via Emergent LLM key (gpt-5.4).
- Priority: Patients + Appointments + Progress Notes first.
- Branding: designed in-house (tan & money-green, Manrope + IBM Plex Sans).
- Telehealth: Jitsi Meet (no API keys).

## Architecture
- Backend: FastAPI + MongoDB (motor). JWT auth (bcrypt), role-based access via require_roles(). All routes under /api.
- Frontend: React + Tailwind + shadcn, AuthContext (Bearer token in localStorage), LanguageContext (EN/ES dict), react-router.
- Integrations: emergentintegrations LlmChat (AI notes); Jitsi external_api.js (telehealth).

## User Personas
- Doctor / Nurse: patients, appointments, notes (+AI), telehealth, messages.
- Receptionist: patients, appointments, forms, invoices, messages.
- Biller: invoices/CPT, messages.
- Admin: all + user registration.

## Implemented (2026-06)
- JWT auth + 5 seeded role accounts; RBAC enforced (403 on disallowed) + UI gating (perms.js).
- Patients CRUD + search; Appointments CRUD; Progress Notes + AI summarize (working).
- Invoices with CPT-code library + total calc + mark paid.
- Digital Forms (send/receive/status); Internal Messaging (inbox, read).
- **Patient-facing public forms**: tokenized `/form/:token` (no auth), bilingual EN/ES field rendering from server templates (Intake/Consent/Medical History/Insurance/Referral), submission flows back as "received" with staff-side responses viewer; resubmit blocked + server-side required-field validation.
- Dashboard stats; Telehealth (Jitsi) with per-appointment room launch.
- Bilingual EN/ES toggle; responsive tan & money-green UI.
- Tested: 36/36 backend, frontend 100%.

## FMP Claim Packets — Fully Developed Claim format (2026-06-20)
- Completed/merged claim packets now generate a PDF that begins with an auto-generated **Summary/Cover page** (Veteran, DOB, SSN/VA Claim File No., Service Date, Provider, Clinic Address, Diagnosis, CPT, Invoice, Amount Billed, Payment Direction) + an **FMP Fully Developed Claim Checklist page**, followed by all attached documents. Built in `_build_packet_pdf()` in `routers/claims.py`; used by GET /claims/{cid}/merged, POST /claims/{cid}/send-email, POST /claims/{cid}/to-folder.
- Claim documents can be tagged with a **category** (cover_sheet, invoice, progress_note, va_disability_letter, fmp_registration, provider_exequatur, provider_diploma) via the item edit modal; checklist rows auto-check for present categories (invoice/note auto by source).
- Claim Packet edit modal gained FMP cover fields: va_claim_number, veteran_physical_address, veteran_mailing_address, diagnosis_narrative, payment_to (provider/veteran).
- Per-document actions (view/edit/move/download/delete/arrange) + packet Send (emails merged packet); merging marks packet **complete** (green badge + green row). (iter 34-35)
- Invoice numbering floor set to **MB-0025** (INVOICE_SEQ_BASE=25 in billing.py).
- Billing Reports: in Spanish (ES) all money shows **RD$ = USD × rate** using editable `usd_to_dop` setting (default 60) on the CEO Clinic Letterhead modal. Amounts formatted with thousands separators.
- Verified: iteration_34.json (100%), iteration_35.json (100%).


## Claim Packets — "Build from Date" shortcut (2026-06-19)
- New backend endpoint `POST /api/claims/from-date` (admin only): given `{patient_id, date}`, auto-creates an FMP Claim packet named `"{Patient Name} {mm/dd/yyyy} FMP Claim"` (claim_number = date), auto-pulling that day's matching invoice(s) (by `service_date`) and progress note(s) (by `visit_date`) as rendered PDF items. Returns 404 if nothing found for the date.
- New claim item `source: "note"` supported (icon/tone/label + storage cleanup on delete). i18n keys added (EN/ES): `src_note, buildFromDate, buildFromDateTitle, buildFromDateHint, build, serviceDate`.
- Frontend `Claims.js`: "Build from Date" button + modal (patient select + date). On success opens the new packet. Tested via curl (invoice+note packet built) and screenshot.

## Resend Sender (2026-06-19) — BLOCKED on domain verification
- User requested `SENDER_EMAIL=admin@vpp.com`. Resend rejected: **vpp.com domain is NOT verified**. Reverted `SENDER_EMAIL` to `onboarding@resend.dev` (test sender, owner-only) to keep email functional. ACTION: user must verify vpp.com at resend.com/domains, then we switch the sender.


## Security Audit (2026-06) — REMEDIATED
- SEC-001 (CRITICAL): demo seeding now gated behind `SEED_DEMO_USERS` env (off by default in code; `true` only in preview); admin password moved to a strong env value with idempotent rotation; **brute-force lockout added** (5 failed attempts / 15 min, keyed on X-Forwarded-For client IP + email).
- SEC-002 (HIGH): `/api/notes` now restricted to clinical roles (doctor/nurse/admin) — billers/receptionists get 403.
- SEC-003 (MEDIUM): patient search input `re.escape`-d + length-capped (ReDoS neutralized).
- SEC-004 (MEDIUM): telehealth room names are unguessable — scheduled = uuid; **ad-hoc rooms now use crypto.randomUUID()** (was timestamp). Jitsi BAA limitation documented — swap to BAA-covered video before real PHI.
- Hardening: JWT TTL reduced to 8h; invoice/form status allowlists; message mark-read ownership check; **TTL index on `login_attempts.expires_at`** (auto-expires lockout rows).
- Re-audit (2026-06) verdict: most items resolved. Remaining, accepted for PREVIEW only: demo staff seeding active (`SEED_DEMO_USERS=true`) so the demo is usable — MUST be `false` in production. Login lockout keyed on client-supplied X-Forwarded-For is spoofable (LOW/P3) — rely on a trusted proxy in production.
- Still OPEN for production PHI: set `SEED_DEMO_USERS=false`, explicit CORS origins, move token to httpOnly cookie, Mongo data-at-rest encryption, HIPAA-BAA video provider, and trusted-proxy IP for throttling.

## CPT Codes Module (2026-06)
- DB-backed `cpt_codes` collection (seeded with 10 common codes), full CRUD at `/api/cpt-codes` (biller/admin only). Sidebar page with search, add/edit/delete; codes feed the Invoices line-item dropdown live.

## Iteration 6 (2026-06) — Reports, Roles, Permissions, Uploads
- **Billing Reports** (`/api/reports/billing` + `/export`, biller/admin): summary cards (billed/collected/outstanding/#invoices), revenue-over-time area chart, revenue-by-CPT bar chart + table, date-range filter, CSV export.
- **Psychologist role**: limited default tabs (Dashboard, Appointments, Telehealth, Notes, Messages); can create notes & appointments.
- **Admin-assignable per-user tab access**: users carry `allowed_tabs`; admin Team page creates users and toggles each employee's tabs (`PUT /api/users/{id}/tabs`, `GET /api/meta/tabs`); sidebar + routes gate on `allowed_tabs`.
- **Forms upload + external URL**: upload files (PDF/img/Word/txt ≤15MB) to Emergent object storage (`POST /api/forms/upload`, `GET /api/forms/{id}/download`), or attach an external link; both downloadable/openable from Forms.
- Tested: 74/74 backend, frontend 100%.

## Iteration 7 (2026-06) — Admin employee control + patient form emails
- **Admin edits any employee**: name, email, role, and password reset via `PUT /api/users/{id}` (email uniqueness enforced; an admin's role is locked). Team page has an Edit action per user.
- **Email patient the form link**: on form creation, staff can enter/auto-fill a recipient email; backend sends the secure `/form/{token}` link via Yahoo SMTP (`send_email`, env-gated). Best-effort — form always saves even if email fails/unconfigured (`email_sent` flag).
- ⚠️ EMAIL SENDING IS NOT YET ACTIVE — `YAHOO_EMAIL`/`YAHOO_APP_PASSWORD` are empty in backend/.env. Sending no-ops until credentials are added.
- Tested: 86/86 backend, frontend E2E 100%.

## Security Re-Audit #3 (2026-06) — NEW-feature findings REMEDIATED
- SEC-002 (HIGH, attachment IDOR + token-in-URL): download now requires a DB-resolved staff role (FORMS_ROLES) via Authorization header; `?auth=` query token removed (frontend downloads via authenticated blob).
- SEC-003 (HIGH, stored-XSS via upload content-type): upload stores a server-derived content type from an extension allowlist (ignores client value); download forces `application/octet-stream` + `Content-Disposition: attachment` + `X-Content-Type-Options: nosniff`.
- SEC-004 (MEDIUM, stale-token role on CSV export): export now uses DB-resolved `require_roles('biller','admin')`; token no longer in URL.
- SEC-005 (MEDIUM, phishing via client link_base): form email link built from server `PUBLIC_BASE_URL`; client `link_base` ignored.
- P3: create_form/upload/status/download gated by FORMS_ROLES; register enforces min-6 password.
- Verified: 96/96 backend, frontend E2E.
- STILL ACCEPTED (preview-only / prod-config): SEC-001 demo seeding active (`SEED_DEMO_USERS=true`) for demo usability — set `false` in production; CORS `*`, localStorage token, XFF-based lockout, HIPAA data-at-rest + BAA video remain production hardening items.

## Iteration 9 (2026-06) — Signature capture + audit LOW fixes
- **Doctor signatures on progress notes**: draw-to-sign canvas (`SignaturePad`) in the note editor; stored as PNG data URL with `signed_by` + `signed_at`; rendered with attribution on the note card. Signature optional; 600KB size guard.
- **Patient signatures on forms**: Consent template's signature field renders a signature pad on the unauthenticated public form; drawn signature stored in submission (1.2MB guard) and shown as an image in the staff responses viewer. Client + server required-field enforcement.
- Security LOW fixes: non-admin `GET /users` returns only id/name/role (no email/tabs); `send_email` strips CR/LF from subject + validates recipient (header-injection hardening).
- Tested: 106/106 backend, frontend E2E.

## Iteration 10 (2026-06) — Signatures on all forms + Signed badge
- Patient **signature field added to every form template** (Intake, Medical History, Insurance, Referral; Consent already had one) — renders a signature pad on the public patient link.
- Forms list shows a green **"Signed" badge** on any received form whose submission contains a signature image.
- Tested: 111/111 backend, frontend E2E (signed-badge correct across 84 forms, 0 mismatches).

## Iteration 11 (2026-06) — SOAP progress notes
- Progress note editor now has a **Note Type** toggle: **Free Text** (original, unchanged) or **SOAP** (Subjective/Objective/Assessment/Plan four-field layout).
- SOAP notes auto-build a combined `content` server-side so search, AI summarize, and signatures work identically for both types; card shows a SOAP badge + labeled S/O/A/P sections. Empty notes rejected (client + 400).
- Tested: 118/118 backend, frontend E2E.

## Iteration 12 (2026-06) — Company letterhead on forms
- Admin-editable **clinic letterhead** (name, tagline, address, phone, email, logo upload) via `settings` collection: `GET /api/public/settings` (no auth), `GET /api/settings` (authed), `PUT /api/settings` (admin, logo ≤~650KB).
- Reusable `Letterhead` component renders at the top of every patient-facing public form and on the staff responses view. Editable from Team → "Clinic Letterhead".
- Tested: 126/126 backend, frontend E2E (public no-auth read, admin-only write 403 for others, logo guard).

## Iteration 13 (2026-06) — Invoice builder refinements + Forms Print/PDF
- **Invoice builder**: full-page printable builder (`Invoices.js`) with letterhead, patient/invoice info, CPT line items, Save/Print/Save-as-PDF.
  - Visit Reason dropdown options: General Consultation, Physical Therapy, Therapeutic Massage, Relaxing Massage, Evaluation, Follow-up, Re-evaluation, Psychotherapy, Group Therapy.
  - Units → Minutes auto-mapping (15 min/unit; minutes read-only). Fee = Unit Price × Units. Unit Price auto-fills from selected CPT code.
  - Invoice number auto-advances after each save (`GET /api/invoices/next-number`, format MB-000N). Verified MB-0029 → MB-0030 via curl.
  - Added missing EN/ES i18n labels (saveInvoice, visitReason, addService, etc.).
- **Forms Print / Save as PDF**: responses viewer modal now has Print + Save-as-PDF buttons using `window.print()`; `#form-print` region in `App.css` @media print isolates the letterhead form document (title, metadata, all field responses, signature image) — modal chrome hidden. Verified via print-media screenshots (empty + signed forms).
- Verified: frontend print-emulation screenshots + backend curl (invoice create/next-number).

## Iteration 14 (2026-06) — Daily Progress Note type
- Added a **third note type** "Daily Progress Note" to the Notes page (toggle alongside Free Text & SOAP), mimicking the user's example: clinic **letterhead** header + structured fields (DOB, Gender, SSN, Visit Date, ICD-10-CM, Reason for Visit, Attending Provider, Referring Provider) + Notes body.
  - DOB/Gender **auto-fill** from selected patient (editable). Reason-for-visit reuses the invoice list (incl. Group Therapy). Attending/Referring provider dropdowns list staff providers (doctor/nurse/psychologist).
  - Kept AI Summarize + provider Signature capture. Added **Print / Save as PDF** with letterhead (`#note-print` @media print region).
  - Backend `NoteInput` extended with dob/gender/ssn/visit_date/reason_for_visit/attending_provider/referring_provider/icd10; note card shows a "Daily Progress Note" badge + visit metadata.
- Verified: frontend modal + print-emulation screenshots; backend curl (daily note create persists all fields).

## Iteration 15 (2026-06) — Backend refactor into routers
- Split the monolithic `server.py` (~980 lines) into a clean package:
  - `core/` → `config.py` (constants/tabs/settings), `db.py` (mongo client + now_iso + logger), `security.py` (bcrypt/JWT/get_current_user/require_roles/effective_tabs), `storage.py` (object storage), `email_utils.py` (Yahoo SMTP).
  - `models/schemas.py` → all Pydantic models. `data/seed.py` → CPT_LIBRARY, DEMO_USERS, FORM_TEMPLATES.
  - `routers/` → auth, settings, patients, appointments, notes, billing (cpt+invoices+reports), messages, forms (+public), dashboard. `server.py` now only wires app, includes routers under `/api`, runs startup seeding + CORS.
- All 48 routes import cleanly; behavior/paths unchanged.
- Tested: 132/132 backend pytest (full regression + 6 new tests) + full frontend Playwright regression — 100% pass. RBAC, brute-force lockout, /users minimization, forms security all intact.
- Advisory (non-blocking, deferred): `/invoices/next-number` uses count-based numbering (race-prone under concurrent creates → consider a counters collection); add `Field(ge=1)` on invoice quantity; sanitize the raw LLM 500 message.

## Security Audit #4 (2026-06) — post-refactor, REMEDIATED
- SEC-001 (HIGH, CONFIRMED): `GET /api/invoices` was gated only by `get_current_user`, exposing SSN/policy numbers to all authenticated roles. FIXED → `require_roles("biller","receptionist")` (+admin override) and `ssn`/`policy_number` excluded from the list projection. Verified: doctor/psych 403, biller/reception 200, no SSN in payload.
- SEC-003 (MEDIUM, forms portion): `GET /api/forms` returned patient form responses (medical history/insurance) to any authenticated user. FIXED → `require_roles("doctor","nurse","receptionist")` matching the Forms-tab design. Verified: psych/biller 403, doctor/reception 200.
- P3 (error leak): `/api/notes/summarize` no longer returns the raw LLM exception; returns a generic message and logs server-side.
- ACCEPTED for PREVIEW (production-config items, unchanged): SEC-002 demo seeding active (`SEED_DEMO_USERS=true`, weak demo passwords) for demo usability — MUST be `false` + strong passwords in production; wildcard CORS; XFF-based lockout (needs trusted proxy in prod); localStorage token; patient directory readable by all staff (small-clinic design); HIPAA data-at-rest + BAA video remain prod items.

## Iteration 16 (2026-06) — HIPAA Audit Log
- New `audit_logs` collection + `core/audit.py` (`log_audit`, IP via middleware contextvar, 2-year TTL) + `routers/audit.py` (`GET /api/audit`, admin-only, filters: resource/action/date-range + pagination).
- Captures **views + changes** across Patients, Notes, Invoices, Forms + login success/failed. Admin-only "Audit Log" sidebar page (`AuditLog.js`) with filters, pagination, IP/actor columns. New `audit` tab in ALL_TABS.
- Tested: 155/155 backend, frontend E2E (admin-only nav, filters, pagination).

## Iteration 17 (2026-06) — Editable letterhead + Daily Note UI + View/Edit notes
- **Editable letterhead**: `EditableLetterhead` component in the Daily Progress Note edits clinic info inline and saves GLOBALLY via `PUT /api/settings` (now allowed for admin+doctor+nurse+psychologist; 403 for receptionist/biller). Fields: clinic name, tagline, physical address, email, phone, mailing address, logo (no primary insurance). Reflects on forms/invoices.
- **Daily Note UI**: patient dropdown moved beneath the letterhead (before DOB); Title field removed (auto-generated title `Daily Progress Note — <patient> · <date>`).
- **View & Edit saved notes**: note cards now have View + Edit actions. View modal shows the full note (free/soap/daily) with letterhead + "Edited by" attribution + Print. Edit opens the pre-filled editor; `PUT /api/notes/{id}` updates + writes an audit `update` row (sets updated_at/updated_by; re-signs if signature changes).
- Verified: backend curl (note create→edit persists, updated_by set) + frontend screenshots (view modal, edit pre-fill, letterhead edit/save global persist).

## Iteration 18 (2026-06) — Staff signature, Doxy.me telehealth, note-summary merge, "sin AI" note
- **Staff signature**: SignaturePad now supports image **upload** (`allowUpload`) in addition to draw. Providers can save a reusable **default signature** to their profile (`PUT /api/auth/signature`; returned in login + `/auth/me` as `default_signature`), which auto-applies to new notes, plus "Insert my signature" / "Save as my default" controls.
- **Doxy.me telehealth** (replaces public Jitsi): `routers/telehealth.py` — `PUT /api/telehealth/my-room` (validated slug, strips `doxy.me/` prefix, stored per-provider) and `POST /api/telehealth/doxy-invite` (builds `doxy.me/<room>?username=&autocheckin=true&pid=<HMAC>`, optional email; no PHI in link). Telehealth page: room config, "Open My Waiting Room", per-appointment "Copy Patient Link". No API key needed; BAA required before production (see DEPLOYMENT.md).
- **Note summary merge**: saved-note view + card no longer show an "AI SUMMARY" label; content and AI summary render together in one box.
- **New "Progress Note sin AI"** note type (`daily_no_ai`): identical to the Daily Progress Note layout (letterhead + structured fields + notes) but with NO AI Summary section.
- **Prod hardening documented** in `/app/memory/DEPLOYMENT.md` (SEED_DEMO_USERS=false, explicit CORS_ORIGINS, Doxy.me BAA) — preview left as-is per user.
- Tested: 177/177 backend + full frontend regression (iteration 15) for signature/telehealth/view-edit; iteration 18 note-merge + sin-AI verified via screenshots.

## Iteration 19 (2026-06) — Unified Progress Note editor
- ALL four note types (Free Text, SOAP, Daily, Progress Note sin AI) now share the SAME header as the Daily note: editable letterhead + Patient, DOB, Gender, SSN, Visit Date, ICD-10-CM, Reason for Visit, Attending & Referring Provider — in the editor, the saved View, AND print (`#note-print` / `note-fields`).
- Per-type body: Free Text/Daily/sin AI → single Notes box (`nf-content`); SOAP → S/O/A/P boxes. Title field removed entirely (auto-title `<Type> — <patient> · <date>`), patient required for all.
- AI: removed the labeled "AI SUMMARY" editing box; a small "AI Summarize" button remains on Free Text/SOAP/Daily (absent on Progress Note sin AI). Generated summary merges into the note (no heading) on save/view. `nf-title` and `nf-summary` testids removed; unified body testid is `nf-content`.
- Backend `POST/PUT /api/notes` persist all header fields for any note_type.
- Tested: 187/187 backend pytest + 100% frontend (all 4 types unified-header contract, create, view, print, regression). No issues.

## Iteration 20 (2026-06) — WhatsApp header, blank templates, WhatsApp send, patient upload-back
- **WhatsApp number** added to clinic letterhead (`settings.whatsapp`, max 40 chars): displayed in `Letterhead`, editable in `EditableLetterhead` (notes) + Team → Clinic Letterhead (`lh-whatsapp`).
- **Blank downloadable templates**: `GET /api/forms/blank-template/{docx|xlsx|pdf}` (FORMS_ROLES) generate blank Word/Excel/PDF with the clinic name (python-docx / openpyxl / fpdf2). Forms header buttons `tpl-docx/xlsx/pdf-btn`.
- **Send via WhatsApp**: Forms row button (`whatsapp-<id>`) opens `wa.me/<patientPhone>?text=<clinic + form link>`.
- **Patient upload-back**: `POST /api/public/forms/{token}/upload` (no auth, allowed exts, 15MB cap, blocks re-upload after `received`); public form page shows an upload section (`pf-doc-file`, `pf-doc-upload-btn`). `GET /api/public/forms/{token}` now returns `has_template`/`has_attachment`. Staff view/download returned file via existing `GET /api/forms/{id}/download` (octet-stream + nosniff).
- **KNOWN LIMITATION (not built)**: true in-app editing of Word/Excel/PDF *content* requires a document-editing server (OnlyOffice/Collabora) — not feasible in this container. Online form-field forms remain fully editable; documents are view/download/store/replace only.
- Tested: 210/210 backend pytest + 100% frontend; plus re-upload guard (400) and whatsapp max-length (422) verified via curl.

## Backlog / tech-debt notes
- Split `server.py` (~780 lines) into per-resource routers.
- Billing report aggregates in Python; move to Mongo aggregation pipeline past ~10k invoices.
- `?auth=` query-token on download/export could leak via logs; consider short-lived signed URLs.

## Known Limitations
- AI summarization returns clean 500 until the Emergent LLM Universal Key balance is topped up ($0 currently).
- No payment gateway (deferred by user choice).

## Iteration 21 (2026-06) — Claim Packets (Admin-only)
- **Claim Packets** module (`/api/claims`, admin-only) to bundle documents for VA billing. Router `routers/claims.py` registered in `server.py`; tab `claims` in `ALL_TABS` (admin default), page `/app/frontend/src/pages/Claims.js`, nav in `Layout.js`, bilingual i18n keys.
- Packet fields: name, patient (optional), claim number, status (draft/submitted), notes. Full CRUD.
- **Attach existing forms** (`POST /claims/{cid}/attach-form`, references form's stored attachment), **attach invoices** (`POST /claims/{cid}/attach-invoice` → renders a styled invoice PDF via fpdf2 and stores as item), **upload new docs** (`POST /claims/{cid}/upload`, exts pdf/img/doc/docx/txt/xls/xlsx, 15MB). Remove items, individual download (octet-stream + nosniff), and **merged PDF** (`GET /claims/{cid}/merged`, combines PDF + image items only; Word/Excel downloadable individually).
- Admin-only option lists: `GET /claims/options/forms|invoices|patients`.
- Storage cleanup: deleting a packet or removing an upload/invoice item now calls `storage.delete_object()` (best-effort) to avoid orphaned blobs; form-sourced items are NOT deleted (shared with the form). UI confirms before packet delete.
- Tested: 238/238 backend pytest + 100% frontend (CRUD, attach-invoice→PDF, upload, merged PDF, item download/remove, RBAC hide for non-admin). No critical issues.
- Known limitation: invoice-PDF text uses latin-1 fallback (`_s`) — non-Latin chars (accents/ñ) replaced with `?`; acceptable for now, revisit with a Unicode TTF font.

## Iteration 22 (2026-06) — Create Invoice from Note + SMS forms (Twilio)
- **Create Invoice from Note**: Invoices page gains a "Create from Note" picker (biller/receptionist). New `GET /api/notes/for-billing?patient_id=` (roles biller/receptionist/admin; clinical roles 403) returns a patient's notes (header fields + 180-char content preview). Selecting a session pre-fills invoice patient, DOB, gender, SSN, service date (visit_date/created), visit reason, ICD-10, and provider; biller then adds CPT line items. Free-text reason injected into the reason dropdown if not preset.
- **Send forms via SMS (Twilio)**: `POST /api/forms/{fid}/send-sms` (FORMS_ROLES) texts the patient the secure form link via `core/sms_utils.py` (twilio SDK). Env-gated (`TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_PHONE_NUMBER` — currently EMPTY) → returns `{sent:false, configured:false}` and the Forms SMS button (`sms-{id}`, next to WhatsApp) shows a friendly "SMS not configured" toast. ⚠️ SMS SENDING IS INACTIVE until the user adds Twilio credentials.
- Tested: 15/15 backend pytest + 100% frontend (both flows, RBAC 403, graceful unconfigured SMS, regression). No issues.

## Iteration 23 (2026-06) — Admin Settings area + Staff Invite flow
- **Settings** (gear) sidebar item (admin-only, `team` tab) — the former "Team" page relabeled and expanded to house Staff Members, Role/Tab access, Clinic Letterhead, and Invitations. Routes: `/settings` (and legacy `/team` still works).
- **Invite Staff**: admin creates an invite (`POST /api/invites`) picking email + role (admin role rejected) + allowed tabs → generates a single-use, no-expiry copyable link `/accept-invite/{token}` (token via `secrets.token_urlsafe(32)`). Invitations table lists pending/accepted with copy-link + revoke (`GET`/`DELETE /api/invites`).
- **Accept flow** (public, no auth): `GET /api/public/invites/{token}` shows invited email/role; `POST /api/public/invites/{token}/accept` (name + password) creates the user with the invite's role + tabs, marks the invite accepted (single-use), and returns a JWT so the new staffer is logged straight in. New public page `AcceptInvite.js`.
- RBAC: non-admin 403 on invite endpoints; existing-email → 400; reused/invalid token → 400/404.
- Tested: 10/10 backend pytest + 100% frontend (create→copy link→accept→login with assigned tabs, single-use, RBAC). No issues.
- Note: invites allow multiple pending per email (no dedupe); acceptable.

## Iteration 24 (2026-06) — Unicode PDF fonts (P2)
- Bundled DejaVuSans + DejaVuSans-Bold TTFs in `/app/backend/assets/fonts/` and added `core/pdf_utils.py` (`new_pdf`/`pdf_bytes`, family "DejaVu"). Invoice PDFs (`claims._invoice_pdf`) and blank-template PDFs (`forms._build_pdf`) now render full Unicode — accents & ñ (e.g., "Muñoz", "José") no longer mangled to "?". Removed the latin-1 `_s` fallback.
- Verified: accented text round-trips via pypdf text extraction; invoice + blank-template PDF endpoints return valid PDFs.

## Iteration 25 (2026-06) — Staff Clinical AI Assistant (OpenAI gpt-5.4)
- New **AI Assistant** sidebar tab (tab key `assistant`) — an in-app multi-turn chat that helps staff with documentation, summaries, letters, and CPT/ICD-10 questions. Bilingual (replies in the user's language). Powered by `emergentintegrations` LlmChat → OpenAI **gpt-5.4** via the Emergent LLM key.
- Backend `routers/assistant.py`: per-user conversations in `ai_conversations` (`GET/POST /api/assistant/conversations`, `GET/DELETE /{cid}`, `POST /{cid}/message`). Ownership-isolated (404 across users). Multi-turn context preserved by embedding the last 20 stored messages into the system prompt each call (verified: recalls facts across turns). Auto-titles from first message; message validation (empty/≤8000).
- RBAC: `assistant` added to `ALL_TABS` + default tabs for admin + clinical roles (doctor/nurse/psychologist); receptionist/biller excluded by default (admin can grant).
- Frontend `AIAssistant.js`: conversation sidebar + chat thread + input (Enter to send, Shift+Enter newline), thinking indicator, "assistance only" disclaimer.
- Tested: 11/11 backend pytest + 100% frontend (real LLM multi-turn recall, RBAC hide for biller, conversation CRUD, ownership isolation). No issues.

## Iteration 26 (2026-06) — Admin site control: Suspend access + Role templates
- **Suspend / Activate access**: users get an `active` flag; admin toggles it (`PUT /api/users/{id}/active`). Suspended users are blocked at login (403) AND existing JWT sessions are cut immediately (enforced in `get_current_user`). Safeguards: can't suspend self or any admin (400). UI: Status column (Active/Suspended) + suspend/restore toggle with confirm dialog in the Admin page.
- **Role access templates**: admin edits default tabs per role from the UI (`GET/PUT /api/role-templates/{role}`, stored in `role_templates` collection). Optional "apply to all existing users of this role" bulk-updates their `allowed_tabs`. New users (register + invite) inherit the template via `core/roles.resolve_role_tabs`. `GET /api/meta/tabs` is template-aware. UI: Role Access cards + edit modal.
- **Rename**: "Settings" page → **"Admin"** (label only; route /settings unchanged). Houses Staff (+status/suspend), Role Access, Invitations, Clinic Letterhead.
- Also fixed ui-kit `Badge`/`Card` to forward props (`data-testid`) — improves testability app-wide.
- Tested: 13/13 backend pytest + 100% frontend (suspend blocks login + kills sessions, safeguards, role template save/apply/inherit, RBAC, regression). No issues.

## Iteration 27 (2026-06) — Admin login-access controls
- **Admin password reset** (`PUT /api/users/{id}/password`): sets a new password, invalidates old password + all old sessions, optionally requires change on next login. Self-reset blocked.
- **Force logout** (`POST /api/users/{id}/logout`): instantly invalidates a user's active sessions. Self blocked.
- **Forced first-login password change**: admin-created users (Add User, default ON) and reset accounts get `must_change_password`; the `Protected` gate forces the `ChangePassword` screen until done. `POST /api/auth/change-password` verifies current pw, sets new, clears flag, bumps token_version, returns fresh token.
- **Session invalidation**: per-user `token_version` embedded as `tv` claim; `get_current_user` rejects mismatches (401). Backward compatible with legacy tokens.
- Admin UI: per-user Reset password + Force logout actions; Add User "require password change" checkbox.
- Tested: 17/17 backend pytest + 100% frontend UI e2e (forced-change gate, reset/force-logout session kill, safeguards, RBAC, login regression all 6 roles). No issues.

## Iteration 28 (2026-06) — Staff Enrollment page (admin)
- New dedicated **Enroll Staff** page (`/enroll`, admin-only) replacing the Add-User modal. Sections: Account (name/email/role), **Access** (tab checklist prefilled from the role template — this is where the admin assigns clinic **Dashboard** + other tab access), Login Credentials (auto-generated temp password + Generate button + "require password change on first login"), and Professional Profile (phone, title, license #, Doxy.me room).
- On submit → creates the account and shows a success panel with the login email + temporary password + Copy credentials / Enroll another / Back to Admin.
- Backend: `RegisterInput` extended with `phone/title/license_number/doxy_room` (stored on the user doc). `/auth/register` unchanged otherwise.
- Admin page "Add User" button now navigates to `/enroll`; old modal removed.
- Tested: backend curl (custom tabs + profile fields persisted, must_change) + full UI e2e (fill → submit → credentials panel). No issues.

## Iteration 29 (2026-06) — Delete notes, refactor auth, real accounts
- **Delete progress notes**: `DELETE /api/notes/{id}` (author or admin, audited) + trash button on each note card with confirm.
- **Refactor**: split `routers/auth.py` → kept auth-only endpoints (login, register, change-password, me, signature); moved user management to `routers/users.py` and role/tab meta to `routers/roles.py`. URLs unchanged; all endpoints verified 200.
- **Accounts**: erased the 5 demo staff + old `admin@vpp.com`; created the real admin **ADMIN / usvopp@yahoo.com**. Set `.env` `ADMIN_EMAIL`/`ADMIN_PASSWORD` to match and `SEED_DEMO_USERS=false`. Only the real admin remains. (Production: set the same env vars in the deployment.)
- Verified: new admin logs in (14 tabs); old admin + demo staff → 401; note delete create→delete→404.

## Iteration 30 (2026-06) — Deployment readiness
- Ran deployment agent: **no blockers** (can deploy). Fixed the two flagged N+1 patterns — `appointments` list, `invoices` list, and billing CSV export now project only `id/first_name/last_name` when building the patient-name map.
- Fixed login-page bug: removed the hardcoded demo quick-login cards (demo accounts were erased) — they were 401ing.
- Cleaned leftover test data (52 test invoices, test users/patients). DB now: 1 real admin (usvopp@yahoo.com), 1 patient, 27 real invoices.
- Verified: 15/15 backend regression tests pass (testing agent, iteration_24), real admin logs in, no demo panel.

## Iteration 31 (2026-06) — Backup-admin / lockout prevention
- **Enroll Staff** page now allows selecting the **admin** role, so an admin can create a second/backup administrator (full ALL_TABS access). Backend `/auth/register` already permits `admin`.
- **Lockout-prevention banner**: the Admin page shows an amber reminder ("Protect against lockout") with an "Enroll a second admin" button whenever fewer than 2 admins exist; it disappears once a second admin is added.
- Verified: create-admin via enrollment → logs in as admin with 14 tabs → admin count = 2 (banner clears). Throwaway removed; only real admin remains.

## Iteration 32 (2026-06) — 4-Phase feature drop (appointment types, clickable dashboard, bulk delete, patient deep-dive)
- **Phase 1 — Appointment Types**: appointments now carry `appointment_type` (in_person/telehealth). Toggle in the create/edit modal, type badge on cards, `Join Video` only on telehealth, and a type/provider filter bar. Backend list accepts `patient_id`/`appointment_type`/`provider` query filters; new appts store `created_by`/`created_by_id`.
- **Phase 2 — Clickable Dashboard stats**: each stat card is a Link. Unpaid Invoices → /invoices?status=unpaid (filtered list), Appointments Today → /appointments?date=today, Pending Forms → /forms?status=pending, etc.
- **Phase 3 — Bulk/Single delete, NO confirmation**: checkbox selection + "Delete Selected" across Appointments, Progress Notes (removed old window.confirm), Forms (added single DELETE + bulk), Messages (added single DELETE + bulk), and AI Assistant conversations. New `POST /api/{resource}/bulk-delete` endpoints returning `{deleted, skipped}`. RBAC: admin deletes anything; staff delete only their own (owner = created_by_id for appts, author/created_by name for notes/forms, sender/recipient for messages, user_id for chats). Toast shown when items are skipped. Shared `lib/bulk.js` (useSelection + bulkDelete).
- **Phase 4 — Patient deep-dive**: `View` button on each patient row opens a wide modal (patient-detail) showing that patient's Appointments, Progress Notes, and Forms, with provider + appointment-type filters.
- Verified: testing agent iteration_25 — 10/10 backend PASS, 100% frontend e2e, zero browser confirm dialogs, RBAC skipped-toast path confirmed. No regressions.
- Note (pre-existing, not a regression): some appointment cards show patient "Unknown" (orphan appts referencing deleted patients).

## Iteration 33 (2026-06) — Progress Notes redesign, Privacy mode, Patient SSN, Billing Reports upgrade, ICD memory, Invoice status realignment
- **Invoice status model**: replaced unpaid/paid/void with **In Transit / Paid / Denied** (+legacy kept). Dashboard "Unpaid Invoices" and Billing "Outstanding" now = everything NOT Paid; dashboard card links to `/invoices?status=outstanding`.
- **Invoice tab (prior iter 32 base)**: view/edit/delete, select-all + bulk delete (no confirm), inline status change, auto-increment invoice number after save, single-invoice print (one #invoice-print at a time).
- **Progress Notes redesign**: editable stacked header (Patient Name, DOB, Social Security, Date of Session, ICD-10, CPT, Risk Assessment dropdown [Low/Moderate/High/Imminent], Provider) + full-width **blank writing page** (old boxed textarea removed). Note renders identically on screen / save / PDF. **PDF fix**: textarea is `.no-print` with a `.print-only` body sibling; print CSS strips input borders → clean single-note PDF. NoteInput +cpt_code +risk_level.
- **ICD-10 / CPT memory**: `GET /api/notes/patient-code-history` returns codes previously used for a patient; Notes editor shows clickable suggestion chips on patient select.
- **Patients SSN**: PatientInput +ssn; SSN field in form + detail. Name/DOB/SSN auto-flow into Invoices & Notes on patient select.
- **Privacy mode**: `PrivacyContext` + `<Private>` component + header toggle (next to EN/ES). Masks patient Name/SSN/DOB across Patients, Notes, Invoices, Billing Reports; click-to-reveal, click-again-to-hide. (In-memory; resets on hard reload.)
- **Billing Reports upgrade**: lookup dropdowns By Patient / By Doctor / By Appointment Type; Revenue-by-Patient bar chart; invoice list with select-all + bulk delete + inline status edit + single delete; CSV export retained. `GET /api/reports/billing` accepts patient_id/provider/appointment_type and returns patient_breakdown + invoices[].
- **Provider dropdowns** now include admin (sole clinical user selectable).
- Verified: testing_agent iteration_28 — 100% frontend, backend curl-verified, zero bugs, no-confirm deletes, no regressions.

## Iteration 34 (2026-06/07) — Note redesign polish, robust multi-page print, patient-data accuracy, invoice UX, appointments filters
- **Progress Notes**: compact 2-col editable header; fixed input focus-loss (inlined header JSX instead of nested component); AI Summarize prompt now = experienced psychologist tone, S/O/A/P with 3-4 sentences each; List/Card view toggle.
- **Robust print (multi-page fix)**: `lib/print.js` printSection() clones content into a top-level `#print-holder` (body.printing) so notes/invoices/forms paginate without overlap. Notes editor+view, Invoice VIEW modal, and Forms use it. Invoice EDITOR print stays legacy (live form). Legacy `#invoice-print`/`#form-print` CSS scoped to `body:not(.printing)`.
- **Patient data accuracy**: selecting a patient in Invoices/Notes fetches fresh `GET /patients/{id}` (name/DOB/SSN/gender); `GET /invoices/{id}` and invoice list always reflect the current patient record.
- **Invoices**: compact 2-col Patient/Invoice info layout; saved-invoice rows clickable to open on-screen view; Service Date shows chosen date; new **Completed** column = date marked Paid (`completed_at` set on paid, cleared otherwise).
- **Appointments**: Provider is now a staff-name dropdown; filter bar adds Patient filter.
- **Patients**: SSN field; Name/DOB/SSN flow into invoices/notes; privacy masking applies.
- Verified: testing_agent iterations 29-31, all 100%. Known: ~25 legacy orphan invoices (null number/date) render '—' gracefully — optional cleanup.

## Iteration 44 (2026-06) — Folder "ready" status, FMP packet polish, invoice floor MB-0029
- **Patient Folders "Mark as Ready"**: per-patient folder now has a ready flag (stored on patient doc: `folder_ready`/`folder_ready_at`/`folder_ready_by`). New `PUT /api/folders/{patient_id}/ready`. Detail header toggle button (`folder-ready-toggle`) + green "Ready" badge in header and on each folder card in the list. Included in `GET /folders/patients` and `GET /folders/{id}`.
- **FMP checklist**: removed the "FMP Registration Form (VA Form 10-7959f-1)" line from `FMP_CHECKLIST` and the suggested-order text.
- **Professional FMP packet & checklist** (`_build_packet_pdf`): green header bands (clinic + title + tan subtitle strip), green section titles with underline rules, alternating-row Claim Summary table (wrap-aware via fpdf2 dry_run line measure + page-break guard), and a real checkbox checklist (filled green box + white X when present). Unicode-safe (José/Muñoz OK). Verified 2-page PDF renders.
- **Invoice numbering floor → MB-0029** (`INVOICE_SEQ_BASE=29` in billing.py). Verified `GET /invoices/next-number` returns MB-0029 (no existing MB- invoices in DB).
- Verified: backend curl (invoice next-number, folder ready toggle round-trip via list+detail) + PDF render test. Frontend compiles clean.

## In progress / Pending
- (none active)

## Iteration 35 (2026-06) — Patient Folders (per-patient document management)
- New **Patient Folders** tab (tab key `folders`, `/folders`, icon FolderTree). One folder auto per patient; inside each, create custom **sub-folders** (e.g., Insurance, Lab Results). Items = **uploaded files** (pdf/img/doc/docx/txt/xls/xlsx ≤15MB, Emergent object storage) + **existing patient Forms** attached from the Forms tab (references the form's stored attachment; deleting the folder-item never deletes the shared form file).
- Item actions: **view/download**, **edit** (rename label + description), **move** (within same patient's sub-folders AND to a different patient's folder), single **delete** + **bulk delete** (Select all/Deselect all, NO confirmation — matches app pattern). Sub-folder chips filter items (All Items / Unfiled / each sub-folder); deleting a sub-folder moves its items to Unfiled (never deletes documents). Sub-folder rename/delete inline on chips (delete has a confirm).
- Backend `routers/folders.py` (collections `folder_subfolders`, `folder_items`). RBAC via `FOLDERS_ROLES` (doctor/nurse/psychologist/receptionist/biller + admin override); item ownership = `created_by_id` (admin deletes anything, staff only their own). Audit-logged as resource `folder`. Tab added to ALL_TABS + defaults for admin/doctor/nurse/receptionist. Privacy masking (`<Private>`) on patient names/DOB.
- Tested: testing_agent iteration_32 — 18/18 backend pytest, 100% frontend critical flows, no bugs. DB left clean (1 admin, 1 patient).


## Iteration 36 (2026-06) — Forms email (Resend+Yahoo), form View/Edit/Delete, Move-to-Folder; Folders drag-drop + preview
- **Email sending (Forms)**: `POST /api/forms/{id}/send-email` sends the secure form link (+ attaches the uploaded doc if present) to ANY email — existing patient (auto-filled) or a prospective patient (typed). New `core/email_utils.send_email(..., attachments=)` supports **Resend** (primary, `RESEND_API_KEY`+`SENDER_EMAIL`) and **Yahoo SMTP** (fallback). ⚠️ EMAIL IS INACTIVE until credentials added to backend/.env (both empty) — endpoint returns `{sent:false, configured:false}` and UI shows a friendly "Email is not set up yet" toast. Row button `email-form-<id>` + in-modal `fm-email-btn`.
- **Form View/Edit/Delete**: clicking a form title (`open-form-<id>`) opens a View/Edit modal — edit title/type/status/patient/recipient/external link AND the patient's answered response fields (signatures shown read-only). `PUT /api/forms/{id}` (owner-or-admin; audited). Save + Delete inside modal. Fixed a latent bug: creating a form with an empty recipient email 422'd (EmailStr) — frontend now sends `null`.
- **Move form to Patient Folder**: `POST /api/forms/{id}/to-folder` — uploaded-doc forms attach the file (source `form`); field-based forms generate a PDF of the answers (`_form_pdf`, DejaVu Unicode) stored as folder item (source `upload`). Row button `to-folder-<id>` + in-modal `fm-folder-btn`; pick patient + sub-folder.
- **Patient Folders drag-drop + preview**: drag files onto the open folder to upload (multi-file, into the active sub-folder) with a drop overlay; in-app **preview** modal for image/PDF items (`folder-preview-<id>` → `<img>`/`<iframe>`), non-previewable types show an info toast.
- Cleanup: removed ~255 leftover `TEST_` forms from the preview DB (now 27 forms, 1 patient).
- Tested: testing_agent iteration_33 — 10/10 backend pytest + 6/6 frontend flows, no bugs. DB left clean.

## Backlog / Next
- **Add email credentials to activate sending**: Yahoo needs a 16-char **App Password** (the account password is rejected by Yahoo SMTP), or use Resend (`RESEND_API_KEY`+`SENDER_EMAIL`). Set same in production env.
- P2: Stripe payment gateway for invoices.

## Iteration 43 (2026-06) — Claim Packet naming & claim-number date
- **Claim Number** is now a **date field** (meant to match the invoice service date / progress-note session date), displayed mm/dd/yyyy in the form, list, and detail.
- **Packet Name auto-generates** as **"{Patient Name} {date} FMP Claim"** whenever the patient or claim date changes (remains manually editable). Reordered the modal: Patient → Claim date → auto Name.
- Self-tested via screenshot (name auto-built as "Test Patient 07/19/2026 FMP Claim").

## Iteration 42 (2026-06) — Auto-file saved PDFs into Patient Folders
- Saving a PDF of a **Progress Note**, **Invoice**, or **Claim Packet** now also files a server-generated PDF into that patient's folder, inside a subfolder named **"{FirstName} MM-DD-YYYY"** (created automatically if missing).
- Backend: new `core/folder_filing.py` (`file_pdf_into_folder` + `invoice_pdf`/`note_pdf` generators) and endpoints `POST /api/notes/{id}/to-folder`, `POST /api/invoices/{id}/to-folder`, `POST /api/claims/{id}/to-folder` (claims merges its docs into one PDF). Filed item = `folder_items` source `upload`, content-type PDF, label "Progress Note/Invoice/Claim {date}".
- Frontend: the existing "Save as PDF" buttons (note editor + view, invoice editor + view, claim "Download merged PDF") now also fire the to-folder call (fire-and-forget) and toast "Also saved to patient folder ✓".
- Requires the doc to have a linked patient. Self-tested via curl (all 3 types file correctly) + UI screenshot (toast confirmed). Cleaned up test artifacts.

## Iteration 41 (2026-06) — Security safe-fixes + Notes/Invoice/Telehealth polish
**Security (safe fixes applied; user chose permissive options for the rest):**
- Added `.env`/`backend/.env`/`frontend/.env` to `.gitignore` (SEC-002 fixed).
- Capped form email at 20 recipients per send (SEC-003 partial).
- User decisions on SEC-001: keep broad patient access for all staff incl. biller (B-b), and do NOT enforce per-user tab access server-side for now (C-no). So `allowed_tabs` remains client-side only by explicit choice; documented as accepted risk.

**Features:**
- **Progress Notes dates → mm/dd/yyyy** display everywhere (list, cards, view, print) via `fmtDate()`. (Date inputs remain native.)
- **Notes signature**: removed "Signed by <admin>"; now shows the signature image with **"Provider Signature · mm/dd/yyyy"** (date = session date) at bottom-left, in cards, view modal, and print.
- **Invoice numbering rolled back 1**: `next-number` now = max existing `MB-####` + 1 (ignores unnumbered/junk invoices). Renumbered the lone existing `MB-0026 → MB-0025` so the next invoice is `MB-0026` and continues regularly.
- **Invoice ICD-10-CM**: replaced the "previously used" chips with a **datalist dropdown** (type-or-pick) fed by the patient's prior ICD-10 codes.
- **List/row view added to Telehealth** (toggle appears once a Doxy room is set). Notes & Appointments already had list view.
- Self-tested via screenshots + curl.

## Iteration 40 (2026-06) — Email ACTIVATED via Resend + Invoice view sections + Invoice ICD-10 memory
- **Email is LIVE via Resend** (`RESEND_API_KEY` set, sender `onboarding@resend.dev`). Confirmed a real send through the app (`sent:1`). ⚠️ On the current free/unverified tier, Resend only delivers to the account owner's address (**ptempl29@gmail.com**). To email patients/prospects at any address, verify a domain at resend.com/domains and set `SENDER_EMAIL` to an address on that domain (e.g. forms@clinic.com). Yahoo SMTP abandoned (cloud IP blocked by Yahoo).
- **Invoice view**: clicking a saved invoice now shows full **Patient Information** (name, DOB, SSN, gender, policy #) and **Invoice Information** (invoice #, service date, completed, status, visit reason, ICD-10, provider) sections, all fields shown with "—" fallback.
- **Invoice ICD-10 memory**: new `GET /api/invoices/patient-code-history?patient_id=` (biller/receptionist) returns ICD-10 codes previously used for a patient (from invoices + notes). Invoice editor shows "Previously used:" ICD-10 suggestion chips on patient select / edit / duplicate / create-from-note — mirrors Progress Notes code memory.
- Also removed the Status field from the Invoice Information editor section (still managed via the Saved Invoices list dropdown).
- Self-tested via curl + screenshots.

## Iteration 39 (2026-06) — Shared filters + list view on Appointments & Progress Notes
- **Appointments**: added a card↔list view toggle (list = invoice-style table: Patient, Provider, Type, Date, Time, Status, Actions with checkboxes/select-all/bulk-delete). Replaced the "today" URL badge with a proper **date filter** input (+clear); keeps Type/Provider/Patient filters. Dashboard "today" deep-link still pre-selects today's date.
- **Progress Notes**: added the same filter bar as Appointments — **Provider**, **Patient**, and **Date (session date)** filters (list/cards views already existed with selection).
- Both pages filter client-side via `useMemo`; subtitle counts reflect filtered results.
- Self-tested via screenshots (toggles, filters, list tables render with selection). Compiles clean.

## Iteration 38 (2026-06) — Rename "Admin" → "CEO" (display only)
- The `admin` role is now labeled **"CEO"** everywhere in the UI (sidebar nav/page, page title, staff role badge, account name/role, role dropdowns in Team + Staff Enrollment, lockout copy). Internal role key remains `admin` — all RBAC (`require_roles("admin")`, `user.role==="admin"` bypass, JWT, seeding) is unchanged and unaffected. Added `roleLabel()` helper in `lib/perms.js`.
- Fixed: Team.js `ALL_TABS` was missing `folders` — CEO can now grant/revoke the Patient Folders tab per user/role.
- Renamed the primary admin account's display name from "ADMIN" → "CEO" (data update; email/password unchanged: usvopp@yahoo.com / Football2023?).
- Self-tested via screenshot; frontend compiles clean.

## Iteration 37 (2026-06) — Multi-recipient form email
- Forms email dialog now supports **multiple recipients**: dynamic add/remove email inputs ("Add recipient"), send the same form (with attachment) to a patient AND e.g. their referring doctor at once. `POST /api/forms/{id}/send-email` accepts `recipients: [..]` (backward-compatible with `recipient_email`), de-dupes, drops invalid addresses, 400 on none; returns `{sent, total, configured, failed[]}`. UI toast shows `sent/total` and lists any failures.
- Self-tested: backend dedup/invalid-filter/empty→400 via curl; frontend add/remove recipient inputs verified. Email still INACTIVE pending valid Yahoo App Password.


## Backlog / Next (superseded)

## Earlier backlog
