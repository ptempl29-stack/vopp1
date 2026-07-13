import re
import hmac
import hashlib
import base64
import os
from urllib.parse import urlencode, quote
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core.security import get_current_user, require_roles
from core.audit import log_audit
from core.email_utils import send_email
from core.db import db

router = APIRouter()

ROOM_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{2,63}$", re.I)


def validate_room(room: str) -> str:
    room = (room or "").strip().lstrip("/")
    if "doxy.me/" in room:
        room = room.split("doxy.me/", 1)[1]
    room = room.strip("/")
    if not ROOM_RE.match(room):
        raise HTTPException(status_code=400, detail="Invalid Doxy.me room name")
    return room


def _pid(patient_id: str) -> str:
    digest = hmac.new(os.environ["JWT_SECRET"].encode(), (patient_id or "").encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:16]


def build_url(room: str, patient_name: Optional[str] = None, patient_id: Optional[str] = None) -> str:
    base = f"https://doxy.me/{quote(room)}"
    params = {}
    if patient_name:
        params["username"] = patient_name
        params["autocheckin"] = "true"
    if patient_id:
        params["pid"] = _pid(patient_id)
    return f"{base}?{urlencode(params, quote_via=quote)}" if params else base


class InviteInput(BaseModel):
    patient_name: Optional[str] = None
    patient_id: Optional[str] = None
    patient_email: Optional[str] = None
    send_email: bool = False


class RoomInput(BaseModel):
    room: str


@router.put("/telehealth/my-room")
async def set_my_room(data: RoomInput, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    room = "" if not data.room.strip() else validate_room(data.room)
    await db.users.update_one({"id": user["id"]}, {"$set": {"doxy_room": room}})
    return {"ok": True, "doxy_room": room}


@router.post("/telehealth/doxy-invite")
async def doxy_invite(data: InviteInput, user: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    room = user.get("doxy_room")
    if not room:
        raise HTTPException(status_code=400, detail="Set your Doxy.me room name first")
    url = build_url(room, data.patient_name, data.patient_id)
    sent = False
    if data.send_email:
        if not data.patient_email:
            raise HTTPException(status_code=400, detail="Patient email required")
        sent = send_email(data.patient_email,
            "Your telehealth visit link — Veterans of Puerto Plata",
            f"Hello,\n\nPlease join your secure video visit using the link below:\n{url}\n\nThank you.")
    await log_audit("create", "telehealth", actor=user,
                    detail=f"invite {data.patient_name or ''}" + (" (emailed)" if sent else ""))
    return {"join_url": url, "emailed": sent}
