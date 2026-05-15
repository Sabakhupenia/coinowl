"""Minimal forward-only migration runner.

Reads `migrations/NNN_*.sql` files at the project root and applies any whose
version (the leading integer) isn't yet recorded in `schema_versions`. Each
file runs in its own transaction; on failure the migration is rolled back and
the runner aborts (so a broken migration doesn't half-apply and silently move
on).
"""

from __future__ import annotations

from pathlib import Path

import asyncpg

from coinowl.core.logging import get_logger

log = get_logger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def apply_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_versions (
                version    INT         PRIMARY KEY,
                filename   TEXT        NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        rows = await conn.fetch("SELECT version FROM schema_versions")
        applied = {r["version"] for r in rows}

        pending = []
        for path in sorted(_MIGRATIONS_DIR.glob("[0-9]*.sql")):
            try:
                version = int(path.name.split("_", 1)[0])
            except ValueError:
                log.warning("Skipping migration with non-numeric prefix: {}", path.name)
                continue
            if version in applied:
                continue
            pending.append((version, path))

        if not pending:
            log.info("DB schema up to date")
            return

        for version, path in pending:
            sql = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_versions (version, filename) VALUES ($1, $2)",
                    version,
                    path.name,
                )
            log.info("Applied migration {}: {}", version, path.name)
