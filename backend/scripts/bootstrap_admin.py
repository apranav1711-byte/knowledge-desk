"""Create an administrator account in the local database.

    cd backend
    .venv\\Scripts\\python -m scripts.bootstrap_admin you@company.com "Your Name"

A random password is generated and written to data/initial-admin-password.txt (never printed).
Sign in with it, change it from the account menu, then delete that file.
"""
import asyncio
import secrets
import sys

from app.core.auth import hash_password
from app.core.config import settings
from app.core.db import DEFAULT_TENANT, close_pool, new_id, now, pool


async def main(email: str, name: str) -> None:
    p = await pool()
    if await p.fetchval("select 1 from profiles where lower(email)=lower(?)", email):
        sys.exit("That user already exists.")
    password = secrets.token_urlsafe(14)
    ts = now()
    await p.execute(
        "insert into profiles (id, tenant_id, email, full_name, department, role, password_hash, created_at, updated_at) "
        "values (?,?,?,?,'Administration','admin',?,?,?)",
        new_id(), DEFAULT_TENANT, email, name, hash_password(password), ts, ts)
    out = settings.DATA_DIR / "initial-admin-password.txt"
    out.write_text(password, encoding="utf-8")
    print(f"Admin created: {email}\nPassword saved to: {out}")
    await close_pool()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
