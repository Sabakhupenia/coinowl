## Project

CoinOwl is a Telegram bot for cryptocurrency analytics. Users chat in plain text (English, Georgian, Russian) and the bot replies with live prices, historical stats, and price chart images fetched from CoinGecko. It is explicitly a *statistics tool* — it never predicts prices or gives financial advice, enforced by both a system prompt and a regex guardrail. Single developer, pre-alpha, proprietary.

**Stack:** Python 3.12 · Telethon (Telegram MTProto client) · openai (gpt-5.4-mini, primary LLM for non-chart messages) · google-genai (Gemini 2.5 Flash, primary for chart messages; `gemini-embedding-001` @ 768d for message embeddings) · anthropic (Claude Haiku 4.5, last-resort fallback) · Supabase Postgres + asyncpg + pgvector (user profile, quota, chat history with embeddings) · httpx + CoinGecko REST API · Plotly + kaleido (PNG/HTML chart rendering, brand gold-on-navy palette) · loguru (structured logging) · python-dotenv

---

## Run it

```bash
# one-time setup
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

# start bot
python main.py
```

**Required env vars** (copy `.env.example` → `.env`, fill in):

| Var | How to get |
|-----|-----------|
| `TELEGRAM_API_ID` | my.telegram.org → API development tools |
| `TELEGRAM_API_HASH` | same |
| `TELEGRAM_BOT_TOKEN` | @BotFather on Telegram |
| `GEMINI_API_KEY` | aistudio.google.com |
| `DATABASE_URL` | Supabase Session Pooler URL (port 5432). Dashboard → Settings → Database → "Session Pooler". Enable the `vector` extension at Database → Extensions before first run. |

**Optional:**

| Var | Effect if absent |
|-----|-----------------|
| `OPENAI_API_KEY` | All queries route to Gemini (no intent split, no quota relief) |
| `OPENAI_MODEL` | Defaults to `gpt-5.4-mini` (2.5M tokens/day free) |
| `ANTHROPIC_API_KEY` | No last-resort fallback; if both OpenAI and Gemini fail, user sees an error |
| `COINGECKO_API_KEY` | Free tier (~5 req/min); demo key gives 30 req/min |

**First run:** Telethon opens a browser or prompts for a phone number to authenticate. This writes `coinowl_bot.session` (gitignored). Subsequent runs reuse the session silently.

**Runs locally** on the developer's Windows machine. No server, Docker, or cloud deployment.

**No test runner, no linter, no CI configured yet.** To verify a change: `python -c "from coinowl.bot.main import run; print('OK')"`.

---

## Architecture

```
main.py
  └── coinowl/bot/main.py          Telethon event loop, command handlers, quota
        └── coinowl/agent/main.py  Agent.reply() → intent-routed provider chain:
                                     chart keywords → Gemini → OpenAI → Claude
                                     otherwise      → OpenAI → Gemini → Claude
              └── execute_tool()   dispatches get_price / get_market_chart /
                                   get_top_movers / get_chart / get_chart_html /
                                   set_user_profile / update_watchlist /
                                   get_watchlist / get_market_summary /
                                   recall_past_conversations
                    ├── coinowl/data/coingecko.py        async HTTP, TTL cache
                    ├── coinowl/data/symbols.py          ticker → CoinGecko ID
                    └── coinowl/charts/plotly_chart.py   bar PNG via kaleido,
                                                         interactive HTML via to_html
```

**Intent router:** `wants_chart()` in `agent/main.py` matches `_CHART_INTENT_RE` —
chart/graph/plot/visualize/html (EN), ჩარტი/გრაფიკი/ნახაზი/ვიზუალ/ინტერაქტიულ (KA),
график/диаграмм/чарт/визуализ/интерактивн (RU). True → Gemini-first; False → OpenAI-first.
The chart PNG/HTML is rendered by Plotly + kaleido regardless of which LLM is in front;
the routing exists only to conserve Gemini's per-day quota for messages that explicitly
ask for charts (Gemini's tool-calling path is the one we've battle-tested for charts).

**Key files:**

| File | Why it matters |
|------|---------------|
| `coinowl/bot/main.py` | All Telegram wiring: commands, quota, follow-up expansion, chart delivery |
| `coinowl/agent/main.py` | LLM dual-provider loop, tool dispatcher, `AgentResult` dataclass, output guardrail |
| `coinowl/agent/prompts.py` | `SYSTEM_PROMPT` — safety rules, language matching, tool instructions |
| `coinowl/core/config.py` | `load_settings()` — single place for env var loading; raises `MissingEnvVarError` on missing required vars |
| `coinowl/core/logging.py` | loguru config with Tbilisi timezone patcher; call `configure_logging()` once at startup |
| `coinowl/data/coingecko.py` | `CoinGeckoClient` async context manager, error subclasses, `PricePoint` dataclass |

**Data flow (chat message):**
```
Telegram message
  → bot/main.py: identity check → quota check → yes-expansion
  → Agent.reply(text) → GeminiProvider.chat() [tool loop ≤5 iterations]
  → execute_tool() writes side_effects dict (chart_png, chart_context)
  → AgentResult(text, chart_png, chart_context)
  → bot: send_file() if chart_png else reply()
```

**Data flow (tool call):**
```
execute_tool("get_chart", {symbol, days}, cg, side_effects)
  → cg.get_market_chart() → list[PricePoint]
  → generate_price_chart() [kaleido thread] → bytes
  → side_effects["chart_png"] = bytes
  → returns {"chart": "ready", ...} JSON to LLM
```

---

## Data

**CoinGecko REST API** (`https://api.coingecko.com/api/v3`)
- `GET /simple/price` — spot price, 30s TTL cache
- `GET /coins/{id}/market_chart` — OHLCV timeseries, 300s TTL cache
- Auth: optional `x-cg-demo-api-key` header; without it, rate limit is ~5 req/min
- Attribution required in every reply: `ATTRIBUTION = "Data: CoinGecko (https://www.coingecko.com)"`

**Ticker map:** `coinowl/data/symbols.py` — 20 tickers hardcoded. `resolve(symbol)` is case-insensitive; unknown symbols pass through as-is (CoinGecko accepts full IDs like `the-open-network`).

**Postgres-backed state (persists across restarts):**
- `users` — identity, display_name, preferred_languages, watched_coins, onboarded flag, digest config
- `quota_log` — rolling per-user message-rate window (replaces in-memory `QuotaTracker`)
- `messages` — full chat history (user + assistant turns) with Gemini 768d embeddings for RAG over past Q&A

**In-memory state (resets on restart):**
- `follow_up_store: dict[int, dict]` in `bot/main.py` — last chart context per user for "yes" expansion (when a chart tool ran)
- `last_reply_store: dict[int, str]` in `bot/main.py` — last assistant text per user; used when "yes" arrives but no chart tool was called (multi-turn-lite)

**Database:** Supabase Postgres with `pgvector`. Schema lives in versioned `migrations/NNN_*.sql` files at the project root; `coinowl/db/migrate.py` runs them once on startup, tracked in `schema_versions`. asyncpg pool is the only DB driver — no `psycopg2` (it's sync and would block the event loop). Watchlist/alerts/digest tables land in v0.7.1+.

**Secrets:** `.env` only, gitignored. Never in `.env.example`, never in logs (loguru file sink at `logs/coinowl.log`).

---

## Conventions

**Logging:** loguru with `{}` format strings, never `%s`. All timestamps in Asia/Tbilisi (UTC+4, no DST). Get a logger with `log = get_logger(__name__)` — this binds `component=<module name>`. Call `configure_logging()` once in `main.py` before anything else.

**Tool errors:** `execute_tool()` always returns a `dict`, never raises. Errors go in `{"error": "..."}` so the LLM can apologize naturally. Raising would drop the whole turn.

**Side effects:** Non-text results (chart PNG bytes, chart context for follow-up) are written into the mutable `side_effects: dict` param passed to `execute_tool()`. This dict flows up through the provider's tool loop and is unpacked into `AgentResult`.

**Safety constraints (hard):** The system prompt and guardrail regex together enforce no predictions, no buy/sell/hold advice. Don't weaken either. The guardrail in `agent/main.py:_PREDICTION_PATTERNS` is a belt-and-braces backstop — it fires even if the prompt slips.

**Language:** Georgian (ქართული) is a first-class audience. Any change to the system prompt must preserve `"always match theirs"` language instruction. Model choice is constrained by Georgian support — Gemini and Claude pass; Groq's gpt-oss family does not (dropped 2026-05-12).

**Version bump:** `coinowl/__init__.py:__version__`. No pyproject.toml — version lives only here.

**Commit style:** one logical unit per commit, imperative subject line, Co-Authored-By trailer.

---

## Gotchas

- **`*.session` files** contain Telethon auth state. They are gitignored but must exist on the machine running the bot. Deleting them forces re-authentication. Never commit them.

- **`ZoneInfo("Asia/Tbilisi")` on Windows** requires the `tzdata` package (added to requirements.txt with `sys_platform == "win32"` guard). Without it you get `ZoneInfoNotFoundError` at startup.

- **kaleido < 1.0 is broken** as of 2026. `kaleido>=1.0` is required (pinned in requirements.txt). kaleido 0.2.x deprecated itself; `fig.to_image()` hangs or fails silently on that version.

- **kaleido first render** takes 10–20 seconds (starts a headless browser subprocess). Subsequent renders in the same process are fast (~1s). Don't mistake the first slow render for a hang. The sparkline rendered per stats reply doubles render volume — caching is v2/Supabase work.

- **Telegram edit rate limit** is roughly 1 edit per second per message. `StreamingReply` in `bot/main.py` debounces via a single pending task; never call `msg.edit` directly from elsewhere when streaming is active or you'll trip `FloodWait`.

- **Telethon parse mode is HTML.** Set on `client.parse_mode = "html"` at startup. Any bot-generated text that flows into Telegram (LLM replies, captions, status edits, hardcoded `_HELP_TEXT` etc.) must be HTML-safe — run dynamic strings through `_esc()` (which is `html.escape`). Hardcoded constants need literal `<` / `>` replaced with `&lt;` / `&gt;` in source. The quota footer uses `<blockquote>…</blockquote>` for a colored vertical bar.

- **Supabase direct connection (`db.<ref>.supabase.co:5432`) is IPv6-only** without the paid IPv4 add-on. Use the **Session Pooler** URL instead (`aws-0-<region>.pooler.supabase.com:5432`, compound username `postgres.<project-ref>`). Direct port 5432 will hang on connect from IPv4-only networks.

- **`pgvector` ivfflat indexes** cap at 2000 dimensions; we pin Gemini embeddings to **768d** via `output_dimensionality=768` to stay inside that limit. Switching providers/sizes is a schema change (the `vector(N)` column type carries the dimension).

- **Message logging is fire-and-forget.** Each chat turn spawns `asyncio.create_task(log_message(...))` instead of awaiting — embeddings + INSERTs must not block the user-facing reply.

- **No `psycopg2`.** Supabase's quickstart suggests it; ignore. We're async-first and use `asyncpg`.

- **Brand palette is fixed.** Gold (`#D4AF37`) line, soft gold fill, dark navy (`#0a0a1a`) paper, cream (`#F5E6C8`) text, copper (`#C04A2A`) for negative sparklines. Don't reintroduce the old green-on-blue scheme. If `assets/logo.png` exists (transparent-bg PNG), it's embedded bottom-right at ~35% opacity; missing file → chart renders without it (no failure).

- **CoinGecko free tier** is ~5 req/min in practice, much tighter than documented 10-50 req/min. TTL cache handles typical traffic; set `COINGECKO_API_KEY` (demo plan) for anything beyond casual testing.

- **`get_market_summary` issues one fetch per watchlist coin** (capped at 10 by `WATCHLIST_MAX`) and serializes via `asyncio.Semaphore(2)` to stay under free-tier rate limits. First-time summaries take ~5-10s; subsequent fetches inside the 300s `MARKET_CHART_TTL_SEC` are instant.

- **Onboarding now collects three fields** (name + languages + ≥1 coin). The `onboarded` flag is computed in SQL from `display_name`, `preferred_languages`, `watched_coins` — if any is missing, the bot re-enters the onboarding loop on the next message. Reset via `DELETE FROM users WHERE user_id = <uid>` if a row is wedged.

- **Conversation memory is two-tier.** Tier 1 (always-on, no embedding cost): the chat handler injects the user's last 6 turns from the `messages` table into the system instruction as a `## RECENT CONVERSATION` block — that's how "yes" handling survives bot restart. Tier 2 (on-demand, one embedding call): the LLM calls `recall_past_conversations(query)` when it needs to recall something older than the recent block. Don't add Tier-2 retrieval to every turn — defeats the cost argument.

- **Quota resets on restart.** `QuotaTracker` is in-memory. A bot restart lets users bypass the 3-hour window. Acceptable for now; Postgres persistence is v2.

- **`ANTHROPIC_API_KEY` is optional.** Disabled silently if unset (logged at INFO). The remaining chain (OpenAI ↔ Gemini) still works.

- **`OPENAI_API_KEY` is optional but recommended.** Without it, every message routes to Gemini and the per-day RPD limit becomes the bottleneck. With it, only chart-keyword messages hit Gemini.

- **OpenAI free-tier model defaults to `gpt-5.4-mini`.** 2.5M tokens/day on the traffic-share tier. Override with `OPENAI_MODEL=gpt-5.4` for higher quality (250K/day budget). The chart-render path is unaffected by model choice — Plotly does the rendering.

- **README is partially stale.** Architecture diagram still shows Groq (dropped). `/interactive` command is listed but not implemented. Roadmap phases in README don't match current commit history exactly.

- **No test suite.** `tests/__init__.py` exists but is empty. Before committing logic changes, run a quick import smoke test: `python -c "from coinowl.bot.main import run"`.

---

## Current state

**Working end-to-end:**
- Natural-language chat in English, Georgian, Russian via OpenAI gpt-5.4-mini (primary for non-chart messages) or Gemini 2.5 Flash (primary for chart messages)
- Silent fallback chain: if the primary LLM throws, the other one picks up the same message without user-visible notice (logged at warning level)
- Claude Haiku 4.5 as last-resort fallback (when `ANTHROPIC_API_KEY` set)
- `/price`, `/start`, `/help`, `/version`, `/disclaimer` commands
- `get_price` and `get_market_chart` LLM tools
- `get_top_movers` tool → top N gainers/losers across the whole market in 24h/7d/30d, via CoinGecko `/coins/markets`. Handles "biggest losers today", "top gainers this week" style questions in EN/KA/RU
- Per-user **watchlist** (capped at 10 coins) collected during onboarding alongside name + languages; mutated via `update_watchlist(symbols, mode='add'|'remove'|'replace')`; readable via `get_watchlist`
- `get_market_summary(window)` tool → prices + percent changes + **two composite PNG charts** (vertical stack of mini area charts, one per coin + normalized %-change comparison overlay) for the user's watchlist. Window auto-picked by LLM (24h/7d/30d) from user phrasing
- **Conversation memory (RAG)**: every chat turn is logged + embedded; the bot injects the user's last 6 turns into the system context for free on every reply (survives bot restart). For older recall, the LLM can call `recall_past_conversations(query)` which embeds the query and runs pgvector cosine search over the user's full chat history
- `get_chart` tool → Plotly **area** chart PNG (y-axis zoomed to actual price range, not anchored at $0) sent inline as Telegram photo (named `SYM_Nd.png`)
- `get_chart_html` tool → interactive Plotly HTML sent as Telegram document; offered after every PNG chart, only generated when user confirms
- 200×40 inline **sparkline PNG** auto-attached to every stats reply (replaces the old 🟩🟥 emoji-square mini-chart)
- Streaming responses with tool-call status: bot sends "🦉 …" placeholder, edits it to "🔎 Looking up BTC price…" while CoinGecko fetches, then streams the LLM's text reply via debounced edits (~1 edit/sec to respect Telegram throttle)
- Follow-up "yes"/"კი"/"да" expansion: **prefers** last-reply preamble when the LLM's prior offer mentioned chart/HTML (so a "yes" to "Want a chart?" actually fires `get_chart`); falls back to chart-context shortcut for stats follow-ups
- In-memory quota: 10 messages / 3-hour window
- Identity prefilter ("who are you" → /help, no API call)
- loguru structured logging to stderr + `logs/coinowl.log` in Tbilisi time

**Placeholder / not started:**
- Price alerts (v0.7.3)
- Daily digest scheduler (v0.7.4)
- News fetcher + `knowledge_chunks` RAG (CoinDesk RSS source decided; subsystem unbuilt)
- `coins` table + `/similar` tool (needs CoinGecko coin-detail bootstrap)
- Server-side cache of generated charts (re-renders identical chart/HTML on every call today)
- Any tests or CI

---

## Roadmap

1. **v0.7.3 — Price alerts:** `alerts` table, user-configured polling intervals (5m / 30m / 1h / daily / custom), background watcher task that wakes per-alert, Telegram push on threshold cross. Example user-flow: "tell me when BTC reaches $80k or drops below $75k" → bot stores two alerts → watcher pings user when either threshold crosses. Survives bot restart (state lives in Postgres).
2. **v0.7.4 — Daily digest:** per-user schedule, auto-pushed market summary at configured hour (reuses v0.7.1 summary tooling + v0.7.3 push channel).
3. **News RAG:** CoinDesk RSS → `knowledge_chunks` with Gemini embeddings → grounded "why did X drop?" answers.
4. **`/similar` tool:** bootstrap `coins` table from CoinGecko coin-detail endpoints + embed; vector similarity search.
5. **Chart render cache:** key by `(symbol, days, kind)`; skip kaleido on repeats.
6. **Test suite + CI:** unit tests for guardrail regex, `wants_chart`, `resolve()`, yes-expansion, quota math. GitHub Actions for import smoke + lint.

---

## Working with Claude

- **Minimal diffs.** Edit only what the task requires. Don't clean up surrounding code or add abstractions not needed by the current change.
- **No comments** unless the WHY is non-obvious (a hidden constraint, a workaround, a surprising invariant). Never describe WHAT the code does.
- **Log format is `{}`** (loguru), never `%s`/`%r`. Migrate any new stdlib-style calls.
- **Tool errors are dicts.** If adding a new tool branch in `execute_tool()`, return `{"error": "..."}` on failure — do not raise.
- **Safety is non-negotiable.** Never remove or weaken the guardrail patterns in `agent/main.py` or the prediction/advice prohibitions in `SYSTEM_PROMPT`.
- **Georgian is first-class.** Any change that might affect multilingual behavior needs explicit verification.
- **No tests exist.** Don't add test stubs or pytest scaffolding unless the user asks. Do run import smoke tests before committing.
- **Commit after each logical unit.** Don't batch unrelated changes.
- **No SQLite.** Persistence target is Supabase (Postgres + pgvector). Don't introduce a SQLite intermediate.
- **No email/password auth.** `event.sender_id` (Telegram user_id) is identity. Passwords typed in Telegram are visible in chat history and log files.
