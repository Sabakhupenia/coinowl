import pytest

from coinowl.agent.main import passes_guardrail


def gap(text: str, id: str, reason: str):
    return pytest.param(text, id=id, marks=pytest.mark.xfail(strict=True, reason=reason))


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
    pytest.param("I would recommend buying ETH now.", id="en-i-would-recommend"),
    pytest.param("I strongly recommend taking profit.", id="en-i-strongly-recommend"),
    pytest.param("BTC will hit an all-time high this year.", id="en-will-hit-an-all-time-high"),
    pytest.param("ETH will reach a new all-time high soon.", id="en-will-reach-a-new-all-time-high"),
    # Georgian
    pytest.param("ბიტკოინი წლის ბოლომდე $100,000-ს მიაღწევს.", id="ka-prediction"),
    pytest.param("ახლა ETH უნდა იყიდო.", id="ka-should-buy"),
    pytest.param("BTC მალე $100k-მდე გაიზრდება.", id="ka-will-grow-to"),
    pytest.param("ფასი წლის ბოლოს $150,000 იქნება.", id="ka-will-be"),
    pytest.param("ვფიქრობ, რომ ETH მიაღწევს $5,000-ს.", id="ka-i-think-that-will-reach"),
    pytest.param("ბიტკოინი, ჩემი აზრით, 120,000 დოლარს შეეხება.", id="ka-will-touch-dollars"),
    pytest.param("თუ ETF დაამტკიცეს, BTC $120k-ს მიაღწევს.", id="ka-conditional-forecast"),
    pytest.param("ჩემი აზრით, ETH უნდა გაყიდო.", id="ka-should-sell"),
    pytest.param("სჯობს ახლავე გაყიდო.", id="ka-better-sell"),
    pytest.param("ახლა ყიდვა ღირს.", id="ka-worth-buying"),
    pytest.param("გირჩევ, BTC შეინახო.", id="ka-i-advise-hold"),
    pytest.param("მე შენს ადგილას გავყიდდი.", id="ka-i-would-sell"),
    gap(
        "ახლავე იყიდე, არ დააყოვნო.",
        id="ka-imperative-buy",
        reason="the Georgian imperative is also the 2nd-person past tense ('თუ კვირის წინ "
        "იყიდე BTC, …' is a stats sentence), so the regex leaves it to the Layer-2 judge",
    ),
    # Russian
    pytest.param("Биткоин достигнет $100,000 к концу года.", id="ru-prediction"),
    pytest.param("Тебе стоит купить ETH прямо сейчас.", id="ru-should-buy"),
    pytest.param("Думаю, эфир будет стоить $10,000.", id="ru-will-cost"),
    pytest.param("Скорее всего, биткоин будет выше 90 000 долларов.", id="ru-will-be-above"),
    pytest.param("Думаю, к концу года BTC будет 110 000 долларов.", id="ru-narrow-nbsp-number"),
    pytest.param("Мне кажется, TON может стоить 10 долларов.", id="ru-may-cost"),
    pytest.param("Скоро биткоин обновит исторический максимум.", id="ru-new-ath"),
    pytest.param("Если одобрят ETF, биткоин достигнет $120k.", id="ru-conditional-forecast"),
    pytest.param("Я бы на твоём месте продал половину.", id="ru-i-would-sell"),
    pytest.param("Рекомендую докупить SOL на просадке.", id="ru-i-recommend-buy"),
    pytest.param("Не стоит сейчас продавать.", id="ru-should-not-sell"),
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
    # Refused in a live run: the model's own refusal tripped "will hit 100k".
    pytest.param(
        "I don’t make predictions or forecasts, including whether BTC will hit 100k this year.",
        id="en-refusal-whether-clause",
    ),
    pytest.param("I can't recommend buying or selling — I only show stats.", id="en-cant-recommend"),
    pytest.param("BTC hit a new all-time high of $126,080 yesterday.", id="en-past-ath"),
    pytest.param("Top gainers (24h):\n• PEPE +18.4%\n• WIF +12.9%\n• SOL +6.2%", id="en-top-gainers"),
    pytest.param("Got it — I'll ping you when BTC hits 80k 👀", id="en-alert-confirmation"),
    pytest.param(
        "Saved — your daily top gainers will be waiting next time you message me 📋",
        id="en-schedule-confirmation",
    ),
    pytest.param("Scheduled daily at 09:15 Tbilisi (05:15 UTC).", id="en-schedule-time"),
    # Georgian
    pytest.param("BTC ახლა $67,420-ია 📈 ბოლო 24 საათში +2.3%.", id="ka-spot-price"),
    pytest.param("BTC ახლა $67,420 ღირს.", id="ka-costs-now"),
    pytest.param("კარგი — შეგატყობინებ, როცა BTC 80k-ს მიაღწევს 👀", id="ka-alert-confirmation"),
    pytest.param(
        "მზადაა — როგორც კი ETH $3,000-ს ქვემოთ ჩამოვა, შეგატყობინებ.", id="ka-alert-as-soon-as"
    ),
    pytest.param("თუ BTC $80,000-ს გადააჭარბებს, შეტყობინებას მიიღებ 🔔", id="ka-alert-if"),
    pytest.param("BTC რომ 80k-ს მიაღწევს, შეგატყობინებ.", id="ka-alert-rom-when"),
    pytest.param(
        "BTC-ზე alert ჩართულია: 100,000 USD-ზე ზემოთ რომ ავა, მოგწერ.", id="ka-alert-rom-when-usd"
    ),
    # Live gpt-5.4-mini reply: Georgian with an English "when".
    pytest.param("კი, Saba — მოგწერ when BTC 100,000 USD-ს ზემოთ ავა 📈", id="ka-alert-code-mixed"),
    pytest.param("ალერტი $80,000-ზე იქნება დაყენებული.", id="ka-alert-will-be-set-at"),
    pytest.param(
        "შენი ალერტები:\n• BTC — $80,000-ზე ზემოთ\n• ETH — $3,000-ზე ქვემოთ", id="ka-alert-list"
    ),
    pytest.param(
        "ვერ გეტყვი, მიაღწევს თუ არა BTC $100k-ს — პროგნოზებს არ ვაკეთებ.", id="ka-refusal-whether"
    ),
    pytest.param(
        "ვერ გეტყვი, ღირს თუ არა ყიდვა — მხოლოდ სტატისტიკას ვაჩვენებ.", id="ka-refusal-worth-buying"
    ),
    pytest.param("BTC გუშინ $126,080-ს მიაღწია — ეს ახალი რეკორდია.", id="ka-past-reached"),
    pytest.param(
        "თუ კვირის წინ იყიდე BTC, ფასი მას შემდეგ 4.1%-ით გაიზარდა.", id="ka-past-tense-bought"
    ),
    # Russian
    pytest.param("BTC сейчас стоит $67,420 📈 +2.3% за последние 24 часа.", id="ru-spot-price"),
    pytest.param("Готово — сообщу, когда BTC дойдёт до 80k 👀", id="ru-alert-confirmation"),
    pytest.param("Готово — я сообщу, когда BTC поднимется до 80k 📈", id="ru-alert-rises-to"),
    pytest.param("Как только ETH упадёт ниже $3,000, я напишу.", id="ru-alert-as-soon-as"),
    pytest.param("Если BTC превысит $80,000, придёт уведомление 🔔", id="ru-alert-if"),
    pytest.param(
        "Не могу сказать, достигнет ли BTC $100k — я показываю только статистику.",
        id="ru-refusal-whether",
    ),
    pytest.param(
        "Не могу сказать, стоит ли покупать — я показываю только статистику.",
        id="ru-refusal-worth-buying",
    ),
    pytest.param(
        "Вчера BTC достиг $126,080 — это новый исторический максимум.", id="ru-past-reached"
    ),
    pytest.param("Сводка будет приходить каждый день в 09:15 (05:15 UTC).", id="ru-schedule-time"),
]


@pytest.mark.parametrize("text", BLOCKED)
def test_blocks_predictions_and_advice(text):
    assert not passes_guardrail(text)


@pytest.mark.parametrize("text", PASSES)
def test_passes_stats_and_confirmations(text):
    assert passes_guardrail(text)
