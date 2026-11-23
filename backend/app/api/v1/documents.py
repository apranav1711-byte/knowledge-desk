from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from app.api.v1.schemas import DocumentPatch
from app.core.acl import CLASSIFICATIONS, can_read, can_upload
from app.core.auth import Identity, current_identity
from app.core.config import settings
from app.core.db import pool
from app.services import audit, ingestion, supabase_admin
from app.services.parsing import SUPPORTED

router = APIRouter(prefix="/documents", tags=["Documents"])

_COLS = """id, title, filename, file_type, file_size, classification, department, status, error, version,
           total_pages, total_chunks, uploaded_by, created_at, updated_at"""


def _json(r) -> dict:
    d = dict(r)
    for k in ("id", "uploaded_by"):
        d[k] = str(d[k]) if d.get(k) else None
    return d


async def _visible(p, user: Identity, doc_id: str):
    """Fetch a document only if this user may see it (same predicate as the RLS policy)."""
    try:
        r = await p.fetchrow(f"select {_COLS}, storage_path from public.documents where id=$1::uuid and tenant_id=$2::uuid",
                             doc_id, user.tenant_id)
    except Exception:  # malformed uuid
        raise HTTPException(404, "Document not found")
    if not r or not can_read(user.role, r["classification"]):
        raise HTTPException(404, "Document not found")  # 404, not 403: do not reveal that it exists
    if r["status"] != "ready" and user.role != "admin" and str(r["uploaded_by"]) != user.id:
        raise HTTPException(404, "Document not found")
    return r


def _can_manage(user: Identity, r) -> bool:
    return user.role == "admin" or (str(r["uploaded_by"]) == user.id and can_upload(user.role, r["classification"]))


@router.get("")
async def list_documents(user: Identity = Depends(current_identity)):
    p = await pool()
    rows = await p.fetch(
        f"""select {_COLS} from public.documents
            where tenant_id=$1::uuid
              and $2 = any(private.roles_for_classification(classification))
              and (status='ready' or $2='admin' or uploaded_by=$3::uuid)
            order by created_at desc""",
        user.tenant_id, user.role, user.id,
    )
    return [{**_json(r), "can_manage": _can_manage(user, r)} for r in rows]


@router.post("", status_code=202)
async def upload(
    background: BackgroundTasks,
    classification: str = Form(...),
    department: str = Form(""),
    file: UploadFile = File(...),
    user: Identity = Depends(current_identity),
):
    if classification not in CLASSIFICATIONS:
        raise HTTPException(422, f"Classification must be one of {CLASSIFICATIONS}")
    if not can_upload(user.role, classification):
        raise HTTPException(403, "Your role cannot add documents at this classification level")
    name = ingestion.safe_name(file.filename or "document")
    if Path(name).suffix.lower() not in SUPPORTED:
        raise HTTPException(422, "Unsupported file type. Supported: PDF, DOCX, XLSX, CSV, PPTX, HTML, Markdown, TXT.")
    data = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    await file.close()
    if not data:
        raise HTTPException(422, "The file is empty.")
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"The file exceeds the {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")
    doc_id, duplicate = await ingestion.register_upload(user, name, data, classification, department[:80])
    if not duplicate:
        if settings.INLINE_PROCESSING:  # serverless: work after the response would be frozen, so finish it now
            await ingestion.process_document(doc_id, data, user)
        else:
            background.add_task(ingestion.process_document, doc_id, data, user)
    p = await pool()
    row = await p.fetchrow(f"select {_COLS} from public.documents where id=$1::uuid", doc_id)
    return {**_json(row), "duplicate": duplicate}


@router.get("/{doc_id}")
async def get_document(doc_id: str, user: Identity = Depends(current_identity)):
    p = await pool()
    r = await _visible(p, user, doc_id)
    chunks = await p.fetch(
        "select chunk_index, page, section, kind, content from public.chunks where document_id=$1::uuid order by chunk_index",
        doc_id,
    )
    return {**_json(r), "can_manage": _can_manage(user, r), "excerpts": [dict(c) for c in chunks]}


@router.get("/{doc_id}/download")
async def download(doc_id: str, user: Identity = Depends(current_identity)):
    p = await pool()
    r = await _visible(p, user, doc_id)
    if r["status"] != "ready" or not r["storage_path"]:
        raise HTTPException(409, "The original file is not available")
    await audit.log_event(user, "document.download", detail=dict(document_id=doc_id))
    return {"url": await supabase_admin.storage_signed_url(r["storage_path"], 60), "expires_in": 60}


@router.patch("/{doc_id}")
async def patch_document(doc_id: str, body: DocumentPatch, user: Identity = Depends(current_identity)):
    p = await pool()
    r = await _visible(p, user, doc_id)
    if not _can_manage(user, r):
        raise HTTPException(403, "You cannot modify this document")
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(422, "Nothing to change")
    if "classification" in changes and not can_upload(user.role, changes["classification"]):
        raise HTTPException(403, "Your role cannot assign that classification")
    await p.execute(
        "update public.documents set title=coalesce($2,title), classification=coalesce($3,classification), "
        "department=coalesce($4,department) where id=$1::uuid",  # trigger re-labels chunk ACLs atomically
        doc_id, changes.get("title"), changes.get("classification"), changes.get("department"),
    )
    if "classification" in changes:
        await audit.log_event(user, "document.reclassify", detail=dict(
            document_id=doc_id, **{"from": r["classification"], "to": changes["classification"]}))
    row = await p.fetchrow(f"select {_COLS} from public.documents where id=$1::uuid", doc_id)
    return _json(row)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, user: Identity = Depends(current_identity)):
    p = await pool()
    r = await _visible(p, user, doc_id)
    if not _can_manage(user, r):
        raise HTTPException(403, "You cannot delete this document")
    await p.execute("delete from public.documents where id=$1::uuid", doc_id)  # chunks cascade: instantly unsearchable
    if r["storage_path"]:
        try:
            await supabase_admin.storage_delete(r["storage_path"])
        except Exception:  # noqa: BLE001 - file orphan is harmless; DB rows are already gone
            pass
    await audit.log_event(user, "document.delete", detail=dict(document_id=doc_id, filename=r["filename"]))
