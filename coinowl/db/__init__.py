"""Database layer — asyncpg pool, versioned migrations, DAOs.

`init_db()` must be awaited once at startup before any DAO function is called.
`close_db()` drains the pool on shutdown.
"""

from coinowl.db.pool import init_db, close_db, pool

__all__ = ["init_db", "close_db", "pool"]
