import os
import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from pymongo import MongoClient

_log = logging.getLogger("preview_sandbox")

EXPECTED_DB = "test_database"
EXPECTED_PREFIX = "vpp-clinic-preview"
PRODUCTION_PREFIX = "vpp-clinic"
PREVIEW_HOST_SUFFIX = ".preview.emergentagent.com"

_designation = os.environ.get("VOPP_ENV", "").strip().lower()
_db_name = os.environ["DB_NAME"]
_mongo_host = (urlparse(os.environ["MONGO_URL"]).hostname or "").lower()
_public_host = (urlparse(os.environ.get("PUBLIC_BASE_URL", "")).hostname or "").lower()
_prefix = os.environ.get("STORAGE_SANDBOX_PREFIX", "").strip().strip("/")

LOCAL_DB = _mongo_host in ("localhost", "127.0.0.1")


def _checks() -> dict:
    return {
        "designation_preview": _designation == "preview",
        "db_name_is_test_database": _db_name == EXPECTED_DB,
        "mongo_is_local": LOCAL_DB,
        "public_url_is_preview": _public_host.endswith(PREVIEW_HOST_SUFFIX),
        "prefix_exact": _prefix == EXPECTED_PREFIX,
        "prefix_not_production": bool(_prefix) and _prefix != PRODUCTION_PREFIX
                                 and not _prefix.startswith(PRODUCTION_PREFIX + "/"),
    }


CHECKS = _checks()
# ON only when every Preview check passes.
SANDBOX = all(CHECKS.values())
# Local DB (Preview machine) but not fully verified -> refuse all storage + outbound comms.
FAIL_CLOSED = LOCAL_DB and not SANDBOX
if _designation == "preview" and not LOCAL_DB:
    _log.critical("VOPP_ENV=preview found on a non-local database: ignored, production behaviour unchanged")

PREFIX = _prefix

_ledger = None


def ledger():
    global _ledger
    if _ledger is None:
        _ledger = MongoClient(os.environ["MONGO_URL"])[_db_name]["sandbox_storage_ledger"]
    return _ledger


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record_write(path: str, data: bytes, content_type: str):
    ledger().insert_one({"path": path, "sha256": sha256(data), "size": len(data),
                         "content_type": content_type, "op": "put",
                         "at": datetime.now(timezone.utc).isoformat()})


def record_event(op: str, path: str, detail: str = ""):
    ledger().insert_one({"path": path, "op": op, "detail": detail,
                         "at": datetime.now(timezone.utc).isoformat()})


def authorized_path(path: str):
    """Ledger record for a path Preview itself wrote; checked BEFORE any request is sent."""
    if not path.startswith(PREFIX + "/"):
        return None
    return ledger().find_one({"path": path, "op": "put"}, sort=[("at", -1)])


def outbound_blocked() -> bool:
    return SANDBOX or FAIL_CLOSED


def status() -> dict:
    return {"sandbox": SANDBOX, "fail_closed": FAIL_CLOSED, "checks": CHECKS,
            "prefix": PREFIX if SANDBOX else None, "outbound_blocked": outbound_blocked()}
