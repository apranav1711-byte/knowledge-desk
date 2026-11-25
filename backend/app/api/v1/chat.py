import time

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from app.api.v1.schemas import FeedbackIn, Question
from app.core.acl import can_read
from app.core.auth import Identity, current_identity
from app.core.config import settings
from app.core.db import new_id, now, pool
from app.services import audit
from app.services.answer import build_answer
from app.services.embeddings import get_embedder

router = APIRouter(tags=["Assistant"])


@router.post("/chat/query")
async def query(body: Question, user: Identity = Depends(current_identity)):
    started = time.perf_counter()
    embedder = get_embedder()
    qvec = await run_in_threadpool(embedder.embed_query, body.query)
    embed_ms = round((time.perf_counter() - started) * 1000)

    p = await pool()
    t1 = time.perf_counter()
    # PRE-retrieval filtering: tenant + role are part of the candidate query inside the database.
    rows = await p.match_chunks(qvec, body.query, user.tenant_id, [user.role], 10)
    retrieval_ms = round((time.perf_counter() - t1) * 1000)
    hits = [dict(r) for r in rows]
    # Defence in depth: fail closed if anything unauthorised ever reached this point.
    violations = [h for h in hits if not can_read(user.role, h["classification"])]
    if violations:
        await audit.log_event(user, "acl.violation", query=body.query, detail=dict(count=len(violations)))
        hits = [h for h in hits if can_read(user.role, h["classification"])]

    answer = build_answer(body.query, hits)
    elapsed = round((time.perf_counter() - started) * 1000)
    audit_id = await audit.log_event(
        user, "query", query=body.query, answer=answer.text, mode=answer.mode,
        chunk_ids=[s["chunk_id"] for s in answer.sources], score=answer.sources[0]["score"] if answer.sources else 0.0,
        latency_ms=elapsed, detail=dict(reason=answer.reason, candidates=len(hits)),
    )
    return dict(
        answer=answer.text, mode=answer.mode, reason=answer.reason, sources=answer.sources, audit_id=audit_id,
        telemetry=dict(
            embedding_ms=embed_ms, retrieval_ms=retrieval_ms, total_ms=elapsed, candidates=len(hits),
            role=user.role, embedding_model=embedder.name, retrieval="hybrid dense+lexical RRF, pre-filtered by role",
            answer_stage="extractive-evidence-v1",
        ),
    )


@router.get("/chat/history")
async def history(user: Identity = Depends(current_identity)):
    p = await pool()
    rows = await p.fetch(
        "select id, query, mode, created_at from audit_logs where tenant_id=? and user_id=? "
        "and event='query' order by seq desc limit 30", user.tenant_id, user.id,
    )
    return [dict(id=str(r["id"]), query=r["query"], mode=r["mode"], created_at=r["created_at"]) for r in rows]


@router.post("/feedback", status_code=201)
async def feedback(body: FeedbackIn, user: Identity = Depends(current_identity)):
    p = await pool()
    owner = await p.fetchrow("select user_id, tenant_id from audit_logs where id=?", body.audit_id)
    if not owner or owner["user_id"] != user.id or owner["tenant_id"] != user.tenant_id:
        raise HTTPException(404, "Answer not found")  # only feedback on your own answers
    await p.execute(
        "insert into feedback (id, tenant_id, audit_id, user_id, rating, comment, created_at) values (?,?,?,?,?,?,?) "
        "on conflict (audit_id, user_id) do update set rating=excluded.rating, comment=excluded.comment",
        new_id(), user.tenant_id, body.audit_id, user.id, body.rating, body.comment, now(),
    )
    return {"ok": True}
