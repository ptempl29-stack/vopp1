import os
import hmac
import json
import hashlib
import uuid

from core.db import db, now_iso

# Fields whose change is a substantive clinical edit (decision 11 / C).
SUBSTANTIVE_FIELDS = ("content", "subjective", "objective", "assessment", "plan", "icd10", "cpt_code",
                      "visit_date", "risk_level", "reason_for_visit", "attending_provider")
SNAPSHOT_FIELDS = SUBSTANTIVE_FIELDS + (
    "patient_id", "title", "note_type", "summary", "signature", "signed_by", "signed_at",
    "referring_provider", "exequatur_number", "completed", "completed_at", "completed_by",
    "billing_review_status", "billing_reviewed_by", "billing_reviewed_at", "billing_review_note")


def _key() -> bytes:
    return os.environ["NOTE_INTEGRITY_KEY"].encode()


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(snapshot: dict) -> str:
    return hashlib.sha256(_canon(snapshot).encode()).hexdigest()


def _seal(prev_seal: str, chash: str, note_id: str, version: int, archived_at: str) -> str:
    msg = f"{prev_seal}|{chash}|{note_id}|{version}|{archived_at}".encode()
    return hmac.new(_key(), msg, hashlib.sha256).hexdigest()


def is_substantive(existing: dict, doc: dict) -> bool:
    if any((existing.get(f) or "") != (doc.get(f) or "") for f in SUBSTANTIVE_FIELDS):
        return True
    title_changed = (existing.get("title") or "") != (doc.get("title") or "")
    return title_changed and not doc.get("title_nonclinical_confirmed")


def needs_protection(note: dict) -> bool:
    return bool(note.get("signature") or note.get("completed")
                or note.get("billing_review_status") == "approved")


async def archive_version(note: dict, reason: str, user: dict) -> dict:
    """Append-only: the only writer of note_versions (insert_one, never update/delete)."""
    last = await db.note_versions.find_one({"note_id": note["id"]}, {"_id": 0}, sort=[("version", -1)])
    version = (last["version"] + 1) if last else 1
    snapshot = {f: note.get(f) for f in SNAPSHOT_FIELDS}
    archived_at = now_iso()
    chash = content_hash(snapshot)
    rec = {"id": str(uuid.uuid4()), "note_id": note["id"], "version": version, "snapshot": snapshot,
           "content_hash": chash, "prev_seal": last["seal"] if last else "",
           "seal": _seal(last["seal"] if last else "", chash, note["id"], version, archived_at),
           "reason": reason, "archived_at": archived_at, "archived_by": user["name"],
           "archived_by_id": user["id"]}
    await db.note_versions.insert_one(dict(rec))
    return rec


async def verify_chain(note_id: str, expected_count=None) -> dict:
    versions = await db.note_versions.find({"note_id": note_id}, {"_id": 0}).sort("version", 1).to_list(1000)
    problems, prev = [], ""
    for i, v in enumerate(versions, start=1):
        if v["version"] != i:
            problems.append(f"version gap/order at {i}")
        if content_hash(v["snapshot"]) != v["content_hash"]:
            problems.append(f"v{v['version']} content altered")
        if v.get("prev_seal") != prev or not hmac.compare_digest(
                _seal(prev, v["content_hash"], note_id, v["version"], v["archived_at"]), v["seal"]):
            problems.append(f"v{v['version']} seal invalid")
        prev = v["seal"]
    if expected_count is not None and expected_count != len(versions):
        problems.append(f"expected {expected_count} versions, found {len(versions)}")
    return {"ok": not problems, "count": len(versions), "problems": problems}
