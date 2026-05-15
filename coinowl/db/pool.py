"""Module-level asyncpg pool singleton + lifecycle."""

from __future__ import annotations

import asyncpg

from coinowl.core.logging import get_logger
from coinowl.db.migrate import apply_migrations

log = get_logger(__name__)

_pool: asyncpg.Pool | None = None


async def init_db(dsn: str) -> None:
    global _pool
    if _pool is not None:
        return
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=5,
        statement_cache_size=0,  # Supabase pgbouncer transaction mode is unforgiving; safe default
    )
    log.info("Postgres pool ready")
    await apply_migrations(_pool)


async def close_db() -> None:
    global _pool
    if _pool is None:
        return
    await _pool.close()
    _pool = None
    log.info("Postgres pool closed")


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized — call init_db() first")
    return _pool
