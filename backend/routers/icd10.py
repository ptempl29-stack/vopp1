from fastapi import APIRouter, Depends

from core.security import get_current_user
from core import icd10 as icd10_lookup

router = APIRouter()


@router.get("/icd10/search")
async def icd10_search(q: str = "", user: dict = Depends(get_current_user)):
    """Search ICD-10-CM codes by code or description keyword, for the
    diagnosis picker on notes and invoices. Read-only; never touches any
    patient record."""
    return {"results": await icd10_lookup.search(q)}


@router.get("/icd10/describe")
async def icd10_describe(code: str = "", user: dict = Depends(get_current_user)):
    """Resolve a single stored code to its official description, for
    read-only displays (note/invoice views, lists). Read-only; never
    touches any patient record."""
    description = await icd10_lookup.describe(code)
    return {
        "code": code,
        "description": description,
        "label": icd10_lookup.format_label(code, description),
    }
