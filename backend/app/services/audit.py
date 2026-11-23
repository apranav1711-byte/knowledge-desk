"""Audit trail writer/reader. Hash-chaining is done inside Postgres (private.append_audit / verify_audit) under a
per-tenant advisory lock, so it stays correct with multiple API workers."""
import json
from uuid import UUID

from app.core.auth import Identity
from app.core.db import pool


async def log_event(
    user: Identity | None, event: str, *, tenant_id: str | None = None, query: str = "", answer: str = "",
    mode: str = "", chunk_ids: list[str] | None = None, score: float = 0.0, latency_ms: int = 0,
    detail: dict | None = None,
) -> str:
    p = await pool()
    tenant = tenant_id or (user.tenant_id if user else None)
    row = await p.fetchval(
        "select private.append_audit($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8,$9::uuid[],$10,$11,$12::jsonb)",
        tenant, user.id if user else None, user.email if user else "", user.role if user else "", event, query,
        answer, mode, [UUID(c) for c in (chunk_ids or [])], float(score), int(latency_ms), json.dumps(detail or {}),
    )
    return str(row)


async def verify(tenant_id: str) -> dict:
    p = await pool()
    r = await p.fetchrow("select * from private.verify_audit($1::uuid)", tenant_id)
    return dict(
        tamper_free=r["valid"], records_checked=r["checked"], broken_seq=r["broken_seq"], reason=r["reason"],
        status="SECURE_AND_VERIFIED" if r["valid"] else "TAMPERING_DETECTED",
    )
