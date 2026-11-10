import pytest

from coinowl.core.config import _parse_openai_model_caps

DEFAULTS = {"gpt-5.4": 220_000, "gpt-5.4-mini": 2_200_000}


@pytest.mark.parametrize("raw", [None, ""])
def test_defaults_when_unset(raw):
    assert _parse_openai_model_caps(raw) == DEFAULTS


def test_single_override_keeps_other_default():
    assert _parse_openai_model_caps("gpt-5.4=180000") == {
        "gpt-5.4": 180_000,
        "gpt-5.4-mini": 2_200_000,
    }


def test_overrides_both():
    assert _parse_openai_model_caps("gpt-5.4=180000,gpt-5.4-mini=1800000") == {
        "gpt-5.4": 180_000,
        "gpt-5.4-mini": 1_800_000,
    }


def test_tolerates_whitespace():
    assert _parse_openai_model_caps(" gpt-5.4 = 180000 , gpt-5.4-mini=1800000 ") == {
        "gpt-5.4": 180_000,
        "gpt-5.4-mini": 1_800_000,
    }


def test_adds_unknown_model_alongside_defaults():
    assert _parse_openai_model_caps("gpt-6=50000") == {**DEFAULTS, "gpt-6": 50_000}


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("gpt-5.4", id="no-equals"),
        pytest.param("gpt-5.4=abc", id="non-int"),
        pytest.param("gpt-5.4=1.5e5", id="float"),
        pytest.param("gpt-5.4=", id="empty-value"),
        pytest.param(",,,", id="empty-pairs"),
    ],
)
def test_skips_bad_entries(raw):
    assert _parse_openai_model_caps(raw) == DEFAULTS


def test_applies_good_entries_next_to_bad_ones():
    assert _parse_openai_model_caps("gpt-5.4=abc,gpt-5.4-mini=1800000,garbage") == {
        "gpt-5.4": 220_000,
        "gpt-5.4-mini": 1_800_000,
    }


def test_does_not_mutate_defaults_between_calls():
    _parse_openai_model_caps("gpt-5.4=1")
    assert _parse_openai_model_caps(None) == DEFAULTS
