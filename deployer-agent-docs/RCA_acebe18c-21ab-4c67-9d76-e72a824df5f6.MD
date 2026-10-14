# Read-Only Production Verification — Veterans of Puerto Plata (veteran-care-portal)

**Mode:** Strictly read-only. No deploy, redeploy, rollback, DB write, or Secret change was performed.
**Deployment:** veteran-care-portal (b6eb8821-127e-47d6-8749-44778c422d7e)
**Live URL:** https://veteran-care-portal.emergent.host
**DB read:** veteran-care-portal-test_database
**Check time:** 2026-10-14 ~23:35 UTC

## VERDICT: Version (A) is LIVE — the older GitHub commit ab8213f.
All structural evidence matches A and contradicts B (see sections 2 & 3). Note: the pulled source does not carry the raw git SHA (git metadata is excluded from the deploy pull), so the commit label ab8213f is inferred from the code's structure, which matches A exactly.

---

## (1) Most recent production deploy / in-progress / failed
- **Active (live) run:** acebe18c-21ab-4c67-9d76-e72a824df5f6
  - Type: redeploy | Status: SUCCESS
  - Created: 2026-10-14T22:55:55Z | Completed/Promoted: 2026-10-14T23:00:01Z
  - Image: customers-app@sha256:d042fe2156c890be0cbcaea0b18121abba159e6f57bd0286ce51758d40ddfebc
  - Trigger: agentic | Job: 08e89e4f-25e3-4656-9338-2b7bf30ea09b
- **In progress:** NONE.
- **Recently failed:** NONE. The 5 most recent runs are all status=success (2026-10-13T23:31Z through 2026-10-14T23:00Z).

## (2) File existence in running backend + route responses
File check performed against the active run's pulled source (/app/scratch) — the exact code baked into the live image:
- backend/core/icd10.py        → EXISTS
- backend/core/providers.py     → MISSING
- backend/core/note_versions.py → MISSING (also absent at repo-root core/)
- backend/core/sandbox.py       → MISSING (also absent at repo-root core/)
- backend/core/ssn.py           → MISSING (also absent at repo-root core/)
- backend/routers/sandbox_admin.py → MISSING (also absent at repo-root routers/)
- backend/routers/reports.py       → MISSING (also absent at repo-root routers/)

Route defs found in source: only `@router.get("/icd10/search")` in backend/routers/icd10.py. No sandbox/status or notes-integrity/verify route defined.

Live route probes (https://veteran-care-portal.emergent.host):
- GET /api/icd10/search          → 401 Not authenticated  => EXISTS (auth-gated)
- GET /api/sandbox/status        → 404 Not Found          => DOES NOT EXIST
- GET /api/notes-integrity/verify→ 404 Not Found          => DOES NOT EXIST

=> Matches Version A: has /api/icd10/search + icd10.py; lacks all B-only files and both B-only routes.

## (3) Read-only document counts (veteran-care-portal-test_database)
- users:                 9
- patients:              30
- notes:                 226
- notes w/ signature (signature ^data:image): 197
- note_versions:         2
- invoices:              198
- claim_packets (total): 69
- claim_packets (approved=true): 2
- folder_items:          462
- forms:                 28

## (4) Backend ERROR/Traceback lines in last hour (run acebe18c)
Exactly 1 ERROR line, no tracebacks:
- `ERROR:server:Storage init failed: 429 Client Error: Too Many Requests for url: https://integrations.emergentagent.com/objstore/api/v1/storage/init`
  (object-storage init rate-limited by the Emergent integrations proxy at startup; transient 429, not a code fault.)

---
Note: a `.emergent/markers/.restore-complete` marker is present in the source tree, but the code content itself unambiguously matches Version A (icd10.py + /api/icd10/search present; all B-only files/routes absent). The marker is residual and does not change the verdict.
