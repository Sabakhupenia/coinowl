"""Async wrapper around the CoinGecko free API.

The free tier needs no API key but enforces loose rate limits
(~10-30 requests/minute). Higher quotas live behind their demo / pro plans.

Usage:
    async with CoinGeckoClient() as cg:
        price = await cg.get_price("bitcoin")
        chart = await cg.get_market_chart("bitcoin", days=7)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Self

import httpx

from coinowl.core.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://api.coingecko.com/api/v3"
_DEFAULT_TIMEOUT = 10.0


class CoinGeckoError(RuntimeError):
    """Raised on non-2xx responses, network failures, or unexpected payload shapes."""


@dataclass(frozen=True)
class PricePoint:
    timestamp: datetime
    price: float


class CoinGeckoClient:
    def __init__(self, *, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._client = httpx.AsyncClient(base_url=_BASE_URL, timeout=timeout)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._client.aclose()

    async def get_price(self, coin_id: str, *, vs_currency: str = "usd") -> float:
        """Current spot price for a single coin in `vs_currency`."""
        payload = await self._get(
            "/simple/price",
            params={"ids": coin_id, "vs_currencies": vs_currency},
        )
        try:
            return float(payload[coin_id][vs_currency])
        except (KeyError, TypeError, ValueError) as exc:
            raise CoinGeckoError(
                f"Unexpected /simple/price response for {coin_id!r}: {payload!r}"
            ) from exc

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
        return [
            PricePoint(
                timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                price=float(price),
            )
            for ts_ms, price in raw
        ]

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
