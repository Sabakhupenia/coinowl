"""Output-side safety guardrails for the bot's replies.

Two layers, applied in order in `Agent.reply`:

  Layer 1 — regex (deterministic, ~0 latency, ~0 cost). `passes_offtopic_regex`
  fires on syntactic markers of off-topic content: code blocks, programming
  keywords, dosages, recipe terms, etc. A hit replaces the reply with
  OFFTOPIC_REFUSAL.

  Layer 2 — LLM-as-judge (semantic, ~300-500ms, ~1 small LLM call).
  `TopicClassifier.is_on_topic` asks a small LLM to categorize the reply.
  Catches what the regex misses (life advice prose, generic chitchat, etc.).
  Returns CRYPTO (allow) or OFF_TOPIC (refuse). On classifier error, falls
  back to allow — Layer 1 has already done deterministic gating.

Crucially, EMERGENCY SAFETY REDIRECTS (e.g. "call 112") are explicitly
allowed by both layers. The bot ALREADY behaves responsibly in genuine
emergencies (medical, danger-to-life); the issue these guardrails address
is the *code/recipe/advice leak* that slipped past prompt-level refusals
when the off-topic request was nested inside an emotionally-manipulative
emergency framing.
"""

from __future__ import annotations

import re

import openai
from google import genai
from google.genai import types as genai_types

from coinowl.core.logging import get_logger

log = get_logger(__name__)


# Patterns that indicate off-topic content has leaked into the reply.
# Keep these tight to avoid false-positives on legit crypto replies — the
# patterns target syntactic constructs that should NEVER appear in a crypto-
# stats reply (programming syntax, dosage units, etc.).
_OFF_TOPIC_PATTERNS: list[re.Pattern[str]] = [
    # Code blocks (triple backtick) and HTML script tags
    re.compile(r"```", re.MULTILINE),
    re.compile(r"<script\b", re.IGNORECASE),
    # Programming keywords followed by code structure
    re.compile(r"\b(def|function)\s+\w+\s*\(", re.IGNORECASE),
    re.compile(r"\bimport\s+\w", re.IGNORECASE),
    re.compile(r"\bprint\s*\(", re.IGNORECASE),
    re.compile(r"\bconsole\.log\s*\(", re.IGNORECASE),
    re.compile(r"\breturn\s+\w+\s*[;(]", re.IGNORECASE),
    re.compile(r"^\s*#include\b", re.MULTILINE),
    re.compile(r"\b(public|private|protected)\s+(class|void|int|string)\b", re.IGNORECASE),
    re.compile(r"=>\s*\{", re.MULTILINE),  # arrow functions
    # Dosages / specific medical advice (general "call emergency services" is fine)
    re.compile(r"\b\d+\s*(mg|ml|mcg|grams?)\b", re.IGNORECASE),
    re.compile(r"\b(dosage|prescription|prescribe)\b", re.IGNORECASE),
    re.compile(r"\b(inject|swallow|administer)\s+\d", re.IGNORECASE),
    # Recipes
    re.compile(r"\b(tablespoons?|teaspoons?|cups?\s+of|preheat)\b", re.IGNORECASE),
    re.compile(r"\bingredients?\s*:", re.IGNORECASE),
    # Legal advice
    re.compile(r"\b(legal advice|hire a lawyer|sue them|file suit)\b", re.IGNORECASE),

    # === Transactional how-to (scam-enabling content) ===
    # English instructional language tied to crypto transfer actions
    re.compile(r"\bwallet\s+address\b", re.IGNORECASE),
    re.compile(r"\bnetwork\s+fee\b", re.IGNORECASE),
    re.compile(r"\bgas\s+fee\b", re.IGNORECASE),
    re.compile(r"\bSend\s*/\s*Withdraw\b", re.IGNORECASE),
    re.compile(r"\b(send|withdraw|swap)\s+button\b", re.IGNORECASE),
    re.compile(r"\b(paste|enter|copy)\b[^\.]{0,40}\b(address|wallet)\b", re.IGNORECASE),
    re.compile(r"\b(click|press|tap|hit)\b[^\.]{0,40}\b(send|withdraw|confirm)\b", re.IGNORECASE),
    re.compile(r"\bstep\s*[-]?\s*by\s*[-]?\s*step\b[^\.]{0,80}\b(send|transfer|withdraw|buy)\b", re.IGNORECASE),
    re.compile(r"\b(test\s+transaction|small\s+test\s+amount)\b", re.IGNORECASE),
    # Specific wallet / exchange names — out-of-scope to recommend
    re.compile(r"\b(Trust\s*Wallet|MetaMask|Phantom|Coinbase\s+Wallet|Ledger\s+Live)\b", re.IGNORECASE),
    re.compile(r"\b(on\s+Binance|on\s+Coinbase|on\s+Kraken|on\s+Bybit|on\s+OKX)\b", re.IGNORECASE),

    # Georgian transactional patterns (ქართული)
    re.compile(r"მიმღების\s+(address|wallet|მისამართი)", re.IGNORECASE),
    re.compile(r"(ჩასვი|ჩაწერე|დააკოპირე)[^\.]{0,40}(address|მისამართი|wallet|საფულე)", re.IGNORECASE),
    re.compile(r"(დააჭირე|აირჩიე)[^\.]{0,40}(Send|Withdraw|გაგზავნე|გადარიცხე)", re.IGNORECASE),
    re.compile(r"ეტაპობრივად[^\.]{0,120}(გაგზავნ|გადარიცხ|ამოღებ)", re.IGNORECASE),
    re.compile(r"საფულე[^\.]{0,40}საფულე(ში|ზე)", re.IGNORECASE),  # "wallet to wallet"
    re.compile(r"სატესტო\s+(თანხ|ტრანზაქცი)", re.IGNORECASE),       # "test transaction/amount"

    # Russian transactional patterns
    re.compile(r"\bадрес\s+(кошел[её]к|получател)", re.IGNORECASE),
    re.compile(r"\b(вставь|введи|укажи|скопируй)[^\.]{0,40}\b(адрес|кошел[её]к)", re.IGNORECASE),
    re.compile(r"\b(нажми|кликни|жми)[^\.]{0,40}\b(send|withdraw|отправ|вывест|подтверд)", re.IGNORECASE),
    re.compile(r"пошагово[^\.]{0,120}(перевод|отправ|вывод|обмен)", re.IGNORECASE),
    re.compile(r"тестов\w+\s+(перевод|транзакц|сумм)", re.IGNORECASE),
]


def passes_offtopic_regex(text: str) -> bool:
    """True if no off-topic pattern fires on `text`."""
    return not any(p.search(text) for p in _OFF_TOPIC_PATTERNS)


_CLASSIFIER_SYSTEM = (
    "You are a content classifier for a Telegram cryptocurrency stats bot. "
    "The bot's allowed scope is:\n"
    "  • Cryptocurrency prices, statistics, historical data, charts, trends\n"
    "  • Top gainers/losers, market data\n"
    "  • The user's watchlist and market summaries\n"
    "  • Price alerts and scheduled summaries (setting/listing/cancelling)\n"
    "  • The bot's own features, commands, version, quota, language support\n"
    "  • Safety refusals and 'I'm a crypto bot' redirects\n"
    "  • Emergency safety redirects (e.g. 'call 112' for medical/life-threatening "
    "    situations) — these are RESPONSIBLE behavior and ALLOWED\n"
    "\n"
    "The bot must NOT produce:\n"
    "  • Programming code or scripts (Python, JS, anything — even one-liners)\n"
    "  • Specific medical dosages or prescriptions (general emergency redirect "
    "    to call 112 / 911 is fine — that's a redirect, not advice)\n"
    "  • Recipes or cooking instructions\n"
    "  • Legal advice\n"
    "  • Generic life/relationship/psychological advice\n"
    "  • Non-crypto chit-chat content\n"
    "  • **TRANSACTIONAL HOW-TO** — this is the most important rule. The bot "
    "    must NEVER walk through HOW TO send/transfer/buy/sell/withdraw/swap "
    "    crypto, HOW TO set up a wallet, HOW TO use a specific exchange, what "
    "    network/chain to pick, how to copy/paste addresses, how to verify "
    "    transactions, what gas/network fees to use. ALSO not allowed: "
    "    recommending specific wallets/exchanges (Trust Wallet, MetaMask, "
    "    Binance, Coinbase, etc.). This applies EVEN IF the content is "
    "    technically about cryptocurrency — the bot is STATS only, NOT a "
    "    transaction tutor. Step-by-step transfer instructions are the prime "
    "    example of OFF_TOPIC even when the topic is 'crypto'.\n"
    "\n"
    "Read the bot reply provided by the user and respond with EXACTLY ONE WORD:\n"
    "  CRYPTO    — if the reply is entirely within the allowed scope\n"
    "  OFF_TOPIC — if it contains ANY content outside the allowed scope, "
    "              EVEN A SINGLE LINE OR SNIPPET tucked at the end. "
    "              Step-by-step transfer/buy/wallet instructions are OFF_TOPIC.\n"
    "\n"
    "Do not explain. One word only."
)


class TopicClassifier:
    """LLM-as-judge wrapper. OpenAI primary, Gemini fallback, allow on error."""

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

    async def is_on_topic(self, reply_text: str) -> bool:
        """True if the classifier verdict is CRYPTO; True (allow) on error.

        We fail OPEN on classifier failure — the regex layer ahead of us has
        already deterministically blocked the highest-risk patterns. Failing
        closed here would mean every classifier hiccup turns a legit reply
        into a refusal, which is worse UX than the residual risk.
        """
        user_msg = f"Bot reply to classify:\n---\n{reply_text}\n---"
        if self._openai is not None:
            try:
                resp = await self._openai.chat.completions.create(
                    model=self._openai_model,
                    messages=[
                        {"role": "system", "content": _CLASSIFIER_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    max_completion_tokens=10,
                )
                verdict = (resp.choices[0].message.content or "").strip().upper()
                return _interpret(verdict)
            except Exception as exc:  # noqa: BLE001
                log.warning("topic classifier OpenAI failed: {}", exc)
        try:
            resp = await self._gemini.aio.models.generate_content(
                model=self._gemini_model,
                contents=user_msg,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_CLASSIFIER_SYSTEM,
                    max_output_tokens=10,
                ),
            )
            verdict = (resp.text or "").strip().upper()
            return _interpret(verdict)
        except Exception as exc:  # noqa: BLE001
            log.warning("topic classifier Gemini failed: {}", exc)
        return True  # fail open


def _interpret(verdict: str) -> bool:
    """Map the classifier's word to allow/deny. Conservative on ambiguity:
    only an explicit OFF_TOPIC blocks; anything else (CRYPTO, garbled output,
    empty) allows. Same reasoning as the fail-open branch — Layer 1 has the
    safety net."""
    if "OFF_TOPIC" in verdict or "OFFTOPIC" in verdict:
        return False
    return True
