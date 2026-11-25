"""Sign-in and password change for local accounts."""
import asyncio
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.schemas import LoginIn, PasswordChange
from app.core.auth import Identity, current_identity, hash_password, issue_token, verify_password
from app.core.config import settings
from app.core.db import now, pool
from app.services import audit

router = APIRouter(prefix="/auth", tags=["Auth"])

_failures: dict[str, deque] = defaultdict(deque)  # email -> timestamps of recent failed attempts
_WINDOW, _MAX_FAILS = 15 * 60, 10
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


def _throttled(email: str) -> bool:
    q, cutoff = _failures[email], time.time() - _WINDOW
    while q and q[0] < cutoff:
        q.popleft()
    return len(q) >= _MAX_FAILS


@router.post("/login")
async def login(body: LoginIn):
    email = body.email.lower()
    if _throttled(email):
        raise HTTPException(429, "Too many failed attempts. Wait 15 minutes and try again.")
    p = await pool()
    row = await p.fetchrow("select * from profiles where lower(email) = ?", email)
    ok = verify_password(body.password, row["password_hash"] if row else _DUMMY_HASH)  # same cost either way
    if not row or not ok:
        _failures[email].append(time.time())
        await asyncio.sleep(0.4)
        raise HTTPException(401, "Incorrect email or password.")
    if not row["is_active"]:
        raise HTTPException(403, "Your account is deactivated.")
    _failures.pop(email, None)
    return {"access_token": issue_token(row["id"]), "token_type": "bearer", "expires_in": settings.SESSION_HOURS * 3600}


@router.post("/password")
async def change_password(body: PasswordChange, user: Identity = Depends(current_identity)):
    p = await pool()
    stored = await p.fetchval("select password_hash from profiles where id = ?", user.id)
    if not verify_password(body.current_password, stored or ""):
        raise HTTPException(400, "Your current password is incorrect.")
    await p.execute("update profiles set password_hash = ?, updated_at = ? where id = ?",
                    hash_password(body.new_password), now(), user.id)
    await audit.log_event(user, "user.password_change")
    return {"ok": True}
