"""Per-user message quota — in-memory rolling window.

Resets on bot restart. Intentional: no DB yet.
Postgres persistence lands with the semantic RAG commit.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

_WINDOW = timedelta(hours=3)
_LIMIT = 10


class QuotaTracker:
    def __init__(self) -> None:
        self._log: dict[int, deque[datetime]] = defaultdict(deque)

    def check_and_consume(self, user_id: int) -> tuple[bool, int]:
        """Return (allowed, remaining). Consumes one slot when allowed."""
        now = datetime.now(tz=timezone.utc)
        dq = self._log[user_id]
        cutoff = now - _WINDOW
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= _LIMIT:
            return False, 0
        dq.append(now)
        return True, _LIMIT - len(dq)
