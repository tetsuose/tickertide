"""M5.3 Stock per-name bundles -> web/public/data/stock/<TICKER>.json (+ index.json).

The data behind the M5.4 time-aligned price↔fundamentals stack (PRD §9.6): per ticker, a
~2y daily price/MA history + the 52w-high, the quarterly revenue series (TTM + YoY), and
the daily P/S series — the three things board.json's 90d mini-chart doesn't carry. Stock is
narrow (one name at a time), so each bundle is its own JSON shard, lazily fetched when a
name is opened — no duckdb-wasm needed here (that's the wide Valuation screener).

Self-contained per name (header + valuation card + 5 components too), so the Stock surface
reads ONE file for any universe ticker, not board.json's top-N shortlist. Same daily_bars /
valuation_daily / fundamentals_q as every other surface (C9): a ticker's P/S line here and
its Ocean/Valuation P/S are the same numbers.

The CORE screen (steady-riser, PRD §10.8; 2026-07-02 spine pivot II) is carried per name too,
so the Stock surface can show its riser 诊断 — the chart-verifiable metrics (net5/net10/net20,
up-day ratio, in-window drawdown, path efficiency), the cross-sectional percentile, the STORED
candidate flag and the on-list streak. It is taken VERBATIM from derived_daily and assembled by
board.py's _riser (the canonical riser-block builder), NEVER recomputed here (C9, same source
as compute/run.py and board.json's Risers cards). breakout/ignition/composite blocks are gone
(all retired).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compute import db  # noqa: E402
# Reuse board.py's canonical ignition-block builder (candidate gate + evidence windows) so the
# Stock 点火诊断 is byte-for-byte the same shape/source as the Discovery card (C9, one builder —
# no parallel copy to drift). _ignition is a pure (ig, bars) -> dict; HIST_BARS just sizes the
# window the evidence is derived from (board pulls 260; we already pull HIST_DAYS=504, both end
# at the snapshot, and the evidence windows are the trailing 50/60 bars — identical either way).
from export.board import _riser  # noqa: E402

DATA_DIR = ROOT / "web" / "public" / "data"
STOCK_DIR = DATA_DIR / "stock"
SCHEMA_VERSION = 3  # v3: breakout→riser block (2026-07-02 spine pivot II); v2 = breakout
HIST_DAYS = 504   # ~2y daily price / P/S history for the time-aligned stack (x axis)
HIGH_WIN = 252    # 52-week high window


def _num(x, nd: int | None = None):
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, nd) if nd is not None else f


def _iso(d) -> str | None:
    return None if d is None else str(d)


def _bars(con, ticker: str, snap) -> list[tuple]:
    """Raw daily bars (oldest→newest) — the ONE fetch the price stack and the ignition
    evidence both read (same source, C9). Tuple order (date, open, high, low, close,
    adj_close, volume) matches what board._ignition expects (adj_close=[5], volume=[6])."""
    return con.execute(
        "SELECT date, open, high, low, close, adj_close, volume FROM daily_bars "
        "WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT ?",
        [ticker, snap, HIST_DAYS],
    ).fetchall()[::-1]


def _price(con, ticker: str, snap, bars: list[tuple]) -> dict:
    ma_rows = con.execute(
        "SELECT date, ma50, ma150, ma200 FROM derived_daily "
        "WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT ?",
        [ticker, snap, HIST_DAYS],
    ).fetchall()
    ma = {r[0]: r for r in ma_rows}
    high_52w = max((b[5] for b in bars[-HIGH_WIN:] if b[5] is not None), default=None)
    return {
        "dates": [_iso(b[0]) for b in bars],
        "open": [_num(b[1], 4) for b in bars],
        "high": [_num(b[2], 4) for b in bars],
        "low": [_num(b[3], 4) for b in bars],
        "close": [_num(b[4], 4) for b in bars],
        "adj_close": [_num(b[5], 4) for b in bars],
        "volume": [int(b[6]) if b[6] is not None else None for b in bars],
        "ma50": [_num(ma.get(b[0], (None,) * 4)[1], 4) for b in bars],
        "ma150": [_num(ma.get(b[0], (None,) * 4)[2], 4) for b in bars],
        "ma200": [_num(ma.get(b[0], (None,) * 4)[3], 4) for b in bars],
        "high_52w": _num(high_52w, 4),
    }


def _revenue_q(con, ticker: str, snap) -> list[dict]:
    """Quarterly TTM revenue + YoY (vs 4 quarters back), drives the REVENUE bars (PRD §9.6).
    FORMAL-FILING PIT (§10.5): a quarter appears only once its formal filing is EFFECTIVE
    as-of snap (effective_eod_date <= snap, NOT period_end <= snap) — so the bars never show
    a quarter the market couldn't yet know, and stay aligned with the P/S denominator (which
    steps at effective_eod). Bars are still positioned at period_end (business period); each
    carries filed_date / effective_eod_date / disclosure_lag_days so the Stock view can mark
    the filing date and explain when the value enters P/S."""
    rows = con.execute(
        "SELECT period_end, filed_date, COALESCE(effective_eod_date, filed_date) AS eff, revenue_ttm "
        "FROM fundamentals_q WHERE ticker = ? AND COALESCE(effective_eod_date, filed_date) <= ? "
        "ORDER BY period_end",
        [ticker, snap],
    ).fetchall()
    out = []
    for i, (pe, filed, eff, rev) in enumerate(rows):
        prev = rows[i - 4][3] if i >= 4 else None
        yoy = (rev / prev - 1.0) if (prev and rev is not None and prev != 0) else None
        lag = (filed - pe).days if (pe is not None and filed is not None) else None
        out.append({
            "period_end": _iso(pe), "filed_date": _iso(filed), "effective_eod_date": _iso(eff),
            "disclosure_lag_days": lag, "revenue_ttm": _num(rev), "yoy": _num(yoy, 4),
        })
    return out


def _ps_series(con, ticker: str, snap) -> list[dict]:
    rows = con.execute(
        "SELECT date, ps FROM valuation_daily WHERE ticker = ? AND date <= ? AND ps IS NOT NULL "
        "ORDER BY date DESC LIMIT ?",
        [ticker, snap, HIST_DAYS],
    ).fetchall()[::-1]
    return [{"date": _iso(d), "ps": _num(p, 3)} for d, p in rows]


def build_bundle(con, ticker: str, snap) -> dict:
    head = con.execute(
        "SELECT u.name, u.sector, u.mktcap, d.composite, d.c_rs, d.c_high, d.c_trend, d.c_vol, d.c_accel, "
        "d.rise_net5, d.rise_net10, d.rise_net20, d.rise_up10, d.rise_ddw10, "
        "d.rise_ker10, d.rise_net10_pct, d.rise_candidate, d.rise_streak_days "
        "FROM derived_daily d LEFT JOIN universe u ON u.ticker = d.ticker "
        "WHERE d.ticker = ? AND d.date = ?",
        [ticker, snap],
    ).fetchone()
    val = con.execute(
        "SELECT pe, ps, evs, ev_ebitda, peg, growth, margin, rule40, as_of_period_end, as_of_filed, "
        "as_of_effective_eod, valuation_basis "
        "FROM valuation_daily WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        [ticker, snap],
    ).fetchone()
    chips = db.theme_membership_asof(con, snap, ticker=ticker)
    themes = [{"theme": r.theme, "exposure": _num(r.exposure, 3)} for r in chips.itertuples()]

    bars = _bars(con, ticker, snap)

    # steady-riser (PRD §10.8, core screen) — verbatim from derived_daily, assembled by
    # board.py's canonical _riser (C9, never recomputed — candidate flag included). Same
    # builder + same source as the Risers card, so a name's riser 诊断 here and its Risers
    # card are identical.
    riser_block = None
    if head is not None and head[10] is not None:
        rk = {
            "rise_net5": head[9], "rise_net10": head[10], "rise_net20": head[11],
            "rise_up10": head[12], "rise_ddw10": head[13], "rise_ker10": head[14],
            "rise_net10_pct": head[15], "rise_candidate": head[16], "rise_streak_days": head[17],
        }
        riser_block = _riser(rk)

    valuation = None
    if val is not None:
        lag = (val[9] - val[8]).days if (val[8] is not None and val[9] is not None) else None
        valuation = {
            "pe": _num(val[0], 2), "ps": _num(val[1], 2), "evs": _num(val[2], 2),
            "ev_ebitda": _num(val[3], 2), "peg": _num(val[4], 2), "growth": _num(val[5], 4),
            "margin": _num(val[6], 4), "rule40": _num(val[7], 4),
            "as_of_period_end": _iso(val[8]), "as_of_filed": _iso(val[9]),
            "as_of_effective_eod": _iso(val[10]), "valuation_basis": val[11],
            "disclosure_lag_days": lag,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": _iso(snap),
        "meta": {
            "ticker": ticker,
            "name": head[0] if head else None,
            "sector": head[1] if head else None,
            "mktcap": _num(head[2]) if head else None,
            "composite": _num(head[3], 1) if head else None,
            "themes": themes,
        },
        "components": {
            "rs": _num(head[4], 4), "high": _num(head[5], 4), "trend": _num(head[6], 4),
            "vol": _num(head[7], 4), "accel": _num(head[8], 4),
        } if head else None,
        "riser": riser_block,
        "valuation": valuation,
        "price": _price(con, ticker, snap, bars),
        "revenue_q": _revenue_q(con, ticker, snap),
        "ps_series": _ps_series(con, ticker, snap),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M5.3 export: Stock per-name bundles.")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--out-dir", default=str(STOCK_DIR))
    ap.add_argument("--limit", type=int, default=None, help="cap ticker count (debug)")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    snap = con.execute("SELECT max(date) FROM derived_daily").fetchone()[0]
    if snap is None:
        con.close()
        raise SystemExit("[stock-bundle] derived_daily empty — run `make compute` first.")

    tickers = [r[0] for r in con.execute(
        "SELECT ticker FROM derived_daily WHERE date = ? ORDER BY ticker"
        + (f" LIMIT {int(args.limit)}" if args.limit else ""), [snap]
    ).fetchall()]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for t in tickers:
        bundle = build_bundle(con, t, snap)
        (out_dir / f"{t}.json").write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + "\n")
        written += 1
    con.close()

    index = {"schema_version": SCHEMA_VERSION, "as_of_date": _iso(snap), "count": written,
             "tickers": tickers}
    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n")

    print(f"[stock-bundle] {out_dir}  as_of={_iso(snap)}  bundles={written}  (+ index.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
