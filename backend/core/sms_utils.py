import os
import re

from core.db import logger


def sms_configured() -> bool:
    return bool(os.environ.get("TWILIO_ACCOUNT_SID")
                and os.environ.get("TWILIO_AUTH_TOKEN")
                and os.environ.get("TWILIO_PHONE_NUMBER"))


def _normalize(phone: str) -> str:
    p = re.sub(r"[^\d+]", "", phone or "")
    if p and not p.startswith("+"):
        p = "+" + p
    return p


def send_sms(to_phone: str, body: str) -> bool:
    if not sms_configured():
        logger.info("SMS not configured; skipping send")
        return False
    to_phone = _normalize(to_phone)
    if not re.match(r"^\+\d{7,15}$", to_phone):
        logger.error("Invalid recipient phone; skipping SMS")
        return False
    try:
        from twilio.rest import Client
        client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
        client.messages.create(to=to_phone, from_=os.environ["TWILIO_PHONE_NUMBER"], body=body)
        return True
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
        return False
