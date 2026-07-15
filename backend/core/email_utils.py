import os
import re
import smtplib
from email.message import EmailMessage

from core.db import logger

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def resend_configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY") and os.environ.get("SENDER_EMAIL"))


def yahoo_configured() -> bool:
    return bool(os.environ.get("YAHOO_EMAIL") and os.environ.get("YAHOO_APP_PASSWORD"))


def email_configured() -> bool:
    return resend_configured() or yahoo_configured()


def _valid(addr: str) -> bool:
    return bool(_EMAIL_RE.match(addr or ""))


def _send_resend(to_email: str, subject: str, body: str, attachments) -> bool:
    import resend
    resend.api_key = os.environ["RESEND_API_KEY"]
    params = {"from": os.environ["SENDER_EMAIL"], "to": [to_email],
              "subject": subject, "text": body}
    if attachments:
        params["attachments"] = [
            {"filename": a["filename"], "content": list(a["content"])} for a in attachments]
    resend.Emails.send(params)
    return True


def _send_yahoo(to_email: str, subject: str, body: str, attachments) -> bool:
    msg = EmailMessage()
    msg["From"] = os.environ["YAHOO_EMAIL"]
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    for a in (attachments or []):
        ct = a.get("content_type", "application/octet-stream")
        maintype, _, subtype = ct.partition("/")
        msg.add_attachment(a["content"], maintype=maintype or "application",
                           subtype=subtype or "octet-stream", filename=a["filename"])
    host = os.environ.get("SMTP_HOST", "smtp.mail.yahoo.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=20) as server:
        server.login(os.environ["YAHOO_EMAIL"], os.environ["YAHOO_APP_PASSWORD"])
        server.send_message(msg)
    return True


def send_email(to_email: str, subject: str, body: str, attachments=None) -> bool:
    """Send an email via Resend (primary) or Yahoo SMTP (fallback).
    attachments: optional list of {filename, content(bytes), content_type}."""
    if not email_configured():
        logger.info("Email not configured; skipping send")
        return False
    to_email = (to_email or "").strip().replace("\r", "").replace("\n", "")
    if not _valid(to_email):
        logger.error("Invalid recipient email; skipping send")
        return False
    subject = (subject or "").replace("\r", " ").replace("\n", " ")
    try:
        if resend_configured():
            return _send_resend(to_email, subject, body, attachments)
        return _send_yahoo(to_email, subject, body, attachments)
    except Exception as e:
        logger.error(f"Email send failed (primary): {e}")
        if resend_configured() and yahoo_configured():
            try:
                return _send_yahoo(to_email, subject, body, attachments)
            except Exception as e2:
                logger.error(f"Email send failed (yahoo fallback): {e2}")
        return False
