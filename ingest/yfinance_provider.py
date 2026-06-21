"""yfinance price provider — M0 default backbone.

BUILD-PLAN flags yfinance as a fragile, unofficial fallback (Yahoo ToS gray, can
break). It is the M0 default only because Stooq now gates per-symbol CSV behind an
apikey. Treat outages as expected; the provider interface lets us swap to Stooq/
Tiingo later without touching ingest/run.py.
"""
from __future__ import annotations

from datetime import date, timedelta


def _frame_to_bars(df) -> list[tuple]:
    """One ticker's (flat-column) OHLCV frame -> [(date_iso, o,h,l,close,adj_close,vol)]."""
    if df is None or len(df) == 0:
        return []
    has_adj = "Adj Close" in df.columns

    def g(row, key):
        v = row.get(key)
        return None if v is None or (isinstance(v, float) and v != v) else float(v)

    out: list[tuple] = []
    for idx, row in df.iterrows():
        close = g(row, "Close")
        if close is None:
            continue  # skip incomplete bars (e.g. today's not-yet-closed intraday row)
        vol = row.get("Volume")
        out.append((
            idx.date().isoformat(),
            g(row, "Open"), g(row, "High"), g(row, "Low"), close,
            g(row, "Adj Close") if has_adj else close,
            int(vol) if vol is not None and vol == vol else None,
        ))
    return out


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
        return _frame_to_bars(df)

    def get_bars_batch(self, tickers: list[str], lookback_days: int = 760,
                       chunk: int = 120) -> dict[str, list[tuple]]:
        """Bars for MANY tickers via chunked threaded yf.download — the M6 scale path
        (one HTTP batch per `chunk` tickers instead of one per ticker). Returns
        {ticker: bars}; tickers with no data are simply absent (best-effort, a chunk
        failure skips only that chunk). Multi-ticker downloads come back with a
        (field, ticker) column MultiIndex; we slice each ticker out to a flat frame."""
        import yfinance as yf  # lazy: heavy import

        start = (date.today() - timedelta(days=lookback_days)).isoformat()
        out: dict[str, list[tuple]] = {}
        for i in range(0, len(tickers), chunk):
            part = tickers[i:i + chunk]
            try:
                df = yf.download(part, start=start, auto_adjust=False, progress=False,
                                 threads=True, group_by="column")
            except Exception:
                continue  # whole-chunk network failure: skip, caller logs coverage
            if df is None or len(df) == 0:
                continue
            if getattr(df.columns, "nlevels", 1) > 1:
                for t in part:
                    try:
                        sub = df.xs(t, axis=1, level=1)
                    except (KeyError, IndexError):
                        continue
                    bars = _frame_to_bars(sub)
                    if bars:
                        out[t] = bars
            else:  # a 1-ticker chunk comes back flat
                bars = _frame_to_bars(df)
                if bars:
                    out[part[0]] = bars
        return out

    def get_splits(self, ticker: str) -> list[tuple]:
        """Return [(ex_date_iso, ratio)] forward/reverse splits from Yahoo, oldest first.
        ratio = shares-out multiplier on/after ex_date (10-for-1 → 10.0; reverse 1-for-8 →
        0.125). Feeds split-alignment (PRD §10.5): the bars above are split-adjusted to the
        latest session, so per-share EDGAR fundamentals must be lifted to the same basis.
        Empty on no splits / fetch failure (fragile source — treat outages as expected)."""
        import yfinance as yf  # lazy: heavy import

        try:
            s = yf.Ticker(ticker).splits  # pandas Series: index = ex-date, value = ratio
        except Exception:
            return []
        if s is None or len(s) == 0:
            return []
        out: list[tuple] = []
        for idx, val in s.items():
            try:
                r = float(val)
            except (TypeError, ValueError):
                continue
            if r > 0 and r != 1.0:  # 0/NaN are bad rows; 1.0 is a no-op split
                out.append((idx.date().isoformat(), r))
        out.sort()
        return out
