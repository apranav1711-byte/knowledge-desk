# Knowledge Desk — secure enterprise knowledge assistant

Role-based search over company documents. **No LLM**: answers are quoted from your documents with citations, and the assistant says so when evidence is missing.

- **Website (online):** https://knowledgedesk.vercel.app — the React frontend, deployed on Vercel from `frontend/`.
- **Backend (this PC only):** FastAPI on `http://localhost:8000`. Everything stays on this computer in `backend/data/`:
  the SQLite database, uploaded files, and the key that signs sign-in sessions. No cloud database or storage.
- **Security:** role filtering happens inside the database query, before ranking, with a re-check afterwards. Passwords are
  hashed with scrypt, sign-ins are rate-limited, download links expire after 60 seconds, and the audit log is hash-chained
  (tamper-evident) and append-only.
- **Parsing:** PDF, DOCX, XLSX, CSV, PPTX, HTML, Markdown, TXT, up to 25 MB per file.

| Role | Can read |
| --- | --- |
| employee | Public, General Internal |
| manager | + Management |
| hr | + HR Confidential (not Management) |
| admin | everything, plus users / audit / analytics |

## Use it

1. Double-click **`start-knowledge-desk.cmd`** (or run `.\start-knowledge-desk.ps1`). Keep that window open.
   The first run installs Python packages (a few minutes).
2. The website opens. Sign in. If Chrome asks to let the site access devices on your local network, choose **Allow**:
   that is how the website reaches the backend on your PC.
3. Close the window (or press Ctrl+C) to stop. The website only works on this PC while the backend is running.

**First administrator** (run once):
```powershell
cd backend
.venv\Scripts\python -m scripts.bootstrap_admin you@company.com "Your Name"
```
The password goes to `backend\data\initial-admin-password.txt`. Sign in, change it (click your initials, top right),
then delete that file. Admins add other users, and reset forgotten passwords, under **Users**.

**Backup:** copy the `backend\data` folder while the backend is stopped.

## Develop

```powershell
cd backend; .venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
cd frontend; npm install; npm run dev      # http://localhost:5173
cd backend; .venv\Scripts\python -m pip install -r requirements-local.txt; .venv\Scripts\python -m pytest
```
Pushing to `main` redeploys the website on Vercel. Its `VITE_API_URL` is `http://localhost:8000`.
