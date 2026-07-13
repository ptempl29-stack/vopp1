from fastapi import APIRouter, HTTPException, Depends

from core.db import db
from core.config import ROLES, ALL_TABS
from core.security import require_roles
from core.audit import log_audit
from core.roles import get_role_templates

router = APIRouter()


@router.get("/role-templates")
async def read_role_templates(current: dict = Depends(require_roles("admin"))):
    return await get_role_templates()


@router.put("/role-templates/{role}")
async def update_role_template(role: str, payload: dict, current: dict = Depends(require_roles("admin"))):
    if role not in ROLES or role == "admin":
        raise HTTPException(status_code=400, detail="Invalid role")
    tabs = [tt for tt in payload.get("allowed_tabs", []) if tt in ALL_TABS]
    await db.role_templates.update_one({"role": role}, {"$set": {"role": role, "allowed_tabs": tabs}}, upsert=True)
    updated = 0
    if payload.get("apply_to_existing"):
        res = await db.users.update_many({"role": role}, {"$set": {"allowed_tabs": tabs}})
        updated = res.modified_count
    await log_audit("update", "role", actor=current, resource_id=role,
                    detail=f"tabs={len(tabs)} applied_to={updated}")
    return {"role": role, "allowed_tabs": tabs, "applied_to_existing": updated}


@router.get("/meta/tabs")
async def meta_tabs(current: dict = Depends(require_roles("admin"))):
    return {"tabs": ALL_TABS, "roles": ROLES, "defaults": await get_role_templates()}
