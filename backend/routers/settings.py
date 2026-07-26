from fastapi import APIRouter, HTTPException, Depends

from core.db import db
from core.config import DEFAULT_SETTINGS
from core.security import get_current_user, require_roles
from core.email_utils import send_email, email_configured
from models.schemas import SettingsInput

import os

router = APIRouter()


async def get_settings_doc():
    s = await db.settings.find_one({"key": "clinic"}, {"_id": 0, "key": 0})
    return s or DEFAULT_SETTINGS


@router.get("/public/settings")
async def public_settings():
    return await get_settings_doc()


@router.get("/settings")
async def read_settings(user: dict = Depends(get_current_user)):
    return await get_settings_doc()


@router.put("/settings")
async def update_settings(data: SettingsInput, current: dict = Depends(require_roles("doctor", "nurse", "psychologist"))):
    payload = data.model_dump()
    if payload.get("logo") and len(payload["logo"]) > 900000:
        raise HTTPException(status_code=400, detail="Logo image too large (max ~650KB)")
    await db.settings.update_one({"key": "clinic"}, {"$set": {**payload, "key": "clinic"}}, upsert=True)
    return await get_settings_doc()


@router.get("/hidden-options")
async def get_hidden_options(user: dict = Depends(get_current_user)):
    d = await db.settings.find_one({"key": "hidden_options"}, {"_id": 0, "map": 1})
    return (d or {}).get("map", {})


@router.post("/hidden-options")
async def hide_option(payload: dict, user: dict = Depends(get_current_user)):
    lst = (payload.get("list") or "").strip().replace(".", "_")
    val = str(payload.get("value") or "").strip()
    if not lst or not val:
        raise HTTPException(status_code=400, detail="list and value are required")
    await db.settings.update_one({"key": "hidden_options"},
                                 {"$addToSet": {f"map.{lst}": val}, "$set": {"key": "hidden_options"}},
                                 upsert=True)
    d = await db.settings.find_one({"key": "hidden_options"}, {"_id": 0, "map": 1})
    return (d or {}).get("map", {})


@router.post("/hidden-options/restore")
async def restore_option(payload: dict, user: dict = Depends(get_current_user)):
    lst = (payload.get("list") or "").strip().replace(".", "_")
    val = str(payload.get("value") or "").strip()
    if not lst or not val:
        raise HTTPException(status_code=400, detail="list and value are required")
    await db.settings.update_one({"key": "hidden_options"}, {"$pull": {f"map.{lst}": val}})
    d = await db.settings.find_one({"key": "hidden_options"}, {"_id": 0, "map": 1})
    return (d or {}).get("map", {})


@router.post("/settings/test-email")
async def send_test_email(payload: dict, current: dict = Depends(require_roles("admin"))):
    to = (payload.get("to") or "").strip()
    if not to:
        raise HTTPException(status_code=400, detail="Recipient email is required")
    if not email_configured():
        raise HTTPException(status_code=400, detail="Email is not configured on the server")
    sender = os.environ.get("SENDER_EMAIL", "")
    clinic = (await get_settings_doc()).get("clinic_name", "Veterans of Puerto Plata")
    ok = send_email(
        to,
        f"Test email from {clinic}",
        f"This is a test email confirming that {clinic} can send patient emails.\n\nSent from: {sender}",
    )
    if not ok:
        raise HTTPException(status_code=502, detail="Send failed — check the sender domain is verified and the recipient address is valid")
    return {"ok": True, "sender": sender, "to": to}
