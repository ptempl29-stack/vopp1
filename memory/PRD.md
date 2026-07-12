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
