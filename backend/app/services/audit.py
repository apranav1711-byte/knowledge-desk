"""Audit trail writer/reader. Records are SHA-256 hash-chained per tenant (see db.audit_digest); the database
refuses UPDATE/DELETE on audit_logs, and verify() re-computes the whole chain."""
from app.core.auth import Identity
from app.core.db import pool


async def log_event(
    user: Identity | None, event: str, *, tenant_id: str | None = None, query: str = "", answer: str = "",
    mode: str = "", chunk_ids: list[str] | None = None, score: float = 0.0, latency_ms: int = 0,
    detail: dict | None = None,
) -> str:
    p = await pool()
    tenant = tenant_id or (user.tenant_id if user else None)
    return await p.append_audit(tenant, user.id if user else None, user.email if user else "",
                                user.role if user else "", event, query, answer, mode, [str(c) for c in chunk_ids or []],
                                float(score), int(latency_ms), detail or {})


async def verify(tenant_id: str) -> dict:
    p = await pool()
    r = await p.verify_audit(tenant_id)
    return dict(
        tamper_free=r["valid"], records_checked=r["checked"], broken_seq=r["broken_seq"], reason=r["reason"],
        status="SECURE_AND_VERIFIED" if r["valid"] else "TAMPERING_DETECTED",
    )
