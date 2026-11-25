"""Local accounts: scrypt password hashes + short-lived signed session tokens (HS256).

Identity comes from the verified token (`sub`). Tenant, role and active flag are read from the profiles table on
every request -- never from token claims -- so role changes and deactivation take effect immediately.
"""
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.db import pool

bearer = HTTPBearer(auto_error=False)
AUDIENCE = "knowledge-desk"


@dataclass(frozen=True)
class Identity:
    id: str
    tenant_id: str
    email: str
    full_name: str
    department: str
    role: str


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc.hex(), digest)
    except Exception:  # noqa: BLE001 - malformed hash = no match
        return False


# ------------------------------------------------------------------ tokens
@lru_cache(maxsize=1)
def signing_key() -> str:
    if settings.JWT_SECRET:
        return settings.JWT_SECRET
    path = settings.DATA_DIR / "jwt_secret"
    if not path.exists():
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def issue_token(sub: str, purpose: str = "session", seconds: int | None = None, **extra) -> str:
    now = int(time.time())
    exp = now + (seconds if seconds is not None else settings.SESSION_HOURS * 3600)
    return jwt.encode({"sub": sub, "aud": AUDIENCE, "purpose": purpose, "iat": now, "exp": exp, **extra},
                      signing_key(), algorithm="HS256")


def decode_token(token: str, purpose: str = "session") -> dict:
    """Verify signature, expiry, audience and purpose (a download link can never be used as a session)."""
    claims = jwt.decode(token, signing_key(), algorithms=["HS256"], audience=AUDIENCE,
                        options={"require": ["exp", "sub", "aud"]})
    if claims.get("purpose") != purpose:
        raise jwt.InvalidTokenError("wrong token purpose")
    return claims


async def current_identity(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Identity:
    if not creds:
        raise HTTPException(401, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(401, "Invalid or expired session. Sign in again.", headers={"WWW-Authenticate": "Bearer"})
    p = await pool()
    row = await p.fetchrow(
        "select id, tenant_id, email, full_name, department, role, is_active from profiles where id = ?", claims["sub"])
    if row is None:
        raise HTTPException(401, "Invalid or expired session. Sign in again.", headers={"WWW-Authenticate": "Bearer"})
    if not row["is_active"]:
        raise HTTPException(403, "Your account is deactivated.")
    return Identity(row["id"], row["tenant_id"], row["email"], row["full_name"], row["department"], row["role"])


def require_roles(*roles: str):
    async def dep(user: Identity = Depends(current_identity)) -> Identity:
        if user.role not in roles:
            raise HTTPException(403, "Your role does not permit this operation")
        return user

    return dep
