from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.api.v1.schemas import DocumentPatch
from app.core.acl import CLASSIFICATIONS, can_read, can_upload, roles_for_classification
from app.core.auth import Identity, current_identity, decode_token, issue_token
from app.core.config import settings
from app.core.db import now, pool
from app.services import audit, ingestion, storage
from app.services.parsing import SUPPORTED

router = APIRouter(prefix="/documents", tags=["Documents"])

_COLS = """id, title, filename, file_type, file_size, classification, department, status, error, version,
           total_pages, total_chunks, uploaded_by, created_at, updated_at"""


def _json(r) -> dict:
    return {k: v for k, v in dict(r).items() if k not in ("storage_path",)}


async def _visible(p, user: Identity, doc_id: str):
    """Fetch a document only if this user may see it."""
    r = await p.fetchrow(f"select {_COLS}, storage_path from documents where id=? and tenant_id=?", doc_id, user.tenant_id)
    if not r or not can_read(user.role, r["classification"]):
        raise HTTPException(404, "Document not found")  # 404, not 403: do not reveal that it exists
    if r["status"] != "ready" and user.role != "admin" and r["uploaded_by"] != user.id:
        raise HTTPException(404, "Document not found")
    return r


def _can_manage(user: Identity, r) -> bool:
    return user.role == "admin" or (r["uploaded_by"] == user.id and can_upload(user.role, r["classification"]))


@router.get("")
async def list_documents(user: Identity = Depends(current_identity)):
    p = await pool()
    readable = [c for c in CLASSIFICATIONS if user.role in roles_for_classification(c)]
    marks = ",".join("?" * len(readable))
    rows = await p.fetch(
        f"""select {_COLS} from documents
            where tenant_id=? and classification in ({marks})
              and (status='ready' or ?='admin' or uploaded_by=?)
            order by created_at desc""",
        user.tenant_id, *readable, user.role, user.id,
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
        if settings.INLINE_PROCESSING:
            await ingestion.process_document(doc_id, data, user)
        else:
            background.add_task(ingestion.process_document, doc_id, data, user)
    p = await pool()
    row = await p.fetchrow(f"select {_COLS} from documents where id=?", doc_id)
    return {**_json(row), "duplicate": duplicate}


@router.get("/{doc_id}")
async def get_document(doc_id: str, user: Identity = Depends(current_identity)):
    p = await pool()
    r = await _visible(p, user, doc_id)
    chunks = await p.fetch(
        "select chunk_index, page, section, kind, content from chunks where document_id=? order by chunk_index", doc_id)
    return {**_json(r), "can_manage": _can_manage(user, r), "excerpts": chunks}


@router.get("/{doc_id}/download")
async def download(doc_id: str, user: Identity = Depends(current_identity)):
    """Returns a one-minute link for this one file (the browser opens it in a new tab, without the session token)."""
    p = await pool()
    r = await _visible(p, user, doc_id)
    if r["status"] != "ready" or not r["storage_path"]:
        raise HTTPException(409, "The original file is not available")
    await audit.log_event(user, "document.download", detail=dict(document_id=doc_id))
    token = issue_token(user.id, purpose="download", seconds=60, doc=doc_id)
    return {"url": f"/api/v1/documents/{doc_id}/file?token={token}", "expires_in": 60}


@router.get("/{doc_id}/file")
async def file(doc_id: str, token: str = Query(...)):
    try:
        claims = decode_token(token, purpose="download")
    except Exception:
        raise HTTPException(403, "This download link has expired. Download the file again.")
    if claims.get("doc") != doc_id:
        raise HTTPException(403, "Invalid download link")
    p = await pool()
    who = await p.fetchrow("select role, tenant_id, is_active from profiles where id=?", claims["sub"])
    r = await p.fetchrow("select filename, classification, tenant_id, storage_path from documents where id=?", doc_id)
    if not who or not who["is_active"] or not r or r["tenant_id"] != who["tenant_id"] \
            or not can_read(who["role"], r["classification"]) or not r["storage_path"]:
        raise HTTPException(404, "Document not found")  # access is re-checked at download time
    try:
        data = await run_in_threadpool(storage.get, r["storage_path"])
    except (OSError, ValueError):
        raise HTTPException(404, "The original file is not available")
    safe = r["filename"].replace('"', "")
    return Response(data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{safe}"', "Cache-Control": "no-store"})


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
        "update documents set title=coalesce(?,title), classification=coalesce(?,classification), "
        "department=coalesce(?,department), updated_at=? where id=?",  # trigger re-labels chunk ACLs atomically
        changes.get("title"), changes.get("classification"), changes.get("department"), now(), doc_id,
    )
    if "classification" in changes:
        await audit.log_event(user, "document.reclassify", detail=dict(
            document_id=doc_id, **{"from": r["classification"], "to": changes["classification"]}))
    row = await p.fetchrow(f"select {_COLS} from documents where id=?", doc_id)
    return _json(row)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, user: Identity = Depends(current_identity)):
    p = await pool()
    r = await _visible(p, user, doc_id)
    if not _can_manage(user, r):
        raise HTTPException(403, "You cannot delete this document")
    await p.execute("delete from documents where id=?", doc_id)  # chunks cascade: instantly unsearchable
    if r["storage_path"]:
        try:
            await run_in_threadpool(storage.delete, r["storage_path"])
        except Exception:  # noqa: BLE001 - an orphaned file is harmless; DB rows are already gone
            pass
    await audit.log_event(user, "document.delete", detail=dict(document_id=doc_id, filename=r["filename"]))
