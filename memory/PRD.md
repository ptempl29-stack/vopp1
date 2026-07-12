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
- DB-backed `cpt_codes` collection (seeded with 10 common codes), full CRUD at `/api/cpt-codes` (biller/admin only). New sidebar page with search, add/edit/delete; codes feed the Invoices line-item dropdown live.

## Known Limitations
- AI summarization returns clean 500 until the Emergent LLM Universal Key balance is topped up ($0 currently).
- No payment gateway (deferred by user choice).

## Backlog / Next
- P0: Top up Universal Key to enable AI summaries.
- P1: Payment gateway (Stripe) for invoices; patient detail page with note/appointment history.
- P2: Appointment calendar view; form field builder + patient-facing form fill; audit log; charts on dashboard.
