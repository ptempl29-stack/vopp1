from core.db import db
from core.config import DEFAULT_TABS, ALL_TABS, ROLES


async def get_role_templates() -> dict:
    docs = {d["role"]: d["allowed_tabs"] async for d in db.role_templates.find({}, {"_id": 0})}
    return {r: docs.get(r, DEFAULT_TABS.get(r, ["dashboard"])) for r in ROLES}


async def resolve_role_tabs(role: str) -> list:
    d = await db.role_templates.find_one({"role": role}, {"_id": 0})
    if d:
        return [t for t in d.get("allowed_tabs", []) if t in ALL_TABS] or DEFAULT_TABS.get(role, ["dashboard"])
    return DEFAULT_TABS.get(role, ["dashboard"])
