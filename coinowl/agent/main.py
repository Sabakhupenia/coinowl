"""CoinOwl LLM agent — OpenAI primary for general questions, Gemini for chart
requests, Claude Haiku as last-resort fallback.

All providers see the same four tools (`get_price`, `get_market_chart`,
`get_chart`, `get_chart_html`) and the same system prompt. Per-message routing
is intent-driven: messages mentioning chart/graph/plot keywords (in EN/KA/RU)
go to Gemini first because the chart pipeline was built and tested there; all
other messages go to OpenAI to conserve Gemini's RPD quota. If the primary
fails, the other LLM picks up the slack silently (logged, not user-visible);
Claude is the final safety net.

The tool dispatcher (`execute_tool`) returns dicts rather than raising so the
model can apologize naturally on errors ("I don't recognize 'FOO'") instead
of crashing the whole turn.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import anthropic
import openai
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
from coinowl.charts.plotly_chart import generate_chart, generate_chart_html
from coinowl.data.symbols import resolve

log = get_logger(__name__)

_GEMINI_MODEL = "gemini-2.5-flash"
_OPENAI_MODEL = "gpt-5.4-mini"
_CLAUDE_MODEL = "claude-haiku-4-5"

# Route messages mentioning these tokens to Gemini first; everything else to
# OpenAI. The actual chart PNG/HTML is rendered by Plotly regardless of LLM —
# this split is just to conserve Gemini's per-day quota for messages where the
# user is explicitly asking for a chart.
_CHART_INTENT_RE = re.compile(
    r"\b(chart|graph|plot|visuali[sz]e|html|interactive)\b"
    r"|ჩარტი|გრაფიკი|ნახაზი|ვიზუალ|ინტერაქტიულ"
    r"|график|диаграмм|чарт|визуализ|интерактивн",
    re.IGNORECASE,
)


def wants_chart(text: str) -> bool:
    return bool(_CHART_INTENT_RE.search(text))


def _mini_chart(prices: list[float], buckets: int = 8) -> str:
    """Return colored-square mini-chart: 🟩 = up, 🟥 = down vs previous sample."""
    if len(prices) < 2:
        return ""
    step = max(1, len(prices) // buckets)
    sampled = [prices[i] for i in range(0, len(prices), step)][:buckets]
    return "".join("🟩" if sampled[i] >= sampled[i - 1] else "🟥" for i in range(1, len(sampled)))


@dataclass
class AgentResult:
    text: str
    chart_png: bytes | None = field(default=None)
    chart_filename: str | None = field(default=None)
    chart_html: bytes | None = field(default=None)
    chart_html_filename: str | None = field(default=None)
    chart_context: dict | None = field(default=None)  # {"symbol": str, "days": int}


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
    tool_name: str,
    args: dict[str, Any],
    cg: CoinGeckoClient,
    side_effects: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one tool call and return a JSON-serializable result dict.

    Returning errors as dict payloads (rather than raising) lets the LLM
    surface a natural apology to the user instead of dropping the whole turn.
    Non-text side effects (chart context) are written into `side_effects` if provided.
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
            log.warning("get_price failed for {}: {}", coin_id, exc)
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
            log.warning("get_market_chart failed for {}: {}", coin_id, exc)
            return {"error": "CoinGecko request failed; try again"}

        if not points:
            return {"error": "No data returned", "symbol": symbol}

        first, last = points[0], points[-1]
        change_pct = (last.price - first.price) / first.price * 100 if first.price else 0.0
        if side_effects is not None:
            side_effects["chart_context"] = {"symbol": symbol.upper(), "days": days}
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
            "mini_chart": _mini_chart([p.price for p in points]),
            "attribution": ATTRIBUTION,
        }

    if tool_name == "get_chart":
        symbol = str(args.get("symbol", "")).strip()
        try:
            days = int(args.get("days", 7))
        except (TypeError, ValueError):
            return {"error": "Argument 'days' must be an integer"}
        if not symbol:
            return {"error": "Missing required argument: symbol"}
        if days not in (1, 7, 30, 90):
            days = max(1, min(90, days))

        coin_id = resolve(symbol)
        try:
            points = await cg.get_market_chart(coin_id, days=days)
        except CoinGeckoUnknownCoinError:
            return {"error": f"Unknown coin: {symbol!r}", "symbol": symbol}
        except CoinGeckoRateLimitError:
            return {"error": "CoinGecko is rate-limiting; back off and try later"}
        except CoinGeckoError as exc:
            log.warning("get_chart failed for {}: {}", coin_id, exc)
            return {"error": "CoinGecko request failed; try again"}

        if not points:
            return {"error": "No data returned", "symbol": symbol}

        first, last = points[0], points[-1]
        change_pct = (last.price - first.price) / first.price * 100 if first.price else 0.0

        try:
            png_bytes = await generate_chart(symbol.upper(), points, days)
        except Exception as exc:
            log.warning("Chart render failed for {}: {}", symbol, exc)
            return {"error": "Chart generation failed; try again"}

        if side_effects is not None:
            side_effects["chart_png"] = png_bytes
            side_effects["chart_filename"] = f"{symbol.upper()}_{days}d.png"
            side_effects["chart_context"] = {"symbol": symbol.upper(), "days": days}

        return {
            "chart": "ready",
            "symbol": symbol.upper(),
            "days": days,
            "first_price_usd": first.price,
            "last_price_usd": last.price,
            "change_pct": round(change_pct, 2),
            "attribution": ATTRIBUTION,
        }

    if tool_name == "get_chart_html":
        symbol = str(args.get("symbol", "")).strip()
        try:
            days = int(args.get("days", 7))
        except (TypeError, ValueError):
            return {"error": "Argument 'days' must be an integer"}
        if not symbol:
            return {"error": "Missing required argument: symbol"}
        if days not in (1, 7, 30, 90):
            days = max(1, min(90, days))

        coin_id = resolve(symbol)
        try:
            points = await cg.get_market_chart(coin_id, days=days)
        except CoinGeckoUnknownCoinError:
            return {"error": f"Unknown coin: {symbol!r}", "symbol": symbol}
        except CoinGeckoRateLimitError:
            return {"error": "CoinGecko is rate-limiting; back off and try later"}
        except CoinGeckoError as exc:
            log.warning("get_chart_html failed for {}: {}", coin_id, exc)
            return {"error": "CoinGecko request failed; try again"}

        if not points:
            return {"error": "No data returned", "symbol": symbol}

        try:
            html_bytes = await generate_chart_html(symbol.upper(), points, days)
        except Exception as exc:
            log.warning("HTML chart render failed for {}: {}", symbol, exc)
            return {"error": "HTML chart generation failed; try again"}

        if side_effects is not None:
            side_effects["chart_html"] = html_bytes
            side_effects["chart_html_filename"] = f"{symbol.upper()}_{days}d.html"
            side_effects["chart_context"] = {"symbol": symbol.upper(), "days": days}

        return {
            "html": "ready",
            "symbol": symbol.upper(),
            "days": days,
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
        genai_types.FunctionDeclaration(
            name="get_chart",
            description=(
                "Generate and send a PNG bar chart of historical prices. "
                "Call this when the user explicitly asks for a chart, graph, or plot."
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
        genai_types.FunctionDeclaration(
            name="get_chart_html",
            description=(
                "Send the interactive HTML version of a chart. Call this ONLY after "
                "the user has confirmed (e.g. 'yes') a prior HTML offer. Use the same "
                "symbol and days as the most recent get_chart call."
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
    def __init__(self, api_key: str, coingecko: CoinGeckoClient, model: str = _GEMINI_MODEL) -> None:
        self._client = genai.Client(api_key=api_key)
        self._cg = coingecko
        self._model = model

    async def chat(self, user_text: str) -> tuple[str, dict[str, Any]]:
        side_effects: dict[str, Any] = {}
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
                model=self._model,
                contents=contents,
                config=config,
            )

            candidate = response.candidates[0] if response.candidates else None
            if candidate is None or candidate.content is None:
                return "", side_effects

            contents.append(candidate.content)

            fcs = response.function_calls or []
            if not fcs:
                return (response.text or "").strip(), side_effects

            tool_response_parts: list[Any] = []
            for fc in fcs:
                args = dict(fc.args) if fc.args else {}
                result = await execute_tool(fc.name, args, self._cg, side_effects)
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
        return "I got stuck thinking about that. Could you rephrase your question?", side_effects


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
    {
        "name": "get_chart",
        "description": (
            "Generate and send a PNG bar chart of historical prices. "
            "Call this when the user explicitly asks for a chart, graph, or plot."
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
    {
        "name": "get_chart_html",
        "description": (
            "Send the interactive HTML version of a chart. Call this ONLY after "
            "the user has confirmed (e.g. 'yes') a prior HTML offer. Use the same "
            "symbol and days as the most recent get_chart call."
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

    async def chat(self, user_text: str) -> tuple[str, dict[str, Any]]:
        side_effects: dict[str, Any] = {}
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
                text = next(
                    (b.text for b in response.content if b.type == "text"),
                    "",
                ).strip()
                return text, side_effects

            if response.stop_reason != "tool_use":
                log.warning("Claude returned unexpected stop_reason: {}", response.stop_reason)
                text = next(
                    (b.text for b in response.content if b.type == "text"),
                    "",
                ).strip()
                return text, side_effects

            messages.append({"role": "assistant", "content": response.content})

            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await execute_tool(block.name, dict(block.input), self._cg, side_effects)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})

        log.warning("Claude hit max tool iterations")
        return "I got stuck thinking about that. Could you rephrase your question?", side_effects


# ---------------------------------------------------------------------------
# OpenAI provider — manual tool-calling loop on AsyncOpenAI.
# ---------------------------------------------------------------------------


def _openai_tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


_OPENAI_TOOLS: list[dict[str, Any]] = [
    _openai_tool(
        "get_price",
        "Get the current spot price of a cryptocurrency in USD.",
        {
            "symbol": {
                "type": "string",
                "description": "Ticker (BTC, ETH) or CoinGecko coin id (bitcoin).",
            }
        },
        ["symbol"],
    ),
    _openai_tool(
        "get_market_chart",
        "Get historical price points for a cryptocurrency over the last N days. "
        "Returns first/last prices and percent change.",
        {
            "symbol": {"type": "string", "description": "Ticker or CoinGecko coin id."},
            "days": {"type": "integer", "description": "Lookback window: 1, 7, 30, or 90."},
        },
        ["symbol", "days"],
    ),
    _openai_tool(
        "get_chart",
        "Generate and send a PNG bar chart of historical prices. "
        "Call this when the user explicitly asks for a chart, graph, or plot.",
        {
            "symbol": {"type": "string", "description": "Ticker or CoinGecko coin id."},
            "days": {"type": "integer", "description": "Lookback window: 1, 7, 30, or 90."},
        },
        ["symbol", "days"],
    ),
    _openai_tool(
        "get_chart_html",
        "Send the interactive HTML version of a chart. Call this ONLY after "
        "the user has confirmed (e.g. 'yes') a prior HTML offer. Use the same "
        "symbol and days as the most recent get_chart call.",
        {
            "symbol": {"type": "string", "description": "Ticker or CoinGecko coin id."},
            "days": {"type": "integer", "description": "Lookback window: 1, 7, 30, or 90."},
        },
        ["symbol", "days"],
    ),
]


class OpenAIProvider:
    def __init__(self, api_key: str, coingecko: CoinGeckoClient, model: str = _OPENAI_MODEL) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._cg = coingecko
        self._model = model

    async def chat(self, user_text: str) -> tuple[str, dict[str, Any]]:
        side_effects: dict[str, Any] = {}
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]

        for _ in range(_MAX_TOOL_ITERATIONS):
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=_OPENAI_TOOLS,
                max_completion_tokens=_MAX_OUTPUT_TOKENS,
            )
            msg = response.choices[0].message
            tool_calls = msg.tool_calls or []

            if not tool_calls:
                return (msg.content or "").strip(), side_effects

            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = await execute_tool(tc.function.name, args, self._cg, side_effects)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    }
                )

        log.warning("OpenAI hit max tool iterations")
        return "I got stuck thinking about that. Could you rephrase your question?", side_effects


# ---------------------------------------------------------------------------
# Agent — intent-routed provider chain + guardrail.
# ---------------------------------------------------------------------------


class Agent:
    def __init__(
        self,
        *,
        gemini_api_key: str,
        gemini_model: str = _GEMINI_MODEL,
        openai_api_key: str | None,
        openai_model: str = _OPENAI_MODEL,
        anthropic_api_key: str | None,
        coingecko: CoinGeckoClient,
    ) -> None:
        self._gemini = GeminiProvider(gemini_api_key, coingecko, model=gemini_model)
        self._openai: OpenAIProvider | None = (
            OpenAIProvider(openai_api_key, coingecko, model=openai_model)
            if openai_api_key
            else None
        )
        self._claude: ClaudeProvider | None = (
            ClaudeProvider(anthropic_api_key, coingecko)
            if anthropic_api_key
            else None
        )
        log.info("Gemini model: {}", gemini_model)
        if self._openai is not None:
            log.info("OpenAI model: {} (primary for non-chart queries)", openai_model)
        else:
            log.info("OPENAI_API_KEY not set — routing all queries to Gemini")
        if self._claude is None:
            log.info("ANTHROPIC_API_KEY not set — Claude fallback disabled")

    def _provider_chain(self, user_text: str) -> list[tuple[str, Any]]:
        """Ordered list of (label, provider) to try for this message."""
        chain: list[tuple[str, Any]] = []
        chart_intent = wants_chart(user_text)
        # Primary: Gemini for chart messages, OpenAI otherwise. Fall through
        # the other live provider, then Claude.
        if chart_intent or self._openai is None:
            chain.append(("gemini", self._gemini))
            if self._openai is not None:
                chain.append(("openai", self._openai))
        else:
            chain.append(("openai", self._openai))
            chain.append(("gemini", self._gemini))
        if self._claude is not None:
            chain.append(("claude", self._claude))
        return chain

    async def reply(self, user_text: str) -> AgentResult:
        side_effects: dict[str, Any] = {}
        chain = self._provider_chain(user_text)
        text: str = ""
        errors: list[str] = []
        for label, provider in chain:
            try:
                text, side_effects = await provider.chat(user_text)
                if errors:
                    log.info("{} succeeded after {} failed", label, ", ".join(errors))
                break
            except Exception as exc:  # noqa: BLE001 — broad catch is the fallback contract
                log.warning("{} failed: {}", label, exc)
                errors.append(f"{label}={exc.__class__.__name__}")
        else:
            log.error("All LLMs failed: {}", "; ".join(errors))
            return AgentResult(text=PROVIDER_FAILED)

        if not text:
            return AgentResult(text="🦉 (I had no reply for that — try rephrasing?)")

        if not passes_guardrail(text):
            log.warning("Guardrail tripped on model output: {!r}", text[:200])
            return AgentResult(text=GUARDRAIL_REFUSAL)

        return AgentResult(
            text=text,
            chart_png=side_effects.get("chart_png"),
            chart_filename=side_effects.get("chart_filename"),
            chart_html=side_effects.get("chart_html"),
            chart_html_filename=side_effects.get("chart_html_filename"),
            chart_context=side_effects.get("chart_context"),
        )
