import os
import re
import smtplib
from email.message import EmailMessage

from core.db import logger


def email_configured() -> bool:
    return bool(os.environ.get("YAHOO_EMAIL") and os.environ.get("YAHOO_APP_PASSWORD"))


def send_email(to_email: str, subject: str, body: str) -> bool:
    if not email_configured():
        logger.info("Email not configured; skipping send")
        return False
    to_email = (to_email or "").strip().replace("\r", "").replace("\n", "")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", to_email):
        logger.error("Invalid recipient email; skipping send")
        return False
    subject = (subject or "").replace("\r", " ").replace("\n", " ")
    msg = EmailMessage()
    msg["From"] = os.environ["YAHOO_EMAIL"]
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    host = os.environ.get("SMTP_HOST", "smtp.mail.yahoo.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    try:
        with smtplib.SMTP_SSL(host, port, timeout=20) as server:
            server.login(os.environ["YAHOO_EMAIL"], os.environ["YAHOO_APP_PASSWORD"])
            server.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False
