# Production Deployment — Environment Hardening

These values are **only for the production/deployed environment**. Do NOT apply them to the
preview environment (the preview relies on demo accounts + wildcard CORS for testing).

## backend/.env (production)
```
# Disable demo staff accounts (doctor@vpp.com, nurse@vpp.com, etc.)
SEED_DEMO_USERS=false

# Lock CORS to your real frontend origin(s), comma-separated. NO wildcard.
CORS_ORIGINS=https://YOUR-PRODUCTION-DOMAIN.com

# Strong, unique admin credentials (rotate from any preview/demo value)
ADMIN_EMAIL=admin@your-clinic-domain.com
ADMIN_PASSWORD=<long-random-strong-password>

# Keep existing secrets (already env-driven): MONGO_URL, DB_NAME, JWT_SECRET, EMERGENT_LLM_KEY
# JWT_SECRET must be a long random string (also used to HMAC Doxy.me patient ids).

# Email (form links + telehealth invites) — required if using those features
YAHOO_EMAIL=...
YAHOO_APP_PASSWORD=...

# PUBLIC_BASE_URL must equal the production frontend URL (used to build patient form links)
PUBLIC_BASE_URL=https://YOUR-PRODUCTION-DOMAIN.com
```

## Telehealth / Doxy.me (HIPAA)
- Doxy.me is URL/room-based; **no API key** required.
- ACTION REQUIRED: sign a **BAA with Doxy.me** before using with real patients.
  - Individual providers: Free/Professional plan includes a BAA.
  - Multi-provider clinic: needs a clinic-level BAA (confirm plan with Doxy.me sales).
  - Text invites require Professional/Clinic/Enterprise (we generate copyable links + email instead).
- Each provider sets their own room slug in the app (Telehealth page → "My Doxy.me Room").
- Patient invite links are built server-side with `?username=&autocheckin=true&pid=<HMAC>` (no PHI in the link/email).

## Other production TODOs
- Ensure MongoDB is encrypted at rest (managed provider setting).
- Confirm HTTPS/TLS in transit (platform default).
- Review audit-log retention (currently 2-year TTL) against your compliance policy.
