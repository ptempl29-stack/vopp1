# RCA — Veterans of Puerto Plata (veteran-care-portal)

**Job:** 0573a61e-3f1f-4aed-bce8-88b893c56ab2
**Deployment:** b6eb8821-127e-47d6-8749-44778c422d7e
**Active run:** acebe18c-21ab-4c67-9d76-e72a824df5f6 (redeploy, status=success)
**Image:** sha256:d042fe21…ddfebc (unchanged — no code/data touched)
**Frontend type:** cloudflare | **Tier:** tier_3 | **Cluster:** deployment-cluster-05

## Summary
At the time of investigation the production app is **UP and serving on both the
default URL and the custom domain**. No platform-side outage, crash, OOM, pending,
paused, or undeployed state was found. The reported "NOT ACCESSIBLE" could not be
reproduced from the platform side. No restart was performed because it was not
needed (pods are healthy with 0 restarts and are already handling live traffic).

## (1) Live URL / domain / pod status — EVIDENCE
- `GET https://veteran-care-portal.emergent.host/` → **200**, real SPA shell
  (loads /static/js/main.9fd93201.js — the app bundle, not an nginx default page).
- `GET /api/` → 404 `{"detail":"Not Found"}` and `GET /api/health` → 404 — these
  are "no route at that path," NOT server-down. The backend answers.
- Backend is serving REAL user traffic via Cloudflare: logs show Cloudflare edge
  IPs (172.71.x / 172.69.x) hitting `/api/messages/unread-count` and
  `/api/icd10/describe?code=F06.32` → **200 OK**.
- Pods: 2/2 **Running, ready=true, restart_count=0**. kill_findings empty. No
  CrashLoopBackOff / OOMKilled / Pending / eviction.
- Domains: `veteransofpuertoplata.com` and `www.veteransofpuertoplata.com` both
  verified=true, ssl_status=**active** (Cloudflare), DNS live-check **linked=true**
  for both. No DNS/SSL/CDN/ingress fault.

## (2) Root cause of inaccessibility + recovery
No platform-side cause of inaccessibility exists right now — the app is reachable
and serving. The report does not match current state. The most plausible
explanations are client-side/transient (stale browser bundle, local
network/DNS cache) or the brief startup window before storage init retried
(see #3). **No restart was done** (not required; also the only re-fire path would
re-pull the workspace which holds the forbidden older commit ab8213f — avoided).

## (3) Storage 429
- At boot the app logged: `ERROR:server:Storage init failed: 429 Client Error:
  Too Many Requests for url: https://integrations.emergentagent.com/objstore/api/v1/storage/init`
- **BUT a later log line shows `INFO:server:Object storage initialized`** — the
  app retried and storage init **succeeded**. The 429 is transient (edge
  rate-limit on first attempt), already self-recovered. No persistent 429.
  File upload/download depends on this and is now operational.

## (4) DB counts (read-only) — db: veteran-care-portal-test_database
| Collection | Prior | Now | Match |
|---|---|---|---|
| users | 9 | 9 | ✓ |
| patients | 30 | 30 | ✓ |
| notes | 226 | 226 | ✓ |
| notes signed (signed_at≠null) | 197 | 197 | ✓ |
| note_versions | 2 | 2 | ✓ |
| invoices | 198 | 198 | ✓ |
| claim_packets | 69 | 69 | ✓ |
| claim_packets approved (approved_at≠null) | 2 | 2 | ✓ |
| folder_items | 462 | 462 | ✓ |
| forms | 28 | 28 | ✓ |

All collections present (22 total). **Data fully intact — zero drift.**

## (5) Feature safety
- Login — SAFE (users=9 intact, backend serving auth/API traffic).
- Patients — SAFE (30 records).
- Notes — SAFE (226 / 197 signed).
- Invoices — SAFE (198).
- Claim packets — SAFE (69, 2 approved).
- File upload/download — SAFE (object storage initialized after the 429 retry).

## Actions taken
Read-only diagnosis only. No redeploy, no restart, no DB or Secrets change.
