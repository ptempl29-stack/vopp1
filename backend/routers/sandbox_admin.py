import os
import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse

from core import sandbox
from core.security import require_roles

router = APIRouter()

BACKUP_DIR = "/root/vopp_backups"
TOKEN_FILE = os.path.join(BACKUP_DIR, ".download_token.json")


@router.get("/sandbox/status")
async def sandbox_status(user: dict = Depends(require_roles("admin"))):
    out = sandbox.status()
    if sandbox.SANDBOX:
        led = sandbox.ledger()
        out["ledger"] = {op: led.count_documents({"op": op})
                         for op in ("put", "blocked_get", "blocked_delete")}
    return out


@router.get("/sandbox/backup-download/{token}")
async def backup_download(token: str):
    """One-time, expiring download of the ENCRYPTED Preview backup. Preview only."""
    if not sandbox.SANDBOX or not os.path.exists(TOKEN_FILE):
        raise HTTPException(status_code=404, detail="Not found")
    with open(TOKEN_FILE) as f:
        meta = json.load(f)
    if not secrets.compare_digest(token, meta["token"]) or meta.get("used") \
            or datetime.now(timezone.utc).timestamp() > meta["expires"]:
        raise HTTPException(status_code=404, detail="Not found")
    meta["used"] = True
    with open(TOKEN_FILE, "w") as f:
        json.dump(meta, f)
    path = os.path.join(BACKUP_DIR, meta["file"])
    return FileResponse(path, media_type="application/octet-stream", filename=meta["file"])
