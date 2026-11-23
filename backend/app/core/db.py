"""asyncpg pool for the Supabase Postgres connection."""
import asyncpg

from app.core.config import settings

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        # statement_cache_size=0 keeps this compatible with Supabase's transaction pooler (pgbouncer).
        _pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=10, statement_cache_size=0)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def pool() -> asyncpg.Pool:
    return await init_pool()


def vec(values) -> str:
    """pgvector text literal."""
    return "[" + ",".join(f"{float(v):.6f}" for v in values) + "]"
