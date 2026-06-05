"""M2.1 ocean export: DuckDB weekly snapshots -> web/public/data/ocean.json.

Ocean is the wide-explore surface (PRD §9.2): a canvas scatter of the whole
universe on a fixed RS×Valuation plane, scrubbed week by week with pinned trails.
Unlike the Discovery board (one latest snapshot per stock), Ocean needs a weekly
POSITION SEQUENCE per stock, so the client can scrub the scrubber and draw trails.

Each stock carries `pts[]` aligned to `weeks[]` (oldest→newest), one point per week:
  - rs  : derived_daily.rs_pct  (0-100 cross-sectional RS percentile, x-axis;
          the SAME column Discovery/Stock show, so a point is traceable — C9)
  - val : common-vintage valuation percentile (0-100, y-axis, bottom=cheap;
          PRD §10.5). Computed by compute.valuation.common_vintage — the SAME
          function the M5 Valuation screener will reuse, so the percentile口径
          never forks between the two surfaces (C9; M2 defines, M5 refines the
          coverage threshold).
  - ps  : the raw P/S multiple behind `val` (for the hover tip, PRD §9.2), so the
          number that produced the y-position travels with the point.

Week-ends are the last trading day of each ISO week (date_trunc('week', …)); the
newest week-end is the latest snapshot (== board.json as_of), so Ocean's current
positions match the Discovery/Stock numbers exactly.

Inclusion rule: a stock is exported iff it has BOTH a non-null rs AND a fresh
common-vintage val on the LATEST week — i.e. it has a renderable (x,y) on the
default view (so AC-M2 "≥500 points render" holds). Stale / n.m. / no-fundamentals
stocks have no y-coordinate and are absent (consistent with §10.5 "stale 不进
percentile"). For OLDER weeks a stock may be stale or lack warm history → that
week's pt is `null` (the trail simply doesn't extend there; positions are never
fabricated).

Output (gitignored, derived nightly): web/public/data/ocean.json.
Math spec: PRD §10.2 (rs_pct) / §10.5 (common-vintage); UX: §9.2; schema: §12.
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

from compute import db, valuation  # noqa: E402

SCHEMA_VERSION = 1
DEFAULT_OUT = ROOT / "web" / "public" / "data" / "ocean.json"

DEFAULT_WEEKS = 14       # ~1 quarter of weekly snapshots (aligns with the UX contract)
DEFAULT_METRIC = "ps"    # default valuation axis (PRD §9.2/§10.5: P/S)
FRESH_DAYS = 95          # common-vintage freshness cutoff (PRD §10.5/§9.5)


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
    """Point-in-time theme memberships (PRD §7). Empty until M4; table may not exist."""
    if not has_themes:
        return []
    rows = con.execute(
        "SELECT theme, exposure FROM theme_membership "
        "WHERE ticker = ? AND as_of_date <= ? ORDER BY exposure DESC NULLS LAST",
        [ticker, snap],
    ).fetchall()
    return [{"theme": t, "exposure": _num(e, 4)} for t, e in rows]


def week_ends(con, n_weeks: int) -> list:
    """The last trading day of each of the most recent `n_weeks` ISO weeks, oldest
    first. date_trunc('week', …) buckets by Monday-anchored ISO week (no year-edge
    collision); max(date) per bucket is that week's last traded day. The newest
    equals max(derived_daily.date) = the latest snapshot."""
    rows = con.execute(
        """
        SELECT wk_end FROM (
          SELECT max(date) AS wk_end
          FROM (SELECT DISTINCT date FROM derived_daily)
          GROUP BY date_trunc('week', date)
        ) ORDER BY wk_end DESC LIMIT ?
        """,
        [int(n_weeks)],
    ).fetchall()
    return [r[0] for r in rows][::-1]


def build_ocean(con, n_weeks: int = DEFAULT_WEEKS, metric: str = DEFAULT_METRIC,
                fresh_days: int = FRESH_DAYS, limit: int | None = None) -> dict:
    """Assemble the Ocean weekly-snapshot dict from DuckDB."""
    if metric not in valuation.VINTAGE_METRICS:
        raise ValueError(f"metric {metric!r} not in {valuation.VINTAGE_METRICS}")
    if db.count(con, "derived_daily") == 0:
        raise RuntimeError("derived_daily is empty — run `make compute` first.")
    weeks = week_ends(con, n_weeks)
    if not weeks:
        raise RuntimeError("no trading dates in derived_daily.")
    latest = weeks[-1]
    has_themes = _table_exists(con, "theme_membership")

    ph = ",".join(["?"] * len(weeks))
    # rs (x) for every (ticker, week) — same column Discovery/Stock surface (C9).
    rs_by = {
        (t, d): v
        for t, d, v in con.execute(
            f"SELECT ticker, date, rs_pct FROM derived_daily WHERE date IN ({ph})", weeks
        ).fetchall()
    }
    # raw metric (for the tip) for every (ticker, week). `metric` is allowlist-checked above.
    ps_by = {
        (t, d): v
        for t, d, v in con.execute(
            f"SELECT ticker, date, {metric} FROM valuation_daily WHERE date IN ({ph})", weeks
        ).fetchall()
    }
    # val (y) per week = common-vintage percentile, the SAME function M5 reuses (C9).
    val_by, fresh_latest, stale_latest = {}, 0, 0
    for wk in weeks:
        _, pct, n_fresh, n_stale = valuation.common_vintage(con, metric, wk, fresh_days)
        val_by[wk] = pct
        if wk == latest:
            fresh_latest, stale_latest = n_fresh, n_stale

    meta = {
        t: (sector, mktcap)
        for t, sector, mktcap in con.execute(
            "SELECT ticker, sector, mktcap FROM universe"
        ).fetchall()
    }

    # Candidates: renderable on the latest week (both x and y present), present in
    # universe. Sort by mktcap desc so big caps paint first (small drawn on top).
    val_latest = val_by[latest]
    cands = [
        t for t in val_latest
        if rs_by.get((t, latest)) is not None and t in meta
    ]
    cands.sort(key=lambda t: (meta[t][1] if meta[t][1] is not None else -1.0), reverse=True)
    if limit:
        cands = cands[:limit]

    stocks = []
    for t in cands:
        pts = []
        for wk in weeks:
            r = rs_by.get((t, wk))
            v = val_by[wk].get(t)
            if r is None or v is None:
                pts.append(None)
            else:
                pts.append({"rs": _num(r, 1), "val": _num(v, 1), "ps": _num(ps_by.get((t, wk)), 2)})
        sector, mktcap = meta[t]
        stocks.append({
            "ticker": t,
            "sector": sector,
            "mktcap": _num(mktcap),     # raw USD, same unit as board.json (client renders √(mktcap/1e9))
            "themes": _themes(con, t, latest, has_themes),
            "pts": pts,
        })

    _self_check(stocks, weeks, val_latest, ps_by, latest)

    return {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": _iso(latest),
        "metric": metric,
        "fresh_days": fresh_days,
        "n_weeks": len(weeks),
        "weeks": [_iso(w) for w in weeks],
        "count": len(stocks),
        "fresh_cohort_latest": fresh_latest,
        "stale_excluded_latest": stale_latest,
        "stocks": stocks,
    }


def _self_check(stocks: list[dict], weeks: list, val_latest: dict, ps_by: dict, latest) -> None:
    """Fail loudly here (not silently in the browser) if the contract breaks.

    1. every stock has len(pts)==len(weeks) and a NON-NULL latest pt (renderable);
    2. val orientation is bottom=cheap — the cheapest-P/S stock outranks the
       dearest, i.e. low val == cheap (guards an accidental sort flip vs §10.5).
    """
    n = len(weeks)
    for s in stocks:
        if len(s["pts"]) != n:
            raise RuntimeError(f"{s['ticker']}: pts length {len(s['pts'])} != n_weeks {n}")
        if s["pts"][-1] is None:
            raise RuntimeError(f"{s['ticker']}: latest pt is null but stock was included")

    cohort = [(t, ps_by.get((t, latest))) for t in val_latest if ps_by.get((t, latest)) is not None]
    if len(cohort) > 1:
        cheap = min(cohort, key=lambda x: x[1])[0]
        dear = max(cohort, key=lambda x: x[1])[0]
        if val_latest[cheap] > val_latest[dear]:
            raise RuntimeError(
                f"val orientation flipped: cheapest {cheap} (val={val_latest[cheap]:.1f}) ranks above "
                f"dearest {dear} (val={val_latest[dear]:.1f}); §10.5 requires bottom=cheap."
            )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M2.1 export: Ocean weekly snapshots ocean.json.")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output JSON path")
    ap.add_argument("--weeks", type=int, default=DEFAULT_WEEKS, help="number of weekly snapshots")
    ap.add_argument("--metric", default=DEFAULT_METRIC, choices=valuation.VINTAGE_METRICS,
                    help="valuation metric for the y-axis percentile (default ps)")
    ap.add_argument("--fresh-days", type=int, default=FRESH_DAYS, help="common-vintage freshness cutoff")
    ap.add_argument("--limit", type=int, default=None, help="cap to top-N by mktcap (default: all)")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    ocean = build_ocean(con, n_weeks=args.weeks, metric=args.metric,
                        fresh_days=args.fresh_days, limit=args.limit)
    con.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ocean, ensure_ascii=False, separators=(",", ":")) + "\n")

    kb = out.stat().st_size / 1024
    print(f"[ocean] {args.out}  as_of={ocean['as_of_date']}  weeks={ocean['n_weeks']}  "
          f"stocks={ocean['count']}  metric={ocean['metric']}  "
          f"fresh={ocean['fresh_cohort_latest']}  stale_excluded={ocean['stale_excluded_latest']}  "
          f"size={kb:.1f}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
