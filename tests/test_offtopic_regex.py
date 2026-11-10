import pytest

from coinowl.agent.safety import passes_offtopic_regex


def gap(text: str, id: str, reason: str):
    return pytest.param(text, id=id, marks=pytest.mark.xfail(strict=True, reason=reason))


BLOCKED = [
    pytest.param(
        "Sure! Here's a script:\n```python\nimport requests\nprint(requests.get(url).json())\n```",
        id="code-fence",
    ),
    pytest.param("def get_price(symbol):\n    return fetch(symbol)", id="python-def"),
    pytest.param("const show = () => { console.log(price) }", id="js-arrow-function"),
    pytest.param("<script>alert(1)</script>", id="script-tag"),
    pytest.param(
        "Ingredients: 2 cups of flour, 1 teaspoon of salt. Preheat the oven to 180°C.",
        id="recipe",
    ),
    pytest.param("Take 500 mg of ibuprofen every 6 hours.", id="dosage-mg"),
    pytest.param("The usual dosage for adults is two tablets.", id="dosage-word"),
    pytest.param("Honestly, you should hire a lawyer and sue them.", id="legal-advice"),
    pytest.param(
        "Open Trust Wallet, tap Send, paste your friend's wallet address and confirm.",
        id="en-wallet-howto",
    ),
    pytest.param("You'll need the recipient's wallet address.", id="en-wallet-address"),
    pytest.param("Send a small test amount first to be safe.", id="en-test-amount"),
    pytest.param("You can buy it on Binance in a few minutes.", id="en-exchange-name"),
    pytest.param(
        "გახსენი საფულე, ჩასვი მიმღების მისამართი და დააჭირე Send-ს.",
        id="ka-wallet-howto",
    ),
    pytest.param("ჯერ სატესტო თანხა გაგზავნე.", id="ka-test-amount"),
    pytest.param("ეტაპობრივად აგიხსნი, როგორ გადარიცხო BTC.", id="ka-step-by-step"),
    pytest.param(
        "Открой кошелёк, скопируй адрес получателя и нажми «Отправить».",
        id="ru-wallet-howto",
    ),
    pytest.param("Сначала сделай тестовый перевод на небольшую сумму.", id="ru-test-transfer"),
    pytest.param("Пошагово: открой приложение, выбери BTC и отправь его другу.", id="ru-step-by-step"),
    gap(
        "Тебе понадобится адрес кошелька получателя.",
        id="ru-wallet-address",
        reason="адрес\\s+кошел[её]к only matches nominative 'кошелёк'; the real phrase "
        "'адрес кошелька' (genitive) slips through, unlike English 'wallet address'",
    ),
    gap(
        "დაგჭირდება მიმღების საფულის მისამართი.",
        id="ka-wallet-address",
        reason="no Georgian counterpart of the English 'wallet address' pattern (საფულის მისამართი)",
    ),
    gap(
        "Pick the network with the lowest gas fees.",
        id="en-gas-fees-plural",
        reason="'gas fee' / 'network fee' patterns end in \\b, so the plural 'fees' slips through",
    ),
]

ALLOWED = [
    pytest.param(
        "BTC is at $67,420 📈 +2.3% over the last 24 hours.\n"
        "Data: CoinGecko (https://www.coingecko.com)",
        id="en-spot-price",
    ),
    pytest.param(
        "Top losers (7d):\n• ARB −14.2%\n• OP −11.7%\n• APT −9.3%\n"
        "Data: CoinGecko (https://www.coingecko.com)",
        id="en-top-losers",
    ),
    pytest.param(
        "Your watchlist this week:\n• BTC $67,420 (+4.1%)\n• ETH $3,486 (−1.8%)\n"
        "• SOL $171.20 (+6.2%)\nCharts are below 📈",
        id="en-watchlist-summary",
    ),
    pytest.param("BTC's 30-day return was +12.4% (best month since March).", id="en-30d-return"),
    pytest.param(
        "BTC dominance is 54.2% and total market cap is $2.41T. 24h volume: $98.6B.",
        id="en-market-stats",
    ),
    pytest.param("Got it — I'll ping you when BTC hits 80k 👀", id="en-alert-confirmation"),
    pytest.param(
        "I'm only a crypto stats bot, but if someone's life is in danger, call 112 right now.",
        id="en-emergency-redirect",
    ),
    pytest.param(
        "I don't walk through crypto transfers or wallet setup — too easy to misuse when "
        "someone's pressuring you. For transfer instructions, check your wallet's official "
        "docs or your exchange's help center.",
        id="en-prompt-transfer-refusal",
    ),
    pytest.param(
        "BTC ახლა $67,420-ია 📈 ბოლო 24 საათში +2.3%.\n"
        "მონაცემები: CoinGecko (https://www.coingecko.com)",
        id="ka-spot-price",
    ),
    pytest.param(
        "შენი ვოჩლისტი ამ კვირაში:\n• BTC $67,420 (+4.1%)\n• ETH $3,486 (−1.8%)\n"
        "გრაფიკები ქვემოთაა 📈",
        id="ka-watchlist-summary",
    ),
    pytest.param(
        "კრიპტოს გადარიცხვას ან საფულის გახსნას არ ვასწავლი — საფრთხეა, თუ ვინმე "
        "გაიძულებს. ინსტრუქციისთვის ნახე საფულის ან ბირჟის ოფიციალური დოკუმენტაცია.",
        id="ka-prompt-transfer-refusal",
    ),
    pytest.param(
        "BTC сейчас стоит $67,420 📈 +2.3% за последние 24 часа.\n"
        "Данные: CoinGecko (https://www.coingecko.com)",
        id="ru-spot-price",
    ),
    pytest.param("Лидеры падения за 7 дней:\n• ARB −14.2%\n• OP −11.7%", id="ru-top-losers"),
    pytest.param(
        "Я не объясняю как переводить крипту или настраивать кошелёк — слишком легко "
        "обмануть человека под давлением. За инструкциями обращайтесь к официальной "
        "документации кошелька или биржи.",
        id="ru-prompt-transfer-refusal",
    ),
]


@pytest.mark.parametrize("text", BLOCKED)
def test_blocks_offtopic_content(text):
    assert not passes_offtopic_regex(text)


@pytest.mark.parametrize("text", ALLOWED)
def test_allows_stats_replies(text):
    assert passes_offtopic_regex(text)
