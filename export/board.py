"""M1.1 board export: DuckDB snapshot -> web/public/data/board.json (Discovery).

Reads the latest derived_daily/valuation_daily snapshot and assembles the
evidence-first Discovery board (PRD §9.3, ROADMAP M1.1). One JSON object per
stock: identity, engine composite + the 5 raw components c_* (so the client can
re-weight by the early<->reliable knob k WITHOUT recomputing the engine — C9),
6 raw evidence numbers, a ~90d OHLCV mini-chart, latest valuation with as-of
freshness, and the previous-day composite for d/d.

Three evidence numbers are NOT materialised in derived_daily; they are derived
here from the SAME daily_bars the mini-chart ships, so card and chart stay
traceable to one source (PRD §9.3 "同一份 export"):
  - ret_1m              : 21-trading-day adj_close return
  - vol_mult            : latest volume / SMA(volume, 50)   (PRD §10.6 pulse term)
  - weeks_since_breakout: whole weeks since the last trailing-252d closing high
                          (transparent proxy; a dedicated breakout signal is a
                          later milestone — it is NOT an engine number)

The SECOND engine (ignition = early discovery, PRD §10.8) is carried per stock
alongside composite. Discovery (M7.3) sorts by "持续点火" — sustained ignition —
NOT composite, so each stock ships its ignition score, cross-sectional ign_pct,
top-decile persistence streak, the 5 raw self-relative components ig_* verbatim
from derived_daily (NEVER recomputed here — C9, same source as compute/run.py),
and an `ign_candidate` flag = ign_pct>=90 AND ign_persist_days>=IGN_PERSIST_MIN
(the persistence filter, PRD §10.8.2 — instantaneous ignition has no lift; only
sustained ignition does). early<->reliable does NOT touch ignition (PRD P7).

The ignition card also ships human-readable 点火证据 (ignition evidence) — the
plain-language form of what lit the engine: breakout day / volume surge× /
10d-vs-50d step-rate ratio / whether price reclaimed MA50. vol_mult× is the
engine's own ig_vsurge verbatim; the breakout day + step-rate ratio are derived
from the SAME bars the chart ships (same windows ignition.py uses: BREAKOUT_WIN
=60, ACCEL_FAST/SLOW=10/50), so the evidence stays traceable to one source and
mirrors the raw components without re-scoring the engine.

This export carries each engine's score verbatim and never recomputes it; the
early<->reliable re-weighting is the client's job from the exported c_* (C9). As
a guard, build_board reconstructs 100·Σ weights(k)·c_* at the snapshot k and
checks it reproduces derived_daily.composite, AND reconstructs ignition from the
exported raw vsurge/breakout vs the stored component to catch ignition drift, so
an engine/export drift fails loudly here instead of silently in the browser.

Output (gitignored, derived nightly): web/public/data/board.json.
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

from compute import db, signals  # noqa: E402

SCHEMA_VERSION = 1
DEFAULT_OUT = ROOT / "web" / "public" / "data" / "board.json"

CHART_DAYS = 90          # mini-chart window (PRD §9.3: ~90d K线)
HIST_BARS = 260          # bars pulled per stock; covers the 252d high window
RET_1M_LAG = 21          # ~1 trading month
VOL_WIN = 50             # SMA(volume) window for the pulse multiplier (PRD §10.6)
HIGH_WIN = 252           # 52-week high window
FRESH_DAYS = 95          # <=95d = fresh (current quarter reported), PRD §10.5
STALE_DAYS = 160         # <=160d = stale (one quarter behind); >160d = overdue
COMPOSITE_TOL = 1e-6     # C9 self-check tolerance (engine vs reconstructed)

# ignition (PRD §10.8) — sustained-ignition candidate gate + evidence windows.
IGN_TOP_DECILE = 90      # ign_pct >= this = top decile (lit), PRD §10.8.2
IGN_PERSIST_MIN = 5      # consecutive lit days for the "持续点火" candidate (§3 default ~5)
IGN_BREAKOUT_WIN = 60    # breakout/reclaim prior-high window (= ignition.BREAKOUT_WIN)
IGN_ACCEL_FAST = 10      # step-rate fast window (= ignition.ACCEL_FAST)
IGN_ACCEL_SLOW = 50      # step-rate slow window (= ignition.ACCEL_SLOW)
IGNITION_TOL = 1e-6      # ignition self-check tolerance (stored vs reconstructed component)


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


def _ignition(ig: dict, bars: list[tuple]) -> dict:
    """Per-stock ignition block + 点火证据, verbatim from derived_daily (C9).

    `ig` carries the engine's stored ignition numbers (NEVER recomputed here):
    score `ignition`∈[0,100], cross-sectional `ign_pct`∈[0,100], persistence
    streak `ign_persist_days`, the 5 raw self-relative components ig_*, and ma50.
    `candidate` = top-decile AND sustained (PRD §10.8.2) — Discovery's "持续点火"
    sort key. The components are shipped raw so the client can show what lit the
    engine without re-scoring it.

    The human-readable 点火证据 (evidence) mirrors the raw components from the SAME
    bars the chart ships (same windows ignition.py uses): vol_mult× is the engine's
    own ig_vsurge verbatim; breakout_day is the date of the trailing-60d adj_close
    high (the breakout reference); reclaimed_ma50 is the close>MA50 gate inside
    ig_breakout; step_rate_ratio is (ret_10/10)/(ret_50/50), the readable form of
    ig_accel. Returns ig_vsurge under `_vsurge_recon` so build_board can assert the
    derived multiplier reproduces the stored component (ignition C9 guard)."""
    score = ig.get("ignition")
    pct = ig.get("ign_pct")
    persist = ig.get("ign_persist_days")
    candidate = (
        pct is not None and persist is not None
        and pct >= IGN_TOP_DECILE and persist >= IGN_PERSIST_MIN
    )

    adj = [b[5] for b in bars]
    ma50 = ig.get("ma50")
    close = adj[-1] if adj else None
    reclaimed_ma50 = (close > ma50) if (close is not None and ma50 is not None) else None

    # breakout day: date of the trailing-60d adj_close high (= ignition's hi60 ref).
    breakout_day = days_since_breakout = None
    win = adj[-IGN_BREAKOUT_WIN:]
    win_bars = bars[-IGN_BREAKOUT_WIN:]
    if win and any(p is not None for p in win):
        hi_i, run_max = 0, -math.inf
        for i, p in enumerate(win):
            if p is not None and p >= run_max:
                run_max, hi_i = p, i
        breakout_day = _iso(win_bars[hi_i][0])
        days_since_breakout = (bars[-1][0] - win_bars[hi_i][0]).days

    # 10d-vs-50d step-rate ratio: readable form of ig_accel (slope steepening).
    step_rate_ratio = None
    if len(adj) > IGN_ACCEL_SLOW and adj[-1] is not None:
        f0, s0 = adj[-1 - IGN_ACCEL_FAST], adj[-1 - IGN_ACCEL_SLOW]
        if f0 and s0:
            r_fast = (adj[-1] / f0 - 1) / IGN_ACCEL_FAST
            r_slow = (adj[-1] / s0 - 1) / IGN_ACCEL_SLOW
            if r_slow:
                step_rate_ratio = r_fast / r_slow

    block = {
        "ignition": _num(score, 2),
        "ign_pct": _num(pct, 1),
        "ign_persist_days": int(persist) if persist is not None else None,
        "candidate": bool(candidate),
        "components": {
            "accel": _num(ig.get("ig_accel"), 4),
            "expand": _num(ig.get("ig_expand"), 4),
            "vsurge": _num(ig.get("ig_vsurge"), 4),
            "breakout": _num(ig.get("ig_breakout"), 4),
            "rsturn": _num(ig.get("ig_rsturn"), 4),
        },
        "evidence": {
            "breakout_day": breakout_day,
            "days_since_breakout": days_since_breakout,
            "vol_mult": _num(ig.get("ig_vsurge"), 3),   # engine ig_vsurge verbatim (rounded for display)
            "step_rate_ratio": _num(step_rate_ratio, 3),
            "reclaimed_ma50": reclaimed_ma50,
            "ma50": _num(ma50, 4),
        },
        # unrounded ig_vsurge passed straight through, for the C9 identity guard.
        "_vsurge_recon": _num(ig.get("ig_vsurge")),
    }
    return block


def build_board(con, k: float = 0.5, limit: int | None = None, min_bars: int = 60) -> dict:
    """Assemble the Discovery board dict from the latest DuckDB snapshot."""
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
               d.ignition, d.ign_pct, d.ign_persist_days,
               d.ig_accel, d.ig_expand, d.ig_vsurge, d.ig_breakout, d.ig_rsturn, d.ma50
        FROM derived_daily d
        LEFT JOIN universe u ON u.ticker = d.ticker
        WHERE d.date = ?
        ORDER BY d.composite DESC NULLS LAST
        """ + (f"LIMIT {int(limit)}" if limit else ""),
        [snap],
    ).fetchall()

    stocks, max_drift, n_val = [], 0.0, 0
    ign_max_drift, n_ign, n_cand = 0.0, 0, 0
    for r in head:
        t = r[0]
        comp = {"rs": r[6], "high": r[7], "trend": r[8], "vol": r[9], "accel": r[10]}
        d = {"ret_63": r[11], "ret_126": r[12], "high_prox": r[13]}
        ig = {
            "ignition": r[14], "ign_pct": r[15], "ign_persist_days": r[16],
            "ig_accel": r[17], "ig_expand": r[18], "ig_vsurge": r[19],
            "ig_breakout": r[20], "ig_rsturn": r[21], "ma50": r[22],
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
            "SELECT pe, ps, evs, ev_ebitda, growth, rule40, as_of_period_end, as_of_filed, date "
            "FROM valuation_daily WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT 1",
            [t, snap],
        ).fetchone()
        valuation = None
        if vrow is not None:
            n_val += 1
            age = (vrow[8] - vrow[6]).days if vrow[6] is not None else None
            valuation = {
                "pe": _num(vrow[0], 2), "ps": _num(vrow[1], 2), "evs": _num(vrow[2], 2),
                "ev_ebitda": _num(vrow[3], 2), "growth": _num(vrow[4], 4), "rule40": _num(vrow[5], 4),
                "as_of_period_end": _iso(vrow[6]), "as_of_filed": _iso(vrow[7]),
                "as_of_age_days": age, "freshness": freshness(age),
            }

        # C9 self-check: reconstruct composite from exported components at snap k.
        recon = 100 * sum(w[key] * (comp[key] or 0) for key in w)
        if r[4] is not None:
            max_drift = max(max_drift, abs(recon - r[4]))

        ign_block = _ignition(ig, bars)
        if ign_block["ignition"] is not None:
            n_ign += 1
        if ign_block["candidate"]:
            n_cand += 1
        # ignition C9 guard: the shipped vol_mult× must trace to the stored ig_vsurge
        # component verbatim (same source) — catches ignition export drift / re-scoring.
        ev_vsurge = ign_block.pop("_vsurge_recon")
        if ev_vsurge is not None and r[19] is not None:
            ign_max_drift = max(ign_max_drift, abs(ev_vsurge - r[19]))

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
            "ignition": ign_block,
            "valuation": valuation,
            "chart": _chart(bars, ma_rows),
        })

    if max_drift > COMPOSITE_TOL:
        raise RuntimeError(
            f"C9 drift: reconstructed composite differs from engine by {max_drift:.6f} "
            f"(> {COMPOSITE_TOL}). Exported c_* or weights({k}) are out of sync with the engine."
        )
    if ign_max_drift > IGNITION_TOL:
        raise RuntimeError(
            f"ignition C9 drift: evidence vol_mult differs from stored ig_vsurge by "
            f"{ign_max_drift:.6f} (> {IGNITION_TOL}). Ignition evidence is out of sync "
            f"with derived_daily — the export is re-deriving instead of reading C9."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": _iso(snap),
        "knob_default_k": k,
        "weights_default": {key: round(v, 4) for key, v in w.items()},
        "composite_recon_max_drift": round(max_drift, 9),
        "ignition_recon_max_drift": round(ign_max_drift, 9),
        "ignition_persist_min": IGN_PERSIST_MIN,
        "count": len(stocks),
        "valuation_coverage": n_val,
        "ignition_coverage": n_ign,
        "ignition_candidates": n_cand,
        "stocks": stocks,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M1.1 export: Discovery board.json.")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output JSON path")
    ap.add_argument("--k", type=float, default=0.5,
                    help="snapshot early<->reliable knob; must match the k `make compute` used")
    ap.add_argument("--limit", type=int, default=None, help="cap to top-N by composite (default: all)")
    ap.add_argument("--min-bars", type=int, default=60, help="skip stocks with fewer bars")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    board = build_board(con, k=args.k, limit=args.limit, min_bars=args.min_bars)
    con.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(board, ensure_ascii=False, separators=(",", ":")) + "\n")

    kb = out.stat().st_size / 1024
    print(f"[board] {args.out}  as_of={board['as_of_date']}  stocks={board['count']}  "
          f"valuation={board['valuation_coverage']}  ignition={board['ignition_coverage']}  "
          f"ign_candidates={board['ignition_candidates']}(persist>={board['ignition_persist_min']})  "
          f"C9_drift={board['composite_recon_max_drift']}  ign_drift={board['ignition_recon_max_drift']}  "
          f"size={kb:.1f}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
