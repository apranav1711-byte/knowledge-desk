-- Knowledge Desk — core schema (tenants, profiles/roles, documents, chunks, audit, feedback)
-- Security model:
--   * Supabase Auth owns identities. Authorization data (tenant, role, active flag) lives ONLY in public.profiles,
--     never in user-editable JWT metadata.
--   * RLS is enabled on every table. Browser clients get read-only, role-filtered access; every write goes through
--     the backend (service connection), which also enforces the same ACL predicate before retrieval.
--   * Internal functions live in the non-exposed `private` schema.

create extension if not exists vector with schema extensions;
create extension if not exists pgcrypto with schema extensions;

create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated, service_role;

-- ---------------------------------------------------------------------------------------------------------------
-- Tenants & profiles
-- ---------------------------------------------------------------------------------------------------------------
create table public.tenants (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  created_at timestamptz not null default now()
);
insert into public.tenants (id, name)
values ('00000000-0000-0000-0000-000000000001', 'Default organization')
on conflict (id) do nothing;

create table public.profiles (
  id         uuid primary key references auth.users (id) on delete cascade,
  tenant_id  uuid not null references public.tenants (id),
  email      text not null,
  full_name  text not null default '',
  department text not null default '',
  role       text not null check (role in ('employee', 'manager', 'hr', 'admin')),
  is_active  boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index profiles_tenant_idx on public.profiles (tenant_id);
create unique index profiles_tenant_email_uq on public.profiles (tenant_id, lower(email));

-- ---------------------------------------------------------------------------------------------------------------
-- Permission lattice (single source of truth; mirrors backend/app/core/acl.py)
-- ---------------------------------------------------------------------------------------------------------------
create or replace function private.roles_for_classification(p_classification text)
returns text[]
language sql
immutable
set search_path = ''
as $$
  select case p_classification
    when 'Public'           then array['employee', 'manager', 'hr', 'admin']
    when 'General_Internal' then array['employee', 'manager', 'hr', 'admin']
    when 'Management'       then array['manager', 'admin']
    when 'HR_Confidential'  then array['hr', 'admin']
    when 'Restricted'       then array['admin']
    else array[]::text[]
  end
$$;

-- Helpers used by RLS policies. SECURITY DEFINER so they can read profiles without recursive RLS;
-- they live in `private` (not exposed through the Data API) and only reveal the caller's own attributes.
create or replace function private.current_tenant()
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
  select p.tenant_id from public.profiles p where p.id = (select auth.uid()) and p.is_active
$$;

create or replace function private.current_role()
returns text
language sql
stable
security definer
set search_path = ''
as $$
  select p.role from public.profiles p where p.id = (select auth.uid()) and p.is_active
$$;

revoke all on function private.current_tenant() from public, anon;
revoke all on function private.current_role() from public, anon;
grant execute on function private.current_tenant() to authenticated;
grant execute on function private.current_role() to authenticated;

-- ---------------------------------------------------------------------------------------------------------------
-- Documents & chunks
-- ---------------------------------------------------------------------------------------------------------------
create table public.documents (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references public.tenants (id),
  title          text not null,
  filename       text not null,
  file_type      text not null,
  file_size      bigint not null,
  checksum       text not null,
  classification text not null check (classification in
                   ('Public', 'General_Internal', 'Management', 'HR_Confidential', 'Restricted')),
  department     text not null default '',
  status         text not null default 'processing'
                   check (status in ('processing', 'ready', 'failed', 'retired')),
  error          text,
  version        int not null default 1,
  storage_path   text,
  total_pages    int not null default 0,
  total_chunks   int not null default 0,
  uploaded_by    uuid references public.profiles (id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (tenant_id, checksum)
);
create index documents_tenant_status_idx on public.documents (tenant_id, status);
create index documents_uploaded_by_idx on public.documents (uploaded_by);

create table public.chunks (
  id            uuid primary key default gen_random_uuid(),
  document_id   uuid not null references public.documents (id) on delete cascade,
  tenant_id     uuid not null references public.tenants (id),
  chunk_index   int not null,
  page          int not null default 1,
  section       text not null default '',
  kind          text not null default 'text' check (kind in ('text', 'table')),
  content       text not null,
  token_count   int not null default 0,
  classification text not null,
  allowed_roles text[] not null,
  embedding     extensions.vector (384) not null,
  fts           tsvector generated always as (to_tsvector('english', content)) stored
);
create index chunks_document_idx on public.chunks (document_id);
create index chunks_tenant_idx on public.chunks (tenant_id);
create index chunks_allowed_roles_idx on public.chunks using gin (allowed_roles);
create index chunks_fts_idx on public.chunks using gin (fts);
create index chunks_embedding_hnsw on public.chunks using hnsw (embedding extensions.vector_cosine_ops);

-- Changing a document's classification must immediately change who can retrieve its chunks.
create or replace function private.sync_chunk_acl()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.classification is distinct from old.classification then
    update public.chunks
       set classification = new.classification,
           allowed_roles  = private.roles_for_classification(new.classification)
     where document_id = new.id;
  end if;
  new.updated_at := now();
  return new;
end
$$;
create trigger documents_sync_chunk_acl
  before update on public.documents
  for each row execute function private.sync_chunk_acl();

-- ---------------------------------------------------------------------------------------------------------------
-- Tamper-evident audit chain (per tenant, serialised with an advisory lock so it is safe across workers)
-- ---------------------------------------------------------------------------------------------------------------
create table public.audit_logs (
  id          uuid primary key,
  tenant_id   uuid not null references public.tenants (id),
  seq         bigint not null,
  user_id     uuid,
  user_email  text not null default '',
  user_role   text not null default '',
  event       text not null,
  query       text not null default '',
  answer      text not null default '',
  mode        text not null default '',
  chunk_ids   uuid[] not null default '{}',
  top_score   double precision not null default 0,
  latency_ms  int not null default 0,
  detail      jsonb not null default '{}'::jsonb,
  prev_hash   text not null,
  record_hash text not null,
  created_at  timestamptz not null,
  unique (tenant_id, seq)
);
create index audit_logs_tenant_created_idx on public.audit_logs (tenant_id, created_at desc);

create or replace function private.audit_digest(
  p_prev text, p_id uuid, p_tenant uuid, p_seq bigint, p_user uuid, p_event text, p_query text, p_answer text,
  p_mode text, p_chunk_ids uuid[], p_score double precision, p_latency int, p_detail jsonb, p_created timestamptz)
returns text
language sql
immutable
set search_path = public, extensions
as $$
  select encode(
    digest(
      p_prev || jsonb_build_object(
        'id', p_id, 'tenant_id', p_tenant, 'seq', p_seq, 'user_id', p_user, 'event', p_event,
        'query', p_query, 'answer', p_answer, 'mode', p_mode, 'chunk_ids', to_jsonb(p_chunk_ids),
        'score', p_score, 'latency_ms', p_latency, 'detail', p_detail,
        'created_us', floor(extract(epoch from p_created) * 1000000)
      )::text,
      'sha256'),
    'hex')
$$;

create or replace function private.append_audit(
  p_tenant uuid, p_user uuid, p_email text, p_role text, p_event text, p_query text, p_answer text,
  p_mode text, p_chunk_ids uuid[], p_score double precision, p_latency int, p_detail jsonb)
returns uuid
language plpgsql
set search_path = public, extensions
as $$
declare
  v_prev text;
  v_seq  bigint;
  v_id   uuid := gen_random_uuid();
  v_ts   timestamptz := date_trunc('milliseconds', clock_timestamp());
begin
  perform pg_advisory_xact_lock(hashtextextended('audit:' || p_tenant::text, 0));
  select a.seq, a.record_hash into v_seq, v_prev
    from public.audit_logs a where a.tenant_id = p_tenant order by a.seq desc limit 1;
  v_seq  := coalesce(v_seq, 0) + 1;
  v_prev := coalesce(v_prev, repeat('0', 64));
  insert into public.audit_logs (id, tenant_id, seq, user_id, user_email, user_role, event, query, answer, mode,
                                 chunk_ids, top_score, latency_ms, detail, prev_hash, record_hash, created_at)
  values (v_id, p_tenant, v_seq, p_user, coalesce(p_email, ''), coalesce(p_role, ''), p_event,
          coalesce(p_query, ''), coalesce(p_answer, ''), coalesce(p_mode, ''), coalesce(p_chunk_ids, '{}'),
          coalesce(p_score, 0), coalesce(p_latency, 0), coalesce(p_detail, '{}'::jsonb), v_prev,
          private.audit_digest(v_prev, v_id, p_tenant, v_seq, p_user, p_event, coalesce(p_query, ''),
                               coalesce(p_answer, ''), coalesce(p_mode, ''), coalesce(p_chunk_ids, '{}'),
                               coalesce(p_score, 0), coalesce(p_latency, 0), coalesce(p_detail, '{}'::jsonb), v_ts),
          v_ts);
  return v_id;
end
$$;

-- Walks one tenant's chain: contiguous sequence numbers, prev-hash linkage, recomputed record hashes.
create or replace function private.verify_audit(p_tenant uuid)
returns table (valid boolean, checked bigint, broken_seq bigint, reason text)
language plpgsql
stable
set search_path = public, extensions
as $$
declare
  r record;
  v_prev text := repeat('0', 64);
  v_expect bigint := 1;
  v_count bigint := 0;
begin
  for r in select * from public.audit_logs a where a.tenant_id = p_tenant order by a.seq loop
    v_count := v_count + 1;
    if r.seq <> v_expect then
      return query select false, v_count, v_expect, 'Missing record in sequence'::text; return;
    end if;
    if r.prev_hash <> v_prev then
      return query select false, v_count, r.seq, 'Chain linkage mismatch'::text; return;
    end if;
    if r.record_hash <> private.audit_digest(r.prev_hash, r.id, r.tenant_id, r.seq, r.user_id, r.event, r.query,
         r.answer, r.mode, r.chunk_ids, r.top_score, r.latency_ms, r.detail, r.created_at) then
      return query select false, v_count, r.seq, 'Record content was modified'::text; return;
    end if;
    v_prev := r.record_hash;
    v_expect := v_expect + 1;
  end loop;
  return query select true, v_count, null::bigint, null::text;
end
$$;

-- Append-only: no UPDATE or DELETE on audit rows, for any role.
create or replace function private.audit_immutable()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'audit_logs is append-only';
end
$$;
create trigger audit_logs_no_update before update on public.audit_logs
  for each row execute function private.audit_immutable();
create trigger audit_logs_no_delete before delete on public.audit_logs
  for each row execute function private.audit_immutable();

-- ---------------------------------------------------------------------------------------------------------------
-- Feedback
-- ---------------------------------------------------------------------------------------------------------------
create table public.feedback (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references public.tenants (id),
  audit_id   uuid not null references public.audit_logs (id),
  user_id    uuid not null references public.profiles (id) on delete cascade,
  rating     smallint not null check (rating in (-1, 1)),
  comment    text,
  created_at timestamptz not null default now(),
  unique (audit_id, user_id)
);
create index feedback_user_idx on public.feedback (user_id);
create index feedback_tenant_idx on public.feedback (tenant_id);
create index feedback_audit_idx on public.feedback (audit_id);

-- ---------------------------------------------------------------------------------------------------------------
-- Hybrid retrieval with PRE-retrieval access filtering.
-- The tenant + role predicate is inside the candidate query itself, so unauthorised chunks are never ranked,
-- scored, fused or returned. Dense (pgvector cosine) and lexical (full-text) rankings are fused with RRF (k=60).
-- ---------------------------------------------------------------------------------------------------------------
create or replace function private.match_chunks(
  p_embedding extensions.vector (384), p_query text, p_tenant uuid, p_roles text[], p_k int default 8)
returns table (
  chunk_id uuid, document_id uuid, title text, page int, section text, kind text, content text,
  classification text, dense_score double precision, lexical_score double precision, rrf_score double precision)
language sql
stable
set search_path = public, extensions
as $$
  with q as (
    select case when numnode(websearch_to_tsquery('english', p_query)) = 0 then null
                else replace(websearch_to_tsquery('english', p_query)::text, '&', '|')::tsquery end as tsq
  ),
  eligible as not materialized (
    select c.id, c.document_id, c.page, c.section, c.kind, c.content, c.classification, c.embedding, c.fts, d.title
      from public.chunks c
      join public.documents d on d.id = c.document_id
     where c.tenant_id = p_tenant
       and c.allowed_roles && p_roles
       and d.status = 'ready'
  ),
  dense as (
    select e.id, row_number() over (order by e.embedding <=> p_embedding) as rnk
      from eligible e order by e.embedding <=> p_embedding limit 24
  ),
  lex as (
    select e.id, row_number() over (order by ts_rank_cd(e.fts, q.tsq) desc) as rnk
      from eligible e, q where q.tsq is not null and e.fts @@ q.tsq
     order by ts_rank_cd(e.fts, q.tsq) desc limit 24
  ),
  fused as (
    select coalesce(d.id, l.id) as id,
           coalesce(1.0 / (60 + d.rnk), 0) + coalesce(1.0 / (60 + l.rnk), 0) as rrf
      from dense d full join lex l on l.id = d.id
  )
  select e.id, e.document_id, e.title, e.page, e.section, e.kind, e.content, e.classification,
         (1 - (e.embedding <=> p_embedding))::double precision,
         coalesce((select ts_rank_cd(e.fts, q.tsq) from q where q.tsq is not null), 0)::double precision,
         f.rrf::double precision
    from fused f join eligible e on e.id = f.id
   order by f.rrf desc
   limit p_k
$$;

-- Private functions are for the backend service connection only.
revoke all on all functions in schema private from public, anon, authenticated;
grant execute on function private.current_tenant() to authenticated;
grant execute on function private.current_role() to authenticated;
grant execute on function private.roles_for_classification(text) to authenticated;
grant execute on all functions in schema private to service_role;

-- ---------------------------------------------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------------------------------------------
alter table public.tenants    enable row level security;
alter table public.profiles   enable row level security;
alter table public.documents  enable row level security;
alter table public.chunks     enable row level security;
alter table public.audit_logs enable row level security;
alter table public.feedback   enable row level security;

revoke all on public.tenants, public.profiles, public.documents, public.chunks, public.audit_logs, public.feedback
  from anon, authenticated;
grant select on public.profiles, public.documents, public.chunks, public.audit_logs, public.feedback to authenticated;
grant insert on public.feedback to authenticated;

create policy profiles_select on public.profiles for select to authenticated
  using (id = (select auth.uid())
         or (tenant_id = (select private.current_tenant()) and (select private.current_role()) = 'admin'));

create policy documents_select on public.documents for select to authenticated
  using (tenant_id = (select private.current_tenant())
         and (select private.current_role()) = any (private.roles_for_classification(classification))
         and (status = 'ready' or (select private.current_role()) = 'admin'));

create policy chunks_select on public.chunks for select to authenticated
  using (tenant_id = (select private.current_tenant())
         and (select private.current_role()) = any (allowed_roles));

create policy audit_select_admin on public.audit_logs for select to authenticated
  using (tenant_id = (select private.current_tenant()) and (select private.current_role()) = 'admin');

create policy feedback_select_own on public.feedback for select to authenticated
  using (user_id = (select auth.uid()));
create policy feedback_insert_own on public.feedback for insert to authenticated
  with check (user_id = (select auth.uid()) and tenant_id = (select private.current_tenant()));

-- ---------------------------------------------------------------------------------------------------------------
-- Private storage bucket for original files (no policies => only the backend's service key can read/write)
-- ---------------------------------------------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit)
values ('documents', 'documents', false, 26214400)
on conflict (id) do nothing;
