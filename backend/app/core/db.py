"""Local SQLite database: one file on this PC (data/knowledge.db). No server, nothing to install.

Statements run in a worker thread under a lock (SQLite allows one writer). `async with (await pool()).acquire()`
holds the lock across several statements, which is how multi-statement transactions stay atomic.
Embeddings are stored as float32 blobs; retrieval (vector + full-text) runs in Python over rows that were already
filtered by tenant and role inside the SQL query, so unauthorised content is never even loaded.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import numpy as np
from starlette.concurrency import run_in_threadpool

from app.core.acl import PERMISSION_MATRIX
from app.core.config import settings

DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_id() -> str:
    return str(uuid.uuid4())


def vec(values) -> bytes:
    return np.asarray(values, dtype=np.float32).tobytes()


def _roles_case(col: str) -> str:
    """SQL CASE mirroring acl.PERMISSION_MATRIX, used by the re-classification trigger."""
    from app.core.acl import roles_for_classification

    whens = " ".join(f"when '{c}' then '{json.dumps(roles_for_classification(c))}'" for c in PERMISSION_MATRIX)
    return f"case {col} {whens} else '[]' end"


SCHEMA = f"""
create table if not exists tenants (
  id text primary key, name text not null, created_at text not null);

create table if not exists profiles (
  id text primary key,
  tenant_id text not null references tenants (id),
  email text not null,
  full_name text not null default '',
  department text not null default '',
  role text not null check (role in ('employee', 'manager', 'hr', 'admin')),
  is_active integer not null default 1,
  password_hash text not null,
  created_at text not null,
  updated_at text not null);
create unique index if not exists profiles_tenant_email_uq on profiles (tenant_id, lower(email));

create table if not exists documents (
  id text primary key,
  tenant_id text not null references tenants (id),
  title text not null,
  filename text not null,
  file_type text not null,
  file_size integer not null,
  checksum text not null,
  classification text not null check (classification in
    ('Public', 'General_Internal', 'Management', 'HR_Confidential', 'Restricted')),
  department text not null default '',
  status text not null default 'processing' check (status in ('processing', 'ready', 'failed', 'retired')),
  error text,
  version integer not null default 1,
  storage_path text,
  total_pages integer not null default 0,
  total_chunks integer not null default 0,
  uploaded_by text references profiles (id) on delete set null,
  created_at text not null,
  updated_at text not null,
  unique (tenant_id, checksum));
create index if not exists documents_tenant_status_idx on documents (tenant_id, status);

create table if not exists chunks (
  id text primary key,
  document_id text not null references documents (id) on delete cascade,
  tenant_id text not null references tenants (id),
  chunk_index integer not null,
  page integer not null default 1,
  section text not null default '',
  kind text not null default 'text' check (kind in ('text', 'table')),
  content text not null,
  token_count integer not null default 0,
  classification text not null,
  allowed_roles text not null,
  embedding blob not null);
create index if not exists chunks_document_idx on chunks (document_id);
create index if not exists chunks_tenant_idx on chunks (tenant_id);

create virtual table if not exists chunks_fts using fts5 (content, chunk_id unindexed, tokenize = 'porter unicode61');
create trigger if not exists chunks_fts_ins after insert on chunks begin
  insert into chunks_fts (content, chunk_id) values (new.content, new.id);
end;
create trigger if not exists chunks_fts_del after delete on chunks begin
  delete from chunks_fts where chunk_id = old.id;
end;

-- re-classifying a document re-labels its chunks in the same statement (atomic ACL change)
create trigger if not exists documents_sync_chunk_acl after update of classification on documents
when new.classification is not old.classification begin
  update chunks set classification = new.classification, allowed_roles = {_roles_case('new.classification')}
   where document_id = new.id;
end;

create table if not exists audit_logs (
  id text primary key,
  tenant_id text not null references tenants (id),
  seq integer not null,
  user_id text,
  user_email text not null default '',
  user_role text not null default '',
  event text not null,
  query text not null default '',
  answer text not null default '',
  mode text not null default '',
  chunk_ids text not null default '[]',
  top_score real not null default 0,
  latency_ms integer not null default 0,
  detail text not null default '{{}}',
  prev_hash text not null,
  record_hash text not null,
  created_at text not null,
  unique (tenant_id, seq));
create index if not exists audit_logs_tenant_created_idx on audit_logs (tenant_id, created_at);
create trigger if not exists audit_logs_no_update before update on audit_logs begin
  select raise(abort, 'audit_logs is append-only');
end;
create trigger if not exists audit_logs_no_delete before delete on audit_logs begin
  select raise(abort, 'audit_logs is append-only');
end;

create table if not exists feedback (
  id text primary key,
  tenant_id text not null references tenants (id),
  audit_id text not null references audit_logs (id),
  user_id text not null references profiles (id) on delete cascade,
  rating integer not null check (rating in (-1, 1)),
  comment text,
  created_at text not null,
  unique (audit_id, user_id));
"""


class _Conn:
    """Executes on the shared connection. Callers must hold the DB lock (via DB methods or DB.acquire())."""

    def __init__(self, c: sqlite3.Connection):
        self._c = c

    def _run(self, fn):
        return run_in_threadpool(fn)

    async def fetch(self, sql: str, *args) -> list[dict]:
        return await self._run(lambda: [dict(r) for r in self._c.execute(sql, args).fetchall()])

    async def fetchrow(self, sql: str, *args) -> dict | None:
        def f():
            r = self._c.execute(sql, args).fetchone()
            return dict(r) if r else None
        return await self._run(f)

    async def fetchval(self, sql: str, *args):
        def f():
            r = self._c.execute(sql, args).fetchone()
            return r[0] if r else None
        return await self._run(f)

    async def execute(self, sql: str, *args) -> int:
        return await self._run(lambda: self._c.execute(sql, args).rowcount)

    async def executemany(self, sql: str, rows) -> None:
        await self._run(lambda: self._c.executemany(sql, rows))

    @asynccontextmanager
    async def transaction(self):
        await self._run(lambda: self._c.execute("begin immediate"))
        try:
            yield self
        except BaseException:
            await self._run(lambda: self._c.execute("rollback"))
            raise
        await self._run(lambda: self._c.execute("commit"))

    # ---------------------------------------------------------------- retrieval
    async def match_chunks(self, qvec, query: str, tenant: str, roles: list[str], k: int = 8, mode: str = "hybrid") -> list[dict]:
        return await self._run(lambda: _match_chunks(self._c, qvec, query, tenant, roles, k, mode))

    # ---------------------------------------------------------------- audit chain
    async def append_audit(self, tenant: str, user_id: str | None, email: str, role: str, event: str, query: str,
                           answer: str, mode: str, chunk_ids: list[str], score: float, latency: int,
                           detail: dict) -> str:
        def f():
            last = self._c.execute("select seq, record_hash from audit_logs where tenant_id=? order by seq desc limit 1",
                                   (tenant,)).fetchone()
            seq, prev = (last[0] + 1, last[1]) if last else (1, "0" * 64)
            rec = dict(id=new_id(), tenant_id=tenant, seq=seq, user_id=user_id, user_email=email or "",
                       user_role=role or "", event=event, query=query or "", answer=answer or "", mode=mode or "",
                       chunk_ids=json.dumps(chunk_ids), top_score=float(score), latency_ms=int(latency),
                       detail=json.dumps(detail, sort_keys=True, default=str), prev_hash=prev, created_at=now())
            rec["record_hash"] = audit_digest(rec)
            cols = ",".join(rec)
            self._c.execute(f"insert into audit_logs ({cols}) values ({','.join('?' * len(rec))})", tuple(rec.values()))
            return rec["id"]
        return await self._run(f)

    async def verify_audit(self, tenant: str) -> dict:
        def f():
            expect, prev, count = 1, "0" * 64, 0
            for r in self._c.execute("select * from audit_logs where tenant_id=? order by seq", (tenant,)):
                r, count = dict(r), count + 1
                if r["seq"] != expect:
                    return dict(valid=False, checked=count, broken_seq=expect, reason="Missing record in sequence")
                if r["prev_hash"] != prev:
                    return dict(valid=False, checked=count, broken_seq=r["seq"], reason="Chain linkage mismatch")
                if r["record_hash"] != audit_digest(r):
                    return dict(valid=False, checked=count, broken_seq=r["seq"], reason="Record content was modified")
                prev, expect = r["record_hash"], expect + 1
            return dict(valid=True, checked=count, broken_seq=None, reason=None)
        return await self._run(f)


_HASHED = ("id", "tenant_id", "seq", "user_id", "user_email", "user_role", "event", "query", "answer", "mode",
           "chunk_ids", "top_score", "latency_ms", "detail", "prev_hash", "created_at")


def audit_digest(rec: dict) -> str:
    body = json.dumps({k: rec[k] for k in _HASHED}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((rec["prev_hash"] + body).encode()).hexdigest()


def _fts_query(text: str) -> str | None:
    words = sorted({w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1})
    return " OR ".join(f'"{w}"' for w in words) or None


def _match_chunks(c: sqlite3.Connection, qvec, query: str, tenant: str, roles: list[str], k: int, mode: str = "hybrid") -> list[dict]:
    """Hybrid retrieval: dense cosine + BM25 full-text, fused with reciprocal rank fusion (k=60).
    PRE-filtering: only chunks of ready documents in this tenant whose allowed_roles include the caller's role
    are selected from the database at all."""
    marks = ",".join("?" * len(roles)) or "''"
    rows = c.execute(
        f"""select c.id, c.document_id, c.page, c.section, c.kind, c.content, c.classification, c.embedding, d.title
              from chunks c join documents d on d.id = c.document_id
             where c.tenant_id = ? and d.status = 'ready'
               and exists (select 1 from json_each(c.allowed_roles) j where j.value in ({marks}))""",
        (tenant, *roles),
    ).fetchall()
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    mat = np.frombuffer(b"".join(r["embedding"] for r in rows), dtype=np.float32).reshape(len(rows), -1)
    q = np.asarray(qvec, dtype=np.float32)
    sims = mat @ q / ((np.linalg.norm(mat, axis=1) * (np.linalg.norm(q) or 1.0)) + 1e-12)
    dense_rank = {ids[i]: n + 1 for n, i in enumerate(np.argsort(-sims)[:24])}

    lex_score, lex_rank = {}, {}
    fq = _fts_query(query)
    if fq:
        allowed = set(ids)
        hits = c.execute("select chunk_id, bm25(chunks_fts) s from chunks_fts where chunks_fts match ? order by s limit 500",
                         (fq,)).fetchall()
        for cid, s in hits:
            if cid in allowed and len(lex_rank) < 24:
                lex_rank[cid], lex_score[cid] = len(lex_rank) + 1, -float(s)

    if mode == "dense":  # ablations used in the evaluation; production always uses "hybrid"
        lex_rank = {}
    elif mode == "lexical":
        dense_rank = {}
    fused = {i: (1 / (60 + dense_rank[i]) if i in dense_rank else 0) + (1 / (60 + lex_rank[i]) if i in lex_rank else 0)
             for i in set(dense_rank) | set(lex_rank)}
    pos = {cid: n for n, cid in enumerate(ids)}
    out = []
    for cid in sorted(fused, key=fused.get, reverse=True)[:k]:
        r = rows[pos[cid]]
        out.append(dict(chunk_id=cid, document_id=r["document_id"], title=r["title"], page=r["page"],
                        section=r["section"], kind=r["kind"], content=r["content"], classification=r["classification"],
                        dense_score=float(sims[pos[cid]]), lexical_score=lex_score.get(cid, 0.0), rrf_score=fused[cid]))
    return out


class DB:
    def __init__(self, path: str):
        self._c = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._c.row_factory = sqlite3.Row
        for pragma in ("journal_mode=wal", "foreign_keys=on", "busy_timeout=5000", "synchronous=normal"):
            self._c.execute(f"pragma {pragma}")
        self._c.executescript(SCHEMA)
        self._c.execute("insert or ignore into tenants (id, name, created_at) values (?, ?, ?)",
                        (DEFAULT_TENANT, "Default organization", now()))
        self._conn = _Conn(self._c)
        self._lock = None  # created lazily inside the running event loop

    def _get_lock(self):
        import asyncio

        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @asynccontextmanager
    async def acquire(self):
        async with self._get_lock():
            yield self._conn

    def __getattr__(self, name):
        """fetch / fetchrow / fetchval / execute / executemany / match_chunks / append_audit / verify_audit,
        each run atomically under the lock."""
        fn = getattr(self._conn, name)

        async def locked(*args, **kw):
            async with self._get_lock():
                return await fn(*args, **kw)
        return locked

    def close(self) -> None:
        self._c.close()


_db: DB | None = None
_init = threading.Lock()


async def init_pool() -> DB:
    global _db
    with _init:
        if _db is None:
            settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
            _db = DB(str(settings.DATABASE_PATH))
    return _db


async def close_pool() -> None:
    global _db
    if _db is not None:
        _db.close()
        _db = None


async def pool() -> DB:
    return await init_pool()
