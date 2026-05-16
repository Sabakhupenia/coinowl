"""Chat history persistence + Gemini embedding helper.

Both `log_message` and `embed_text` are best-effort — they log warnings on
failure and never raise, because a failed embedding write must not break the
user-facing chat turn.
"""

from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types as genai_types

from coinowl.core.logging import get_logger
from coinowl.db.pool import pool

log = get_logger(__name__)

_EMBED_MODEL = "gemini-embedding-001"
_EMBED_DIM = 768

_client: genai.Client | None = None


def _init_embedding_client(api_key: str) -> None:
    """Called once at startup with the Gemini API key from settings."""
    global _client
    _client = genai.Client(api_key=api_key)


async def embed_text(text: str) -> list[float] | None:
    """Embed text with Gemini, normalized to 768 dimensions for pgvector ivfflat."""
    if _client is None or not text.strip():
        return None
    try:
        resp = await _client.aio.models.embed_content(
            model=_EMBED_MODEL,
            contents=text,
            config=genai_types.EmbedContentConfig(output_dimensionality=_EMBED_DIM),
        )
        if not resp.embeddings:
            return None
        return list(resp.embeddings[0].values)
    except Exception as exc:  # noqa: BLE001
        log.warning("embed_text failed: {}", exc)
        return None


def _vector_literal(values: list[float] | None) -> str | None:
    if values is None:
        return None
    return "[" + ",".join(f"{v:.7f}" for v in values) + "]"


async def recent_messages(user_id: int, limit: int = 6) -> list[dict[str, Any]]:
    """Return the user's last `limit` chat turns (newest first), as dicts with
    role, content, ts. Cheap timestamp-ordered SQL — no embedding needed."""
    rows = await pool().fetch(
        """
        SELECT role, content, ts
          FROM messages
         WHERE user_id = $1
         ORDER BY ts DESC
         LIMIT $2
        """,
        user_id,
        limit,
    )
    return [dict(r) for r in rows]


async def semantic_recall(
    user_id: int,
    query: str,
    *,
    k: int = 3,
) -> list[dict[str, Any]]:
    """Vector-similarity search over the user's past messages. Embeds the
    query via Gemini, then orders by pgvector cosine distance. Returns
    matching rows with a similarity score in [0, 1]."""
    emb = await embed_text(query)
    if emb is None:
        return []
    emb_lit = _vector_literal(emb)
    try:
        rows = await pool().fetch(
            """
            SELECT role, content, ts,
                   1 - (embedding <=> $2::vector) AS similarity
              FROM messages
             WHERE user_id = $1 AND embedding IS NOT NULL
             ORDER BY embedding <=> $2::vector
             LIMIT $3
            """,
            user_id,
            emb_lit,
            k,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("semantic_recall query failed: {}", exc)
        return []
    return [dict(r) for r in rows]


async def log_message(
    user_id: int,
    role: str,
    content: str,
    *,
    language: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> None:
    """Persist one chat turn. Embeds the content. Never raises."""
    if not content.strip():
        return
    try:
        emb = await embed_text(content)
        emb_lit = _vector_literal(emb)
        tool_calls_json = json.dumps(tool_calls) if tool_calls else None
        await pool().execute(
            """
            INSERT INTO messages
              (user_id, role, content, language, llm_provider, llm_model,
               tool_calls, embedding)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::vector)
            """,
            user_id,
            role,
            content,
            language,
            llm_provider,
            llm_model,
            tool_calls_json,
            emb_lit,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("log_message failed (uid={}, role={}): {}", user_id, role, exc)
