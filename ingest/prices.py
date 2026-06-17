"""Pluggable price provider interface (M0).

BUILD-PLAN's intended price backbone was Stooq (free, no per-symbol rate limit).
That assumption changed: Stooq's per-symbol CSV now requires an apikey (captcha).
So M0 defaults to yfinance (BUILD-PLAN's listed fallback) and keeps Stooq behind
the same interface, to be enabled once an apikey exists. Swapping the backbone is
a provider choice, not a spine change (per-stock engine / 5 surfaces unchanged).

A provider returns bars as a list of tuples:
    (date_iso: str, open, high, low, close, adj_close, volume)
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class PriceProvider(ABC):
    name: str

    @abstractmethod
    def get_bars(self, ticker: str, lookback_days: int = 760) -> list[tuple]:
        """Return daily bars for ticker over ~lookback_days calendar days (newest last)."""

    def get_splits(self, ticker: str) -> list[tuple]:
        """Return [(ex_date_iso, ratio)] forward/reverse splits, oldest first. OPTIONAL
        capability (default: none) — split-alignment (PRD §10.5) degrades gracefully to a
        factor of 1.0 when a provider can't supply splits. ratio = shares-out multiplier
        on/after ex_date (forward 10-for-1 → 10.0; reverse 1-for-5 → 0.2)."""
        return []


def get_provider(name: str = "yfinance") -> PriceProvider:
    """Factory. Lazy-imports the concrete provider so its deps load only when used."""
    name = (name or "yfinance").lower()
    if name == "yfinance":
        from yfinance_provider import YFinanceProvider
        return YFinanceProvider()
    if name == "stooq":
        from stooq import StooqProvider
        return StooqProvider()
    raise ValueError(f"unknown price provider: {name!r} (use 'yfinance' or 'stooq')")
