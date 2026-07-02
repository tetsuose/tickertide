"""Ocean export: DuckDB daily snapshots -> web/public/data/ocean.json (schema v5).

Ocean is the wide-explore surface (PRD §9.2), a **steady-riser × Valuation daily SEA-LEVEL
map** (2026-07-02 spine pivot II — was base→breakout-strength × Valuation; breakout retired §10.9):
  - y = `rise_net10_pct` (0-100, the 10d-net-rise cross-sectional percentile, §10.8) with a
    fixed "sea level" at 90 — a VISUAL reference line only (top decile of the last-2-weeks
    rise). It is NOT the candidate gate.
  - x = raw trailing P/S TTM (`ps`) on a LOG axis — the raw multiple, NOT a valuation
    percentile and NOT a composite valuation score (no implicit threshold params, §16).

`cand` is the STORED `derived_daily.rise_candidate` flag — the SAME gate+top-N the Risers
board uses (gate up10>=0.6 AND net10>0, net10 top-N; computed ONCE in compute/run.py and
NEVER re-derived from the y percentile here — C9 single source, the #92-#94 boundary lesson).
An Ocean candidate point is the SAME population as the Risers board, traceable point-for-point.
recall-first: false positives are expected, fundamentals/financials are the downstream
precision stage. breakout/composite/ignition are gone from this surface.

PAYLOAD SPLIT (schema v5, payload reduction — scales to the full universe):
Drawing every animation frame needs only THREE fields per (ticker, day): `ps` (x), `rise_pct`
(y) and `cand` (the candidate glow/ring). The other tooltip fields are shown ONLY in the hover
tooltip, for one stock at one date. Measured, those are the bulk of the compressed payload.
So the export splits in two:
  - BULK `ocean.json` — every stock's draw fields in a COLUMNAR layout: per stock, three
    arrays (`ps` / `rise_pct` / `cand`) index-aligned to `dates[]` (oldest→newest). A null in
    `ps`/`rise_pct` at index i = no renderable position that day (the tween fades it in/out;
    positions are never fabricated). This is the only file the client downloads up front.
  - DETAIL `ocean/<TICKER>.json` — the tooltip-only fields (net5 / net10 / net20 / up10 /
    ddw10 / streak_days / evs / pe / ev_ebitda / freshness + the formal-filing PIT dates
    as_of_period_end / as_of_effective_eod), all COLUMNAR and index-aligned to the SAME
    `dates[]`, plus a scalar valuation_basis. Fetched lazily on hover, per stock — so a
    session only downloads detail for names actually inspected.
Both files derive from the SAME per-stock pipeline in one pass (C9): every field still traces
to derived_daily / valuation_daily / universe; the screen is NEVER recomputed.

Field provenance:
  - rise_pct / cand (and detail net5 / net10 / net20 / up10 / ddw10 / streak_days) : verbatim
    from derived_daily — the SAME columns board.py ships (C9). Every one is chart-verifiable
    (§10.8: count the candles).
  - ps (and detail evs / pe / ev_ebitda / freshness) : from valuation_daily (C9). `ps` is the
    x-axis; the rest + the §10.5 as-of freshness bucket ride along for the tooltip.

Animation contract: the bulk carries ONLY real EOD snapshots. The client lerps positions
between adjacent dates for the play tween but reads tooltip/state off the real snapshot — no
fabricated intra-window trading days here (PRD §9.2).

Inclusion rule: a stock is exported iff on the LATEST date it has BOTH a valid rise_net10_pct
AND a valid ps (>0) AND is in the universe — i.e. it has a renderable (x,y) on the default view.
For older dates a stock's columns are null where either coordinate is missing.

`x_domain` = [min, max] of every valid P/S across the exported window, computed from the data
for the client's log scale — NO hard-coded valuation threshold (PRD §9.2/§16).

Output (gitignored, derived nightly): web/public/data/ocean.json (bulk, schema_version 5) +
web/public/data/ocean/<TICKER>.json (per-stock hover detail, schema_version 5).
Math spec: PRD §10.8 (steady-riser) / §10.5 (P/S); UX: §9.2; schema: PRD §12 / File-Contracts.
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

from compute import db  # noqa: E402

SCHEMA_VERSION = 5
DEFAULT_OUT = ROOT / "web" / "public" / "data" / "ocean.json"

DEFAULT_DAYS = 60        # ~3 months of daily EOD snapshots (sea-level animation window)
SEA_LEVEL = 90           # rise_net10_pct sea level — VISUAL reference (top decile), NOT the gate
FRESH_DAYS = 95          # valuation as-of freshness cutoff (PRD §10.5/§9.5; == board.py)
STALE_DAYS = 160         # <=160d = stale (one quarter behind); >160d = overdue

# The hover-only fields shipped per stock in ocean/<TICKER>.json (columnar, dates-aligned).
# as_of_period_end/as_of_effective_eod are per-day dates (formal-filing PIT, §10.5) so the
# tooltip stays honest while the date slider scrubs history. valuation_basis is a scalar.
DETAIL_FIELDS = (
    "net5", "net10", "net20", "up10", "ddw10", "streak_days",
    "evs", "pe", "ev_ebitda", "freshness",
    "as_of_period_end", "as_of_effective_eod",
)


def freshness(age_days: int | None) -> str | None:
    """As-of bucket per PRD §9.5/§10.5: fresh <=95d, stale <=160d, else overdue (== board.py)."""
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
    """Point-in-time theme chips as-of the latest snapshot (PRD §7 C3): per theme the latest
    as_of_date<=snap with exposure>0, via the canonical db.theme_membership_asof — the SAME
    PIT query board.py uses, so Ocean's chips match the Breakouts card's (C9). Highest
    exposure first. Empty until themes are seeded; table may not exist pre-M4."""
    if not has_themes:
        return []
    m = db.theme_membership_asof(con, snap, ticker=ticker).sort_values("exposure", ascending=False)
    return [{"theme": r.theme, "exposure": _num(r.exposure, 4)} for r in m.itertuples()]


def trading_days(con, n_days: int) -> list:
    """The most recent `n_days` distinct trading days in derived_daily, oldest first. The
    newest == max(derived_daily.date) == board/Breakouts as_of, so Ocean's default (latest)
    positions match the Breakouts numbers exactly (C9)."""
    rows = con.execute(
        "SELECT DISTINCT date FROM derived_daily ORDER BY date DESC LIMIT ?", [int(n_days)]
    ).fetchall()
    return [r[0] for r in rows][::-1]


def _ps2(raw):
    """Stored P/S (2dp) iff renderable on the log axis: a positive finite multiple, else None.
    Validate the ROUNDED value we actually store/plot — a tiny raw ps that rounds to 0.00 is
    NOT renderable (degenerate on a log axis). Checking the raw value but storing the rounded
    one would let a 0.001 ps slip in as 0.00 and trip _self_check (seen on real data: MCD)."""
    v = _num(raw, 2)
    return v if (v is not None and v > 0) else None


def build_ocean(con, n_days: int = DEFAULT_DAYS, limit: int | None = None) -> tuple[dict, dict]:
    """Assemble the Ocean export (schema v4) from DuckDB.

    Returns (bulk, detail_by_ticker):
      - bulk: the dict written to ocean.json (columnar draw fields per stock).
      - detail_by_ticker: {ticker -> detail dict} written to ocean/<ticker>.json (hover fields).
    Both are built in ONE pass over the same per-stock data so they can never desync (C9).
    """
    if db.count(con, "derived_daily") == 0:
        raise RuntimeError("derived_daily is empty — run `make compute` first.")
    dates = trading_days(con, n_days)
    if not dates:
        raise RuntimeError("no trading dates in derived_daily.")
    latest = dates[-1]
    has_themes = _table_exists(con, "theme_membership")

    ph = ",".join(["?"] * len(dates))
    # steady-riser (y + candidate + tooltip evidence) per (ticker, date) — verbatim
    # derived_daily columns (C9). cand = the STORED rise_candidate flag, never re-derived.
    rise_by = {
        (t, d): (pct, cand, n5, n10, n20, up, ddw, streak)
        for t, d, pct, cand, n5, n10, n20, up, ddw, streak in con.execute(
            f"SELECT ticker, date, rise_net10_pct, rise_candidate, rise_net5, rise_net10, "
            f"rise_net20, rise_up10, rise_ddw10, rise_streak_days "
            f"FROM derived_daily WHERE date IN ({ph})",
            dates,
        ).fetchall()
    }
    # valuation (x + tooltip) per (ticker, date) — same valuation_daily as board/Valuation (C9).
    val_by = {
        (t, d): (ps, evs, pe, ev_ebitda, period_end, eff_eod)
        for t, d, ps, evs, pe, ev_ebitda, period_end, eff_eod in con.execute(
            f"SELECT ticker, date, ps, evs, pe, ev_ebitda, as_of_period_end, as_of_effective_eod "
            f"FROM valuation_daily WHERE date IN ({ph})",
            dates,
        ).fetchall()
    }
    meta = {
        t: (sector, mktcap)
        for t, sector, mktcap in con.execute(
            "SELECT ticker, sector, mktcap FROM universe"
        ).fetchall()
    }

    # Inclusion: renderable on the LATEST date (valid rise_net10_pct AND valid ps) AND in universe.
    # Sort by mktcap desc so big caps paint first (small drawn on top, as the canvas expects).
    latest_tickers = []
    for t in meta:
        rk = rise_by.get((t, latest))
        vv = val_by.get((t, latest))
        if rk and rk[0] is not None and vv and _ps2(vv[0]) is not None:
            latest_tickers.append(t)
    latest_tickers.sort(key=lambda t: (meta[t][1] if meta[t][1] is not None else -1.0), reverse=True)
    if limit:
        latest_tickers = latest_tickers[:limit]

    all_ps: list[float] = []
    stocks: list[dict] = []
    detail_by_ticker: dict[str, dict] = {}
    for t in latest_tickers:
        # bulk columnar draw fields + detail columnar hover fields, built in lockstep so a
        # null day is null across BOTH (index alignment to dates[] is the cross-file contract).
        ps_col: list[float | None] = []
        rise_col: list[float | None] = []
        cand_col: list[int] = []
        det: dict[str, list] = {f: [] for f in DETAIL_FIELDS}
        for d in dates:
            rk = rise_by.get((t, d))
            vv = val_by.get((t, d))
            rise_pct = rk[0] if rk else None
            ps = _ps2(vv[0]) if vv else None   # rounded-to-2dp P/S, as stored (None if degenerate)
            if rise_pct is None or ps is None:
                ps_col.append(None)         # no renderable position this day (tween fades it)
                rise_col.append(None)
                cand_col.append(0)
                for f in DETAIL_FIELDS:
                    det[f].append(None)     # detail stays index-aligned: null where bulk is null
                continue
            all_ps.append(ps)
            period_end = vv[4]
            eff_eod = vv[5]
            age = (d - period_end).days if period_end is not None else None
            ps_col.append(ps)                     # already rounded to 2dp by _ps2 (and > 0)
            rise_col.append(_num(rise_pct, 1))
            cand_col.append(1 if rk[1] == 1 else 0)   # STORED flag, verbatim (C9 single source)
            det["net5"].append(_num(rk[2], 4))
            det["net10"].append(_num(rk[3], 4))
            det["net20"].append(_num(rk[4], 4))
            det["up10"].append(_num(rk[5], 2))
            det["ddw10"].append(_num(rk[6], 4))
            det["streak_days"].append(int(rk[7]) if rk[7] is not None else 0)
            det["evs"].append(_num(vv[1], 2))
            det["pe"].append(_num(vv[2], 2))
            det["ev_ebitda"].append(_num(vv[3], 2))
            det["freshness"].append(freshness(age))
            det["as_of_period_end"].append(_iso(period_end))
            det["as_of_effective_eod"].append(_iso(eff_eod))
        sector, mktcap = meta[t]
        stocks.append({
            "ticker": t,
            "sector": sector,
            "mktcap": _num(mktcap),     # raw USD (client renders radius √(mktcap/1e9), same as board)
            "themes": _themes(con, t, latest, has_themes),
            "ps": ps_col,
            "rise_pct": rise_col,
            "cand": cand_col,
        })
        detail_by_ticker[t] = {
            "schema_version": SCHEMA_VERSION,
            "ticker": t,
            "n": len(dates),
            "valuation_basis": "formal_filing_pit",  # scalar:口径 tag for the tooltip (formal-filing PIT)
            **det,
        }

    # log-scale x domain from the data (no hard-coded valuation threshold, §16). all_ps is
    # non-empty whenever any stock is included (inclusion requires a valid latest ps).
    x_domain = [round(min(all_ps), 4), round(max(all_ps), 4)] if all_ps else [0.1, 100.0]

    bulk = {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": _iso(latest),
        "axis": {"x_metric": "ps", "x_scale": "log", "y_metric": "rise_net10_pct", "sea_level": SEA_LEVEL},
        "dates": [_iso(d) for d in dates],
        "x_domain": x_domain,
        "count": len(stocks),
        "stocks": stocks,
    }

    _self_check(bulk, detail_by_ticker)

    return bulk, detail_by_ticker


def _self_check(bulk: dict, detail_by_ticker: dict) -> None:
    """Fail loudly here (not silently in the browser) if the v5 contract breaks:

    1. every stock's ps/rise_pct/cand columns have len==len(dates), and a NON-NULL latest
       coordinate (renderable default view);
    2. every present day has rise_pct ∈ [0,100], ps > 0 (log axis), cand ∈ {0,1};
    3. cand==1 ⇒ the stored riser gate is visible in the detail evidence (up10 >= 0.6 and
       net10 > 0) — guards flag/evidence pairing WITHOUT re-deriving the top-N (the flag
       itself is the stored single truth; candidate is NOT implied by rise_pct >= sea level);
    4. x_domain is a positive ordered interval (so the client's log scale is well-defined);
    5. each stock has a detail file, dates-aligned (len==n==len(dates)), and the detail is
       null at EXACTLY the days the bulk has no position (cross-file index alignment, C9).
    """
    dates = bulk["dates"]
    n = len(dates)
    x_domain = bulk["x_domain"]
    for s in bulk["stocks"]:
        t = s["ticker"]
        ps, rise, cand = s["ps"], s["rise_pct"], s["cand"]
        if not (len(ps) == len(rise) == len(cand) == n):
            raise RuntimeError(f"{t}: column lengths {len(ps)}/{len(rise)}/{len(cand)} != n_days {n}")
        if ps[-1] is None or rise[-1] is None:
            raise RuntimeError(f"{t}: latest coordinate is null but stock was included")
        det = detail_by_ticker.get(t)
        if det is None:
            raise RuntimeError(f"{t}: no detail file emitted")
        if det.get("n") != n:
            raise RuntimeError(f"{t}: detail n={det.get('n')} != n_days {n}")
        for f in DETAIL_FIELDS:
            col = det.get(f)
            if col is None or len(col) != n:
                raise RuntimeError(f"{t}: detail.{f} length {None if col is None else len(col)} != n_days {n}")
        for i in range(n):
            present = ps[i] is not None and rise[i] is not None
            if not present:
                # a null day: cand must be 0 and EVERY detail field null (index alignment).
                if cand[i] != 0:
                    raise RuntimeError(f"{t}: cand={cand[i]} on a null day {dates[i]}")
                for f in DETAIL_FIELDS:
                    if det[f][i] is not None:
                        raise RuntimeError(f"{t}: detail.{f} non-null on a null day {dates[i]}")
                continue
            if not (ps[i] > 0):
                raise RuntimeError(f"{t}: ps={ps[i]} on {dates[i]} (log axis needs ps>0)")
            if not (0 <= rise[i] <= 100):
                raise RuntimeError(f"{t}: rise_pct={rise[i]} out of [0,100] on {dates[i]}")
            if cand[i] not in (0, 1):
                raise RuntimeError(f"{t}: cand={cand[i]} not in {{0,1}} on {dates[i]}")
            if cand[i] == 1:
                up, n10 = det["up10"][i], det["net10"][i]
                if up is None or n10 is None or up < 0.6 or n10 <= 0:
                    raise RuntimeError(
                        f"{t}: candidate on {dates[i]} but gate evidence fails (up10={up}, net10={n10})"
                    )
    if not (x_domain[0] > 0 and x_domain[0] <= x_domain[1]):
        raise RuntimeError(f"x_domain {x_domain} is not a positive ordered interval (log scale).")


def _write_detail(out_dir: Path, detail_by_ticker: dict) -> int:
    """Write per-stock hover detail to <out_dir>/ocean/<TICKER>.json, clearing stale files
    first so a shrinking universe never leaves orphaned detail behind. Returns bytes written."""
    det_dir = out_dir / "ocean"
    det_dir.mkdir(parents=True, exist_ok=True)
    for old in det_dir.glob("*.json"):
        old.unlink()
    total = 0
    for t, det in detail_by_ticker.items():
        p = det_dir / f"{t}.json"
        p.write_text(json.dumps(det, ensure_ascii=False, separators=(",", ":")) + "\n")
        total += p.stat().st_size
    return total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide export: Ocean steady-riser × valuation daily ocean.json (v5 bulk + detail).")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output bulk JSON path (detail -> <dir>/ocean/<T>.json)")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS, help="number of daily EOD snapshots")
    ap.add_argument("--limit", type=int, default=None, help="cap to top-N by mktcap (default: all)")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    bulk, detail_by_ticker = build_ocean(con, n_days=args.days, limit=args.limit)
    con.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bulk, ensure_ascii=False, separators=(",", ":")) + "\n")
    det_bytes = _write_detail(out.parent, detail_by_ticker)

    kb = out.stat().st_size / 1024
    det_kb = det_bytes / 1024
    n_cand = sum(1 for s in bulk["stocks"] if s["cand"][-1] == 1)
    print(f"[ocean] {args.out}  as_of={bulk['as_of_date']}  days={len(bulk['dates'])}  "
          f"stocks={bulk['count']}  candidates_latest={n_cand}  "
          f"x_domain={bulk['x_domain']}  sea_level={bulk['axis']['sea_level']}  "
          f"bulk={kb:.1f}KB  detail={len(detail_by_ticker)}×→{det_kb:.1f}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
