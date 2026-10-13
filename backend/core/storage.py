import os
import requests

from core.config import APP_NAME  # noqa: F401 (kept for callers importing app name)
from core import sandbox

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
_storage_key = None


class StorageBlocked(PermissionError):
    pass


def _fail_closed(op: str, path: str):
    if sandbox.FAIL_CLOSED:
        sandbox._log.error(f"FAIL-CLOSED {op} refused (Preview configuration not verified): {path}")
        raise StorageBlocked("Preview storage safeguards not verified — storage access refused")


def init_storage():
    global _storage_key
    if sandbox.FAIL_CLOSED:
        raise StorageBlocked("Preview storage safeguards not verified — storage access refused")
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ["EMERGENT_LLM_KEY"]}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    _fail_closed("PUT", path)
    if sandbox.SANDBOX and not path.startswith(sandbox.PREFIX + "/"):
        path = f"{sandbox.PREFIX}/{path}"
    key = init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120)
    resp.raise_for_status()
    result = resp.json()
    if sandbox.SANDBOX:
        stored = result.get("path") or path
        result["path"] = stored
        sandbox.record_write(stored, data, content_type)
    return result


def get_object(path: str):
    _fail_closed("GET", path)
    if sandbox.SANDBOX:
        rec = sandbox.authorized_path(path)
        if not rec:
            sandbox.record_event("blocked_get", path, "not written by this Preview sandbox")
            raise StorageBlocked("Preview may only open documents it created in the sandbox")
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    if sandbox.SANDBOX and sandbox.sha256(resp.content) != rec.get("sha256"):
        sandbox.record_event("blocked_get", path, "content fingerprint mismatch")
        raise StorageBlocked("Document fingerprint mismatch — access refused")
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


def delete_object(path: str) -> bool:
    if sandbox.SANDBOX or sandbox.FAIL_CLOSED:
        sandbox._log.warning(f"BLOCKED delete (Preview): {path}")
        if sandbox.SANDBOX:
            sandbox.record_event("blocked_delete", path)
        return False
    try:
        key = init_storage()
        resp = requests.delete(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=30)
        return resp.status_code < 400
    except Exception:
        return False
