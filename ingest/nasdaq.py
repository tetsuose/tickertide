"""US equity universe from the Nasdaq screener download endpoint (M0).

One request per exchange returns the full listing (symbol/name/sector/industry/
country/marketCap). US-only by construction: the three exchanges are US-listed
(ADRs allowed per SCOPE). Requires a browser-like User-Agent or the API returns
an empty body.
"""
from __future__ import annotations

import json
import urllib.request

_BASE = "https://api.nasdaq.com/api/screener/stocks?tableonly=false&limit=0&download=true"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
EXCHANGES = ("NASDAQ", "NYSE", "AMEX")


def _num(s) -> float | None:
    if s is None:
        return None
    try:
        v = float(str(s).replace(",", "").replace("$", "").strip())
        return v if v != 0 else None
    except (ValueError, TypeError):
        return None


def fetch_universe(exchanges: tuple[str, ...] = EXCHANGES, timeout: int = 40) -> list[dict]:
    """Return deduped universe rows (keep the largest-mktcap dup of any ticker)."""
    by_ticker: dict[str, dict] = {}
    for ex in exchanges:
        req = urllib.request.Request(f"{_BASE}&exchange={ex}", headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        rows = (data.get("data") or {}).get("rows") or (data.get("data") or {}).get("table", {}).get("rows") or []
        for r in rows:
            sym = (r.get("symbol") or "").strip().upper()
            if not sym or "^" in sym or "/" in sym:
                continue
            row = {
                "ticker": sym,
                "name": (r.get("name") or "").strip() or None,
                "exchange": ex,
                "sector": (r.get("sector") or "").strip() or None,
                "industry": (r.get("industry") or "").strip() or None,
                "country": (r.get("country") or "").strip() or None,
                "mktcap": _num(r.get("marketCap")),
            }
            prev = by_ticker.get(sym)
            if prev is None or (row["mktcap"] or 0) > (prev["mktcap"] or 0):
                by_ticker[sym] = row
    return list(by_ticker.values())
