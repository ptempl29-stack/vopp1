# RCA — VA Disability Breakdown Letter not auto-attached on "Build from Date"

**Deployment:** veteran-care-portal (b6eb8821-127e-47d6-8749-44778c422d7e)
**Active run:** ae97701e-6c12-4bf9-9a7b-eca3ffebd129 (redeploy, success)
**DB queried (read-only):** veteran-care-portal-test_database
**Symptom:** After the latest deploy, admin used Claim Packets → "Build from Date" (POST /api/claims/from-date). The VA Disability Breakdown Letter did NOT auto-attach to the new packet, though the patient has one on file.

## Root cause (CONFIRMED)
`backend/routers/claims.py` `_auto_attach_credentials` searches **only `db.folder_items`** and matches when the lowercased **`filename`** (or `label` when filename is empty) contains one of: `disability`, `discapacidad`, `disabilidad`, `rating`, `va letter`, `va-letter`. It ignores `category`, `description`, and the entire `db.forms` collection.

For the affected patient (David Turner, patient_id `1e2a8787-312a-43a6-803b-24745ae25b5b`):
- All 11 `folder_items` are progress-note/invoice PDFs (`Prog_*.pdf`, `Patient_Invoice_MB-0158_09-23-2026.pdf`) — **none** contain any keyword.
- The Disability Breakdown Letter exists **only as a `forms` document**: form_type `Disability Breakdown Letter`, title `david`, status `received`, attachment `David Turner dbl.pdf`. The matcher never looks at `forms`, so nothing was attached. Note: even the attachment filename (`...dbl.pdf`) would not match the keyword list.

This is systemic, not a one-off: across the ENTIRE database only **1** `folder_items` row matches the keyword set (a *different* patient, Idriss), **0** `folder_items` carry category `va_disability_letter`, and only **1** `forms` row has form_type `Disability Breakdown Letter` (David's). So the folder-keyword path essentially never fires. Letters attached on older packets came via `source=form` or direct `source=upload` into the claim, not via this matcher.

Backend logs since deploy show `POST /api/claims/from-date` → **200 OK**, no errors/tracebacks — the auto-attach fails **silently** (no match, no exception).

## Findings (verbatim)

### 1. 5 most recent claim_packets
1. id `565931ca-a075-4249-80a6-f1f906d5f19c` | patient_id `1e2a8787-312a-43a6-803b-24745ae25b5b` | claim_number `2026-10-12` | created_at `2026-10-13T22:31:27` | created_by `Clinic Admin` | status `draft` | items: invoice/`Invoice_MB-0195.pdf`, progress_note/`Progress_Note_10-12-2026.pdf`, provider_exequatur/`Saday Cabrera exquator copy 52.pdf`, provider_diploma/`Saday diploma copy 12.pdf` → **NO va_disability_letter** (affected packet, created 7 min after the 22:24 deploy)
2. id `de977f13-5303-4963-8bf0-de526c937e46` | patient_id `0a86f50e-8fa1-421c-aace-3a23982918db` | `2026-10-01` | status complete → has va_disability_letter (`Mark_Roberson_DISABILITY copy.pdf`, source=upload)
3. id `de784f5a-fdb1-4b8c-add0-e34e5adbf0a9` | patient_id `a5b58317-d670-4cf6-86d2-b4de05ad077a` | `2026-10-01` | complete → has va_disability_letter (`Henry Heras Breakdown Letter copy.pdf`, source=form)
4. id `1b7a2aee-4e00-48ec-8309-bebd98258976` | patient_id `263944d5-cf15-4946-b24c-f48628cd7aa1` | `2026-08-18` | complete → has va_disability_letter (`DISABILITYPRINTISSTEMPLE(2) copy 3.pdf`, source=upload)
5. id `d046447a-cda3-4113-ab61-fdb8b2afbc3f` | patient_id `0f0ba22f-3403-40d7-8ea8-d111be77ad94` | `2026-08-19` | complete → has va_disability_letter (`2024-10-9-16-20-52 Disability Breakdown Letter - UDO copy.pdf`, source=form)

Only packet #1 lacks the letter.

### 2. folder_items for patient 1e2a8787 (11 items; all description "Auto-saved PDF", source upload)
- `Prog_09-16-2026.pdf` (label "Prog 09-16-2026") ×4 — subfolder `9a901dc4…` = "David 09-16-2026"
- `Prog_09-29-2026.pdf` ×3 — subfolder `2f3efb91…` = "David 09-29-2026"
- `Prog_09-23-2026.pdf` + `Patient_Invoice_MB-0158_09-23-2026.pdf` — subfolder `cd78f97f…` = "David 09-23-2026"
- `Prog_10-05-2026.pdf` ×2 — subfolder `20aa2e7c…` = "David 10-05-2026"
No category `va_disability_letter`; no keyword match in filename/label/description.

### 3. forms for patient 1e2a8787
- id `2009c9b9-2bdb-48c8-9c9b-8847cdf7dd6e` | form_type `Disability Breakdown Letter` | title `david` | status `received` | attachment EXISTS, filename `David Turner dbl.pdf` | created_at `2026-10-13T19:05:55` ← **the letter, invisible to the matcher**

### 4. Cross-patient counts
- folder_items matching (filename/label/description, case-insensitive) `disab|discapac|desglose|rating|va letter|breakdown|carta|benefit|beneficio|summary`: **1** (example: filename `Idriss 3156 Disability Breakdown Letter - UDO.pdf`, label `Idriss disability breakdown letter`, description ``)
- folder_items with category == `va_disability_letter`: **0**
- forms with form_type == `Disability Breakdown Letter`: **1** (David's)

### 5. Ambiguity (patients with >1 candidate letter)
**0.** The only folder_item candidate (Idriss) and the only form candidate (David) belong to different patients; 0 folder_items carry the category. No patient has more than one candidate.

### 6. Backend logs since latest deploy
`POST /api/claims/from-date` → `200 OK`. No error/traceback/auto-attach/merge-skip lines. Failure is silent (no match, no exception).

## Suggested fix (Code — E1; no redeploy performed, no data changed)
Broaden `_auto_attach_credentials` in `backend/routers/claims.py` to also source the letter from `db.forms` (form_type == "Disability Breakdown Letter" with an `attachment`) for the packet's patient_id, and to consider `folder_items` `label`/`description`/`category` (e.g. category == "va_disability_letter") in addition to `filename`. Consider expanding the keyword set (`breakdown`, `desglose`, `carta`) and de-duping so a letter present as both a form and a folder item is attached once. Add a log line when no letter is found so the silent case is observable.
