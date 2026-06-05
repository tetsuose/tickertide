"""M0.3 compute orchestrator: daily_bars + spx_daily -> derived_daily.

Usage:
    python3 compute/run.py [--k 0.5] [--db data/tickertide.duckdb] [--min-bars 60]

Per-stock time-series metrics (pandas, compute/signals.py) are concatenated, then
the cross-sectional work runs in DuckDB:
  - rs_pct  = PERCENT_RANK() over each date (the IBD-style cross-sectional RS)
  - rs_accel = rs_pct[t] - rs_pct[t-21]
  - components c_* clamped to [0,1]; composite = 100·Σ wᵢ·cᵢ at the given k
  - rank_in_universe = RANK() by composite per date
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from compute import db, signals  # noqa: E402


def compute_all(con, k: float = 0.5, min_bars: int = 60) -> dict:
    """Recompute derived_daily for every ticker that has bars. Returns counts."""
    spx = db.read_spx(con)
    if len(spx) == 0:
        raise RuntimeError("spx_daily is empty — run ingest first (needs the benchmark).")

    tickers = db.bar_tickers(con)
    frames, skipped = [], 0
    for t in tickers:
        bars = db.read_bars(con, t)
        if len(bars) < min_bars:
            skipped += 1
            continue
        m = signals.compute_metrics(bars, spx)
        m["ticker"] = t
        frames.append(m)

    if not frames:
        raise RuntimeError("no ticker had enough bars to compute metrics.")
    allm = pd.concat(frames, ignore_index=True)

    w = signals.weights(k)
    con.register("allm", allm)
    db.clear_derived(con)
    con.execute(
        f"""
        INSERT OR REPLACE INTO derived_daily
        WITH x AS (
          SELECT *, PERCENT_RANK() OVER (PARTITION BY date ORDER BY rs_raw) * 100 AS rs_pct
          FROM allm WHERE rs_raw IS NOT NULL
        ),
        y AS (
          SELECT *, rs_pct - LAG(rs_pct, 21) OVER (PARTITION BY ticker ORDER BY date) AS rs_accel
          FROM x
        ),
        z AS (
          SELECT *,
            LEAST(1, GREATEST(0, rs_pct / 100.0))                      AS c_rs,
            LEAST(1, GREATEST(0, high_prox))                           AS c_high,
            LEAST(1, GREATEST(0, trend_quality))                       AS c_trend,
            LEAST(1, GREATEST(0, (vol_ratio - 1.0) / 0.6 + 0.5))       AS c_vol,
            LEAST(1, GREATEST(0, COALESCE(rs_accel, 0) / 100.0 + 0.5)) AS c_accel
          FROM y
        ),
        c AS (
          SELECT *,
            100 * ({w['rs']}*c_rs + {w['high']}*c_high + {w['trend']}*c_trend
                   + {w['vol']}*c_vol + {w['accel']}*c_accel) AS composite
          FROM z
        )
        SELECT ticker, date, ret_63, ret_126, rs_raw, rs_pct, rs_accel, high_prox,
               ma50, ma150, ma200, trend_quality, vol_ratio, ud_vol_ratio,
               ewmac_fast, ewmac_slow, c_rs, c_high, c_trend, c_vol, c_accel, composite,
               CAST(RANK() OVER (PARTITION BY date ORDER BY composite DESC) AS INTEGER) AS rank_in_universe
        FROM c
        """
    )
    con.unregister("allm")

    rows = db.count(con, "derived_daily")
    tk = con.execute("SELECT count(DISTINCT ticker) FROM derived_daily").fetchone()[0]
    return {"tickers_in": len(tickers), "tickers_computed": len(frames),
            "skipped": skipped, "rows": rows, "derived_tickers": tk}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M0.3 compute: derived_daily + composite.")
    ap.add_argument("--k", type=float, default=0.5, help="early<->reliable knob for the composite snapshot")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--min-bars", type=int, default=60, help="skip tickers with fewer bars")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    print(f"[compute] k={args.k} reading daily_bars ...")
    stats = compute_all(con, k=args.k, min_bars=args.min_bars)
    print(f"[compute] tickers in={stats['tickers_in']} computed={stats['tickers_computed']} "
          f"skipped={stats['skipped']} -> derived_daily rows={stats['rows']} tickers={stats['derived_tickers']}")

    latest = con.execute("SELECT max(date) FROM derived_daily").fetchone()[0]
    print(f"[compute] latest date = {latest}; top 5 by composite:")
    for r in con.execute(
        "SELECT ticker, round(composite,1), round(rs_pct,0), round(c_high,2), round(c_trend,2), rank_in_universe "
        "FROM derived_daily WHERE date = ? ORDER BY composite DESC LIMIT 5", [latest]
    ).fetchall():
        print(f"    {r[0]:6} composite={r[1]:5}  rs_pct={r[2]:3}  c_high={r[3]}  c_trend={r[4]}  rank={r[5]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
