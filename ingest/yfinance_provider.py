"""yfinance price provider — M0 default backbone.

BUILD-PLAN flags yfinance as a fragile, unofficial fallback (Yahoo ToS gray, can
break). It is the M0 default only because Stooq now gates per-symbol CSV behind an
apikey. Treat outages as expected; the provider interface lets us swap to Stooq/
Tiingo later without touching ingest/run.py.
"""
from __future__ import annotations

from datetime import date, timedelta


class YFinanceProvider:
    name = "yfinance"

    def get_bars(self, ticker: str, lookback_days: int = 760) -> list[tuple]:
        import yfinance as yf  # lazy: heavy import

        start = (date.today() - timedelta(days=lookback_days)).isoformat()
        df = yf.download(
            ticker, start=start, auto_adjust=False, progress=False, threads=False
        )
        if df is None or len(df) == 0:
            return []

        # Single-ticker downloads can still return MultiIndex columns; flatten.
        cols = df.columns
        if hasattr(cols, "nlevels") and cols.nlevels > 1:
            df = df.copy()
            df.columns = cols.get_level_values(0)

        def g(row, key):
            v = row.get(key)
            return None if v is None or (isinstance(v, float) and v != v) else float(v)

        out: list[tuple] = []
        for idx, row in df.iterrows():
            close = g(row, "Close")
            if close is None:
                continue  # skip incomplete bars (e.g. today's not-yet-closed intraday row)
            d = idx.date().isoformat()
            vol = row.get("Volume")
            out.append((
                d,
                g(row, "Open"), g(row, "High"), g(row, "Low"), close,
                g(row, "Adj Close") if "Adj Close" in df.columns else close,
                int(vol) if vol is not None and vol == vol else None,
            ))
        return out
