"""Administrator-only: user management, audit trail, analytics, ACL self-test."""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.api.v1.schemas import UserCreate, UserPatch
from app.core.acl import ALL_ROLES, can_read
from app.core.auth import Identity, require_roles
from app.core.db import pool, vec
from app.services import audit, supabase_admin
from app.services.embeddings import get_embedder

router = APIRouter(prefix="/admin", tags=["Administration"])
admin_only = require_roles("admin")


def _user_json(r) -> dict:
    d = dict(r)
    d["id"] = str(d["id"])
    return d


# --------------------------------------------------------------------------------------------- users
@router.get("/users")
async def list_users(admin: Identity = Depends(admin_only)):
    p = await pool()
    rows = await p.fetch(
        "select id, email, full_name, department, role, is_active, created_at from public.profiles "
        "where tenant_id=$1::uuid order by created_at", admin.tenant_id,
    )
    return [_user_json(r) for r in rows]


@router.post("/users", status_code=201)
async def create_user(body: UserCreate, admin: Identity = Depends(admin_only)):
    p = await pool()
    if await p.fetchval("select 1 from public.profiles where tenant_id=$1::uuid and lower(email)=lower($2)",
                        admin.tenant_id, body.email):
        raise HTTPException(409, "A user with this email already exists")
    user_id = await supabase_admin.create_auth_user(body.email, body.password, body.full_name)
    try:
        await p.execute(
            "insert into public.profiles (id, tenant_id, email, full_name, department, role) "
            "values ($1::uuid,$2::uuid,$3,$4,$5,$6)",
            user_id, admin.tenant_id, body.email, body.full_name, body.department, body.role,
        )
    except Exception:
        await supabase_admin.delete_auth_user(user_id)  # do not leave an un-provisioned login behind
        raise HTTPException(500, "Could not provision the user")
    await audit.log_event(admin, "user.create", detail=dict(user_id=user_id, email=body.email, role=body.role,
                                                           invited=body.password is None))
    row = await p.fetchrow("select id, email, full_name, department, role, is_active, created_at from public.profiles "
                           "where id=$1::uuid", user_id)
    return {**_user_json(row), "invited": body.password is None}


@router.patch("/users/{user_id}")
async def patch_user(user_id: str, body: UserPatch, admin: Identity = Depends(admin_only)):
    p = await pool()
    try:
        target = await p.fetchrow("select * from public.profiles where id=$1::uuid and tenant_id=$2::uuid",
                                  user_id, admin.tenant_id)
    except Exception:
        raise HTTPException(404, "User not found")
    if not target:
        raise HTTPException(404, "User not found")
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(422, "Nothing to change")
    losing_admin = target["role"] == "admin" and target["is_active"] and (
        changes.get("role", "admin") != "admin" or changes.get("is_active", True) is False)
    if losing_admin:
        others = await p.fetchval("select count(*) from public.profiles where tenant_id=$1::uuid and role='admin' "
                                  "and is_active and id<>$2::uuid", admin.tenant_id, user_id)
        if others == 0:
            raise HTTPException(409, "At least one active administrator must remain")
    await p.execute(
        "update public.profiles set full_name=coalesce($2,full_name), department=coalesce($3,department), "
        "role=coalesce($4,role), is_active=coalesce($5,is_active), updated_at=now() where id=$1::uuid",
        user_id, changes.get("full_name"), changes.get("department"), changes.get("role"), changes.get("is_active"),
    )
    if "is_active" in changes:
        await supabase_admin.set_user_banned(user_id, not changes["is_active"])
    await audit.log_event(admin, "user.update", detail=dict(user_id=user_id, **{
        k: v for k, v in changes.items() if k in ("role", "is_active")}))
    row = await p.fetchrow("select id, email, full_name, department, role, is_active, created_at from public.profiles "
                           "where id=$1::uuid", user_id)
    return _user_json(row)


# --------------------------------------------------------------------------------------------- audit
@router.get("/audit")
async def audit_log(
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), event: str | None = Query(None, max_length=40),
    admin: Identity = Depends(admin_only),
):
    p = await pool()
    rows = await p.fetch(
        "select id, seq, user_email, user_role, event, query, mode, latency_ms, detail, record_hash, created_at "
        "from public.audit_logs where tenant_id=$1::uuid and ($2::text is null or event=$2) "
        "order by seq desc limit $3 offset $4", admin.tenant_id, event, limit, offset,
    )
    total = await p.fetchval("select count(*) from public.audit_logs where tenant_id=$1::uuid and ($2::text is null or event=$2)",
                             admin.tenant_id, event)
    items = []
    for r in rows:
        d = dict(r)
        d["id"] = str(d["id"])
        d["detail"] = json.loads(d["detail"]) if isinstance(d["detail"], str) else d["detail"]
        items.append(d)
    return {"total": total, "items": items}


@router.get("/audit/verify")
async def audit_verify(admin: Identity = Depends(admin_only)):
    return await audit.verify(admin.tenant_id)


# --------------------------------------------------------------------------------------------- analytics
@router.get("/analytics")
async def analytics(admin: Identity = Depends(admin_only)):
    p, t = await pool(), admin.tenant_id
    kpi = await p.fetchrow(
        """select count(*) filter (where event='query' and created_at > now() - interval '30 days') as queries_30d,
                  count(*) filter (where event='query' and mode='extractive_answer' and created_at > now() - interval '30 days') as answered_30d,
                  count(*) filter (where event='query' and mode='fallback' and created_at > now() - interval '30 days') as fallback_30d,
                  count(*) filter (where event='query' and created_at > now() - interval '24 hours') as queries_24h,
                  coalesce(avg(latency_ms) filter (where event='query' and created_at > now() - interval '30 days'),0) as avg_latency,
                  coalesce(percentile_cont(0.95) within group (order by latency_ms)
                           filter (where event='query' and created_at > now() - interval '30 days'),0) as p95_latency,
                  count(*) filter (where event='acl.violation') as acl_violations
           from public.audit_logs where tenant_id=$1::uuid""", t)
    docs = await p.fetch("select status, classification, count(*) n from public.documents where tenant_id=$1::uuid group by 1,2", t)
    users = await p.fetch("select role, is_active, count(*) n from public.profiles where tenant_id=$1::uuid group by 1,2", t)
    series = await p.fetch(
        """select d::date as day,
                  count(a.*) filter (where a.mode='extractive_answer') as answered,
                  count(a.*) filter (where a.mode='fallback') as fallback
           from generate_series(current_date - 13, current_date, interval '1 day') d
           left join public.audit_logs a on a.tenant_id=$1::uuid and a.event='query' and a.created_at::date = d::date
           group by 1 order by 1""", t)
    by_role = await p.fetch("select user_role role, count(*) n from public.audit_logs where tenant_id=$1::uuid and event='query' group by 1", t)
    fb = await p.fetchrow("select count(*) filter (where rating=1) up, count(*) filter (where rating=-1) down from public.feedback where tenant_id=$1::uuid", t)
    top = await p.fetch(
        "select query, count(*) n from public.audit_logs where tenant_id=$1::uuid and event='query' and created_at > now() - interval '30 days' "
        "group by 1 order by n desc, max(created_at) desc limit 8", t)
    total_chunks = await p.fetchval("select coalesce(sum(total_chunks),0) from public.documents where tenant_id=$1::uuid and status='ready'", t)
    q = kpi["queries_30d"] or 0
    return dict(
        kpis=dict(
            queries_30d=q, queries_24h=kpi["queries_24h"], answered_30d=kpi["answered_30d"], fallback_30d=kpi["fallback_30d"],
            answer_rate=round(kpi["answered_30d"] / q, 3) if q else None, avg_latency_ms=round(float(kpi["avg_latency"])),
            p95_latency_ms=round(float(kpi["p95_latency"])), acl_violations=kpi["acl_violations"],
            indexed_passages=int(total_chunks), feedback_up=fb["up"], feedback_down=fb["down"]),
        documents=[dict(status=r["status"], classification=r["classification"], count=r["n"]) for r in docs],
        users=[dict(role=r["role"], active=r["is_active"], count=r["n"]) for r in users],
        timeseries=[dict(day=r["day"].isoformat(), answered=r["answered"], fallback=r["fallback"]) for r in series],
        queries_by_role=[dict(role=r["role"], count=r["n"]) for r in by_role],
        top_queries=[dict(query=r["query"], count=r["n"]) for r in top],
    )


# --------------------------------------------------------------------------------------------- ACL self-test
@router.post("/security-check")
async def security_check(admin: Identity = Depends(admin_only)):
    """For every ready document, probe retrieval AS EACH ROLE using that document's own text and verify nothing
    outside the role's clearance is ever returned. Reports exact trial counts and any leak."""
    p = await pool()
    docs = await p.fetch(
        """select d.id, d.title, d.classification,
                  (select c.content from public.chunks c where c.document_id=d.id order by c.chunk_index limit 1) as probe
           from public.documents d where d.tenant_id=$1::uuid and d.status='ready' limit 40""", admin.tenant_id)
    embedder = get_embedder()
    trials, leaks, per_role = 0, [], {r: dict(trials=0, leaks=0) for r in ALL_ROLES}
    for d in docs:
        probe = " ".join(((d["title"] or "") + " " + (d["probe"] or "")).split()[:40])
        qv = vec(await run_in_threadpool(embedder.embed_query, probe))
        for role in ALL_ROLES:
            rows = await p.fetch("select chunk_id, classification from private.match_chunks($1::extensions.vector,$2,$3::uuid,$4::text[],10)",
                                 qv, probe, admin.tenant_id, [role])
            trials += 1
            per_role[role]["trials"] += 1
            bad = [r for r in rows if not can_read(role, r["classification"])]
            if bad:
                per_role[role]["leaks"] += 1
                leaks.append(dict(role=role, document=d["title"], leaked_classifications=sorted({b["classification"] for b in bad})))
    await audit.log_event(admin, "security.check", detail=dict(trials=trials, leaks=len(leaks)))
    return dict(trials=trials, leaks=len(leaks), per_role=per_role, failures=leaks, documents_probed=len(docs),
                ran_at=datetime.utcnow().isoformat() + "Z")
