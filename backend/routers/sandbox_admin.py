import os
import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse, HTMLResponse

from core import sandbox
from core.security import require_roles

router = APIRouter()

BACKUP_DIR = "/root/vopp_backups"
TOKEN_FILE = os.path.join(BACKUP_DIR, ".download_token.json")
MAX_DOWNLOADS = 3


@router.get("/sandbox/status")
async def sandbox_status(user: dict = Depends(require_roles("admin"))):
    out = sandbox.status()
    if sandbox.SANDBOX:
        led = sandbox.ledger()
        out["ledger"] = {op: led.count_documents({"op": op})
                         for op in ("put", "blocked_get", "blocked_delete")}
    return out


def _valid_meta(token: str):
    if not sandbox.SANDBOX or not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE) as f:
        meta = json.load(f)
    if not secrets.compare_digest(token, meta["token"]) or meta.get("downloads", 0) >= MAX_DOWNLOADS \
            or datetime.now(timezone.utc).timestamp() > meta["expires"]:
        return None
    return meta


@router.get("/sandbox/backup-download/{token}")
async def backup_download_page(token: str):
    """Confirmation page only (link previews/prefetch can't consume the one-time download)."""
    meta = _valid_meta(token)
    if not meta:
        raise HTTPException(status_code=404, detail="Not found")
    html = (f"<html><body style='font-family:sans-serif;padding:40px'>"
            f"<h3>Encrypted Preview backup</h3><p>{meta['file']}</p>"
            f"<p>This link allows up to 3 downloads and expires in 2 hours. Press the button to download.</p>"
            f"<form method='post'><button style='font-size:18px;padding:10px 20px'>Download</button></form>"
            f"</body></html>")
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@router.post("/sandbox/backup-download/{token}")
async def backup_download(token: str):
    """One-time, expiring download of the ENCRYPTED Preview backup. Preview only."""
    meta = _valid_meta(token)
    if not meta:
        raise HTTPException(status_code=404, detail="Not found")
    meta["downloads"] = meta.get("downloads", 0) + 1
    with open(TOKEN_FILE, "w") as f:
        json.dump(meta, f)
    path = os.path.join(BACKUP_DIR, meta["file"])
    return FileResponse(path, media_type="application/octet-stream", filename=meta["file"])
