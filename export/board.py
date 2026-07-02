"""M1.1 board export: DuckDB snapshot -> web/public/data/board.json (Discovery).

Reads the latest derived_daily/valuation_daily snapshot and assembles the
evidence-first Discovery board (PRD §9.3, ROADMAP M1.1). One JSON object per
stock: identity, engine composite + the 5 raw components c_* (so the client can
show each component's weight in the fixed-weight composite WITHOUT recomputing
the engine — C9), 6 raw evidence numbers, latest valuation with as-of freshness,
and the previous-day composite for d/d.

PAYLOAD SPLIT (schema v2, payload reduction — the ocean-v3 idiom applied to board):
the ~90d OHLCV mini-chart is ~96% of the raw payload, yet Discovery is bounded/
decide (App caps the board at top-20), so only ~20 of the ~500 charts are ever on
screen at once. So v2 splits the export in two:
  - BULK `board.json` — every stock's card data (identity / composite + c_* / the
    6 evidence numbers / riser block / valuation / theme chips), WITHOUT the
    chart. The only file the client downloads up front; it still carries every
    field Risers needs to sort (net10) and scope-filter the WHOLE universe.
  - DETAIL `board/<TICKER>.json` — that stock's mini-chart only ({schema_version,
    ticker, chart}). Fetched lazily by the card as it renders, so a session only
    downloads charts for the handful of names actually shown. Measured: full board
    brotli ~1.20MB → bulk ~51KB + 20×~2.5KB ≈ 101KB first paint (−92%).
Both derive from the SAME daily_bars in ONE pass (C9): the chart still ships the
same bars the evidence numbers are derived from — the split changes WHERE the
chart lives, never WHAT it is.

Three evidence numbers are NOT materialised in derived_daily; they are derived
here from the SAME daily_bars the chart ships, so card and chart stay
traceable to one source (PRD §9.3 "同一份 export"):
  - ret_1m              : 21-trading-day adj_close return
  - vol_mult            : latest volume / SMA(volume, 50)   (PRD §10.6 pulse term)
  - weeks_since_breakout: whole weeks since the last trailing-252d closing high
                          (transparent proxy; a dedicated breakout signal is a
                          later milestone — it is NOT an engine number)

The CORE screen (steady-riser, PRD §10.8; 2026-07-02 spine pivot II — replaces base→breakout,
which is retired §10.9) is carried per stock. Risers (the renamed Breakouts, §9.3) gates on
`up10>=0.6 AND net10>0` and sorts by `rise_net10`, so each stock ships its chart-verifiable
metrics (rise_net5/net10/net20, rise_up10, rise_ddw10, rise_ker10), the cross-sectional
`rise_net10_pct`, the STORED `rise_candidate` flag and `rise_streak_days` — ALL verbatim from
derived_daily (NEVER recomputed here — C9, same source as compute/run.py). In particular the
candidate flag is read as stored, never re-derived from the percentile or re-gated here
(the #92-#94 rounding-boundary lesson). recall-first: false positives are expected — and
names that later fall are fine; fundamentals/financials are the downstream precision stage
(§10.8.4). Smoothness (ker/ddw) is evidence, never a hard gate (§10.8.3). No tunable knob.
composite is retired (kept transitionally for the C9 reconstruct guard until the web stops
reading it).

This export carries each engine's score verbatim and never recomputes it; the
client reads the exported composite directly and uses the c_* only to show each
component's contribution at the fixed weighting (C9 — the knob is gone). As a
guard, build_board reconstructs 100·Σ weights(k)·c_* at the snapshot k and
checks it reproduces derived_daily.composite, AND reconstructs ignition from the
exported raw vsurge/breakout vs the stored component to catch ignition drift, so
an engine/export drift fails loudly here instead of silently in the browser.

Output (gitignored, derived nightly): web/public/data/board.json (bulk, schema_version 2)
+ web/public/data/board/<TICKER>.json (per-stock mini-chart, lazily fetched on render).
Math spec: PRD §10; freshness thresholds PRD §10.5/§9.5; schema PRD §12.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compute import db, riser, signals  # noqa: E402

SCHEMA_VERSION = 4  # v4: breakout→riser block (2026-07-02 spine pivot II); v3 = breakout; v2 = payload split
DEFAULT_OUT = ROOT / "web" / "public" / "data" / "board.json"

CHART_DAYS = 90          # mini-chart window (PRD §9.3: ~90d K线)
HIST_BARS = 260          # bars pulled per stock; covers the 252d high window
RET_1M_LAG = 21          # ~1 trading month
VOL_WIN = 50             # SMA(volume) window for the pulse multiplier (PRD §10.6)
HIGH_WIN = 252           # 52-week high window
FRESH_DAYS = 95          # <=95d = fresh (current quarter reported), PRD §10.5
STALE_DAYS = 160         # <=160d = stale (one quarter behind); >160d = overdue
COMPOSITE_TOL = 1e-6     # C9 self-check tolerance (engine vs reconstructed)


def freshness(age_days: int | None) -> str | None:
    """As-of bucket per PRD §9.5/§10.5: fresh <=95d, stale <=160d, else overdue."""
    if age_days is None:
        return None
    if age_days <= FRESH_DAYS:
        return "fresh"
    if age_days <= STALE_DAYS:
        return "stale"
    return "overdue"


def _num(x, ndigits: int | None = None):
    """JSON-safe number: NaN/inf/None -> None; optional rounding."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, ndigits) if ndigits is not None else f


def _iso(d) -> str | None:
    return d.isoformat() if isinstance(d, date) else (str(d) if d is not None else None)


def _table_exists(con, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ?", [name]
    ).fetchone() is not None


def _themes(con, ticker: str, snap, has_themes: bool) -> list[dict]:
    """Point-in-time theme chips as-of the board snapshot (PRD §7 C3): per theme the latest
    as_of_date<=snap kept only if exposure>0, via the canonical db.theme_membership_asof —
    so a multi-as_of ticker shows each theme ONCE at its current exposure (NOT the old naive
    scan that returned every historical row). Highest exposure first (chip order). exposure
    is the [0,1] revenue-share fraction; the card renders it as a %. Empty until themes are
    seeded; table may not exist pre-M4."""
    if not has_themes:
        return []
    m = db.theme_membership_asof(con, snap, ticker=ticker).sort_values("exposure", ascending=False)
    return [{"theme": r.theme, "exposure": _num(r.exposure, 4)} for r in m.itertuples()]


def _chart(bars: list[tuple], ma_rows: list[tuple]) -> dict:
    """~90d OHLCV + MA50/150/200 (engine, aligned by date) + 52w-high level."""
    tail = bars[-CHART_DAYS:]
    ma = {r[0]: r for r in ma_rows}  # keyed by date
    high_52w = max((b[5] for b in bars[-HIGH_WIN:] if b[5] is not None), default=None)
    return {
        "dates": [_iso(b[0]) for b in tail],
        "open": [_num(b[1], 4) for b in tail],
        "high": [_num(b[2], 4) for b in tail],
        "low": [_num(b[3], 4) for b in tail],
        "close": [_num(b[4], 4) for b in tail],
        "adj_close": [_num(b[5], 4) for b in tail],
        "volume": [int(b[6]) if b[6] is not None else None for b in tail],
        "ma50": [_num(ma.get(b[0], (None,) * 4)[1], 4) for b in tail],
        "ma150": [_num(ma.get(b[0], (None,) * 4)[2], 4) for b in tail],
        "ma200": [_num(ma.get(b[0], (None,) * 4)[3], 4) for b in tail],
        "high_52w": _num(high_52w, 4),
    }


def _evidence(d: dict, bars: list[tuple], snap) -> dict:
    """6 raw evidence numbers (PRD §9.1.3). ret_3m/6m + from_high come from the
    engine snapshot; ret_1m/vol_mult/weeks_since_breakout are derived from bars."""
    adj = [b[5] for b in bars]
    vols = [b[6] for b in bars]

    ret_1m = None
    if len(adj) > RET_1M_LAG and adj[-1] is not None and adj[-1 - RET_1M_LAG]:
        ret_1m = adj[-1] / adj[-1 - RET_1M_LAG] - 1

    vol_mult = None
    if len(vols) >= VOL_WIN and vols[-1] is not None:
        win = [v for v in vols[-VOL_WIN:] if v is not None]
        avg = sum(win) / len(win) if win else 0
        vol_mult = vols[-1] / avg if avg else None

    # weeks since the last trailing-252d closing high (transparent proxy).
    weeks = None
    if adj:
        last_high_i, run_max = 0, -math.inf
        for i, p in enumerate(adj):
            if p is not None and p >= run_max:
                run_max, last_high_i = p, i
        weeks = ((bars[-1][0] - bars[last_high_i][0]).days) // 7

    high_prox = d.get("high_prox")
    return {
        "ret_1m": _num(ret_1m, 4),
        "ret_3m": _num(d.get("ret_63"), 4),
        "ret_6m": _num(d.get("ret_126"), 4),
        "from_high": _num(high_prox - 1, 4) if high_prox is not None else None,
        "weeks_since_breakout": weeks,
        "vol_mult": _num(vol_mult, 3),
    }


def _riser(rk: dict) -> dict:
    """Per-stock steady-riser block, verbatim from derived_daily (C9, core screen §10.8).

    `rk` carries the screen's stored numbers (NEVER recomputed here): the chart-verifiable
    metrics (rise_net5/net10/net20 net rises, rise_up10 up-day ratio, rise_ddw10 in-window
    drawdown, rise_ker10 path efficiency), the cross-sectional `rise_net10_pct`, the STORED
    `rise_candidate` flag (computed ONCE in compute/run.py — gate up10>=0.6 AND net10>0,
    net10 top-N; never re-derived from the percentile here, the #92-#94 boundary lesson)
    and `rise_streak_days` (consecutive days on the list; display column, not a filter)."""
    return {
        "net5": _num(rk.get("rise_net5"), 4),
        "net10": _num(rk.get("rise_net10"), 4),
        "net20": _num(rk.get("rise_net20"), 4),
        "up10": _num(rk.get("rise_up10"), 2),
        "ddw10": _num(rk.get("rise_ddw10"), 4),
        "ker10": _num(rk.get("rise_ker10"), 3),
        "net10_pct": _num(rk.get("rise_net10_pct"), 1),
        "candidate": bool(rk.get("rise_candidate") == 1),
        "streak_days": int(rk.get("rise_streak_days") or 0),
    }


def build_board(con, k: float = 0.5, limit: int | None = None, min_bars: int = 60) -> tuple[dict, dict]:
    """Assemble the Discovery board (schema v2) from the latest DuckDB snapshot.

    Returns (bulk, chart_by_ticker):
      - bulk: the dict written to board.json (every stock's card data, NO chart).
      - chart_by_ticker: {ticker -> {schema_version, ticker, chart}} written to
        board/<ticker>.json (the lazily-fetched per-stock mini-chart).
    Both are built in ONE pass over the same per-stock bars so they can never
    desync — the chart traces to the SAME daily_bars the evidence numbers do (C9).
    """
    snap = con.execute("SELECT max(date) FROM derived_daily").fetchone()[0]
    if snap is None:
        raise RuntimeError("derived_daily is empty — run `make compute` first.")

    w = signals.weights(k)
    has_themes = _table_exists(con, "theme_membership")

    head = con.execute(
        """
        SELECT d.ticker, u.name, u.sector, u.mktcap,
               d.composite, d.rank_in_universe,
               d.c_rs, d.c_high, d.c_trend, d.c_vol, d.c_accel,
               d.ret_63, d.ret_126, d.high_prox,
               d.rise_net5, d.rise_net10, d.rise_net20, d.rise_up10, d.rise_ddw10,
               d.rise_ker10, d.rise_net10_pct, d.rise_candidate, d.rise_streak_days
        FROM derived_daily d
        LEFT JOIN universe u ON u.ticker = d.ticker
        WHERE d.date = ?
        ORDER BY d.rise_net10 DESC NULLS LAST
        """ + (f"LIMIT {int(limit)}" if limit else ""),
        [snap],
    ).fetchall()

    stocks, max_drift, n_val = [], 0.0, 0
    n_ris, n_cand = 0, 0
    chart_by_ticker: dict[str, dict] = {}  # v2 split: per-stock mini-chart (board/<t>.json)
    for r in head:
        t = r[0]
        comp = {"rs": r[6], "high": r[7], "trend": r[8], "vol": r[9], "accel": r[10]}
        d = {"ret_63": r[11], "ret_126": r[12], "high_prox": r[13]}
        rk = {
            "rise_net5": r[14], "rise_net10": r[15], "rise_net20": r[16],
            "rise_up10": r[17], "rise_ddw10": r[18], "rise_ker10": r[19],
            "rise_net10_pct": r[20], "rise_candidate": r[21], "rise_streak_days": r[22],
        }

        bars = con.execute(
            "SELECT date, open, high, low, close, adj_close, volume FROM daily_bars "
            "WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT ?",
            [t, snap, HIST_BARS],
        ).fetchall()[::-1]
        if len(bars) < min_bars:
            continue

        ma_rows = con.execute(
            "SELECT date, ma50, ma150, ma200 FROM derived_daily "
            "WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT ?",
            [t, snap, CHART_DAYS],
        ).fetchall()[::-1]

        prev = con.execute(
            "SELECT composite FROM derived_daily WHERE ticker = ? AND date < ? "
            "ORDER BY date DESC LIMIT 1",
            [t, snap],
        ).fetchone()

        vrow = con.execute(
            "SELECT pe, ps, evs, ev_ebitda, growth, rule40, as_of_period_end, as_of_filed, "
            "as_of_effective_eod, valuation_basis, date "
            "FROM valuation_daily WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT 1",
            [t, snap],
        ).fetchone()
        valuation = None
        if vrow is not None:
            n_val += 1
            # freshness measures the fiscal vintage (date − period_end), NOT the disclosure
            # latency; disclosure_lag exposes filed − period_end separately (formal-filing PIT).
            age = (vrow[10] - vrow[6]).days if vrow[6] is not None else None
            lag = (vrow[7] - vrow[6]).days if (vrow[6] is not None and vrow[7] is not None) else None
            valuation = {
                "pe": _num(vrow[0], 2), "ps": _num(vrow[1], 2), "evs": _num(vrow[2], 2),
                "ev_ebitda": _num(vrow[3], 2), "growth": _num(vrow[4], 4), "rule40": _num(vrow[5], 4),
                "as_of_period_end": _iso(vrow[6]), "as_of_filed": _iso(vrow[7]),
                "as_of_effective_eod": _iso(vrow[8]), "valuation_basis": vrow[9],
                "as_of_age_days": age, "disclosure_lag_days": lag, "freshness": freshness(age),
            }

        # C9 self-check: reconstruct composite from exported components at snap k.
        recon = 100 * sum(w[key] * (comp[key] or 0) for key in w)
        if r[4] is not None:
            max_drift = max(max_drift, abs(recon - r[4]))

        ris_block = _riser(rk)
        if ris_block["net10"] is not None:
            n_ris += 1
        if ris_block["candidate"]:
            n_cand += 1
        # No reconstruct guard for the riser block: every field is read verbatim from
        # derived_daily (the screen is NEVER re-derived here — candidate included), so
        # there is no drift to catch (unlike the composite C9 guard below).

        stocks.append({
            "ticker": t,
            "name": r[1],
            "sector": r[2],
            "mktcap": _num(r[3]),
            "themes": _themes(con, t, snap, has_themes),
            "composite": _num(r[4], 2),
            "composite_prev": _num(prev[0], 2) if prev else None,
            "rank": int(r[5]) if r[5] is not None else None,
            "components": {key: _num(comp[key], 4) for key in comp},
            "evidence": _evidence(d, bars, snap),
            "riser": ris_block,
            "valuation": valuation,
        })
        # v2 payload split: the ~90d mini-chart rides in its OWN per-stock file
        # (board/<t>.json), built from the SAME bars/ma_rows in this pass (C9). The
        # card fetches it lazily on render, so it stays out of the up-front bulk.
        chart_by_ticker[t] = {
            "schema_version": SCHEMA_VERSION,
            "ticker": t,
            "chart": _chart(bars, ma_rows),
        }

    if max_drift > COMPOSITE_TOL:
        raise RuntimeError(
            f"C9 drift: reconstructed composite differs from engine by {max_drift:.6f} "
            f"(> {COMPOSITE_TOL}). Exported c_* or weights({k}) are out of sync with the engine."
        )
    bulk = {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": _iso(snap),
        "composite_recon_max_drift": round(max_drift, 9),
        "count": len(stocks),
        "valuation_coverage": n_val,
        "riser_coverage": n_ris,
        "riser_candidates": n_cand,
        "riser_top_n": riser.TOP_N,
        "stocks": stocks,
    }
    _self_check(bulk, chart_by_ticker)
    return bulk, chart_by_ticker


# every chart list column is index-aligned to dates[] (high_52w is a scalar, excluded).
_CHART_COLS = ("open", "high", "low", "close", "adj_close", "volume", "ma50", "ma150", "ma200")


def _self_check(bulk: dict, chart_by_ticker: dict) -> None:
    """Fail loudly here (not silently in the browser) if the v2 split contract breaks:

    1. every bulk stock has its OWN chart file (no rendered card hits a missing chart);
    2. each chart file's ticker matches, and its list columns are index-aligned to
       dates[] (len==len(dates)) so MiniChart's parallel-array reads stay in bounds;
    3. no orphan chart without a bulk stock (cross-file 1:1 — a shrinking universe
       leaves none behind).
    The chart VALUES are the engine's (_chart derives them from the same bars, C9);
    this guards the SPLIT (where the chart lives + alignment), not the numbers.
    """
    tickers = {s["ticker"] for s in bulk["stocks"]}
    for t in tickers:
        det = chart_by_ticker.get(t)
        if det is None:
            raise RuntimeError(f"{t}: no chart file emitted (bulk stock without board/<t>.json)")
        if det.get("ticker") != t:
            raise RuntimeError(f"{t}: chart file ticker={det.get('ticker')} != {t}")
        chart = det.get("chart") or {}
        dates = chart.get("dates")
        if not dates:
            raise RuntimeError(f"{t}: chart has no dates[]")
        n = len(dates)
        for col in _CHART_COLS:
            c = chart.get(col)
            if c is None or len(c) != n:
                raise RuntimeError(
                    f"{t}: chart.{col} length {None if c is None else len(c)} != dates {n}"
                )
    orphans = set(chart_by_ticker) - tickers
    if orphans:
        raise RuntimeError(f"chart files without a bulk stock: {sorted(orphans)[:5]}")


def _write_chart_detail(out_dir: Path, chart_by_ticker: dict) -> int:
    """Write per-stock mini-charts to <out_dir>/board/<TICKER>.json, clearing stale
    files first so a shrinking universe never leaves orphaned charts behind (mirrors
    ocean._write_detail). The bulk board.json sits beside this board/ dir, untouched.
    Returns bytes written."""
    det_dir = out_dir / "board"
    det_dir.mkdir(parents=True, exist_ok=True)
    for old in det_dir.glob("*.json"):
        old.unlink()
    total = 0
    for t, det in chart_by_ticker.items():
        p = det_dir / f"{t}.json"
        p.write_text(json.dumps(det, ensure_ascii=False, separators=(",", ":")) + "\n")
        total += p.stat().st_size
    return total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide export: Discovery board.json (v2 bulk + per-stock chart).")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output bulk JSON path (charts -> <dir>/board/<T>.json)")
    ap.add_argument("--k", type=float, default=0.5,
                    help="composite fixed weighting (knob removed, PRD §16); must match the k `make compute` used")
    ap.add_argument("--limit", type=int, default=None, help="cap to top-N by composite (default: all)")
    ap.add_argument("--min-bars", type=int, default=60, help="skip stocks with fewer bars")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    board, chart_by_ticker = build_board(con, k=args.k, limit=args.limit, min_bars=args.min_bars)
    con.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(board, ensure_ascii=False, separators=(",", ":")) + "\n")
    chart_bytes = _write_chart_detail(out.parent, chart_by_ticker)

    kb = out.stat().st_size / 1024
    chart_kb = chart_bytes / 1024
    print(f"[board] {args.out}  as_of={board['as_of_date']}  stocks={board['count']}  "
          f"valuation={board['valuation_coverage']}  riser={board['riser_coverage']}  "
          f"riser_candidates={board['riser_candidates']}(top-{board['riser_top_n']})  "
          f"C9_drift={board['composite_recon_max_drift']}  "
          f"bulk={kb:.1f}KB  charts={len(chart_by_ticker)}×→{chart_kb:.1f}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
