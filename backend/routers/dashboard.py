from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from core.db import db
from core.security import get_current_user

router = APIRouter()


@router.get("/stats")
async def stats(user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).date().isoformat()
    return {
        "patients": await db.patients.count_documents({}),
        "appointments_today": await db.appointments.count_documents({"date": today}),
        "appointments_total": await db.appointments.count_documents({}),
        "pending_notes": await db.notes.count_documents({
            "ai_summarized": {"$ne": True},
            "summary": {"$in": [None, ""]},
            "note_type": {"$ne": "daily_no_ai"},
        }),
        "unpaid_invoices": await db.invoices.count_documents({"status": {"$ne": "paid"}}),
        "pending_forms": await db.forms.count_documents({"status": {"$in": ["sent", "pending"]}}),
        "unread_messages": await db.messages.count_documents({"to_user_id": user["id"], "read": False}),
    }
