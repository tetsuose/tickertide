"""Stooq price provider (stub) — disabled until an apikey exists.

BUILD-PLAN's intended backbone. Stooq's per-symbol CSV endpoint now requires an
apikey obtained via captcha (a policy change after BUILD-PLAN was written), so
this provider raises with guidance unless STOOQ_APIKEY is set. The request shape
below is left for whoever wires the key in — verify the exact apikey param then.
"""
from __future__ import annotations

import os


class StooqProvider:
    name = "stooq"

    def __init__(self) -> None:
        self.apikey = os.environ.get("STOOQ_APIKEY")

    def get_bars(self, ticker: str, lookback_days: int = 760) -> list[tuple]:
        if not self.apikey:
            raise RuntimeError(
                "Stooq per-symbol CSV requires STOOQ_APIKEY (get via captcha at "
                "stooq.com). For M0 use --provider yfinance, or set STOOQ_APIKEY in "
                ".env (gitignored) to enable Stooq."
            )
        # Endpoint shape (verify the apikey param name once a real key exists):
        #   https://stooq.com/q/d/l/?s={ticker}.us&i=d&apikey=...
        # Parse CSV: Date,Open,High,Low,Close,Volume -> bar tuples (adj_close=close).
        raise NotImplementedError(
            "Stooq fetch+parse not wired yet — implement when STOOQ_APIKEY is available."
        )
