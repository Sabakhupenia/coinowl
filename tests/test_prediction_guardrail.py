import pytest

from coinowl.agent.main import passes_guardrail


def gap(text: str, id: str, reason: str):
    return pytest.param(text, id=id, marks=pytest.mark.xfail(strict=True, reason=reason))


_EN_ONLY = "prediction/advice patterns are English-only; Georgian and Russian replies are never checked"

BLOCKED = [
    pytest.param("BTC will hit $80k", id="will-hit-dollar"),
    pytest.param("it will reach 80,000", id="will-reach-comma-number"),
    pytest.param("you should buy", id="should-buy"),
    pytest.param("my price target is", id="price-target"),
    pytest.param("ETH will reach new highs", id="will-reach-new-highs"),
    pytest.param("BTC will hit 100k by December.", id="will-hit-k-suffix"),
    pytest.param("ETH will be $5,000 next year.", id="will-be-dollar"),
    pytest.param("ADA will hit all-time highs this cycle.", id="will-hit-all-time"),
    pytest.param("SOL will go to the moon 🚀", id="will-go-to-the-moon"),
    pytest.param("BTC is going to $100k.", id="is-going-to-dollar"),
    pytest.param("You should sell before the weekend.", id="should-sell"),
    pytest.param("If you ask me, you should hold.", id="should-hold"),
    pytest.param("I recommend holding BTC.", id="i-recommend"),
    pytest.param("I'd recommend buying some ETH while it's this low.", id="id-recommend"),
    pytest.param("I’d recommend taking some profit here.", id="id-recommend-curly-apostrophe"),
    pytest.param("BTC WILL HIT $80K", id="uppercase"),
    pytest.param(
        "BTC is at $67,420 (+2.3% in 24h).\nHonestly, it will reach 80,000 soon.",
        id="leak-inside-stats-reply",
    ),
    gap(
        "I would recommend buying ETH now.",
        id="en-i-would-recommend",
        reason="recommend pattern needs 'I recommend' / \"I'd recommend\" back to back; "
        "any word in between ('would', 'strongly') slips through",
    ),
    gap(
        "BTC will hit an all-time high this year.",
        id="en-will-hit-an-all-time-high",
        reason="new-highs/ATH pattern needs the phrase right after the verb; an article slips through",
    ),
    gap("ბიტკოინი წლის ბოლომდე $100,000-ს მიაღწევს.", id="ka-prediction", reason=_EN_ONLY),
    gap("ახლა ETH უნდა იყიდო.", id="ka-should-buy", reason=_EN_ONLY),
    gap("Биткоин достигнет $100,000 к концу года.", id="ru-prediction", reason=_EN_ONLY),
    gap("Тебе стоит купить ETH прямо сейчас.", id="ru-should-buy", reason=_EN_ONLY),
]

PASSES = [
    pytest.param("your summary will be ready at 9am", id="summary-ready-at-9am"),
    pytest.param("it will hit your inbox tomorrow", id="hit-your-inbox"),
    pytest.param(
        "BTC is at $67,420 📈 +2.3% over the last 24 hours.\n"
        "Data: CoinGecko (https://www.coingecko.com)",
        id="en-spot-price",
    ),
    pytest.param(
        "Over the last 7 days ETH ranged from $3,112 to $3,486 and is down 1.8% 📉\n"
        "Want the 30-day view?",
        id="en-7d-range",
    ),
    pytest.param(
        "I don't make predictions, but here's how BTC has moved over the last 7 days: "
        "+4.1%, from $64,210 to $66,840.",
        id="en-prompt-refusal-with-stats",
    ),
    pytest.param("Top gainers (24h):\n• PEPE +18.4%\n• WIF +12.9%\n• SOL +6.2%", id="en-top-gainers"),
    pytest.param("Got it — I'll ping you when BTC hits 80k 👀", id="en-alert-confirmation"),
    pytest.param(
        "Saved — your daily top gainers will be waiting next time you message me 📋",
        id="en-schedule-confirmation",
    ),
    pytest.param("Scheduled daily at 09:15 Tbilisi (05:15 UTC).", id="en-schedule-time"),
    pytest.param("BTC ახლა $67,420-ია 📈 ბოლო 24 საათში +2.3%.", id="ka-spot-price"),
    pytest.param("კარგი — შეგატყობინებ, როცა BTC 80k-ს მიაღწევს 👀", id="ka-alert-confirmation"),
    pytest.param("BTC сейчас стоит $67,420 📈 +2.3% за последние 24 часа.", id="ru-spot-price"),
    pytest.param("Готово — сообщу, когда BTC дойдёт до 80k 👀", id="ru-alert-confirmation"),
]


@pytest.mark.parametrize("text", BLOCKED)
def test_blocks_predictions_and_advice(text):
    assert not passes_guardrail(text)


@pytest.mark.parametrize("text", PASSES)
def test_passes_stats_and_confirmations(text):
    assert passes_guardrail(text)
