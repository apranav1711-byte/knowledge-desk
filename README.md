# Knowledge Desk — secure enterprise knowledge assistant

Role-based RAG over company documents. **No LLM**: answers are extractive, quoted from your documents with citations, and the assistant says so when evidence is missing.

- **Backend:** FastAPI + Supabase (Auth, Postgres/pgvector, Storage)
- **Frontend:** React + Vite dashboard (Overview, Assistant, Documents, Users, Analytics, Audit)
- **Security:** access is enforced *inside the retrieval SQL* (before ranking), with RLS on every table and a runtime re-check. Tamper-evident hash-chained audit log.
- **Parsing:** PDF (tables, headings, optional OCR), DOCX, XLSX, CSV, PPTX, HTML, MD, TXT.

| Role | Can read |
| --- | --- |
| employee | Public, General Internal |
| manager | + Management |
| hr | + HR Confidential (not Management) |
| admin | everything, plus users / audit / analytics |

## Setup

1. **Supabase:** create/restore a project, apply `supabase/migrations/*.sql` (SQL editor or `supabase db push`).
   In Auth → Providers → Email: **disable "Allow new users to sign up"** (admins create accounts).
   Auth → URL config: add your frontend URL as a redirect (needed for invite/reset links).
2. **Backend:**
   ```bash
   cd backend && python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # fill SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, DATABASE_URL (+ SUPABASE_JWT_SECRET only for legacy HS256 projects)
   python -m scripts.bootstrap_admin you@company.com "Your Name"
   uvicorn app.main:app --reload --port 8000
   ```
   First run downloads the embedding model (~130 MB). The service-role key is server-side only — never put it in the frontend.
3. **Frontend:**
   ```bash
   cd frontend && cp .env.example .env   # VITE_SUPABASE_URL, VITE_SUPABASE_PUBLISHABLE_KEY, VITE_API_URL=http://localhost:8000
   npm install && npm run dev
   ```
4. Log in, add users under **Users**, upload files from `backend/sample_uploads` and `backend/demo`, then run **Audit → Security check**.

## Tests
`cd backend && pytest` (22 tests: parsers, ACL truth table, JWT validation, answer guard; uses a hash embedder, no model download).

## Known limits
Scanned PDFs need Tesseract for OCR (otherwise rejected with a clear message). The hash chain cannot detect deletion of the newest records without an external checkpoint. Extractive answers quote passages; they don't synthesize across documents.
