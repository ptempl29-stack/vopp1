import re

from core.db import db
from core.config import CLINICAL_ROLES

_TITLE_PREFIX = re.compile(r"^(dr|dra|doctor|doctora|lic|licda|licdo)\.?\s+", re.I)


def norm_name(name) -> str:
    return " ".join(_TITLE_PREFIX.sub("", (name or "").strip().lower()).split())


def _names_match(note_name: str, account_name: str) -> bool:
    """Exact normalized match, or same first name with all names contained (e.g. 'Saday Cabrera' ~ 'Saday Cabrera Rodriguez')."""
    a, b = norm_name(note_name), norm_name(account_name)
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = a.split(), b.split()
    short, full = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    # same first name and every name of the shorter form present in the longer one
    # ('Saday Cabrera' ~ 'Saday Cabrera Rodriguez' / 'Saday Rodriguez Cabrera')
    return len(short) >= 2 and short[0] == full[0] and set(short) <= set(full)


async def resolve_provider_id(name):
    """Map a legacy free-text provider name to ONE clinical account id (None if none/ambiguous)."""
    if not norm_name(name):
        return None
    users = await db.users.find({"role": {"$in": list(CLINICAL_ROLES)}}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
    exact = [u["id"] for u in users if norm_name(u.get("name")) == norm_name(name)]
    if exact:
        return exact[0] if len(exact) == 1 else None
    loose = [u["id"] for u in users if _names_match(name, u.get("name"))]
    return loose[0] if len(loose) == 1 else None


async def note_provider_id(note: dict):
    return note.get("attending_provider_id") or await resolve_provider_id(note.get("attending_provider"))


async def note_signer_id(note: dict):
    return note.get("signed_by_id") or await resolve_provider_id(note.get("signed_by"))
