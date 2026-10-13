# Pre-Deploy Read-Only Verification — veteran-care-portal ("Veterans of Puerto Plata")

Mode: READ-ONLY. No redeploy/restart/secret change/data write performed. No secret values, patient data, note contents, or signatures printed.

## 1. Active live run / health
- Active run id: `ad6b991f-42ed-40a6-bca1-101b9fca22a7` (type=secret_reuse, trigger=secret_change)
- Created: 2026-10-13T19:55:54Z — Completed/deploy time: **2026-10-13T19:57:26Z** — status: success
- Frontend type: cloudflare (static served from R2 worker; `/api` proxied to the k8s backend)
- Health:
  - `GET /health` → **200** (served by the Cloudflare/SPA layer — returns the app HTML, not the backend health JSON)
  - `GET /api/` → **404** `{"detail":"Not Found"}` — expected (no root API route); proves the worker reaches the backend and FastAPI is routing
  - Backend logs at latest start: `INFO: Application startup complete.` (2 worker procs) — backend is UP and serving

## 2. Running live pod environment (active run = currently serving)
Note: list_secrets reads the ACTIVE run's secret rows, which ARE exactly the running pod's env. The active run was itself triggered by the secret change, so pod env reflects the latest Secrets edit.
- **VOPP_ENV = `production`** (confirmed: matches_expected=true vs "production"; sandbox check designation_preview=false)
- NOTE_INTEGRITY_KEY present: **YES** (is_empty=false)
  - Identical to repo `backend/.env` (the Preview key)? **NO** (matches_expected=false vs repo value). → The new production key is in effect; the preview key is NOT live.
  - Length: **cannot be determined** — read-only secret tooling never returns the value or its length. (For reference only: the repo/preview key is 64 hex chars; the prod value differs.)
- STORAGE_SANDBOX_PREFIX present? **YES** (is_empty=false)
- DB_NAME == 'test_database'? **NO** (matches_expected=false). Resolved DB name is `veteran-care-portal-test_database` (prefixed Atlas DB); sandbox check db_name_is_test_database=false
- MONGO host localhost? **NO** (sandbox check mongo_is_local=false)

## 3. Deploy/restart after most recent Secrets edit — saved Secrets vs running pod
- A deploy DID occur after the Secrets edit: the latest run `ad6b991f` is type=secret_reuse/trigger=secret_change (19:55→19:57Z), superseding an earlier 19:38Z secret_change run.
- Saved Secrets match running pod:
  - VOPP_ENV: **YES** (in sync; pod = production)
  - NOTE_INTEGRITY_KEY: **YES** (in sync; the saved new-prod key is what the pod runs — confirmed not the preview key)

## 4. Backend logs since latest start (startup lines)
- Present (one per worker, ×2):
  `WARNING:server:Preview sandbox status: {'sandbox': False, 'fail_closed': False, 'checks': {'designation_preview': False, 'db_name_is_test_database': False, 'mongo_is_local': False, 'public_url_is_preview': False, 'prefix_exact': True, 'prefix_not_production': True}, 'prefix': None, 'outbound_blocked': False}`
- No `CRITICAL` line. No `VOPP_ENV=preview found` line. (Code logs CRITICAL only if VOPP_ENV=preview on a non-local DB — did not occur.)
- Interpretation: sandbox=False, fail_closed=False, outbound_blocked=False → running in full production behavior; no sandbox gating.

## 5. Collection counts
- patients: **29**
- notes: **224**
- notes with signature: **192** (field `signature`, $nin [null, ""])
- invoices: **198**
- claim_packets: **69**
- folder_items: **456**
- forms: **28**
- note_versions: **does NOT exist** (collection absent in DB `veteran-care-portal-test_database`; referenced in code but no versions archived yet)

## 6. "Test VOPP_ENV=preview" — separate test/staging deployment?
- No separate test/staging DEPLOYMENT is visible for this app — tooling shows a single deployment (`veteran-care-portal`, b6eb8821…). The Secrets-tab "Test" scope value does not create a separate production environment.
- The only "preview" is the Emergent Preview sandbox (the coding-agent pod), which per repo `backend/.env` is configured with VOPP_ENV=preview, DB_NAME=`test_database`, a local Mongo, and STORAGE_SANDBOX_PREFIX=`vpp-clinic-preview`. Classification: Preview sandbox uses a LOCAL MongoDB / `test_database`; this production deployment uses Atlas DB `veteran-care-portal-test_database`. The sandbox code path engages only when all preview checks pass (local DB + test_database + preview URL + preview designation + prefix), which is NOT the case in production.

## Verdict
All pre-deploy checks pass. Production is running as production: VOPP_ENV=production, the new NOTE_INTEGRITY_KEY (not the preview key) is live, DB is the Atlas prod DB (not test_database/local), no sandbox/fail-closed/outbound-block engaged, no CRITICAL log. Saved Secrets are in sync with the running pod (a secret_change deploy occurred after the edit). Only limitation: the running NOTE_INTEGRITY_KEY length cannot be read (value never exposed), but identity-vs-preview was confirmed different.
