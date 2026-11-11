# CoinOwl web app

Standalone web console for the CoinOwl bot — the "see and steer" surface for a chat-first agent.
Telegram stays the chat; this is where you look at charts, manage alerts and schedules, and edit what the agent remembers.

**Stack:** Vite · React 19 · TypeScript · Tailwind v4 · shadcn/ui (Radix) · Kibo UI (Ticker, Status, RelativeTime, Pill) · Lightweight Charts · cmdk · Sonner.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # dist/  (normal, code-split)
npx vite build -c vite.artifact.config.ts   # dist-artifact/index.html — single file for sharing
```

## Layouts

- **Standard** (default, mobile-friendly): rail + pages. Gold-on-navy brand, dark by default.
- **Advanced** (wide screens ≥ 1100px only): one-screen workbench — watchlist · coin workspace · agent pane — with an omnibox that understands `btc 30d`, `alert eth below 3800`, `compare btc eth`, `why did sol drop`. Toggle in the top bar shows a disclaimer first; narrow screens fall back to standard automatically.

Query overrides for deep links / demos: `?ui=advanced&lang=ka&theme=light`.

## Two kinds of language

- **Site language** (`lib/i18n.tsx`, switch in the top bar): the UI strings, EN / KA. Stored per device.
- **Bot languages** (Settings → Profile, or the account menu): the languages the *bot* may reply in. Server state (`users.preferred_languages`). The two never touch.

## Data

`src/lib/mock.ts` is a seeded sample-data layer (shared market factor so `/similar` correlations are real). Every consumer goes through `lib/mock.ts`, `lib/store.ts` (user state) and `lib/chat.ts` (thread) — those three files are what the FastAPI client replaces.

Chat components in `components/chat/` mirror the AI Elements API (Conversation / Message / PromptInput / Tool / Suggestion) without its markdown/mermaid/katex payload; swap for AI Elements if richer rendering is wanted.
