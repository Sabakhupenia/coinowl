"""Ticker-symbol → CoinGecko-ID resolution.

CoinGecko's API uses string IDs like "bitcoin", "ethereum", "avalanche-2".
Users will type "BTC", "eth", "AVAX". This module bridges the gap with a
small hardcoded table covering the most-queried coins.

Unknown symbols pass through (lowercased) so power users can supply a
CoinGecko ID directly. The eventual error from CoinGecko (404 / empty result)
is the natural failure mode for genuinely unknown coins.
"""

from __future__ import annotations

SYMBOLS: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "USDC": "usd-coin",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "SOL": "solana",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "TON": "the-open-network",
    "DOT": "polkadot",
    "TRX": "tron",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "ATOM": "cosmos",
    "UNI": "uniswap",
    "NEAR": "near",
    "XLM": "stellar",
}


def resolve(symbol_or_id: str) -> str:
    cleaned = symbol_or_id.strip()
    return SYMBOLS.get(cleaned.upper(), cleaned.lower())
