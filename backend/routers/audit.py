from typing import Optional

from fastapi import APIRouter, Depends

from core.db import db
from core.security import require_roles

router = APIRouter()


@router.get("/audit")
async def list_audit(actor_id: Optional[str] = None, resource: Optional[str] = None,
                     action: Optional[str] = None, start: Optional[str] = None,
                     end: Optional[str] = None, limit: int = 100, skip: int = 0,
                     user: dict = Depends(require_roles("admin"))):
    q = {}
    if actor_id:
        q["actor_id"] = actor_id
    if resource:
        q["resource"] = resource
    if action:
        q["action"] = action
    if start or end:
        rng = {}
        if start:
            rng["$gte"] = start
        if end:
            rng["$lte"] = end + "T23:59:59"
        q["created_at"] = rng
    limit = max(1, min(int(limit), 500))
    skip = max(0, int(skip))
    total = await db.audit_logs.count_documents(q)
    items = await db.audit_logs.find(q, {"_id": 0, "expires_at": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": items}
