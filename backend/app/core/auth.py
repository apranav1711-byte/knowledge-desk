"""Supabase Auth JWT verification + server-side authorization.

Identity comes from the verified JWT (`sub`). Tenant, role and active flag are read from public.profiles on every
request -- never from token claims -- so role changes and deactivation take effect immediately.
"""
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.db import pool

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Identity:
    id: str
    tenant_id: str
    email: str
    full_name: str
    department: str
    role: str


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json", cache_keys=True)


def decode_token(token: str) -> dict:
    """Verify signature, expiry and audience. Supports asymmetric (JWKS) and legacy HS256 projects."""
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "")
    if alg == "HS256":
        if not settings.SUPABASE_JWT_SECRET:
            raise jwt.InvalidTokenError("HS256 token but SUPABASE_JWT_SECRET is not configured")
        key, algorithms = settings.SUPABASE_JWT_SECRET, ["HS256"]
    elif alg in ("ES256", "RS256"):
        key, algorithms = _jwks_client().get_signing_key_from_jwt(token).key, [alg]
    else:
        raise jwt.InvalidTokenError("Unsupported token algorithm")
    return jwt.decode(token, key, algorithms=algorithms, audience="authenticated", options={"require": ["exp", "sub"]})


async def current_identity(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Identity:
    if not creds:
        raise HTTPException(401, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(401, "Invalid or expired session. Sign in again.", headers={"WWW-Authenticate": "Bearer"})
    p = await pool()
    row = await p.fetchrow(
        "select id, tenant_id, email, full_name, department, role, is_active from public.profiles where id = $1::uuid",
        claims["sub"],
    )
    if row is None:
        raise HTTPException(403, "Your account has not been provisioned. Ask an administrator for access.")
    if not row["is_active"]:
        raise HTTPException(403, "Your account is deactivated.")
    return Identity(str(row["id"]), str(row["tenant_id"]), row["email"], row["full_name"], row["department"], row["role"])


def require_roles(*roles: str):
    async def dep(user: Identity = Depends(current_identity)) -> Identity:
        if user.role not in roles:
            raise HTTPException(403, "Your role does not permit this operation")
        return user

    return dep
