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
- P1: FMP Claim Automation Phase 2 (validation engine, claim-review mismatch detection, duplicate-prevention AI rules).
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
