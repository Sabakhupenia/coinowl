"""Personality-wrap LLM helper for v0.7.3 alert and scheduled-push delivery.

When the watcher fires a price alert or drains a batch of scheduled summaries,
the raw numbers go through a one-shot LLM call here to get a warm 1-3 sentence
opener that references the user's `original_phrasing`. The numbers themselves
are formatted deterministically by the caller and appended below the opener.

This is NOT a user-initiated LLM call — it should not count against the user's
quota. Tool-calling is intentionally disabled; the model just writes text.
Falls back through OpenAI → Gemini → a templated default so a push always
gets out even if both providers are down.
"""

from __future__ import annotations

import openai
from google import genai
from google.genai import types as genai_types

from coinowl.core.logging import get_logger

log = get_logger(__name__)


_PERSONALITY_SYSTEM = (
    "You are CoinOwl 🦉, a friendly Telegram crypto stats bot. You are delivering "
    "a notification the user previously asked you to set up. Write ONLY a warm, "
    "conversational opener (1-3 sentences) that:\n"
    "  • References what the user originally asked for (\"as you asked\", \"like "
    "    you wanted\", \"the check you set up\")\n"
    "  • Names what's happening briefly (a price crossed, a daily summary is ready)\n"
    "  • Sounds like a continuation of a past conversation, not a robot beep\n"
    "\n"
    "Reply in the SAME LANGUAGE the user originally used (English, Georgian "
    "ქართული, or Russian).\n"
    "\n"
    "Output ONLY the opener — no markdown (no **bold**, no `code`, no bullets), "
    "no quotation marks around it, no disclaimers, no financial advice. The "
    "exact numbers will be appended automatically by the bot below your opener, "
    "so do NOT include prices or percentages yourself — just the human-feeling "
    "opener."
)


class PersonalityWrapper:
    def __init__(
        self,
        *,
        openai_api_key: str | None,
        gemini_api_key: str,
        openai_model: str = "gpt-5.4-mini",
        gemini_model: str = "gemini-2.5-flash",
    ) -> None:
        self._openai = (
            openai.AsyncOpenAI(api_key=openai_api_key) if openai_api_key else None
        )
        self._gemini = genai.Client(api_key=gemini_api_key)
        self._openai_model = openai_model
        self._gemini_model = gemini_model

    async def compose_alert_opener(
        self,
        *,
        original_phrasing: str,
        symbol: str,
        direction: str,
        threshold: float,
        current_price: float,
    ) -> str:
        prompt = (
            f"The user originally asked: \"{original_phrasing}\"\n"
            f"Their {symbol} alert just fired — price went {direction} the threshold of "
            f"${threshold:,.2f}. Current {symbol} price: ${current_price:,.2f}."
        )
        opener = await self._generate(prompt)
        if opener:
            return opener
        return self._fallback_alert(symbol=symbol, direction=direction)

    async def compose_batch_opener(self, items: list[dict]) -> str:
        """`items` is a list of {"original_phrasing": str, "tool_name": str,
        "fired_at": isoformat-string}. The opener should acknowledge that the
        user has returned and these were waiting."""
        if not items:
            return ""
        lines = ["The user just opened the chat. While they were away, the "
                 "following scheduled checks fired and need delivering:"]
        for i, item in enumerate(items, 1):
            lines.append(
                f"  ({i}) original ask: \"{item.get('original_phrasing', '')}\" "
                f"— scheduled tool: {item.get('tool_name', 'unknown')}"
            )
        lines.append(
            "\nWrite a single warm opener that welcomes them back and briefly "
            "names each thing waiting (you can group them naturally — don't "
            "just list them mechanically). The detailed data will follow below "
            "your opener; do NOT include any specific numbers."
        )
        opener = await self._generate("\n".join(lines))
        if opener:
            return opener
        return self._fallback_batch(len(items))

    async def _generate(self, prompt: str) -> str:
        if self._openai is not None:
            try:
                resp = await self._openai.chat.completions.create(
                    model=self._openai_model,
                    messages=[
                        {"role": "system", "content": _PERSONALITY_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    max_completion_tokens=300,
                )
                text = (resp.choices[0].message.content or "").strip()
                if text:
                    return text
            except Exception as exc:  # noqa: BLE001
                log.warning("personality OpenAI call failed: {}", exc)
        try:
            resp = await self._gemini.aio.models.generate_content(
                model=self._gemini_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_PERSONALITY_SYSTEM,
                    max_output_tokens=300,
                ),
            )
            text = (resp.text or "").strip()
            if text:
                return text
        except Exception as exc:  # noqa: BLE001
            log.warning("personality Gemini call failed: {}", exc)
        return ""

    @staticmethod
    def _fallback_alert(*, symbol: str, direction: str) -> str:
        word = "crossed above" if direction == "above" else "dipped below"
        return f"🦉 Heads up — {symbol} just {word} your alert threshold."

    @staticmethod
    def _fallback_batch(count: int) -> str:
        if count == 1:
            return "🦉 Welcome back — one scheduled check is waiting for you."
        return f"🦉 Welcome back — {count} scheduled checks are waiting for you."
