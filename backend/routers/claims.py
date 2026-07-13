import io
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from core.db import db, now_iso, logger
from core.config import APP_NAME, EXT_CONTENT_TYPES
from core.security import require_roles
from core.audit import log_audit
from core.storage import put_object, get_object

router = APIRouter()

CLAIM_STATUSES = {"draft", "submitted"}
UPLOAD_EXTS = {"pdf", "png", "jpg", "jpeg", "webp", "doc", "docx", "txt", "xls", "xlsx"}
EXTRA_CT = {"xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


class ClaimInput(BaseModel):
    name: str
    patient_id: Optional[str] = None
    claim_number: Optional[str] = None
    status: str = "draft"
    notes: Optional[str] = None


async def _patient_name(pid):
    if not pid:
        return None
    p = await db.patients.find_one({"id": pid}, {"_id": 0})
    return f"{p['first_name']} {p['last_name']}" if p else None


@router.get("/claims")
async def list_claims(user: dict = Depends(require_roles("admin"))):
    packets = await db.claim_packets.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    await log_audit("view", "claim", actor=user, detail=f"list ({len(packets)})")
    return packets


@router.post("/claims")
async def create_claim(data: ClaimInput, user: dict = Depends(require_roles("admin"))):
    if data.status not in CLAIM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    doc = {"id": str(uuid.uuid4()), "name": data.name, "patient_id": data.patient_id,
           "patient_name": await _patient_name(data.patient_id), "claim_number": data.claim_number,
           "status": data.status, "notes": data.notes, "items": [],
           "created_at": now_iso(), "created_by": user["name"]}
    await db.claim_packets.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "claim", actor=user, resource_id=doc["id"], detail=data.name)
    return doc


@router.get("/claims/{cid}")
async def get_claim(cid: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    return c


@router.put("/claims/{cid}")
async def update_claim(cid: str, data: ClaimInput, user: dict = Depends(require_roles("admin"))):
    if data.status not in CLAIM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    updates = {"name": data.name, "patient_id": data.patient_id,
               "patient_name": await _patient_name(data.patient_id), "claim_number": data.claim_number,
               "status": data.status, "notes": data.notes, "updated_at": now_iso()}
    res = await db.claim_packets.update_one({"id": cid}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=data.name)
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.delete("/claims/{cid}")
async def delete_claim(cid: str, user: dict = Depends(require_roles("admin"))):
    await db.claim_packets.delete_one({"id": cid})
    await log_audit("delete", "claim", actor=user, resource_id=cid)
    return {"ok": True}


@router.post("/claims/{cid}/attach-form")
async def attach_form(cid: str, payload: dict, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    form = await db.forms.find_one({"id": payload.get("form_id")})
    if not form or not form.get("attachment"):
        raise HTTPException(status_code=400, detail="Form has no attached document")
    att = form["attachment"]
    item = {"id": str(uuid.uuid4()), "source": "form", "form_id": form["id"],
            "storage_path": att["storage_path"], "filename": att["filename"],
            "content_type": att.get("content_type", "application/octet-stream"), "size": att.get("size")}
    await db.claim_packets.update_one({"id": cid}, {"$push": {"items": item}, "$set": {"updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"attach form {att['filename']}")
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.post("/claims/{cid}/upload")
async def upload_to_claim(cid: str, file: UploadFile = File(...), user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    if ext not in UPLOAD_EXTS:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    safe_ct = EXT_CONTENT_TYPES.get(ext) or EXTRA_CT.get(ext, "application/octet-stream")
    payload = await file.read()
    if len(payload) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 15MB)")
    path = f"{APP_NAME}/claims/{cid}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, payload, safe_ct)
    except Exception as e:
        logger.error(f"claim upload failed: {e}")
        raise HTTPException(status_code=502, detail="File storage failed")
    item = {"id": str(uuid.uuid4()), "source": "upload", "form_id": None,
            "storage_path": result["path"], "filename": file.filename, "content_type": safe_ct,
            "size": result.get("size")}
    await db.claim_packets.update_one({"id": cid}, {"$push": {"items": item}, "$set": {"updated_at": now_iso()}})
    await log_audit("update", "claim", actor=user, resource_id=cid, detail=f"upload {file.filename}")
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.delete("/claims/{cid}/items/{item_id}")
async def remove_item(cid: str, item_id: str, user: dict = Depends(require_roles("admin"))):
    await db.claim_packets.update_one({"id": cid}, {"$pull": {"items": {"id": item_id}}, "$set": {"updated_at": now_iso()}})
    return await db.claim_packets.find_one({"id": cid}, {"_id": 0})


@router.get("/claims/{cid}/items/{item_id}/download")
async def download_item(cid: str, item_id: str, user: dict = Depends(require_roles("admin"))):
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    item = next((i for i in c.get("items", []) if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    data, _ = get_object(item["storage_path"])
    fname = item["filename"].replace('"', "").replace("\n", "").replace("\r", "")
    return Response(content=data, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-Content-Type-Options": "nosniff"})


@router.get("/claims/{cid}/merged")
async def merged_pdf(cid: str, user: dict = Depends(require_roles("admin"))):
    from pypdf import PdfWriter, PdfReader
    from PIL import Image
    c = await db.claim_packets.find_one({"id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Claim packet not found")
    writer = PdfWriter()
    added = 0
    for item in c.get("items", []):
        try:
            data, _ = get_object(item["storage_path"])
            fn = item["filename"].lower()
            if fn.endswith(".pdf"):
                for page in PdfReader(io.BytesIO(data)).pages:
                    writer.add_page(page)
                added += 1
            elif fn.rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp"):
                img = Image.open(io.BytesIO(data)).convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="PDF")
                for page in PdfReader(io.BytesIO(buf.getvalue())).pages:
                    writer.add_page(page)
                added += 1
        except Exception as e:
            logger.error(f"merge skip {item.get('filename')}: {e}")
    if added == 0:
        raise HTTPException(status_code=400, detail="No PDF/image documents to merge in this packet")
    out = io.BytesIO()
    writer.write(out)
    await log_audit("view", "claim", actor=user, resource_id=cid, detail="download merged PDF")
    fname = (c.get("name") or "claim_packet").replace('"', "").replace(" ", "_")[:60]
    return StreamingResponse(io.BytesIO(out.getvalue()), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'})
