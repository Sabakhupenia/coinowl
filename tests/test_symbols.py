import pytest

from coinowl.data.symbols import SYMBOLS, resolve


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BTC", "bitcoin"),
        ("ETH", "ethereum"),
        ("TON", "the-open-network"),
        ("AVAX", "avalanche-2"),
    ],
)
def test_known_ticker(raw, expected):
    assert resolve(raw) == expected


@pytest.mark.parametrize("raw", ["btc", "Btc", "bTC"])
def test_case_insensitive(raw):
    assert resolve(raw) == "bitcoin"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  BTC  ", "bitcoin"),
        ("\tsol\n", "solana"),
        ("  pepe ", "pepe"),
    ],
)
def test_strips_surrounding_whitespace(raw, expected):
    assert resolve(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PEPE", "pepe"),
        ("Shiba-Inu", "shiba-inu"),
        ("bitcoin", "bitcoin"),
    ],
)
def test_unknown_passes_through_lowercased(raw, expected):
    assert resolve(raw) == expected


def test_table_keys_are_uppercase():
    # resolve() looks up cleaned.upper(), so a lowercase key could never be hit.
    assert all(key == key.upper() for key in SYMBOLS)
