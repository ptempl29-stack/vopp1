from fastapi import APIRouter, HTTPException, Depends

from core.db import db
from core.config import DEFAULT_SETTINGS
from core.security import get_current_user, require_roles
from models.schemas import SettingsInput

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
