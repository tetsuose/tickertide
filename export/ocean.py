"""M8 ocean export: DuckDB daily snapshots -> web/public/data/ocean.json (schema v2).

Ocean is the wide-explore surface (PRD §9.2), rebuilt in M8 from the old RS×Valuation
weekly scatter into an **Ignition × Valuation daily SEA-LEVEL map**:
  - y = `ign_pct` (0-100, the ignition cross-sectional percentile, §10.8) with a fixed
    "sea level" at ign_pct = 90. Above the line = lit (igniting / accelerating / breaking
    out / surging volume); jump-height ∝ ign_pct - 90.
  - x = raw trailing P/S TTM (`ps`) on a LOG axis — the raw multiple, NOT a valuation
    percentile and NOT a composite valuation score (no implicit threshold params, §16).

A `candidate` (ign_pct>=90 AND ign_persist_days>=5) is the SAME gate Discovery sorts by
(§10.8.2), so an Ocean point above the sea level is the SAME population as the Discovery
board — traceable point-for-point (C9). Composite is gone from this surface (M8).

Unlike the Discovery board (one latest snapshot per stock), Ocean needs a daily POSITION
SEQUENCE per stock so the client can scrub a date slider and tween the play animation
between adjacent real EOD snapshots. Each stock carries `pts[]` aligned to `dates[]`
(oldest→newest), one point per trading day:
  - ign_pct / ignition / ign_persist_days / candidate : verbatim from derived_daily — the
        SAME columns board.py ships (C9); the engine is NEVER recomputed here.
  - ps / evs / pe / ev_ebitda / freshness : from valuation_daily (C9). `ps` is the x-axis;
        the rest + the §10.5 as-of freshness bucket ride along for the tooltip.
  - ret_10d / ret_1m / vol_mult : evidence numbers from the SAME daily_bars the Discovery
        card uses (board.py's idiom) — ret_Nd = adj_close/LAG(adj_close,N)-1; vol_mult is
        derived_daily.ig_vsurge (the 5/60 volume surge), a stored column read verbatim.

Animation contract (M8): pts carry ONLY real EOD snapshots. The client lerps positions
between adjacent dates for the play tween but reads tooltip/state off the real snapshot —
no fabricated intra-window trading days here (PRD §9.2 §9-9.10).

Inclusion rule: a stock is exported iff on the LATEST date it has BOTH a valid ign_pct
AND a valid ps (>0) AND is in the universe — i.e. it has a renderable (x,y) on the default
view. For older dates a stock's pt is null where either coordinate is missing (the tween
fades it in/out; positions are never fabricated).

`x_domain` = [min, max] of every valid P/S across the exported window, computed from the
data for the client's log scale — NO hard-coded valuation threshold (PRD §9.2/§16).

Output (gitignored, derived nightly): web/public/data/ocean.json (schema_version 2).
Math spec: PRD §10.8 (ignition) / §10.5 (P/S); UX: §9.2; schema: PRD §12 / File-Contracts.
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

SCHEMA_VERSION = 2
DEFAULT_OUT = ROOT / "web" / "public" / "data" / "ocean.json"

DEFAULT_DAYS = 60        # ~3 months of daily EOD snapshots (M8 sea-level animation window)
SEA_LEVEL = 90           # ign_pct sea level (== board.py IGN_TOP_DECILE; top decile, §10.8.2)
IGN_PERSIST_MIN = 5      # candidate persistence gate (== board.py IGN_PERSIST_MIN)
FRESH_DAYS = 95          # valuation as-of freshness cutoff (PRD §10.5/§9.5; == board.py)
STALE_DAYS = 160         # <=160d = stale (one quarter behind); >160d = overdue
RET_10D_LAG = 10         # ret_10d window in trading days (== ignition step-rate fast window)
RET_1M_LAG = 21          # ret_1m window (~1 trading month; == board.py RET_1M_LAG)


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
    PIT query board.py uses, so Ocean's chips match the Discovery card's (C9). Highest
    exposure first. Empty until themes are seeded; table may not exist pre-M4."""
    if not has_themes:
        return []
    m = db.theme_membership_asof(con, snap, ticker=ticker).sort_values("exposure", ascending=False)
    return [{"theme": r.theme, "exposure": _num(r.exposure, 4)} for r in m.itertuples()]


def trading_days(con, n_days: int) -> list:
    """The most recent `n_days` distinct trading days in derived_daily, oldest first. The
    newest == max(derived_daily.date) == board/Discovery as_of, so Ocean's default (latest)
    positions match the Discovery numbers exactly (C9)."""
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


def build_ocean(con, n_days: int = DEFAULT_DAYS, limit: int | None = None) -> dict:
    """Assemble the Ocean daily-snapshot dict (schema v2) from DuckDB."""
    if db.count(con, "derived_daily") == 0:
        raise RuntimeError("derived_daily is empty — run `make compute` first.")
    dates = trading_days(con, n_days)
    if not dates:
        raise RuntimeError("no trading dates in derived_daily.")
    latest = dates[-1]
    has_themes = _table_exists(con, "theme_membership")

    ph = ",".join(["?"] * len(dates))
    # ignition (y + lit state) per (ticker, date) — verbatim derived_daily columns (C9).
    # vol_mult = ig_vsurge (5/60 volume surge), the SAME stored column board ships as 放量×.
    ign_by = {
        (t, d): (ign_pct, ignition, persist, vsurge)
        for t, d, ign_pct, ignition, persist, vsurge in con.execute(
            f"SELECT ticker, date, ign_pct, ignition, ign_persist_days, ig_vsurge "
            f"FROM derived_daily WHERE date IN ({ph})",
            dates,
        ).fetchall()
    }
    # valuation (x + tooltip) per (ticker, date) — same valuation_daily as board/Valuation (C9).
    val_by = {
        (t, d): (ps, evs, pe, ev_ebitda, period_end)
        for t, d, ps, evs, pe, ev_ebitda, period_end in con.execute(
            f"SELECT ticker, date, ps, evs, pe, ev_ebitda, as_of_period_end "
            f"FROM valuation_daily WHERE date IN ({ph})",
            dates,
        ).fetchall()
    }
    # ret_10d / ret_1m (evidence) per (ticker, date): adj_close/LAG(adj_close,N)-1 over the
    # FULL daily_bars history (the lag must see bars before the window), filtered to the
    # window. Same source + formula board.py derives ret_1m from (C9 evidence, not engine).
    ret_by = {
        (t, d): (r10, r1m)
        for t, d, r10, r1m in con.execute(
            f"""
            WITH r AS (
              SELECT ticker, date,
                     adj_close / NULLIF(lag(adj_close, {RET_10D_LAG}) OVER w, 0) - 1 AS ret_10d,
                     adj_close / NULLIF(lag(adj_close, {RET_1M_LAG}) OVER w, 0) - 1 AS ret_1m
              FROM daily_bars
              WINDOW w AS (PARTITION BY ticker ORDER BY date)
            )
            SELECT ticker, date, ret_10d, ret_1m FROM r WHERE date IN ({ph})
            """,
            dates,
        ).fetchall()
    }

    meta = {
        t: (sector, mktcap)
        for t, sector, mktcap in con.execute(
            "SELECT ticker, sector, mktcap FROM universe"
        ).fetchall()
    }

    # Inclusion: renderable on the LATEST date (valid ign_pct AND valid ps) AND in universe.
    # Sort by mktcap desc so big caps paint first (small drawn on top, as the canvas expects).
    latest_tickers = []
    for t in meta:
        ig = ign_by.get((t, latest))
        vv = val_by.get((t, latest))
        if ig and ig[0] is not None and vv and _ps2(vv[0]) is not None:
            latest_tickers.append(t)
    latest_tickers.sort(key=lambda t: (meta[t][1] if meta[t][1] is not None else -1.0), reverse=True)
    if limit:
        latest_tickers = latest_tickers[:limit]

    all_ps: list[float] = []
    stocks = []
    for t in latest_tickers:
        pts = []
        for d in dates:
            ig = ign_by.get((t, d))
            vv = val_by.get((t, d))
            ign_pct = ig[0] if ig else None
            ps = _ps2(vv[0]) if vv else None   # rounded-to-2dp P/S, as stored (None if degenerate)
            if ign_pct is None or ps is None:
                pts.append(None)  # no renderable position this day (tween fades it in/out)
                continue
            all_ps.append(ps)
            persist = ig[2]
            candidate = persist is not None and ign_pct >= SEA_LEVEL and persist >= IGN_PERSIST_MIN
            ret = ret_by.get((t, d))
            period_end = vv[4]
            age = (d - period_end).days if period_end is not None else None
            pts.append({
                "ign_pct": _num(ign_pct, 1),
                "ignition": _num(ig[1], 2),
                "ign_persist_days": int(persist) if persist is not None else None,
                "candidate": bool(candidate),
                "ps": ps,   # already rounded to 2dp by _ps2 (and > 0)
                "evs": _num(vv[1], 2),
                "pe": _num(vv[2], 2),
                "ev_ebitda": _num(vv[3], 2),
                "ret_10d": _num(ret[0] if ret else None, 4),
                "ret_1m": _num(ret[1] if ret else None, 4),
                "vol_mult": _num(ig[3], 3),   # ig_vsurge (5/60 volume surge), stored col (C9)
                "freshness": freshness(age),
            })
        sector, mktcap = meta[t]
        stocks.append({
            "ticker": t,
            "sector": sector,
            "mktcap": _num(mktcap),     # raw USD (client renders radius √(mktcap/1e9), same as board)
            "themes": _themes(con, t, latest, has_themes),
            "pts": pts,
        })

    # log-scale x domain from the data (no hard-coded valuation threshold, §16). all_ps is
    # non-empty whenever any stock is included (inclusion requires a valid latest ps).
    x_domain = [round(min(all_ps), 4), round(max(all_ps), 4)] if all_ps else [0.1, 100.0]

    _self_check(stocks, dates, x_domain)

    return {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": _iso(latest),
        "axis": {"x_metric": "ps", "x_scale": "log", "y_metric": "ign_pct", "sea_level": SEA_LEVEL},
        "dates": [_iso(d) for d in dates],
        "x_domain": x_domain,
        "count": len(stocks),
        "stocks": stocks,
    }


def _self_check(stocks: list[dict], dates: list, x_domain: list) -> None:
    """Fail loudly here (not silently in the browser) if the contract breaks:

    1. every stock has len(pts)==len(dates) and a NON-NULL latest pt (renderable default);
    2. every non-null pt has ign_pct ∈ [0,100] and ps > 0 (log axis needs positive x);
    3. candidate ⇒ above the sea level (ign_pct >= SEA_LEVEL) — guards the gate/axis pairing;
    4. x_domain is a positive ordered interval (so the client's log scale is well-defined).
    """
    n = len(dates)
    for s in stocks:
        if len(s["pts"]) != n:
            raise RuntimeError(f"{s['ticker']}: pts length {len(s['pts'])} != n_days {n}")
        if s["pts"][-1] is None:
            raise RuntimeError(f"{s['ticker']}: latest pt is null but stock was included")
        for p in s["pts"]:
            if p is None:
                continue
            if p["ps"] is None or p["ps"] <= 0:
                raise RuntimeError(f"{s['ticker']}: non-null pt has ps={p['ps']} (log axis needs ps>0)")
            if p["ign_pct"] is None or not (0 <= p["ign_pct"] <= 100):
                raise RuntimeError(f"{s['ticker']}: ign_pct={p['ign_pct']} out of [0,100]")
            if p["candidate"] and p["ign_pct"] < SEA_LEVEL:
                raise RuntimeError(
                    f"{s['ticker']}: candidate below sea level (ign_pct={p['ign_pct']} < {SEA_LEVEL})"
                )
    if not (x_domain[0] > 0 and x_domain[0] <= x_domain[1]):
        raise RuntimeError(f"x_domain {x_domain} is not a positive ordered interval (log scale).")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M8 export: Ocean ignition×valuation daily ocean.json.")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output JSON path")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS, help="number of daily EOD snapshots")
    ap.add_argument("--limit", type=int, default=None, help="cap to top-N by mktcap (default: all)")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    ocean = build_ocean(con, n_days=args.days, limit=args.limit)
    con.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ocean, ensure_ascii=False, separators=(",", ":")) + "\n")

    kb = out.stat().st_size / 1024
    n_cand = sum(1 for s in ocean["stocks"] if s["pts"][-1]["candidate"])
    print(f"[ocean] {args.out}  as_of={ocean['as_of_date']}  days={len(ocean['dates'])}  "
          f"stocks={ocean['count']}  candidates_latest={n_cand}  "
          f"x_domain={ocean['x_domain']}  sea_level={ocean['axis']['sea_level']}  size={kb:.1f}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
