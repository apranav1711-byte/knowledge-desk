import time

from fastapi import APIRouter, Depends

from app.core.acl import readable_classifications
from app.core.auth import Identity, current_identity
from app.core.config import settings
from app.core.db import pool

router = APIRouter(tags=["General"])


@router.get("/health")
async def health():
    out = {"status": "healthy", "environment": settings.ENVIRONMENT, "components": {}}
    start = time.perf_counter()
    try:
        p = await pool()
        await p.fetchval("select 1")
        out["components"]["database"] = {"status": "healthy", "engine": "sqlite",
                                         "latency_ms": round((time.perf_counter() - start) * 1000, 1)}
        out["components"]["users"] = await p.fetchval("select count(*) from profiles")
    except Exception:  # noqa: BLE001
        out["status"] = "degraded"
        out["components"]["database"] = {"status": "unreachable"}
    out["components"]["embedding_backend"] = settings.EMBEDDING_BACKEND
    return out


@router.get("/me")
async def me(user: Identity = Depends(current_identity)):
    return dict(
        id=user.id, email=user.email, full_name=user.full_name, department=user.department, role=user.role,
        tenant_id=user.tenant_id, can_read=readable_classifications(user.role),
        permissions=dict(
            upload=user.role != "employee", manage_users=user.role == "admin", view_audit=user.role == "admin",
            view_analytics=user.role == "admin",
        ),
    )
