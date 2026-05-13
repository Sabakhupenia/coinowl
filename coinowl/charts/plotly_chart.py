"""Generate Plotly price chart and export as PNG / HTML bytes for Telegram delivery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import plotly.graph_objects as go

if TYPE_CHECKING:
    from coinowl.data.coingecko import PricePoint

_BAR_COLOR = "#00C896"
_BG_COLOR = "#1a1a2e"
_GRID_COLOR = "#2a2a4e"


def _build_figure(symbol: str, points: list[PricePoint], days: int) -> go.Figure:
    times = [p.timestamp for p in points]
    prices = [p.price for p in points]

    fig = go.Figure(
        go.Bar(
            x=times,
            y=prices,
            marker_color=_BAR_COLOR,
            hovertemplate="%{x|%b %d}<br>$%{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=f"{symbol} — {days}d price (USD)", font=dict(size=14)),
        paper_bgcolor=_BG_COLOR,
        plot_bgcolor=_BG_COLOR,
        font=dict(color="white", family="monospace"),
        xaxis=dict(showgrid=False, color="white"),
        yaxis=dict(showgrid=True, gridcolor=_GRID_COLOR, color="white", tickprefix="$"),
        margin=dict(l=60, r=20, t=50, b=40),
        width=800,
        height=400,
    )
    return fig


async def generate_chart(
    symbol: str, points: list[PricePoint], days: int
) -> bytes:
    """Return PNG bytes for a price chart. Runs kaleido in a thread executor."""
    fig = _build_figure(symbol, points, days)
    return await asyncio.to_thread(_render_png, fig)


async def generate_chart_html(
    symbol: str, points: list[PricePoint], days: int
) -> bytes:
    """Return UTF-8 bytes of a self-contained interactive HTML chart."""
    fig = _build_figure(symbol, points, days)
    return await asyncio.to_thread(_render_html, fig)


def _render_png(fig: go.Figure) -> bytes:
    return fig.to_image(format="png")


def _render_html(fig: go.Figure) -> bytes:
    return fig.to_html(include_plotlyjs="cdn", full_html=True).encode("utf-8")
