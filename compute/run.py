"""M0.3 compute orchestrator: daily_bars + spx_daily -> derived_daily.

Usage:
    python3 compute/run.py [--k 0.5] [--db data/tickertide.duckdb] [--min-bars 60]

Per-stock time-series metrics (pandas, compute/signals.py + compute/ignition.py) are
concatenated, then the cross-sectional work runs in DuckDB:
  - rs_pct  = PERCENT_RANK() over each date (the IBD-style cross-sectional RS)
  - rs_accel = rs_pct[t] - rs_pct[t-21]
  - components c_* clamped to [0,1]; composite = 100·Σ wᵢ·cᵢ at the given k
  - rank_in_universe = RANK() by composite per date
  - ignition (PRD §10.8): each of the 5 short-window components is PERCENT_RANK()'d
    per date to [0,1] and averaged -> `ignition`; `ign_pct` = PERCENT_RANK() of that
    per date; `ign_persist_days` = consecutive days (incl. today) with ign_pct>=90
    (top-decile persistence — the precision filter, PRD §10.8.2).
The two engines share this one per-stock pass and land in the SAME derived_daily row (C9).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from compute import breakout, db, ignition, signals  # noqa: E402


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
        m = signals.compute_metrics(bars, spx)       # composite inputs (long windows) — RETIRED, transitional
        g = ignition.compute_ignition(bars, spx)     # ignition components (short windows) — RETIRED, transitional
        b = breakout.compute_breakout(bars)          # base→breakout features (core engine, PRD §10.8)
        # All engines share the SAME bars (C9) and emit a str `date`; merge per ticker so
        # each (ticker,date) row carries every engine's per-stock features. composite/ignition
        # are kept transitionally (expand-then-contract) until export/web stop reading them.
        m = m.merge(g, on="date", how="left").merge(b, on="date", how="left")
        m["ticker"] = t
        frames.append(m)

    if not frames:
        raise RuntimeError("no ticker had enough bars to compute metrics.")
    allm = pd.concat(frames, ignore_index=True)

    w = signals.weights(k)
    con.register("allm", allm)
    db.ensure_breakout_columns(con)   # migrate existing derived_daily to carry brk_* (§10.8)
    db.clear_derived(con)
    con.execute(
        f"""
        INSERT OR REPLACE INTO derived_daily
        WITH x AS (
          SELECT *,
            PERCENT_RANK() OVER (PARTITION BY date ORDER BY rs_raw) * 100 AS rs_pct,
            -- ignition: cross-sectional percentile-rank of each short-window component
            -- to [0,1] per date (PRD §10.8.1); NULL components stay out of their own rank.
            PERCENT_RANK() OVER (PARTITION BY date ORDER BY ig_accel)   AS p_accel,
            PERCENT_RANK() OVER (PARTITION BY date ORDER BY ig_expand)  AS p_expand,
            PERCENT_RANK() OVER (PARTITION BY date ORDER BY ig_vsurge)  AS p_vsurge,
            PERCENT_RANK() OVER (PARTITION BY date ORDER BY ig_breakout) AS p_breakout,
            PERCENT_RANK() OVER (PARTITION BY date ORDER BY ig_rsturn)  AS p_rsturn,
            -- base→breakout (core, PRD §10.8): cross-sectional percentile of the per-stock
            -- raw strength → brk_strength_pct (drives Ocean y-axis / Breakouts ranking).
            PERCENT_RANK() OVER (PARTITION BY date ORDER BY brk_strength) * 100 AS brk_strength_pct
          FROM allm WHERE rs_raw IS NOT NULL
        ),
        y AS (
          SELECT *,
            rs_pct - LAG(rs_pct, 21) OVER (PARTITION BY ticker ORDER BY date) AS rs_accel,
            -- equal-weight average of the 5 ranked components -> ignition (PRD §10.8.1).
            100 * (p_accel + p_expand + p_vsurge + p_breakout + p_rsturn) / 5.0 AS ignition
          FROM x
        ),
        z AS (
          SELECT *,
            LEAST(1, GREATEST(0, rs_pct / 100.0))                      AS c_rs,
            LEAST(1, GREATEST(0, high_prox))                           AS c_high,
            LEAST(1, GREATEST(0, trend_quality))                       AS c_trend,
            LEAST(1, GREATEST(0, (vol_ratio - 1.0) / 0.6 + 0.5))       AS c_vol,
            LEAST(1, GREATEST(0, COALESCE(rs_accel, 0) / 100.0 + 0.5)) AS c_accel,
            -- ign_pct: cross-sectional percentile of the ignition score, per date (PRD §10.8.2).
            PERCENT_RANK() OVER (PARTITION BY date ORDER BY ignition) * 100 AS ign_pct
          FROM y
        ),
        lit AS (
          SELECT *, CASE WHEN ign_pct >= 90 THEN 1 ELSE 0 END AS is_lit
          FROM z
        ),
        grp AS (
          -- islands: a run counter minus a run-of-lit counter is constant within one
          -- consecutive top-decile streak per ticker (gaps reset it). PRD §10.8.2.
          SELECT *,
            ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date)
            - ROW_NUMBER() OVER (PARTITION BY ticker, is_lit ORDER BY date) AS streak_grp
          FROM lit
        ),
        persist AS (
          SELECT *,
            CASE WHEN is_lit = 1
                 THEN CAST(ROW_NUMBER() OVER (PARTITION BY ticker, is_lit, streak_grp ORDER BY date) AS INTEGER)
                 ELSE 0 END AS ign_persist_days
          FROM grp
        ),
        c AS (
          SELECT *,
            100 * ({w['rs']}*c_rs + {w['high']}*c_high + {w['trend']}*c_trend
                   + {w['vol']}*c_vol + {w['accel']}*c_accel) AS composite
          FROM persist
        )
        SELECT ticker, date, ret_63, ret_126, rs_raw, rs_pct, rs_accel, high_prox,
               ma50, ma150, ma200, trend_quality, vol_ratio, ud_vol_ratio,
               ewmac_fast, ewmac_slow, c_rs, c_high, c_trend, c_vol, c_accel, composite,
               CAST(RANK() OVER (PARTITION BY date ORDER BY composite DESC) AS INTEGER) AS rank_in_universe,
               ig_accel, ig_expand, ig_vsurge, ig_breakout, ig_rsturn,
               ignition, ign_pct, ign_persist_days,
               brk_tau_date, brk_base_slope, brk_brk_slope, brk_drift_step, brk_fit_gain,
               brk_clearance, brk_vcp, brk_vsurge, brk_strength, brk_strength_pct
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
    print("[compute] top 5 by base→breakout strength (core, PRD §10.8; brk_pct = cross-sectional rank):")
    for r in con.execute(
        "SELECT ticker, brk_tau_date, round(brk_strength_pct,0), round(brk_drift_step,2), "
        "round(brk_fit_gain,2), round(brk_clearance,2) "
        "FROM derived_daily WHERE date = ? AND brk_strength > 0 ORDER BY brk_strength DESC LIMIT 5", [latest]
    ).fetchall():
        print(f"    {r[0]:6} τ={r[1]}  brk_pct={r[2]:3}  drift={r[3]}  fit={r[4]}  clr={r[5]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
