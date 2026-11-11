import pytest

from coinowl.agent.main import wants_chart


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
    pytest.param("show me BTC and ETH charts", id="en-plural"),
    pytest.param("graphs for SOL and ADA", id="en-graphs"),
    pytest.param("plotting DOGE over 90 days", id="en-plotting"),
    pytest.param("a visualization of BTC this month", id="en-visualization"),
    pytest.param("ETH-ის გრაფიკს მაჩვენებ?", id="ka-dative"),
    pytest.param("BTC-ის და ETH-ის ჩარტები მაჩვენე", id="ka-plural"),
    pytest.param("BTC-ის გრაფიკები 30 დღეზე", id="ka-graph-plural"),
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
    # გრაფიკი also means "schedule"; these list or cancel scheduled pushes.
    pytest.param("რა გრაფიკი მაქვს?", id="ka-schedule-list"),
    pytest.param("რა გრაფიკები მაქვს ჩართული?", id="ka-schedule-list-plural"),
    pytest.param("გააუქმე ყოველდღიური გრაფიკი", id="ka-schedule-cancel"),
    pytest.param("ორშაბათის გრაფიკი წაშალე", id="ka-schedule-delete"),
    pytest.param("сколько стоит BTC?", id="ru-price"),
    pytest.param("как ETH на этой неделе?", id="ru-weekly-stats"),
]


@pytest.mark.parametrize("text", CHART)
def test_chart_requests_route_to_chart_provider(text):
    assert wants_chart(text)


@pytest.mark.parametrize("text", NOT_CHART)
def test_plain_questions_do_not(text):
    assert not wants_chart(text)
