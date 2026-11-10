import pytest

from coinowl.agent.main import wants_chart


def gap(text: str, id: str, reason: str):
    return pytest.param(text, id=id, marks=pytest.mark.xfail(strict=True, reason=reason))


_KA_NOMINATIVE = (
    "Georgian terms carry the nominative -ი ending, so other forms (dative გრაფიკს, "
    "plural ჩარტები) don't match; ვიზუალ / ინტერაქტიულ are bare stems and do"
)

CHART = [
    pytest.param("show me a BTC chart", id="en-chart"),
    pytest.param("ETH graph for the last 30 days", id="en-graph"),
    pytest.param("can you plot SOL?", id="en-plot"),
    pytest.param("visualize ADA over 90 days", id="en-visualize"),
    pytest.param("visualise DOGE please", id="en-visualise"),
    pytest.param("send me the HTML version", id="en-html"),
    pytest.param("interactive version please", id="en-interactive"),
    pytest.param("CHART BTC", id="en-uppercase"),
    pytest.param("BTC-ის ჩარტი მაჩვენე", id="ka-chart"),
    pytest.param("ETH-ის გრაფიკი 7 დღეზე", id="ka-graph"),
    pytest.param("SOL-ის ნახაზი გამიკეთე", id="ka-drawing"),
    pytest.param("ვიზუალიზაცია მინდა", id="ka-visualization"),
    pytest.param("ინტერაქტიული ვერსია გამომიგზავნე", id="ka-interactive"),
    pytest.param("покажи график BTC", id="ru-graph"),
    pytest.param("графики BTC и ETH за месяц", id="ru-graph-plural"),
    pytest.param("диаграмма ETH за неделю", id="ru-diagram"),
    pytest.param("скинь чарт SOL", id="ru-chart"),
    pytest.param("визуализируй ADA", id="ru-visualize"),
    pytest.param("интерактивную версию, пожалуйста", id="ru-interactive"),
    gap(
        "show me BTC and ETH charts",
        id="en-plural",
        reason="English words sit inside \\b...\\b, so inflected forms "
        "(charts, graphs, plots, visualization) don't match",
    ),
    gap("ETH-ის გრაფიკს მაჩვენებ?", id="ka-dative", reason=_KA_NOMINATIVE),
    gap("BTC-ის და ETH-ის ჩარტები მაჩვენე", id="ka-plural", reason=_KA_NOMINATIVE),
]

NOT_CHART = [
    pytest.param("what's BTC at?", id="en-price"),
    pytest.param("how did ETH do this week?", id="en-weekly-stats"),
    pytest.param("biggest losers today", id="en-top-movers"),
    pytest.param("add ADA to my watchlist", id="en-watchlist"),
    pytest.param("tell me when BTC hits 80k", id="en-alert"),
    pytest.param("summarize BTC's week in one paragraph", id="en-word-boundary"),
    pytest.param("BTC-ის ფასი რა არის?", id="ka-price"),
    pytest.param("ETH როგორ იყო ამ კვირაში?", id="ka-weekly-stats"),
    pytest.param("сколько стоит BTC?", id="ru-price"),
    pytest.param("как ETH на этой неделе?", id="ru-weekly-stats"),
]


@pytest.mark.parametrize("text", CHART)
def test_chart_requests_route_to_chart_provider(text):
    assert wants_chart(text)


@pytest.mark.parametrize("text", NOT_CHART)
def test_plain_questions_do_not(text):
    assert not wants_chart(text)
