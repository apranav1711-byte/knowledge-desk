"""Server-side Supabase Auth admin + Storage calls (service-role key; never exposed to the browser)."""
import httpx
from fastapi import HTTPException

from app.core.config import settings


def _headers() -> dict:
    k = settings.SUPABASE_SERVICE_ROLE_KEY
    return {"apikey": k, "Authorization": f"Bearer {k}"}


def _base() -> str:
    return settings.SUPABASE_URL.rstrip("/")


async def _request(method: str, path: str, **kw) -> httpx.Response:
    async with httpx.AsyncClient(timeout=30) as c:
        return await c.request(method, f"{_base()}{path}", headers={**_headers(), **kw.pop("headers", {})}, **kw)


# ----------------------------- Auth admin -----------------------------
async def create_auth_user(email: str, password: str | None, full_name: str) -> str:
    """With a password: create a confirmed user. Without: send an invite email (needs SMTP/default mailer)."""
    meta = {"full_name": full_name}
    if password:
        r = await _request("POST", "/auth/v1/admin/users",
                           json={"email": email, "password": password, "email_confirm": True, "user_metadata": meta})
    else:
        r = await _request("POST", "/auth/v1/invite", json={"email": email, "data": meta})
    if r.status_code >= 400:
        msg = (r.json() or {}).get("msg") or (r.json() or {}).get("message") or "Could not create the user"
        raise HTTPException(409 if r.status_code in (409, 422) else 502, msg)
    return r.json()["id"]


async def set_user_banned(user_id: str, banned: bool) -> None:
    r = await _request("PUT", f"/auth/v1/admin/users/{user_id}", json={"ban_duration": "876000h" if banned else "none"})
    if r.status_code >= 400:
        raise HTTPException(502, "Could not update the sign-in state in Supabase Auth")


async def delete_auth_user(user_id: str) -> None:
    await _request("DELETE", f"/auth/v1/admin/users/{user_id}")


# ----------------------------- Storage -----------------------------
async def storage_put(path: str, data: bytes, content_type: str) -> None:
    r = await _request("POST", f"/storage/v1/object/{settings.STORAGE_BUCKET}/{path}", content=data,
                       headers={"Content-Type": content_type or "application/octet-stream", "x-upsert": "true"})
    if r.status_code >= 400:
        raise RuntimeError(f"Storage upload failed ({r.status_code})")


async def storage_get(path: str) -> bytes:
    r = await _request("GET", f"/storage/v1/object/{settings.STORAGE_BUCKET}/{path}")
    if r.status_code >= 400:
        raise RuntimeError(f"Storage download failed ({r.status_code})")
    return r.content


async def storage_upload_url(path: str) -> str:
    """One-time signed URL the browser can PUT a file to directly (bypasses the API's request-size limit)."""
    r = await _request("POST", f"/storage/v1/object/upload/sign/{settings.STORAGE_BUCKET}/{path}")
    if r.status_code >= 400:
        raise HTTPException(502, "Could not prepare the upload")
    return f"{_base()}/storage/v1{r.json()['url']}"


async def storage_delete(path: str) -> None:
    await _request("DELETE", f"/storage/v1/object/{settings.STORAGE_BUCKET}/{path}")


async def storage_signed_url(path: str, seconds: int = 60) -> str:
    r = await _request("POST", f"/storage/v1/object/sign/{settings.STORAGE_BUCKET}/{path}", json={"expiresIn": seconds})
    if r.status_code >= 400:
        raise HTTPException(502, "Could not create a download link")
    return f"{_base()}/storage/v1{r.json()['signedURL']}"
