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

## Security Audit (2026-06) — OPEN ITEMS (not yet fixed)
Audit verdict: FAIL/DO-NOT-LAUNCH for production PHI. Key findings to address before real patient data:
- SEC-001 CRITICAL: hard-coded/self-seeding demo staff + default admin creds → remove seeding, strong unique admin secret.
- SEC-002 HIGH: all roles can read all patient records/clinical notes → restrict PHI reads by role/need-to-know.
- SEC-003 MEDIUM: patient search $regex ReDoS → escape/anchor input + timeouts.
- SEC-004 MEDIUM: public Jitsi rooms, predictable ad-hoc names → BAA-compliant video / lobby + secret.
- P3 hardening: CORS '*'+credentials, localStorage token (XSS), 7-day JWT no revocation, no login rate limit, arbitrary status query params, mark_read no ownership check, no data-at-rest encryption (HIPAA).

## Known Limitations
- AI summarization returns clean 500 until the Emergent LLM Universal Key balance is topped up ($0 currently).
- No payment gateway (deferred by user choice).

## Backlog / Next
- P0: Top up Universal Key to enable AI summaries.
- P1: Payment gateway (Stripe) for invoices; patient detail page with note/appointment history.
- P2: Appointment calendar view; form field builder + patient-facing form fill; audit log; charts on dashboard.
