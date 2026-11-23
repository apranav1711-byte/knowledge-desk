"""Deploy backend to a Hugging Face Docker Space. Usage: python deploy/deploy_hf.py [space-name]
Needs: pip install huggingface_hub ; `hf auth login` with a WRITE token. Secrets are read from backend/.env, never printed."""
import re, shutil, sys, tempfile
from pathlib import Path
from huggingface_hub import HfApi

root = Path(__file__).resolve().parent.parent
name = sys.argv[1] if len(sys.argv) > 1 else "knowledge-desk-api"
frontend = "https://accenture-knowledge-desk.vercel.app"
api = HfApi()
repo = f"{api.whoami()['name']}/{name}"

env = {}
for line in (root / "backend" / ".env").read_text(encoding="utf-8").splitlines():
    m = re.match(r"^\s*([A-Z_]+)\s*=\s*(.*)$", line)
    if m: env[m[1]] = m[2].strip().strip('"\'')
for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "DATABASE_URL"):
    if not env.get(k) or "YOUR-" in env[k]: sys.exit(f"Fill in {k} in backend/.env")

stage = Path(tempfile.mkdtemp())
for d in ("app", "scripts"):
    shutil.copytree(root / "backend" / d, stage / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
shutil.copy(root / "backend" / "requirements.txt", stage)
for f in (root / "deploy" / "hf-space").iterdir(): shutil.copy(f, stage)

api.create_repo(repo, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
secrets = {k: env[k] for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "DATABASE_URL", "SUPABASE_JWT_SECRET", "DEFAULT_TENANT_ID") if env.get(k)}
secrets.update(CORS_ORIGINS=frontend, ENVIRONMENT="production")
for k, v in secrets.items(): api.add_space_secret(repo, k, v)
api.upload_folder(folder_path=str(stage), repo_id=repo, repo_type="space", commit_message="Deploy backend")
shutil.rmtree(stage, ignore_errors=True)
print(f"Space: https://huggingface.co/spaces/{repo}\nAPI URL: https://{repo.replace('/', '-').replace('_', '-').lower()}.hf.space")
