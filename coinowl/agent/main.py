"""CoinOwl LLM agent — Gemini Flash primary, Claude Haiku 4.5 fallback.

Both providers see the same tool surface (`get_price`, `get_market_chart`)
and the same system prompt (see `prompts.SYSTEM_PROMPT`). Each provider runs
its own tool-calling loop; the Agent class orchestrates the fallback chain
and runs an output guardrail before returning.

The tool dispatcher (`execute_tool`) returns dicts rather than raising so the
model can apologize naturally on errors ("I don't recognize 'FOO'") instead
of crashing the whole turn.
"""

from __future__ import annotations

import json
import re
from typing import Any

import anthropic
from google import genai
from google.genai import types as genai_types

from coinowl.agent.prompts import (
    GUARDRAIL_REFUSAL,
    PROVIDER_FAILED,
    SYSTEM_PROMPT,
)
from coinowl.core.logging import get_logger
from coinowl.data.coingecko import (
    ATTRIBUTION,
    CoinGeckoClient,
    CoinGeckoError,
    CoinGeckoRateLimitError,
    CoinGeckoUnknownCoinError,
)
from coinowl.data.symbols import resolve

log = get_logger(__name__)

_GEMINI_MODEL = "gemini-2.5-flash"
_CLAUDE_MODEL = "claude-haiku-4-5"
_MAX_TOOL_ITERATIONS = 5
_MAX_OUTPUT_TOKENS = 2048


# Output guardrail: a deterministic backstop on top of the system prompt's
# "no predictions / no advice" instruction. Catches obvious leak patterns.
_PREDICTION_PATTERNS = [
    re.compile(r"\bwill (reach|hit|go to|be)\b", re.IGNORECASE),
    re.compile(r"\bshould (buy|sell|hold)\b", re.IGNORECASE),
    re.compile(r"\b(i|my)['’]?d? recommend\b", re.IGNORECASE),
    re.compile(r"\bprice target\b", re.IGNORECASE),
    re.compile(r"\bis going to \$", re.IGNORECASE),
]


def passes_guardrail(text: str) -> bool:
    return not any(p.search(text) for p in _PREDICTION_PATTERNS)


# ---------------------------------------------------------------------------
# Tool dispatcher — shared by both providers.
# ---------------------------------------------------------------------------


async def execute_tool(
    tool_name: str, args: dict[str, Any], cg: CoinGeckoClient
) -> dict[str, Any]:
    """Run one tool call and return a JSON-serializable result dict.

    Returning errors as dict payloads (rather than raising) lets the LLM
    surface a natural apology to the user instead of dropping the whole turn.
    """
    if tool_name == "get_price":
        symbol = str(args.get("symbol", "")).strip()
        if not symbol:
            return {"error": "Missing required argument: symbol"}
        coin_id = resolve(symbol)
        try:
            price = await cg.get_price(coin_id)
        except CoinGeckoUnknownCoinError:
            return {"error": f"Unknown coin: {symbol!r}", "symbol": symbol}
        except CoinGeckoRateLimitError:
            return {"error": "CoinGecko is rate-limiting; back off and try later"}
        except CoinGeckoError as exc:
            log.warning("get_price failed for %s: %s", coin_id, exc)
            return {"error": "CoinGecko request failed; try again"}
        return {
            "symbol": symbol.upper(),
            "coin_id": coin_id,
            "price_usd": price,
            "attribution": ATTRIBUTION,
        }

    if tool_name == "get_market_chart":
        symbol = str(args.get("symbol", "")).strip()
        try:
            days = int(args.get("days", 7))
        except (TypeError, ValueError):
            return {"error": "Argument 'days' must be an integer"}
        if not symbol:
            return {"error": "Missing required argument: symbol"}
        if days not in (1, 7, 30, 90):
            days = max(1, min(90, days))  # clamp politely

        coin_id = resolve(symbol)
        try:
            points = await cg.get_market_chart(coin_id, days=days)
        except CoinGeckoUnknownCoinError:
            return {"error": f"Unknown coin: {symbol!r}", "symbol": symbol}
        except CoinGeckoRateLimitError:
            return {"error": "CoinGecko is rate-limiting; back off and try later"}
        except CoinGeckoError as exc:
            log.warning("get_market_chart failed for %s: %s", coin_id, exc)
            return {"error": "CoinGecko request failed; try again"}

        if not points:
            return {"error": "No data returned", "symbol": symbol}

        first, last = points[0], points[-1]
        change_pct = (last.price - first.price) / first.price * 100 if first.price else 0.0
        return {
            "symbol": symbol.upper(),
            "coin_id": coin_id,
            "days": days,
            "first_timestamp": first.timestamp.isoformat(),
            "first_price_usd": first.price,
            "last_timestamp": last.timestamp.isoformat(),
            "last_price_usd": last.price,
            "change_pct": round(change_pct, 2),
            "point_count": len(points),
            "attribution": ATTRIBUTION,
        }

    return {"error": f"Unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# Gemini provider — manual tool-calling loop on the async client.
# ---------------------------------------------------------------------------


_GEMINI_TOOLS = genai_types.Tool(
    function_declarations=[
        genai_types.FunctionDeclaration(
            name="get_price",
            description="Get the current spot price of a cryptocurrency in USD.",
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "symbol": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Ticker (BTC, ETH) or CoinGecko coin id (bitcoin).",
                    ),
                },
                required=["symbol"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="get_market_chart",
            description=(
                "Get historical price points for a cryptocurrency over the last N days. "
                "Returns first/last prices and percent change."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "symbol": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Ticker or CoinGecko coin id.",
                    ),
                    "days": genai_types.Schema(
                        type=genai_types.Type.INTEGER,
                        description="Lookback window: 1, 7, 30, or 90.",
                    ),
                },
                required=["symbol", "days"],
            ),
        ),
    ]
)


class GeminiProvider:
    def __init__(self, api_key: str, coingecko: CoinGeckoClient) -> None:
        self._client = genai.Client(api_key=api_key)
        self._cg = coingecko

    async def chat(self, user_text: str) -> str:
        contents: list[Any] = [
            genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(text=user_text)],
            )
        ]
        config = genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[_GEMINI_TOOLS],
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        )

        for _ in range(_MAX_TOOL_ITERATIONS):
            response = await self._client.aio.models.generate_content(
                model=_GEMINI_MODEL,
                contents=contents,
                config=config,
            )

            candidate = response.candidates[0] if response.candidates else None
            if candidate is None or candidate.content is None:
                return ""

            contents.append(candidate.content)

            fcs = response.function_calls or []
            if not fcs:
                return (response.text or "").strip()

            tool_response_parts: list[Any] = []
            for fc in fcs:
                args = dict(fc.args) if fc.args else {}
                result = await execute_tool(fc.name, args, self._cg)
                tool_response_parts.append(
                    genai_types.Part.from_function_response(
                        name=fc.name,
                        response=result,
                    )
                )
            contents.append(
                genai_types.Content(role="user", parts=tool_response_parts)
            )

        log.warning("Gemini hit max tool iterations")
        return "I got stuck thinking about that. Could you rephrase your question?"


# ---------------------------------------------------------------------------
# Claude provider — manual tool-calling loop on AsyncAnthropic.
# ---------------------------------------------------------------------------


_CLAUDE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_price",
        "description": "Get the current spot price of a cryptocurrency in USD.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker (BTC, ETH) or CoinGecko coin id (bitcoin).",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_market_chart",
        "description": (
            "Get historical price points for a cryptocurrency over the last N days. "
            "Returns first/last prices and percent change."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker or CoinGecko coin id.",
                },
                "days": {
                    "type": "integer",
                    "description": "Lookback window: 1, 7, 30, or 90.",
                },
            },
            "required": ["symbol", "days"],
        },
    },
]


class ClaudeProvider:
    def __init__(self, api_key: str, coingecko: CoinGeckoClient) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._cg = coingecko

    async def chat(self, user_text: str) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_text}
        ]
        # cache_control is forward-compat scaffolding: our system prompt is
        # currently below Haiku's ~4096-token cache minimum, so this is a no-op
        # until the prompt grows.
        system = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        for _ in range(_MAX_TOOL_ITERATIONS):
            response = await self._client.messages.create(
                model=_CLAUDE_MODEL,
                max_tokens=_MAX_OUTPUT_TOKENS,
                system=system,
                tools=_CLAUDE_TOOLS,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                return next(
                    (b.text for b in response.content if b.type == "text"),
                    "",
                ).strip()

            if response.stop_reason != "tool_use":
                log.warning("Claude returned unexpected stop_reason: %s", response.stop_reason)
                return next(
                    (b.text for b in response.content if b.type == "text"),
                    "",
                ).strip()

            messages.append({"role": "assistant", "content": response.content})

            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await execute_tool(block.name, dict(block.input), self._cg)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})

        log.warning("Claude hit max tool iterations")
        return "I got stuck thinking about that. Could you rephrase your question?"


# ---------------------------------------------------------------------------
# Agent — fallback chain + guardrail.
# ---------------------------------------------------------------------------


class Agent:
    def __init__(
        self,
        *,
        gemini_api_key: str,
        anthropic_api_key: str | None,
        coingecko: CoinGeckoClient,
    ) -> None:
        self._gemini = GeminiProvider(gemini_api_key, coingecko)
        self._claude: ClaudeProvider | None = (
            ClaudeProvider(anthropic_api_key, coingecko)
            if anthropic_api_key
            else None
        )
        if self._claude is None:
            log.info("ANTHROPIC_API_KEY not set — running Gemini-only (no fallback)")

    async def reply(self, user_text: str) -> str:
        try:
            text = await self._gemini.chat(user_text)
        except Exception as exc:  # noqa: BLE001 — broad catch is the fallback contract
            log.warning("Gemini failed: %s", exc)
            if self._claude is None:
                return PROVIDER_FAILED
            log.info("Falling back to Claude")
            try:
                text = await self._claude.chat(user_text)
            except Exception as exc2:  # noqa: BLE001
                log.error("Both LLMs failed: gemini=%s claude=%s", exc, exc2)
                return PROVIDER_FAILED

        if not text:
            return "🦉 (I had no reply for that — try rephrasing?)"

        if not passes_guardrail(text):
            log.warning("Guardrail tripped on model output: %r", text[:200])
            return GUARDRAIL_REFUSAL

        return text
