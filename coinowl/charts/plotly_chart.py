"""Generate Plotly price chart and export as PNG / HTML bytes for Telegram delivery.

Palette is extracted from the CoinOwl brand logo: dark navy paper, gold line and
fill, copper for negatives, cream text. If `assets/logo.png` exists at the
project root, it's embedded in the bottom-right of every full chart as a
semi-transparent watermark. Sparklines are too small for the logo — left bare.
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import TYPE_CHECKING

import plotly.graph_objects as go

if TYPE_CHECKING:
    from coinowl.data.coingecko import PricePoint

# CoinOwl brand palette
_GOLD = "#D4AF37"
_GOLD_FILL = "rgba(212, 175, 55, 0.22)"
_COPPER = "#C04A2A"
_CREAM = "#F5E6C8"
_BG_PAPER = "#0a0a1a"
_BG_PLOT = "#15151f"
_GRID = "rgba(212, 175, 55, 0.10)"

_LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "logo.png"
_LOGO_DATA_URI: str | None = None
_LOGO_LOADED = False


def _load_logo_uri() -> str | None:
    global _LOGO_DATA_URI, _LOGO_LOADED
    if _LOGO_LOADED:
        return _LOGO_DATA_URI
    _LOGO_LOADED = True
    if not _LOGO_PATH.exists():
        return None
    try:
        b64 = base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
        _LOGO_DATA_URI = f"data:image/png;base64,{b64}"
    except Exception:
        _LOGO_DATA_URI = None
    return _LOGO_DATA_URI


def _yrange(prices: list[float]) -> tuple[float, float]:
    pmin, pmax = min(prices), max(prices)
    pad = (pmax - pmin) * 0.08 or pmax * 0.02
    return pmin - pad, pmax + pad


def _build_figure(symbol: str, points: list[PricePoint], days: int) -> go.Figure:
    times = [p.timestamp for p in points]
    prices = [p.price for p in points]
    ymin, ymax = _yrange(prices)

    fig = go.Figure(
        go.Scatter(
            x=times,
            y=prices,
            mode="lines",
            line=dict(color=_GOLD, width=2),
            fill="tozeroy",
            fillcolor=_GOLD_FILL,
            hovertemplate="%{x|%b %d}<br>$%{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=f"{symbol} — {days}d price (USD)", font=dict(size=14, color=_CREAM)),
        paper_bgcolor=_BG_PAPER,
        plot_bgcolor=_BG_PLOT,
        font=dict(color=_CREAM, family="monospace"),
        xaxis=dict(showgrid=False, color=_CREAM),
        yaxis=dict(
            showgrid=True,
            gridcolor=_GRID,
            color=_CREAM,
            tickprefix="$",
            range=[ymin, ymax],
        ),
        margin=dict(l=60, r=20, t=50, b=40),
        width=800,
        height=400,
    )
    logo_uri = _load_logo_uri()
    if logo_uri is not None:
        fig.update_layout(
            images=[dict(
                source=logo_uri,
                xref="paper", yref="paper",
                x=0.99, y=0.04,
                sizex=0.14, sizey=0.22,
                xanchor="right", yanchor="bottom",
                opacity=0.35,
                layer="above",
            )]
        )
    return fig


def _build_sparkline(points: list[PricePoint]) -> go.Figure:
    prices = [p.price for p in points]
    ymin, ymax = _yrange(prices)
    up = prices[-1] >= prices[0]
    color = _GOLD if up else _COPPER

    fig = go.Figure(
        go.Scatter(
            x=list(range(len(prices))),
            y=prices,
            mode="lines",
            line=dict(color=color, width=1.5),
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, range=[ymin, ymax]),
        margin=dict(l=0, r=0, t=0, b=0),
        width=200,
        height=40,
        showlegend=False,
    )
    return fig


async def generate_chart(
    symbol: str, points: list[PricePoint], days: int
) -> bytes:
    """Return PNG bytes for the full price chart."""
    fig = _build_figure(symbol, points, days)
    return await asyncio.to_thread(_render_png, fig)


async def generate_chart_html(
    symbol: str, points: list[PricePoint], days: int
) -> bytes:
    """Return UTF-8 bytes of a self-contained interactive HTML chart."""
    fig = _build_figure(symbol, points, days)
    return await asyncio.to_thread(_render_html, fig)


async def generate_sparkline(points: list[PricePoint]) -> bytes:
    """Return PNG bytes for a 200x40 inline sparkline (no axes, transparent bg)."""
    fig = _build_sparkline(points)
    return await asyncio.to_thread(_render_png, fig)


def _render_png(fig: go.Figure) -> bytes:
    return fig.to_image(format="png")


def _render_html(fig: go.Figure) -> bytes:
    return fig.to_html(include_plotlyjs="cdn", full_html=True).encode("utf-8")
