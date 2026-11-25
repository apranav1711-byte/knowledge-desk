"""Document lifecycle: upload -> store original -> parse -> chunk -> embed -> index -> ready (or failed).

Chunks are written in ONE transaction together with the status flip to 'ready', and retrieval only considers
documents with status='ready' -- so a crash mid-way can never expose partial content.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
import logging
import re
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.core.acl import roles_for_classification
from app.core.auth import Identity
from app.core.db import new_id, now, pool, vec
from app.services import audit, storage
from app.services.chunking import chunk_blocks
from app.services.embeddings import get_embedder
from app.services.parsing import ParseError, parse_document

log = logging.getLogger("knowledge.ingestion")


def safe_name(filename: str) -> str:
    name = Path(filename.replace("\\", "/")).name
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:200] or "document"


async def register_upload(user: Identity, filename: str, data: bytes, classification: str, department: str):
    """Create the document row (idempotent on checksum). Returns (document_id, duplicate_of_existing)."""
    p = await pool()
    checksum = hashlib.sha256(data).hexdigest()
    existing = await p.fetchrow(
        "select id, status from documents where tenant_id=? and checksum=?", user.tenant_id, checksum
    )
    if existing and existing["status"] in ("ready", "processing"):
        return str(existing["id"]), True
    name = safe_name(filename)
    if existing:  # failed/retired earlier: reuse the row and retry
        await p.execute(
            "update documents set status='processing', error=null, classification=?, filename=?, department=?, "
            "uploaded_by=?, updated_at=? where id=?",
            classification, name, department, user.id, now(), existing["id"],
        )
        return str(existing["id"]), False
    doc_id, ts = new_id(), now()
    await p.execute(
        """insert into documents (id, tenant_id, title, filename, file_type, file_size, checksum, classification,
                                  department, status, uploaded_by, created_at, updated_at)
           values (?,?,?,?,?,?,?,?,?,'processing',?,?,?)""",
        doc_id, user.tenant_id, Path(name).stem.replace("_", " ").replace("-", " ").strip() or name, name,
        Path(name).suffix.lstrip(".").lower(), len(data), checksum, classification, department, user.id, ts, ts,
    )
    return str(doc_id), False


async def process_document(doc_id: str, data: bytes, user: Identity) -> None:
    """Background job. Never raises: failures are recorded on the document."""
    p = await pool()
    try:
        row = await p.fetchrow("select filename, classification, tenant_id from documents where id=?", doc_id)
        tenant, name, classification = str(row["tenant_id"]), row["filename"], row["classification"]
        storage_path = f"{tenant}/{doc_id}/{name}"
        await run_in_threadpool(storage.put, storage_path, data)

        parsed = await run_in_threadpool(parse_document, name, data)
        chunks = chunk_blocks(parsed.title, parsed.blocks)
        if not chunks:
            raise ParseError("No searchable content was found in the document.")
        embedder = get_embedder()
        vectors = await run_in_threadpool(embedder.embed_passages, [c.embed_text for c in chunks])
        roles = roles_for_classification(classification)

        async with p.acquire() as conn:
            async with conn.transaction():
                await conn.execute("delete from chunks where document_id=?", doc_id)
                await conn.executemany(
                    """insert into chunks (id, document_id, tenant_id, chunk_index, page, section, kind, content,
                                           token_count, classification, allowed_roles, embedding)
                       values (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [(new_id(), doc_id, tenant, c.index, c.page, c.section, c.kind, c.content, c.tokens, classification,
                      json.dumps(roles), vec(v)) for c, v in zip(chunks, vectors)],
                )
                await conn.execute(
                    """update documents set status='ready', error=null, title=?, total_pages=?,
                              total_chunks=?, storage_path=?, updated_at=? where id=?""",
                    parsed.title, parsed.pages, len(chunks), storage_path, now(), doc_id,
                )
        await audit.log_event(user, "document.upload", detail=dict(
            document_id=doc_id, filename=name, classification=classification, chunks=len(chunks), pages=parsed.pages,
            warnings=parsed.warnings))
    except ParseError as exc:
        await _fail(doc_id, str(exc), user)
    except Exception as exc:  # noqa: BLE001 - surfaced to admins as a bounded message, details in logs
        log.exception("ingestion failed for %s", doc_id)
        await _fail(doc_id, f"Indexing failed ({type(exc).__name__}). Retry the upload; incomplete content is not searchable.", user)


async def _fail(doc_id: str, message: str, user: Identity) -> None:
    p = await pool()
    await p.execute("update documents set status='failed', error=?, updated_at=? where id=?",
                    message[:400], now(), doc_id)
    try:
        await audit.log_event(user, "document.failed", detail=dict(document_id=doc_id, error=message[:200]))
    except Exception:  # noqa: BLE001
        log.exception("could not audit ingestion failure")


async def recover_stuck_documents() -> int:
    """On startup: documents left in 'processing' by a crashed worker are marked failed (and stay unsearchable)."""
    p = await pool()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="microseconds")
    return await p.execute(
        "update documents set status='failed', error='Processing was interrupted. Upload the file again.' "
        "where status='processing' and updated_at < ?", cutoff)
