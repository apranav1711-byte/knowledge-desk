"""Create the first administrator (run once, after applying the migration).

    cd backend && python -m scripts.bootstrap_admin you@company.com "Your Name"

Prompts for a password (min 10 chars). Needs DATABASE_URL, SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY in backend/.env.
"""
import asyncio
import getpass
import sys

from app.core.db import close_pool, pool
from app.services import supabase_admin

DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"


async def main(email: str, name: str) -> None:
    password = getpass.getpass("Password (min 10 chars): ")
    if len(password) < 10:
        sys.exit("Password too short.")
    p = await pool()
    if await p.fetchval("select 1 from public.profiles where lower(email)=lower($1)", email):
        sys.exit("That user already exists.")
    uid = await supabase_admin.create_auth_user(email, password, name)
    try:
        await p.execute(
            "insert into public.profiles (id, tenant_id, email, full_name, department, role) "
            "values ($1::uuid,$2::uuid,$3,$4,'Administration','admin')", uid, DEFAULT_TENANT, email, name)
    except Exception:
        await supabase_admin.delete_auth_user(uid)
        raise
    print(f"Admin created: {email}")
    await close_pool()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
