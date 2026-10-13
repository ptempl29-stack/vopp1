import base64
import imaplib
import smtplib
import ssl
import time
import uuid
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from core.db import db, now_iso, logger
from core.security import require_roles
from core.mailbox_crypto import encrypt_text, decrypt_text
from core.storage import get_object

router = APIRouter()

SETTINGS_KEY = "mailbox"


class MailboxSettingsIn(BaseModel):
    imap_host: str
    imap_port: int = 993
    imap_ssl: bool = True
    smtp_host: str
    smtp_port: int = 465
    smtp_starttls: bool = False
    email_address: str
    password: Optional[str] = None
    inbox_folder: str = "INBOX"
    sent_folder: str = "Sent"
    trash_folder: str = "Trash"


class InlineAttachment(BaseModel):
    filename: str
    content_type: Optional[str] = None
    data_b64: str


class ComposeIn(BaseModel):
    to: List[str]
    cc: List[str] = []
    subject: str = ""
    body_text: str = ""
    attachment_item_ids: List[str] = []
    inline_attachments: List[InlineAttachment] = []


async def _load_cfg() -> dict:
    doc = await db.mail_settings.find_one({"key": SETTINGS_KEY}, {"_id": 0})
    if not doc or not doc.get("password"):
        raise HTTPException(status_code=400, detail="Mailbox is not configured. Open Settings and connect your mailbox.")
    return doc


# ---------------- IMAP / SMTP (blocking, run in threadpool) ----------------

def _imap(cfg: dict, pwd: str):
    if cfg.get("imap_ssl", True):
        m = imaplib.IMAP4_SSL(cfg["imap_host"], int(cfg.get("imap_port", 993)), ssl_context=ssl.create_default_context())
    else:
        m = imaplib.IMAP4(cfg["imap_host"], int(cfg.get("imap_port", 993)))
        m.starttls(ssl_context=ssl.create_default_context())
    m.login(cfg["email_address"], pwd)
    return m


def _smtp(cfg: dict, pwd: str):
    if cfg.get("smtp_starttls"):
        s = smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_port", 587)), timeout=30)
        s.ehlo(); s.starttls(context=ssl.create_default_context()); s.ehlo()
    else:
        s = smtplib.SMTP_SSL(cfg["smtp_host"], int(cfg.get("smtp_port", 465)), context=ssl.create_default_context(), timeout=30)
    s.login(cfg["email_address"], pwd)
    return s


def _test_conn(cfg: dict, pwd: str):
    m = _imap(cfg, pwd)
    try:
        m.select(cfg.get("inbox_folder", "INBOX"))
    finally:
        try: m.logout()
        except Exception: pass
    s = _smtp(cfg, pwd)
    try: s.noop()
    finally:
        try: s.quit()
        except Exception: pass
    return True


def _list_folders(cfg: dict, pwd: str):
    m = _imap(cfg, pwd)
    try:
        typ, data = m.list()
        out = []
        for line in data or []:
            try:
                s = line.decode(errors="ignore")
                name = s.split(' "')[-1].strip().strip('"') if '"' in s else s.split()[-1]
                if name:
                    out.append(name)
            except Exception:
                continue
        return out
    finally:
        try: m.logout()
        except Exception: pass


def _decode_hdr(val):
    from email.header import decode_header, make_header
    if not val:
        return ""
    try:
        return str(make_header(decode_header(val)))
    except Exception:
        return str(val)


def _list_messages(cfg: dict, pwd: str, folder: str, page: int, limit: int):
    m = _imap(cfg, pwd)
    try:
        m.select(folder)
        typ, data = m.uid("SEARCH", None, "ALL")
        uids = data[0].split()[::-1] if data and data[0] else []
        total = len(uids)
        page_uids = uids[(page - 1) * limit: page * limit]
        items = []
        for uid in page_uids:
            typ, md = m.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE)] FLAGS)")
            raw = b""
            flags = b""
            for part in md:
                if isinstance(part, tuple):
                    raw = part[1]
                    flags += part[0] or b""
                else:
                    flags += part or b""
            msg = BytesParser(policy=policy.default).parsebytes(raw)
            items.append({
                "uid": uid.decode(),
                "subject": _decode_hdr(msg.get("Subject", "")),
                "from_": _decode_hdr(msg.get("From", "")),
                "to": _decode_hdr(msg.get("To", "")),
                "date": str(msg.get("Date", "")),
                "seen": b"\\Seen" in flags,
            })
        return {"items": items, "total": total, "page": page, "limit": limit}
    finally:
        try: m.logout()
        except Exception: pass


def _get_message(cfg: dict, pwd: str, folder: str, uid: str):
    m = _imap(cfg, pwd)
    try:
        m.select(folder)
        typ, md = m.uid("FETCH", uid.encode(), "(RFC822)")
        raw = None
        for part in md:
            if isinstance(part, tuple):
                raw = part[1]
        if raw is None:
            raise HTTPException(status_code=404, detail="Message not found")
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        body_text, body_html = None, None
        if msg.is_multipart():
            tp = msg.get_body(preferencelist=("plain",))
            hp = msg.get_body(preferencelist=("html",))
            if tp: body_text = tp.get_content()
            if hp: body_html = hp.get_content()
        else:
            body_text = msg.get_content()
        atts = []
        for part in msg.iter_attachments():
            payload = part.get_payload(decode=True) or b""
            atts.append({
                "filename": part.get_filename() or "attachment",
                "content_type": part.get_content_type(),
                "size": len(payload),
                "data_b64": base64.b64encode(payload).decode(),
            })
        m.uid("STORE", uid.encode(), "+FLAGS.SILENT", r"(\Seen)")
        return {
            "uid": uid,
            "subject": _decode_hdr(msg.get("Subject", "")),
            "from_": _decode_hdr(msg.get("From", "")),
            "to": _decode_hdr(msg.get("To", "")),
            "cc": _decode_hdr(msg.get("Cc", "")),
            "date": str(msg.get("Date", "")),
            "body_text": body_text,
            "body_html": body_html,
            "attachments": atts,
        }
    finally:
        try: m.logout()
        except Exception: pass


def _delete_message(cfg: dict, pwd: str, folder: str, uid: str):
    from core import sandbox
    if sandbox.outbound_blocked():
        raise RuntimeError("Clinic mailbox changes are blocked in Preview")
    m = _imap(cfg, pwd)
    try:
        m.select(folder)
        trash = cfg.get("trash_folder")
        if trash and trash != folder:
            try:
                m.uid("COPY", uid.encode(), trash)
            except Exception as e:
                logger.error(f"mailbox trash copy failed: {e}")
        m.uid("STORE", uid.encode(), "+FLAGS.SILENT", r"(\Deleted)")
        m.expunge()
        return True
    finally:
        try: m.logout()
        except Exception: pass


def _unread_count(cfg: dict, pwd: str, folder: str):
    m = _imap(cfg, pwd)
    try:
        m.select(folder, readonly=True)
        typ, data = m.uid("SEARCH", None, "UNSEEN")
        uids = data[0].split() if data and data[0] else []
        return len(uids)
    finally:
        try: m.logout()
        except Exception: pass


def _send_message(cfg: dict, pwd: str, to, cc, subject, body_text, attachments=None):
    from core import sandbox
    if sandbox.outbound_blocked():
        raise RuntimeError("Sending from the clinic mailbox is blocked in Preview")
    msg = EmailMessage()
    msg["From"] = cfg["email_address"]
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg.set_content(body_text or "")
    for att in (attachments or []):
        ct = att.get("content_type") or "application/octet-stream"
        maintype, _, subtype = ct.partition("/")
        msg.add_attachment(att["data"], maintype=maintype or "application",
                           subtype=subtype or "octet-stream", filename=att["filename"])
    s = _smtp(cfg, pwd)
    try:
        s.send_message(msg)
    finally:
        try: s.quit()
        except Exception: pass
    # best-effort append to Sent folder
    try:
        m = _imap(cfg, pwd)
        try:
            m.append(cfg.get("sent_folder", "Sent"), r"(\Seen)",
                     imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        finally:
            m.logout()
    except Exception as e:
        logger.error(f"mailbox append to Sent failed: {e}")
    return True


def _wrap(fn, *args):
    try:
        return fn(*args)
    except HTTPException:
        raise
    except (imaplib.IMAP4.error, smtplib.SMTPException) as e:
        raise HTTPException(status_code=400, detail=f"Mail server error: {e}")
    except RuntimeError as e:
        if "blocked in Preview" in str(e):
            raise HTTPException(status_code=403, detail=str(e))
        raise
    except Exception as e:
        logger.error(f"mailbox op failed: {e}")
        raise HTTPException(status_code=502, detail=f"Mailbox connection failed: {e}")


# ---------------- Routes ----------------

@router.get("/mailbox/settings")
async def get_settings(user: dict = Depends(require_roles("admin"))):
    doc = await db.mail_settings.find_one({"key": SETTINGS_KEY}, {"_id": 0, "password": 0})
    if not doc:
        return {"configured": False}
    doc["configured"] = True
    return doc


@router.put("/mailbox/settings")
async def save_settings(data: MailboxSettingsIn, user: dict = Depends(require_roles("admin"))):
    existing = await db.mail_settings.find_one({"key": SETTINGS_KEY}, {"_id": 0})
    doc = data.model_dump()
    if data.password:
        doc["password"] = encrypt_text(data.password)
    elif existing and existing.get("password"):
        doc["password"] = existing["password"]
    else:
        raise HTTPException(status_code=400, detail="Password / app password is required")
    doc["key"] = SETTINGS_KEY
    doc["updated_at"] = now_iso()
    await db.mail_settings.update_one({"key": SETTINGS_KEY}, {"$set": doc}, upsert=True)
    return {"ok": True}


@router.post("/mailbox/test")
async def test_connection(user: dict = Depends(require_roles("admin"))):
    cfg = await _load_cfg()
    pwd = decrypt_text(cfg["password"])
    await run_in_threadpool(_wrap, _test_conn, cfg, pwd)
    return {"ok": True}


@router.get("/mailbox/folders")
async def folders(user: dict = Depends(require_roles("admin"))):
    cfg = await _load_cfg()
    pwd = decrypt_text(cfg["password"])
    names = await run_in_threadpool(_wrap, _list_folders, cfg, pwd)
    return {"folders": names}


@router.get("/mailbox/messages")
async def list_messages(folder: str = "INBOX", page: int = 1, limit: int = 25,
                        user: dict = Depends(require_roles("admin"))):
    cfg = await _load_cfg()
    pwd = decrypt_text(cfg["password"])
    return await run_in_threadpool(_wrap, _list_messages, cfg, pwd, folder, page, limit)


@router.get("/mailbox/messages/{uid}")
async def get_msg(uid: str, folder: str = "INBOX", user: dict = Depends(require_roles("admin"))):
    cfg = await _load_cfg()
    pwd = decrypt_text(cfg["password"])
    return await run_in_threadpool(_wrap, _get_message, cfg, pwd, folder, uid)


@router.delete("/mailbox/messages/{uid}")
async def delete_msg(uid: str, folder: str = "INBOX", user: dict = Depends(require_roles("admin"))):
    cfg = await _load_cfg()
    pwd = decrypt_text(cfg["password"])
    await run_in_threadpool(_wrap, _delete_message, cfg, pwd, folder, uid)
    return {"ok": True}


class DraftIn(BaseModel):
    id: Optional[str] = None
    to: str = ""
    cc: str = ""
    subject: str = ""
    body_text: str = ""
    attachments: List[dict] = []


@router.get("/mailbox/drafts")
async def list_drafts(user: dict = Depends(require_roles("admin"))):
    docs = await db.mail_drafts.find({"owner_id": user["id"]}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    return docs


@router.post("/mailbox/drafts")
async def save_draft(data: DraftIn, user: dict = Depends(require_roles("admin"))):
    inline_bytes = sum(len(a.get("data_b64", "")) for a in (data.attachments or []))
    if inline_bytes > 12_000_000:
        raise HTTPException(status_code=400, detail="Draft attachments are too large to save — remove large files first.")
    did = data.id or str(uuid.uuid4())
    doc = {"id": did, "owner_id": user["id"], "owner_name": user.get("name"),
           "to": data.to, "cc": data.cc, "subject": data.subject, "body_text": data.body_text,
           "attachments": data.attachments or [], "updated_at": now_iso()}
    await db.mail_drafts.update_one({"id": did, "owner_id": user["id"]}, {"$set": doc}, upsert=True)
    return {"ok": True, "id": did}


@router.delete("/mailbox/drafts/{did}")
async def delete_draft(did: str, user: dict = Depends(require_roles("admin"))):
    await db.mail_drafts.delete_one({"id": did, "owner_id": user["id"]})
    return {"ok": True}


@router.get("/mailbox/unread")
async def unread_count(user: dict = Depends(require_roles("admin"))):
    doc = await db.mail_settings.find_one({"key": SETTINGS_KEY}, {"_id": 0})
    if not doc or not doc.get("password"):
        return {"unread": 0, "configured": False}
    pwd = decrypt_text(doc["password"])
    try:
        n = await run_in_threadpool(_unread_count, doc, pwd, doc.get("inbox_folder", "INBOX"))
    except Exception as e:
        logger.error(f"mailbox unread failed: {e}")
        return {"unread": 0, "configured": True, "error": True}
    return {"unread": n, "configured": True}


@router.get("/mailbox/attachable/{patient_id}")
async def attachable_folder_items(patient_id: str, user: dict = Depends(require_roles("admin"))):
    items = await db.folder_items.find(
        {"patient_id": patient_id}, {"_id": 0, "id": 1, "label": 1, "filename": 1, "size": 1, "content_type": 1}
    ).sort("created_at", -1).to_list(1000)
    return items


@router.post("/mailbox/send")
async def send_msg(data: ComposeIn, user: dict = Depends(require_roles("admin"))):
    if not data.to:
        raise HTTPException(status_code=400, detail="At least one recipient is required")
    cfg = await _load_cfg()
    pwd = decrypt_text(cfg["password"])
    attachments = []
    for item_id in (data.attachment_item_ids or []):
        it = await db.folder_items.find_one({"id": item_id}, {"_id": 0})
        if not it or not it.get("storage_path"):
            continue
        try:
            content, ct = get_object(it["storage_path"])
        except Exception as e:
            logger.error(f"mailbox attachment fetch failed ({item_id}): {e}")
            raise HTTPException(status_code=502, detail="Could not load an attachment from storage")
        attachments.append({"filename": it.get("filename") or "document",
                            "content_type": it.get("content_type") or ct, "data": content})
    for ia in (data.inline_attachments or []):
        try:
            raw = base64.b64decode(ia.data_b64)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid uploaded file: {ia.filename}")
        attachments.append({"filename": ia.filename or "attachment",
                            "content_type": ia.content_type or "application/octet-stream", "data": raw})
    total = sum(len(a["data"]) for a in attachments)
    if total > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Attachments exceed 20MB total")
    await run_in_threadpool(_wrap, _send_message, cfg, pwd, data.to, data.cc, data.subject, data.body_text, attachments)
    return {"ok": True}
