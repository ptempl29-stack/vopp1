import uuid
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta

from core.db import db, logger

_client_ip: ContextVar[str] = ContextVar("client_ip", default="")
RETENTION_DAYS = 730  # ~2 years


def set_client_ip(ip: str):
    _client_ip.set(ip or "")


async def log_audit(action: str, resource: str, actor: dict = None,
                    resource_id: str = None, detail: str = None):
    """Best-effort PHI access/change audit trail. Never raises into the request."""
    try:
        now = datetime.now(timezone.utc)
        actor = actor or {}
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "action": action,
            "resource": resource,
            "resource_id": resource_id,
            "detail": (detail or "")[:300],
            "actor_id": actor.get("id"),
            "actor_name": actor.get("name"),
            "actor_role": actor.get("role"),
            "ip": _client_ip.get(),
            "created_at": now.isoformat(),
            "expires_at": now + timedelta(days=RETENTION_DAYS),
        })
    except Exception:
        logger.exception("audit log write failed")
