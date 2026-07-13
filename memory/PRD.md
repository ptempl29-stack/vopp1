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

## Backlog / tech-debt notes
- Split `server.py` (~780 lines) into per-resource routers.
- Billing report aggregates in Python; move to Mongo aggregation pipeline past ~10k invoices.
- `?auth=` query-token on download/export could leak via logs; consider short-lived signed URLs.

## Known Limitations
- AI summarization returns clean 500 until the Emergent LLM Universal Key balance is topped up ($0 currently).
- No payment gateway (deferred by user choice).

## Backlog / Next
- P0: Top up Universal Key to enable AI summaries.
- P1: Payment gateway (Stripe) for invoices; patient detail page with note/appointment history.
- P2: Appointment calendar view; form field builder + patient-facing form fill; audit log; charts on dashboard.
