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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import anthropic
import openai
from google import genai
from google.genai import types as genai_types

from coinowl.agent.prompts import (
    GUARDRAIL_REFUSAL,
    OFFTOPIC_REFUSAL,
    PROVIDER_FAILED,
    SYSTEM_PROMPT,
)
from coinowl.agent.safety import TopicClassifier, passes_offtopic_regex
from coinowl.core.logging import get_logger
from coinowl.data.coingecko import (
    ATTRIBUTION,
    CoinGeckoClient,
    CoinGeckoError,
    CoinGeckoRateLimitError,
    CoinGeckoUnknownCoinError,
)
from coinowl.charts.plotly_chart import generate_chart, generate_chart_html, generate_sparkline
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


ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]


async def _emit(cb: ProgressCallback | None, event: dict[str, Any]) -> None:
    if cb is None:
        return
    try:
        await cb(event)
    except Exception as exc:  # noqa: BLE001 — progress callback must not break the turn
        log.warning("on_progress callback raised: {}", exc)


@dataclass
class AgentResult:
    text: str
    chart_png: bytes | None = field(default=None)
    chart_filename: str | None = field(default=None)
    chart_html: bytes | None = field(default=None)
    chart_html_filename: str | None = field(default=None)
    sparkline_png: bytes | None = field(default=None)
    sparkline_filename: str | None = field(default=None)
    summary_stack_png: bytes | None = field(default=None)
    summary_stack_filename: str | None = field(default=None)
    summary_comparison_png: bytes | None = field(default=None)
    summary_comparison_filename: str | None = field(default=None)
    summary_stack_html: bytes | None = field(default=None)
    summary_stack_html_filename: str | None = field(default=None)
    summary_comparison_html: bytes | None = field(default=None)
    summary_comparison_html_filename: str | None = field(default=None)
    chart_context: dict | None = field(default=None)  # {"symbol": str, "days": int}
    schedule_proposal: dict | None = field(default=None)  # delivery-mode-decision-pending
    provider_used: str | None = field(default=None)   # 'openai' | 'gemini' | 'claude'
    model_used: str | None = field(default=None)
    tool_calls_made: list[dict[str, Any]] | None = field(default=None)


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


_DELIVERABLE_KEYS = ("chart_png", "chart_html", "sparkline_png")


# Tools the user can put on a schedule. Read-only / stats-producing tools are
# allowed; meta-tools (set_user_profile, schedule_push itself, etc.) are not —
# scheduling those would either be nonsensical or recursive.
_SCHEDULABLE_TOOLS = frozenset({
    "get_price",
    "get_market_chart",
    "get_chart",
    "get_chart_html",
    "get_top_movers",
    "get_market_summary",
})

# Required keys in `tool_args` for each schedulable tool. Validating at
# schedule_push time means the LLM gets a clear error and retries with proper
# args; otherwise the watcher would just produce a useless error at fire time.
_SCHEDULE_REQUIRED_TOOL_ARGS = {
    "get_price": ["symbol"],
    "get_market_chart": ["symbol", "days"],
    "get_chart": ["symbol", "days"],
    "get_chart_html": ["symbol", "days"],
    "get_top_movers": ["direction", "window"],
    "get_market_summary": [],  # all-optional
}


def _max_iter_text(side_effects: dict[str, Any]) -> str:
    """When max tool iterations is hit, prefer a soft message if we already
    produced something deliverable (a chart, html, sparkline) during the loop.
    Otherwise admit confusion."""
    if any(side_effects.get(k) for k in _DELIVERABLE_KEYS):
        return "Here's what you asked for."
    return "I got stuck thinking about that. Could you rephrase your question?"


# ---------------------------------------------------------------------------
# Tool dispatcher — shared by both providers.
# ---------------------------------------------------------------------------


async def execute_tool(
    tool_name: str,
    args: dict[str, Any],
    cg: CoinGeckoClient,
    side_effects: dict[str, Any] | None = None,
    uid: int | None = None,
) -> dict[str, Any]:
    """Run one tool call and return a JSON-serializable result dict.

    Returning errors as dict payloads (rather than raising) lets the LLM
    surface a natural apology to the user instead of dropping the whole turn.
    Non-text side effects (chart context) are written into `side_effects` if provided.
    `uid` is required by user-scoped tools (set_user_profile, etc.); price/chart
    tools ignore it.
    """
    if tool_name == "set_user_profile":
        if uid is None:
            return {"error": "Internal: uid not available for set_user_profile"}
        name = str(args.get("name", "")).strip()
        langs = args.get("languages") or []
        if not isinstance(langs, list):
            langs = [str(langs)]
        langs = [str(lang).strip().lower() for lang in langs if str(lang).strip()]
        raw_coins = args.get("coins") or []
        if not isinstance(raw_coins, list):
            raw_coins = [str(raw_coins)]
        coins = [str(c).strip().upper() for c in raw_coins if str(c).strip()]
        coins = list(dict.fromkeys(coins))  # dedupe, preserve order
        if not name or not langs or not coins:
            return {"error": "All three required: name, at least one language, and at least one coin."}
        from coinowl.db import users as db_users
        for sym in coins:
            try:
                resolve(sym)
            except Exception:
                return {"error": f"Unknown ticker: {sym!r}. Use BTC, ETH, SOL, etc."}
        if len(coins) > db_users.WATCHLIST_MAX:
            return {"error": f"Watchlist capped at {db_users.WATCHLIST_MAX} coins; pick up to {db_users.WATCHLIST_MAX}."}
        # Auto-detect timezone from preferred languages so scheduled-push time
        # conversion works without an explicit onboarding question. Users can
        # change later via admin or a profile-edit tool.
        tz_arg = str(args.get("timezone", "")).strip()
        if tz_arg:
            timezone = tz_arg
        elif "ka" in langs:
            timezone = "Asia/Tbilisi"
        elif "ru" in langs:
            timezone = "Europe/Moscow"
        else:
            timezone = "Asia/Tbilisi"  # bot's current user base; safe fallback
        try:
            await db_users.set_profile(
                uid,
                display_name=name,
                preferred_languages=langs,
                coins=coins,
                timezone=timezone,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("set_user_profile DB write failed: {}", exc)
            return {"error": "Could not save profile; try again"}
        return {
            "profile_set": True,
            "name": name,
            "languages": langs,
            "coins": coins,
            "timezone": timezone,
        }

    if tool_name == "update_watchlist":
        if uid is None:
            return {"error": "Internal: uid not available for update_watchlist"}
        raw_syms = args.get("symbols") or []
        if not isinstance(raw_syms, list):
            raw_syms = [str(raw_syms)]
        symbols = [str(s).strip().upper() for s in raw_syms if str(s).strip()]
        mode = str(args.get("mode", "replace")).strip().lower()
        if mode not in ("replace", "add", "remove"):
            return {"error": "Argument 'mode' must be 'replace', 'add', or 'remove'"}
        if not symbols:
            return {"error": "At least one symbol is required"}
        from coinowl.db import users as db_users
        if mode != "remove":
            for sym in symbols:
                try:
                    resolve(sym)
                except Exception:
                    return {"error": f"Unknown ticker: {sym!r}. Use BTC, ETH, SOL, etc."}
        try:
            result = await db_users.update_watchlist(uid, symbols=symbols, mode=mode)
        except db_users.WatchlistTooLarge as exc:
            return {"error": str(exc) + f". Cap is {db_users.WATCHLIST_MAX}. Remove some first."}
        except Exception as exc:  # noqa: BLE001
            log.warning("update_watchlist DB write failed: {}", exc)
            return {"error": "Could not update watchlist; try again"}
        return {"watchlist": result, "mode": mode, "count": len(result)}

    if tool_name == "get_watchlist":
        if uid is None:
            return {"error": "Internal: uid not available for get_watchlist"}
        from coinowl.db import users as db_users
        try:
            wl = await db_users.get_watchlist(uid)
        except Exception as exc:  # noqa: BLE001
            log.warning("get_watchlist DB read failed: {}", exc)
            return {"error": "Could not read watchlist; try again"}
        return {"watchlist": wl, "count": len(wl)}

    if tool_name == "get_market_summary":
        if uid is None:
            return {"error": "Internal: uid not available for get_market_summary"}
        window = str(args.get("window", "7d")).strip().lower()
        if window not in ("24h", "7d", "30d"):
            window = "7d"
        days_map = {"24h": 1, "7d": 7, "30d": 30}
        days = days_map[window]
        want_html = bool(args.get("html") or False)
        from coinowl.db import users as db_users
        try:
            wl = await db_users.get_watchlist(uid)
        except Exception as exc:  # noqa: BLE001
            log.warning("get_market_summary watchlist read failed: {}", exc)
            return {"error": "Could not read your watchlist; try again"}
        if not wl:
            return {"error": "Your watchlist is empty — add coins first with 'add BTC and ETH to my watchlist'."}

        import asyncio as _asyncio
        sem = _asyncio.Semaphore(2)

        async def fetch(sym: str):
            coin_id = resolve(sym)
            async with sem:
                try:
                    points = await cg.get_market_chart(coin_id, days=days)
                    return (sym, points, None)
                except CoinGeckoRateLimitError:
                    return (sym, [], "rate_limited")
                except CoinGeckoUnknownCoinError:
                    return (sym, [], "unknown")
                except CoinGeckoError as exc:
                    log.warning("summary fetch {} failed: {}", sym, exc)
                    return (sym, [], "failed")

        fetched = await _asyncio.gather(*(fetch(s) for s in wl))
        rows: list[tuple[str, list[Any]]] = []
        coin_payload: list[dict[str, Any]] = []
        for sym, points, err in fetched:
            if err or not points:
                coin_payload.append({"symbol": sym, "error": err or "no_data"})
                continue
            first, last = points[0], points[-1]
            change_pct = (last.price - first.price) / first.price * 100 if first.price else 0.0
            coin_payload.append({
                "symbol": sym,
                "price_usd": round(last.price, 4),
                "change_pct": round(change_pct, 2),
            })
            rows.append((sym, points))

        if not rows:
            return {
                "window": window,
                "coins": coin_payload,
                "error": "Could not fetch chart data for any of your coins",
                "attribution": ATTRIBUTION,
            }

        window_label = {"24h": "24-hour", "7d": "7-day", "30d": "30-day"}[window]
        try:
            from coinowl.charts.plotly_chart import (
                generate_summary_stack,
                generate_summary_comparison,
                generate_summary_stack_html,
                generate_summary_comparison_html,
            )
            render_tasks = [
                generate_summary_stack(rows, window_label),
                generate_summary_comparison(rows, window_label),
            ]
            if want_html:
                render_tasks.extend([
                    generate_summary_stack_html(rows, window_label),
                    generate_summary_comparison_html(rows, window_label),
                ])
            renders = await _asyncio.gather(*render_tasks)
            stack_bytes, comp_bytes = renders[0], renders[1]
            stack_html_bytes, comp_html_bytes = (
                (renders[2], renders[3]) if want_html else (None, None)
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("summary chart render failed: {}", exc)
            return {
                "window": window,
                "coins": coin_payload,
                "error": "Chart render failed",
                "attribution": ATTRIBUTION,
            }

        if side_effects is not None:
            side_effects["summary_stack_png"] = stack_bytes
            side_effects["summary_stack_filename"] = f"watchlist_{window}_stack.png"
            side_effects["summary_comparison_png"] = comp_bytes
            side_effects["summary_comparison_filename"] = f"watchlist_{window}_comparison.png"
            if stack_html_bytes is not None:
                side_effects["summary_stack_html"] = stack_html_bytes
                side_effects["summary_stack_html_filename"] = f"watchlist_{window}_stack.html"
            if comp_html_bytes is not None:
                side_effects["summary_comparison_html"] = comp_html_bytes
                side_effects["summary_comparison_html_filename"] = f"watchlist_{window}_comparison.html"

        return {
            "window": window,
            "coins": coin_payload,
            "html_delivered": want_html,
            "attribution": ATTRIBUTION,
        }

    if tool_name == "recall_past_conversations":
        if uid is None:
            return {"error": "Internal: uid not available for recall_past_conversations"}
        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "Argument 'query' is required"}
        try:
            k = int(args.get("k", 3))
        except (TypeError, ValueError):
            k = 3
        k = max(1, min(5, k))
        from coinowl.db.messages import semantic_recall
        try:
            matches = await semantic_recall(uid, query, k=k)
        except Exception as exc:  # noqa: BLE001
            log.warning("recall_past_conversations failed: {}", exc)
            return {"error": "Could not search past conversations; try again"}
        return {
            "query": query,
            "matches": [
                {
                    "role": m["role"],
                    "content": m["content"],
                    "ts": m["ts"].isoformat() if m.get("ts") else None,
                    "similarity": round(float(m.get("similarity") or 0.0), 3),
                }
                for m in matches
            ],
            "count": len(matches),
        }

    if tool_name == "set_price_alert":
        if uid is None:
            return {"error": "Internal: uid not available for set_price_alert"}
        symbol = str(args.get("symbol", "")).strip().upper()
        if not symbol:
            return {"error": "Missing required argument: symbol"}
        try:
            threshold = float(args.get("threshold"))
        except (TypeError, ValueError):
            return {"error": "Argument 'threshold' must be a number (price in USD)"}
        if threshold <= 0:
            return {"error": "Argument 'threshold' must be positive"}
        direction = str(args.get("direction", "")).strip().lower()
        if direction not in ("above", "below"):
            return {"error": "Argument 'direction' must be 'above' or 'below'"}
        recurring = bool(args.get("recurring") or False)
        original_phrasing = str(args.get("original_phrasing", "")).strip()
        if not original_phrasing:
            return {"error": "Argument 'original_phrasing' is required (the user's own words)"}
        try:
            coin_id = resolve(symbol)
        except Exception:
            return {"error": f"Unknown ticker: {symbol!r}. Use BTC, ETH, SOL, etc."}
        from coinowl.db import alerts as db_alerts
        try:
            row = await db_alerts.create_alert(
                user_id=uid,
                symbol=symbol,
                coin_id=coin_id,
                threshold=threshold,
                direction=direction,
                recurring=recurring,
                original_phrasing=original_phrasing,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("set_price_alert DB write failed: {}", exc)
            return {"error": "Could not save the alert; try again"}
        return {
            "alert_id": row["id"],
            "symbol": row["symbol"],
            "threshold": float(row["threshold"]),
            "direction": row["direction"],
            "recurring": row["recurring"],
        }

    if tool_name == "list_price_alerts":
        if uid is None:
            return {"error": "Internal: uid not available for list_price_alerts"}
        from coinowl.db import alerts as db_alerts
        try:
            rows = await db_alerts.list_alerts(uid, only_enabled=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("list_price_alerts failed: {}", exc)
            return {"error": "Could not read alerts; try again"}
        return {
            "alerts": [
                {
                    "alert_id": r["id"],
                    "symbol": r["symbol"],
                    "threshold": float(r["threshold"]),
                    "direction": r["direction"],
                    "recurring": r["recurring"],
                    "original_phrasing": r["original_phrasing"],
                }
                for r in rows
            ],
            "count": len(rows),
        }

    if tool_name == "cancel_price_alert":
        if uid is None:
            return {"error": "Internal: uid not available for cancel_price_alert"}
        try:
            alert_id = int(args.get("alert_id"))
        except (TypeError, ValueError):
            return {"error": "Argument 'alert_id' must be an integer (from list_price_alerts)"}
        from coinowl.db import alerts as db_alerts
        try:
            cancelled = await db_alerts.cancel_alert(user_id=uid, alert_id=alert_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("cancel_price_alert failed: {}", exc)
            return {"error": "Could not cancel; try again"}
        if not cancelled:
            return {"error": f"No active alert with id {alert_id} found on your account"}
        return {"cancelled": True, "alert_id": alert_id}

    if tool_name == "schedule_push":
        if uid is None:
            return {"error": "Internal: uid not available for schedule_push"}
        cron_expr = str(args.get("cron_expr", "")).strip()
        if not cron_expr:
            return {"error": "Argument 'cron_expr' is required (5-field cron, e.g. '0 9 * * 1' for every Monday 9am UTC)"}
        from croniter import croniter
        if not croniter.is_valid(cron_expr):
            return {"error": f"Invalid cron expression: {cron_expr!r}. Use 5-field cron, e.g. '0 9 * * *' for daily 9am UTC."}
        target_tool = str(args.get("tool_name", "")).strip()
        if target_tool not in _SCHEDULABLE_TOOLS:
            return {
                "error": (
                    f"Tool {target_tool!r} cannot be scheduled. "
                    f"Schedulable: {', '.join(sorted(_SCHEDULABLE_TOOLS))}."
                )
            }
        tool_args = args.get("tool_args") or {}
        if not isinstance(tool_args, dict):
            return {"error": "Argument 'tool_args' must be an object/dict"}
        required = _SCHEDULE_REQUIRED_TOOL_ARGS.get(target_tool, [])
        missing = [k for k in required if k not in tool_args or tool_args[k] in (None, "")]
        if missing:
            return {
                "error": (
                    f"tool_args for {target_tool} is missing required keys: "
                    f"{', '.join(missing)}. Examples — get_top_movers needs "
                    "{'direction':'gainers'|'losers','window':'24h'|'7d'|'30d'}, "
                    "get_chart needs {'symbol':'BTC','days':7}, etc. Retry the "
                    "schedule_push call with complete tool_args."
                )
            }
        delivery_mode_raw = args.get("delivery_mode")
        delivery_mode: str | None
        if delivery_mode_raw is None or str(delivery_mode_raw).strip() == "":
            delivery_mode = None
        else:
            delivery_mode = str(delivery_mode_raw).strip().lower()
            if delivery_mode not in ("push", "deferred"):
                return {"error": "Argument 'delivery_mode' must be 'push' or 'deferred'"}
        original_phrasing = str(args.get("original_phrasing", "")).strip()
        if not original_phrasing:
            return {"error": "Argument 'original_phrasing' is required (the user's own words)"}
        from datetime import datetime, timezone
        next_fire = croniter(cron_expr, datetime.now(timezone.utc)).get_next(datetime)

        # If the user (or the LLM, on an unambiguous request) already picked a
        # mode, write the row now. Otherwise stage the proposal in side_effects;
        # the bot will offer inline buttons and the callback handler creates
        # the row once the user taps.
        if delivery_mode is not None:
            from coinowl.db import schedules as db_sched
            try:
                row = await db_sched.create_schedule(
                    user_id=uid,
                    cron_expr=cron_expr,
                    tool_name=target_tool,
                    tool_args=tool_args,
                    original_phrasing=original_phrasing,
                    delivery_mode=delivery_mode,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("schedule_push DB write failed: {}", exc)
                return {"error": "Could not save the schedule; try again"}
            return {
                "schedule_id": row["id"],
                "status": "created",
                "cron_expr": row["cron_expr"],
                "tool_name": row["tool_name"],
                "tool_args": row["tool_args_json"],
                "delivery_mode": row["delivery_mode"],
                "next_fire_utc": next_fire.isoformat(),
            }

        if side_effects is not None:
            side_effects["schedule_proposal"] = {
                "user_id": uid,
                "cron_expr": cron_expr,
                "tool_name": target_tool,
                "tool_args": tool_args,
                "original_phrasing": original_phrasing,
            }
        return {
            "status": "needs_delivery_mode",
            "cron_expr": cron_expr,
            "tool_name": target_tool,
            "next_fire_utc": next_fire.isoformat(),
        }

    if tool_name == "list_scheduled_pushes":
        if uid is None:
            return {"error": "Internal: uid not available for list_scheduled_pushes"}
        from coinowl.db import schedules as db_sched
        try:
            rows = await db_sched.list_schedules(uid, only_enabled=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("list_scheduled_pushes failed: {}", exc)
            return {"error": "Could not read schedules; try again"}
        return {
            "schedules": [
                {
                    "schedule_id": r["id"],
                    "cron_expr": r["cron_expr"],
                    "tool_name": r["tool_name"],
                    "tool_args": r["tool_args_json"],
                    "delivery_mode": r.get("delivery_mode") or "push",
                    "original_phrasing": r["original_phrasing"],
                }
                for r in rows
            ],
            "count": len(rows),
        }

    if tool_name == "cancel_scheduled_push":
        if uid is None:
            return {"error": "Internal: uid not available for cancel_scheduled_push"}
        try:
            schedule_id = int(args.get("schedule_id"))
        except (TypeError, ValueError):
            return {"error": "Argument 'schedule_id' must be an integer (from list_scheduled_pushes)"}
        from coinowl.db import schedules as db_sched
        try:
            cancelled = await db_sched.cancel_schedule(user_id=uid, schedule_id=schedule_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("cancel_scheduled_push failed: {}", exc)
            return {"error": "Could not cancel; try again"}
        if not cancelled:
            return {"error": f"No active schedule with id {schedule_id} found on your account"}
        return {"cancelled": True, "schedule_id": schedule_id}

    if tool_name == "get_top_movers":
        direction = str(args.get("direction", "")).strip().lower()
        if direction not in ("gainers", "losers"):
            return {"error": "Argument 'direction' must be 'gainers' or 'losers'"}
        window = str(args.get("window", "24h")).strip().lower()
        if window not in ("24h", "7d", "30d"):
            window = "24h"
        try:
            limit = int(args.get("limit", 10))
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(20, limit))

        try:
            markets = await cg.get_markets(
                price_change_percentage="24h,7d,30d",
                per_page=250,
            )
        except CoinGeckoRateLimitError:
            return {"error": "CoinGecko is rate-limiting; back off and try later"}
        except CoinGeckoError as exc:
            log.warning("get_top_movers failed: {}", exc)
            return {"error": "CoinGecko request failed; try again"}

        key_map = {
            "24h": "price_change_percentage_24h_in_currency",
            "7d": "price_change_percentage_7d_in_currency",
            "30d": "price_change_percentage_30d_in_currency",
        }
        pct_key = key_map[window]
        scored = [
            (m, m.get(pct_key))
            for m in markets
            if isinstance(m.get(pct_key), (int, float))
        ]
        scored.sort(key=lambda pair: pair[1], reverse=(direction == "gainers"))
        top = scored[:limit]
        return {
            "direction": direction,
            "window": window,
            "movers": [
                {
                    "symbol": (m.get("symbol") or "").upper(),
                    "name": m.get("name"),
                    "price_usd": m.get("current_price"),
                    "market_cap_rank": m.get("market_cap_rank"),
                    "change_pct": round(float(pct), 2),
                }
                for m, pct in top
            ],
            "attribution": ATTRIBUTION,
        }

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
            try:
                spark_bytes = await generate_sparkline(points)
                side_effects["sparkline_png"] = spark_bytes
                side_effects["sparkline_filename"] = f"{symbol.upper()}_{days}d_spark.png"
            except Exception as exc:
                log.warning("sparkline render failed for {}: {}", symbol, exc)
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
                "Generate and send a PNG area chart of historical prices. "
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
        genai_types.FunctionDeclaration(
            name="set_user_profile",
            description=(
                "Save the user's display name, preferred languages, AND initial coin "
                "watchlist so the bot can personalize replies and generate summaries. "
                "Call this ONLY during onboarding, after collecting ALL THREE: name, "
                "at least one language, and at least one coin (max 10) from the user."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "name": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="User's preferred display name (first name or chosen handle).",
                    ),
                    "languages": genai_types.Schema(
                        type=genai_types.Type.ARRAY,
                        items=genai_types.Schema(type=genai_types.Type.STRING),
                        description="ISO codes (e.g. 'en','ka','ru') the user is comfortable in.",
                    ),
                    "coins": genai_types.Schema(
                        type=genai_types.Type.ARRAY,
                        items=genai_types.Schema(type=genai_types.Type.STRING),
                        description="Uppercase tickers (e.g. ['BTC','ETH','SOL']) the user wants on their watchlist. 1-10 coins.",
                    ),
                },
                required=["name", "languages", "coins"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="update_watchlist",
            description=(
                "Mutate the user's coin watchlist. Use mode='add' for 'add X to my "
                "watchlist', mode='remove' for 'drop X / remove X', mode='replace' for "
                "'set my watchlist to X Y Z'. Tickers must be uppercase. Cap is 10 coins."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "symbols": genai_types.Schema(
                        type=genai_types.Type.ARRAY,
                        items=genai_types.Schema(type=genai_types.Type.STRING),
                        description="Uppercase tickers to add/remove/replace with.",
                    ),
                    "mode": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="'add', 'remove', or 'replace'.",
                    ),
                },
                required=["symbols", "mode"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="get_watchlist",
            description=(
                "Return the user's current coin watchlist. Call this when the user "
                "asks 'what's on my watchlist', 'what coins do I follow', etc."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={},
            ),
        ),
        genai_types.FunctionDeclaration(
            name="get_market_summary",
            description=(
                "Fetch prices, % changes, AND deliver composite charts (vertical "
                "stack of mini area charts + normalized comparison overlay) for the "
                "user's watchlist. Call this when the user asks 'how's my market', "
                "'summary please', 'how are my coins', 'ჩემი მონეტები', 'мой портфель', "
                "etc. Pick window from user phrasing: 'today' → 24h, 'this week' → 7d, "
                "'this month' → 30d. Default 7d. "
                "Set html=true when the user explicitly asks for interactive / HTML "
                "summary charts ('html version of summary', 'interactive summary'); "
                "the bot will deliver BOTH PNG and HTML versions of both summary "
                "charts. Default html=false (PNG only). Do NOT call get_chart_html "
                "for summary HTML — that's for single-coin charts only."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "window": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Time window: '24h', '7d', or '30d'. Default '7d'.",
                    ),
                    "html": genai_types.Schema(
                        type=genai_types.Type.BOOLEAN,
                        description="If true, also deliver interactive HTML versions of both summary charts. Default false (PNG only).",
                    ),
                },
                required=[],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="recall_past_conversations",
            description=(
                "Search the user's OWN past chat history (across all sessions) by "
                "semantic similarity to a query. Use this ONLY when the user references "
                "something OLDER than the recent conversation block already in your "
                "system instruction — for example: 'remember when we talked about "
                "staking last week?', 'what coin did I ask about a few days ago?', "
                "'show me the chart you made for me before'. The RECENT CONVERSATION "
                "block covers the last few turns automatically; only call this for "
                "older recall. Returns the top-K most semantically similar past "
                "messages."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "query": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="What you want to search for in the user's past conversations.",
                    ),
                    "k": genai_types.Schema(
                        type=genai_types.Type.INTEGER,
                        description="How many matches to return (1-5, default 3).",
                    ),
                },
                required=["query"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="get_top_movers",
            description=(
                "Return the top N gainers or losers across the whole crypto market "
                "over a 24h / 7d / 30d window. Call this for market-wide questions "
                "like 'biggest losers today', 'top gainers this week', 'what's "
                "moving?', 'ყველაზე დიდი დანაკარგი', 'лидеры падения'. Do NOT call "
                "this when the user named a specific coin — use get_price or "
                "get_market_chart for single-coin questions."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "direction": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="'gainers' for top up-movers, 'losers' for top down-movers.",
                    ),
                    "window": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Time window: '24h', '7d', or '30d'.",
                    ),
                    "limit": genai_types.Schema(
                        type=genai_types.Type.INTEGER,
                        description="How many movers to return (1–20, default 10).",
                    ),
                },
                required=["direction", "window"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="set_price_alert",
            description=(
                "Create a price-threshold alert. The watcher pushes the user a "
                "notification in real-time when the price crosses the threshold. "
                "Use when the user says 'tell me when BTC hits 80k', "
                "'let me know if ETH drops below 3000', 'მაცნობე როცა BTC მიაღწევს', "
                "'сообщи когда BTC дойдёт до'. Set recurring=true ONLY if the user "
                "said 'every time' or 'each time the price crosses'; default false "
                "(alert auto-disables after first fire). original_phrasing MUST be "
                "the user's own words verbatim — the bot reads it back when the "
                "alert fires."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "symbol": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Ticker (BTC, ETH, …) or CoinGecko coin id.",
                    ),
                    "threshold": genai_types.Schema(
                        type=genai_types.Type.NUMBER,
                        description="Price in USD that triggers the alert when crossed.",
                    ),
                    "direction": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="'above' to fire when price > threshold; 'below' for price < threshold.",
                    ),
                    "recurring": genai_types.Schema(
                        type=genai_types.Type.BOOLEAN,
                        description="If true, re-arms after each fire. Default false (one-shot).",
                    ),
                    "original_phrasing": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="The user's own words when creating this alert (e.g. 'tell me when BTC hits 80k').",
                    ),
                },
                required=["symbol", "threshold", "direction", "original_phrasing"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="list_price_alerts",
            description=(
                "Return the user's active price alerts. Use when the user asks "
                "'what alerts do I have', 'show my alerts', 'რა შეტყობინებები მაქვს', "
                "'мои оповещения'."
            ),
            parameters=genai_types.Schema(type=genai_types.Type.OBJECT, properties={}),
        ),
        genai_types.FunctionDeclaration(
            name="cancel_price_alert",
            description=(
                "Cancel/disable a price alert by id. Get the id from list_price_alerts. "
                "Use when the user says 'cancel my BTC alert' / 'remove that alert' — "
                "if the user is ambiguous about WHICH alert, call list_price_alerts "
                "first and ask them to pick."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "alert_id": genai_types.Schema(
                        type=genai_types.Type.INTEGER,
                        description="ID returned by list_price_alerts.",
                    ),
                },
                required=["alert_id"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="schedule_push",
            description=(
                "Schedule a recurring summary delivery. Two delivery modes: "
                "'push' (default) sends the result to the user's Telegram in "
                "real-time when the schedule fires — matches 'send me X every "
                "Monday', 'notify me', 'ping me'. 'deferred' enqueues the "
                "result so it's delivered as a prefix the NEXT time the user "
                "messages — matches 'have my watchlist ready next time we "
                "chat', 'save it for our next conversation'. Default to 'push' "
                "unless the user clearly asked for the wait-for-me behavior. "
                "Map natural-language cadence to 5-field cron (UTC): 'every "
                "Monday 9am' → '0 9 * * 1'; 'every day at 8am' → '0 8 * * *'; "
                "'every Sunday evening' → '0 18 * * 0'; 'first of every month' "
                "→ '0 9 1 * *'. tool_name must be one of: get_market_summary, "
                "get_top_movers, get_price, get_market_chart, get_chart, "
                "get_chart_html. tool_args MUST include all required args for "
                "that tool (get_top_movers needs direction + window, get_chart "
                "needs symbol + days, etc.). original_phrasing MUST be the "
                "user's own words verbatim."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "cron_expr": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="5-field cron in UTC, e.g. '0 9 * * 1' for Monday 9am.",
                    ),
                    "tool_name": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Tool to fire each schedule tick.",
                    ),
                    "tool_args": genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        description="Args object passed to the scheduled tool. Must include all required args for the target tool.",
                    ),
                    "delivery_mode": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="'push' (default — send to Telegram immediately when schedule fires) or 'deferred' (save for next user message).",
                    ),
                    "original_phrasing": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="The user's own words when creating this schedule.",
                    ),
                },
                required=["cron_expr", "tool_name", "original_phrasing"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="list_scheduled_pushes",
            description=(
                "Return the user's active scheduled pushes. Use when they ask "
                "'what summaries am I subscribed to', 'show my schedules', "
                "'რა გრაფიკი მაქვს', 'мои подписки'."
            ),
            parameters=genai_types.Schema(type=genai_types.Type.OBJECT, properties={}),
        ),
        genai_types.FunctionDeclaration(
            name="cancel_scheduled_push",
            description=(
                "Cancel/disable a scheduled push by id. Get the id from "
                "list_scheduled_pushes. If the user is ambiguous about WHICH "
                "schedule, call list_scheduled_pushes first and ask them to pick."
            ),
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "schedule_id": genai_types.Schema(
                        type=genai_types.Type.INTEGER,
                        description="ID returned by list_scheduled_pushes.",
                    ),
                },
                required=["schedule_id"],
            ),
        ),
    ]
)


class GeminiProvider:
    def __init__(self, api_key: str, coingecko: CoinGeckoClient, model: str = _GEMINI_MODEL) -> None:
        self._client = genai.Client(api_key=api_key)
        self._cg = coingecko
        self._model = model

    async def chat(
        self,
        user_text: str,
        on_progress: ProgressCallback | None = None,
        uid: int | None = None,
        user_context: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        side_effects: dict[str, Any] = {"tool_calls_made": []}
        contents: list[Any] = [
            genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(text=user_text)],
            )
        ]
        system_instruction = (
            f"{user_context}\n\n{SYSTEM_PROMPT}" if user_context else SYSTEM_PROMPT
        )
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[_GEMINI_TOOLS],
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        )

        for _ in range(_MAX_TOOL_ITERATIONS):
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model,
                contents=contents,
                config=config,
            )
            text_parts: list[str] = []
            fcs: list[Any] = []
            final_content: Any = None
            async for chunk in stream:
                candidate = chunk.candidates[0] if chunk.candidates else None
                if candidate is None or candidate.content is None:
                    continue
                final_content = candidate.content
                for part in candidate.content.parts or []:
                    if getattr(part, "text", None):
                        text_parts.append(part.text)
                        await _emit(on_progress, {"type": "text_delta", "delta": part.text})
                    fc = getattr(part, "function_call", None)
                    if fc is not None and getattr(fc, "name", None):
                        fcs.append(fc)

            if final_content is None:
                return "", side_effects
            contents.append(final_content)

            if not fcs:
                return "".join(text_parts).strip(), side_effects

            tool_response_parts: list[Any] = []
            for fc in fcs:
                args = dict(fc.args) if fc.args else {}
                await _emit(on_progress, {"type": "tool_call_start", "tool": fc.name, "args": args})
                result = await execute_tool(fc.name, args, self._cg, side_effects, uid=uid)
                side_effects["tool_calls_made"].append({"name": fc.name, "args": args})
                await _emit(on_progress, {"type": "tool_call_done", "tool": fc.name})
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
        return _max_iter_text(side_effects), side_effects


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
            "Generate and send a PNG area chart of historical prices. "
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
    {
        "name": "set_user_profile",
        "description": (
            "Save the user's display name, preferred languages, AND initial coin "
            "watchlist. Call this ONLY during onboarding, after collecting ALL THREE: "
            "name, at least one language, and at least one coin (max 10) from the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "User's preferred display name (first name or chosen handle).",
                },
                "languages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "ISO codes (e.g. 'en','ka','ru') the user is comfortable in.",
                },
                "coins": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Uppercase tickers (e.g. ['BTC','ETH','SOL']) — 1 to 10.",
                },
            },
            "required": ["name", "languages", "coins"],
        },
    },
    {
        "name": "update_watchlist",
        "description": (
            "Mutate the user's coin watchlist. mode='add' / 'remove' / 'replace'. "
            "Uppercase tickers. Cap is 10 coins."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Uppercase tickers to add/remove/replace with.",
                },
                "mode": {
                    "type": "string",
                    "description": "'add', 'remove', or 'replace'.",
                },
            },
            "required": ["symbols", "mode"],
        },
    },
    {
        "name": "get_watchlist",
        "description": "Return the user's current coin watchlist.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_market_summary",
        "description": (
            "Fetch prices + composite charts (vertical stack + normalized comparison) "
            "for the user's watchlist. Window: '24h', '7d' (default), '30d'. Set "
            "html=true when the user asks for interactive/HTML summary charts (the "
            "bot will deliver both PNG and HTML versions). Do NOT use get_chart_html "
            "for summary HTML — that's single-coin only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {
                    "type": "string",
                    "description": "Time window: '24h', '7d', or '30d'. Default '7d'.",
                },
                "html": {
                    "type": "boolean",
                    "description": "If true, also deliver interactive HTML versions of both summary charts. Default false.",
                },
            },
        },
    },
    {
        "name": "recall_past_conversations",
        "description": (
            "Search the user's own past chat history by semantic similarity. Use ONLY "
            "for references older than the RECENT CONVERSATION block already in your "
            "system instruction. Returns the top-K most similar past messages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in the user's past conversations.",
                },
                "k": {
                    "type": "integer",
                    "description": "How many matches to return (1-5, default 3).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_top_movers",
        "description": (
            "Return the top N gainers or losers across the whole crypto market "
            "over a 24h / 7d / 30d window. Call this for market-wide questions "
            "like 'biggest losers today', 'top gainers this week', 'what's "
            "moving?'. Do NOT call this when the user named a specific coin — "
            "use get_price or get_market_chart for single-coin questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "description": "'gainers' for top up-movers, 'losers' for top down-movers.",
                },
                "window": {
                    "type": "string",
                    "description": "Time window: '24h', '7d', or '30d'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "How many movers to return (1–20, default 10).",
                },
            },
            "required": ["direction", "window"],
        },
    },
    {
        "name": "set_price_alert",
        "description": (
            "Create a price-threshold alert that pushes to the user in real-time "
            "when the price crosses. Set recurring=true ONLY if user said 'every "
            "time'; default false (auto-disables after first fire). "
            "original_phrasing MUST be the user's own words verbatim."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker or coin id."},
                "threshold": {"type": "number", "description": "Price in USD."},
                "direction": {
                    "type": "string",
                    "description": "'above' or 'below'.",
                },
                "recurring": {"type": "boolean", "description": "Default false."},
                "original_phrasing": {
                    "type": "string",
                    "description": "User's own words.",
                },
            },
            "required": ["symbol", "threshold", "direction", "original_phrasing"],
        },
    },
    {
        "name": "list_price_alerts",
        "description": "Return the user's active price alerts.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancel_price_alert",
        "description": "Cancel/disable a price alert by id (from list_price_alerts).",
        "input_schema": {
            "type": "object",
            "properties": {
                "alert_id": {"type": "integer", "description": "ID from list_price_alerts."},
            },
            "required": ["alert_id"],
        },
    },
    {
        "name": "schedule_push",
        "description": (
            "Schedule a recurring summary. delivery_mode='push' (default) sends "
            "the result to Telegram in real-time when the schedule fires — "
            "matches 'send me X every Monday'. delivery_mode='deferred' saves "
            "it for the user's next message — matches 'have it ready next time "
            "we chat'. Default 'push' unless the user clearly asked to wait. "
            "Map cadence to 5-field cron (UTC). tool_name must be one of: "
            "get_market_summary, get_top_movers, get_price, get_market_chart, "
            "get_chart, get_chart_html. tool_args MUST include all required "
            "args for that tool (get_top_movers needs direction + window, "
            "get_chart needs symbol + days). original_phrasing MUST be user's "
            "own words verbatim."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cron_expr": {
                    "type": "string",
                    "description": "5-field cron in UTC, e.g. '0 9 * * 1'.",
                },
                "tool_name": {
                    "type": "string",
                    "description": "Tool to fire on each tick.",
                },
                "tool_args": {
                    "type": "object",
                    "description": "Args dict for the scheduled tool (must include all required args).",
                },
                "delivery_mode": {
                    "type": "string",
                    "description": "'push' (default) or 'deferred'.",
                },
                "original_phrasing": {
                    "type": "string",
                    "description": "User's own words.",
                },
            },
            "required": ["cron_expr", "tool_name", "original_phrasing"],
        },
    },
    {
        "name": "list_scheduled_pushes",
        "description": "Return the user's active scheduled pushes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancel_scheduled_push",
        "description": "Cancel/disable a scheduled push by id (from list_scheduled_pushes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "schedule_id": {"type": "integer", "description": "ID from list_scheduled_pushes."},
            },
            "required": ["schedule_id"],
        },
    },
]


class ClaudeProvider:
    def __init__(self, api_key: str, coingecko: CoinGeckoClient) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._cg = coingecko

    async def chat(
        self,
        user_text: str,
        on_progress: ProgressCallback | None = None,
        uid: int | None = None,
        user_context: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        side_effects: dict[str, Any] = {"tool_calls_made": []}
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_text}
        ]
        system_text = (
            f"{user_context}\n\n{SYSTEM_PROMPT}" if user_context else SYSTEM_PROMPT
        )
        # cache_control is forward-compat scaffolding: our system prompt is
        # currently below Haiku's ~4096-token cache minimum, so this is a no-op
        # until the prompt grows.
        system = [
            {
                "type": "text",
                "text": system_text,
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
                if text:
                    await _emit(on_progress, {"type": "text_delta", "delta": text})
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
                    args = dict(block.input)
                    await _emit(on_progress, {"type": "tool_call_start", "tool": block.name, "args": args})
                    result = await execute_tool(block.name, args, self._cg, side_effects, uid=uid)
                    side_effects["tool_calls_made"].append({"name": block.name, "args": args})
                    await _emit(on_progress, {"type": "tool_call_done", "tool": block.name})
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})

        log.warning("Claude hit max tool iterations")
        return _max_iter_text(side_effects), side_effects


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
        "Generate and send a PNG area chart of historical prices. "
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
    _openai_tool(
        "set_user_profile",
        "Save the user's display name, preferred languages, AND initial coin watchlist. "
        "Call this ONLY during onboarding, after collecting ALL THREE: name, at least "
        "one language, and at least one coin (max 10) from the user.",
        {
            "name": {
                "type": "string",
                "description": "User's preferred display name (first name or chosen handle).",
            },
            "languages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "ISO codes (e.g. 'en','ka','ru') the user is comfortable in.",
            },
            "coins": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Uppercase tickers (e.g. ['BTC','ETH','SOL']) — 1 to 10.",
            },
        },
        ["name", "languages", "coins"],
    ),
    _openai_tool(
        "update_watchlist",
        "Mutate the user's coin watchlist. mode='add' / 'remove' / 'replace'. "
        "Uppercase tickers. Cap is 10 coins.",
        {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Uppercase tickers to add/remove/replace with.",
            },
            "mode": {
                "type": "string",
                "description": "'add', 'remove', or 'replace'.",
            },
        },
        ["symbols", "mode"],
    ),
    _openai_tool(
        "get_watchlist",
        "Return the user's current coin watchlist.",
        {},
        [],
    ),
    _openai_tool(
        "get_market_summary",
        "Fetch prices + composite charts (vertical stack + normalized comparison) "
        "for the user's watchlist. Window: '24h', '7d' (default), '30d'. Set "
        "html=true when the user asks for interactive/HTML summary charts (bot "
        "delivers both PNG and HTML). Do NOT use get_chart_html for summary HTML.",
        {
            "window": {
                "type": "string",
                "description": "Time window: '24h', '7d', or '30d'. Default '7d'.",
            },
            "html": {
                "type": "boolean",
                "description": "If true, also deliver interactive HTML versions of both summary charts. Default false.",
            },
        },
        [],
    ),
    _openai_tool(
        "recall_past_conversations",
        "Search the user's own past chat history by semantic similarity. Use ONLY "
        "for references older than the RECENT CONVERSATION block already in your "
        "system instruction. Returns the top-K most similar past messages.",
        {
            "query": {
                "type": "string",
                "description": "What to search for in the user's past conversations.",
            },
            "k": {
                "type": "integer",
                "description": "How many matches to return (1-5, default 3).",
            },
        },
        ["query"],
    ),
    _openai_tool(
        "get_top_movers",
        "Return the top N gainers or losers across the whole crypto market "
        "over a 24h / 7d / 30d window. Call this for market-wide questions "
        "like 'biggest losers today', 'top gainers this week', 'what's "
        "moving?'. Do NOT call this when the user named a specific coin — "
        "use get_price or get_market_chart for single-coin questions.",
        {
            "direction": {
                "type": "string",
                "description": "'gainers' for top up-movers, 'losers' for top down-movers.",
            },
            "window": {
                "type": "string",
                "description": "Time window: '24h', '7d', or '30d'.",
            },
            "limit": {
                "type": "integer",
                "description": "How many movers to return (1–20, default 10).",
            },
        },
        ["direction", "window"],
    ),
    _openai_tool(
        "set_price_alert",
        "Create a price-threshold alert. The watcher pushes the user in real-time "
        "when the price crosses. Set recurring=true ONLY if the user said 'every "
        "time'; default false (auto-disables after first fire). original_phrasing "
        "MUST be the user's own words verbatim.",
        {
            "symbol": {"type": "string", "description": "Ticker or coin id."},
            "threshold": {"type": "number", "description": "Price in USD."},
            "direction": {"type": "string", "description": "'above' or 'below'."},
            "recurring": {"type": "boolean", "description": "Default false."},
            "original_phrasing": {
                "type": "string",
                "description": "User's own words.",
            },
        },
        ["symbol", "threshold", "direction", "original_phrasing"],
    ),
    _openai_tool(
        "list_price_alerts",
        "Return the user's active price alerts.",
        {},
        [],
    ),
    _openai_tool(
        "cancel_price_alert",
        "Cancel/disable a price alert by id (from list_price_alerts).",
        {"alert_id": {"type": "integer", "description": "ID from list_price_alerts."}},
        ["alert_id"],
    ),
    _openai_tool(
        "schedule_push",
        "Schedule a recurring summary. delivery_mode='push' (default) sends the "
        "result to Telegram in real-time when the schedule fires — matches 'send "
        "me X every Monday'. delivery_mode='deferred' saves it for the user's "
        "next message — matches 'have it ready next time we chat'. Default 'push' "
        "unless the user clearly asked to wait. Map cadence to 5-field cron (UTC). "
        "tool_name must be one of: get_market_summary, get_top_movers, get_price, "
        "get_market_chart, get_chart, get_chart_html. tool_args MUST include all "
        "required args for that tool (get_top_movers needs direction + window, "
        "get_chart needs symbol + days). original_phrasing MUST be user's own "
        "words verbatim.",
        {
            "cron_expr": {
                "type": "string",
                "description": "5-field cron in UTC, e.g. '0 9 * * 1'.",
            },
            "tool_name": {
                "type": "string",
                "description": "Tool to fire on each tick.",
            },
            "tool_args": {
                "type": "object",
                "description": "Args dict for the scheduled tool (must include all required args).",
            },
            "delivery_mode": {
                "type": "string",
                "description": "'push' (default) or 'deferred'.",
            },
            "original_phrasing": {
                "type": "string",
                "description": "User's own words.",
            },
        },
        ["cron_expr", "tool_name", "original_phrasing"],
    ),
    _openai_tool(
        "list_scheduled_pushes",
        "Return the user's active scheduled pushes.",
        {},
        [],
    ),
    _openai_tool(
        "cancel_scheduled_push",
        "Cancel/disable a scheduled push by id (from list_scheduled_pushes).",
        {
            "schedule_id": {
                "type": "integer",
                "description": "ID from list_scheduled_pushes.",
            },
        },
        ["schedule_id"],
    ),
]


class OpenAIProvider:
    def __init__(self, api_key: str, coingecko: CoinGeckoClient, model: str = _OPENAI_MODEL) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._cg = coingecko
        self._model = model

    async def chat(
        self,
        user_text: str,
        on_progress: ProgressCallback | None = None,
        uid: int | None = None,
        user_context: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        side_effects: dict[str, Any] = {"tool_calls_made": []}
        system_content = (
            f"{user_context}\n\n{SYSTEM_PROMPT}" if user_context else SYSTEM_PROMPT
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_text},
        ]

        for _ in range(_MAX_TOOL_ITERATIONS):
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=_OPENAI_TOOLS,
                max_completion_tokens=_MAX_OUTPUT_TOKENS,
                stream=True,
            )

            content_parts: list[str] = []
            # tool_calls accumulate across deltas, keyed by `index`
            tc_acc: dict[int, dict[str, Any]] = {}
            finish_reason: str | None = None
            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta is None:
                    continue
                if delta.content:
                    content_parts.append(delta.content)
                    await _emit(on_progress, {"type": "text_delta", "delta": delta.content})
                for tc_delta in (delta.tool_calls or []):
                    slot = tc_acc.setdefault(
                        tc_delta.index,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    if tc_delta.id:
                        slot["id"] = tc_delta.id
                    fn = tc_delta.function
                    if fn is not None:
                        if fn.name:
                            slot["name"] = fn.name
                        if fn.arguments:
                            slot["arguments"] += fn.arguments
                if choice.finish_reason:
                    finish_reason = choice.finish_reason

            if finish_reason != "tool_calls" or not tc_acc:
                return "".join(content_parts).strip(), side_effects

            tool_calls = [tc_acc[i] for i in sorted(tc_acc)]
            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(content_parts) or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                await _emit(on_progress, {"type": "tool_call_start", "tool": tc["name"], "args": args})
                result = await execute_tool(tc["name"], args, self._cg, side_effects, uid=uid)
                side_effects["tool_calls_made"].append({"name": tc["name"], "args": args})
                await _emit(on_progress, {"type": "tool_call_done", "tool": tc["name"]})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    }
                )

        log.warning("OpenAI hit max tool iterations")
        return _max_iter_text(side_effects), side_effects


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
        self._classifier = TopicClassifier(
            openai_api_key=openai_api_key,
            gemini_api_key=gemini_api_key,
            openai_model=openai_model,
            gemini_model=gemini_model,
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

    async def reply(
        self,
        user_text: str,
        on_progress: ProgressCallback | None = None,
        uid: int | None = None,
        user_context: str | None = None,
    ) -> AgentResult:
        side_effects: dict[str, Any] = {}
        chain = self._provider_chain(user_text)
        text: str = ""
        errors: list[str] = []
        winning_label: str | None = None
        winning_model: str | None = None
        for label, provider in chain:
            try:
                text, side_effects = await provider.chat(
                    user_text,
                    on_progress=on_progress,
                    uid=uid,
                    user_context=user_context,
                )
                winning_label = label
                winning_model = getattr(provider, "_model", None) or {
                    "gemini": _GEMINI_MODEL,
                    "openai": _OPENAI_MODEL,
                    "claude": _CLAUDE_MODEL,
                }.get(label)
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

        # Off-topic safety: Layer 1 (regex) is cheap + deterministic; Layer 2
        # (LLM-as-judge) catches what the regex misses. Both swap in
        # OFFTOPIC_REFUSAL on hit. Emergency-safety redirects are explicitly
        # allowed by both layers (see coinowl/agent/safety.py).
        if not passes_offtopic_regex(text):
            log.warning(
                "Off-topic regex tripped on model output: {!r}", text[:200]
            )
            return AgentResult(text=OFFTOPIC_REFUSAL)
        try:
            on_topic = await self._classifier.is_on_topic(text)
        except Exception as exc:  # noqa: BLE001
            log.warning("topic classifier raised: {}; failing open", exc)
            on_topic = True
        if not on_topic:
            log.warning(
                "Topic classifier flagged OFF_TOPIC on output: {!r}", text[:200]
            )
            return AgentResult(text=OFFTOPIC_REFUSAL)

        return AgentResult(
            text=text,
            chart_png=side_effects.get("chart_png"),
            chart_filename=side_effects.get("chart_filename"),
            chart_html=side_effects.get("chart_html"),
            chart_html_filename=side_effects.get("chart_html_filename"),
            sparkline_png=side_effects.get("sparkline_png"),
            sparkline_filename=side_effects.get("sparkline_filename"),
            summary_stack_png=side_effects.get("summary_stack_png"),
            summary_stack_filename=side_effects.get("summary_stack_filename"),
            summary_comparison_png=side_effects.get("summary_comparison_png"),
            summary_comparison_filename=side_effects.get("summary_comparison_filename"),
            summary_stack_html=side_effects.get("summary_stack_html"),
            summary_stack_html_filename=side_effects.get("summary_stack_html_filename"),
            summary_comparison_html=side_effects.get("summary_comparison_html"),
            summary_comparison_html_filename=side_effects.get("summary_comparison_html_filename"),
            chart_context=side_effects.get("chart_context"),
            schedule_proposal=side_effects.get("schedule_proposal"),
            provider_used=winning_label,
            model_used=winning_model,
            tool_calls_made=side_effects.get("tool_calls_made") or None,
        )
