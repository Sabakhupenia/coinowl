## Project

CoinOwl is a Telegram bot for cryptocurrency analytics. Users chat in plain text (English, Georgian, Russian) and the bot replies with live prices, historical stats, and price chart images fetched from CoinGecko. It is explicitly a *statistics tool* — it never predicts prices or gives financial advice, enforced by both a system prompt and a regex guardrail. Single developer, pre-alpha, proprietary.

**Stack:** Python 3.12 · Telethon (Telegram MTProto client) · google-genai (Gemini 2.5 Flash, primary LLM) · anthropic (Claude Haiku 4.5, optional fallback) · httpx + CoinGecko REST API · Plotly + kaleido (PNG chart rendering) · loguru (structured logging) · python-dotenv

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

**Optional:**

| Var | Effect if absent |
|-----|-----------------|
| `ANTHROPIC_API_KEY` | Gemini-only mode, no LLM fallback |
| `COINGECKO_API_KEY` | Free tier (~5 req/min); demo key gives 30 req/min |

**First run:** Telethon opens a browser or prompts for a phone number to authenticate. This writes `coinowl_bot.session` (gitignored). Subsequent runs reuse the session silently.

**Runs locally** on the developer's Windows machine. No server, Docker, or cloud deployment.

**No test runner, no linter, no CI configured yet.** To verify a change: `python -c "from coinowl.bot.main import run; print('OK')"`.

---

## Architecture

```
main.py
  └── coinowl/bot/main.py          Telethon event loop, command handlers, quota
        └── coinowl/agent/main.py  Agent.reply() → GeminiProvider or ClaudeProvider
              └── execute_tool()   dispatches get_price / get_market_chart / get_chart
                    ├── coinowl/data/coingecko.py   async HTTP, TTL cache
                    ├── coinowl/data/symbols.py      ticker → CoinGecko ID
                    └── coinowl/charts/plotly_chart.py  PNG via kaleido
```

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

**In-memory state (resets on restart):**
- `QuotaTracker._log: dict[int, deque[datetime]]` — per user_id rolling window
- `follow_up_store: dict[int, dict]` in `bot/main.py` — last chart context per user for "yes" expansion

**No database yet.** `coinowl/db/__init__.py` is a placeholder. Supabase (hosted Postgres + pgvector) is planned for v2 (persistent quota, user records, conversation history, coin embeddings for `/similar`).

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

- **kaleido first render** takes 10–20 seconds (starts a headless browser subprocess). Subsequent renders in the same process are fast (~1s). Don't mistake the first slow render for a hang.

- **CoinGecko free tier** is ~5 req/min in practice, much tighter than documented 10-50 req/min. TTL cache handles typical traffic; set `COINGECKO_API_KEY` (demo plan) for anything beyond casual testing.

- **Quota resets on restart.** `QuotaTracker` is in-memory. A bot restart lets users bypass the 3-hour window. Acceptable for now; Postgres persistence is v2.

- **`ANTHROPIC_API_KEY` is optional.** If not set, Claude fallback is disabled silently (logged at INFO). The bot runs Gemini-only.

- **README is partially stale.** Architecture diagram still shows Groq (dropped). `/interactive` command is listed but not implemented. Roadmap phases in README don't match current commit history exactly.

- **No test suite.** `tests/__init__.py` exists but is empty. Before committing logic changes, run a quick import smoke test: `python -c "from coinowl.bot.main import run"`.

---

## Current state

**Working end-to-end:**
- Natural-language chat in English, Georgian, Russian via Gemini 2.5 Flash
- Claude Haiku 4.5 fallback (when `ANTHROPIC_API_KEY` set)
- `/price`, `/start`, `/help`, `/version`, `/disclaimer` commands
- `get_price` and `get_market_chart` LLM tools
- `get_chart` tool → Plotly PNG sent inline as Telegram photo
- Colored-square mini-chart (🟩🟥) in text stats replies
- Follow-up "yes"/"კი"/"да" expansion to last chart context
- In-memory quota: 10 messages / 3-hour window
- Identity prefilter ("who are you" → /help, no API call)
- loguru structured logging to stderr + `logs/coinowl.log` in Tbilisi time

**Placeholder / not started:**
- `coinowl/db/` — empty, waiting for Postgres+pgvector commit
- `/interactive` command (HTML chart export) — in README, not coded
- Multi-turn conversation memory — each message is stateless
- Quota persistence across restarts
- Any tests or CI

---

## Roadmap

1. **Test suite + bugfixes (now):** unit tests for guardrail regex, `_mini_chart`, `QuotaTracker`, `resolve()`, and the yes-expansion logic. Fix any bugs found during live testing.
2. **v2 — Supabase (Postgres + pgvector):** persistent user records, quota, conversation history, coin embeddings for `/similar`. Connect via Supabase Python client or psycopg. No SQLite intermediate.
3. **v3 — Alerts:** user-configured price alerts, background polling loop.
4. **/interactive:** re-render last chart as self-contained Plotly HTML file, delivered as Telegram document.
5. **CI/CD:** GitHub Actions workflow for import smoke tests and lint on push.

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
