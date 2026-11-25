"""Administrator-only: user management, audit trail, analytics, ACL self-test."""
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.api.v1.schemas import UserCreate, UserPatch
from app.core.acl import ALL_ROLES, can_read
from app.core.auth import Identity, hash_password, require_roles
from app.core.db import new_id, now, pool
from app.services import audit
from app.services.embeddings import get_embedder

router = APIRouter(prefix="/admin", tags=["Administration"])
admin_only = require_roles("admin")


_USER_COLS = "id, email, full_name, department, role, is_active, created_at"


def _user_json(r) -> dict:
    d = dict(r)
    d["is_active"] = bool(d["is_active"])
    return d


def _ago(**kw) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat(timespec="microseconds")


# --------------------------------------------------------------------------------------------- users
@router.get("/users")
async def list_users(admin: Identity = Depends(admin_only)):
    p = await pool()
    rows = await p.fetch(f"select {_USER_COLS} from profiles where tenant_id=? order by created_at", admin.tenant_id)
    return [_user_json(r) for r in rows]


@router.post("/users", status_code=201)
async def create_user(body: UserCreate, admin: Identity = Depends(admin_only)):
    p = await pool()
    if await p.fetchval("select 1 from profiles where lower(email)=lower(?)", body.email):
        raise HTTPException(409, "A user with this email already exists")
    user_id, ts = new_id(), now()
    await p.execute(
        "insert into profiles (id, tenant_id, email, full_name, department, role, password_hash, created_at, updated_at) "
        "values (?,?,?,?,?,?,?,?,?)",
        user_id, admin.tenant_id, body.email, body.full_name, body.department, body.role,
        hash_password(body.password), ts, ts,
    )
    await audit.log_event(admin, "user.create", detail=dict(user_id=user_id, email=body.email, role=body.role))
    row = await p.fetchrow(f"select {_USER_COLS} from profiles where id=?", user_id)
    return {**_user_json(row), "invited": False}


@router.patch("/users/{user_id}")
async def patch_user(user_id: str, body: UserPatch, admin: Identity = Depends(admin_only)):
    p = await pool()
    target = await p.fetchrow("select * from profiles where id=? and tenant_id=?", user_id, admin.tenant_id)
    if not target:
        raise HTTPException(404, "User not found")
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(422, "Nothing to change")
    losing_admin = target["role"] == "admin" and target["is_active"] and (
        changes.get("role", "admin") != "admin" or changes.get("is_active", True) is False)
    if losing_admin:
        others = await p.fetchval("select count(*) from profiles where tenant_id=? and role='admin' "
                                  "and is_active and id<>?", admin.tenant_id, user_id)
        if others == 0:
            raise HTTPException(409, "At least one active administrator must remain")
    active = changes.get("is_active")
    await p.execute(
        "update profiles set full_name=coalesce(?,full_name), department=coalesce(?,department), "
        "role=coalesce(?,role), is_active=coalesce(?,is_active), password_hash=coalesce(?,password_hash), "
        "updated_at=? where id=?",
        changes.get("full_name"), changes.get("department"), changes.get("role"),
        None if active is None else int(active), hash_password(changes["password"]) if "password" in changes else None,
        now(), user_id,
    )
    await audit.log_event(admin, "user.update", detail=dict(user_id=user_id, **{
        k: v for k, v in changes.items() if k in ("role", "is_active")}, password_reset="password" in changes))
    row = await p.fetchrow(f"select {_USER_COLS} from profiles where id=?", user_id)
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
        "from audit_logs where tenant_id=? and (? is null or event=?) order by seq desc limit ? offset ?",
        admin.tenant_id, event, event, limit, offset,
    )
    total = await p.fetchval("select count(*) from audit_logs where tenant_id=? and (? is null or event=?)",
                             admin.tenant_id, event, event)
    return {"total": total, "items": [{**r, "detail": json.loads(r["detail"] or "{}")} for r in rows]}


@router.get("/audit/verify")
async def audit_verify(admin: Identity = Depends(admin_only)):
    return await audit.verify(admin.tenant_id)


# --------------------------------------------------------------------------------------------- analytics
@router.get("/analytics")
async def analytics(admin: Identity = Depends(admin_only)):
    p, t = await pool(), admin.tenant_id
    d30, d1 = _ago(days=30), _ago(hours=24)
    kpi = await p.fetchrow(
        """select coalesce(sum(event='query' and created_at > ?),0) queries_30d,
                  coalesce(sum(event='query' and mode='extractive_answer' and created_at > ?),0) answered_30d,
                  coalesce(sum(event='query' and mode='fallback' and created_at > ?),0) fallback_30d,
                  coalesce(sum(event='query' and created_at > ?),0) queries_24h,
                  coalesce(sum(event='acl.violation'),0) acl_violations
           from audit_logs where tenant_id=?""", d30, d30, d30, d1, t)
    lat = sorted(r["latency_ms"] for r in await p.fetch(
        "select latency_ms from audit_logs where tenant_id=? and event='query' and created_at > ?", t, d30))
    avg_latency = sum(lat) / len(lat) if lat else 0
    p95_latency = lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))] if lat else 0
    docs = await p.fetch("select status, classification, count(*) n from documents where tenant_id=? group by 1,2", t)
    users = await p.fetch("select role, is_active, count(*) n from profiles where tenant_id=? group by 1,2", t)
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    per_day = {r["day"]: r for r in await p.fetch(
        "select substr(created_at,1,10) day, sum(mode='extractive_answer') answered, sum(mode='fallback') fallback "
        "from audit_logs where tenant_id=? and event='query' and created_at >= ? group by 1", t, days[0].isoformat())}
    by_role = await p.fetch("select user_role role, count(*) n from audit_logs where tenant_id=? and event='query' group by 1", t)
    fb = await p.fetchrow("select coalesce(sum(rating=1),0) up, coalesce(sum(rating=-1),0) down from feedback where tenant_id=?", t)
    top = await p.fetch(
        "select query, count(*) n from audit_logs where tenant_id=? and event='query' and created_at > ? "
        "group by 1 order by n desc, max(created_at) desc limit 8", t, d30)
    total_chunks = await p.fetchval("select coalesce(sum(total_chunks),0) from documents where tenant_id=? and status='ready'", t)
    q = kpi["queries_30d"] or 0
    return dict(
        kpis=dict(
            queries_30d=q, queries_24h=kpi["queries_24h"], answered_30d=kpi["answered_30d"], fallback_30d=kpi["fallback_30d"],
            answer_rate=round(kpi["answered_30d"] / q, 3) if q else None, avg_latency_ms=round(avg_latency),
            p95_latency_ms=round(p95_latency), acl_violations=kpi["acl_violations"],
            indexed_passages=int(total_chunks), feedback_up=fb["up"], feedback_down=fb["down"]),
        documents=[dict(status=r["status"], classification=r["classification"], count=r["n"]) for r in docs],
        users=[dict(role=r["role"], active=bool(r["is_active"]), count=r["n"]) for r in users],
        timeseries=[dict(day=d.isoformat(), answered=(per_day.get(d.isoformat()) or {}).get("answered") or 0,
                         fallback=(per_day.get(d.isoformat()) or {}).get("fallback") or 0) for d in days],
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
                  (select c.content from chunks c where c.document_id=d.id order by c.chunk_index limit 1) as probe
           from documents d where d.tenant_id=? and d.status='ready' limit 40""", admin.tenant_id)
    embedder = get_embedder()
    trials, leaks, per_role = 0, [], {r: dict(trials=0, leaks=0) for r in ALL_ROLES}
    for d in docs:
        probe = " ".join(((d["title"] or "") + " " + (d["probe"] or "")).split()[:40])
        qv = await run_in_threadpool(embedder.embed_query, probe)
        for role in ALL_ROLES:
            rows = await p.match_chunks(qv, probe, admin.tenant_id, [role], 10)
            trials += 1
            per_role[role]["trials"] += 1
            bad = [r for r in rows if not can_read(role, r["classification"])]
            if bad:
                per_role[role]["leaks"] += 1
                leaks.append(dict(role=role, document=d["title"], leaked_classifications=sorted({b["classification"] for b in bad})))
    await audit.log_event(admin, "security.check", detail=dict(trials=trials, leaks=len(leaks)))
    return dict(trials=trials, leaks=len(leaks), per_role=per_role, failures=leaks, documents_probed=len(docs),
                ran_at=datetime.utcnow().isoformat() + "Z")
