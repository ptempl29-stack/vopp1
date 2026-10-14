import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel

from core.db import db, now_iso, logger
from core.config import FOLDERS_ROLES, EXT_CONTENT_TYPES, APP_NAME
from core.security import require_roles
from core.audit import log_audit
from core.storage import put_object, get_object, delete_object
from models.schemas import IdList

router = APIRouter()

UPLOAD_EXTS = {"pdf", "png", "jpg", "jpeg", "webp", "doc", "docx", "txt", "xls", "xlsx"}
EXTRA_CT = {"xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


class SubfolderInput(BaseModel):
    name: str


class ItemEdit(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None


class MoveItem(BaseModel):
    patient_id: str
    subfolder_id: Optional[str] = None


class AttachForm(BaseModel):
    form_id: str
    subfolder_id: Optional[str] = None


async def _patient_name(pid):
    if not pid:
        return None
    p = await db.patients.find_one({"id": pid}, {"_id": 0, "first_name": 1, "last_name": 1})
    return f"{p['first_name']} {p['last_name']}" if p else None


@router.get("/folders/patients")
async def list_patient_folders(user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    pts = await db.patients.find({}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "dob": 1, "folder_ready": 1}).to_list(2000)
    counts, subcounts = {}, {}
    async for it in db.folder_items.find({}, {"_id": 0, "patient_id": 1}):
        counts[it["patient_id"]] = counts.get(it["patient_id"], 0) + 1
    async for sf in db.folder_subfolders.find({}, {"_id": 0, "patient_id": 1}):
        subcounts[sf["patient_id"]] = subcounts.get(sf["patient_id"], 0) + 1
    result = [{"id": p["id"], "name": f"{p['first_name']} {p['last_name']}", "dob": p.get("dob"),
               "ready": bool(p.get("folder_ready")),
               "item_count": counts.get(p["id"], 0), "subfolder_count": subcounts.get(p["id"], 0)} for p in pts]
    result.sort(key=lambda x: x["name"].lower())
    await log_audit("view", "folder", actor=user, detail=f"list ({len(result)})")
    return result


@router.get("/folders/options/forms")
async def attachable_forms(user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    forms = await db.forms.find({"attachment": {"$ne": None}}, {"_id": 0}).sort("created_at", -1).to_list(500)
    patients = {p["id"]: f"{p['first_name']} {p['last_name']}" async for p in db.patients.find({}, {"_id": 0})}
    return [{"id": f["id"], "title": f.get("title"), "form_type": f.get("form_type"),
             "filename": f["attachment"].get("filename"), "patient_id": f.get("patient_id"),
             "patient_name": patients.get(f.get("patient_id"), "-")} for f in forms]


@router.get("/folders/{patient_id}")
async def get_patient_folder(patient_id: str, user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    p = await db.patients.find_one({"id": patient_id}, {"_id": 0, "first_name": 1, "last_name": 1, "folder_ready": 1})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    name = f"{p['first_name']} {p['last_name']}"
    subs = await db.folder_subfolders.find({"patient_id": patient_id}, {"_id": 0}).sort("name", 1).to_list(500)
    items = await db.folder_items.find({"patient_id": patient_id}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    await log_audit("view", "folder", actor=user, resource_id=patient_id, detail=name)
    return {"patient_id": patient_id, "patient_name": name, "ready": bool(p.get("folder_ready")),
            "subfolders": subs, "items": items}


class ReadyInput(BaseModel):
    ready: bool


@router.put("/folders/{patient_id}/ready")
async def set_folder_ready(patient_id: str, data: ReadyInput, user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    if not await _patient_name(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    await db.patients.update_one({"id": patient_id}, {"$set": {
        "folder_ready": data.ready,
        "folder_ready_at": now_iso() if data.ready else None,
        "folder_ready_by": user["name"] if data.ready else None}})
    await log_audit("update", "folder", actor=user, resource_id=patient_id,
                    detail=f"folder {'ready' if data.ready else 'not ready'}")
    return {"ok": True, "ready": data.ready}


@router.post("/folders/{patient_id}/subfolders")
async def create_subfolder(patient_id: str, data: SubfolderInput, user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Folder name required")
    if not await _patient_name(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    doc = {"id": str(uuid.uuid4()), "patient_id": patient_id, "name": name[:80],
           "created_at": now_iso(), "created_by": user["name"], "created_by_id": user["id"]}
    await db.folder_subfolders.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "folder", actor=user, resource_id=patient_id, detail=f"subfolder {name}")
    return doc


@router.put("/folders/subfolders/{sid}")
async def rename_subfolder(sid: str, data: SubfolderInput, user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Folder name required")
    res = await db.folder_subfolders.update_one({"id": sid}, {"$set": {"name": name[:80], "updated_at": now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Folder not found")
    await log_audit("update", "folder", actor=user, resource_id=sid, detail=f"rename {name}")
    return await db.folder_subfolders.find_one({"id": sid}, {"_id": 0})


@router.delete("/folders/subfolders/{sid}")
async def delete_subfolder(sid: str, user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    sf = await db.folder_subfolders.find_one({"id": sid}, {"_id": 0})
    if not sf:
        raise HTTPException(status_code=404, detail="Folder not found")
    # keep documents safe: move items inside back to the patient's root folder
    await db.folder_items.update_many({"subfolder_id": sid}, {"$set": {"subfolder_id": None}})
    await db.folder_subfolders.delete_one({"id": sid})
    await log_audit("delete", "folder", actor=user, resource_id=sid, detail=sf.get("name"))
    return {"ok": True}


@router.post("/folders/{patient_id}/upload")
async def upload_item(patient_id: str, file: UploadFile = File(...),
                      subfolder_id: str = Form(""), label: str = Form(""),
                      user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    if not await _patient_name(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    if ext not in UPLOAD_EXTS:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    safe_ct = EXT_CONTENT_TYPES.get(ext) or EXTRA_CT.get(ext, "application/octet-stream")
    payload = await file.read()
    if len(payload) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 15MB)")
    path = f"{APP_NAME}/folders/{patient_id}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, payload, safe_ct)
    except Exception as e:
        logger.error(f"folder upload failed: {e}")
        raise HTTPException(status_code=502, detail="File storage failed")
    doc = {"id": str(uuid.uuid4()), "patient_id": patient_id, "subfolder_id": subfolder_id or None,
           "source": "upload", "form_id": None, "storage_path": result["path"],
           "filename": file.filename, "label": (label.strip() or file.filename)[:120], "description": "",
           "content_type": safe_ct, "size": result.get("size"),
           "created_at": now_iso(), "created_by": user["name"], "created_by_id": user["id"]}
    await db.folder_items.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "folder", actor=user, resource_id=patient_id, detail=f"upload {file.filename}")
    return doc


@router.post("/folders/{patient_id}/attach-form")
async def attach_form(patient_id: str, data: AttachForm, user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    if not await _patient_name(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    form = await db.forms.find_one({"id": data.form_id})
    if not form or not form.get("attachment"):
        raise HTTPException(status_code=400, detail="Form has no attached document")
    att = form["attachment"]
    doc = {"id": str(uuid.uuid4()), "patient_id": patient_id, "subfolder_id": data.subfolder_id or None,
           "source": "form", "form_id": form["id"], "storage_path": att["storage_path"],
           "filename": att["filename"], "label": (form.get("title") or att["filename"])[:120], "description": "",
           "content_type": att.get("content_type", "application/octet-stream"), "size": att.get("size"),
           "created_at": now_iso(), "created_by": user["name"], "created_by_id": user["id"]}
    await db.folder_items.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("create", "folder", actor=user, resource_id=patient_id, detail=f"attach form {att['filename']}")
    return doc


@router.put("/folders/items/{item_id}")
async def edit_item(item_id: str, data: ItemEdit, user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    updates = {"updated_at": now_iso()}
    if data.label is not None:
        updates["label"] = data.label.strip()[:120]
    if data.description is not None:
        updates["description"] = data.description[:2000]
    res = await db.folder_items.update_one({"id": item_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    await log_audit("update", "folder", actor=user, resource_id=item_id, detail="edit item")
    return await db.folder_items.find_one({"id": item_id}, {"_id": 0})


@router.post("/folders/items/{item_id}/move")
async def move_item(item_id: str, data: MoveItem, user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    it = await db.folder_items.find_one({"id": item_id}, {"_id": 0})
    if not it:
        raise HTTPException(status_code=404, detail="Item not found")
    if not await _patient_name(data.patient_id):
        raise HTTPException(status_code=404, detail="Target patient not found")
    if data.subfolder_id:
        sf = await db.folder_subfolders.find_one({"id": data.subfolder_id, "patient_id": data.patient_id})
        if not sf:
            raise HTTPException(status_code=400, detail="Target folder not found for that patient")
    await db.folder_items.update_one({"id": item_id}, {"$set": {
        "patient_id": data.patient_id, "subfolder_id": data.subfolder_id or None, "updated_at": now_iso()}})
    await log_audit("update", "folder", actor=user, resource_id=item_id, detail=f"move to {data.patient_id}")
    return await db.folder_items.find_one({"id": item_id}, {"_id": 0})


@router.post("/folders/items/bulk-delete")
async def bulk_delete_items(data: IdList, user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    docs = await db.folder_items.find({"id": {"$in": data.ids}}, {"_id": 0}).to_list(2000)
    deletable = [d for d in docs
                 if user["role"] == "admin" or d.get("created_by_id") in (user["id"], None)]
    for d in deletable:
        if d.get("source") == "upload" and d.get("storage_path"):
            delete_object(d["storage_path"])
    ids = [d["id"] for d in deletable]
    if ids:
        await db.folder_items.delete_many({"id": {"$in": ids}})
    await log_audit("delete", "folder", actor=user, detail=f"bulk ({len(ids)})")
    return {"deleted": len(ids), "skipped": len(data.ids) - len(ids)}


@router.delete("/folders/items/{item_id}")
async def delete_item(item_id: str, user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    it = await db.folder_items.find_one({"id": item_id}, {"_id": 0})
    if not it:
        raise HTTPException(status_code=404, detail="Item not found")
    if user["role"] != "admin" and it.get("created_by_id") not in (user["id"], None):
        raise HTTPException(status_code=403, detail="You can only delete items you added")
    if it.get("source") == "upload" and it.get("storage_path"):
        delete_object(it["storage_path"])
    await db.folder_items.delete_one({"id": item_id})
    await log_audit("delete", "folder", actor=user, resource_id=item_id, detail=it.get("label"))
    return {"ok": True}


@router.get("/folders/items/{item_id}/download")
async def download_item(item_id: str, user: dict = Depends(require_roles(*FOLDERS_ROLES))):
    it = await db.folder_items.find_one({"id": item_id})
    if not it:
        raise HTTPException(status_code=404, detail="Item not found")
    data, _ = get_object(it["storage_path"])
    fname = (it.get("filename") or "document").replace('"', "").replace("\n", "").replace("\r", "")
    await log_audit("view", "folder", actor=user, resource_id=item_id, detail=f"download {fname}")
    return Response(content=data, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-Content-Type-Options": "nosniff"})
