"""M3.3 rotation export: bucket_rrg + league_table -> web/public/data/rotation.json.

Rotation is the narrow-decide surface (PRD §9.4): the RS-Ratio multi-line chart + an
enriched league. This export assembles, per bucket (sector M3 / theme M4):
  - rs_ratio[] aligned to a shared weeks[] axis (oldest->newest; missing weeks null),
    the SAME alignment Ocean uses for pts[] so the client just zips series to axis;
  - the league snapshot: level / slope_4w / state + member aggregates (breadth /
    #at-52w-high / composite median / agg EV-S / multi-horizon rel return) — all from
    compute.rotation.league_table, the SAME source as Discovery/Ocean/Stock (C9);
  - members[]: top-N member tickers; the client filters board.json by scope=sector for
    the actual evidence cards, so rotation.json carries only the ticker list (DRY/C9);
  - etf: the SPDR ticker from ingest/sector_etf_map.txt (audit; bucket joins by name).

Constants n1/n2/k are surfaced in `params` (transparent reconstruction, PRD §10.4) —
NOT a claim to replicate StockCharts. RS-Momentum 归一量 is cut (PRD §16); momentum is
the rs_ratio slope, materialised as slope_4w (compute.rotation.slope_4w / infer_state).

Output (gitignored, derived nightly): web/public/data/rotation.json.
Schema: ROADMAP M3.3 contract; math: PRD §10.4; UX: §9.4.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ingest"))

import pandas as pd  # noqa: E402

from compute import db, rotation  # noqa: E402
import sector_etf  # noqa: E402

SCHEMA_VERSION = 1
DEFAULT_OUT = ROOT / "web" / "public" / "data" / "rotation.json"
DEFAULT_WEEKS = 52       # ~1y of weekly RS-Ratio points (PRD §9.4 / ROADMAP M3.3)
DEFAULT_MEMBERS = 12     # top-N member tickers per bucket (client filters board.json)
BUCKET_TYPE = "sector"


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


def _int(x):
    """JSON-safe int: NaN/None -> None."""
    f = _num(x)
    return int(f) if f is not None else None


def _etf_map() -> dict:
    """bucket (GICS name) -> SPDR ETF ticker, from ingest/sector_etf_map.txt (audit field)."""
    return {sector: etf for sector, etf in sector_etf.load_map(sector_etf.MAP_FILE)}


def _members(con, latest_date, top_n: int) -> dict:
    """Top-N member tickers per sector by composite on `latest_date`. The client filters
    board.json by scope=sector for the actual evidence cards (DRY/C9) — this carries the
    ticker list only."""
    rows = con.execute(
        """
        SELECT u.sector AS bucket, d.ticker
        FROM derived_daily d JOIN universe u ON u.ticker = d.ticker
        WHERE d.date = ? AND d.composite IS NOT NULL
        ORDER BY u.sector, d.composite DESC
        """,
        [latest_date],
    ).fetchall()
    out: dict[str, list] = {}
    for bucket, ticker in rows:
        lst = out.setdefault(bucket, [])
        if len(lst) < top_n:
            lst.append(ticker)
    return out


def build_rotation(con, bucket_type: str = BUCKET_TYPE, n_weeks: int = DEFAULT_WEEKS,
                   top_n: int = DEFAULT_MEMBERS, n1=None, n2=None, k=None) -> dict:
    """Assemble the rotation dict from bucket_rrg (recomputed) + league_table."""
    stats = rotation.compute_rotation(con, n1, n2, k, bucket_type)
    rrg = db.read_bucket_rrg(con, bucket_type)
    if len(rrg) == 0:
        raise RuntimeError(f"bucket_rrg empty for {bucket_type} — run sector ETF ingest first.")
    rrg["date"] = pd.to_datetime(rrg["date"])

    # Shared weeks axis: the most recent n_weeks across all buckets, oldest -> newest.
    all_weeks = sorted(rrg["date"].unique())[-n_weeks:]
    week_index = pd.DatetimeIndex(all_weeks)
    week_iso = [pd.Timestamp(w).strftime("%Y-%m-%d") for w in all_weeks]

    league = rotation.league_table(con, bucket_type)
    etf_map = _etf_map()
    latest = con.execute("SELECT max(date) FROM derived_daily").fetchone()[0]
    members = _members(con, latest, top_n) if latest is not None else {}

    buckets = []
    for _, lr in league.iterrows():
        b = lr["bucket"]
        sub = rrg[rrg["bucket"] == b].set_index("date")["rs_ratio"].reindex(week_index)
        buckets.append({
            "bucket_type": bucket_type,
            "bucket": b,
            "etf": etf_map.get(b),
            "rs_ratio": [_num(v, 3) for v in sub.to_numpy()],  # aligned to weeks[]; missing -> null
            "level": _num(lr["rs_ratio"], 2),
            "slope_4w": _num(lr["slope_4w"], 2),
            "state": lr["state"],
            "breadth_ma50": _num(lr.get("breadth_ma50"), 1),
            "breadth_ma200": _num(lr.get("breadth_ma200"), 1),
            "at_high": _int(lr.get("at_high")),
            "member_count": _int(lr.get("member_count")),
            "composite_median": _num(lr.get("composite_median"), 2),
            "agg_evs": _num(lr.get("agg_evs"), 2),
            "rel_ret_1m": _num(lr.get("rel_ret_1m"), 4),
            "rel_ret_3m": _num(lr.get("rel_ret_3m"), 4),
            "rel_ret_6m": _num(lr.get("rel_ret_6m"), 4),
            "members": members.get(b, []),
        })

    _self_check(buckets, week_iso)

    return {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": week_iso[-1] if week_iso else None,
        "benchmark": "SPX",
        "bucket_type": bucket_type,
        "params": {
            "basis": stats["params"]["basis"],
            "n1_ema": stats["params"]["n1_ema"],
            "n2_window": stats["params"]["n2_window"],
            "k": stats["params"]["k"],
        },
        "n_weeks": len(week_iso),
        "weeks": week_iso,
        "count": len(buckets),
        "buckets": buckets,
    }


def _self_check(buckets: list, weeks: list) -> None:
    """Fail loudly here (not in the browser) if the contract breaks:
    1. weeks is oldest->newest;
    2. every bucket's rs_ratio aligns to weeks[] (same length);
    3. the latest rs_ratio is non-null (a renderable line endpoint)."""
    n = len(weeks)
    if weeks != sorted(weeks):
        raise RuntimeError("weeks not oldest->newest")
    for b in buckets:
        if len(b["rs_ratio"]) != n:
            raise RuntimeError(f"{b['bucket']}: rs_ratio length {len(b['rs_ratio'])} != n_weeks {n}")
        if n and b["rs_ratio"][-1] is None:
            raise RuntimeError(f"{b['bucket']}: latest rs_ratio is null (no renderable endpoint)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M3.3 export: Rotation rotation.json.")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output JSON path")
    ap.add_argument("--weeks", type=int, default=DEFAULT_WEEKS, help="weekly RS-Ratio points (default 52)")
    ap.add_argument("--members", type=int, default=DEFAULT_MEMBERS, help="top-N member tickers per bucket")
    ap.add_argument("--bucket-type", default=BUCKET_TYPE, help="sector (M3) | theme (M4)")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    rot = build_rotation(con, bucket_type=args.bucket_type, n_weeks=args.weeks, top_n=args.members)
    con.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rot, ensure_ascii=False, separators=(",", ":")) + "\n")

    states: dict[str, int] = {}
    for b in rot["buckets"]:
        states[b["state"]] = states.get(b["state"], 0) + 1
    kb = out.stat().st_size / 1024
    print(f"[rotation] {args.out}  as_of={rot['as_of_date']}  buckets={rot['count']}  "
          f"weeks={rot['n_weeks']}  states={states}  size={kb:.1f}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
