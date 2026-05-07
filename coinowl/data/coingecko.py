"""Async wrapper around the CoinGecko free API.

Free tier needs no API key but rate-limits aggressively (~5 req/min from a
residential IP in practice). The optional `api_key` argument enables the demo
plan (~30 req/min after free signup at coingecko.com) by sending the
`x-cg-demo-api-key` header. The base URL is the same for both tiers; the pro
plan uses a different host and is not supported here.

Includes an in-memory TTL cache so back-to-back queries for the same coin
don't burn through the rate budget. Cache scope is per client instance and
not shared across bot restarts.

Usage:
    async with CoinGeckoClient(api_key=settings.coingecko_api_key) as cg:
        price = await cg.get_price("bitcoin")
        chart = await cg.get_market_chart("bitcoin", days=7)

CoinGecko data must be attributed wherever it is displayed (any tier). Use
the `ATTRIBUTION` constant when surfacing data in bot replies. See:
https://brand.coingecko.com/resources/attribution-guide
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, NamedTuple, Self

import httpx

from coinowl.core.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://api.coingecko.com/api/v3"
_DEFAULT_TIMEOUT = 10.0

ATTRIBUTION = "Data: CoinGecko (https://www.coingecko.com)"


class CoinGeckoError(RuntimeError):
    """Raised on non-2xx responses, network failures, or unexpected payload shapes."""


@dataclass(frozen=True)
class PricePoint:
    timestamp: datetime
    price: float


class _CacheEntry(NamedTuple):
    value: object
    expires_at: float  # time.monotonic() seconds


# Sentinel so cached `None` (or any value) is distinguishable from a miss.
_CACHE_MISS: object = object()


class CoinGeckoClient:
    PRICE_TTL_SEC = 30.0
    MARKET_CHART_TTL_SEC = 300.0

    def __init__(
        self,
        *,
        api_key: str | None = None,
        cache: bool = True,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["x-cg-demo-api-key"] = api_key
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            timeout=timeout,
            headers=headers,
        )
        self._cache: dict[tuple[Any, ...], _CacheEntry] | None = (
            {} if cache else None
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._client.aclose()

    async def get_price(self, coin_id: str, *, vs_currency: str = "usd") -> float:
        """Current spot price for a single coin in `vs_currency`."""
        key = ("price", coin_id, vs_currency)
        cached = self._cache_get(key)
        if cached is not _CACHE_MISS:
            return cached  # type: ignore[return-value]

        payload = await self._get(
            "/simple/price",
            params={"ids": coin_id, "vs_currencies": vs_currency},
        )
        try:
            price = float(payload[coin_id][vs_currency])
        except (KeyError, TypeError, ValueError) as exc:
            raise CoinGeckoError(
                f"Unexpected /simple/price response for {coin_id!r}: {payload!r}"
            ) from exc

        self._cache_put(key, price, self.PRICE_TTL_SEC)
        return price

    async def get_market_chart(
        self,
        coin_id: str,
        *,
        days: int,
        vs_currency: str = "usd",
    ) -> list[PricePoint]:
        """Historical price points for the last `days` days, oldest first.

        CoinGecko's resolution adapts to the range: minute-level for 1 day,
        hourly for 2-90 days, daily for 91+ days.
        """
        key = ("market_chart", coin_id, days, vs_currency)
        cached = self._cache_get(key)
        if cached is not _CACHE_MISS:
            return cached  # type: ignore[return-value]

        payload = await self._get(
            f"/coins/{coin_id}/market_chart",
            params={"vs_currency": vs_currency, "days": days},
        )
        try:
            raw = payload["prices"]
        except KeyError as exc:
            raise CoinGeckoError(
                f"Unexpected /market_chart response for {coin_id!r}: missing 'prices'"
            ) from exc
        points = [
            PricePoint(
                timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                price=float(price),
            )
            for ts_ms, price in raw
        ]
        self._cache_put(key, points, self.MARKET_CHART_TTL_SEC)
        return points

    def _cache_get(self, key: tuple[Any, ...]) -> object:
        if self._cache is None:
            return _CACHE_MISS
        entry = self._cache.get(key)
        if entry is None or entry.expires_at <= time.monotonic():
            return _CACHE_MISS
        return entry.value

    def _cache_put(self, key: tuple[Any, ...], value: object, ttl: float) -> None:
        if self._cache is not None:
            self._cache[key] = _CacheEntry(value, time.monotonic() + ttl)

    async def _get(self, path: str, *, params: dict[str, Any]) -> Any:
        try:
            resp = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise CoinGeckoError(f"GET {path} failed: {exc}") from exc
        if resp.status_code >= 400:
            raise CoinGeckoError(
                f"GET {path} returned {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()
