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
    # Pool tuning for Supabase Session Pooler:
    # - statement_cache_size=0 — pgbouncer (which Supabase uses) doesn't share
    #   prepared statements across pooled clients; disabling avoids "prepared
    #   statement does not exist" errors.
    # - max_inactive_connection_lifetime=60 — Supabase closes idle server-side
    #   connections within a few minutes; recycling our pool every 60s prevents
    #   us from handing out a stale connection mid-query (ConnectionDoesNotExistError).
    # - command_timeout=15 — bound the wait if Supabase wedges so we fail fast
    #   instead of leaving the chat handler hung.
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=5,
        statement_cache_size=0,
        max_inactive_connection_lifetime=60.0,
        command_timeout=15.0,
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
