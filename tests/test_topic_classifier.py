import pytest

from coinowl.agent.safety import (
    _CLASSIFIER_SYSTEM,
    VERDICT_OFF_TOPIC,
    VERDICT_OK,
    VERDICT_PREDICTION,
    _interpret,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("OK", VERDICT_OK, id="ok"),
        pytest.param("OFF_TOPIC", VERDICT_OFF_TOPIC, id="off-topic"),
        pytest.param("OFFTOPIC", VERDICT_OFF_TOPIC, id="off-topic-no-underscore"),
        pytest.param("OFF_TOPIC.", VERDICT_OFF_TOPIC, id="off-topic-trailing-dot"),
        pytest.param("PREDICTION", VERDICT_PREDICTION, id="prediction"),
        pytest.param("OFF", VERDICT_OFF_TOPIC, id="off-topic-cut-by-token-limit"),
        pytest.param("PRED", VERDICT_PREDICTION, id="prediction-cut-by-token-limit"),
    ],
)
def test_explicit_verdicts(raw, expected):
    assert _interpret(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("", id="empty"),
        pytest.param("CRYPTO", id="legacy-allow-word"),
        pytest.param("CR", id="truncated-allow-word"),
        pytest.param("I CANNOT CLASSIFY THIS", id="garbled"),
    ],
)
def test_anything_else_fails_open(raw):
    assert _interpret(raw) == VERDICT_OK


@pytest.mark.parametrize("word", ["OK", "PREDICTION", "OFF_TOPIC"])
def test_prompt_asks_for_the_words_the_parser_reads(word):
    # A label renamed in the prompt but not in _interpret would silently fail open.
    assert f"  {word} " in _CLASSIFIER_SYSTEM
